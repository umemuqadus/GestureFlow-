"""Logging setup.

Logs are written to the per-user application-data directory (see
``utils.platform_utils.app_data_dir``).  Log records must never contain webcam
frames, screenshots or personal data; modules log only diagnostic text.
"""

from __future__ import annotations

import logging
import logging.handlers
from pathlib import Path

from utils.platform_utils import app_data_dir

_LOG_FORMAT = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"
_configured = False


def log_dir() -> Path:
    """Directory holding the rotating log file."""
    path = app_data_dir() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def setup_logging(level: int = logging.INFO) -> Path:
    """Configure root logging once; returns the log file path."""
    global _configured
    logfile = log_dir() / "gestureflow.log"
    if _configured:
        return logfile

    root = logging.getLogger()
    root.setLevel(level)

    stream = logging.StreamHandler()
    stream.setFormatter(logging.Formatter(_LOG_FORMAT, datefmt="%H:%M:%S"))
    root.addHandler(stream)

    # 3 x 512 KiB rotating file, no personal data by design.
    file_handler = logging.handlers.RotatingFileHandler(
        logfile, maxBytes=512 * 1024, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(logging.Formatter(_LOG_FORMAT))
    root.addHandler(file_handler)

    # Keep third-party noise down.
    logging.getLogger("PIL").setLevel(logging.WARNING)

    # Silence OpenCV's own C++ logger.  Camera enumeration probes absent
    # indices, which makes OpenCV emit "index out of range" / backend noise to
    # stderr; none of it is actionable for the user.  Import lazily and never
    # let logging setup break the app if cv2 is unavailable.
    try:
        import cv2  # noqa: PLC0415

        cv2.utils.logging.setLogLevel(cv2.utils.logging.LOG_LEVEL_SILENT)
    except Exception:  # noqa: BLE001 - optional dependency
        pass

    _configured = True
    logging.getLogger(__name__).info("Logging initialised at %s", logfile)
    return logfile


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
