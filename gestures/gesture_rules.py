"""Geometric gesture rules and their priority order.

Each rule is a pure predicate over :class:`~vision.landmark_processor.FingerState`
plus the runtime :class:`~app.config.GestureConfig`.  Hysteresis for pinch-style
gestures is applied here (``enter`` vs ``sustain`` thresholds) so a hand
hovering at the threshold cannot flicker between states.
"""

from __future__ import annotations

from vision.landmark_processor import (
    FingerState,
    distance,
    hand_scale,
    normalised_distance,
)
from vision.types import HandObservation

from app import constants as C
from app.config import GestureConfig

# Highest priority first.  The classifier walks this list and takes the first
# gesture whose predicate is satisfied.
#
# The system-control poses (thumb up/down, shaka, flat hand, three fingers) sit
# after the pause gesture and before point/scroll/fist.  They are mutually
# exclusive with point/scroll/palm by finger-extension count, and the distance
# based pinch/right-click rules stay ahead of everything so a click is never
# stolen by a system gesture.
PRIORITY: tuple[str, ...] = (
    C.GESTURE_PINCH,
    C.GESTURE_RIGHT_CLICK,
    C.GESTURE_OPEN_PALM,
    C.GESTURE_THUMB_UP,
    C.GESTURE_THUMB_DOWN,
    C.GESTURE_SHAKA,
    C.GESTURE_FLAT_HAND,
    C.GESTURE_THREE_FINGERS,
    C.GESTURE_SCROLL_V,
    C.GESTURE_SCROLL_H,
    C.GESTURE_POINT,
    C.GESTURE_FIST,
)

# A curled-hand pose only counts as a deliberate volume gesture when the thumb
# clears the knuckle line by this much (hand-scale units).  The asymmetric
# margins keep a plain fist (thumb wrapped across the fingers, i.e. sitting at
# knuckle height) from being read as a direction: a genuine thumbs-up rises
# clearly above the knuckles, a genuine thumbs-down drops well below them.
THUMB_UP_MARGIN = 0.30
THUMB_DOWN_MARGIN = 0.50


def is_scroll_pose(fingers: FingerState) -> bool:
    """Index + middle up with ring + pinky down.

    This two-finger configuration takes precedence over pinch gestures so a
    scroll is not mistaken for a click when the thumb happens to sit near the
    index tip.
    """
    return (
        fingers.index_extended
        and fingers.middle_extended
        and not fingers.ring_extended
        and not fingers.pinky_extended
    )


def is_pinch_enter(fingers: FingerState, cfg: GestureConfig) -> bool:
    """Pinch starts when thumb+index are closer than the activation threshold
    and the middle finger is *not* also pinched (keeps right-click distinct).

    The scroll pose is excluded so two-finger scrolling is not captured by the
    pinch rule.
    """
    return (
        not is_scroll_pose(fingers)
        and fingers.pinch_distance < cfg.pinch_threshold
        and fingers.right_pinch_distance > cfg.right_pinch_threshold
    )


def is_pinch_sustain(fingers: FingerState, cfg: GestureConfig) -> bool:
    """Holding a pinch: distance may drift past the activation point but stays
    under the (larger) release threshold."""
    return (
        fingers.pinch_distance < cfg.release_threshold
        and fingers.right_pinch_distance > cfg.right_pinch_threshold
    )


def is_right_click_enter(fingers: FingerState, cfg: GestureConfig) -> bool:
    """Thumb+middle pinch with the middle finger *reaching* toward the thumb.

    Requiring ``middle_extended`` keeps a resting/curled middle finger (as in a
    point or fist pose, where the thumb and middle tips naturally sit close in
    the palm) from being misread as a right click.  The scroll pose is excluded
    for the same reason as in :func:`is_pinch_enter`.
    """
    return (
        not is_scroll_pose(fingers)
        and fingers.middle_extended
        and fingers.right_pinch_distance < cfg.right_pinch_threshold
        and fingers.pinch_distance > cfg.pinch_threshold
    )


def is_right_click_sustain(fingers: FingerState, cfg: GestureConfig) -> bool:
    limit = cfg.right_pinch_threshold + 0.12
    return (
        fingers.middle_extended
        and fingers.right_pinch_distance < limit
        and fingers.pinch_distance > cfg.pinch_threshold
    )


def is_scroll_vertical(obs: HandObservation, fingers: FingerState) -> bool:
    """Index + middle fingers up while ring + pinky stay down."""
    return is_scroll_pose(fingers)


