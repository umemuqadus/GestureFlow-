"""Runtime metrics collection.

Pure-Python, thread-safe enough for single-producer usage from the vision
thread; the UI receives immutable snapshots through Qt signals.
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field


@dataclass(frozen=True)
class MetricsSnapshot:
    fps: float = 0.0
    latency_ms: float = 0.0
    tracking_confidence: float = 0.0
    hands_detected: int = 0
    frames_processed: int = 0
    clicks: int = 0
    right_clicks: int = 0
    double_clicks: int = 0
    scroll_events: int = 0
    drag_events: int = 0
    tracking_losses: int = 0
    gesture: str = "none"
    state: str = "IDLE"
    paused: bool = False
    running: bool = False
    uptime_s: float = 0.0
    pinch_distance: float = 0.0


class MetricsCollector:
    """Rolling FPS / latency window plus lifetime session counters."""

    def __init__(self, window: int = 60) -> None:
        self._frame_times: deque[float] = deque(maxlen=window)
        self._latencies: deque[float] = deque(maxlen=window)
        self.reset_session()

    # -- session lifecycle ---------------------------------------------------
    def reset_session(self) -> None:
        self._frame_times.clear()
        self._latencies.clear()
        self.clicks = 0
        self.right_clicks = 0
        self.double_clicks = 0
        self.scroll_events = 0
        self.drag_events = 0
        self.tracking_losses = 0
        self.frames_processed = 0
        self._started_at: float | None = None
        self.tracking_confidence = 0.0
        self.hands_detected = 0
        self.gesture = "none"
        self.state = "IDLE"
        self.pinch_distance = 0.0

    def mark_start(self) -> None:
        self.reset_session()
        self._started_at = time.perf_counter()

    # -- recording -----------------------------------------------------------
    def record_frame(self, latency_ms: float, now: float | None = None) -> None:
        self._frame_times.append(now if now is not None else time.perf_counter())
        self._latencies.append(latency_ms)
        self.frames_processed += 1

    def record_click(self) -> None:
        self.clicks += 1

    def record_right_click(self) -> None:
        self.right_clicks += 1

    def record_double_click(self) -> None:
        self.double_clicks += 1
        self.clicks += 2  # a double click is two click events

    def record_scroll(self, amount: int = 1) -> None:
        self.scroll_events += max(1, int(amount))

    def record_drag(self) -> None:
        self.drag_events += 1

    def record_tracking_loss(self) -> None:
        self.tracking_losses += 1

    # -- derived values ------------------------------------------------------
    @property
    def fps(self) -> float:
        if len(self._frame_times) < 2:
            return 0.0
        span = self._frame_times[-1] - self._frame_times[0]
        if span <= 0:
            return 0.0
        return (len(self._frame_times) - 1) / span

    @property
    def latency_ms(self) -> float:
        if not self._latencies:
            return 0.0
        return sum(self._latencies) / len(self._latencies)

    @property
    def uptime_s(self) -> float:
        if self._started_at is None:
            return 0.0
        return time.perf_counter() - self._started_at

    def snapshot(
        self,
        *,
        gesture: str,
        state: str,
        paused: bool,
        running: bool,
        tracking_confidence: float,
        hands_detected: int,
        pinch_distance: float = 0.0,
    ) -> MetricsSnapshot:
        self.gesture = gesture
        self.state = state
        return MetricsSnapshot(
            fps=round(self.fps, 1),
            latency_ms=round(self.latency_ms, 1),
            tracking_confidence=round(float(tracking_confidence), 3),
            hands_detected=hands_detected,
            frames_processed=self.frames_processed,
            clicks=self.clicks,
            right_clicks=self.right_clicks,
            double_clicks=self.double_clicks,
            scroll_events=self.scroll_events,
            drag_events=self.drag_events,
            tracking_losses=self.tracking_losses,
            gesture=gesture,
            state=state,
            paused=paused,
            running=running,
            uptime_s=round(self.uptime_s, 1),
            pinch_distance=round(float(pinch_distance), 3),
        )
