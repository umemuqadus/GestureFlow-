"""Session statistics service: accumulates counters and stores summaries."""

from __future__ import annotations

from datetime import datetime, timezone

from database.database_manager import DatabaseManager
from database.models import SessionSummary
from database.repositories import SessionRepository
from utils.logger import get_logger
from utils.metrics import MetricsSnapshot

log = get_logger(__name__)


class StatisticsService:
    def __init__(self, db: DatabaseManager) -> None:
        self._repo = SessionRepository(db)

    def record_session(self, profile_name: str, started: datetime,
                       snapshot: MetricsSnapshot) -> int | None:
        """Persist one finished session; returns the stored row id."""
        ended = datetime.now(timezone.utc)
        duration = max(0.0, (ended - started).total_seconds())
        summary = SessionSummary(
            id=None,
            profile_name=profile_name,
            started_at=started.isoformat(timespec="seconds"),
            ended_at=ended.isoformat(timespec="seconds"),
            duration_s=round(duration, 1),
            clicks=snapshot.clicks,
            right_clicks=snapshot.right_clicks,
            double_clicks=snapshot.double_clicks,
            scroll_events=snapshot.scroll_events,
            drag_events=snapshot.drag_events,
            tracking_losses=snapshot.tracking_losses,
            frames_processed=snapshot.frames_processed,
            avg_fps=snapshot.fps,
        )
        try:
            row_id = self._repo.add(summary)
            log.info("Session stored (id=%s, %.1fs, %d frames)",
                     row_id, duration, snapshot.frames_processed)
            return row_id
        except Exception as exc:  # noqa: BLE001 - statistics must not break the app
            log.error("Could not store session summary: %s", exc)
            return None

    def recent(self, limit: int = 25) -> list[SessionSummary]:
        try:
            return self._repo.recent(limit)
        except Exception as exc:  # noqa: BLE001
            log.error("Could not load session history: %s", exc)
            return []

    def clear(self) -> int:
        count = self._repo.clear()
        log.info("Cleared %d session rows", count)
        return count

    def count(self) -> int:
        return self._repo.count()
