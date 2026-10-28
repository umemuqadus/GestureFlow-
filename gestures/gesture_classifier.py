"""Gesture classifier: turns landmarks into a stable gesture label.

Holds only the per-frame hysteresis state (which pinch-style gesture is
currently latched); everything else is delegated to ``gesture_rules``.
"""

from __future__ import annotations

from dataclasses import dataclass

from app import constants as C
from app.config import GestureConfig
from gestures import gesture_rules as rules
from vision.landmark_processor import FingerState, analyze
from vision.types import HandObservation


@dataclass(frozen=True)
class Classification:
    """Result of classifying one frame."""

    gesture: str
    fingers: FingerState | None
    observation: HandObservation | None

    @property
    def confidence(self) -> float:
        """Heuristic confidence in [0, 1]: how decisively the gesture is held."""
        if self.observation is None or self.fingers is None:
            return 0.0
        distance = rules.gesture_distance(self.observation, self.fingers, self.gesture)
        if self.gesture == C.GESTURE_PINCH:
            span = max(0.05, self.fingers.pinch_distance)
            strength = max(0.0, 1.0 - distance / max(0.05, span * 2))
        elif self.gesture in (C.GESTURE_POINT, C.GESTURE_SCROLL_V, C.GESTURE_SCROLL_H,
                              C.GESTURE_OPEN_PALM, C.GESTURE_FIST,
                              C.GESTURE_THUMB_UP, C.GESTURE_THUMB_DOWN,
                              C.GESTURE_SHAKA, C.GESTURE_FLAT_HAND,
                              C.GESTURE_THREE_FINGERS):
            strength = 0.8
        else:
            strength = 0.0
        # Blend in the detector's own score so low-quality frames read lower.
        return round(min(1.0, strength * 0.6 + self.observation.score * 0.4), 3)


class GestureClassifier:
    """Rule-based classifier with pinch/right-click hysteresis."""

    def __init__(self, cfg: GestureConfig) -> None:
        self.cfg = cfg
        self._latched: str | None = None  # pinch / right_pinch latch

    def reset(self) -> None:
        self._latched = None

    def classify(self, obs: HandObservation | None) -> Classification:
        if obs is None or not obs.valid:
            self._latched = None
            return Classification(C.GESTURE_NONE, None, None)

        fingers = analyze(obs)
        cfg = self.cfg

        # --- latched pinch-style gestures (hysteresis) ----------------------
        if self._latched == C.GESTURE_PINCH:
            if rules.is_pinch_sustain(fingers, cfg):
                return Classification(C.GESTURE_PINCH, fingers, obs)
            self._latched = None
        if self._latched == C.GESTURE_RIGHT_CLICK:
            if rules.is_right_click_sustain(fingers, cfg):
                return Classification(C.GESTURE_RIGHT_CLICK, fingers, obs)
            self._latched = None

        for gesture in rules.PRIORITY:
            if self._matches(gesture, obs, fingers):
                if gesture in (C.GESTURE_PINCH, C.GESTURE_RIGHT_CLICK):
                    self._latched = gesture
                return Classification(gesture, fingers, obs)

        return Classification(C.GESTURE_NONE, fingers, obs)

    def _matches(self, gesture: str, obs: HandObservation, fingers: FingerState) -> bool:
        if gesture == C.GESTURE_PINCH:
            return rules.is_pinch_enter(fingers, self.cfg)
        if gesture == C.GESTURE_RIGHT_CLICK:
            return rules.is_right_click_enter(fingers, self.cfg)
        if gesture == C.GESTURE_OPEN_PALM:
            return rules.is_open_palm(fingers)
        if gesture == C.GESTURE_SCROLL_H:
            return rules.is_scroll_horizontal(obs, fingers)
        if gesture == C.GESTURE_SCROLL_V:
            return rules.is_scroll_vertical(obs, fingers)
        if gesture == C.GESTURE_POINT:
            return rules.is_point(fingers)
        if gesture == C.GESTURE_FIST:
            return rules.is_fist(fingers)
        # System-control poses.
        if gesture == C.GESTURE_THUMB_UP:
            return rules.is_thumb_up(obs, fingers)
        if gesture == C.GESTURE_THUMB_DOWN:
            return rules.is_thumb_down(obs, fingers)
        if gesture == C.GESTURE_SHAKA:
            return rules.is_shaka(fingers)
        if gesture == C.GESTURE_FLAT_HAND:
            return rules.is_flat_hand(fingers)
        if gesture == C.GESTURE_THREE_FINGERS:
            return rules.is_three_fingers(fingers)
        return False
