"""Tests for the virtual keyboard: keystroke controller + on-screen widget.

The controller is tested against a fake backend so no real keys are ever sent.
The widget is built offscreen and its critical guarantee — that it can never
take keyboard focus away from the target application — is asserted directly via
its window flags and per-button focus policy.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from controller.keyboard_controller import (  # noqa: E402
    KeyboardController,
    VALID_SPECIAL_KEYS,
)
from ui.theme import LIGHT  # noqa: E402
from ui.virtual_keyboard import VirtualKeyboard, _build_rows  # noqa: E402


class FakeBackend:
    """Records every call instead of touching the OS."""

    def __init__(self) -> None:
        self.written: list[str] = []
        self.pressed: list[str] = []

    def write(self, text: str) -> None:
        self.written.append(text)

    def press(self, key: str) -> None:
        self.pressed.append(key)


class ExplodingBackend:
    """Raises on every call, to prove the controller never propagates errors."""

    def write(self, text: str) -> None:
        raise RuntimeError("boom")

    def press(self, key: str) -> None:
        raise RuntimeError("boom")


@pytest.fixture()
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture()
def backend():
    return FakeBackend()


@pytest.fixture()
def controller(backend):
    return KeyboardController(backend=backend)


# -- KeyboardController ------------------------------------------------------

def test_type_char_writes_character(controller, backend):
    assert controller.type_char("a") is True
    assert backend.written == ["a"]


def test_type_char_handles_uppercase_and_symbols(controller, backend):
    controller.type_char("A")
    controller.type_char("!")
    assert backend.written == ["A", "!"]


def test_type_char_rejects_empty(controller, backend):
    assert controller.type_char("") is False
    assert backend.written == []


def test_type_text_writes_run(controller, backend):
    assert controller.type_text("hi") is True
    assert backend.written == ["hi"]


def test_press_key_valid(controller, backend):
    assert controller.press_key("space") is True
    assert controller.press_key("enter") is True
    assert backend.pressed == ["space", "enter"]


def test_press_key_rejects_unknown(controller, backend):
    """An unrecognised key name must never reach the OS."""
    assert controller.press_key("not-a-key") is False
    assert backend.pressed == []


def test_press_key_rejects_empty(controller, backend):
    assert controller.press_key("") is False
    assert backend.pressed == []


def test_valid_special_keys_are_lowercase_and_sane():
    assert "space" in VALID_SPECIAL_KEYS
    assert all(k == k.lower() for k in VALID_SPECIAL_KEYS)


def test_backend_exception_is_swallowed():
    """A failing backend must not raise into the caller (pipeline safety)."""
    bad = KeyboardController(backend=ExplodingBackend())
    assert bad.type_char("a") is False
    assert bad.type_text("hello") is False
    assert bad.press_key("space") is False


# -- layout ------------------------------------------------------------------

def test_layout_has_all_letters_and_digits():
    """Every letter a-z and digit 0-9 appears exactly once as a char key."""
    chars: list[str] = []
    for row in _build_rows():
        for key in row.keys:
            if key.kind == "char":
                chars.append(key.base)
    for expected in "abcdefghijklmnopqrstuvwxyz0123456789":
        assert chars.count(expected) == 1, f"{expected} appears {chars.count(expected)}x"


def test_layout_includes_essential_special_keys():
    keys = [key for row in _build_rows() for key in row.keys]
    specials = {k.special for k in keys if k.kind == "special"}
    for needed in ("space", "enter", "backspace", "tab"):
        assert needed in specials, f"missing {needed}"
    # Shift is its own kind (a one-shot UI toggle, not an OS key press).
    assert any(k.kind == "shift" for k in keys)


def test_digit_keys_have_shifted_symbols():
    """The number row must map to symbols when Shift is active."""
    row0 = _build_rows()[0]
    digits = {k.base: k.shifted for k in row0.keys if k.kind == "char"}
    assert digits["1"] == "!"
    assert digits["0"] == ")"


def test_letter_keys_shift_to_uppercase():
    rows = _build_rows()
    q_key = next(k for k in rows[1].keys if k.base == "q")
    assert q_key.shifted == "Q"


# -- VirtualKeyboard widget --------------------------------------------------

@pytest.fixture()
def keyboard(qapp, backend):
    kb = VirtualKeyboard(KeyboardController(backend=backend), LIGHT)
    yield kb
    kb.deleteLater()


def test_keyboard_never_accepts_focus(keyboard):
    """The window must be flagged to never take keyboard focus."""
    flags = keyboard.windowFlags()
    assert flags & Qt.WindowType.WindowDoesNotAcceptFocus


def test_show_without_activating(keyboard):
    assert keyboard.testAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)


def test_all_key_buttons_have_no_focus_policy(keyboard):
    """Clicking a key must not move focus to the keyboard."""
    for button, _key in keyboard._key_buttons:
        assert button.focusPolicy() == Qt.FocusPolicy.NoFocus


def test_clicking_letter_types_base_char(keyboard, backend):
    button = next(b for b, k in keyboard._key_buttons if k.base == "a")
    button.click()
    assert backend.written == ["a"]


def test_shift_is_one_shot(keyboard, backend):
    """Shift then a letter types uppercase, then Shift auto-releases."""
    shift_btn = next(b for b, k in keyboard._key_buttons if k.kind == "shift")
    a_btn = next(b for b, k in keyboard._key_buttons if k.base == "a")
    shift_btn.click()
    a_btn.click()
    assert backend.written == ["A"]
    # Shift must be released after the character.
    assert keyboard._shift is False
    # A second click types lowercase again.
    a_btn.click()
    assert backend.written == ["A", "a"]


def test_shift_toggles_state(keyboard):
    shift_btn = next(b for b, k in keyboard._key_buttons if k.kind == "shift")
    assert keyboard._shift is False
    shift_btn.click()
    assert keyboard._shift is True
    shift_btn.click()
    assert keyboard._shift is False


def test_shift_relabels_letter_buttons(keyboard):
    shift_btn = next(b for b, k in keyboard._key_buttons if k.kind == "shift")
    a_btn = next(b for b, k in keyboard._key_buttons if k.base == "a")
    assert a_btn.text() == "a"
    shift_btn.click()
    assert a_btn.text() == "A"
    a_btn.click()
    assert a_btn.text() == "a"


def test_space_and_enter_press_specials(keyboard, backend):
    space_btn = next(b for b, k in keyboard._key_buttons if k.special == "space")
    enter_btn = next(b for b, k in keyboard._key_buttons if k.special == "enter")
    space_btn.click()
    enter_btn.click()
    assert backend.pressed == ["space", "enter"]


def test_backspace_presses_special(keyboard, backend):
    bs_btn = next(b for b, k in keyboard._key_buttons if k.special == "backspace")
    bs_btn.click()
    assert backend.pressed == ["backspace"]


def test_toggle_show_hide(keyboard):
    keyboard.toggle()
    assert keyboard.isVisible()
    keyboard.toggle()
    assert not keyboard.isVisible()


def test_hide_emits_signal(keyboard):
    from PySide6.QtTest import QSignalSpy

    spy = QSignalSpy(keyboard.hidden)
    keyboard.show_keyboard()
    keyboard.request_hide()
    assert spy.count() == 1


def test_show_resets_shift(keyboard):
    shift_btn = next(b for b, k in keyboard._key_buttons if k.kind == "shift")
    shift_btn.click()
    assert keyboard._shift is True
    keyboard.request_hide()
    keyboard.show_keyboard()
    assert keyboard._shift is False
