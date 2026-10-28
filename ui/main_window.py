"""Main window: sidebar navigation and page wiring."""

from __future__ import annotations

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app import APP_NAME, __version__
from app.application import Application
from ui.about_page import AboutPage
from ui.calibration_page import CalibrationPage
from ui.controller_page import ControllerPage
from ui.dashboard_page import DashboardPage
from ui.gestures_page import GesturesPage
from ui.history_page import HistoryPage
from ui.level_overlay import LevelOverlay
from ui.settings_page import SettingsPage
from ui.screenshot_overlay import ScreenshotOverlay
from ui.theme import build_qss, theme_by_name
from utils.logger import get_logger

log = get_logger(__name__)

NAV_ITEMS = [
    ("dashboard", "Dashboard"),
    ("controller", "Live Controller"),
    ("calibration", "Calibration"),
    ("gestures", "Gesture Mapping"),
    ("history", "Session History"),
    ("settings", "Settings"),
    ("about", "About"),
]


class MainWindow(QMainWindow):
    def __init__(self, app: Application) -> None:
        super().__init__()
        self.app = app
        self.setWindowTitle(f"{APP_NAME} {__version__}")
        self.resize(1240, 800)

        self._pages: dict[str, QWidget] = {}
        self._nav_buttons: dict[str, QPushButton] = {}

        root = QFrame()
        root.setObjectName("Root")
        self.setCentralWidget(root)
        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        layout.addWidget(self._build_sidebar())

        self.stack = QStackedWidget()
        self._build_pages()
        layout.addWidget(self.stack, stretch=1)

        # Screenshot feedback overlay (shows a fading thumbnail after a capture).
        # Created before apply_theme() so the first theme pass styles it too.
        self._shot_overlay = ScreenshotOverlay(theme_by_name(self.app.config.ui.theme))
        self.app.screenshot_taken.connect(self._shot_overlay.show_image)

        # Volume/brightness feedback overlay (bottom-centre level indicator).
        # Created before apply_theme() so the first theme pass styles it too.
        self._level_overlay = LevelOverlay(theme_by_name(self.app.config.ui.theme))
        self.app.level_changed.connect(self._level_overlay.show_level)

        self.apply_theme(self.app.config.ui.theme)
        QApplication.instance().installEventFilter(self)
        self._focus_was_active = True

        # Emergency-stop menu action (always reachable from the window chrome).
        stop_action = QAction("Emergency Stop", self)
        stop_action.setShortcut("Esc")
        stop_action.triggered.connect(lambda: self.app.emergency_stop("Esc key"))
        self.addAction(stop_action)
        self._stop_action = stop_action

    # -- sidebar -----------------------------------------------------------------
    def _build_sidebar(self) -> QWidget:
        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(220)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(14, 18, 14, 18)
        layout.setSpacing(4)

        title = QLabel(APP_NAME)
        title.setObjectName("SidebarTitle")
        subtitle = QLabel("AI mouse controller")
        subtitle.setObjectName("SidebarSubtitle")
        layout.addWidget(title)
        layout.addWidget(subtitle)

        self._button_group = QButtonGroup(self)
        self._button_group.setExclusive(True)
        for key, label in NAV_ITEMS:
            button = QPushButton(label)
            button.setObjectName("NavButton")
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda _=False, k=key: self.show_page(k))
            self._button_group.addButton(button)
            self._nav_buttons[key] = button
            layout.addWidget(button)
        layout.addStretch(1)

        footer = QLabel(f"v{__version__} · runs fully offline")
        footer.setObjectName("CardSubtitle")
        layout.addWidget(footer)
        return sidebar

    # -- pages --------------------------------------------------------------------
    def _build_pages(self) -> None:
        pages = {
            "dashboard": DashboardPage(self.app),
            "controller": ControllerPage(self.app),
            "calibration": CalibrationPage(self.app),
            "gestures": GesturesPage(self.app),
            "history": HistoryPage(self.app),
            "settings": SettingsPage(self.app),
            "about": AboutPage(self.app),
        }
        for key, page in pages.items():
            self._pages[key] = page
            self.stack.addWidget(page)
        self.show_page("dashboard")

    def show_page(self, key: str) -> None:
        page = self._pages.get(key)
        if page is None:
            return
        self.stack.setCurrentWidget(page)
        button = self._nav_buttons.get(key)
        if button is not None:
            button.setChecked(True)
        refresh = getattr(page, "refresh", None)
        if callable(refresh):
            refresh()

    # -- theme ---------------------------------------------------------------------
    def apply_theme(self, theme_name: str) -> None:
        theme = theme_by_name(theme_name)
        QApplication.instance().setStyleSheet(build_qss(theme))
        self._shot_overlay.apply_theme(theme)
        self._level_overlay.apply_theme(theme)

    # -- focus-loss pause ------------------------------------------------------------
    def eventFilter(self, obj, event) -> bool:  # noqa: N802 - Qt API name
        if event.type() == QEvent.Type.ApplicationDeactivate:
            self.app.safety.on_focus_changed(False)
        elif event.type() == QEvent.Type.ApplicationActivate:
            self._focus_was_active = True
        return super().eventFilter(obj, event)

    # -- shutdown --------------------------------------------------------------------
    def closeEvent(self, event) -> None:  # noqa: N802 - Qt API name
        """Safe shutdown: stop the engine, release buttons, close the database."""
        try:
            self.app.shutdown()
        except Exception as exc:  # noqa: BLE001 - never block close on error
            log.error("Shutdown error: %s", exc)
        event.accept()
