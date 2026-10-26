"""System-control gestures: classification and state-machine arbitration.

Covers the six non-mouse gestures (screenshot, volume up/down, brightness,
mute, play/pause), verifies they do not collide with the core mouse gestures,
and drives the state machine with synthetic timestamps to check hold delays,
once-per-hold discrete firing, volume repeat, and brightness movement gating.
"""

from __future__ import annotations

from app import constants as C
from app.config import GestureConfig
from gestures.gesture_classifier import GestureClassifier
from gestures.gesture_state import GestureStateMachine

from conftest import (
    fist,
    flat_hand_pose,
    open_palm,
    point,
    scroll_vertical,
    shaka_pose,
    three_fingers_pose,
    thumb_down_pose,
    thumb_up_pose,
)


# -- classification ------------------------------------------------------------
def test_thumb_up_classified():
    classifier = GestureClassifier(GestureConfig())
    assert classifier.classify(thumb_up_pose()).gesture == C.GESTURE_THUMB_UP


def test_thumb_down_classified():
    classifier = GestureClassifier(GestureConfig())
    assert classifier.classify(thumb_down_pose()).gesture == C.GESTURE_THUMB_DOWN


def test_shaka_classified():
    classifier = GestureClassifier(GestureConfig())
    assert classifier.classify(shaka_pose()).gesture == C.GESTURE_SHAKA


def test_flat_hand_classified():
    classifier = GestureClassifier(GestureConfig())
    assert classifier.classify(flat_hand_pose()).gesture == C.GESTURE_FLAT_HAND


def test_three_fingers_classified():
    classifier = GestureClassifier(GestureConfig())
    assert classifier.classify(three_fingers_pose()).gesture == C.GESTURE_THREE_FINGERS


def test_fist_still_screenshot_not_volume():
    """Regression: a plain fist must not be stolen by the thumb volume rules."""
    classifier = GestureClassifier(GestureConfig())
    assert classifier.classify(fist()).gesture == C.GESTURE_FIST


# -- no collisions with core mouse gestures -----------------------------------
def test_new_poses_do_not_hijack_core_gestures():
    classifier = GestureClassifier(GestureConfig())
    core = {
        C.GESTURE_POINT: point(),
        C.GESTURE_OPEN_PALM: open_palm(),
        C.GESTURE_SCROLL_V: scroll_vertical(),
        C.GESTURE_FIST: fist(),
    }
    for expected, pose in core.items():
        assert classifier.classify(pose).gesture == expected


def test_system_poses_are_not_read_as_point_or_scroll():
    classifier = GestureClassifier(GestureConfig())
    for pose in (thumb_up_pose(), thumb_down_pose(), shaka_pose(),
                 flat_hand_pose(), three_fingers_pose()):
        got = classifier.classify(pose).gesture
        assert got not in (C.GESTURE_POINT, C.GESTURE_SCROLL_V,
                           C.GESTURE_SCROLL_H, C.GESTURE_OPEN_PALM), got


def test_null_pose_is_none():
    classifier = GestureClassifier(GestureConfig())
    assert classifier.classify(None).gesture == C.GESTURE_NONE


# -- state machine: hold delay -------------------------------------------------
def _cfg(**overrides) -> GestureConfig:
    return GestureConfig(**overrides)


def test_system_action_requires_hold():
    machine = GestureStateMachine(_cfg())
    t0 = 1000.0
    # First frame of the pose: not yet held long enough -> no action.
    out = machine.update(C.GESTURE_THUMB_UP, now=t0)
    assert out.action == C.ACTION_NONE
    # Just short of the hold time -> still no action.
    out = machine.update(C.GESTURE_THUMB_UP, now=t0 + (machine.cfg.system_hold_ms - 50) / 1000)
    assert out.action == C.ACTION_NONE
    # Past the hold time -> fires.
    out = machine.update(C.GESTURE_THUMB_UP, now=t0 + (machine.cfg.system_hold_ms + 40) / 1000)
    assert out.action == C.ACTION_VOLUME_UP
    assert out.state == C.STATE_VOLUME


def test_volume_repeats_while_held():
    machine = GestureStateMachine(_cfg())
    t0 = 500.0
    machine.update(C.GESTURE_THUMB_UP, now=t0)
    fire_t = t0 + (machine.cfg.system_hold_ms + 40) / 1000
    assert machine.update(C.GESTURE_THUMB_UP, now=fire_t).action == C.ACTION_VOLUME_UP
    # Within the repeat interval -> suppressed.
    soon = fire_t + (machine.cfg.system_repeat_ms - 60) / 1000
    assert machine.update(C.GESTURE_THUMB_UP, now=soon).action == C.ACTION_NONE
    # Past the repeat interval -> fires again.
    later = fire_t + (machine.cfg.system_repeat_ms + 40) / 1000
    assert machine.update(C.GESTURE_THUMB_UP, now=later).action == C.ACTION_VOLUME_UP


