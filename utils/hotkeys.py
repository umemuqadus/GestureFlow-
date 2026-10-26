"""Global (system-wide) hotkeys on Windows via the Win32 API.

Uses ``RegisterHotKey`` through ctypes: no third-party dependency, no
administrator rights, and no low-level keyboard hook that could be flagged by
security software.

Hotkeys are registered on the GUI thread and delivered as ``WM_HOTKEY``
messages, which Qt dispatches through a ``QAbstractNativeEventFilter``.  This
means the shortcuts work even when the application window is not focused.

If registration fails (e.g. another app owns the combination) the failure is
reported and in-window shortcuts remain as the documented fallback.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes

from PySide6.QtCore import QAbstractNativeEventFilter, QObject, Signal

WM_HOTKEY = 0x0312

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000

_MODIFIER_MAP = {
    "ctrl": MOD_CONTROL,
    "control": MOD_CONTROL,
    "alt": MOD_ALT,
    "shift": MOD_SHIFT,
    "win": MOD_WIN,
    "super": MOD_WIN,
}

_NAMED_KEYS = {
    "esc": 0x1B, "escape": 0x1B,
    "space": 0x20,
    "tab": 0x09,
    "enter": 0x0D, "return": 0x0D,
    "backspace": 0x08,
    "pause": 0x13, "break": 0x13,
    "insert": 0x2D, "delete": 0x2E, "del": 0x2E,
    "home": 0x24, "end": 0x23, "pageup": 0x21, "pagedown": 0x22,
    "left": 0x25, "up": 0x26, "right": 0x27, "down": 0x28,
    "plus": 0xBB, "minus": 0xBD,
}
for _i in range(1, 13):
    _NAMED_KEYS[f"f{_i}"] = 0x70 + _i - 1


def parse_hotkey(spec: str) -> tuple[int, int] | None:
    """Parse ``"ctrl+alt+m"`` into ``(modifiers, virtual_key)``.

    Returns ``None`` when the spec cannot be understood.
    """
    if not spec or not isinstance(spec, str):
        return None
    parts = [p.strip().lower() for p in spec.split("+") if p.strip()]
    if not parts:
        return None
    key_token = parts[-1]
    modifier_tokens = parts[:-1]

    modifiers = 0
    for token in modifier_tokens:
        if token not in _MODIFIER_MAP:
            return None
        modifiers |= _MODIFIER_MAP[token]

    if key_token in _NAMED_KEYS:
        vk = _NAMED_KEYS[key_token]
    elif len(key_token) == 1 and key_token.isalnum():
        vk = ord(key_token.upper())
    else:
        return None
    return modifiers, vk


class GlobalHotkeyFilter(QAbstractNativeEventFilter, QObject):
    """Registers global hotkeys and emits a signal when one fires."""

    triggered = Signal(str)  # the original spec string, e.g. "ctrl+alt+m"

    def __init__(self, parent: QObject | None = None) -> None:
        QObject.__init__(self, parent)
        self._registered: dict[int, str] = {}   # hotkey id -> spec
        self._next_id = 1
        self._user32 = ctypes.windll.user32  # type: ignore[attr-defined]

    # -- registration --------------------------------------------------------
    def register(self, spec: str) -> bool:
        """Register one hotkey; returns True on success."""
        parsed = parse_hotkey(spec)
        if parsed is None:
            return False
        modifiers, vk = parsed
        hid = self._next_id
        ok = self._user32.RegisterHotKey(None, hid, modifiers | MOD_NOREPEAT, vk)
        if not ok:
            return False
        self._registered[hid] = spec
        self._next_id += 1
        return True

    def register_many(self, specs: list[str]) -> dict[str, bool]:
        return {spec: self.register(spec) for spec in specs}

    def unregister_all(self) -> None:
        for hid in list(self._registered):
            self._user32.UnregisterHotKey(None, hid)
        self._registered.clear()

    # -- dispatch ------------------------------------------------------------
    def nativeEventFilter(self, eventType, message):  # noqa: N802 - Qt API name
        try:
            msg_id = int(message.message) if hasattr(message, "message") else 0
        except (AttributeError, TypeError):
            return False, 0
        if msg_id != WM_HOTKEY:
            return False, 0
        hid = int(message.wParam) if hasattr(message, "wParam") else 0
        spec = self._registered.get(hid)
        if spec:
            self.triggered.emit(spec)
        return False, 0
