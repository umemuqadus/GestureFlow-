"""Tests for landmark geometry and finger/pinch analysis."""

from __future__ import annotations

import math

from app import constants as C
from tests.conftest import fist, make_hand, open_palm, pinch, point, scroll_vertical
from vision.landmark_processor import (
    angle_deg,
    analyze,
    cursor_anchor,
    distance,
    hand_scale,
    normalised_distance,
)


def test_distance_is_euclidean():
    assert distance((0, 0), (3, 4)) == 5.0
    assert distance((1, 1), (1, 1)) == 0.0


def test_angle_straight_line_is_180():
    assert math.isclose(angle_deg((0, 0), (1, 0), (2, 0)), 180.0, abs_tol=1e-6)


def test_angle_right_angle_is_90():
    assert math.isclose(angle_deg((0, 1), (0, 0), (1, 0)), 90.0, abs_tol=1e-6)


def test_hand_scale_uses_wrist_to_middle_mcp():
    obs = point()
    expected = distance(obs.point(C.WRIST), obs.point(C.MIDDLE_MCP))
    assert math.isclose(hand_scale(obs), expected, rel_tol=1e-6)


def test_normalised_distance_is_scale_invariant():
    """Uniformly scaling the hand must not change the normalised distance."""
    obs = point()
    base = normalised_distance(obs, C.THUMB_TIP, C.INDEX_TIP)
    scaled_landmarks = tuple((x * 2, y * 2, z) for (x, y, z) in obs.landmarks)
    scaled = type(obs)(landmarks=scaled_landmarks, handedness=obs.handedness,
                       score=obs.score, timestamp=obs.timestamp)
    assert math.isclose(base, normalised_distance(scaled, C.THUMB_TIP, C.INDEX_TIP),
                        rel_tol=1e-6)


def test_point_pose_extension():
    fingers = analyze(point())
    assert fingers.index_extended is True
    assert fingers.middle_extended is False
    assert fingers.ring_extended is False
    assert fingers.pinky_extended is False
    assert fingers.fist is False
    assert fingers.open_palm is False


def test_open_palm_pose():
    fingers = analyze(open_palm())
    assert fingers.index_extended and fingers.middle_extended
    assert fingers.ring_extended and fingers.pinky_extended
    assert fingers.open_palm is True
    assert fingers.fist is False


def test_fist_pose():
    fingers = analyze(fist())
    assert fingers.extended_count == 0
    assert fingers.fist is True
    assert fingers.open_palm is False


def test_pinch_distance_shrinks_when_tips_meet():
    close = analyze(pinch(0.05))
    far = analyze(pinch(0.6))
    assert close.pinch_distance < far.pinch_distance
    assert close.pinch_distance < 0.1


def test_scroll_pose_has_two_fingers_up():
    fingers = analyze(scroll_vertical())
    assert fingers.index_extended and fingers.middle_extended
    assert not fingers.ring_extended and not fingers.pinky_extended


def test_cursor_anchor_is_index_tip():
    obs = point()
    assert cursor_anchor(obs) == obs.point(C.INDEX_TIP)
