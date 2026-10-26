"""Settings service: load / validate / persist ``AppConfig`` per profile."""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal

from app.config import AppConfig
from database.database_manager import DatabaseManager, DatabaseError
from database.repositories import SettingsRepository
from services.profile_service import ProfileService
from utils.logger import get_logger

log = get_logger(__name__)


class SettingsService(QObject):
    """Owns the live ``AppConfig`` and notifies the UI when it changes."""

    settings_changed = Signal(object)  # AppConfig

    def __init__(self, db: DatabaseManager, profiles: ProfileService) -> None:
        super().__init__()
        self._repo = SettingsRepository(db)
        self._profiles = profiles
        self._config = self._load_for_active_profile()

    # -- access --------------------------------------------------------------
    @property
    def config(self) -> AppConfig:
        return self._config

    # -- persistence ---------------------------------------------------------
    def _load_for_active_profile(self) -> AppConfig:
        try:
            loaded = self._repo.load_config(self._profiles.active_profile_id)
        except DatabaseError as exc:
            log.error("Failed to load settings, using defaults: %s", exc)
            loaded = None
        if loaded is None:
            log.info("No saved settings for profile %r; using defaults.",
                     self._profiles.active.name)
            return AppConfig()
        try:
            loaded.validate()
        except ValueError as exc:
            log.warning("Saved settings were invalid (%s); using defaults.", exc)
            return AppConfig()
        return loaded

    def reload(self) -> AppConfig:
        self._config = self._load_for_active_profile()
        self.settings_changed.emit(self._config)
        return self._config

    def save(self, config: AppConfig | None = None) -> bool:
        """Validate and persist. Returns True on success, False on failure."""
        candidate = config or self._config
        try:
            candidate.validate()
        except ValueError as exc:
            log.error("Refusing to save invalid settings: %s", exc)
            return False
        try:
            self._repo.save_config(self._profiles.active_profile_id, candidate)
        except DatabaseError as exc:
            log.error("Could not persist settings: %s", exc)
            return False
        self._config = candidate
        self.settings_changed.emit(self._config)
        log.info("Settings saved for profile %r", self._profiles.active.name)
        return True

    def update(self, **sections) -> bool:
        """Update fields by section name, e.g. ``update(cursor={"speed": 1.4})``."""
        new_config = AppConfig.from_dict(self._config.to_dict())
        for section_name, values in sections.items():
            section = getattr(new_config, section_name, None)
            if section is None:
                log.error("Unknown settings section: %s", section_name)
                return False
            for key, value in values.items():
                if not hasattr(section, key):
                    log.error("Unknown setting %s.%s", section_name, key)
                    return False
                setattr(section, key, value)
        return self.save(new_config)

    def reset_to_defaults(self) -> bool:
        log.info("Resetting settings to defaults")
        return self.save(AppConfig())
