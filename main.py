"""GestureFlow AI entry point.

Run with:  python main.py
"""

from __future__ import annotations

import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMessageBox

from app import APP_NAME, __version__
from app.application import Application
from ui.main_window import MainWindow
from utils.logger import get_logger, setup_logging

log = get_logger(__name__)


def main() -> int:
    setup_logging()
    log.info("Starting %s %s", APP_NAME, __version__)

    # High-DPI scaling so the cursor mapping and UI stay correct on scaled displays.
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    qapp = QApplication(sys.argv)
    qapp.setApplicationName(APP_NAME)
    qapp.setApplicationVersion(__version__)
    qapp.setOrganizationName("GestureFlow")

    app = Application()

    if app.db_error:
        # Non-fatal: the app opens so non-database pages remain usable.
        QMessageBox.warning(
            None,
            "Database unavailable",
            "Settings and history could not be loaded:\n\n"
            f"{app.db_error}\n\n"
            "The controller will still work with default settings.",
        )

    window = MainWindow(app)
    window.show()

    hotkey_results = app.install_hotkeys(qapp)
    failed = [spec for spec, ok in hotkey_results.items() if not ok]
    if failed:
        log.warning("Some global hotkeys could not be registered: %s", ", ".join(failed))

    try:
        exit_code = qapp.exec()
    finally:
        # Always release held buttons and close the database, even on error.
        app.shutdown()
    log.info("Exiting with code %s", exit_code)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
