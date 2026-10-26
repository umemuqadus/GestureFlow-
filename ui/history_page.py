"""Session History page: stored summaries from SQLite."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.application import Application
from ui.components import Card, EmptyState


def _fmt_duration(seconds: float) -> str:
    seconds = int(max(0, seconds))
    minutes, secs = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes}m {secs}s" if hours else f"{minutes}m {secs}s"


class HistoryPage(QWidget):
    _COLUMNS = [
        ("Started (UTC)", 160),
        ("Profile", 100),
        ("Duration", 90),
        ("Clicks", 70),
        ("Right", 70),
        ("Double", 70),
        ("Scrolls", 80),
        ("Drags", 70),
        ("Lost track", 90),
        ("Frames", 90),
        ("Avg FPS", 80),
    ]

    def __init__(self, app: Application, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.app = app
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(12)

        header = QHBoxLayout()
        title_box = QVBoxLayout()
        title = QLabel("Session History")
        title.setObjectName("PageTitle")
        subtitle = QLabel("Summaries are stored locally in SQLite. No video is recorded.")
        subtitle.setObjectName("CardSubtitle")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        header.addLayout(title_box)
        header.addStretch(1)
        self.clear_btn = QPushButton("Clear history")
        self.clear_btn.setObjectName("DangerButton")
        header.addWidget(self.clear_btn)
        layout.addLayout(header)

        card = Card("Recorded sessions")
        self.table = QTableWidget(0, len(self._COLUMNS))
        self.table.setHorizontalHeaderLabels([c[0] for c in self._COLUMNS])
        header_view = self.table.horizontalHeader()
        for index, (_, width) in enumerate(self._COLUMNS):
            header_view.resizeSection(index, width)
        header_view.setStretchLastSection(True)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        card.body().addWidget(self.table)
        self.empty_state = EmptyState(
            "No sessions yet",
            "Run the controller and your session summary will be saved here automatically.",
        )
        card.body().addWidget(self.empty_state)
        layout.addWidget(card, stretch=1)

        self.clear_btn.clicked.connect(self._clear)

    def refresh(self) -> None:
        if self.app.statistics is None:
            self.table.hide()
            self.empty_state.show()
            self.clear_btn.setEnabled(False)
            return
        sessions = self.app.statistics.recent(200)
        self.clear_btn.setEnabled(bool(sessions))
        self.empty_state.setVisible(not sessions)
        self.table.setVisible(bool(sessions))
        self.table.setRowCount(len(sessions))
        for row, s in enumerate(sessions):
            values = [
                s.started_at.replace("T", " ")[:19],
                s.profile_name,
                _fmt_duration(s.duration_s),
                str(s.clicks),
                str(s.right_clicks),
                str(s.double_clicks),
                str(s.scroll_events),
                str(s.drag_events),
                str(s.tracking_losses),
                str(s.frames_processed),
                f"{s.avg_fps:.1f}",
            ]
            for col, text in enumerate(values):
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.table.setItem(row, col, item)

    def _clear(self) -> None:
        if self.app.statistics is None:
            return
        answer = QMessageBox.question(
            self, "Clear history",
            "Delete all stored session summaries? This cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.app.statistics.clear()
        self.refresh()
