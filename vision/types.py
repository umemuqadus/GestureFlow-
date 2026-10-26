"""Shared data types for the vision pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence


@dataclass(frozen=True)
class HandObservation:
    """One tracked hand in normalised frame coordinates.

    ``landmarks`` holds 21 ``(x, y, z)`` tuples where ``x``/``y`` are in
    ``[0, 1]`` relative to the *processed* frame (already mirrored if mirroring
    is enabled) and ``z`` is depth relative to the wrist.
    """

    landmarks: tuple[tuple[float, float, float], ...]
    handedness: str                 # "Left" | "Right" as reported by MediaPipe
    score: float                    # classification confidence [0, 1]
    timestamp: float                # monotonic capture time, seconds

    @property
    def valid(self) -> bool:
        return len(self.landmarks) == 21 and self.score > 0.0

    def point(self, index: int) -> tuple[float, float]:
        x, y, _ = self.landmarks[index]
        return x, y


@dataclass
class FrameResult:
    """Everything computed for one captured frame."""

    frame_bgr: object               # np.ndarray, annotated for preview
    observation: HandObservation | None
    gesture: str
    latency_ms: float
    timestamp: float
    extra: dict = field(default_factory=dict)
