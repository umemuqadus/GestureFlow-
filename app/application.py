"""Application: wires services, safety, hotkeys and the engine together.

This is the composition root.  UI pages talk to ``Application``; they never
construct database connections, the camera, or the mouse directly.
"""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QObject, Signal

from app import constants as C
from app.config import AppConfig
from controller.engine import ControllerEngine
from controller.mouse_controller import MouseController
from controller.safety_manager import SafetyManager
from database.database_manager import DatabaseManager, DatabaseError
from gestures.gesture_config import GestureRule, default_rules, validate_mappings
from services.calibration_service import CalibrationService
from services.profile_service import ProfileService
from services.settings_service import SettingsService
from services.statistics_service import StatisticsService
from utils.hotkeys import GlobalHotkeyFilter
from utils.logger import get_logger, setup_logging

log = get_logger(__name__)


class Application(QObject):
    """Owns the whole running application (excluding widgets)."""

    status_changed = Signal(str)
    error = Signal(str)
    controller_started = Signal()
    controller_stopped = Signal()
    paused_changed = Signal(bool)
    metrics_updated = Signal(object)
    frame_updated = Signal(object)
    gesture_changed = Signal(str)
    state_changed = Signal(str)
    screenshot_taken = Signal(str)  # absolute path of a just-saved screenshot
    level_changed = Signal(str, int, bool)  # (volume|brightness, 0-100, muted)

    def __init__(self) -> None:
        super().__init__()
        setup_logging()
        self.db: DatabaseManager | None = None
        self.db_error: str | None = None
        try:
            self.db = DatabaseManager()
        except DatabaseError as exc:
            # The app must still open so non-database pages remain usable.
            self.db_error = str(exc)
            log.error("Database unavailable: %s", exc)

        self.profiles = ProfileService(self.db) if self.db else None
        self.settings = SettingsService(self.db, self.profiles) if self.db else None
        self.statistics = StatisticsService(self.db) if self.db else None
        self.calibration = CalibrationService(self.db, self.settings) if self.db else None

        self.config: AppConfig = self.settings.config if self.settings else AppConfig()
        self.rules: dict[str, GestureRule] = default_rules(self.config.gestures)

        self.mouse = MouseController(failsafe=self.config.safety.pyautogui_failsafe)
        self.safety = SafetyManager(self.mouse, self.config.safety)
        self.engine: ControllerEngine | None = None
        self.hotkeys: GlobalHotkeyFilter | None = None

        if self.settings is not None:
            self.settings.settings_changed.connect(self._on_settings_changed)
        self.safety.paused_changed.connect(self.paused_changed.emit)
        self.safety.emergency_stopped.connect(self._on_emergency)

    # -- hotkeys -------------------------------------------------------------
    def install_hotkeys(self, qt_app) -> dict[str, bool]:
        """Register global hotkeys on the Qt app's native event filter."""
        if self.hotkeys is None:
            self.hotkeys = GlobalHotkeyFilter()
            qt_app.installNativeEventFilter(self.hotkeys)
            self.hotkeys.triggered.connect(self._on_hotkey)
        specs = [
            self.config.safety.start_stop_hotkey,
            self.config.safety.pause_hotkey,
            self.config.safety.emergency_stop_hotkey,
            self.config.safety.calibration_hotkey,
            self.config.safety.quit_hotkey,
        ]
        results = self.hotkeys.register_many(specs)
        for spec, ok in results.items():
            if not ok:
                log.warning("Global hotkey unavailable (already in use?): %s", spec)
        return results

    def _on_hotkey(self, spec: str) -> None:
        cfg = self.config.safety
        if spec == cfg.start_stop_hotkey:
            self.toggle_controller()
        elif spec == cfg.pause_hotkey:
            self.toggle_pause()
        elif spec == cfg.emergency_stop_hotkey:
            self.emergency_stop("hotkey")
        elif spec == cfg.quit_hotkey:
            self.request_quit()
        elif spec == cfg.calibration_hotkey:
            self.status_changed.emit("Open the Calibration page to recalibrate.")

    # -- controller lifecycle ------------------------------------------------
    @property
    def is_running(self) -> bool:
        return self.engine is not None and self.engine.isRunning()

    def start_controller(self) -> bool:
        if self.is_running:
            return True
        if self.engine is not None:
            self.engine.deleteLater()
            self.engine = None
        self.safety.clear_emergency()
        self.safety.cfg = self.config.safety

        engine = ControllerEngine(self.config, self.mouse, self.safety, self.rules)
        engine.frame_ready.connect(self.frame_updated.emit)
        engine.metrics_ready.connect(self.metrics_updated.emit)
        engine.status_changed.connect(self.status_changed.emit)
        engine.error_occurred.connect(self.error.emit)
        engine.gesture_changed.connect(self.gesture_changed.emit)
        engine.state_changed.connect(self.state_changed.emit)
        engine.paused_changed.connect(self.paused_changed.emit)
        engine.session_ended.connect(self._on_session_ended)
        engine.screenshot_taken.connect(self.screenshot_taken.emit)
        engine.level_changed.connect(self.level_changed.emit)
        self.engine = engine
        engine.start()
        log.info("Controller started")
        self.controller_started.emit()
        return True

    def stop_controller(self) -> None:
        engine = self.engine
        if engine is None or not engine.isRunning():
            self.safety.shutdown()
            self.controller_stopped.emit()
            return
        engine.request_stop()
        engine.wait(5000)
        if engine.isRunning():
            log.warning("Engine did not stop within timeout; terminating")
            engine.terminate()
            engine.wait(1000)
        self.safety.shutdown()
        self.engine = None
        engine.deleteLater()
        log.info("Controller stopped")
        self.controller_stopped.emit()

    def toggle_controller(self) -> None:
        if self.is_running:
            self.stop_controller()
        else:
            self.start_controller()

    def toggle_pause(self) -> None:
        if not self.is_running:
            self.status_changed.emit("Start the controller before pausing.")
            return
        self.safety.toggle_pause()

    def emergency_stop(self, reason: str = "user") -> None:
        """Immediate halt: releases buttons and stops the engine."""
        self.safety.emergency_stop(reason)
        if self.is_running:
            self.stop_controller()
        self.status_changed.emit("Emergency stop engaged. Press Resume to clear.")

    def _on_emergency(self) -> None:
        self.status_changed.emit("EMERGENCY STOP")

    def shutdown(self) -> None:
        """Safe teardown for application close."""
        self.stop_controller()
        self.safety.shutdown()
        if self.hotkeys is not None:
            self.hotkeys.unregister_all()
        if self.db is not None:
            self.db.close()

    def request_quit(self) -> None:
        self.status_changed.emit("Quit requested")

    # -- settings ------------------------------------------------------------
    def _on_settings_changed(self, config: AppConfig) -> None:
        self.config = config
        self.safety.cfg = config.safety
        self.rules = default_rules(config.gestures)
        if self.engine is not None and self.engine.isRunning():
            self.engine.apply_config(config)

    # -- history -------------------------------------------------------------
    def _on_session_ended(self, started: datetime, snapshot) -> None:
        if self.statistics is None or self.profiles is None:
            return
        self.statistics.record_session(self.profiles.active.name, started, snapshot)

    def validate_rules(self) -> list[str]:
        return validate_mappings(self.rules)

    @property
    def profile_name(self) -> str:
        return self.profiles.active.name if self.profiles else "Default"
