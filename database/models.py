"""Row-level dataclasses mirroring the SQLite schema.

These are *not* an ORM; repositories map rows <-> dataclasses explicitly so the
SQL stays readable and testable.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Profile:
    id: int | None
    name: str
    created_at: str
    last_used_at: str


@dataclass
class SessionSummary:
    id: int | None
    profile_name: str
    started_at: str
    ended_at: str
    duration_s: float
    clicks: int
    right_clicks: int
    double_clicks: int
    scroll_events: int
    drag_events: int
    tracking_losses: int
    frames_processed: int
    avg_fps: float
