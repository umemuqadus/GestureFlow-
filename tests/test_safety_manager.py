"""Tests for the safety manager (pause, emergency stop, release guarantees)."""

from __future__ import annotations

import pytest

from app.config import SafetyConfig
from controller.mouse_controller import LEFT, MouseController
from controller.safety_manager import SafetyManager
from tests.conftest import FakeMouseBackend


@pytest.fixture
def backend():
    return FakeMouseBackend()


@pytest.fixture
def mouse(backend):
    return MouseController(failsafe=True, backend=backend)


@pytest.fixture
def safety(mouse):
    return SafetyManager(mouse, SafetyConfig())


def test_may_act_true_by_default(safety):
    assert safety.may_act() is True


def test_pause_releases_held_buttons(safety, mouse, backend):
    mouse.press_down(LEFT)
    assert mouse.is_held(LEFT)
    safety.pause("test")
    assert safety.paused is True
    assert mouse.is_held(LEFT) is False
    assert backend.of_type("mouseUp")


def test_paused_blocks_actions(safety):
    safety.pause()
    assert safety.may_act() is False


def test_resume_restores_actions(safety):
    safety.pause()
    safety.resume()
    assert safety.paused is False
    assert safety.may_act() is True


def test_toggle_pause(safety):
    safety.toggle_pause()
    assert safety.paused is True
    safety.toggle_pause()
    assert safety.paused is False


def test_emergency_stop_releases_and_blocks(safety, mouse, backend):
    mouse.press_down(LEFT)
    safety.emergency_stop("unit test")
    assert safety.emergency is True
    assert safety.paused is True
    assert safety.may_act() is False
    assert mouse.is_held(LEFT) is False
    assert backend.of_type("mouseUp")


def test_resume_ignored_while_emergency_active(safety):
    safety.emergency_stop()
    safety.resume()
    assert safety.paused is True  # cannot resume without clearing the emergency


def test_clear_emergency_allows_resume(safety):
    safety.emergency_stop()
    safety.clear_emergency()
    assert safety.emergency is False
    assert safety.may_act() is True


def test_focus_loss_pauses_when_enabled(mouse):
    safety = SafetyManager(mouse, SafetyConfig(pause_on_focus_loss=True))
    safety.on_focus_changed(False)
    assert safety.paused is True


def test_focus_loss_ignored_when_disabled(mouse):
    safety = SafetyManager(mouse, SafetyConfig(pause_on_focus_loss=False))
    safety.on_focus_changed(False)
    assert safety.paused is False


def test_shutdown_releases_buttons_and_is_idempotent(safety, mouse, backend):
    mouse.press_down(LEFT)
    safety.shutdown()
    safety.shutdown()  # calling twice must not raise
    assert mouse.is_held(LEFT) is False


def test_signal_emitted_on_pause(safety):
    received: list[bool] = []
    safety.paused_changed.connect(received.append)
    safety.pause("x")
    assert received == [True]
