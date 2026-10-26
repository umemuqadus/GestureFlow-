"""Camera capture management.

Handles device enumeration, opening, reading and clean release.  Pure Python +
OpenCV (no Qt), so it can be unit tested with a fake capture object.
"""

from __future__ import annotations

import time
from typing import Iterator

import cv2
import numpy as np

from utils.logger import get_logger

log = get_logger(__name__)


class CameraError(RuntimeError):
    """Raised when a camera cannot be opened or read."""


def list_cameras(max_index: int = 6) -> list[int]:
    """Probe device indices 0..max_index-1 and return the ones that open.

    Tries several backends per index: integrated laptop webcams frequently
    fail on DirectShow but work on MSMF, so a single-backend probe would
    wrongly report "no camera".
    """
    found: list[int] = []
    for index in range(max_index):
        # DSHOW + MSMF are the two real Windows capture backends; CAP_ANY is
        # omitted because its FFMPEG fallback logs a warning for absent indices.
        for backend in (cv2.CAP_DSHOW, cv2.CAP_MSMF):
            cap = cv2.VideoCapture(index, backend)
            opened = cap.isOpened()
            cap.release()
            if opened:
                found.append(index)
                break
    return found


def camera_names(indices: list[int]) -> dict[int, str]:
    """Human-readable labels for the given device indices."""
    names: dict[int, str] = {}
    for index in indices:
        label = f"Camera {index}"
        for backend in (cv2.CAP_DSHOW, cv2.CAP_MSMF):
            cap = cv2.VideoCapture(index, backend)
            if cap.isOpened():
                try:
                    backend_name = cap.getBackendName()
                except Exception:  # noqa: BLE001
                    backend_name = "default"
                label = f"Camera {index} ({backend_name})"
                cap.release()
                break
            cap.release()
        names[index] = label
    return names


class CameraManager:
    """Owns one OpenCV capture. Not thread-safe; call from the vision thread."""

    def __init__(self) -> None:
        self._cap: cv2.VideoCapture | None = None
        self.device_index: int | None = None
        self.width: int = 0
        self.height: int = 0

    # -- state ---------------------------------------------------------------
    @property
    def is_open(self) -> bool:
        return self._cap is not None and self._cap.isOpened()

    def open(self, device_index: int, width: int, height: int, max_fps: int = 30) -> None:
        """Open the camera, falling back to the driver's default resolution."""
        self.close()
        cap = cv2.VideoCapture(device_index, cv2.CAP_DSHOW)
        if not cap.isOpened():
            # Retry without the DirectShow backend (helps some USB cameras).
            cap = cv2.VideoCapture(device_index)
        if not cap.isOpened():
            raise CameraError(
                f"Could not open camera {device_index}. "
                "It may be in use by another application or disconnected."
            )
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        cap.set(cv2.CAP_PROP_FPS, max_fps)
        # Reduce internal buffering so the preview stays live.
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        actual_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or width
        actual_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or height
        self._cap = cap
        self.device_index = device_index
        self.width, self.height = actual_w, actual_h
        log.info("Camera %s opened at %dx%d", device_index, actual_w, actual_h)

    def read(self) -> np.ndarray:
        """Grab one BGR frame. Raises CameraError on failure."""
        if self._cap is None or not self._cap.isOpened():
            raise CameraError("Camera is not open.")
        ok, frame = self._cap.read()
        if not ok or frame is None:
            raise CameraError("Failed to read a frame from the camera.")
        return frame

    def close(self) -> None:
        if self._cap is not None:
            try:
                self._cap.release()
            except Exception:  # noqa: BLE001 - release must never raise
                pass
            self._cap = None
            log.info("Camera released")

    def __enter__(self) -> "CameraManager":
        return self

    def __exit__(self, *exc) -> None:
        self.close()


def frames_with_retry(camera: CameraManager, attempts: int = 3,
                      delay: float = 0.05) -> Iterator[np.ndarray]:
    """Yield frames, retrying transient read failures before giving up."""
    while True:
        for attempt in range(attempts):
            try:
                yield camera.read()
                break
            except CameraError:
                if attempt == attempts - 1:
                    raise
                time.sleep(delay)
