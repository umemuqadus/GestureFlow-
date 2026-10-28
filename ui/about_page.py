"""About page: version, stack, privacy statement and shortcut reference."""

from __future__ import annotations

from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from app import APP_NAME, __version__
from app.application import Application
from ui.components import Card, ScrollContainer

_STACK = (
    "Python 3.12  ·  OpenCV  ·  MediaPipe (Tasks API)  ·  NumPy  ·  "
    "PyAutoGUI  ·  PySide6  ·  SQLite  ·  Pytest"
)

_PRIVACY = (
    "GestureFlow AI runs entirely on this computer.\n\n"
    "• The webcam feed is processed locally and never uploaded, streamed or shared.\n"
    "• There is no telemetry, analytics, crash reporting, advertising, cloud API or "
    "automatic update check.\n"
    "• No network connections are opened by the application after setup.\n"
    "• Only settings, gesture mappings, calibration values and session statistics "
    "(click/scroll counts, timings, FPS) are stored, in a local SQLite database and "
    "log files under your application-data folder.\n"
    "• No webcam images or video recordings are saved.\n"
    "• No keystrokes, clipboard contents, browser history, documents or other "
    "application data are collected.\n"
    "• To delete everything, remove the application-data folder "
    "(%APPDATA%\\GestureFlowAI) or use Clear history / Reset settings in the app."
)

_SHORTCUTS = (
    "Ctrl + Alt + M — Start or stop the controller\n"
    "Ctrl + Alt + P — Pause or resume control\n"
    "Esc — Emergency stop (releases held buttons and halts automation)\n"
    "Ctrl + Alt + C — Open the calibration flow\n"
    "Ctrl + Alt + Q — Quit after safe cleanup\n\n"
    "These are registered system-wide on Windows, so they work even when the "
    "window is not focused. If a combination is already used by another program, "
    "the in-window buttons remain available."
)

_DESCRIPTION = (
    "GestureFlow AI is a desktop application that lets you control the Windows "
    "mouse with hand gestures through your webcam. It uses MediaPipe's on-device "
    "hand-landmark model plus a geometric gesture classifier and a state machine "
    "to move the cursor, click, drag, scroll and pause — with safety features that "
    "release held buttons whenever tracking is lost or control is stopped."
)


class AboutPage(QWidget):
    def __init__(self, app: Application, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.app = app
        container = ScrollContainer(self)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(container)
        body = container.content_layout()

        title = QLabel("About")
        title.setObjectName("PageTitle")
        body.addWidget(title)

        version = Card(f"{APP_NAME} {__version__}")
        version.body().addWidget(self._label(_DESCRIPTION))
        version.body().addWidget(self._label(f"Technology stack: {_STACK}"))
        body.addWidget(version)

        privacy = Card("Privacy and security")
        privacy.body().addWidget(self._label(_PRIVACY))
        body.addWidget(privacy)

        shortcuts = Card("Keyboard shortcuts")
        shortcuts.body().addWidget(self._label(_SHORTCUTS))
        body.addWidget(shortcuts)

        storage = Card("Where your data lives")
        from utils.platform_utils import app_data_dir, database_path

        storage.body().addWidget(self._label(
            f"Application data folder: {app_data_dir()}\n"
            f"Database: {database_path()}\n"
            "Delete that folder to remove all stored settings and history."
        ))
        body.addWidget(storage)
        body.addStretch(1)

    @staticmethod
    def _label(text: str) -> QLabel:
        label = QLabel(text)
        label.setWordWrap(True)
        label.setObjectName("CardSubtitle")
        return label
