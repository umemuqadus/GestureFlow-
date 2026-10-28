"""Dashboard page: controller status, live metrics and recent sessions."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app import constants as C
from app.application import Application
from ui.components import Card, EmptyState, Pill, ScrollContainer, StatTile


def _fmt_duration(seconds: float) -> str:
    seconds = int(max(0, seconds))
    minutes, secs = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}h {minutes}m"
    if minutes:
        return f"{minutes}m {secs}s"
    return f"{secs}s"


class DashboardPage(QWidget):
    """Landing page with genuine runtime values from the engine."""

    def __init__(self, app: Application, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.app = app
        self.container = ScrollContainer(self)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.container)
        body = self.container.content_layout()

        # -- header ---------------------------------------------------------
        header = QHBoxLayout()
        title_box = QVBoxLayout()
        title = QLabel("Dashboard")
        title.setObjectName("PageTitle")
        subtitle = QLabel("Control your computer with hand gestures — everything runs locally.")
        subtitle.setObjectName("CardSubtitle")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        header.addLayout(title_box)
        header.addStretch(1)
        self.status_pill = Pill("Idle", "neutral")
        header.addWidget(self.status_pill)
        body.addLayout(header)

        # -- controller actions --------------------------------------------
        actions = Card("Controller")
        actions_layout = QHBoxLayout()
        self.start_btn = QPushButton("Start Controller")
        self.start_btn.setObjectName("PrimaryButton")
        self.stop_btn = QPushButton("Stop")
        self.pause_btn = QPushButton("Pause / Resume")
        self.pause_btn.setEnabled(False)
        self.emergency_btn = QPushButton("Emergency Stop")
        self.emergency_btn.setObjectName("DangerButton")
        self.stop_btn.setEnabled(False)
        for button in (self.start_btn, self.stop_btn, self.pause_btn, self.emergency_btn):
            actions_layout.addWidget(button)
        actions_layout.addStretch(1)
        actions.body().addLayout(actions_layout)
        self.controller_status = QLabel("Controller is stopped.")
        self.controller_status.setObjectName("CardSubtitle")
        actions.body().addWidget(self.controller_status)
        body.addWidget(actions)

        self.error_banner = QLabel("")
        self.error_banner.setObjectName("BannerError")
        self.error_banner.setWordWrap(True)
        self.error_banner.hide()
        body.addWidget(self.error_banner)

        # -- live metrics ----------------------------------------------------
        metrics = Card("Live metrics")
        grid = QGridLayout()
        grid.setSpacing(12)
        self.tile_fps = StatTile("FPS")
        self.tile_latency = StatTile("Latency")
        self.tile_confidence = StatTile("Confidence")
        self.tile_gesture = StatTile("Gesture")
        self.tile_clicks = StatTile("Clicks")
        self.tile_scroll = StatTile("Scrolls")
        self.tile_frames = StatTile("Frames")
        self.tile_duration = StatTile("Duration")
        for i, tile in enumerate(
            (self.tile_fps, self.tile_latency, self.tile_confidence, self.tile_gesture,
             self.tile_clicks, self.tile_scroll, self.tile_frames, self.tile_duration)
        ):
            row, col = divmod(i, 4)
            grid.addWidget(tile, row, col)
            grid.setColumnStretch(col, 1)
        metrics.body().addLayout(grid)
        body.addWidget(metrics)

        # -- recent sessions -------------------------------------------------
        history = Card("Recent sessions")
        self.history_table = QTableWidget(0, 5)
        self.history_table.setHorizontalHeaderLabels(
            ["Started", "Duration", "Clicks", "Scrolls", "Avg FPS"]
        )
        self.history_table.horizontalHeader().setStretchLastSection(True)
        self.history_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.history_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self.history_table.verticalHeader().setVisible(False)
        self.history_table.setAlternatingRowColors(True)
        history.body().addWidget(self.history_table)
        self.empty_state = EmptyState(
            "No sessions recorded yet",
            "Start the controller and your session summary will appear here.",
        )
        history.body().addWidget(self.empty_state)
        body.addWidget(history)
        body.addStretch(1)

        # -- wiring ----------------------------------------------------------
        self.start_btn.clicked.connect(self.app.start_controller)
        self.stop_btn.clicked.connect(self.app.stop_controller)
        self.pause_btn.clicked.connect(self.app.toggle_pause)
        self.emergency_btn.clicked.connect(lambda: self.app.emergency_stop("dashboard"))

        self.app.controller_started.connect(self._on_started)
        self.app.controller_stopped.connect(self._on_stopped)
        self.app.metrics_updated.connect(self._on_metrics)
        self.app.status_changed.connect(self._on_status)
        self.app.error.connect(self._on_error)
        self.app.paused_changed.connect(self._on_paused)
        self.app.gesture_changed.connect(self._on_gesture)

        self._on_stopped()

    # -- slots ----------------------------------------------------------------
    def _on_started(self) -> None:
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.pause_btn.setEnabled(True)
        self.status_pill.setText("Running")
        self.status_pill.set_kind("ok")
        self.controller_status.setText("Controller is running. Show your hand to the camera.")
        self.error_banner.hide()

    def _on_stopped(self) -> None:
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.pause_btn.setEnabled(False)
        self.status_pill.setText("Idle")
        self.status_pill.set_kind("neutral")
        self.controller_status.setText("Controller is stopped.")
        self.tile_gesture.set_value("—")

    def _on_paused(self, paused: bool) -> None:
        if not self.app.is_running:
            return
        self.status_pill.setText("Paused" if paused else "Running")
        self.status_pill.set_kind("warn" if paused else "ok")
        self.pause_btn.setText("Resume" if paused else "Pause")
        self.controller_status.setText(
            "Control paused. Press Resume or hold an open palm to resume."
            if paused else "Controller is running. Show your hand to the camera."
        )

    def _on_metrics(self, snapshot) -> None:
        self.tile_fps.set_value(f"{snapshot.fps:.0f}")
        self.tile_latency.set_value(f"{snapshot.latency_ms:.0f} ms")
        self.tile_confidence.set_value(f"{snapshot.tracking_confidence:.2f}")
        self.tile_clicks.set_value(str(snapshot.clicks))
        self.tile_scroll.set_value(str(snapshot.scroll_events))
        self.tile_frames.set_value(str(snapshot.frames_processed))
        self.tile_duration.set_value(_fmt_duration(snapshot.uptime_s))
        self.tile_gesture.set_value(C.GESTURE_LABELS.get(snapshot.gesture, snapshot.gesture))

    def _on_status(self, message: str) -> None:
        self.controller_status.setText(message)

    def _on_error(self, message: str) -> None:
        self.error_banner.setText(message)
        self.error_banner.show()

    def _on_gesture(self, gesture: str) -> None:
        self.tile_gesture.set_value(C.GESTURE_LABELS.get(gesture, gesture))

    def refresh(self) -> None:
        """Reload recent sessions when the page is shown."""
        if self.app.statistics is None:
            self.history_table.hide()
            self.empty_state.show()
            return
        sessions = self.app.statistics.recent(10)
        self.history_table.setRowCount(len(sessions))
        self.empty_state.setVisible(not sessions)
        self.history_table.setVisible(bool(sessions))
        for row, session in enumerate(sessions):
            started = session.started_at.replace("T", " ")[:16] + " UTC"
            values = [
                started,
                _fmt_duration(session.duration_s),
                str(session.clicks),
                str(session.scroll_events),
                f"{session.avg_fps:.0f}",
            ]
            for col, text in enumerate(values):
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.history_table.setItem(row, col, item)
