"""Shared test helpers.

Builds synthetic 21-landmark hands in normalised frame coordinates so gesture
logic can be tested without a webcam.  Positions were chosen so each pose
satisfies the geometric rules in ``vision.landmark_processor``.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

# Make project modules importable when running `pytest` from the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from vision.types import HandObservation  # noqa: E402


def _chain(base: tuple[float, float], extended: bool,
           direction: tuple[float, float] = (0.0, -1.0),
           spacing: float = 0.06) -> list[tuple[float, float, float]]:
    """Build a 4-joint finger (PIP/DIP/TIP + base) as extended or curled."""
    dx, dy = direction
    norm = math.hypot(dx, dy) or 1.0
    ux, uy = dx / norm, dy / norm
    if extended:
        points = []
        x, y = base
        for _ in range(3):
            x += ux * spacing
            y += uy * spacing
            points.append((x, y, 0.0))
        return points
    # Curled: bend so the tip folds back toward the palm and the PIP angle is acute.
    pip = (base[0], base[1] - 0.05)
    dip = (pip[0] + 0.03, pip[1] - 0.02)
    tip = (dip[0] - 0.01, dip[1] + 0.06)
    return [(pip[0], pip[1], 0.0), (dip[0], dip[1], 0.0), (tip[0], tip[1], 0.0)]


def make_hand(
    *,
    index_ext: bool = True,
    middle_ext: bool = False,
    ring_ext: bool = False,
    pinky_ext: bool = False,
    thumb_ext: bool = False,
    thumb_tip: tuple[float, float] | None = None,
    index_tip: tuple[float, float] | None = None,
    middle_tip: tuple[float, float] | None = None,
    score: float = 0.95,
) -> HandObservation:
    """Construct a synthetic hand pose as a ``HandObservation``."""
    wrist = (0.50, 0.90, 0.0)
    thumb_cmc = (0.42, 0.82, 0.0)
    thumb_mcp = (0.38, 0.72, 0.0)
    thumb_ip = (0.34, 0.62, 0.0)
    if thumb_ext:
        # Thumb reaching up and out: far from the index MCP (satisfies the
        # >1.35 x hand-scale rule used by _thumb_extended).
        tip = thumb_tip or (0.16, 0.24)
        thumb_tip_pt = (tip[0], tip[1], 0.0)
    else:
        tip = thumb_tip or (0.44, 0.55)
        thumb_tip_pt = (tip[0], tip[1], 0.0)
    thumb = [thumb_cmc, thumb_mcp, thumb_ip, thumb_tip_pt]

    index_base = (0.44, 0.60)
    middle_base = (0.50, 0.58)
    ring_base = (0.56, 0.60)
    pinky_base = (0.61, 0.63)

    index_pts = _chain(index_base, index_ext, direction=(0.0, -1.0))
    middle_pts = _chain(middle_base, middle_ext, direction=(0.0, -1.0))
    ring_pts = _chain(ring_base, ring_ext, direction=(0.0, -1.0))
    pinky_pts = _chain(pinky_base, pinky_ext, direction=(0.0, -1.0))

    if index_tip is not None:
        index_pts[2] = (index_tip[0], index_tip[1], 0.0)
    if middle_tip is not None:
        middle_pts[2] = (middle_tip[0], middle_tip[1], 0.0)

    landmarks = (
        wrist,
        *thumb,
        (index_base[0], index_base[1], 0.0), *index_pts,
        (middle_base[0], middle_base[1], 0.0), *middle_pts,
        (ring_base[0], ring_base[1], 0.0), *ring_pts,
        (pinky_base[0], pinky_base[1], 0.0), *pinky_pts,
    )
    assert len(landmarks) == 21, len(landmarks)
    return HandObservation(landmarks=landmarks, handedness="Right", score=score, timestamp=0.0)


# -- common poses -------------------------------------------------------------
def open_palm() -> HandObservation:
    return make_hand(index_ext=True, middle_ext=True, ring_ext=True, pinky_ext=True,
                     thumb_ext=True)


def fist() -> HandObservation:
    return make_hand(index_ext=False, middle_ext=False, ring_ext=False, pinky_ext=False,
                     thumb_ext=False)


def point() -> HandObservation:
    return make_hand(index_ext=True, middle_ext=False, ring_ext=False, pinky_ext=False)


def pinch(distance: float = 0.1) -> HandObservation:
    """Index-thumb pinch at a given normalised distance (hand scale = 0.32)."""
    # Index tip fixed; thumb tip placed to achieve the requested normalised gap.
    index_tip = (0.44, 0.42)
    scale = 0.32
    gap = distance * scale
    thumb_tip = (index_tip[0] + gap, index_tip[1])
    return make_hand(index_ext=True, middle_ext=False, ring_ext=False, pinky_ext=False,
                     thumb_tip=thumb_tip, index_tip=index_tip)


def right_pinch(distance: float = 0.1) -> HandObservation:
    """Thumb+middle pinch with the index finger curled out of the way."""
    middle_tip = (0.50, 0.40)
    scale = 0.32
    gap = distance * scale
    thumb_tip = (middle_tip[0] + gap, middle_tip[1])
    return make_hand(index_ext=False, middle_ext=True, ring_ext=False, pinky_ext=False,
                     thumb_tip=thumb_tip, middle_tip=middle_tip)


def scroll_vertical() -> HandObservation:
    return make_hand(index_ext=True, middle_ext=True, ring_ext=False, pinky_ext=False)


def zoom_pose(spread: float = 0.60) -> HandObservation:
    """Index + middle up and opened into a 'V', ring/pinky down -> zoom.

    ``spread`` is the tip-to-tip distance in hand-scale units (hand scale =
    0.32).  The default (0.60) clears the arming threshold (0.48); smaller
    values model the closing motion (0.45 = latched zoom-out, 0.20 = back to
    the scroll pose).  The whole finger chain leans outward so the joints
    stay straight and both fingers still count as extended.
    """
    u = max(0.0, (0.32 * spread - 0.06) / 0.36)  # per-finger outward lean
    index = _chain((0.44, 0.60), True, direction=(-u, -1.0))
    middle = _chain((0.50, 0.58), True, direction=(u, -1.0))
    ring = _chain((0.56, 0.60), False)
    pinky = _chain((0.61, 0.63), False)
    thumb = [(0.42, 0.82, 0.0), (0.38, 0.72, 0.0), (0.34, 0.62, 0.0),
             (0.44, 0.55, 0.0)]
    landmarks = (
        (0.50, 0.90, 0.0),
        *thumb,
        (0.44, 0.60, 0.0), *index,
        (0.50, 0.58, 0.0), *middle,
        (0.56, 0.60, 0.0), *ring,
        (0.61, 0.63, 0.0), *pinky,
    )
    assert len(landmarks) == 21, len(landmarks)
    return HandObservation(landmarks=landmarks, handedness="Right", score=0.95,
                           timestamp=0.0)


# -- system-control poses -------------------------------------------------------
def thumb_up_pose() -> HandObservation:
    """Curled hand, thumb raised well above the knuckles -> volume up."""
    return make_hand(index_ext=False, middle_ext=False, ring_ext=False,
                     pinky_ext=False, thumb_ext=True)


def thumb_down_pose() -> HandObservation:
    """Curled hand, thumb dropped below the knuckles -> volume down."""
    return make_hand(index_ext=False, middle_ext=False, ring_ext=False,
                     pinky_ext=False, thumb_tip=(0.50, 0.85))


def shaka_pose() -> HandObservation:
    """Thumb + pinky out, index/middle/ring curled -> mute."""
    return make_hand(index_ext=False, middle_ext=False, ring_ext=False,
                     pinky_ext=True, thumb_ext=True)


def flat_hand_pose() -> HandObservation:
    """Four fingers up with the thumb tucked -> play/pause."""
    return make_hand(index_ext=True, middle_ext=True, ring_ext=True,
                     pinky_ext=True, thumb_ext=False)


def three_fingers_pose() -> HandObservation:
    """Index + middle + ring up, pinky down -> brightness."""
    return make_hand(index_ext=True, middle_ext=True, ring_ext=True,
                     pinky_ext=False)


@pytest.fixture
def no_hand() -> None:
    return None


class FakeMouseBackend:
    """Stands in for PyAutoGUI so tests never move the real mouse."""

    def __init__(self, width: int = 1920, height: int = 1080) -> None:
        self.calls: list[tuple] = []
        self._pos = (0, 0)
        self._size = (width, height)
        self.FAILSAFE = True
        self.PAUSE = 0.0

    # -- recorded actions -----------------------------------------------------
    def moveTo(self, x, y, _pause=False):  # noqa: N802 - mirrors pyautogui API
        self.calls.append(("moveTo", int(x), int(y)))
        self._pos = (int(x), int(y))

    def click(self, button="left", _pause=False):
        self.calls.append(("click", button))

    def doubleClick(self, _pause=False):  # noqa: N802
        self.calls.append(("doubleClick",))

    def mouseDown(self, button="left", _pause=False):  # noqa: N802
        self.calls.append(("mouseDown", button))

    def mouseUp(self, button="left", _pause=False):  # noqa: N802
        self.calls.append(("mouseUp", button))

    def scroll(self, amount, _pause=False):
        self.calls.append(("scroll", int(amount)))

    def hscroll(self, amount, _pause=False):  # noqa: N802
        self.calls.append(("hscroll", int(amount)))

    def keyDown(self, key):  # noqa: N802 - mirrors pyautogui API
        self.calls.append(("keyDown", key))

    def keyUp(self, key):  # noqa: N802
        self.calls.append(("keyUp", key))

    def size(self):
        class _Size:
            width = self._size[0]
            height = self._size[1]
        return _Size()

    def position(self):
        class _Pos:
            x = self._pos[0]
            y = self._pos[1]
        return _Pos()

    # -- helpers ----------------------------------------------------------------
    def of_type(self, name: str) -> list[tuple]:
        return [c for c in self.calls if c[0] == name]
