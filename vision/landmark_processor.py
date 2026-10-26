"""Geometric landmark processing.

Pure functions over 21-point hand landmarks; no MediaPipe, OpenCV, Qt or numpy
imports so the maths can be unit tested in isolation.

Coordinates are normalised to [0, 1] frame space.  Distances are computed in a
scale-invariant way (relative to hand size) so the same thresholds work at any
distance from the camera.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from app import constants as C
from vision.types import HandObservation

Point = tuple[float, float, float]


def distance(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Euclidean distance between two 2-D points."""
    return math.hypot(a[0] - b[0], a[1] - b[1])


def hand_scale(obs: HandObservation) -> float:
    """Robust hand size estimate: wrist-to-middle-MCP distance.

    Used to normalise all other distances, making thresholds independent of how
    close the hand is to the camera.
    """
    wrist = obs.point(C.WRIST)
    middle_mcp = obs.point(C.MIDDLE_MCP)
    scale = distance(wrist, middle_mcp)
    return scale if scale > 1e-6 else 1e-6


def normalised_distance(obs: HandObservation, a: int, b: int) -> float:
    """Distance between landmarks ``a`` and ``b``, divided by hand scale."""
    return distance(obs.point(a), obs.point(b)) / hand_scale(obs)


def angle_deg(a: tuple[float, float], b: tuple[float, float], c: tuple[float, float]) -> float:
    """Angle ABC in degrees (B is the vertex)."""
    ba = (a[0] - b[0], a[1] - b[1])
    bc = (c[0] - b[0], c[1] - b[1])
    denom = math.hypot(*ba) * math.hypot(*bc)
    if denom < 1e-9:
        return 180.0
    cos_val = max(-1.0, min(1.0, (ba[0] * bc[0] + ba[1] * bc[1]) / denom))
    return math.degrees(math.acos(cos_val))


@dataclass(frozen=True)
class FingerState:
    """Extension flags and pinch metrics derived from one hand."""

    index_extended: bool
    middle_extended: bool
    ring_extended: bool
    pinky_extended: bool
    thumb_extended: bool
    pinch_distance: float        # thumb tip <-> index tip, normalised
    right_pinch_distance: float  # thumb tip <-> middle tip, normalised
    open_palm: bool
    fist: bool

    @property
    def extended_count(self) -> int:
        return sum(
            (self.index_extended, self.middle_extended,
             self.ring_extended, self.pinky_extended)
        )


def _finger_extended(obs: HandObservation, mcp: int, pip: int, dip: int, tip: int) -> bool:
    """A finger counts as extended when tip is farther from the wrist than PIP
    *and* the PIP joint is comparatively straight."""
    wrist = obs.point(C.WRIST)
    d_tip = distance(obs.point(tip), wrist)
    d_pip = distance(obs.point(pip), wrist)
    bend = angle_deg(obs.point(mcp), obs.point(pip), obs.point(tip))
    return d_tip > d_pip * 1.08 and bend > 145.0


def _thumb_extended(obs: HandObservation) -> bool:
    """Thumb is extended when its tip is far from the index MCP."""
    return normalised_distance(obs, C.THUMB_TIP, C.INDEX_MCP) > 1.35


def analyze(obs: HandObservation) -> FingerState:
    """Compute the full finger/pinch state for a hand."""
    index = _finger_extended(obs, C.INDEX_MCP, C.INDEX_PIP, C.INDEX_DIP, C.INDEX_TIP)
    middle = _finger_extended(obs, C.MIDDLE_MCP, C.MIDDLE_PIP, C.MIDDLE_DIP, C.MIDDLE_TIP)
    ring = _finger_extended(obs, C.RING_MCP, C.RING_PIP, C.RING_DIP, C.RING_TIP)
    pinky = _finger_extended(obs, C.PINKY_MCP, C.PINKY_PIP, C.PINKY_DIP, C.PINKY_TIP)
    thumb = _thumb_extended(obs)

    pinch = normalised_distance(obs, C.THUMB_TIP, C.INDEX_TIP)
    right_pinch = normalised_distance(obs, C.THUMB_TIP, C.MIDDLE_TIP)

    extended_count = sum((index, middle, ring, pinky))
    return FingerState(
        index_extended=index,
        middle_extended=middle,
        ring_extended=ring,
        pinky_extended=pinky,
        thumb_extended=thumb,
        pinch_distance=pinch,
        right_pinch_distance=right_pinch,
        open_palm=extended_count >= 4 and thumb,
        fist=extended_count == 0 and not thumb,
    )


def cursor_anchor(obs: HandObservation) -> tuple[float, float]:
    """Point used for cursor tracking: the index fingertip.

    Falls back to the index PIP joint when the tip is occluded (very low
    confidence is handled upstream, this is a geometry-only fallback).
    """
    return obs.point(C.INDEX_TIP)
