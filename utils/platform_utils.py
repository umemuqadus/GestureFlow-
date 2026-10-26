"""Small platform helpers: application-data paths and screen size queries.

No network access, no telemetry, no subprocess execution.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_DIR_NAME = "GestureFlowAI"


def app_data_dir() -> Path:
    """Per-user application-data directory for the database, logs and config.

    Windows: ``%APPDATA%\\GestureFlowAI``
    Fallback (any other OS): ``~/.gestureflow_ai``
    """
    if sys.platform.startswith("win"):
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        path = Path(base) / APP_DIR_NAME
    else:  # pragma: no cover - non-Windows fallback
        path = Path.home() / f".{APP_DIR_NAME.lower()}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def database_path() -> Path:
    return app_data_dir() / "gestureflow.db"


def primary_screen_size() -> tuple[int, int]:
    """Best-effort primary screen size without importing the GUI stack.

    Order of attempts:
    1. ``ctypes`` user32 metrics on Windows (no Qt import needed).
    2. ``QApplication.screens()`` if Qt is already running.
    3. Hard 1920x1080 fallback, clearly flagged as a guess.
    """
    if sys.platform.startswith("win"):
        try:
            import ctypes

            user32 = ctypes.windll.user32  # type: ignore[attr-defined]
            user32.SetProcessDPIAware()
            width = int(user32.GetSystemMetrics(0))
            height = int(user32.GetSystemMetrics(1))
            if width > 0 and height > 0:
                return width, height
        except Exception:  # noqa: BLE001 - fall through to Qt / default
            pass
    try:  # pragma: no cover - depends on a running QApplication
        from PySide6.QtGui import QGuiApplication

        app = QGuiApplication.instance()
        if app is not None:
            screen = app.primaryScreen()
            if screen is not None:
                geo = screen.geometry()
                return int(geo.width()), int(geo.height())
    except Exception:  # noqa: BLE001
        pass
    return 1920, 1080


def is_windows() -> bool:
    return sys.platform.startswith("win")
