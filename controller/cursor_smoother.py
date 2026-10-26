"""Cursor smoothing filters.

Two strategies:

* :class:`EmaSmoother` - exponential moving average with a fixed alpha derived
  from the user's ``smoothing`` slider (0 = raw, 1 = very heavy).  Simple,
  predictable, and the default fallback.
* :class:`OneEuroFilter` - the One Euro filter (Casiez et al., 2012), which
  adapts its cutoff to speed: heavy filtering at rest (kills jitter), light
  filtering during fast motion (keeps responsiveness).

Both operate in screen-pixel space and expose ``reset()`` so a new gesture
sequence starts clean instead of sliding in from a stale position.
"""

from __future__ import annotations

import math


class EmaSmoother:
    """Exponential moving average over 2-D points."""

    def __init__(self, smoothing: float = 0.5) -> None:
        self.smoothing = max(0.0, min(0.98, smoothing))
        self._state: tuple[float, float] | None = None

    def update_smoothing(self, smoothing: float) -> None:
        self.smoothing = max(0.0, min(0.98, smoothing))

    def reset(self) -> None:
        self._state = None

    @property
    def alpha(self) -> float:
        """Blend factor for the new sample (1 = no smoothing)."""
        return max(0.02, 1.0 - self.smoothing)

    def __call__(self, x: float, y: float) -> tuple[float, float]:
        if self._state is None:
            self._state = (x, y)
            return (x, y)
        a = self.alpha
        nx = self._state[0] + a * (x - self._state[0])
        ny = self._state[1] + a * (y - self._state[1])
        self._state = (nx, ny)
        return (nx, ny)


class _OneEuroAxis:
    """One Euro filter for a single scalar channel."""

    def __init__(self, min_cutoff: float = 1.0, beta: float = 0.007,
                 d_cutoff: float = 1.0) -> None:
        self.min_cutoff = max(1e-3, min_cutoff)
        self.beta = beta
        self.d_cutoff = max(1e-3, d_cutoff)
        self._x: float | None = None
        self._dx: float = 0.0
        self._t: float | None = None

    @staticmethod
    def _alpha(cutoff: float, dt: float) -> float:
        tau = 1.0 / (2.0 * math.pi * cutoff)
        return 1.0 / (1.0 + tau / max(dt, 1e-6))

    def reset(self) -> None:
        self._x = None
        self._dx = 0.0
        self._t = None

    def __call__(self, value: float, t: float) -> float:
        if self._x is None or self._t is None:
            self._x, self._t = value, t
            return value
        dt = max(t - self._t, 1e-6)
        self._t = t
        # Derivative of the signal, smoothed with the d-cutoff.
        raw_dx = (value - self._x) / dt
        a_d = self._alpha(self.d_cutoff, dt)
        self._dx = a_d * raw_dx + (1 - a_d) * self._dx
        # Cutoff adapted to speed: fast motion -> higher cutoff -> less lag.
        cutoff = self.min_cutoff + self.beta * abs(self._dx)
        a = self._alpha(cutoff, dt)
        self._x = a * value + (1 - a) * self._x
        return self._x


class OneEuroFilter:
    """One Euro filter over a 2-D point, timestamped in seconds."""

    def __init__(self, min_cutoff: float = 1.2, beta: float = 0.007) -> None:
        self._x = _OneEuroAxis(min_cutoff, beta)
        self._y = _OneEuroAxis(min_cutoff, beta)

    def reset(self) -> None:
        self._x.reset()
        self._y.reset()

    def __call__(self, x: float, y: float, t: float) -> tuple[float, float]:
        return (self._x(x, t), self._y(y, t))


class CursorSmoother:
    """Facade choosing between EMA and One Euro based on user settings."""

    def __init__(self, smoothing: float = 0.55, use_one_euro: bool = True,
                 min_cutoff: float = 1.2, beta: float = 0.007) -> None:
        self.ema = EmaSmoother(smoothing)
        self.one_euro = OneEuroFilter(min_cutoff, beta)
        self.use_one_euro = use_one_euro

    def update(self, smoothing: float | None = None, use_one_euro: bool | None = None,
               min_cutoff: float | None = None, beta: float | None = None) -> None:
        if smoothing is not None:
            self.ema.update_smoothing(smoothing)
        if use_one_euro is not None:
            self.use_one_euro = use_one_euro
        if min_cutoff is not None or beta is not None:
            self.one_euro = OneEuroFilter(
                min_cutoff if min_cutoff is not None else 1.2,
                beta if beta is not None else 0.007,
            )

    def reset(self) -> None:
        self.ema.reset()
        self.one_euro.reset()

    def __call__(self, x: float, y: float, t: float) -> tuple[float, float]:
        if self.use_one_euro:
            return self.one_euro(x, y, t)
        return self.ema(x, y)
