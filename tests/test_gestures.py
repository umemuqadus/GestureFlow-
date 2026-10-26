"""Tests for the gesture classifier and the gesture state machine."""

from __future__ import annotations

from app import constants as C
from app.config import GestureConfig
from gestures.gesture_classifier import GestureClassifier
from gestures.gesture_config import default_rules, validate_mappings
from gestures.gesture_state import GestureStateMachine
from tests.conftest import fist, open_palm, pinch, point, right_pinch, scroll_vertical


# ---------------------------------------------------------------------------
# Classifier
# ---------------------------------------------------------------------------
def test_no_hand_classifies_as_none():
    classifier = GestureClassifier(GestureConfig())
    result = classifier.classify(None)
    assert result.gesture == C.GESTURE_NONE
    assert result.confidence == 0.0


def test_point_pose_classified_as_point():
    classifier = GestureClassifier(GestureConfig())
    assert classifier.classify(point()).gesture == C.GESTURE_POINT


def test_pinch_enter_and_hysteresis():
    cfg = GestureConfig(pinch_threshold=0.3, release_threshold=0.45)
    classifier = GestureClassifier(cfg)
    # A clear pinch.
    assert classifier.classify(pinch(0.05)).gesture == C.GESTURE_PINCH
    # Slightly past the activation threshold but under release: still latched.
    assert classifier.classify(pinch(0.4)).gesture == C.GESTURE_PINCH
    # Past the release threshold: latch drops.
    assert classifier.classify(pinch(0.6)).gesture != C.GESTURE_PINCH


def test_point_pose_is_not_right_click():
    """Thumb near a curled middle finger must not register a right click."""
    cfg = GestureConfig()
    classifier = GestureClassifier(cfg)
    assert classifier.classify(point()).gesture != C.GESTURE_RIGHT_CLICK


def test_fist_is_not_a_click():
    cfg = GestureConfig()
    classifier = GestureClassifier(cfg)
    result = classifier.classify(fist())
    assert result.gesture not in (C.GESTURE_PINCH, C.GESTURE_RIGHT_CLICK)


def test_right_click_classified():
    cfg = GestureConfig(right_pinch_threshold=0.35)
    classifier = GestureClassifier(cfg)
    result = classifier.classify(right_pinch(0.08))
    assert result.gesture == C.GESTURE_RIGHT_CLICK


def test_open_palm_classified():
    classifier = GestureClassifier(GestureConfig())
    assert classifier.classify(open_palm()).gesture == C.GESTURE_OPEN_PALM


def test_scroll_classified():
    classifier = GestureClassifier(GestureConfig())
    assert classifier.classify(scroll_vertical()).gesture == C.GESTURE_SCROLL_V


def test_fist_classified():
    classifier = GestureClassifier(GestureConfig())
    assert classifier.classify(fist()).gesture == C.GESTURE_FIST


# ---------------------------------------------------------------------------
# State machine
# ---------------------------------------------------------------------------
def make_machine(**overrides) -> GestureStateMachine:
    cfg = GestureConfig(**overrides)
    return GestureStateMachine(cfg, default_rules(cfg))


def test_point_moves_cursor():
    machine = make_machine()
    out = machine.update(C.GESTURE_POINT, now=1.0)
    assert out.action == C.ACTION_MOVE
    assert out.state == C.STATE_MOVING


def test_quick_pinch_tap_produces_single_left_click():
    machine = make_machine(min_gesture_frames=1)
    # Establish tracking, then a short pinch, then release.
    machine.update(C.GESTURE_POINT, now=0.0)
    machine.update(C.GESTURE_PINCH, now=0.10)
    out = machine.update(C.GESTURE_POINT, now=0.15)
    assert out.action == C.ACTION_LEFT_CLICK


def test_held_pinch_becomes_drag_not_click():
    machine = make_machine(min_gesture_frames=1, drag_hold_ms=300)
    machine.update(C.GESTURE_POINT, now=0.0)
    machine.update(C.GESTURE_PINCH, now=0.10)          # tap starts
    out_start = machine.update(C.GESTURE_PINCH, now=0.45)  # held past drag time
    assert out_start.action == C.ACTION_DRAG_START
    out_move = machine.update(C.GESTURE_PINCH, now=0.55)
    assert out_move.action == C.ACTION_DRAG_MOVE
    out_end = machine.update(C.GESTURE_POINT, now=0.65)
    assert out_end.action == C.ACTION_DRAG_END


def test_repeated_pinch_frames_do_not_repeatedly_click():
    """A sustained pinch must not emit a click every frame."""
    machine = make_machine(min_gesture_frames=1, drag_hold_ms=0)
    machine.update(C.GESTURE_POINT, now=0.0)
    machine.update(C.GESTURE_PINCH, now=0.10)
    machine.update(C.GESTURE_PINCH, now=0.20)
    machine.update(C.GESTURE_PINCH, now=0.30)
    # Still pinching -> dragging, not a stream of clicks.
    assert machine.state in (C.STATE_DRAGGING, C.STATE_TRACKING)


