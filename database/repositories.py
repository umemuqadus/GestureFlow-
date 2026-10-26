"""Repositories: typed access to each table.

Every statement uses bound parameters.  Repositories never touch the camera,
never log personal data, and never perform network I/O.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from app.config import AppConfig
from database.database_manager import DatabaseManager
from database.models import Profile, SessionSummary


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class ProfileRepository:
    def __init__(self, db: DatabaseManager) -> None:
        self._db = db

    def list_all(self) -> list[Profile]:
        rows = self._db.query(
            "SELECT id, name, created_at, last_used_at FROM profiles ORDER BY name"
        )
        return [Profile(r["id"], r["name"], r["created_at"], r["last_used_at"]) for r in rows]

    def get_by_name(self, name: str) -> Profile | None:
        rows = self._db.query(
            "SELECT id, name, created_at, last_used_at FROM profiles WHERE name = ?",
            (name,),
        )
        if not rows:
            return None
        r = rows[0]
        return Profile(r["id"], r["name"], r["created_at"], r["last_used_at"])

    def create(self, name: str) -> Profile:
        name = name.strip()
        if not name:
            raise ValueError("Profile name cannot be empty.")
        if len(name) > 48:
            raise ValueError("Profile name must be 48 characters or fewer.")
        existing = self.get_by_name(name)
        if existing:
            raise ValueError(f"A profile named '{name}' already exists.")
        cur = self._db.execute(
            "INSERT INTO profiles (name, created_at, last_used_at) VALUES (?, ?, ?)",
            (name, _now(), _now()),
        )
        return Profile(int(cur.lastrowid), name, _now(), _now())

    def touch(self, name: str) -> None:
        self._db.execute(
            "UPDATE profiles SET last_used_at = ? WHERE name = ?", (_now(), name)
        )

    def delete(self, name: str) -> None:
        self._db.execute("DELETE FROM profiles WHERE name = ?", (name,))

    def ensure_default(self) -> Profile:
        profile = self.get_by_name("Default")
        if profile is None:
            profile = self.create("Default")
        return profile


class SettingsRepository:
    """Stores the JSON-serialised ``AppConfig`` per profile, plus raw key access."""

    def __init__(self, db: DatabaseManager) -> None:
        self._db = db

    CONFIG_KEY = "app_config_json"

    def save_config(self, profile_id: int, config: AppConfig) -> None:
        config.validate()
        payload = json.dumps(config.to_dict())
        self._db.execute(
            """INSERT INTO settings (profile_id, key, value, updated_at)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(profile_id, key) DO UPDATE SET value = excluded.value,
                                                          updated_at = excluded.updated_at""",
            (profile_id, self.CONFIG_KEY, payload, _now()),
        )

    def load_config(self, profile_id: int) -> AppConfig | None:
        rows = self._db.query(
            "SELECT value FROM settings WHERE profile_id = ? AND key = ?",
            (profile_id, self.CONFIG_KEY),
        )
        if not rows:
            return None
        try:
            data = json.loads(rows[0]["value"])
        except json.JSONDecodeError:
            return None
        if not isinstance(data, dict):
            return None
        return AppConfig.from_dict(data)

    def set_value(self, profile_id: int, key: str, value: str) -> None:
        self._db.execute(
            """INSERT INTO settings (profile_id, key, value, updated_at)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(profile_id, key) DO UPDATE SET value = excluded.value,
                                                          updated_at = excluded.updated_at""",
            (profile_id, key, value, _now()),
        )

    def get_value(self, profile_id: int, key: str, default: str | None = None) -> str | None:
        rows = self._db.query(
            "SELECT value FROM settings WHERE profile_id = ? AND key = ?",
            (profile_id, key),
        )
        return rows[0]["value"] if rows else default


class GestureMappingRepository:
    def __init__(self, db: DatabaseManager) -> None:
        self._db = db

    def save(self, profile_id: int, mappings: dict[str, dict]) -> None:
        """``mappings``: gesture_id -> {action, enabled, threshold, hold_ms, cooldown_ms}."""
        with self._db.transaction():
            for gesture_id, spec in mappings.items():
                self._db.connection.execute(
                    """INSERT INTO gesture_mappings
                       (profile_id, gesture_id, action, enabled, threshold, hold_ms, cooldown_ms)
                       VALUES (?, ?, ?, ?, ?, ?, ?)
                       ON CONFLICT(profile_id, gesture_id) DO UPDATE SET
                           action = excluded.action, enabled = excluded.enabled,
                           threshold = excluded.threshold, hold_ms = excluded.hold_ms,
                           cooldown_ms = excluded.cooldown_ms""",
                    (
                        profile_id,
                        gesture_id,
                        str(spec.get("action", "")),
                        1 if spec.get("enabled", True) else 0,
                        spec.get("threshold"),
                        spec.get("hold_ms"),
                        spec.get("cooldown_ms"),
                    ),
                )

    def load(self, profile_id: int) -> dict[str, dict]:
        rows = self._db.query(
            """SELECT gesture_id, action, enabled, threshold, hold_ms, cooldown_ms
               FROM gesture_mappings WHERE profile_id = ?""",
            (profile_id,),
        )
        return {
            r["gesture_id"]: {
                "action": r["action"],
                "enabled": bool(r["enabled"]),
                "threshold": r["threshold"],
                "hold_ms": r["hold_ms"],
                "cooldown_ms": r["cooldown_ms"],
            }
            for r in rows
        }


class CalibrationRepository:
    def __init__(self, db: DatabaseManager) -> None:
        self._db = db

    def save(
        self,
        profile_id: int,
        name: str,
        *,
        roi_fraction: float,
        cursor_speed: float,
        smoothing: float,
        pinch_threshold: float,
        scroll_sensitivity: float,
    ) -> int:
        cur = self._db.execute(
            """INSERT INTO calibration_profiles
               (profile_id, name, roi_fraction, cursor_speed, smoothing,
                pinch_threshold, scroll_sensitivity, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                profile_id,
                name,
                roi_fraction,
                cursor_speed,
                smoothing,
                pinch_threshold,
                scroll_sensitivity,
                _now(),
            ),
        )
        return int(cur.lastrowid)

    def list_for_profile(self, profile_id: int) -> list[dict]:
        rows = self._db.query(
            """SELECT id, name, roi_fraction, cursor_speed, smoothing,
                      pinch_threshold, scroll_sensitivity, created_at
               FROM calibration_profiles WHERE profile_id = ?
               ORDER BY created_at DESC""",
            (profile_id,),
        )
        return [dict(r) for r in rows]

    def delete(self, calibration_id: int) -> None:
        self._db.execute("DELETE FROM calibration_profiles WHERE id = ?", (calibration_id,))


