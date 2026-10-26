"""Tests for settings validation and (de)serialisation."""

from __future__ import annotations

import pytest

from app.config import AppConfig


def test_default_config_is_valid():
    AppConfig().validate()


def test_to_dict_from_dict_round_trip():
    cfg = AppConfig()
    cfg.cursor.speed = 1.75
    cfg.camera.device_index = 2
    cfg.ui.theme = "dark"
    restored = AppConfig.from_dict(cfg.to_dict())
    assert restored.cursor.speed == pytest.approx(1.75)
    assert restored.camera.device_index == 2
    assert restored.ui.theme == "dark"


def test_from_dict_ignores_unknown_keys():
    cfg = AppConfig.from_dict({"cursor": {"speed": 1.2, "bogus_key": 5},
                               "not_a_section": {"x": 1}})
    assert cfg.cursor.speed == pytest.approx(1.2)


def test_invalid_cursor_speed_rejected():
    cfg = AppConfig()
    cfg.cursor.speed = 99.0
    with pytest.raises(ValueError):
        cfg.validate()


def test_release_threshold_must_exceed_pinch():
    cfg = AppConfig()
    cfg.gestures.pinch_threshold = 0.5
    cfg.gestures.release_threshold = 0.3   # smaller than activation
    with pytest.raises(ValueError):
        cfg.validate()


def test_confidence_out_of_range_rejected():
    cfg = AppConfig()
    cfg.tracking.detection_confidence = 0.0
    with pytest.raises(ValueError):
        cfg.validate()


def test_invalid_theme_rejected():
    cfg = AppConfig()
    cfg.ui.theme = "blue"
    with pytest.raises(ValueError):
        cfg.validate()


def test_negative_cooldown_rejected():
    cfg = AppConfig()
    cfg.gestures.click_cooldown_ms = -5
    with pytest.raises(ValueError):
        cfg.validate()


def test_from_dict_coerces_types():
    cfg = AppConfig.from_dict({"camera": {"max_fps": "45", "mirror_preview": 0}})
    assert cfg.camera.max_fps == 45
    assert cfg.camera.mirror_preview is False
