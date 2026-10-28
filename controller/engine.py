"""Controller engine: the QThread running the capture -> control loop.

Separation of concerns
----------------------
* The engine *orchestrates*; it does no geometry or classification maths itself.
* All mouse actions go through :class:`~controller.mouse_controller.MouseController`
  and are gated by :class:`~controller.safety_manager.SafetyManager`.
* Qt signals carry frames, metrics and status to the UI thread; no widget is
  ever touched from this thread.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone

import cv2
import numpy as np
from PySide6.QtCore import QThread, Signal

from app import constants as C
from app.config import AppConfig
from controller.coordinate_mapper import CoordinateMapper
from controller.cursor_smoother import CursorSmoother
from controller.mouse_controller import LEFT, MouseController
from controller.safety_manager import SafetyManager
from controller.system_controller import SystemController
from gestures.gesture_classifier import GestureClassifier
from gestures.gesture_config import GestureRule
from gestures.gesture_state import GestureStateMachine, StateMachineOutput
from utils.logger import get_logger
from utils.metrics import MetricsCollector, MetricsSnapshot
from utils.platform_utils import primary_screen_size
from vision.camera_manager import CameraError, CameraManager
from vision.frame_processor import HAND_CONNECTIONS, FrameProcessor
from vision.hand_tracker import HandTracker
from vision.landmark_processor import cursor_anchor
from vision.types import HandObservation

log = get_logger(__name__)


class ControllerEngine(QThread):
    """Runs the webcam pipeline and drives the system cursor."""

    frame_ready = Signal(object)         # annotated BGR np.ndarray
    metrics_ready = Signal(object)       # MetricsSnapshot
    status_changed = Signal(str)         # human-readable status line
    error_occurred = Signal(str)         # fatal error for this run
    gesture_changed = Signal(str)        # gesture id
    state_changed = Signal(str)          # controller state id
    paused_changed = Signal(bool)
    session_ended = Signal(object, object)  # (started_datetime, MetricsSnapshot)
    screenshot_taken = Signal(str)       # absolute path of a just-saved screenshot
    level_changed = Signal(str, int, bool)  # (volume|brightness, 0-100, muted)

    def __init__(
        self,
        config: AppConfig,
        mouse: MouseController,
        safety: SafetyManager,
        rules: dict[str, GestureRule] | None = None,
        camera=None,
        tracker=None,
        system=None,
    ) -> None:
        super().__init__()
        self.config = config
        self.mouse = mouse
        self.safety = safety
        self.rules = rules or {}
        # Injection points for headless integration tests.
        self._camera_override = camera
        self._tracker_override = tracker
        self.system: SystemController = system if system is not None else SystemController()

        self.classifier = GestureClassifier(config.gestures)
        self.machine = GestureStateMachine(config.gestures, self.rules)
        self.mapper = CoordinateMapper(
            screen_size=primary_screen_size,
            roi_fraction=config.cursor.roi_fraction,
            invert_x=config.cursor.invert_x,
            invert_y=config.cursor.invert_y,
            speed=config.cursor.speed,
        )
        self.smoother = CursorSmoother(
            smoothing=config.cursor.smoothing,
            use_one_euro=config.cursor.use_one_euro,
            min_cutoff=config.cursor.one_euro_min_cutoff,
            beta=config.cursor.one_euro_beta,
        )
        self.metrics = MetricsCollector()
        self._brightness_warned = False

        self._stop_requested = False
        self._camera: CameraManager | None = None
        self._tracker: HandTracker | None = None
        self._processor: FrameProcessor | None = None
        self._started_at: datetime | None = None
        self._last_preview_at = 0.0
        self._last_gesture = ""
        self._last_state = ""

    # -- control -------------------------------------------------------------
    def request_stop(self) -> None:
        """Ask the loop to exit; always releases held buttons."""
        self._stop_requested = True

    def emergency_stop(self) -> None:
        self.safety.emergency_stop("engine")
        self._stop_requested = True

    def pause(self) -> None:
        self.safety.pause("user")

    def resume(self) -> None:
        self.safety.resume()

    def apply_config(self, config: AppConfig) -> None:
        """Hot-apply a new configuration without restarting the thread."""
        self.config = config
        self.classifier.cfg = config.gestures
        self.machine.cfg = config.gestures
        self.mapper.update(
            roi_fraction=config.cursor.roi_fraction,
            invert_x=config.cursor.invert_x,
            invert_y=config.cursor.invert_y,
            speed=config.cursor.speed,
        )
        self.smoother.update(
            smoothing=config.cursor.smoothing,
            use_one_euro=config.cursor.use_one_euro,
            min_cutoff=config.cursor.one_euro_min_cutoff,
            beta=config.cursor.one_euro_beta,
        )
        if self._tracker is not None:
            self._tracker.reconfigure(
                max_num_hands=config.tracking.max_num_hands,
                detection_confidence=config.tracking.detection_confidence,
                tracking_confidence=config.tracking.tracking_confidence,
            )
        self.mouse.set_failsafe(config.safety.pyautogui_failsafe)
        self.safety.cfg = config.safety

    # -- main loop -----------------------------------------------------------
    def run(self) -> None:  # noqa: C901 - a single ordered pipeline is clearest here
        self._stop_requested = False
        self._started_at = datetime.now(timezone.utc)
        self.metrics.mark_start()
        self.machine.reset()
        self.smoother.reset()
        self.classifier.reset()
        self.mouse.set_failsafe(self.config.safety.pyautogui_failsafe)

        camera = self._camera_override or CameraManager()
        self._camera = camera
        try:
            if self._camera_override is None:
                camera.open(
                    self.config.camera.device_index,
                    self.config.camera.width,
                    self.config.camera.height,
                    self.config.camera.max_fps,
                )
        except CameraError as exc:
            self.error_occurred.emit(str(exc))
            self.status_changed.emit(f"Camera error: {exc}")
            self._finish()
            return

        tracker = self._tracker_override or HandTracker(
            max_num_hands=self.config.tracking.max_num_hands,
            detection_confidence=self.config.tracking.detection_confidence,
            tracking_confidence=self.config.tracking.tracking_confidence,
        )
        self._tracker = tracker
        if not tracker.ready:
            msg = tracker.error or "Hand tracker failed to initialise."
            self.error_occurred.emit(msg)
            self.status_changed.emit(f"Tracking error: {msg}")
            camera.close()
            self._finish()
            return

        self._processor = FrameProcessor(camera, tracker)
        self.status_changed.emit("Controller running")
        self.state_changed.emit(C.STATE_TRACKING)

        frame_interval = 1.0 / max(1, self.config.camera.max_fps)
        prev_anchor: tuple[float, float] | None = None
        consecutive_failures = 0

        while not self._stop_requested:
            loop_start = time.perf_counter()
            try:
                observation, annotated, latency = self._processor.process_once(
                    mirror=self.config.camera.mirror_preview,
                    show_landmarks=self.config.ui.show_landmarks,
                )
                consecutive_failures = 0
            except CameraError as exc:
                consecutive_failures += 1
                log.warning("Camera read failed (%d/%d): %s",
                            consecutive_failures, 3, exc)
                if consecutive_failures >= 3:
                    self.error_occurred.emit(
                        "Camera stopped responding. Check that it is connected "
                        "and not in use by another application."
                    )
                    self.status_changed.emit("Camera lost")
                    break
                time.sleep(0.05)
                continue

            self.metrics.record_frame(latency)

            # --- classify + arbitrate --------------------------------------
            classification = self.classifier.classify(observation)
            gesture = classification.gesture

            # Keep the state machine's paused flag in sync with the
            # SafetyManager (hotkey / focus-loss pause must gate gestures too).
            if self.safety.paused and not self.machine.paused:
                self.machine.force_pause()
            elif not self.safety.paused and self.machine.paused:
                self.machine.resume()

            anchor: tuple[float, float] | None = None
            pinch_distance: float | None = None
            if observation is not None:
                anchor = cursor_anchor(observation)
                self.metrics.hands_detected = 1
                self.metrics.tracking_confidence = classification.confidence
                if classification.fingers is not None:
                    pinch_distance = classification.fingers.pinch_distance
                self.metrics.pinch_distance = pinch_distance or 0.0
            else:
                self.metrics.hands_detected = 0
                self.metrics.tracking_confidence = 0.0
                self.metrics.pinch_distance = 0.0
                self.metrics.record_tracking_loss()
                prev_anchor = None
                self.smoother.reset()  # don't slide in from a stale position

            output = self.machine.update(gesture, hand_position=anchor)

            # --- execute (only when safety allows) -------------------------
            if self.safety.may_act():
                self._execute(output, observation, anchor, prev_anchor)
            elif self.machine.dragging or self.mouse.held_buttons:
                # Defensive: never keep a button held while not allowed to act.
                self.mouse.release_all()
                self.machine.reset(paused=self.safety.paused)

            if observation is not None:
                prev_anchor = anchor

            # --- emit preview + metrics (throttled) ------------------------
            now = time.perf_counter()
            preview_interval = 1.0 / max(1, self.config.ui.preview_throttle_fps)
            if now - self._last_preview_at >= preview_interval:
                self._last_preview_at = now
                self.frame_ready.emit(self._draw_hud(annotated, gesture, classification.confidence))

            if gesture != self._last_gesture:
                self._last_gesture = gesture
                self.gesture_changed.emit(gesture)
            if output.state != self._last_state:
                self._last_state = output.state
                self.state_changed.emit(output.state)
            self.paused_changed.emit(self.safety.paused)

            self.metrics_ready.emit(
                self.metrics.snapshot(
                    gesture=gesture,
                    state=output.state,
                    paused=self.safety.paused,
                    running=True,
                    tracking_confidence=classification.confidence,
                    hands_detected=self.metrics.hands_detected,
                    pinch_distance=self.metrics.pinch_distance,
                )
            )

            # --- pace to target FPS ----------------------------------------
            elapsed = time.perf_counter() - loop_start
            remaining = frame_interval - elapsed
            if remaining > 0:
                time.sleep(remaining)

        self._finish()

    # -- action execution ----------------------------------------------------
    def _execute(
        self,
        output: StateMachineOutput,
        observation: HandObservation | None,
        anchor: tuple[float, float] | None,
        prev_anchor: tuple[float, float] | None,
    ) -> None:
        action = output.action
        if action == C.ACTION_NONE:
            return

        if action in (C.ACTION_MOVE, C.ACTION_DRAG_MOVE):
            self._move_cursor(anchor)
            return

        if action == C.ACTION_LEFT_CLICK:
            self.mouse.click(LEFT)
            self.metrics.record_click()
            return

        if action == C.ACTION_RIGHT_CLICK:
            self.mouse.click("right")
            self.metrics.record_right_click()
            return

        if action == C.ACTION_DOUBLE_CLICK:
            self.mouse.double_click()
            self.metrics.record_double_click()
            return

        if action == C.ACTION_DRAG_START:
            self.mouse.press_down(LEFT)
            self.metrics.record_drag()
            self._move_cursor(anchor)  # align cursor before dragging
            return

        if action == C.ACTION_DRAG_END:
            self.mouse.release(LEFT)
            return

        if action == C.ACTION_SCROLL_V:
            self.mouse.scroll_vertical(output.scroll_dy)
            self.metrics.record_scroll(abs(output.scroll_dy))
            return

        if action == C.ACTION_SCROLL_H:
            self.mouse.scroll_horizontal(output.scroll_dx)
            self.metrics.record_scroll(abs(output.scroll_dx))
            return

        # --- system actions (screenshot / volume / brightness / media) -------
        if action == C.ACTION_SCREENSHOT:
            path = self.system.screenshot()
            self.status_changed.emit(
                f"Screenshot saved: {path.name}" if path else "Screenshot failed."
            )
            if path is not None:
                self.screenshot_taken.emit(str(path))
            return

        if action == C.ACTION_VOLUME_UP:
            self.system.volume_up()
            self._emit_level("volume")
            return

        if action == C.ACTION_VOLUME_DOWN:
            self.system.volume_down()
            self._emit_level("volume")
            return

        if action == C.ACTION_VOLUME_MUTE:
            self.system.volume_mute()
            self._emit_level("volume")
            return

        if action == C.ACTION_MEDIA_TOGGLE:
            self.system.media_toggle()
            return

        if action == C.ACTION_BRIGHTNESS_UP:
            self._apply_brightness(+1)
            return

        if action == C.ACTION_BRIGHTNESS_DOWN:
            self._apply_brightness(-1)
            return

        if action == C.ACTION_PAUSE:
            self.safety.pause(output.reason)
            return

        if action == C.ACTION_RESUME:
            self.safety.resume()
            return

    def _move_cursor(self, anchor: tuple[float, float] | None) -> None:
        """Map, smooth and apply a dead zone before moving the real cursor."""
        if anchor is None:
            return
        nx, ny = anchor
        try:
            # ROI + speed + inversion -> virtual screen space.
            vx, vy = self.mapper.to_virtual(nx, ny)
        except ValueError:
            return

        # Smooth in virtual space so the ROI/speed mapping stays correct.
        sx, sy = self.smoother(vx, vy, time.perf_counter())

        try:
            px, py = self.mapper.virtual_to_pixels(sx, sy)
        except ValueError:
            return

        # Dead-zone filter in pixel space: ignores sub-threshold jitter.
        width, _ = primary_screen_size()
        last = self.mouse.position()
        if last is not None:
            dead_px = self.config.cursor.movement_deadzone * width
            if abs(px - last[0]) < dead_px and abs(py - last[1]) < dead_px:
                return
        self.mouse.move_to(px, py)

    def _apply_brightness(self, direction: int) -> None:
        """Raise/lower brightness once, reporting an unsupported display."""
        ok = self.system.brightness_up() if direction > 0 else self.system.brightness_down()
        if not ok and not self._brightness_warned:
            self._brightness_warned = True
            self.status_changed.emit(
                "Brightness control is not available on this display."
            )
        if ok:
            self._emit_level("brightness")

    def _emit_level(self, kind: str) -> None:
        """Ask the UI to show the volume/brightness indicator.

        Injected test doubles simply do not expose a level, so no indicator is
        shown for them; an unknown level (``None``) also keeps it hidden rather
        than displaying a fabricated value.
        """
        level = getattr(self.system, f"{kind}_level", None)
        if level is None:
            return
        muted = bool(getattr(self.system, "muted", False)) if kind == "volume" else False
        self.level_changed.emit(kind, int(level), muted)

    # -- preview -------------------------------------------------------------
    def _draw_hud(self, frame: np.ndarray, gesture: str, confidence: float) -> np.ndarray:
        """Overlay status text on the preview frame (copy only when needed)."""
        canvas = frame
        label = C.GESTURE_LABELS.get(gesture, gesture)
        state = self.machine.state
        lines = [
            f"{label}",
            f"conf {confidence:.2f}   fps {self.metrics.fps:.0f}   {state}",
        ]
        if self.safety.paused:
            lines.append("PAUSED")
        y = 26
        for i, text in enumerate(lines):
            color = (60, 90, 220) if not self.safety.paused else (30, 140, 240)
            if i == 0:
                color = (40, 190, 150) if not self.safety.paused else (30, 140, 240)
            cv2.putText(canvas, text, (10, y), cv2.FONT_HERSHEY_SIMPLEX,
                        0.62, (0, 0, 0), 3, cv2.LINE_AA)
            cv2.putText(canvas, text, (10, y), cv2.FONT_HERSHEY_SIMPLEX,
                        0.62, color, 1, cv2.LINE_AA)
            y += 24
        return canvas

    # -- teardown ------------------------------------------------------------
    def _finish(self) -> None:
        """Release everything and report the finished session."""
        released = self.mouse.release_all()
        if released:
            log.info("Engine teardown released: %s", ", ".join(sorted(released)))
        if self._tracker is not None:
            self._tracker.close()
            self._tracker = None
        if self._camera is not None:
            self._camera.close()
            self._camera = None
        self._processor = None
        self.machine.reset(paused=False)
        self.state_changed.emit(C.STATE_IDLE)
        self.status_changed.emit("Controller stopped")
        snapshot = self.metrics.snapshot(
            gesture=C.GESTURE_NONE,
            state=C.STATE_IDLE,
            paused=self.safety.paused,
            running=False,
            tracking_confidence=0.0,
            hands_detected=0,
        )
        if self._started_at is not None and snapshot.frames_processed > 0:
            self.session_ended.emit(self._started_at, snapshot)
        self._started_at = None
