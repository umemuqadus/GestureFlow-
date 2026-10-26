"""Transient on-screen level indicator for the volume and brightness gestures.

Raising or lowering volume/brightness with a hand gesture is silent by nature:
without feedback you cannot tell whether the gesture was recognised, or where
the level now sits.  This overlay pops a small, frameless, always-on-top card
(a drawn sun or speaker glyph plus a progress bar) at the bottom centre of the
screen and fades it out again — the same idea as Windows' own volume OSD.

It is pure feedback: like :class:`ui.screenshot_overlay.ScreenshotOverlay` it
never steals focus (``Tool`` + ``WA_ShowWithoutActivating``) and it never
touches the system state itself.  The glyphs are painted rather than loaded so
no image assets are needed and both themes render crisply.
"""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QPropertyAnimation, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import (
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QVBoxLayout,
    QWidget,
)

from ui.theme import Theme

_DISPLAY_MS = 1400   # how long the indicator stays fully visible
_FADE_MS = 300       # fade-out duration
_BAR_WIDTH = 220     # width of the level bar
_BAR_HEIGHT = 8      # height of the level bar (also its corner radius * 2)
_ICON_SIZE = 26      # glyph box
_CARD_RADIUS = 16    # card corner radius

KIND_VOLUME = "volume"
KIND_BRIGHTNESS = "brightness"


def _arc(painter: QPainter, cx: float, cy: float, radius: float,
         start_deg: float, end_deg: float, steps: int = 18) -> None:
    """Stroke a circular arc sampled as line segments.

    Sampled explicitly instead of ``QPainter.drawArc`` so the angle convention
    (screen y grows downwards) cannot surprise us across Qt versions.
    """
    points = []
    for i in range(steps + 1):
        angle = math.radians(start_deg + (end_deg - start_deg) * i / steps)
        points.append(QPointF(cx + radius * math.cos(angle),
                              cy + radius * math.sin(angle)))
    for a, b in zip(points, points[1:]):
        painter.drawLine(a, b)


class LevelIcon(QWidget):
    """Hand-drawn glyph: a sun for brightness, a speaker for volume."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(_ICON_SIZE, _ICON_SIZE)
        self._kind = KIND_VOLUME
        self._muted = False
        self._color = QColor("#1B2559")
        self._slash_color = QColor("#E0475B")

    def set_glyph(self, kind: str, muted: bool, color: QColor,
                  slash_color: QColor) -> None:
        self._kind = kind
        self._muted = bool(muted)
        self._color = QColor(color)
        self._slash_color = QColor(slash_color)
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API name
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(self._color, 1.8)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        cx = self.width() / 2.0
        cy = self.height() / 2.0

        if self._kind == KIND_BRIGHTNESS:
            # Outline sun: filled-looking core ring plus eight rays.
            radius = 4.5
            painter.drawEllipse(QPointF(cx, cy), radius, radius)
            inner, outer = radius + 3.0, radius + 6.5
            for step in range(8):
                angle = math.radians(step * 45.0)
                dx, dy = math.cos(angle), math.sin(angle)
                painter.drawLine(QPointF(cx + inner * dx, cy + inner * dy),
                                 QPointF(cx + outer * dx, cy + outer * dy))
        else:
            # Speaker: filled body + cone, then one or two sound waves.
            painter.setBrush(self._color)
            body = QPolygonF([
                QPointF(cx - 9.0, cy - 2.5),
                QPointF(cx - 5.0, cy - 2.5),
                QPointF(cx - 1.0, cy - 6.5),
                QPointF(cx - 1.0, cy + 6.5),
                QPointF(cx - 5.0, cy + 2.5),
                QPointF(cx - 9.0, cy + 2.5),
            ])
            painter.drawPolygon(body)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            if not self._muted:
                _arc(painter, cx - 1.0, cy, 5.0, -55, 55)
                _arc(painter, cx - 1.0, cy, 9.0, -55, 55)
            else:
                pen = QPen(self._slash_color, 2.0)
                pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                painter.setPen(pen)
                painter.drawLine(QPointF(cx - 9.0, cy + 7.0),
                                 QPointF(cx + 8.0, cy - 7.0))
        painter.end()


class LevelBar(QWidget):
    """Rounded progress bar: a soft track with a coloured fill."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(_BAR_WIDTH, _BAR_HEIGHT)
        self._value = 0
        self._fill = QColor("#B7791F")
        self._track = QColor("#E6E8F2")

    def set_level(self, percent: int, fill: str | QColor,
                  track: str | QColor) -> None:
        self._value = max(0, min(100, int(percent)))
        self._fill = QColor(fill)
        self._track = QColor(track)
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API name
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)

        width, height = self.width(), self.height()
        radius = height / 2.0
        painter.setBrush(self._track)
        painter.drawRoundedRect(QRectF(0, 0, width, height), radius, radius)

        if self._value > 0:
            # Keep the minimum width at the bar height so the round cap of a
            # very small fill never inverts.
            fill_width = max(height, width * self._value / 100.0)
            painter.setBrush(self._fill)
            painter.drawRoundedRect(QRectF(0, 0, fill_width, height),
                                    radius, radius)
        painter.end()