def test_two_quick_taps_make_double_click():
    machine = make_machine(min_gesture_frames=1, click_cooldown_ms=200,
                           double_click_window_ms=500, drag_hold_ms=300)
    machine.update(C.GESTURE_POINT, now=0.0)
    # Tap 1
    machine.update(C.GESTURE_PINCH, now=0.10)
    machine.update(C.GESTURE_POINT, now=0.15)   # -> LEFT_CLICK
    # Tap 2 shortly after (within the double-click window, past the cooldown)
    machine.update(C.GESTURE_PINCH, now=0.35)
    out = machine.update(C.GESTURE_POINT, now=0.40)
    assert out.action == C.ACTION_DOUBLE_CLICK


def test_click_cooldown_suppresses_rapid_clicks():
    machine = make_machine(min_gesture_frames=1, click_cooldown_ms=1000,
                           enable_double_click=False, enable_drag=False,
                           drag_hold_ms=0)
    machine.update(C.GESTURE_POINT, now=0.0)
    machine.update(C.GESTURE_PINCH, now=0.10)
    first = machine.update(C.GESTURE_POINT, now=0.15)
    assert first.action == C.ACTION_LEFT_CLICK
    # Second tap inside the cooldown window -> suppressed.
    machine.update(C.GESTURE_PINCH, now=0.20)
    second = machine.update(C.GESTURE_POINT, now=0.25)
    assert second.action == C.ACTION_NONE


def test_right_click_gesture_emits_action():
    machine = make_machine(min_gesture_frames=1)
    machine.update(C.GESTURE_POINT, now=0.0)
    machine.update(C.GESTURE_RIGHT_CLICK, now=0.10)
    out = machine.update(C.GESTURE_RIGHT_CLICK, now=0.15)
    assert out.action == C.ACTION_RIGHT_CLICK


def test_open_palm_pause_requires_hold():
    machine = make_machine(min_gesture_frames=1, pause_hold_ms=500)
    machine.update(C.GESTURE_POINT, now=0.0)
    # Brief palm: must NOT pause.
    out = machine.update(C.GESTURE_OPEN_PALM, now=0.10)
    assert out.action != C.ACTION_PAUSE
    assert machine.paused is False
    # Held palm: pauses.
    out = machine.update(C.GESTURE_OPEN_PALM, now=0.70)
    assert out.action == C.ACTION_PAUSE
    assert machine.paused is True
    assert machine.state == C.STATE_PAUSED


def test_paused_state_blocks_actions():
    machine = make_machine(min_gesture_frames=1, pause_hold_ms=100)
    machine.update(C.GESTURE_OPEN_PALM, now=0.0)
    machine.update(C.GESTURE_OPEN_PALM, now=0.5)
    assert machine.paused is True
    # Pointing while paused does not move the cursor.
    out = machine.update(C.GESTURE_POINT, now=0.6)
    assert out.action != C.ACTION_MOVE


def test_no_hand_releases_drag_and_reports_state():
    machine = make_machine(min_gesture_frames=1, drag_hold_ms=100)
    machine.update(C.GESTURE_POINT, now=0.0)
    machine.update(C.GESTURE_PINCH, now=0.10)
    machine.update(C.GESTURE_PINCH, now=0.30)   # dragging
    assert machine.state == C.STATE_DRAGGING
    out = machine.update(C.GESTURE_NONE, now=0.40)
    assert out.action == C.ACTION_DRAG_END      # never leave the button held
    assert out.state == C.STATE_NO_HAND


def test_scroll_emits_steps_and_respects_deadzone():
    machine = make_machine(min_gesture_frames=1, scroll_deadzone_px=0)
    machine.update(C.GESTURE_SCROLL_V, now=0.0, hand_position=(0.5, 0.6))
    out = machine.update(C.GESTURE_SCROLL_V, now=0.1, hand_position=(0.5, 0.5))
    assert out.action == C.ACTION_SCROLL_V
    assert out.scroll_dy != 0


def _feed_scroll(machine, positions, dt=0.033):
    """Feed a hand-position sequence; return the per-frame (action, scroll)."""
    results = []
    now = 0.0
    for p in positions:
        out = machine.update(C.GESTURE_SCROLL_V, now=now, hand_position=p)
        results.append((out.action, out.scroll_dy))
        now += dt
    return results


def test_slow_steady_motion_accumulates_scroll():
    """Slow deliberate scrolling must not be rounded away to zero.

    A 0.002/frame delta used to hit ``round(0.002*60) == 0`` every frame, so
    slow scrolling produced nothing at all.  The accumulator banks those
    fractions and emits whole steps once they cross a boundary.
    """
    machine = make_machine(min_gesture_frames=1, scroll_deadzone_px=0)
    positions = [(0.5, 0.5 - 0.002 * i) for i in range(80)]
    results = _feed_scroll(machine, positions)
    total = sum(dy for _, dy in results)
    assert abs(total) >= 3            # accumulated a real, sustained amount
    assert all(dy <= 0 for _, dy in results)  # steady motion stays one direction


