"""Tests for the mouse controller (uses a fake backend; never moves the mouse)."""

from __future__ import annotations

import pytest

from controller.mouse_controller import LEFT, RIGHT, MouseController
from tests.conftest import FakeMouseBackend


@pytest.fixture
def backend():
    return FakeMouseBackend(width=1920, height=1080)


@pytest.fixture
def mouse(backend):
    return MouseController(failsafe=True, backend=backend)


def test_move_to_records_position(mouse, backend):
    mouse.move_to(100, 200)
    assert backend.of_type("moveTo")[-1] == ("moveTo", 100, 200)


def test_move_to_rejects_out_of_bounds(mouse, backend):
    mouse.move_to(5000, 5000)
    assert backend.of_type("moveTo") == []


def test_move_to_rejects_negative(mouse, backend):
    mouse.move_to(-10, 50)
    assert backend.of_type("moveTo") == []


def test_move_to_skips_redundant_move(mouse, backend):
    mouse.move_to(10, 10)
    mouse.move_to(10, 10)  # identical target is skipped
    assert len(backend.of_type("moveTo")) == 1


def test_press_down_tracks_held_button(mouse, backend):
    mouse.press_down(LEFT)
    assert mouse.is_held(LEFT)
    assert backend.of_type("mouseDown") == [("mouseDown", LEFT)]


def test_press_down_never_sends_second_mouse_down(mouse, backend):
    mouse.press_down(LEFT)
    mouse.press_down(LEFT)
    mouse.press_down(LEFT)
    assert len(backend.of_type("mouseDown")) == 1


def test_release_clears_held_state(mouse, backend):
    mouse.press_down(LEFT)
    mouse.release(LEFT)
    assert mouse.is_held(LEFT) is False
    assert backend.of_type("mouseUp") == [("mouseUp", LEFT)]


def test_release_without_press_is_noop(mouse, backend):
    mouse.release(LEFT)
    assert backend.of_type("mouseUp") == []


def test_release_all_releases_every_button(mouse, backend):
    mouse.press_down(LEFT)
    mouse.press_down(RIGHT)
    released = mouse.release_all()
    assert released == {LEFT, RIGHT}
    assert mouse.held_buttons == frozenset()


def test_click_and_double_click(mouse, backend):
    mouse.click(LEFT)
    mouse.double_click()
    assert ("click", LEFT) in backend.calls
    assert ("doubleClick",) in backend.calls


def test_scroll_is_clamped(mouse, backend):
    mouse.scroll_vertical(999)
    assert backend.of_type("scroll") == [("scroll", 10)]
    mouse.scroll_vertical(-999)
    assert backend.of_type("scroll")[-1] == ("scroll", -10)


def test_scroll_zero_is_noop(mouse, backend):
    mouse.scroll_vertical(0)
    assert backend.of_type("scroll") == []


def test_horizontal_scroll(mouse, backend):
    mouse.scroll_horizontal(3)
    assert backend.of_type("hscroll") == [("hscroll", 3)]


def test_invalid_button_raises(mouse):
    with pytest.raises(ValueError):
        mouse.click("sideways")
    with pytest.raises(ValueError):
        mouse.press_down("sideways")


def test_failsafe_toggle(mouse, backend):
    mouse.set_failsafe(False)
    assert backend.FAILSAFE is False
    mouse.set_failsafe(True)
    assert backend.FAILSAFE is True
