"""Calibration service: applies tested values to the live configuration."""

from __future__ import annotations

from app.config import AppConfig
from database.database_manager import DatabaseManager
from database.repositories import CalibrationRepository
from services.settings_service import SettingsService
from utils.logger import get_logger

log = get_logger(__name__)


class CalibrationService:
    """Stores named calibration snapshots and applies them to the live config.

    A calibration snapshot captures the five parameters that most affect the
    *feel* of the controller: tracking region, cursor speed, smoothing, pinch
    sensitivity and scroll speed.  Applying a calibration writes those values
    into the active profile's settings so the controller picks them up on the
    next frame.
    """

    def __init__(self, db: DatabaseManager, settings: SettingsService) -> None:
        self._repo = CalibrationRepository(db)
        self._settings = settings

    def save(self, name: str, profile_id: int) -> int:
        cfg = self._settings.config
        calibration_id = self._repo.save(
            profile_id,
            name.strip() or "Calibration",
            roi_fraction=cfg.cursor.roi_fraction,
            cursor_speed=cfg.cursor.speed,
            smoothing=cfg.cursor.smoothing,
            pinch_threshold=cfg.gestures.pinch_threshold,
            scroll_sensitivity=cfg.gestures.scroll_sensitivity,
        )
        log.info("Saved calibration %r (id=%s)", name, calibration_id)
        return calibration_id

    def list_for_profile(self, profile_id: int) -> list[dict]:
        return self._repo.list_for_profile(profile_id)

    def apply(self, calibration: dict) -> bool:
        ok = self._settings.update(
            cursor={
                "roi_fraction": float(calibration["roi_fraction"]),
                "speed": float(calibration["cursor_speed"]),
                "smoothing": float(calibration["smoothing"]),
            },
            gestures={"scroll_sensitivity": float(calibration["scroll_sensitivity"])},
        )
        if ok:
            log.info("Applied calibration %r", calibration.get("name"))
        return ok

    def delete(self, calibration_id: int) -> None:
        self._repo.delete(calibration_id)
