"""Coordinate mapping: normalised frame space -> desktop pixels.

Design notes
------------
* The screen size is **injected** (never hardcoded): callers pass a callable so
  the mapper can use ``pyautogui.size()``, which matches the coordinate space
  PyAutoGUI actually writes to.  This keeps DPI-scaled desktops correct.
* An active tracking region (ROI) lets a small hand motion cover the full
  screen; the ROI is a centred rectangle occupying ``roi_fraction`` of the
  frame.
* Mirroring is already applied upstream (the tracker mirrors before inference),
  so this class only needs to support explicit axis inversion.
* Every result is clamped into valid screen bounds.
"""

from __future__ import annotations

from typing import Callable

ScreenSize = Callable[[], tuple[int, int]]


class CoordinateMapper:
    def __init__(
        self,
        screen_size: ScreenSize,
        roi_fraction: float = 0.62,
        invert_x: bool = False,
        invert_y: bool = False,
        speed: float = 1.0,
    ) -> None:
        self._screen_size = screen_size
        self.roi_fraction = max(0.2, min(1.0, roi_fraction))
        self.invert_x = invert_x
        self.invert_y = invert_y
        self.speed = max(0.1, min(5.0, speed))

    # -- configuration -------------------------------------------------------
    def update(self, roi_fraction: float | None = None,
               invert_x: bool | None = None,
               invert_y: bool | None = None,
               speed: float | None = None) -> None:
        if roi_fraction is not None:
            self.roi_fraction = max(0.2, min(1.0, roi_fraction))
        if invert_x is not None:
            self.invert_x = invert_x
        if invert_y is not None:
            self.invert_y = invert_y
        if speed is not None:
            self.speed = max(0.1, min(5.0, speed))

    # -- mapping -------------------------------------------------------------
    def _roi_bounds(self) -> tuple[float, float, float, float]:
        """(x0, y0, x1, y1) of the active region in normalised coordinates."""
        half = self.roi_fraction / 2.0
        return (0.5 - half, 0.5 - half, 0.5 + half, 0.5 + half)

    def to_virtual(self, nx: float, ny: float) -> tuple[float, float]:
        """Map a normalised frame point to a virtual screen position in [0, 1].

        Applies ROI normalisation, cursor-speed scaling and axis inversion.
        Returns fractional screen coordinates; smoothing should be applied
        *here* (in virtual space) before converting to pixels.
        """
        x0, y0, x1, y1 = self._roi_bounds()
        rx = (nx - x0) / (x1 - x0)
        ry = (ny - y0) / (y1 - y0)

        # Cursor speed: scale sensitivity around the ROI centre so a shorter
        # hand motion covers the same screen distance at higher speeds.
        rx = (rx - 0.5) * self.speed + 0.5
        ry = (ry - 0.5) * self.speed + 0.5

        if self.invert_x:
            rx = 1.0 - rx
        if self.invert_y:
            ry = 1.0 - ry
        return rx, ry

    def virtual_to_pixels(self, rx: float, ry: float) -> tuple[int, int]:
        """Convert a virtual screen position to clamped desktop pixels."""
        width, height = self._screen_size()
        if width <= 0 or height <= 0:  # pragma: no cover - defensive
            raise ValueError(f"Invalid screen size: {width}x{height}")
        sx = int(round(rx * (width - 1)))
        sy = int(round(ry * (height - 1)))
        return self.clamp(sx, sy, width, height)

    def to_screen(self, nx: float, ny: float) -> tuple[int, int]:
        """Convenience: unsmoothed normalised frame point -> desktop pixels."""
        rx, ry = self.to_virtual(nx, ny)
        return self.virtual_to_pixels(rx, ry)

    @staticmethod
    def clamp(x: int, y: int, width: int, height: int) -> tuple[int, int]:
        """Clamp a point into the valid desktop area.

        A 1px inset is applied on the top and left edges.  PyAutoGUI treats the
        exact top-left pixel ``(0, 0)`` as its emergency fail-safe corner: once
        the real cursor lands there, ``failSafeCheck()`` raises on *every*
        subsequent mouse call — including the one that would move it away —
        permanently deadlocking control until the physical mouse is nudged.  By
        never emitting ``(0, 0)`` we keep the fail-safe enabled (still a genuine
        safety net for other corners) while removing the deadlock.  The inset is
        imperceptible and keeps the cursor able to reach every usable pixel.
        """
        return (max(1, min(int(x), int(width) - 1)),
                max(1, min(int(y), int(height) - 1)))

    def is_inside_roi(self, nx: float, ny: float, margin: float = 0.08) -> bool:
        """True when the point is comfortably inside the active region.

        Used to avoid snapping the cursor to the ROI edge when the hand drifts
        outside the intended tracking area.
        """
        x0, y0, x1, y1 = self._roi_bounds()
        return (x0 - margin) <= nx <= (x1 + margin) and (y0 - margin) <= ny <= (y1 + margin)
