"""Safety manager: the layer that guarantees mouse automation cannot run away.

Responsibilities
----------------
* Emergency stop: a single call that pauses control *and* releases every held
  button immediately.
* Pause-on-window-focus-loss: the engine calls :meth:`on_focus_changed`; when
  the app loses focus (and the option is on) control pauses and buttons release.
* Shutdown safety: :meth:`shutdown` is idempotent and always releases buttons.
* Fail-closed defaults: if anything is uncertain, the safety manager stops
  automation rather than continuing.

Kept deliberately separate from gesture recognition so safety decisions never
depend on gesture heuristics.
"""

from __future__ import annotations

import time

from PySide6.QtCore import QObject, Signal

from app.config import SafetyConfig
from controller.mouse_controller import MouseController
from utils.logger import get_logger

log = get_logger(__name__)


class SafetyManager(QObject):
    """Owns pause/emergency-stop state for the running controller."""

    emergency_stopped = Signal()
    paused_changed = Signal(bool)

    def __init__(self, mouse: MouseController, cfg: SafetyConfig) -> None:
        super().__init__()
        self._mouse = mouse
        self.cfg = cfg
        self._paused = False
        self._emergency = False
        self._stopped_at: float | None = None

    # -- state ---------------------------------------------------------------
    @property
    def paused(self) -> bool:
        return self._paused

    @property
    def emergency(self) -> bool:
        return self._emergency

    def may_act(self) -> bool:
        """True only when automation is allowed to perform actions."""
        return not self._paused and not self._emergency

    # -- pause / resume ------------------------------------------------------
    def pause(self, reason: str = "") -> None:
        if self._paused:
            return
        self._paused = True
        self._mouse.release_all()
        log.info("Control paused%s", f": {reason}" if reason else "")
        self.paused_changed.emit(True)

    def resume(self) -> None:
        if not self._paused:
            return
        if self._emergency:
            log.info("Resume ignored: emergency stop is active")
            return
        self._paused = False
        log.info("Control resumed")
        self.paused_changed.emit(False)

    def toggle_pause(self) -> None:
        if self._paused:
            self.resume()
        else:
            self.pause("toggled by user")

    # -- emergency -----------------------------------------------------------
    def emergency_stop(self, reason: str = "emergency stop") -> None:
        """Immediate, unconditional halt: release buttons and stop actions."""
        self._emergency = True
        self._paused = True
        released = self._mouse.release_all()
        self._stopped_at = time.perf_counter()
        log.warning("EMERGENCY STOP (%s); released: %s",
                    reason, ", ".join(sorted(released)) or "none")
        self.paused_changed.emit(True)
        self.emergency_stopped.emit()

    def clear_emergency(self) -> None:
        """Explicit user action required to leave the emergency state."""
        self._emergency = False
        self._paused = False
        log.info("Emergency stop cleared by user")
        self.paused_changed.emit(False)

    # -- focus handling ------------------------------------------------------
    def on_focus_changed(self, focused: bool) -> None:
        if not focused and self.cfg.pause_on_focus_loss:
            self.pause("window lost focus")

    # -- shutdown ------------------------------------------------------------
    def shutdown(self) -> None:
        """Called on stop and on app close; must be safe to call repeatedly."""
        self._paused = True
        released = self._mouse.release_all()
        if released:
            log.info("Shutdown released: %s", ", ".join(sorted(released)))
