"""System mouse control via PyAutoGUI.

This is the only module that touches the OS cursor.  It tracks which buttons
are currently held so :meth:`release_all` can never leave a drag stuck, and it
validates coordinates before acting.

PyAutoGUI's built-in failsafe (move the pointer to a screen corner to abort) is
left enabled by default; see :meth:`set_failsafe`.
"""

from __future__ import annotations

import threading

from utils.logger import get_logger

log = get_logger(__name__)

LEFT = "left"
RIGHT = "right"
MIDDLE = "middle"

_VALID_BUTTONS = (LEFT, RIGHT, MIDDLE)


class MouseController:
    """Thread-safe wrapper over PyAutoGUI with held-button bookkeeping.

    ``backend`` may be injected for testing; it must expose the same subset of
    the PyAutoGUI API used here (moveTo, click, doubleClick, mouseDown, mouseUp,
    scroll, hscroll, keyDown, keyUp, size, position, FAILSAFE, PAUSE).
    """

    def __init__(self, failsafe: bool = True, backend=None) -> None:
        if backend is None:
            import pyautogui  # noqa: PLC0415 - imported lazily for testability

            pyautogui.FAILSAFE = failsafe
            # A short default duration keeps movement snappy; smoothing lives in
            # the CursorSmoother, not in PyAutoGUI's tweening.
            pyautogui.PAUSE = 0.0
            backend = pyautogui
        self._pyautogui = backend
        self._pyautogui.FAILSAFE = failsafe
        self._lock = threading.RLock()
        self._held: set[str] = set()
        self._last_position: tuple[int, int] | None = None

    # -- failsafe ------------------------------------------------------------
    def set_failsafe(self, enabled: bool) -> None:
        """Enable/disable PyAutoGUI's corner failsafe.

        When enabled, moving the mouse to the upper-left corner of the screen
        raises ``pyautogui.FailSafeException`` and halts automation.  We keep
        it on unless the user explicitly turns it off.
        """
        self._pyautogui.FAILSAFE = bool(enabled)
        log.info("PyAutoGUI failsafe %s", "enabled" if enabled else "DISABLED by user")

    @property
    def failsafe(self) -> bool:
        return bool(self._pyautogui.FAILSAFE)

    # -- state ---------------------------------------------------------------
    @property
    def held_buttons(self) -> frozenset[str]:
        with self._lock:
            return frozenset(self._held)

    def is_held(self, button: str) -> bool:
        with self._lock:
            return button in self._held

    # -- movement ------------------------------------------------------------
    def move_to(self, x: int, y: int) -> None:
        """Move the cursor, skipping redundant writes to reduce system load."""
        with self._lock:
            if not self._valid_point(x, y):
                log.warning("Rejected invalid cursor target (%r, %r)", x, y)
                return
            if self._last_position == (x, y):
                return
            try:
                self._pyautogui.moveTo(x, y, _pause=False)
                self._last_position = (x, y)
            except Exception as exc:  # noqa: BLE001 - surface, don't crash
                log.error("Cursor move failed: %s", exc)

    def _valid_point(self, x: object, y: object) -> bool:
        return (
            isinstance(x, int) and isinstance(y, int)
            and x >= 0 and y >= 0
            and x < self._pyautogui.size().width
            and y < self._pyautogui.size().height
        )

    # -- buttons -------------------------------------------------------------
    def click(self, button: str = LEFT) -> None:
        if button not in _VALID_BUTTONS:
            raise ValueError(f"Unknown mouse button: {button}")
        try:
            self._pyautogui.click(button=button, _pause=False)
        except Exception as exc:  # noqa: BLE001
            log.error("Click failed: %s", exc)

    def double_click(self) -> None:
        try:
            self._pyautogui.doubleClick(_pause=False)
        except Exception as exc:  # noqa: BLE001
            log.error("Double click failed: %s", exc)

    def press_down(self, button: str = LEFT) -> None:
        if button not in _VALID_BUTTONS:
            raise ValueError(f"Unknown mouse button: {button}")
        with self._lock:
            if button in self._held:
                return  # never send a second mouse-down
            try:
                self._pyautogui.mouseDown(button=button, _pause=False)
                self._held.add(button)
            except Exception as exc:  # noqa: BLE001
                log.error("mouseDown failed: %s", exc)

    def release(self, button: str = LEFT) -> None:
        if button not in _VALID_BUTTONS:
            raise ValueError(f"Unknown mouse button: {button}")
        with self._lock:
            if button not in self._held:
                return
            try:
                self._pyautogui.mouseUp(button=button, _pause=False)
            except Exception as exc:  # noqa: BLE001
                log.error("mouseUp failed: %s", exc)
            finally:
                self._held.discard(button)

    def scroll_vertical(self, amount: int) -> None:
        """Positive scrolls up, negative down (PyAutoGUI units of 120/notches)."""
        if not isinstance(amount, int) or amount == 0:
            return
        try:
            self._pyautogui.scroll(int(max(-10, min(10, amount))), _pause=False)
        except Exception as exc:  # noqa: BLE001
            log.error("Scroll failed: %s", exc)

    def scroll_horizontal(self, amount: int) -> None:
        if not isinstance(amount, int) or amount == 0:
            return
        try:
            self._pyautogui.hscroll(int(max(-10, min(10, amount))), _pause=False)
        except Exception as exc:  # noqa: BLE001
            log.error("Horizontal scroll failed: %s", exc)

    # -- safety --------------------------------------------------------------
    def release_all(self) -> set[str]:
        """Release every held button. Returns the buttons that were released."""
        with self._lock:
            released: set[str] = set()
            for button in list(self._held):
                self.release(button)
                released.add(button)
            if released:
                log.info("Released held buttons: %s", ", ".join(sorted(released)))
            return released

    def position(self) -> tuple[int, int] | None:
        try:
            pos = self._pyautogui.position()
            return int(pos.x), int(pos.y)
        except Exception:  # noqa: BLE001 - never let a query break the loop
            return None
