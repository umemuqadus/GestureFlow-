"""Reusable UI components shared across pages."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSlider,
    QVBoxLayout,
    QWidget,
)


class Card(QFrame):
    """A titled content card."""

    def __init__(self, title: str = "", subtitle: str = "",
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(16, 14, 16, 14)
        self.layout.setSpacing(6)
        self._title = QLabel(title)
        self._title.setObjectName("CardTitle")
        self._subtitle = QLabel(subtitle)
        self._subtitle.setObjectName("CardSubtitle")
        self._subtitle.setWordWrap(True)
        if title:
            self.layout.addWidget(self._title)
        if subtitle:
            self.layout.addWidget(self._subtitle)
        self._body = QVBoxLayout()
        self._body.setSpacing(10)
        self.layout.addLayout(self._body)

    def body(self) -> QVBoxLayout:
        return self._body

    def set_title(self, title: str) -> None:
        self._title.setText(title)

    def set_subtitle(self, subtitle: str) -> None:
        self._subtitle.setText(subtitle)
        self._subtitle.setVisible(bool(subtitle))


class StatTile(QWidget):
    """A single metric: big value with a label above and optional note below."""

    def __init__(self, label: str, value: str = "—",
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.card = Card(parent=None)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.card)
        body = self.card.body()
        body.setSpacing(2)
        self.label = QLabel(label.upper())
        self.label.setObjectName("StatLabel")
        self.value = QLabel(value)
        self.value.setObjectName("StatValue")
        self.note = QLabel("")
        self.note.setObjectName("CardSubtitle")
        body.addWidget(self.label)
        body.addWidget(self.value)
        body.addWidget(self.note)

    def set_value(self, value: str) -> None:
        self.value.setText(value)

    def set_note(self, note: str) -> None:
        self.note.setText(note)
        self.note.setVisible(bool(note))

    def set_value_font_size(self, px: int) -> None:
        font = self.value.font()
        font.setPointSize(px)
        self.value.setFont(font)


class Pill(QLabel):
    """Small status badge."""

    def __init__(self, text: str = "", kind: str = "neutral",
                 parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setObjectName(self._object_name(kind))

    @staticmethod
    def _object_name(kind: str) -> str:
        return {"ok": "PillOk", "warn": "PillWarn", "accent": "PillAccent"}.get(kind, "Pill")

    def set_kind(self, kind: str) -> None:
        self.setObjectName(self._object_name(kind))
        self.style().unpolish(self)
        self.style().polish(self)


class Toggle(QCheckBox):
    """A switch-style checkbox that reports changes as a bool signal."""

    toggled_bool = Signal(bool)

    def __init__(self, checked: bool = False, label: str = "",
                 parent: QWidget | None = None) -> None:
        super().__init__(label, parent)
        self.setChecked(checked)
        self.stateChanged.connect(lambda state: self.toggled_bool.emit(state == Qt.CheckState.Checked.value))

    @property
    def is_checked(self) -> bool:
        return self.isChecked()

    def set_checked(self, checked: bool) -> None:
        self.blockSignals(True)
        self.setChecked(checked)
        self.blockSignals(False)


class SliderRow(QWidget):
    """Label + slider + live value read-out, with optional unit."""

    valueChanged = Signal(float)

    def __init__(
        self,
        label: str,
        minimum: float,
        maximum: float,
        value: float,
        *,
        steps: int = 100,
        decimals: int = 2,
        unit: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._min, self._max = minimum, maximum
        self._decimals = decimals
        self._unit = unit

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        header = QHBoxLayout()
        self._label = QLabel(label)
        self._label.setObjectName("CardTitle")
        self._value_label = QLabel()
        self._value_label.setObjectName("CardSubtitle")
        font = QFont()
        font.setBold(True)
        self._value_label.setFont(font)
        header.addWidget(self._label)
        header.addStretch(1)
        header.addWidget(self._value_label)
        layout.addLayout(header)

        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.setRange(0, steps)
        layout.addWidget(self._slider)

        self._slider.valueChanged.connect(self._on_internal_change)
        self.set_value(value)

    def _to_slider(self, value: float) -> int:
        fraction = (value - self._min) / (self._max - self._min)
        return int(round(fraction * self._slider.maximum()))

    def _from_slider(self, position: int) -> float:
        fraction = position / max(1, self._slider.maximum())
        return self._min + fraction * (self._max - self._min)

    def _on_internal_change(self, position: int) -> None:
        value = self._from_slider(position)
        self._value_label.setText(f"{value:.{self._decimals}f}{self._unit}")
        self.valueChanged.emit(value)

    def value(self) -> float:
        return self._from_slider(self._slider.value())

    def set_value(self, value: float) -> None:
        self._slider.blockSignals(True)
        self._slider.setValue(self._to_slider(value))
        self._value_label.setText(f"{value:.{self._decimals}f}{self._unit}")
        self._slider.blockSignals(False)


def hbox(*widgets: QWidget, stretch_last: bool = True) -> QHBoxLayout:
    layout = QHBoxLayout()
    for widget in widgets:
        layout.addWidget(widget)
    if stretch_last:
        layout.addStretch(1)
    return layout


def vbox(*widgets: QWidget, spacing: int = 10) -> QVBoxLayout:
    layout = QVBoxLayout()
    layout.setSpacing(spacing)
    for widget in widgets:
        layout.addWidget(widget)
    return layout


class EmptyState(QWidget):
    """Placeholder shown when a list has no content."""

    def __init__(self, title: str, detail: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_label = QLabel(title)
        title_label.setObjectName("SectionTitle")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        detail_label = QLabel(detail)
        detail_label.setObjectName("CardSubtitle")
        detail_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        detail_label.setWordWrap(True)
        layout.addWidget(title_label)
        if detail:
            layout.addWidget(detail_label)


def metric_grid(*tiles: StatTile, columns: int = 4) -> QGridLayout:
    """Lay out stat tiles in a responsive grid."""
    grid = QGridLayout()
    grid.setSpacing(12)
    for index, tile in enumerate(tiles):
        row, col = divmod(index, columns)
        grid.addWidget(tile, row, col)
        grid.setColumnStretch(col, 1)
    return grid


class ScrollContainer(QScrollArea):
    """Vertically scrolling page body with a stretchy content column."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._content = QWidget()
        self._content.setObjectName("Root")
        self._layout = QVBoxLayout(self._content)
        self._layout.setContentsMargins(24, 22, 24, 22)
        self._layout.setSpacing(14)
        self.setWidget(self._content)

    def content_layout(self) -> QVBoxLayout:
        return self._layout

    def add_widget(self, widget: QWidget) -> None:
        self._layout.addWidget(widget)

    def add_layout(self, layout) -> None:
        self._layout.addLayout(layout)

    def add_stretch(self) -> None:
        self._layout.addStretch(1)