class LevelOverlay(QWidget):
    """Shows a fading volume/brightness indicator at the bottom centre."""

    def __init__(self, theme: Theme) -> None:
        super().__init__(
            None,
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool,
        )
        # Feedback only: never steal focus from whatever the user is doing.
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._theme = theme

        self._kind = KIND_VOLUME
        self._level = 0
        self._muted = False

        self._card = QWidget(self)
        self._card.setObjectName("LevelCard")
        row = QHBoxLayout(self._card)
        row.setContentsMargins(22, 14, 28, 14)
        row.setSpacing(16)
        self._icon = LevelIcon(self._card)
        self._bar = LevelBar(self._card)
        row.addWidget(self._icon, 0, Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(self._bar, 0, Qt.AlignmentFlag.AlignVCenter)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(self._card)

        self._apply_styles()

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(30)
        shadow.setOffset(0, 6)
        shadow.setColor(QColor(0, 0, 0, 120))
        self.setGraphicsEffect(shadow)

        self._fade = QPropertyAnimation(self, b"windowOpacity", self)
        self._fade.setDuration(_FADE_MS)
        self._fade.finished.connect(self.hide)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._start_fade)

    # -- styling -------------------------------------------------------------
    def _apply_styles(self) -> None:
        t = self._theme
        self._card.setStyleSheet(
            f"QWidget#LevelCard {{ background-color: {t.surface};"
            f" border: 1px solid {t.border};"
            f" border-radius: {_CARD_RADIUS}px; }}"
        )
        self._refresh()

    def apply_theme(self, theme: Theme) -> None:
        self._theme = theme
        self._apply_styles()

    # -- public API ----------------------------------------------------------
    def show_level(self, kind: str, level: int, muted: bool = False) -> None:
        """Display (or update) the indicator at ``level`` percent."""
        self._kind = kind if kind in (KIND_VOLUME, KIND_BRIGHTNESS) else KIND_VOLUME
        self._level = max(0, min(100, int(level)))
        self._muted = bool(muted)
        self._refresh()

        self._fade.stop()
        self.setWindowOpacity(1.0)
        self._position()
        if not self.isVisible():
            self.show()
        self.raise_()
        self._timer.start(_DISPLAY_MS)

    # -- internals -----------------------------------------------------------
    def _refresh(self) -> None:
        """Recompute glyph/bar colours from the current theme and state."""
        t = self._theme
        if self._kind == KIND_BRIGHTNESS:
            glyph, fill = t.text, t.warn          # amber, as the OS-style OSD
        elif self._muted:
            glyph, fill = t.muted, t.muted        # dimmed while muted
        else:
            glyph, fill = t.text, t.accent
        self._icon.set_glyph(self._kind, self._muted, QColor(glyph),
                             QColor(t.danger))
        self._bar.set_level(self._level, fill, t.muted_soft)

    def _position(self) -> None:
        """Place the indicator at the bottom centre of the active screen."""
        screen = self.screen()
        if screen is None:
            return
        geo = screen.availableGeometry()
        self.adjustSize()
        width, height = self.width(), self.height()
        x = geo.left() + (geo.width() - width) // 2
        y = geo.bottom() - height - 40
        self.move(max(geo.left(), x), max(geo.top(), y))

    def _start_fade(self) -> None:
        self._fade.setStartValue(1.0)
        self._fade.setEndValue(0.0)
        self._fade.start()
