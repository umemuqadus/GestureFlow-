"""On-screen virtual keyboard driven by the gesture-controlled OS cursor.

Because the app already moves the *real* Windows cursor (point = move,
pinch = click), the virtual keyboard is simply a window of real buttons: point
at a key and pinch to type.  This requires **no new gesture recognition**.

The single most important behaviour is that the keyboard must never steal
keyboard focus from the application the user is actually typing into.  If it
did, the characters it emits would come straight back to itself.  Three things
guarantee it stays out of the way:

* ``Qt.WindowDoesNotAcceptFocus`` - the window can never become active.
* ``WA_ShowWithoutActivating``    - showing it does not focus it either.
* every key uses ``NoFocus`` policy - clicking a button does not grab focus.

The result: a pinch-click on a key delivers the keystroke to whatever window
the user focused beforehand (Notepad, a browser box, ...).

Shift is a *one-shot* toggle (click Shift, then a letter types its uppercase
form and Shift releases automatically), which is the intuitive model for a
point-and-click keyboard.  The window is frameless and draggable via its title
bar so it can be repositioned with a pinch-drag.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from controller.keyboard_controller import KeyboardController
from ui.theme import Theme

# Fixed key height keeps every row the same size regardless of label length.
_KEY_H = 46
_TITLE_H = 34


@dataclass(frozen=True)
class Key:
    """One key on the virtual keyboard.

    ``kind`` is one of:

    * ``"char"``    - types ``base``, or ``shifted`` when Shift is active.
    * ``"special"`` - presses a named key (``space``, ``enter``, ...).
    * ``"shift"``   - toggles the one-shot Shift state.
    * ``"close"``   - hides the keyboard window.
    """

    label: str
    kind: str = "char"
    base: str = ""
    shifted: str = ""
    special: str = ""
    span: float = 1.0  # relative width within its row


def _char(label: str, base: str, shifted: str = "", span: float = 1.0) -> Key:
    return Key(label=label, kind="char", base=base, shifted=shifted or base, span=span)


def _special(label: str, name: str, span: float = 1.0) -> Key:
    return Key(label=label, kind="special", special=name, span=span)


def _shift(span: float = 1.0) -> Key:
    return Key(label="Shift", kind="shift", span=span)


# (digit, shifted-symbol) pairs for the number row.
_NUMBER_SHIFTS = {
    "1": "!", "2": "@", "3": "#", "4": "$", "5": "%",
    "6": "^", "7": "&", "8": "*", "9": "(", "0": ")",
}


@dataclass
class _KeyRow:
    keys: list[Key] = field(default_factory=list)


def _build_rows() -> list[_KeyRow]:
    """Define the full QWERTY layout as rows of keys."""
    rows: list[_KeyRow] = []

    # Row 1: digits + backspace.
    r1 = [_char(d, d, _NUMBER_SHIFTS[d]) for d in "1234567890"]
    r1.append(_special("\u232B", "backspace", span=2.0))  # ⌫
    rows.append(_KeyRow(r1))

    # Row 2: tab + top letter row + brackets.
    r2 = [_special("Tab", "tab", span=1.5)]
    r2 += [_char(c, c, c.upper()) for c in "qwertyuiop"]
    r2 += [_char("[", "[", "{"), _char("]", "]", "}")]
    rows.append(_KeyRow(r2))

    # Row 3: shift + home row + punctuation + enter.
    r3 = [_shift(span=2.0)]
    r3 += [_char(c, c, c.upper()) for c in "asdfghjkl"]
    r3 += [_char(";", ";", ":"), _char("'", "'", '"')]
    r3.append(_special("Enter", "enter", span=2.0))
    rows.append(_KeyRow(r3))

    # Row 4: shift + bottom letter row + punctuation + right shift.
    # Two shifts (left + right) keep the left/right edges aligned with row 3;
    # both toggle the same one-shot Shift state.
    r4 = [_shift(span=2.0)]
    r4 += [_char(c, c, c.upper()) for c in "zxcvbnm"]
    r4 += [_char(",", ",", "<"), _char(".", ".", ">"), _char("/", "/", "?")]
    r4.append(_shift(span=2.0))
    rows.append(_KeyRow(r4))

    # Row 5: a single full-width space bar (easy to hit with a gesture).
    rows.append(_KeyRow([_special("Space", "space", span=15.0)]))

    return rows


class _TitleBar(QWidget):
    """Draggable strip that also hosts the Shift indicator and Hide button."""

    def __init__(self, keyboard: "VirtualKeyboard") -> None:
        super().__init__(keyboard)
        self._kb = keyboard
        self._drag_offset: QPoint | None = None
        self.setObjectName("VTitleBar")
        self.setFixedHeight(_TITLE_H)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 8, 0)
        layout.setSpacing(8)

        self._title = QLabel("Virtual Keyboard", self)
        self._title.setObjectName("VTitle")
        layout.addWidget(self._title)

        self._shift_badge = QLabel("", self)
        self._shift_badge.setObjectName("VShiftBadge")
        layout.addWidget(self._shift_badge)

        layout.addStretch(1)

        hide = QPushButton("Hide", self)
        hide.setObjectName("VHide")
        hide.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        hide.setCursor(Qt.CursorShape.PointingHandCursor)
        hide.clicked.connect(self._kb.request_hide)
        layout.addWidget(hide)

    def set_shift_active(self, active: bool) -> None:
        self._shift_badge.setText("SHIFT" if active else "")

    # -- dragging (works with the real cursor, including pinch-drag) --------
    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = event.globalPosition().toPoint() - self._kb.frameGeometry().topLeft()
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self._drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self._kb.move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        self._drag_offset = None
        super().mouseReleaseEvent(event)


class VirtualKeyboard(QWidget):
    """Frameless, always-on-top, click-to-type keyboard overlay."""

    #: emitted when the user clicks Hide (so the app can sync its toggle state)
    hidden = Signal()

    def __init__(
        self,
        controller: KeyboardController,
        theme: Theme,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(
            parent,
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowDoesNotAcceptFocus,
        )
        # Never steal focus from the app the user is actually typing into.
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self._controller = controller
        self._theme = theme
        self._shift = False

        self._title_bar = _TitleBar(self)
        self._key_buttons: list[tuple[QPushButton, Key]] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(6)
        root.addWidget(self._title_bar)

        for row in _build_rows():
            root.addWidget(self._build_row(row.keys))

        self._apply_styles()

    # -- construction --------------------------------------------------------
    def _build_row(self, keys: list[Key]) -> QWidget:
        row = QWidget(self)
        row.setObjectName("VRow")
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        for key in keys:
            button = self._make_button(key)
            layout.addWidget(button, stretch=int(key.span * 10))
            self._key_buttons.append((button, key))
        return row

    def _make_button(self, key: Key) -> QPushButton:
        button = QPushButton(self._display_label(key), self)
        button.setObjectName(self._object_name(key))
        # NoFocus is essential: clicking must not move keyboard focus away
        # from the target application.
        button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setFixedHeight(_KEY_H)
        button.clicked.connect(lambda _=False, k=key: self._on_key(k))
        return button

    @staticmethod
    def _display_label(key: Key) -> str:
        if key.kind == "shift":
            return "\u21E7 Shift"  # ⇧
        return key.label

    @staticmethod
    def _object_name(key: Key) -> str:
        if key.kind == "shift":
            return "VKeyShift"
        if key.kind == "special":
            return "VKeyWide" if key.span > 1.0 else "VKey"
        return "VKey"

    # -- key handling --------------------------------------------------------
    def _on_key(self, key: Key) -> None:
        if key.kind == "char":
            char = key.shifted if self._shift else key.base
            self._controller.type_char(char)
            if self._shift:
                # one-shot: release Shift after a character is typed
                self._set_shift(False)
        elif key.kind == "special":
            self._controller.press_key(key.special)
        elif key.kind == "shift":
            self._set_shift(not self._shift)
        elif key.kind == "close":
            self.request_hide()

    def _set_shift(self, on: bool) -> None:
        self._shift = on
        self._title_bar.set_shift_active(on)
        for button, key in self._key_buttons:
            if key.kind == "char":
                label = key.shifted if on else key.base
                button.setText(label)
            elif key.kind == "shift":
                button.setText("\u21E7 Shift" + (" \u25CF" if on else ""))  # ● marks active

    # -- public API ----------------------------------------------------------
    def toggle(self) -> None:
        if self.isVisible():
            self.request_hide()
        else:
            self.show_keyboard()

    def show_keyboard(self) -> None:
        """Show without activating, position near the bottom of the screen."""
        if not self.isVisible():
            self._position_bottom()
            # Reset shift so the keyboard always opens in a known state.
            self._set_shift(False)
        self.show()
        self.raise_()

    def request_hide(self) -> None:
        self.hide()
        self.hidden.emit()

    def apply_theme(self, theme: Theme) -> None:
        self._theme = theme
        self._apply_styles()

    # -- placement -----------------------------------------------------------
    def _position_bottom(self) -> None:
        """Place the keyboard along the bottom-centre of the primary screen."""
        screen = self.screen()
        if screen is None:
            return
        geo = screen.availableGeometry()
        self.adjustSize()
        w, h = self.width(), self.height()
        x = geo.left() + (geo.width() - w) // 2
        y = geo.bottom() - h - 20
        self.move(max(geo.left(), x), max(geo.top(), y))

    # -- styling -------------------------------------------------------------
    def _apply_styles(self) -> None:
        t = self._theme
        self.setStyleSheet(
            f"""
            QWidget#VRow {{ background: transparent; }}
            QWidget#VTitleBar {{ background: {t.header}; border-bottom: 1px solid {t.border};
                                 border-top-left-radius: 12px; border-top-right-radius: 12px; }}
            QLabel#VTitle {{ color: {t.text}; font-weight: 600; background: transparent; }}
            QLabel#VShiftBadge {{ color: {t.accent}; font-weight: 700; background: transparent;
                                  padding: 2px 8px; }}
            QPushButton#VHide {{ background: {t.muted_soft}; color: {t.text}; border: none;
                                 border-radius: 6px; padding: 4px 12px; font-weight: 600; }}
            QPushButton#VHide:hover {{ background: {t.danger_soft}; color: {t.danger}; }}
            QPushButton#VKey, QPushButton#VKeyWide, QPushButton#VKeyShift {{
                background: {t.surface}; color: {t.text};
                border: 1px solid {t.border}; border-radius: 8px;
                font-size: 15px; font-weight: 500;
            }}
            QPushButton#VKey:hover, QPushButton#VKeyWide:hover, QPushButton#VKeyShift:hover {{
                background: {t.hover}; border-color: {t.accent};
            }}
            QPushButton#VKeyShift {{ background: {t.accent_soft}; color: {t.accent};
                                     border-color: {t.accent}; font-weight: 600; }}
            """
        )
        # Round the whole window's top corners are handled per-widget above;
        # give the container itself a surface background with rounded bottom.
        self.setStyleSheet(self.styleSheet() + f"""
            VirtualKeyboard {{ background: {t.surface}; border: 1px solid {t.border};
                               border-radius: 12px; }}
        """)
