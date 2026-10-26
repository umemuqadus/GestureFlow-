"""SQLite connection management and schema initialisation.

The database file lives in the per-user application-data directory.  All queries
use parameterised placeholders; no string interpolation of user data ever
reaches SQL.
"""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

from utils.logger import get_logger
from utils.platform_utils import database_path

log = get_logger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS profiles (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    name         TEXT NOT NULL UNIQUE,
    created_at   TEXT NOT NULL,
    last_used_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS settings (
    profile_id  INTEGER NOT NULL,
    key         TEXT NOT NULL,
    value       TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    PRIMARY KEY (profile_id, key),
    FOREIGN KEY (profile_id) REFERENCES profiles(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS gesture_mappings (
    profile_id        INTEGER NOT NULL,
    gesture_id        TEXT NOT NULL,
    action            TEXT NOT NULL,
    enabled           INTEGER NOT NULL DEFAULT 1,
    threshold         REAL,
    hold_ms           INTEGER,
    cooldown_ms       INTEGER,
    PRIMARY KEY (profile_id, gesture_id),
    FOREIGN KEY (profile_id) REFERENCES profiles(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS calibration_profiles (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_id     INTEGER NOT NULL,
    name           TEXT NOT NULL,
    roi_fraction   REAL NOT NULL,
    cursor_speed   REAL NOT NULL,
    smoothing      REAL NOT NULL,
    pinch_threshold REAL NOT NULL,
    scroll_sensitivity REAL NOT NULL,
    created_at     TEXT NOT NULL,
    FOREIGN KEY (profile_id) REFERENCES profiles(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS session_summaries (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_name    TEXT NOT NULL,
    started_at      TEXT NOT NULL,
    ended_at        TEXT NOT NULL,
    duration_s      REAL NOT NULL,
    clicks          INTEGER NOT NULL DEFAULT 0,
    right_clicks    INTEGER NOT NULL DEFAULT 0,
    double_clicks   INTEGER NOT NULL DEFAULT 0,
    scroll_events   INTEGER NOT NULL DEFAULT 0,
    drag_events     INTEGER NOT NULL DEFAULT 0,
    tracking_losses INTEGER NOT NULL DEFAULT 0,
    frames_processed INTEGER NOT NULL DEFAULT 0,
    avg_fps         REAL NOT NULL DEFAULT 0
);
"""


class DatabaseError(RuntimeError):
    """Raised when the database cannot be opened or initialised."""


class DatabaseManager:
    """Thread-safe SQLite wrapper (one connection guarded by a lock)."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = Path(path) if path else database_path()
        self._lock = threading.RLock()
        self._conn: sqlite3.Connection | None = None
        self.connect()

    # -- lifecycle -----------------------------------------------------------
    def connect(self) -> None:
        with self._lock:
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                self._conn = sqlite3.connect(
                    self.path, check_same_thread=False, timeout=10.0
                )
                self._conn.row_factory = sqlite3.Row
                self._conn.execute("PRAGMA foreign_keys = ON")
                self._conn.executescript(SCHEMA)
                self._conn.commit()
                log.info("Database ready at %s", self.path)
            except sqlite3.Error as exc:
                raise DatabaseError(f"Could not open the database: {exc}") from exc

    def close(self) -> None:
        with self._lock:
            if self._conn is not None:
                try:
                    self._conn.commit()
                    self._conn.close()
                except sqlite3.Error:  # pragma: no cover - best effort
                    pass
                self._conn = None

    # -- helpers -------------------------------------------------------------
    @property
    def connection(self) -> sqlite3.Connection:
        if self._conn is None:
            raise DatabaseError("Database connection is closed.")
        return self._conn

    def execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        with self._lock:
            try:
                cur = self.connection.execute(sql, params)
                self._conn.commit()  # type: ignore[union-attr]
                return cur
            except sqlite3.Error as exc:
                self._conn.rollback()  # type: ignore[union-attr]
                raise DatabaseError(f"Query failed: {exc}") from exc

    def query(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        with self._lock:
            try:
                cur = self.connection.execute(sql, params)
                return cur.fetchall()
            except sqlite3.Error as exc:
                raise DatabaseError(f"Query failed: {exc}") from exc

    def transaction(self):
        """``with db.transaction(): ...`` commits on success, rolls back on error."""
        return _Transaction(self)


class _Transaction:
    def __init__(self, db: "DatabaseManager") -> None:
        self._db = db

    def __enter__(self) -> sqlite3.Connection:
        return self._db.connection

    def __exit__(self, exc_type, exc, tb) -> bool:
        with self._db._lock:
            if exc_type is None:
                self._db.connection.commit()
            else:
                self._db.connection.rollback()
        return False  # never swallow exceptions
