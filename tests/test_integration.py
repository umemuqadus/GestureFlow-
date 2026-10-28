"""Integration test for the core control pipeline.

Drives the real classifier, state machine, coordinate mapper, cursor smoother,
mouse controller and safety manager together with synthetic observations and a
fake mouse backend.  Deterministic (explicit timestamps) and never touches the
real mouse or camera.
"""

from __future__ import annotations

import numpy as np
import pytest

from app import constants as C
from app.config import AppConfig
from controller.coordinate_mapper import CoordinateMapper
from controller.cursor_smoother import CursorSmoother
from controller.mouse_controller import LEFT, MouseController
from controller.safety_manager import SafetyManager
from gestures.gesture_classifier import GestureClassifier
from gestures.gesture_config import default_rules
from gestures.gesture_state import GestureStateMachine
from tests.conftest import FakeMouseBackend, pinch, point, scroll_vertical
from vision.landmark_processor import cursor_anchor

SCREEN = (1920, 1080)


class Pipeline:
    """Minimal harness mirroring the engine's per-frame dispatch, without threads."""

    def __init__(self, config: AppConfig):
        self.config = config
        self.backend = FakeMouseBackend(*SCREEN)
        self.mouse = MouseController(failsafe=True, backend=self.backend)
        self.safety = SafetyManager(self.mouse, config.safety)
        self.classifier = GestureClassifier(config.gestures)
        self.machine = GestureStateMachine(config.gestures, default_rules(config.gestures))
        self.mapper = CoordinateMapper(lambda: SCREEN, roi_fraction=1.0,
                                       speed=config.cursor.speed)
        self.smoother = CursorSmoother(config.cursor.smoothing,
                                       use_one_euro=config.cursor.use_one_euro)

    def frame(self, obs, now: float) -> str:
        """Process one synthetic frame; returns the executed action."""
        classification = self.classifier.classify(obs)
        if self.safety.paused and not self.machine.paused:
            self.machine.force_pause()
        elif not self.safety.paused and self.machine.paused:
            self.machine.resume()
        anchor = cursor_anchor(obs) if obs is not None else None
        out = self.machine.update(classification.gesture, now=now,
                                  hand_position=anchor)
        if not self.safety.may_act():
            if self.machine.dragging or self.mouse.held_buttons:
                self.mouse.release_all()
            return C.ACTION_NONE
        self._execute(out, anchor)
        return out.action

    def _execute(self, out, anchor) -> None:
        action = out.action
        if action in (C.ACTION_MOVE, C.ACTION_DRAG_MOVE):
            self._move(anchor)
        elif action == C.ACTION_LEFT_CLICK:
            self.mouse.click(LEFT)
        elif action == C.ACTION_DRAG_START:
            self.mouse.press_down(LEFT)
        elif action == C.ACTION_DRAG_END:
            self.mouse.release(LEFT)
        elif action == C.ACTION_SCROLL_V:
            self.mouse.scroll_vertical(out.scroll_dy)

    def _move(self, anchor) -> None:
        if anchor is None:
            return
        vx, vy = self.mapper.to_virtual(*anchor)
        sx, sy = self.smoother(vx, vy, 0.0)
        px, py = self.mapper.virtual_to_pixels(sx, sy)
        self.mouse.move_to(px, py)


def test_point_gesture_moves_real_cursor_coordinates():
    config = AppConfig()
    config.cursor.smoothing = 0.0          # raw mapping for a crisp assertion
    config.cursor.use_one_euro = False
    config.cursor.movement_deadzone = 0.0
    pipeline = Pipeline(config)

    obs = point()          # index fingertip at normalised (0.44, 0.42)
    action = pipeline.frame(obs, now=1.0)
    assert action == C.ACTION_MOVE
    assert pipeline.backend.of_type("moveTo"), "cursor should have moved"
    x, y = pipeline.backend.of_type("moveTo")[-1][1:]
    assert 0 <= x < SCREEN[0] and 0 <= y < SCREEN[1]


