"""Transient on-screen preview shown after a screenshot gesture fires.

The screenshot is written silently to the app-data folder, so without feedback
a user cannot tell the fist gesture did anything.  This overlay pops a small,
frameless, always-on-top thumbnail of the captured image in the corner of the
primary screen, then fades it out.  It is pure feedback: it never steals focus
(``Tool`` + ``WA_ShowWithoutActivating``) and it never touches the captured file.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPropertyAnimation, QRect, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPalette, QPixmap
from PySide6.QtWidgets import (
    QGraphicsDropShadowEffect,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from ui.theme import Theme

_DISPLAY_MS = 2200   # how long the thumbnail stays fully visible
_FADE_MS = 350       # fade-out duration
_THUMB_WIDTH = 320   # rendered width of the captured thumbnail


class ScreenshotOverlay(QWidget):
    """Shows a fading thumbnail of a just-captured screenshot."""

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

        self._image = QLabel(self)
        self._image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._image.setObjectName("ShotImage")

        self._caption = QLabel("Screenshot saved", self)
        self._caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._caption.setObjectName("ShotCaption")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(8)
        layout.addWidget(self._image)
        layout.addWidget(self._caption)

        self._apply_styles()

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(28)
        shadow.setOffset(0, 6)
        shadow.setColor(QColor(0, 0, 0, 120))
        self.setGraphicsEffect(shadow)

        self._fade = QPropertyAnimation(self, b"windowOpacity", self)
        self._fade.setDuration(_FADE_MS)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._start_fade)
        self._fade.finished.connect(self.hide)

    # -- styling -------------------------------------------------------------
    def _apply_styles(self) -> None:
        t = self._theme
        self._image.setStyleSheet(
            f"QLabel#ShotImage {{ border: 2px solid {t.accent};"
            f" border-radius: 10px; background-color: {t.surface}; }}"
        )
        self._caption.setStyleSheet(
            f"QLabel#ShotCaption {{ color: {t.text};"
            f" background-color: {t.surface};"
            f" border: 1px solid {t.border};"
            f" border-radius: 8px;"
            f" padding: 6px 12px; font-weight: 600; }}"
        )
        font = QFont()
        font.setPointSize(10)
        self._caption.setFont(font)

    # -- public API ----------------------------------------------------------
    def apply_theme(self, theme: Theme) -> None:
        self._theme = theme
        self._apply_styles()

    def show_image(self, path: str) -> None:
        """Display the captured image briefly, then fade out."""
        pixmap = QPixmap(path)
        if pixmap.isNull():
            # The file vanished or is unreadable; skip feedback rather than
            # show an empty box.
            return

        # Constrain to a thumbnail that preserves aspect ratio.
        target_w = _THUMB_WIDTH
        target_h = max(1, int(target_w * pixmap.height() / max(1, pixmap.width())))
        scaled = pixmap.scaled(
            target_w, target_h,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._image.setPixmap(scaled)
        self._image.setFixedSize(scaled.size())

        self._position_near_corner()
        self.setWindowOpacity(1.0)
        self.show()
        self.raise_()
        self._timer.start(_DISPLAY_MS)

    # -- internals -----------------------------------------------------------
    def _position_near_corner(self) -> None:
        """Place the overlay just inside the bottom-right of the primary screen."""
        screen = self.screen()
        if screen is None:
            return
        geo: QRect = screen.availableGeometry()
        self.adjustSize()
        w, h = self.width(), self.height()
        margin = 24
        x = geo.right() - w - margin
        y = geo.bottom() - h - margin
        self.move(max(geo.left(), x), max(geo.top(), y))

    def _start_fade(self) -> None:
        self._fade.setStartValue(1.0)
        self._fade.setEndValue(0.0)
        self._fade.start()
