"""Runtime configuration objects.

``AppConfig`` is a plain dataclass tree that the settings service loads from /
saves to SQLite.  Every field is validated by :meth:`AppConfig.validate`, which
raises ``ValueError`` with a human readable message when a value is unusable.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any

from app import constants as C


@dataclass
class CameraConfig:
    device_index: int = C.DEFAULT_CAMERA_INDEX
    width: int = C.DEFAULT_CAPTURE_WIDTH
    height: int = C.DEFAULT_CAPTURE_HEIGHT
    max_fps: int = C.DEFAULT_MAX_FPS
    mirror_preview: bool = C.DEFAULT_MIRROR_PREVIEW
    # Process frames at this width (height keeps aspect). Lower = faster.
    processing_width: int = 640

    def validate(self) -> None:
        if not isinstance(self.device_index, int) or self.device_index < 0:
            raise ValueError("Camera device index must be a non-negative integer.")
        for name, value in (("width", self.width), ("height", self.height)):
            if not isinstance(value, int) or not (160 <= value <= 7680):
                raise ValueError(f"Camera {name} must be between 160 and 7680 pixels.")
        if not isinstance(self.max_fps, int) or not (5 <= self.max_fps <= 120):
            raise ValueError("Max FPS must be between 5 and 120.")
        if not isinstance(self.processing_width, int) or not (160 <= self.processing_width <= 1920):
            raise ValueError("Processing width must be between 160 and 1920 pixels.")


@dataclass
class TrackingConfig:
    detection_confidence: float = C.DEFAULT_DETECTION_CONFIDENCE
    tracking_confidence: float = C.DEFAULT_TRACKING_CONFIDENCE
    max_num_hands: int = 1


@dataclass
class CursorConfig:
    speed: float = C.DEFAULT_CURSOR_SPEED
    smoothing: float = C.DEFAULT_SMOOTHING          # 0 = raw, 1 = very heavy
    movement_deadzone: float = C.DEFAULT_MOVEMENT_DEADZONE
    use_one_euro: bool = True
    one_euro_min_cutoff: float = 1.2
    one_euro_beta: float = 0.007
    # Fraction of the frame used as the active tracking region (0.5 = centre half).
    roi_fraction: float = 0.62
    invert_x: bool = False
    invert_y: bool = False


@dataclass
class GestureConfig:
    pinch_threshold: float = C.DEFAULT_PINCH_THRESHOLD
    release_threshold: float = C.DEFAULT_RELEASE_THRESHOLD
    right_pinch_threshold: float = C.DEFAULT_RIGHT_PINCH_THRESHOLD
    click_cooldown_ms: int = C.DEFAULT_CLICK_COOLDOWN_MS
    double_click_window_ms: int = C.DEFAULT_DOUBLE_CLICK_WINDOW_MS
    drag_hold_ms: int = C.DEFAULT_DRAG_HOLD_MS
    scroll_sensitivity: float = C.DEFAULT_SCROLL_SENSITIVITY
    scroll_deadzone_px: int = C.DEFAULT_SCROLL_DEADZONE_PX
    pause_hold_ms: int = C.DEFAULT_PAUSE_HOLD_MS
    min_gesture_frames: int = 2

    # Per-gesture enable switches.
    enable_left_click: bool = True
    enable_right_click: bool = True
    enable_double_click: bool = True
    enable_drag: bool = True
    enable_scroll: bool = True
    enable_pause: bool = True
    # System-control gestures (screenshot / volume / brightness / media).
    enable_screenshot: bool = True
    enable_volume: bool = True        # thumb up, thumb down, and mute
    enable_brightness: bool = True    # three fingers + movement
    enable_media: bool = True         # flat hand play/pause

    # Timing for system actions.
    system_hold_ms: int = 260        # stable hold required before firing
    system_repeat_ms: int = 170      # repeat interval while holding volume
    system_cooldown_ms: int = 900    # extra floor between discrete actions
    brightness_step_ms: int = 95     # min interval between brightness steps


@dataclass
class SafetyConfig:
    # Off by default: a mouse controller must be able to control *other*
    # windows, so pausing the instant our own window loses focus would defeat
    # the purpose.  Emergency stop (Esc), the corner failsafe and the explicit
    # Start button remain the primary safety mechanisms.
    pause_on_focus_loss: bool = False
    pyautogui_failsafe: bool = True
    pause_hotkey: str = "ctrl+alt+p"
    start_stop_hotkey: str = "ctrl+alt+m"
    emergency_stop_hotkey: str = "esc"
    calibration_hotkey: str = "ctrl+alt+c"
    quit_hotkey: str = "ctrl+alt+q"


@dataclass
class UiConfig:
    theme: str = "light"            # "light" | "dark"
    start_minimized: bool = False
    show_landmarks: bool = True
    active_profile: str = "Default"
    preview_throttle_fps: int = 15


@dataclass
class AppConfig:
    camera: CameraConfig = field(default_factory=CameraConfig)
    tracking: TrackingConfig = field(default_factory=TrackingConfig)
    cursor: CursorConfig = field(default_factory=CursorConfig)
    gestures: GestureConfig = field(default_factory=GestureConfig)
    safety: SafetyConfig = field(default_factory=SafetyConfig)
    ui: UiConfig = field(default_factory=UiConfig)

    def validate(self) -> None:
        self.camera.validate()
        g, cur = self.gestures, self.cursor
        for name, value in (
            ("detection_confidence", self.tracking.detection_confidence),
            ("tracking_confidence", self.tracking.tracking_confidence),
        ):
            if not 0.0 < value <= 1.0:
                raise ValueError(f"{name} must be in the range (0, 1].")
        if not 0.1 <= cur.speed <= 5.0:
            raise ValueError("Cursor speed must be between 0.1 and 5.0.")
        if not 0.0 <= cur.smoothing <= 0.98:
            raise ValueError("Cursor smoothing must be between 0 and 0.98.")
        if not 0.2 <= cur.roi_fraction <= 1.0:
            raise ValueError("Tracking region fraction must be between 0.2 and 1.0.")
        if not 0.02 <= g.pinch_threshold <= 0.9:
            raise ValueError("Pinch threshold must be between 0.02 and 0.9.")
        if g.release_threshold <= g.pinch_threshold:
            raise ValueError("Release threshold must be greater than pinch threshold "
                             "(hysteresis prevents repeated clicks).")
        if not 0.0 < g.right_pinch_threshold <= 0.9:
            raise ValueError("Right-pinch threshold must be in (0, 0.9].")
        if not 0 <= g.click_cooldown_ms <= 5000:
            raise ValueError("Click cooldown must be between 0 and 5000 ms.")
        if not 100 <= g.double_click_window_ms <= 2000:
            raise ValueError("Double-click window must be between 100 and 2000 ms.")
        if not 0 <= g.drag_hold_ms <= 3000:
            raise ValueError("Drag hold time must be between 0 and 3000 ms.")
        if not 0.1 <= g.scroll_sensitivity <= 10.0:
            raise ValueError("Scroll sensitivity must be between 0.1 and 10.")
        if not 0 <= g.scroll_deadzone_px <= 200:
            raise ValueError("Scroll dead zone must be between 0 and 200 px.")
        if not 100 <= g.pause_hold_ms <= 10000:
            raise ValueError("Pause hold duration must be between 100 and 10000 ms.")
        if not 1 <= g.min_gesture_frames <= 10:
            raise ValueError("Minimum gesture frames must be between 1 and 10.")
        if not 0 <= g.system_hold_ms <= 3000:
            raise ValueError("System gesture hold must be between 0 and 3000 ms.")
        if not 50 <= g.system_repeat_ms <= 2000:
            raise ValueError("System repeat interval must be between 50 and 2000 ms.")
        if not 100 <= g.system_cooldown_ms <= 5000:
            raise ValueError("System cooldown must be between 100 and 5000 ms.")
        if not 30 <= g.brightness_step_ms <= 2000:
            raise ValueError("Brightness step interval must be between 30 and 2000 ms.")
        if self.ui.theme not in ("light", "dark"):
            raise ValueError("Theme must be 'light' or 'dark'.")
        if not 1 <= self.ui.preview_throttle_fps <= 60:
            raise ValueError("Preview throttle FPS must be between 1 and 60.")
        if not 0 < self.tracking.max_num_hands <= 4:
            raise ValueError("Max hands must be between 1 and 4.")

    # -- (de)serialisation ---------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AppConfig":
        """Build a config from a nested dict, ignoring unknown keys."""
        cfg = cls()
        for section_name in ("camera", "tracking", "cursor", "gestures", "safety", "ui"):
            section = getattr(cfg, section_name)
            raw = data.get(section_name)
            if isinstance(raw, dict):
                for key, value in raw.items():
                    if hasattr(section, key):
                        current = getattr(section, key)
                        # Coerce to the type already held by the default.
                        try:
                            if isinstance(current, bool):
                                value = bool(value)
                            elif isinstance(current, int) and not isinstance(current, bool):
                                value = int(value)
                            elif isinstance(current, float):
                                value = float(value)
                            elif isinstance(current, str):
                                value = str(value)
                        except (TypeError, ValueError):
                            continue
                        setattr(section, key, value)
        return cfg