def test_pinch_tap_clicks_once_and_does_not_hold_button():
    config = AppConfig()
    config.gestures.min_gesture_frames = 1
    config.gestures.drag_hold_ms = 1000    # keep it a tap for this test
    pipeline = Pipeline(config)

    pipeline.frame(point(), now=0.0)
    # Hold the pinch briefly (a tap), then release.
    for i in range(6):
        pipeline.frame(pinch(0.05), now=0.1 + i * 0.02)
    action = pipeline.frame(point(), now=0.30)
    assert action == C.ACTION_LEFT_CLICK
    assert len(pipeline.backend.of_type("click")) == 1
    assert not pipeline.mouse.held_buttons   # a tap must not hold the button


def test_held_pinch_drags_then_releases():
    config = AppConfig()
    config.gestures.min_gesture_frames = 1
    config.gestures.drag_hold_ms = 100
    pipeline = Pipeline(config)

    pipeline.frame(point(), now=0.0)
    pipeline.frame(pinch(0.05), now=0.10)     # pinch onset
    start = pipeline.frame(pinch(0.05), now=0.25)   # held past drag threshold
    assert start == C.ACTION_DRAG_START
    assert pipeline.mouse.is_held(LEFT)
    pipeline.frame(pinch(0.05), now=0.35)     # still dragging
    assert pipeline.mouse.is_held(LEFT)
    end = pipeline.frame(point(), now=0.45)   # released
    assert end == C.ACTION_DRAG_END
    assert not pipeline.mouse.held_buttons


def test_tracking_loss_releases_held_button():
    config = AppConfig()
    config.gestures.min_gesture_frames = 1
    config.gestures.drag_hold_ms = 100
    pipeline = Pipeline(config)

    pipeline.frame(point(), now=0.0)
    pipeline.frame(pinch(0.05), now=0.10)
    pipeline.frame(pinch(0.05), now=0.25)     # dragging
    assert pipeline.mouse.is_held(LEFT)
    action = pipeline.frame(None, now=0.35)   # hand disappears mid-drag
    assert action == C.ACTION_DRAG_END
    assert not pipeline.mouse.held_buttons     # never leave the button stuck


def test_scroll_gesture_issues_scroll_events():
    config = AppConfig()
    config.gestures.scroll_deadzone_px = 0
    pipeline = Pipeline(config)

    def scroll_pose(y: float):
        # Index + middle up, ring + pinky down, with the hand at height y.
        from tests.conftest import make_hand
        return make_hand(index_ext=True, middle_ext=True, ring_ext=False,
                         pinky_ext=False, index_tip=(0.44, y))

    pipeline.frame(scroll_pose(0.42), now=0.0)      # baseline frame
    actions = []
    for i, y in enumerate((0.38, 0.34, 0.30, 0.26)):  # move the hand upward
        actions.append(pipeline.frame(scroll_pose(y), now=0.1 + i * 0.05))
    assert C.ACTION_SCROLL_V in actions
    assert pipeline.backend.of_type("scroll"), "a scroll event should reach the mouse"


def test_safety_pause_blocks_cursor_movement():
    config = AppConfig()
    config.cursor.movement_deadzone = 0.0
    pipeline = Pipeline(config)
    pipeline.safety.pause("test")
    before = len(pipeline.backend.of_type("moveTo"))
    pipeline.frame(point(), now=1.0)
    assert len(pipeline.backend.of_type("moveTo")) == before


def test_emergency_stop_releases_and_blocks():
    config = AppConfig()
    config.gestures.min_gesture_frames = 1
    config.gestures.drag_hold_ms = 100
    pipeline = Pipeline(config)
    pipeline.frame(point(), now=0.0)
    pipeline.frame(pinch(0.05), now=0.10)
    pipeline.frame(pinch(0.05), now=0.25)     # dragging, button held
    assert pipeline.mouse.is_held(LEFT)
    pipeline.safety.emergency_stop("test")
    assert not pipeline.mouse.held_buttons
    before = len(pipeline.backend.of_type("click"))
    pipeline.frame(point(), now=0.35)
    assert len(pipeline.backend.of_type("click")) == before


