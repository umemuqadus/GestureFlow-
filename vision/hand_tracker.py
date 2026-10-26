"""Hand-landmark tracking via the MediaPipe Tasks API.

Uses the ``HandLandmarker`` task with a *local* model file
(``assets/models/hand_landmarker.task``), which is downloaded once during the
explicit installation step by ``scripts/download_model.py``.  Nothing is
fetched at runtime and no frame ever leaves the machine.

MediaPipe is imported lazily so the rest of the application (settings, history,
tests) keeps working when the dependency or the model file is unavailable.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np

from utils.logger import get_logger
from vision.types import HandObservation

log = get_logger(__name__)

# Model location: repo assets folder, or bundled next to a frozen executable.
_REPO_MODEL = Path(__file__).resolve().parent.parent / "assets" / "models" / "hand_landmarker.task"
_RELATIVE_MODEL = Path("assets") / "models" / "hand_landmarker.task"
_FROZEN_MODEL = (Path(sys.executable).parent / _RELATIVE_MODEL) if getattr(sys, "frozen", False) else None


def model_path() -> Path:
    """Best existing model location; prefers the repo copy."""
    for candidate in (_REPO_MODEL, _FROZEN_MODEL):
        if candidate is None:
            continue
        try:
            if candidate.is_file():
                return candidate
        except OSError:  # pragma: no cover - exotic filesystem errors
            continue
    return _REPO_MODEL


def model_available() -> tuple[bool, str]:
    path = model_path()
    if path.is_file() and path.stat().st_size > 1024:
        return True, str(path)
    return False, (
        "Hand-tracking model not found. Run "
        "'python scripts/download_model.py' once during setup."
    )


_MP = None
_MP_ERROR: str | None = None


def _load_mediapipe():
    global _MP, _MP_ERROR
    if _MP is not None or _MP_ERROR is not None:
        return _MP
    try:
        import mediapipe as mp  # noqa: PLC0415 - lazy on purpose

        _MP = mp
        log.info("MediaPipe %s loaded", getattr(mp, "__version__", "unknown"))
    except Exception as exc:  # noqa: BLE001 - report, don't crash
        _MP_ERROR = str(exc)
        log.error("MediaPipe unavailable: %s", exc)
    return _MP


def mediapipe_available() -> tuple[bool, str]:
    mp = _load_mediapipe()
    if mp is None:
        return False, _MP_ERROR or "MediaPipe failed to load."
    return True, ""


class HandTracker:
    """Wraps MediaPipe ``HandLandmarker`` (VIDEO running mode)."""

    def __init__(
        self,
        max_num_hands: int = 1,
        detection_confidence: float = 0.6,
        tracking_confidence: float = 0.6,
    ) -> None:
        self.max_num_hands = max_num_hands
        self.detection_confidence = detection_confidence
        self.tracking_confidence = tracking_confidence
        self._landmarker = None
        self._init_error: str | None = None
        self._last_timestamp_ms: int = 0
        self._init()

    # -- lifecycle -----------------------------------------------------------
    def _init(self) -> None:
        mp = _load_mediapipe()
        if mp is None:
            self._init_error = _MP_ERROR or "MediaPipe failed to load."
            return
        ok, detail = model_available()
        if not ok:
            self._init_error = detail
            log.error(detail)
            return
        try:
            from mediapipe.tasks.python import vision as mp_vision  # noqa: PLC0415
            from mediapipe.tasks.python.core.base_options import BaseOptions  # noqa: PLC0415

            options = mp_vision.HandLandmarkerOptions(
                base_options=BaseOptions(model_asset_path=str(model_path())),
                running_mode=mp_vision.RunningMode.VIDEO,
                num_hands=self.max_num_hands,
                min_hand_detection_confidence=self.detection_confidence,
                min_hand_presence_confidence=self.detection_confidence,
                min_tracking_confidence=self.tracking_confidence,
            )
            self._landmarker = mp_vision.HandLandmarker.create_from_options(options)
            self._init_error = None
            self._last_timestamp_ms = 0
            log.info(
                "Hand tracker ready (hands=%d, detect=%.2f, track=%.2f)",
                self.max_num_hands, self.detection_confidence, self.tracking_confidence,
            )
        except Exception as exc:  # noqa: BLE001
            self._init_error = str(exc)
            log.error("Hand landmarker initialisation failed: %s", exc)

    @property
    def ready(self) -> bool:
        return self._landmarker is not None

    @property
    def error(self) -> str | None:
        return self._init_error

    def reconfigure(self, max_num_hands: int | None = None,
                    detection_confidence: float | None = None,
                    tracking_confidence: float | None = None) -> bool:
        if max_num_hands is not None:
            self.max_num_hands = max_num_hands
        if detection_confidence is not None:
            self.detection_confidence = detection_confidence
        if tracking_confidence is not None:
            self.tracking_confidence = tracking_confidence
        self.close()
        self._init()
        return self.ready

    # -- inference -----------------------------------------------------------
    def process(self, frame_bgr: np.ndarray, mirror: bool = True) -> HandObservation | None:
        """Detect the most prominent hand in a BGR frame.

        The frame is converted to RGB and mirrored *before* tracking when
        ``mirror`` is True, so returned coordinates match the mirrored preview
        and cursor mapping stays intuitive (move hand right -> cursor right).
        """
        if self._landmarker is None:
            return None
        mp = _load_mediapipe()
        if mp is None:
            return None
        import cv2  # noqa: PLC0415 - only needed on this path

        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        if mirror:
            rgb = np.ascontiguousarray(np.fliplr(rgb))

        timestamp_ms = int(time.monotonic() * 1000)
        if timestamp_ms <= self._last_timestamp_ms:  # VIDEO mode needs monotonic time
            timestamp_ms = self._last_timestamp_ms + 1
        self._last_timestamp_ms = timestamp_ms

        try:
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
            # VIDEO running mode requires monotonically increasing timestamps.
            result = self._landmarker.detect_for_video(mp_image, timestamp_ms)
        except Exception as exc:  # noqa: BLE001 - never crash the pipeline
            log.error("Hand tracking failed on frame: %s", exc)
            return None

        if not result.hand_landmarks:
            return None

        # Single-hand control: pick the highest-scoring detection.
        best_index, best_score = 0, -1.0
        for i, categories in enumerate(result.handedness or []):
            if categories and categories[0].score > best_score:
                best_score = categories[0].score
                best_index = i

        hand = result.hand_landmarks[best_index]
        landmarks = tuple((float(lm.x), float(lm.y), float(lm.z)) for lm in hand)
        if len(landmarks) != 21:
            log.warning("Unexpected landmark count: %d", len(landmarks))
            return None

        label, score = "Right", 0.0
        categories = (result.handedness or [[]])[best_index]
        if categories:
            label = str(categories[0].category_name or "Right")
            score = float(categories[0].score)
        if best_score >= 0:
            score = float(best_score)

        return HandObservation(
            landmarks=landmarks,
            handedness=label,
            score=score,
            timestamp=time.perf_counter(),
        )

    def close(self) -> None:
        if self._landmarker is not None:
            try:
                self._landmarker.close()
            except Exception:  # noqa: BLE001
                pass
            self._landmarker = None
