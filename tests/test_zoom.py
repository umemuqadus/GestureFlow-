"""Zoom gesture: two fingers opened in a 'V' with an analog open/close control.

Zoom shares its base pose with scroll (index + middle up, ring/pinky down), so
the tests pin down the separation: fingers held together and moved = scroll, a
clearly opened V = zoom.  Arming needs a wider opening than the release point,
so the pose cannot flicker between the two at the boundary, and closing the V
hands control straight back to scroll.
"""

from __future__ import annotations

from app import constants as C
from app.config import GestureConfig
from gestures import gesture_rules as rules
from gestures.gesture_classifier import GestureClassifier
from gestures.gesture_config import default_rules, validate_mappings
from gestures.gesture_state import GestureStateMachine
from tests.conftest import (
    fist,
    make_hand,
    open_palm,
    point,
    scroll_vertical,
    three_fingers_pose,
    zoom_pose,
)


def _machine(**overrides) -> GestureStateMachine:
    return GestureStateMachine(GestureConfig(**overrides))


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------
def test_zoom_pose_classified_as_zoom():
    classifier = GestureClassifier(GestureConfig())
    assert classifier.classify(zoom_pose()).gesture == C.GESTURE_ZOOM


def test_zoom_is_not_read_as_point_pinch_or_scroll():
    """The V pose must not collide with the core mouse gestures."""
    classifier = GestureClassifier(GestureConfig())
    got = classifier.classify(zoom_pose()).gesture
    assert got not in (C.GESTURE_POINT, C.GESTURE_PINCH, C.GESTURE_SCROLL_V,
                       C.GESTURE_SCROLL_H, C.GESTURE_SHAKA, C.GESTURE_FIST)


def test_scroll_pose_stays_a_scroll():
    """Fingers simply held together (the scroll pose) must never arm zoom."""
    classifier = GestureClassifier(GestureConfig())
    assert classifier.classify(scroll_vertical()).gesture == C.GESTURE_SCROLL_V


def test_spread_just_under_the_gate_stays_scroll():
    """A modest opening is still scroll; zooming in needs a deliberate spread."""
    classifier = GestureClassifier(GestureConfig())
    # 0.45 measured spread sits between the release (0.38) and the arming
    # gate (0.48): not yet zoom, and without a latch it cannot claim the pose.
    assert classifier.classify(zoom_pose(0.40)).gesture == C.GESTURE_SCROLL_V


def test_zoom_does_not_hijack_other_poses():
    classifier = GestureClassifier(GestureConfig())
    assert classifier.classify(fist()).gesture == C.GESTURE_FIST
    assert classifier.classify(point()).gesture == C.GESTURE_POINT
    assert classifier.classify(open_palm()).gesture == C.GESTURE_OPEN_PALM
    assert (classifier.classify(three_fingers_pose()).gesture
            == C.GESTURE_THREE_FINGERS)


# ---------------------------------------------------------------------------
# Latch: the closing motion is zoom-out, and the release hands back to scroll
# ---------------------------------------------------------------------------
def test_zoom_latch_survives_the_closing_motion():
    """Mid-close the spread is under the arming gate, but the latch keeps it
    zoom instead of letting the pose fall back to scroll."""
    classifier = GestureClassifier(GestureConfig())
    assert classifier.classify(zoom_pose()).gesture == C.GESTURE_ZOOM
    # Spread at 0.448: under the gate (0.48) but above the release floor
    # (0.38).  Without the latch this frame would be scroll.
    assert classifier.classify(zoom_pose(0.45)).gesture == C.GESTURE_ZOOM


def test_closing_the_v_hands_control_back_to_scroll():
    """Below the release floor the user means scroll again."""
    classifier = GestureClassifier(GestureConfig())
    assert classifier.classify(zoom_pose()).gesture == C.GESTURE_ZOOM
    assert classifier.classify(zoom_pose(0.20)).gesture == C.GESTURE_SCROLL_V


def test_reopening_the_v_rearms_the_zoom():
    classifier = GestureClassifier(GestureConfig())
    assert classifier.classify(zoom_pose()).gesture == C.GESTURE_ZOOM
    assert classifier.classify(zoom_pose(0.20)).gesture == C.GESTURE_SCROLL_V
    assert classifier.classify(zoom_pose()).gesture == C.GESTURE_ZOOM


def test_spread_thresholds_have_hysteresis():
    """Rule level: arming needs a wider V than the sustain floor."""
    from dataclasses import replace

    from vision.landmark_processor import analyze

    cfg = GestureConfig()
    assert cfg  # thresholds live in the rules module, not per-config
    obs = zoom_pose(0.60)
    fingers = analyze(obs)
    assert rules.is_zoom_enter(obs, fingers)      # 0.578 > 0.48
    assert rules.is_zoom_sustain(obs, fingers)    # 0.578 > 0.38
    closed = zoom_pose(0.45)                      # 0.448: inside the band
    closed_fingers = analyze(closed)
    assert not rules.is_zoom_enter(closed, closed_fingers)
    assert rules.is_zoom_sustain(closed, closed_fingers)
    # Opening any control finger always ends the pose (ring finger up).
    assert not rules.is_zoom_sustain(
        obs, replace(fingers, ring_extended=True))


