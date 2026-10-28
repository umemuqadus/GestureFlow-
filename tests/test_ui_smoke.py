"""Offscreen UI smoke test: every page constructs without a display or camera.

These tests build a real :class:`Application` (the composition root) with the
SQLite database redirected to a temp directory, then construct each page.
They verify wiring and construction only; they do not start the camera or the
engine, and they assert no fabricated rendering metrics.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

import database.database_manager as dbm  # noqa: E402
from app.application import Application  # noqa: E402
from ui.about_page import AboutPage  # noqa: E402
from ui.calibration_page import CalibrationPage  # noqa: E402
from ui.controller_page import ControllerPage  # noqa: E402
from ui.dashboard_page import DashboardPage  # noqa: E402
from ui.gestures_page import GesturesPage  # noqa: E402
from ui.history_page import HistoryPage  # noqa: E402
from ui.settings_page import SettingsPage  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture()
def application(qapp, tmp_path, monkeypatch):
    """A real Application whose database lives in a temp directory."""
    monkeypatch.setattr(dbm, "database_path", lambda: tmp_path / "smoke.db")
    app = Application()
    yield app
    app.shutdown()


def test_dashboard_page_constructs(application):
    page = DashboardPage(application)
    page.deleteLater()


def test_gestures_page_constructs(application):
    page = GesturesPage(application)
    page.deleteLater()


def test_settings_page_constructs(application):
    page = SettingsPage(application)
    page.deleteLater()


def test_controller_page_constructs(application):
    page = ControllerPage(application)
    page.deleteLater()


def test_calibration_page_constructs(application):
    page = CalibrationPage(application)
    page.deleteLater()


def test_history_page_constructs(application):
    page = HistoryPage(application)
    page.deleteLater()


def test_about_page_constructs(application):
    page = AboutPage(application)
    page.deleteLater()


def test_main_window_constructs(application):
    """The full window (sidebar + pages + screenshot overlay) must build.

    Regression guard: ``MainWindow.__init__`` calls ``apply_theme()`` before
    the screenshot overlay existed, crashing on startup with an
    AttributeError.  Building the real window offscreen catches that ordering
    class of bug, which per-page smoke tests miss.
    """
    from ui.main_window import MainWindow

    window = MainWindow(application)
    assert hasattr(window, "_shot_overlay")
    assert hasattr(window, "_level_overlay")
    # Theme switching must also reach the overlays without error.
    window.apply_theme("dark")
    window.apply_theme("light")
    # A level coming from the engine must reach the indicator overlay.
    application.level_changed.emit("volume", 42, False)
    assert window._level_overlay.isVisible()
    window._level_overlay.hide()
    window._shot_overlay.deleteLater()
    window._level_overlay.deleteLater()
    window.deleteLater()


def test_level_overlay_shows_and_rethemes(qapp):
    """The volume/brightness indicator draws real, clamped levels."""
    from ui.level_overlay import LevelOverlay
    from ui.theme import theme_by_name

    overlay = LevelOverlay(theme_by_name("light"))
    overlay.show_level("volume", 42, False)
    assert overlay.isVisible()
    assert overlay._bar._value == 42

    overlay.show_level("brightness", 70, False)
    assert overlay._bar._value == 70

    # Out-of-range levels are clamped rather than drawn past the track.
    overlay.show_level("volume", 250, True)
    assert overlay._bar._value == 100

    # An unknown kind falls back to the volume glyph instead of crashing.
    overlay.show_level("nonsense", -5)
    assert overlay._kind == "volume"
    assert overlay._bar._value == 0

    overlay.apply_theme(theme_by_name("dark"))
    overlay.apply_theme(theme_by_name("light"))
    overlay._timer.stop()
    overlay.hide()
    overlay.deleteLater()
