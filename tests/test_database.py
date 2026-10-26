"""Tests for SQLite persistence (profiles, settings, mappings, sessions)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.config import AppConfig
from database.database_manager import DatabaseManager
from database.models import SessionSummary
from database.repositories import (
    CalibrationRepository,
    GestureMappingRepository,
    ProfileRepository,
    SessionRepository,
    SettingsRepository,
)


@pytest.fixture
def db(tmp_path):
    manager = DatabaseManager(path=tmp_path / "test.db")
    yield manager
    manager.close()


def test_database_creates_schema(db):
    tables = {r["name"] for r in db.query(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"profiles", "settings", "gesture_mappings",
            "calibration_profiles", "session_summaries"} <= tables


def test_profile_create_and_list(db):
    repo = ProfileRepository(db)
    created = repo.create("Work")
    assert created.id is not None
    names = [p.name for p in repo.list_all()]
    assert "Work" in names


def test_duplicate_profile_rejected(db):
    repo = ProfileRepository(db)
    repo.create("Work")
    with pytest.raises(ValueError):
        repo.create("Work")


def test_empty_profile_name_rejected(db):
    repo = ProfileRepository(db)
    with pytest.raises(ValueError):
        repo.create("   ")


def test_ensure_default_is_idempotent(db):
    repo = ProfileRepository(db)
    first = repo.ensure_default()
    second = repo.ensure_default()
    assert first.id == second.id


def test_config_save_and_load(db):
    profiles = ProfileRepository(db)
    profile = profiles.ensure_default()
    settings = SettingsRepository(db)
    cfg = AppConfig()
    cfg.cursor.speed = 2.0
    settings.save_config(profile.id, cfg)
    loaded = settings.load_config(profile.id)
    assert loaded is not None
    assert loaded.cursor.speed == pytest.approx(2.0)


def test_load_config_returns_none_when_missing(db):
    profiles = ProfileRepository(db)
    profile = profiles.ensure_default()
    assert SettingsRepository(db).load_config(profile.id) is None


def test_gesture_mappings_round_trip(db):
    profiles = ProfileRepository(db)
    profile = profiles.ensure_default()
    repo = GestureMappingRepository(db)
    payload = {"pinch": {"action": "left_click", "enabled": True,
                         "threshold": 0.3, "hold_ms": 0, "cooldown_ms": 250}}
    repo.save(profile.id, payload)
    loaded = repo.load(profile.id)
    assert loaded["pinch"]["action"] == "left_click"
    assert loaded["pinch"]["threshold"] == pytest.approx(0.3)


def test_calibration_round_trip(db):
    profiles = ProfileRepository(db)
    profile = profiles.ensure_default()
    repo = CalibrationRepository(db)
    repo.save(profile.id, "My setup", roi_fraction=0.5, cursor_speed=1.4,
              smoothing=0.6, pinch_threshold=0.28, scroll_sensitivity=2.0)
    items = repo.list_for_profile(profile.id)
    assert len(items) == 1
    assert items[0]["name"] == "My setup"
    assert items[0]["cursor_speed"] == pytest.approx(1.4)


def test_session_add_and_recent(db):
    repo = SessionRepository(db)
    summary = SessionSummary(
        id=None, profile_name="Default",
        started_at=datetime.now(timezone.utc).isoformat(),
        ended_at=datetime.now(timezone.utc).isoformat(),
        duration_s=61.0, clicks=12, right_clicks=3, double_clicks=1,
        scroll_events=7, drag_events=2, tracking_losses=1,
        frames_processed=1500, avg_fps=28.5,
    )
    row_id = repo.add(summary)
    assert row_id > 0
    recent = repo.recent()
    assert len(recent) == 1
    assert recent[0].clicks == 12
    assert repo.count() == 1


def test_clear_sessions(db):
    repo = SessionRepository(db)
    summary = SessionSummary(
        id=None, profile_name="Default", started_at="t0", ended_at="t1",
        duration_s=1.0, clicks=0, right_clicks=0, double_clicks=0,
        scroll_events=0, drag_events=0, tracking_losses=0,
        frames_processed=10, avg_fps=30.0)
    repo.add(summary)
    assert repo.clear() == 1
    assert repo.count() == 0


def test_parameterised_query_protects_against_injection(db):
    repo = ProfileRepository(db)
    repo.create("alice'; DROP TABLE profiles;--")
    # Table still exists and the literal name was stored.
    names = [p.name for p in repo.list_all()]
    assert "alice'; DROP TABLE profiles;--" in names
