"""Keyboard input via PyAutoGUI.

This is the only module that types text to the OS.  It is deliberately thin:
the *layout* and *shift* logic live in the virtual-keyboard widget, which
decides which character to send.  This class only validates input, forwards it
to PyAutoGUI and logs failures without ever raising into the pipeline.

Because the virtual keyboard is a window of real buttons that the gesture-driven
OS cursor clicks, no new gesture recognition is required to type.  The keyboard
window is configured never to take focus (see ``ui/virtual_keyboard.py``), so
the characters typed here land in whatever application the user focused.

A ``backend`` may be injected so tests never press real keys.
"""

from __future__ import annotations

from utils.logger import get_logger

log = get_logger(__name__)

# Named keys the virtual keyboard is allowed to emit (subset of PyAutoGUI's
# KEYBOARD_KEYS).  Keeping an explicit allow-list prevents a malformed layout
# from ever sending an unexpected key name to the OS.
VALID_SPECIAL_KEYS = frozenset(
    {
        "space",
        "enter",
        "backspace",
        "tab",
        "esc",
        "delete",
        "home",
        "end",
        "pageup",
        "pagedown",
        "left",
        "up",
        "right",
        "down",
        "shift",
        "ctrl",
        "alt",
    }
)


class PyAutoGUIKeyboardBackend:
    """Real keystroke backend using PyAutoGUI."""

    def write(self, text: str) -> None:
        import pyautogui  # noqa: PLC0415 - lazy so tests need no real backend

        pyautogui.write(text)

    def press(self, key: str) -> None:
        import pyautogui  # noqa: PLC0415 - lazy so tests need no real backend

        pyautogui.press(key)


class KeyboardController:
    """Sends keystrokes to the focused window with app-level validation.

    ``backend`` may be injected for testing; it must expose ``write(text)``
    and ``press(key)``.
    """

    def __init__(self, backend=None) -> None:
        self.backend = backend if backend is not None else PyAutoGUIKeyboardBackend()

    # -- public API ----------------------------------------------------------
    def type_char(self, char: str) -> bool:
        """Type a single printable character (shift handled by PyAutoGUI)."""
        if not char or not isinstance(char, str):
            return False
        try:
            self.backend.write(char)
        except Exception as exc:  # noqa: BLE001 - never crash the pipeline
            log.error("Typing %r failed: %s", char, exc)
            return False
        log.debug("Typed %r", char)
        return True

    def type_text(self, text: str) -> bool:
        """Type a short run of characters (used for words / tests)."""
        if not text or not isinstance(text, str):
            return False
        try:
            self.backend.write(text)
        except Exception as exc:  # noqa: BLE001
            log.error("Typing text failed: %s", exc)
            return False
        log.debug("Typed %d characters", len(text))
        return True

    def press_key(self, key: str) -> bool:
        """Press a named key (space, enter, backspace, tab, esc, ...)."""
        if not key or key not in VALID_SPECIAL_KEYS:
            log.warning("Ignoring unknown special key %r", key)
            return False
        try:
            self.backend.press(key)
        except Exception as exc:  # noqa: BLE001
            log.error("Pressing %r failed: %s", key, exc)
            return False
        log.debug("Pressed %r", key)
        return True
