"""Frame processing: capture -> track -> annotate.

Also draws the landmark overlay used by the live preview (OpenCV primitives
only; MediaPipe's drawing utils are not required).
"""

from __future__ import annotations

import time

import cv2
import numpy as np

from app import constants as C
from vision.camera_manager import CameraManager, CameraError
from vision.hand_tracker import HandTracker
from vision.types import HandObservation

# MediaPipe hand connections (pairs of landmark indices).
HAND_CONNECTIONS: tuple[tuple[int, int], ...] = (
    (0, 1), (1, 2), (2, 3), (3, 4),
    (0, 5), (5, 6), (6, 7), (7, 8),
    (5, 9), (9, 10), (10, 11), (11, 12),
    (9, 13), (13, 14), (14, 15), (15, 16),
    (13, 17), (17, 18), (18, 19), (19, 20),
    (0, 17),
)


class FrameProcessor:
    """Reads frames from a :class:`CameraManager` and tracks one hand."""

    def __init__(self, camera: CameraManager, tracker: HandTracker) -> None:
        self.camera = camera
        self.tracker = tracker

    def process_once(self, mirror: bool = True,
                     show_landmarks: bool = True) -> tuple[HandObservation | None, np.ndarray, float]:
        """Capture and process one frame.

        Returns ``(observation, annotated_frame_bgr, latency_ms)``.
        ``observation`` is ``None`` when no hand is visible.
        """
        start = time.perf_counter()
        frame = self.camera.read()
        observation = self.tracker.process(frame, mirror=mirror)
        annotated = frame
        if show_landmarks:
            annotated = self._annotate(frame, observation, mirror)
        latency_ms = (time.perf_counter() - start) * 1000.0
        return observation, annotated, latency_ms

    @staticmethod
    def _annotate(frame: np.ndarray, obs: HandObservation | None,
                  mirror: bool) -> np.ndarray:
        """Draw landmarks; the image is flipped first when mirroring so the
        overlay lines up with what the tracker saw."""
        if mirror:
            canvas = cv2.flip(frame, 1)
        else:
            canvas = frame
        if obs is None:
            return canvas

        h, w = canvas.shape[:2]
        points: list[tuple[int, int]] = []
        for x, y, _ in obs.landmarks:
            px = int(np.clip(x, 0.0, 1.0) * (w - 1))
            py = int(np.clip(y, 0.0, 1.0) * (h - 1))
            points.append((px, py))

        for a, b in HAND_CONNECTIONS:
            cv2.line(canvas, points[a], points[b], (180, 190, 230), 2, cv2.LINE_AA)
        for i, (px, py) in enumerate(points):
            color = (60, 120, 240) if i in (C.INDEX_TIP, C.THUMB_TIP) else (200, 210, 235)
            radius = 5 if i in (C.INDEX_TIP, C.THUMB_TIP, C.MIDDLE_TIP) else 3
            cv2.circle(canvas, (px, py), radius, color, -1, cv2.LINE_AA)

        # Pinch indicator: line between thumb and index tips.
        cv2.line(canvas, points[C.THUMB_TIP], points[C.INDEX_TIP],
                 (80, 200, 160), 1, cv2.LINE_AA)
        return canvas