def test_scroll_jitter_does_not_flicker_every_frame():
    """Tracking noise must not scroll on every frame the way raw round() did."""
    machine = make_machine(min_gesture_frames=1, scroll_deadzone_px=0)
    # Alternate up/down by a small amount each frame (simulated landmark noise).
    positions = [(0.5, 0.5 + (0.02 if i % 2 else -0.02)) for i in range(60)]
    results = _feed_scroll(machine, positions)
    fired = sum(1 for action, _ in results if action == C.ACTION_SCROLL_V)
    # Raw round() fired on essentially every frame; smoothing + accumulation
    # must suppress the majority of that jitter-driven firing.
    assert fired < len(positions) // 2


def test_scroll_stops_cleanly_without_delayed_burst():
    """Once the hand stops, momentum must bleed off instead of firing later."""
    machine = make_machine(min_gesture_frames=1, scroll_deadzone_px=12)
    machine.update(C.GESTURE_SCROLL_V, now=0.0, hand_position=(0.5, 0.5))
    # Two fast frames bank momentum into the accumulator...
    machine.update(C.GESTURE_SCROLL_V, now=0.033, hand_position=(0.5, 0.6))
    machine.update(C.GESTURE_SCROLL_V, now=0.066, hand_position=(0.5, 0.7))
    # ...then the hand holds perfectly still for many frames.
    results = _feed_scroll(machine, [(0.5, 0.7)] * 20, dt=0.033)
    # Momentum drains, the accumulator reaches exactly zero, and the final
    # frames emit nothing -- no latent burst waiting to fire.
    assert machine._scroll_accum == 0.0
    assert all(dy == 0 for _, dy in results[-5:])


def test_scroll_violent_jerk_is_clamped():
    """A single huge jump cannot emit runaway scroll steps."""
    machine = make_machine(min_gesture_frames=1, scroll_deadzone_px=0)
    machine.update(C.GESTURE_SCROLL_V, now=0.0, hand_position=(0.5, 0.5))
    out = machine.update(C.GESTURE_SCROLL_V, now=0.033, hand_position=(0.5, 0.99))
    assert abs(out.scroll_dy) <= 5
    assert abs(machine._scroll_accum) <= 15.0


def test_scroll_horizontal_uses_same_accumulator():
    """Horizontal scroll gets the identical smoothing/accumulation path."""
    machine = make_machine(min_gesture_frames=1, scroll_deadzone_px=0)
    machine.update(C.GESTURE_SCROLL_H, now=0.0, hand_position=(0.5, 0.5))
    results = []
    now = 0.0
    for i in range(40):
        out = machine.update(C.GESTURE_SCROLL_H, now=now,
                             hand_position=(0.5 + 0.003 * i, 0.5))
        results.append(out)
        now += 0.033
    total = sum(o.scroll_dx for o in results)
    assert abs(total) >= 3
    assert all(o.scroll_dx >= 0 for o in results)


def test_disabled_gesture_does_not_fire():
    """With click/drag/double all disabled, a pinch must not act."""
    cfg = GestureConfig(enable_left_click=False, enable_drag=False,
                        enable_double_click=False)
    machine = GestureStateMachine(cfg, default_rules(cfg))
    machine.update(C.GESTURE_POINT, now=0.0)
    machine.update(C.GESTURE_PINCH, now=0.10)
    out = machine.update(C.GESTURE_POINT, now=0.15)
    assert out.action not in (C.ACTION_LEFT_CLICK, C.ACTION_DOUBLE_CLICK,
                              C.ACTION_DRAG_START)


# ---------------------------------------------------------------------------
# Mapping validation
# ---------------------------------------------------------------------------
def test_default_rules_are_valid():
    assert validate_mappings(default_rules(GestureConfig())) == []


def test_conflicting_actions_are_reported():
    from gestures.gesture_config import GestureRule

    rules = default_rules(GestureConfig())
    rules[C.GESTURE_PINCH] = GestureRule(C.GESTURE_PINCH, C.ACTION_LEFT_CLICK)
    rules[C.GESTURE_RIGHT_CLICK] = GestureRule(C.GESTURE_RIGHT_CLICK, C.ACTION_LEFT_CLICK)
    problems = validate_mappings(rules)
    assert any("multiple gestures" in p for p in problems)


def test_release_must_exceed_threshold():
    from gestures.gesture_config import GestureRule

    rules = default_rules(GestureConfig())
    rules[C.GESTURE_PINCH] = GestureRule(
        C.GESTURE_PINCH, C.ACTION_LEFT_CLICK, threshold=0.4, release_threshold=0.2
    )
    problems = validate_mappings(rules)
    assert any("release threshold" in p for p in problems)