def test_discrete_action_fires_once_per_hold():
    machine = GestureStateMachine(_cfg())
    t0 = 900.0
    machine.update(C.GESTURE_FIST, now=t0)
    fire_t = t0 + (machine.cfg.system_hold_ms + 40) / 1000
    assert machine.update(C.GESTURE_FIST, now=fire_t).action == C.ACTION_SCREENSHOT
    # Holding longer must NOT re-fire (one screenshot per clench).
    assert machine.update(C.GESTURE_FIST, now=fire_t + 5.0).action == C.ACTION_NONE
    # Releasing and re-clenching re-arms it.
    machine.update(C.GESTURE_POINT, now=fire_t + 5.5)
    machine.update(C.GESTURE_FIST, now=fire_t + 6.0)
    again = machine.update(C.GESTURE_FIST, now=fire_t + 6.0 + (machine.cfg.system_hold_ms + 40) / 1000)
    assert again.action == C.ACTION_SCREENSHOT


def test_mute_and_media_discrete_actions():
    cfg = _cfg()
    for gesture, action in ((C.GESTURE_SHAKA, C.ACTION_VOLUME_MUTE),
                            (C.GESTURE_FLAT_HAND, C.ACTION_MEDIA_TOGGLE)):
        machine = GestureStateMachine(cfg)
        t0 = 42.0
        machine.update(gesture, now=t0)
        out = machine.update(gesture, now=t0 + (cfg.system_hold_ms + 40) / 1000)
        assert out.action == action


# -- state machine: brightness -------------------------------------------------
def test_brightness_needs_hand_movement():
    machine = GestureStateMachine(_cfg())
    t0 = 700.0
    # Pose held, but no movement yet -> no action.
    machine.update(C.GESTURE_THREE_FINGERS, now=t0, hand_position=(0.5, 0.6))
    out = machine.update(C.GESTURE_THREE_FINGERS,
                         now=t0 + (machine.cfg.system_hold_ms + 40) / 1000,
                         hand_position=(0.5, 0.6))
    assert out.action == C.ACTION_NONE
    # Moving hand UP (y decreases) -> brighter.
    out = machine.update(C.GESTURE_THREE_FINGERS,
                         now=t0 + (machine.cfg.system_hold_ms + 120) / 1000,
                         hand_position=(0.5, 0.55))
    assert out.action == C.ACTION_BRIGHTNESS_UP
    assert out.state == C.STATE_BRIGHTNESS
    # Moving hand DOWN (y increases) -> dimmer.
    machine.update(C.GESTURE_THREE_FINGERS,
                   now=t0 + (machine.cfg.system_hold_ms + 300) / 1000,
                   hand_position=(0.5, 0.60))
    out = machine.update(C.GESTURE_THREE_FINGERS,
                         now=t0 + (machine.cfg.system_hold_ms + 420) / 1000,
                         hand_position=(0.5, 0.65))
    assert out.action == C.ACTION_BRIGHTNESS_DOWN


def test_brightness_rate_limited():
    machine = GestureStateMachine(_cfg())
    t0 = 300.0
    machine.update(C.GESTURE_THREE_FINGERS, now=t0, hand_position=(0.5, 0.7))
    fire = t0 + (machine.cfg.system_hold_ms + 40) / 1000
    machine.update(C.GESTURE_THREE_FINGERS, now=fire, hand_position=(0.5, 0.7))
    first = machine.update(C.GESTURE_THREE_FINGERS, now=fire + 0.05,
                           hand_position=(0.5, 0.66))
    assert first.action == C.ACTION_BRIGHTNESS_UP
    # Immediate next step is inside the step interval -> suppressed.
    second = machine.update(C.GESTURE_THREE_FINGERS, now=fire + 0.06,
                            hand_position=(0.5, 0.60))
    assert second.action == C.ACTION_NONE


# -- paused gate ----------------------------------------------------------------
def test_system_actions_blocked_while_paused():
    machine = GestureStateMachine(_cfg())
    machine.force_pause(now=100.0)
    t0 = 200.0
    out = machine.update(C.GESTURE_FIST, now=t0)
    assert out.action == C.ACTION_NONE
    out = machine.update(C.GESTURE_THUMB_UP, now=t0 + 1.0)
    assert out.action == C.ACTION_NONE
    assert machine.state == C.STATE_PAUSED


# -- disabled rule --------------------------------------------------------------
def test_disabled_system_gesture_does_not_fire():
    cfg = _cfg(enable_volume=False)
    rules = __import__("gestures.gesture_config", fromlist=["default_rules"]).default_rules(cfg)
    machine = GestureStateMachine(cfg, rules)
    t0 = 600.0
    machine.update(C.GESTURE_THUMB_UP, now=t0)
    out = machine.update(C.GESTURE_THUMB_UP, now=t0 + (cfg.system_hold_ms + 40) / 1000)
    assert out.action == C.ACTION_NONE