# ---------------------------------------------------------------------------
# State machine: analog open/close -> wheel steps
# ---------------------------------------------------------------------------
def _feed(machine, spreads, dt=0.033):
    """Feed a spread sequence via real observations; per-frame (action, steps)."""
    results = []
    now = 0.0
    for s in spreads:
        obs = zoom_pose(s)
        spread = rules.finger_spread(obs)
        out = machine.update(C.GESTURE_ZOOM, now=now, zoom_spread=spread)
        results.append((out.action, out.zoom_steps))
        now += dt
    return results


def test_opening_the_v_zooms_in():
    machine = _machine(scroll_deadzone_px=0, min_gesture_frames=1)
    results = _feed(machine, [0.50, 0.55, 0.60, 0.65, 0.70])
    fired = [s for action, s in results if action == C.ACTION_ZOOM_IN]
    assert fired, "opening the V must emit zoom-in steps"
    assert all(s > 0 for s in fired)
    assert all(action in (C.ACTION_ZOOM_IN, C.ACTION_NONE)
               for action, _ in results)


def test_closing_the_v_zooms_out():
    machine = _machine(scroll_deadzone_px=0, min_gesture_frames=1)
    results = _feed(machine, [0.70, 0.65, 0.60, 0.55, 0.50])
    fired = [s for action, s in results if action == C.ACTION_ZOOM_OUT]
    assert fired, "closing the V must emit zoom-out steps"
    assert all(s < 0 for s in fired)


def test_zoom_first_frame_only_establishes_baseline():
    machine = _machine(scroll_deadzone_px=0, min_gesture_frames=1)
    out = machine.update(C.GESTURE_ZOOM, now=0.0, zoom_spread=0.55)
    assert out.action == C.ACTION_NONE          # no jump on the entry frame
    assert out.state == C.STATE_ZOOMING


def test_zoom_deadzone_suppresses_micro_jitter():
    """A barely-moving pair of fingers must not turn tracking noise into steps."""
    machine = _machine(scroll_deadzone_px=12, min_gesture_frames=1)
    results = _feed(machine, [0.55 + (0.001 if i % 2 else -0.001)
                              for i in range(40)])
    assert all(action == C.ACTION_NONE for action, _ in results)


def test_zoom_violent_jerk_is_clamped():
    machine = _machine(scroll_deadzone_px=0, min_gesture_frames=1)
    machine.update(C.GESTURE_ZOOM, now=0.0, zoom_spread=0.55)
    out = machine.update(C.GESTURE_ZOOM, now=0.033, zoom_spread=0.99)
    assert out.action == C.ACTION_ZOOM_IN
    assert abs(out.zoom_steps) <= 3
    assert abs(machine._zoom_accum) <= 4.5


def test_zoom_without_spread_measurement_is_inert():
    machine = _machine(scroll_deadzone_px=0, min_gesture_frames=1)
    out = machine.update(C.GESTURE_ZOOM, now=0.0)
    assert out.action == C.ACTION_NONE
    assert out.state == C.STATE_ZOOMING


def test_zoom_disabled_rule_does_nothing():
    cfg = GestureConfig(enable_zoom=False)
    machine = GestureStateMachine(cfg, default_rules(cfg))
    machine.update(C.GESTURE_ZOOM, now=0.0, zoom_spread=0.55)
    out = machine.update(C.GESTURE_ZOOM, now=0.033, zoom_spread=0.62)
    assert out.action == C.ACTION_NONE
    assert out.state == C.STATE_TRACKING


def test_zoom_sensitivity_scales_the_steps():
    gentle = _feed(_machine(scroll_deadzone_px=0), [0.45 + 0.02 * i
                                                   for i in range(30)])
    strong = _feed(_machine(scroll_deadzone_px=0, zoom_sensitivity=5.0),
                   [0.45 + 0.02 * i for i in range(30)])
    total_gentle = sum(s for _, s in gentle)
    total_strong = sum(s for _, s in strong)
    assert total_strong > total_gentle >= 1


# ---------------------------------------------------------------------------
# Rule config
# ---------------------------------------------------------------------------
def test_zoom_rule_is_valid_and_unique():
    cfg = GestureConfig()
    cfgmap = default_rules(cfg)
    assert cfgmap[C.GESTURE_ZOOM].enabled is True
    assert cfgmap[C.GESTURE_ZOOM].action == C.ACTION_ZOOM_IN
    assert validate_mappings(cfgmap) == []
