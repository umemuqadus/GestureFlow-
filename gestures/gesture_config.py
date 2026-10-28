"""Per-gesture configuration: thresholds, hold times, cooldowns, toggles."""

from __future__ import annotations

from dataclasses import dataclass, asdict

from app import constants as C
from app.config import GestureConfig


@dataclass
class GestureRule:
    """Tunable behaviour for a single gesture."""

    gesture_id: str
    action: str
    enabled: bool = True
    threshold: float = 0.3          # activation distance (normalised)
    release_threshold: float = 0.45  # hysteresis release point
    hold_ms: int = 0                # minimum stable duration before firing
    cooldown_ms: int = 250          # minimum gap between activations

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "GestureRule":
        known = {f: data[f] for f in cls.__dataclass_fields__ if f in data}
        return cls(**known)


def default_rules(cfg: GestureConfig) -> dict[str, GestureRule]:
    """Build the default rule set from an app-level gesture config.

    The same ``GestureConfig`` object is shared at runtime so slider changes
    take effect immediately; these rules hold the per-gesture extras.
    """
    return {
        C.GESTURE_PINCH: GestureRule(
            gesture_id=C.GESTURE_PINCH,
            action=C.ACTION_LEFT_CLICK,
            enabled=cfg.enable_left_click,
            threshold=cfg.pinch_threshold,
            release_threshold=cfg.release_threshold,
            cooldown_ms=cfg.click_cooldown_ms,
        ),
        C.GESTURE_RIGHT_CLICK: GestureRule(
            gesture_id=C.GESTURE_RIGHT_CLICK,
            action=C.ACTION_RIGHT_CLICK,
            enabled=cfg.enable_right_click,
            threshold=cfg.right_pinch_threshold,
            release_threshold=cfg.right_pinch_threshold + 0.12,
            cooldown_ms=cfg.click_cooldown_ms,
        ),
        C.GESTURE_SCROLL_V: GestureRule(
            gesture_id=C.GESTURE_SCROLL_V,
            action=C.ACTION_SCROLL_V,
            enabled=cfg.enable_scroll,
            hold_ms=0,
        ),
        C.GESTURE_SCROLL_H: GestureRule(
            gesture_id=C.GESTURE_SCROLL_H,
            action=C.ACTION_SCROLL_H,
            enabled=cfg.enable_scroll,
        ),
        C.GESTURE_OPEN_PALM: GestureRule(
            gesture_id=C.GESTURE_OPEN_PALM,
            action=C.ACTION_PAUSE,
            enabled=cfg.enable_pause,
            hold_ms=cfg.pause_hold_ms,
        ),
        C.GESTURE_POINT: GestureRule(
            gesture_id=C.GESTURE_POINT,
            action=C.ACTION_MOVE,
            enabled=True,
        ),
        C.GESTURE_DRAG: GestureRule(
            gesture_id=C.GESTURE_DRAG,
            action=C.ACTION_DRAG_START,
            enabled=cfg.enable_drag,
            hold_ms=cfg.drag_hold_ms,
        ),
        C.GESTURE_DOUBLE_CLICK: GestureRule(
            gesture_id=C.GESTURE_DOUBLE_CLICK,
            action=C.ACTION_DOUBLE_CLICK,
            enabled=cfg.enable_double_click,
            hold_ms=cfg.double_click_window_ms,
        ),
        # -- system-control gestures -----------------------------------------
        C.GESTURE_FIST: GestureRule(
            gesture_id=C.GESTURE_FIST,
            action=C.ACTION_SCREENSHOT,
            enabled=cfg.enable_screenshot,
            hold_ms=cfg.system_hold_ms,
            cooldown_ms=cfg.system_cooldown_ms,
        ),
        C.GESTURE_THUMB_UP: GestureRule(
            gesture_id=C.GESTURE_THUMB_UP,
            action=C.ACTION_VOLUME_UP,
            enabled=cfg.enable_volume,
            hold_ms=cfg.system_hold_ms,
            cooldown_ms=cfg.system_repeat_ms,
        ),
        C.GESTURE_THUMB_DOWN: GestureRule(
            gesture_id=C.GESTURE_THUMB_DOWN,
            action=C.ACTION_VOLUME_DOWN,
            enabled=cfg.enable_volume,
            hold_ms=cfg.system_hold_ms,
            cooldown_ms=cfg.system_repeat_ms,
        ),
        C.GESTURE_SHAKA: GestureRule(
            gesture_id=C.GESTURE_SHAKA,
            action=C.ACTION_VOLUME_MUTE,
            enabled=cfg.enable_volume,
            hold_ms=cfg.system_hold_ms,
            cooldown_ms=cfg.system_cooldown_ms,
        ),
        C.GESTURE_THREE_FINGERS: GestureRule(
            gesture_id=C.GESTURE_THREE_FINGERS,
            action=C.ACTION_BRIGHTNESS,
            enabled=cfg.enable_brightness,
            hold_ms=cfg.system_hold_ms,
            cooldown_ms=cfg.brightness_step_ms,
        ),
        C.GESTURE_FLAT_HAND: GestureRule(
            gesture_id=C.GESTURE_FLAT_HAND,
            action=C.ACTION_MEDIA_TOGGLE,
            enabled=cfg.enable_media,
            hold_ms=cfg.system_hold_ms,
            cooldown_ms=cfg.system_cooldown_ms,
        ),
        C.GESTURE_NONE: GestureRule(
            gesture_id=C.GESTURE_NONE,
            action=C.ACTION_NONE,
            enabled=True,
        ),
    }


# Gestures that must never be active at the same time.
CONFLICT_GROUPS: tuple[frozenset[str], ...] = (
    frozenset({C.GESTURE_PINCH, C.GESTURE_SCROLL_V, C.GESTURE_SCROLL_H}),
    frozenset({C.GESTURE_PINCH, C.GESTURE_RIGHT_CLICK}),
    frozenset({C.GESTURE_SCROLL_V, C.GESTURE_SCROLL_H}),
    frozenset({C.GESTURE_OPEN_PALM, C.GESTURE_POINT, C.GESTURE_PINCH}),
)


def validate_mappings(rules: dict[str, GestureRule]) -> list[str]:
    """Return a list of human-readable mapping problems (empty = valid)."""
    problems: list[str] = []
    action_owners: dict[str, list[str]] = {}
    for gid, rule in rules.items():
        if not rule.enabled:
            continue
        if rule.release_threshold <= rule.threshold:
            problems.append(
                f"{gid}: release threshold must exceed activation threshold."
            )
        if rule.cooldown_ms < 0 or rule.hold_ms < 0:
            problems.append(f"{gid}: cooldown and hold times cannot be negative.")
        action_owners.setdefault(rule.action, []).append(gid)

    # Two enabled gestures claiming the same discrete action is a conflict.
    for action, owners in action_owners.items():
        if action in (C.ACTION_MOVE, C.ACTION_NONE, C.ACTION_SCROLL_V, C.ACTION_SCROLL_H):
            continue
        if len(owners) > 1:
            problems.append(
                f"Action '{action}' is assigned to multiple gestures: {', '.join(owners)}."
            )
    return problems