def is_scroll_horizontal(obs: HandObservation, fingers: FingerState) -> bool:
    """Same two fingers up, but the hand is rotated so the dominant movement
    axis is horizontal (index tip well to one side of the middle tip)."""
    if not is_scroll_vertical(obs, fingers):
        return False
    ix, iy = obs.point(C.INDEX_TIP)
    mx, my = obs.point(C.MIDDLE_TIP)
    dx, dy = abs(ix - mx), abs(iy - my)
    return dx > dy * 1.4 and dx > 0.03


def is_point(fingers: FingerState) -> bool:
    """Index extended, middle/ring/pinky curled -> cursor movement."""
    return (
        fingers.index_extended
        and not fingers.middle_extended
        and not fingers.ring_extended
    )


def is_open_palm(fingers: FingerState) -> bool:
    return fingers.open_palm


def is_fist(fingers: FingerState) -> bool:
    return fingers.fist


# -- system-control poses ------------------------------------------------------
def _knuckle_top_y(obs: HandObservation) -> float:
    """Y of the topmost knuckle (MCP).  Frame y decreases downward, so a
    smaller value is higher in the frame."""
    ys = [
        obs.point(C.INDEX_MCP)[1],
        obs.point(C.MIDDLE_MCP)[1],
        obs.point(C.RING_MCP)[1],
        obs.point(C.PINKY_MCP)[1],
    ]
    return min(ys)


def _curled_hand(fingers: FingerState) -> bool:
    """All four fingers curled — the shared base for fist / thumb-up / thumb-down."""
    return fingers.extended_count == 0


def is_thumb_up(obs: HandObservation, fingers: FingerState) -> bool:
    """Curled hand with the thumb rising clearly above the knuckles -> volume up.

    Checked before :func:`is_fist` (same finger count) so a deliberate thumbs-up
    is never mistaken for a screenshot fist.  The reference is the knuckle line
    rather than the wrist, because a closed fist already sits well above the
    wrist and would otherwise register as "up".
    """
    if not _curled_hand(fingers):
        return False
    scale = hand_scale(obs)
    rise = _knuckle_top_y(obs) - obs.point(C.THUMB_TIP)[1]
    return rise / scale > THUMB_UP_MARGIN


def is_thumb_down(obs: HandObservation, fingers: FingerState) -> bool:
    """Curled hand with the thumb dropping well below the knuckles -> volume down.

    The larger margin is deliberate: it keeps a resting fist whose thumb hangs
    slightly below the knuckles from lowering the volume.
    """
    if not _curled_hand(fingers):
        return False
    scale = hand_scale(obs)
    drop = obs.point(C.THUMB_TIP)[1] - _knuckle_top_y(obs)
    return drop / scale > THUMB_DOWN_MARGIN


def is_shaka(fingers: FingerState) -> bool:
    """Thumb + pinky out, index/middle/ring curled -> mute.

    Requiring the thumb to splay away from the curled index finger also keeps
    the thumb-tip/index-tip distance large, so this pose cannot be captured by
    the pinch (left-click) rule.
    """
    return (
        fingers.thumb_extended
        and fingers.pinky_extended
        and not fingers.index_extended
        and not fingers.middle_extended
        and not fingers.ring_extended
    )


def is_flat_hand(fingers: FingerState) -> bool:
    """Four fingers up with the thumb tucked -> play/pause.

    Distinguished from the open palm (pause) purely by the thumb: an open palm
    splays the thumb, a flat hand keeps it folded against the fingers.
    """
    return fingers.extended_count == 4 and not fingers.thumb_extended


def is_three_fingers(fingers: FingerState) -> bool:
    """Index + middle + ring up, pinky down -> brightness.

    The ring finger separates this from the two-finger scroll pose (ring down).
    """
    return (
        fingers.index_extended
        and fingers.middle_extended
        and fingers.ring_extended
        and not fingers.pinky_extended
    )


def gesture_distance(obs: HandObservation, fingers: FingerState, gesture: str) -> float:
    """Distance metric used for the confidence read-out (lower = stronger)."""
    if gesture == C.GESTURE_PINCH:
        return fingers.pinch_distance
    if gesture == C.GESTURE_RIGHT_CLICK:
        return fingers.right_pinch_distance
    if gesture == C.GESTURE_SCROLL_H:
        ix, _ = obs.point(C.INDEX_TIP)
        mx, _ = obs.point(C.MIDDLE_TIP)
        return abs(ix - mx)
    if gesture == C.GESTURE_POINT:
        wrist = obs.point(C.WRIST)
        tip = obs.point(C.INDEX_TIP)
        return distance(wrist, tip)
    return 0.0
