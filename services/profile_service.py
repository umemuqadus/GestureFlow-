"""Profile management service."""

from __future__ import annotations

from database.database_manager import DatabaseManager
from database.models import Profile
from database.repositories import ProfileRepository
from utils.logger import get_logger

log = get_logger(__name__)


class ProfileService:
    def __init__(self, db: DatabaseManager) -> None:
        self._repo = ProfileRepository(db)
        self._active: Profile = self._repo.ensure_default()

    @property
    def active(self) -> Profile:
        return self._active

    def list_profiles(self) -> list[Profile]:
        return self._repo.list_all()

    def switch(self, name: str) -> Profile:
        profile = self._repo.get_by_name(name)
        if profile is None:
            raise ValueError(f"No profile named '{name}'.")
        self._repo.touch(name)
        self._active = profile
        log.info("Switched to profile %r", name)
        return profile

    def create(self, name: str) -> Profile:
        profile = self._repo.create(name)
        self._repo.touch(name)
        log.info("Created profile %r", name)
        return profile

    def delete(self, name: str) -> None:
        if name == "Default":
            raise ValueError("The 'Default' profile cannot be deleted.")
        if self._active.name == name:
            self.switch("Default")
        self._repo.delete(name)
        log.info("Deleted profile %r", name)

    @property
    def active_profile_id(self) -> int:
        if self._active.id is None:
            self._active = self._repo.ensure_default()
        return int(self._active.id)
