"""Gesture state machine.

Consumes one classified gesture per frame and emits *at most one* discrete
mouse action per frame, so gestures can never fight each other.  Handles
debouncing, cooldowns, double-click detection, tap-vs-drag timing and pause.

Tap-vs-drag rule (important): a pinch that is *released quickly* produces a
left click; a pinch *held past* ``drag_hold_ms`` becomes a drag (mouse-down).
This is the same interaction model as a touchscreen tap vs long-press, and it
guarantees a drag never emits a spurious click, and a hold never emits
repeated clicks.

The state machine is pure Python (no Qt, no pyautogui): it returns actions that
the engine executes, which makes it fully unit-testable.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from app import constants as C
from app.config import GestureConfig
from gestures.gesture_config import GestureRule

MS = 1000.0

# Gestures that drive non-mouse (system) actions.
SYSTEM_GESTURES: frozenset[str] = frozenset({
    C.GESTURE_FIST, C.GESTURE_THUMB_UP, C.GESTURE_THUMB_DOWN,
    C.GESTURE_SHAKA, C.GESTURE_FLAT_HAND, C.GESTURE_THREE_FINGERS,
})

# Pose -> discrete system action.  Brightness is movement-based and resolved
# directionally inside _handle_brightness instead.
_SYSTEM_ACTION: dict[str, str] = {
    C.GESTURE_FIST: C.ACTION_SCREENSHOT,
    C.GESTURE_THUMB_UP: C.ACTION_VOLUME_UP,
    C.GESTURE_THUMB_DOWN: C.ACTION_VOLUME_DOWN,
    C.GESTURE_SHAKA: C.ACTION_VOLUME_MUTE,
    C.GESTURE_FLAT_HAND: C.ACTION_MEDIA_TOGGLE,
}

# Pose -> HUD state shown while the gesture is recognised.
_SYSTEM_STATE: dict[str, str] = {
    C.GESTURE_FIST: C.STATE_SCREENSHOT,
    C.GESTURE_THUMB_UP: C.STATE_VOLUME,
    C.GESTURE_THUMB_DOWN: C.STATE_VOLUME,
    C.GESTURE_SHAKA: C.STATE_VOLUME,
    C.GESTURE_FLAT_HAND: C.STATE_MEDIA,
    C.GESTURE_THREE_FINGERS: C.STATE_BRIGHTNESS,
}

# Poses that keep firing while held (like holding a volume key).
_REPEATABLE_SYSTEM: frozenset[str] = frozenset({
    C.GESTURE_THUMB_UP, C.GESTURE_THUMB_DOWN,
})

# --- scroll tuning -----------------------------------------------------------
# EMA factor for the per-frame hand delta.  Higher = snappier, lower = smoother.
# Damps MediaPipe landmark jitter that would otherwise make scroll speed flicker.
_SCROLL_SMOOTH = 0.45
# Base delta -> scroll-step gain.  Multiplied by ``cfg.scroll_sensitivity``.
_SCROLL_GAIN = 60.0
# Per-frame emitted-step clamp (safety net; the mouse controller clamps too).
_SCROLL_MAX_STEPS = 5
# Accumulator bound, so a burst of fast motion cannot bank a huge backlog that
# later drains as a runaway scroll.
_SCROLL_ACCUM_MAX = 15.0


@dataclass
class StateMachineOutput:
    """What the engine should do for this frame."""

    action: str = C.ACTION_NONE
    state: str = C.STATE_IDLE
    scroll_dx: int = 0
    scroll_dy: int = 0
    reason: str = ""


class GestureStateMachine:
    """Deterministic gesture -> action arbitration."""

    def __init__(self, cfg: GestureConfig,
                 rules: dict[str, GestureRule] | None = None) -> None:
        self.cfg = cfg
        self.rules = rules or {}
        self.state: str = C.STATE_IDLE
        self.paused: bool = False
        self._gesture: str = C.GESTURE_NONE
        self._gesture_since: float = 0.0
        self._last_action_at: float = float("-inf")
        self._last_tap_at: float = float("-inf")   # last completed tap (for double-click)
        self._dragging: bool = False
        self._pinch_started_at: float | None = None   # pending tap-or-drag
        self._last_hand_pos: tuple[float, float] | None = None
        # Scroll smoothing state: EMA velocity + fractional-step accumulator.
        self._scroll_vel: float = 0.0
        self._scroll_accum: float = 0.0
        # System-control bookkeeping (screenshot / volume / brightness / media).
        self._last_system_at: float = float("-inf")
        self._system_fired_gesture: str | None = None  # discrete: one shot per held pose

    # -- lifecycle -----------------------------------------------------------
    def reset(self, paused: bool | None = None) -> None:
        """Return to a safe idle state (used on tracking loss / stop)."""
        if paused is not None:
            self.paused = paused
        self._gesture = C.GESTURE_NONE
        self._gesture_since = 0.0
        self._dragging = False
        self._pinch_started_at = None
        self._last_hand_pos = None
        self._scroll_vel = 0.0
        self._scroll_accum = 0.0
        self._last_system_at = float("-inf")
        self._system_fired_gesture = None
        self.state = C.STATE_PAUSED if self.paused else C.STATE_IDLE

    def force_pause(self, now: float | None = None) -> None:
        self.paused = True
        self._dragging = False
        self._pinch_started_at = None
        self._scroll_vel = 0.0
        self._scroll_accum = 0.0
        # Restart the palm-hold timer so the same continuous palm cannot
        # immediately resume control on the next frame.
        self._gesture_since = time.perf_counter() if now is None else now
        self.state = C.STATE_PAUSED

    def resume(self) -> None:
        self.paused = False
        self._dragging = False
        self._pinch_started_at = None
        self.state = C.STATE_TRACKING

    # -- helpers -------------------------------------------------------------
    def _rule_enabled(self, gesture: str) -> bool:
        rule = self.rules.get(gesture)
        return rule.enabled if rule is not None else True

    def _cooldown_ok(self, now: float, cooldown_ms: int) -> bool:
        return (now - self._last_action_at) * MS >= cooldown_ms

    @property
    def dragging(self) -> bool:
        return self._dragging

    # -- main entry ----------------------------------------------------------
    def update(
        self,
        gesture: str,
        now: float | None = None,
        hand_position: tuple[float, float] | None = None,
    ) -> StateMachineOutput:
        """Advance the machine by one frame.

        ``hand_position`` is the normalised frame coordinate of the tracking
        anchor, used for scroll-delta computation.
        """
        now = time.perf_counter() if now is None else now
        out = StateMachineOutput()

        # --- no hand ------------------------------------------------------
        if gesture == C.GESTURE_NONE:
            return self._handle_no_hand(now)

        # --- pause gesture (open palm held) ------------------------------
        if gesture == C.GESTURE_OPEN_PALM and self._rule_enabled(C.GESTURE_OPEN_PALM):
            if self._gesture != C.GESTURE_OPEN_PALM:
                self._gesture = C.GESTURE_OPEN_PALM
                self._gesture_since = now
            held_ms = (now - self._gesture_since) * MS
            if self.paused:
                # Palm held while paused -> resume (deliberate user action).
                if held_ms >= self.cfg.pause_hold_ms:
                    self.resume()
                    out.state = self.state
                    out.action = C.ACTION_RESUME
                    out.reason = "open palm held"
                    return out
                self.state = C.STATE_PAUSED
                out.state = self.state
                return out
            if held_ms >= self.cfg.pause_hold_ms:
                self.force_pause(now)
                out.state = self.state
                out.action = C.ACTION_PAUSE
                out.reason = "open palm held"
                return out
            # Palm rising but not yet held long enough: treat as tracking.
            self.state = C.STATE_TRACKING
            out.state = self.state
            return out

        # --- while paused, no other gesture may act ------------------------
        # Resuming requires holding the open palm again or the pause hotkey /
        # Resume button (handled by the SafetyManager).  This prevents an
        # accidental point gesture from resuming mouse control.
        if self.paused:
            self.state = C.STATE_PAUSED
            out.state = self.state
            return out

        # --- tracking established ----------------------------------------
        if self._gesture != gesture:
            self._gesture_since = now
            # A new pose re-arms discrete system actions and restarts the
            # baselines used by the movement-based gestures (scroll /
            # brightness).
            self._system_fired_gesture = None
            self._last_hand_pos = None
        held_ms = (now - self._gesture_since) * MS
        min_frames_ms = self.cfg.min_gesture_frames * (1000.0 / 30.0)
        self._gesture = gesture

        # --- pinch: tap (click) vs hold (drag) ---------------------------
        if gesture == C.GESTURE_PINCH and self._rule_enabled(C.GESTURE_PINCH):
            return self._handle_pinch(now, held_ms, min_frames_ms)

        # Pinch released this frame -> finish a drag, or complete a tap.
        if (self._dragging or self._pinch_started_at is not None) \
                and gesture != C.GESTURE_PINCH:
            return self._handle_pinch_end(now, min_frames_ms)

        # --- right click --------------------------------------------------
        if gesture == C.GESTURE_RIGHT_CLICK and self._rule_enabled(C.GESTURE_RIGHT_CLICK):
            if held_ms >= min_frames_ms and self._cooldown_ok(now, self.cfg.click_cooldown_ms):
                self._last_action_at = now
                self.state = C.STATE_RIGHT_CLICK
                out.action = C.ACTION_RIGHT_CLICK
                out.state = self.state
                return out
            self.state = C.STATE_TRACKING
            out.state = self.state
            return out

        # --- system actions (screenshot / volume / brightness / media) -------
        if gesture in SYSTEM_GESTURES and self._rule_enabled(gesture):
            return self._handle_system(gesture, now, held_ms, min_frames_ms,
                                       hand_position)

        # --- scrolling ----------------------------------------------------
        if gesture in (C.GESTURE_SCROLL_V, C.GESTURE_SCROLL_H) \
                and self._rule_enabled(C.GESTURE_SCROLL_V):
            return self._handle_scroll(gesture, now, hand_position)

        # --- cursor movement ---------------------------------------------
        if gesture == C.GESTURE_POINT:
            self.state = C.STATE_MOVING
            out.state = self.state
            out.action = C.ACTION_MOVE
            return out

        self.state = C.STATE_TRACKING
        out.state = self.state
        return out

    # -- branches ------------------------------------------------------------
    def _handle_no_hand(self, now: float) -> StateMachineOutput:
        out = StateMachineOutput()
        if self._dragging:
            self._dragging = False
            out.action = C.ACTION_DRAG_END
            out.reason = "tracking lost during drag"
        self._gesture = C.GESTURE_NONE
        self._gesture_since = 0.0
        self._pinch_started_at = None
        self._last_hand_pos = None
        self.state = C.STATE_PAUSED if self.paused else C.STATE_NO_HAND
        out.state = self.state
        return out

    def _handle_pinch(self, now: float, held_ms: float,
                      min_frames_ms: float) -> StateMachineOutput:
        out = StateMachineOutput()

        if self._dragging:
            self.state = C.STATE_DRAGGING
            out.state = self.state
            out.action = C.ACTION_DRAG_MOVE
            return out

        # Start (or continue) the pending tap-or-drag timer at pinch onset.
        if self._pinch_started_at is None:
            self._pinch_started_at = now

        pinch_ms = (now - self._pinch_started_at) * MS
        drag_enabled = self._rule_enabled(C.GESTURE_DRAG)

        if drag_enabled and pinch_ms >= self.cfg.drag_hold_ms:
            # Held long enough: this is a drag, not a click.
            self._dragging = True
            self.state = C.STATE_DRAGGING
            out.state = self.state
            out.action = C.ACTION_DRAG_START
            out.reason = "pinch held"
            return out

        # Otherwise keep waiting: the tap completes on release.
        self.state = C.STATE_TRACKING
        out.state = self.state
        return out

    def _handle_pinch_end(self, now: float, min_frames_ms: float) -> StateMachineOutput:
        """A pinch stopped: either finish the drag or register a tap."""
        out = StateMachineOutput()
        was_dragging = self._dragging
        started = self._pinch_started_at
        self._dragging = False
        self._pinch_started_at = None

        if was_dragging:
            self._last_action_at = now
            self.state = C.STATE_TRACKING
            out.state = self.state
            out.action = C.ACTION_DRAG_END
            out.reason = "pinch released"
            return out

        if started is None:
            self.state = C.STATE_TRACKING
            out.state = self.state
            return out

        # Ignore a pinch too brief to be a deliberate tap (noise).
        if (now - started) * MS < min_frames_ms:
            self.state = C.STATE_TRACKING
            out.state = self.state
            return out

        # A quick tap completed -> left click, or double click on the second tap.
        if not self._cooldown_ok(now, self.cfg.click_cooldown_ms):
            self.state = C.STATE_TRACKING
            out.state = self.state
            return out

        gap_ms = (now - self._last_tap_at) * MS
        if (self._rule_enabled(C.GESTURE_DOUBLE_CLICK)
                and 0 < gap_ms <= self.cfg.double_click_window_ms):
            self._last_action_at = now
            self._last_tap_at = float("-inf")
            self.state = C.STATE_DOUBLE_CLICK
            out.state = self.state
            out.action = C.ACTION_DOUBLE_CLICK
            out.reason = "two taps within window"
            return out

        self._last_action_at = now
        self._last_tap_at = now
        self.state = C.STATE_LEFT_CLICK
        out.state = self.state
        out.action = C.ACTION_LEFT_CLICK
        return out

    def _handle_scroll(self, gesture: str, now: float,
                       hand_position: tuple[float, float] | None) -> StateMachineOutput:
        """Two-finger scroll with smoothing and a fractional-step accumulator.

        A raw per-frame delta is far too jittery to drive scroll directly:
        MediaPipe landmark noise flickers the speed between 0 and full, and
        ``round()`` throws away slow-but-deliberate movement entirely.  We
        instead EMA-smooth the delta, accumulate fractional steps (a per-frame
        delta already encodes ``velocity x dt``, so summing them yields total
        hand *distance* -- inherently frame-rate independent), and emit whole
        steps as they cross each 1.0 boundary.  The accumulator is bled toward
        zero inside the dead zone so a hand that stops does not fire a delayed
        burst, and is bounded so a violent jerk cannot bank a runaway backlog.
        """
        out = StateMachineOutput()
        self.state = C.STATE_SCROLLING
        out.state = self.state

        if hand_position is None:
            self._last_hand_pos = None
            self._scroll_vel = 0.0
            self._scroll_accum = 0.0
            return out

        if self._last_hand_pos is None:
            self._last_hand_pos = hand_position  # establish baseline, no jump
            self._scroll_vel = 0.0
            self._scroll_accum = 0.0
            return out

        dx = hand_position[0] - self._last_hand_pos[0]
        dy = hand_position[1] - self._last_hand_pos[1]
        self._last_hand_pos = hand_position

        # Smooth the per-frame delta to suppress tracking jitter.
        if gesture == C.GESTURE_SCROLL_V:
            raw = dy
        else:
            raw = dx
        self._scroll_vel = _SCROLL_SMOOTH * raw + (1.0 - _SCROLL_SMOOTH) * self._scroll_vel

        deadzone = self.cfg.scroll_deadzone_px / 1000.0
        if abs(self._scroll_vel) < deadzone:
            # Inside the dead zone: bleed momentum so a stationary hand stops
            # cleanly instead of releasing a delayed burst on the next nudge.
            # The accumulator decays geometrically, then snaps to zero so no
            # fractional residue can fire much later.
            self._scroll_vel = 0.0
            self._scroll_accum *= 0.5
            if abs(self._scroll_accum) < 0.5:
                self._scroll_accum = 0.0
            return out

        gain = _SCROLL_GAIN * self.cfg.scroll_sensitivity
        self._scroll_accum += self._scroll_vel * gain
        # Bound the backlog so one violent motion cannot bank a runaway burst.
        self._scroll_accum = max(
            -_SCROLL_ACCUM_MAX, min(_SCROLL_ACCUM_MAX, self._scroll_accum)
        )

        steps = int(self._scroll_accum)  # truncates toward zero, keeps sign
        if steps == 0:
            return out
        self._scroll_accum -= steps
        steps = max(-_SCROLL_MAX_STEPS, min(_SCROLL_MAX_STEPS, steps))

        if gesture == C.GESTURE_SCROLL_V:
            out.action = C.ACTION_SCROLL_V
            out.scroll_dy = steps
        else:
            out.action = C.ACTION_SCROLL_H
            out.scroll_dx = steps
        return out

    # -- system actions -------------------------------------------------------
    def _handle_system(self, gesture: str, now: float, held_ms: float,
                       min_frames_ms: float,
                       hand_position: tuple[float, float] | None) -> StateMachineOutput:
        """Screenshot / volume / brightness / media dispatch.

        Brightness is pose *plus* hand movement, so it delegates to
        :meth:`_handle_brightness`.  Everything else is pose based: the pose must
        be held for a stable interval before firing, repeatable gestures (volume)
        then keep firing on ``system_repeat_ms`` while held, and discrete
        gestures (screenshot / mute / media) fire exactly once per held pose with
        a cooldown floor as a second line of defence.
        """
        out = StateMachineOutput()

        if gesture == C.GESTURE_THREE_FINGERS:
            return self._handle_brightness(now, held_ms, min_frames_ms, hand_position)

        required_ms = max(min_frames_ms, self.cfg.system_hold_ms)
        if held_ms < required_ms:
            self.state = C.STATE_TRACKING
            out.state = self.state
            return out

        repeatable = gesture in _REPEATABLE_SYSTEM
        if repeatable:
            interval_ms = self.cfg.system_repeat_ms
        else:
            # Discrete: one shot until the pose changes and comes back.
            if self._system_fired_gesture == gesture:
                self.state = _SYSTEM_STATE.get(gesture, C.STATE_TRACKING)
                out.state = self.state
                return out
            interval_ms = self.cfg.system_cooldown_ms

        if (now - self._last_system_at) * MS < interval_ms:
            self.state = _SYSTEM_STATE.get(gesture, C.STATE_TRACKING)
            out.state = self.state
            return out

        self._last_system_at = now
        if not repeatable:
            self._system_fired_gesture = gesture
        out.action = _SYSTEM_ACTION[gesture]
        self.state = _SYSTEM_STATE.get(gesture, C.STATE_TRACKING)
        out.state = self.state
        return out

    def _handle_brightness(self, now: float, held_ms: float, min_frames_ms: float,
                           hand_position: tuple[float, float] | None) -> StateMachineOutput:
        """Three fingers held -> raise/lower brightness with hand movement.

        Follows the scroll model: a dead zone plus a step interval keeps a
        steady hand from ramping the level, and frame y decreases upward so a
        rising hand brightens.
        """
        out = StateMachineOutput()
        self.state = C.STATE_BRIGHTNESS
        out.state = self.state

        required_ms = max(min_frames_ms, self.cfg.system_hold_ms)
        if held_ms < required_ms:
            return out

        if hand_position is None:
            self._last_hand_pos = None
            return out
        if self._last_hand_pos is None:
            self._last_hand_pos = hand_position  # establish baseline, no jump
            return out

        dy = hand_position[1] - self._last_hand_pos[1]
        self._last_hand_pos = hand_position

        deadzone = self.cfg.scroll_deadzone_px / 1000.0
        if abs(dy) < deadzone:
            return out
        if (now - self._last_system_at) * MS < self.cfg.brightness_step_ms:
            return out

        self._last_system_at = now
        # Frame y decreases upward: a rising hand (negative dy) brightens.
        out.action = C.ACTION_BRIGHTNESS_UP if dy < 0 else C.ACTION_BRIGHTNESS_DOWN
        return out