class SessionRepository:
    def __init__(self, db: DatabaseManager) -> None:
        self._db = db

    def add(self, summary: SessionSummary) -> int:
        cur = self._db.execute(
            """INSERT INTO session_summaries
               (profile_name, started_at, ended_at, duration_s, clicks, right_clicks,
                double_clicks, scroll_events, drag_events, tracking_losses,
                frames_processed, avg_fps)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                summary.profile_name,
                summary.started_at,
                summary.ended_at,
                summary.duration_s,
                summary.clicks,
                summary.right_clicks,
                summary.double_clicks,
                summary.scroll_events,
                summary.drag_events,
                summary.tracking_losses,
                summary.frames_processed,
                summary.avg_fps,
            ),
        )
        return int(cur.lastrowid)

    def recent(self, limit: int = 25) -> list[SessionSummary]:
        rows = self._db.query(
            """SELECT * FROM session_summaries ORDER BY started_at DESC LIMIT ?""",
            (limit,),
        )
        return [
            SessionSummary(
                id=r["id"],
                profile_name=r["profile_name"],
                started_at=r["started_at"],
                ended_at=r["ended_at"],
                duration_s=r["duration_s"],
                clicks=r["clicks"],
                right_clicks=r["right_clicks"],
                double_clicks=r["double_clicks"],
                scroll_events=r["scroll_events"],
                drag_events=r["drag_events"],
                tracking_losses=r["tracking_losses"],
                frames_processed=r["frames_processed"],
                avg_fps=r["avg_fps"],
            )
            for r in rows
        ]

    def clear(self) -> int:
        cur = self._db.execute("DELETE FROM session_summaries")
        return cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0

    def count(self) -> int:
        rows = self._db.query("SELECT COUNT(*) AS n FROM session_summaries")
        return int(rows[0]["n"]) if rows else 0