# -- system actions routed through the real engine ------------------------------
class RecordingSystem:
    """Stands in for SystemController; records which OS action was requested."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def screenshot(self):
        self.calls.append("screenshot")
        from pathlib import Path
        return Path("screenshot.png")

    def volume_up(self) -> None:
        self.calls.append("volume_up")

    def volume_down(self) -> None:
        self.calls.append("volume_down")

    def volume_mute(self) -> None:
        self.calls.append("volume_mute")

    def media_toggle(self) -> None:
        self.calls.append("media_toggle")

    def brightness_up(self) -> bool:
        self.calls.append("brightness_up")
        return True

    def brightness_down(self) -> bool:
        self.calls.append("brightness_down")
        return True

    @property
    def brightness_supported(self) -> bool:
        return True


def test_engine_routes_system_actions_to_system_controller():
    """The real engine dispatches each system action to the injected controller."""
    from PySide6.QtWidgets import QApplication

    from controller.engine import ControllerEngine
    from gestures.gesture_state import StateMachineOutput

    app = QApplication.instance() or QApplication([])
    assert app is not None

    config = AppConfig()
    mouse = MouseController(failsafe=True, backend=FakeMouseBackend(*SCREEN))
    safety = SafetyManager(mouse, config.safety)
    system = RecordingSystem()
    engine = ControllerEngine(config, mouse, safety, default_rules(config.gestures),
                              system=system)

    ordered = [
        C.ACTION_VOLUME_UP, C.ACTION_VOLUME_DOWN, C.ACTION_VOLUME_MUTE,
        C.ACTION_MEDIA_TOGGLE, C.ACTION_SCREENSHOT,
        C.ACTION_BRIGHTNESS_UP, C.ACTION_BRIGHTNESS_DOWN,
    ]
    for action in ordered:
        engine._execute(StateMachineOutput(action=action), None, None, None)

    assert system.calls == ["volume_up", "volume_down", "volume_mute",
                            "media_toggle", "screenshot",
                            "brightness_up", "brightness_down"]


def test_engine_emits_level_signal_only_when_a_level_is_known():
    """The on-screen indicator shows real levels and never invents one."""
    from PySide6.QtWidgets import QApplication

    from controller.engine import ControllerEngine
    from gestures.gesture_state import StateMachineOutput

    app = QApplication.instance() or QApplication([])
    assert app is not None

    class LevelSystem(RecordingSystem):
        volume_level = 42
        brightness_level = 55
        muted = False

    config = AppConfig()
    mouse = MouseController(failsafe=True, backend=FakeMouseBackend(*SCREEN))
    safety = SafetyManager(mouse, config.safety)
    engine = ControllerEngine(config, mouse, safety, default_rules(config.gestures),
                              system=LevelSystem())

    seen: list[tuple[str, int, bool]] = []
    engine.level_changed.connect(lambda kind, level, muted: seen.append(
        (kind, level, muted)))

    engine._execute(StateMachineOutput(action=C.ACTION_VOLUME_UP), None, None, None)
    engine._execute(StateMachineOutput(action=C.ACTION_VOLUME_MUTE), None, None, None)
    engine._execute(StateMachineOutput(action=C.ACTION_BRIGHTNESS_UP), None, None, None)
    assert seen == [
        ("volume", 42, False),
        ("volume", 42, False),
        ("brightness", 55, False),
    ]

    # A controller without level bookkeeping reports nothing to display.
    engine.system = RecordingSystem()
    engine._execute(StateMachineOutput(action=C.ACTION_VOLUME_UP), None, None, None)
    engine._execute(StateMachineOutput(action=C.ACTION_BRIGHTNESS_UP), None, None, None)
    assert len(seen) == 3
