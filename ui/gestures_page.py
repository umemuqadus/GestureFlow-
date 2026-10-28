"""Gesture Mapping page: view and edit what each gesture does.

A single source of truth is used: the live ``AppConfig.gestures`` section.  Edits
here are written through the settings service, which rebuilds the rule set and
hot-applies it to the running engine, so changes take effect immediately.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app import constants as C
from app.application import Application
from ui.components import SliderRow, Toggle


class GestureRow(QFrame):
    """One gesture entry: description, action and its tunable parameters."""

    def __init__(self, name: str, description: str, action: str,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(16)

        info = QVBoxLayout()
        info.setSpacing(2)
        title_row = QHBoxLayout()
        title = QLabel(name)
        title.setObjectName("CardTitle")
        title_row.addWidget(title)
        self.toggle = Toggle(True)
        title_row.addWidget(self.toggle)
        title_row.addStretch(1)
        info.addLayout(title_row)
        desc = QLabel(description)
        desc.setObjectName("CardSubtitle")
        desc.setWordWrap(True)
        info.addWidget(desc)
        self.action_label = QLabel(f"Action: {action}")
        self.action_label.setObjectName("CardSubtitle")
        info.addWidget(self.action_label)
        layout.addLayout(info, stretch=2)

        self.controls = QVBoxLayout()
        self.controls.setSpacing(6)
        layout.addLayout(self.controls, stretch=2)

    def add_control(self, widget: QWidget) -> None:
        self.controls.addWidget(widget)


class GesturesPage(QWidget):
    def __init__(self, app: Application, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.app = app
        self._rows: dict[str, GestureRow] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content = QWidget()
        content.setObjectName("Root")
        body = QVBoxLayout(content)
        body.setContentsMargins(24, 22, 24, 22)
        body.setSpacing(12)

        title = QLabel("Gesture Mapping")
        title.setObjectName("PageTitle")
        body.addWidget(title)
        subtitle = QLabel(
            "Each gesture maps to a mouse action. Thresholds and timings update the "
            "controller immediately; use Save to store them in your profile."
        )
        subtitle.setObjectName("CardSubtitle")
        subtitle.setWordWrap(True)
        body.addWidget(subtitle)

        self.banner = QLabel("")
        self.banner.setObjectName("BannerError")
        self.banner.setWordWrap(True)
        self.banner.hide()
        body.addWidget(self.banner)

        cfg = self.app.config.gestures

        # -- point (cursor move) -------------------------------------------
        point = GestureRow(
            "Point",
            "Extend your index finger (others curled). Maps the fingertip to the cursor.",
            "Move cursor",
        )
        point.toggle.setEnabled(False)  # movement is the core behaviour
        body.addWidget(point)
        self._rows[C.GESTURE_POINT] = point

        # -- pinch / left click ---------------------------------------------
        pinch = GestureRow(
            "Pinch (tap) — Left click",
            "Briefly touch thumb + index, then release: one left click.",
            "Left click",
        )
        self.pinch_threshold = SliderRow("Threshold", 0.05, 0.8,
                                         cfg.pinch_threshold, decimals=2)
        self.release_threshold = SliderRow("Release (hysteresis)", 0.05, 0.95,
                                           cfg.release_threshold, decimals=2)
        self.click_cooldown = SliderRow("Cooldown", 0, 1200, cfg.click_cooldown_ms,
                                        decimals=0, unit=" ms")
        pinch.add_control(self.pinch_threshold)
        pinch.add_control(self.release_threshold)
        pinch.add_control(self.click_cooldown)
        pinch.toggle.set_checked(cfg.enable_left_click)
        body.addWidget(pinch)
        self._rows[C.GESTURE_PINCH] = pinch

        # -- drag --------------------------------------------------------------
        drag = GestureRow(
            "Hold pinch — Drag",
            "Hold the pinch past the drag time: holds the left button while you move, "
            "releases when you let go.",
            "Drag and drop",
        )
        self.drag_hold = SliderRow("Drag hold time", 0, 1500, cfg.drag_hold_ms,
                                   decimals=0, unit=" ms")
        drag.add_control(self.drag_hold)
        drag.toggle.set_checked(cfg.enable_drag)
        body.addWidget(drag)
        self._rows[C.GESTURE_DRAG] = drag

        # -- double click -------------------------------------------------------
        dbl = GestureRow(
            "Two quick pinches — Double click",
            "Two short pinches within the window register a double click.",
            "Double click",
        )
        self.dbl_window = SliderRow("Window", 150, 900, cfg.double_click_window_ms,
                                    decimals=0, unit=" ms")
        dbl.add_control(self.dbl_window)
        dbl.toggle.set_checked(cfg.enable_double_click)
        body.addWidget(dbl)
        self._rows[C.GESTURE_DOUBLE_CLICK] = dbl

        # -- right click ---------------------------------------------------------
        right = GestureRow(
            "Middle pinch — Right click",
            "Touch thumb + middle finger (index stays out) for a right click.",
            "Right click",
        )
        self.right_threshold = SliderRow("Threshold", 0.05, 0.8,
                                         cfg.right_pinch_threshold, decimals=2)
        right.add_control(self.right_threshold)
        right.toggle.set_checked(cfg.enable_right_click)
        body.addWidget(right)
        self._rows[C.GESTURE_RIGHT_CLICK] = right

        # -- scrolling ------------------------------------------------------------
        scroll_v = GestureRow(
            "Two fingers — Vertical scroll",
            "Raise index + middle fingers, then move your hand up/down.",
            "Scroll vertically",
        )
        self.scroll_sens = SliderRow("Sensitivity", 0.1, 5.0, cfg.scroll_sensitivity,
                                     decimals=2)
        self.scroll_deadzone = SliderRow("Dead zone", 0, 80, cfg.scroll_deadzone_px,
                                         decimals=0, unit=" px")
        scroll_v.add_control(self.scroll_sens)
        scroll_v.add_control(self.scroll_deadzone)
        scroll_v.toggle.set_checked(cfg.enable_scroll)
        body.addWidget(scroll_v)
        self._rows[C.GESTURE_SCROLL_V] = scroll_v

        scroll_h = GestureRow(
            "Two fingers sideways — Horizontal scroll",
            "Same two fingers up, hand tilted so movement is mainly horizontal.",
            "Scroll horizontally",
        )
        note = QLabel("Uses the same scroll enable switch and sensitivity.")
        note.setObjectName("CardSubtitle")
        scroll_h.add_control(note)
        scroll_h.toggle.set_checked(cfg.enable_scroll)
        scroll_h.toggle.setEnabled(False)
        body.addWidget(scroll_h)
        self._rows[C.GESTURE_SCROLL_H] = scroll_h

        # -- pause --------------------------------------------------------------
        pause = GestureRow(
            "Open palm — Pause",
            "Hold an open palm for the set time to pause. Hold it again to resume.",
            "Pause control",
        )
        self.pause_hold = SliderRow("Hold to pause", 200, 3000, cfg.pause_hold_ms,
                                    decimals=0, unit=" ms")
        pause.add_control(self.pause_hold)
        pause.toggle.set_checked(cfg.enable_pause)
        body.addWidget(pause)
        self._rows[C.GESTURE_OPEN_PALM] = pause

        # -- system-control gestures ------------------------------------------
        section = QLabel("System control")
        section.setObjectName("CardTitle")
        body.addWidget(section)

        self.system_hold = SliderRow("Hold to trigger (all system gestures)", 0, 1500,
                                     cfg.system_hold_ms, decimals=0, unit=" ms")

        screenshot = GestureRow(
            "Fist — Screenshot",
            "Clench your fist (thumb tucked) to capture the screen. Saved to "
            "%APPDATA%\\GestureFlowAI\\screenshots.",
            "Take screenshot",
        )
        screenshot.toggle.set_checked(cfg.enable_screenshot)
        body.addWidget(screenshot)
        self._rows[C.GESTURE_FIST] = screenshot

        volume = GestureRow(
            "Thumb up / down — Volume",
            "Point your thumb up to raise, down to lower the volume. Keep holding "
            "to repeat.",
            "Volume up / down",
        )
        volume.add_control(self.system_hold)
        volume.toggle.set_checked(cfg.enable_volume)
        body.addWidget(volume)
        self._rows[C.GESTURE_THUMB_UP] = volume

        mute = GestureRow(
            "Thumb + pinky — Mute",
            "Stick out your thumb and pinky to toggle mute.",
            "Mute toggle",
        )
        mute.toggle.set_checked(cfg.enable_volume)
        mute.toggle.setEnabled(False)  # follows the volume switch above
        body.addWidget(mute)
        self._rows[C.GESTURE_SHAKA] = mute

        brightness = GestureRow(
            "Three fingers — Brightness",
            "Raise index + middle + ring (pinky down), then move your hand up or "
            "down. Requires a display that exposes brightness (laptop panels).",
            "Brightness up / down",
        )
        brightness.toggle.set_checked(cfg.enable_brightness)
        body.addWidget(brightness)
        self._rows[C.GESTURE_THREE_FINGERS] = brightness

        media = GestureRow(
            "Flat hand — Play / Pause",
            "Four fingers up with the thumb tucked: toggles media playback.",
            "Play / pause",
        )
        media.toggle.set_checked(cfg.enable_media)
        body.addWidget(media)
        self._rows[C.GESTURE_FLAT_HAND] = media

        # -- actions --------------------------------------------------------------
        actions = QHBoxLayout()
        save_btn = QPushButton("Save to profile")
        save_btn.setObjectName("PrimaryButton")
        reset_btn = QPushButton("Reset to defaults")
        self.validate_label = QLabel("")
        self.validate_label.setObjectName("CardSubtitle")
        actions.addWidget(save_btn)
        actions.addWidget(reset_btn)
        actions.addStretch(1)
        actions.addWidget(self.validate_label)
        body.addLayout(actions)
        body.addStretch(1)
        scroll.setWidget(content)
        layout.addWidget(scroll)

        # -- wiring --------------------------------------------------------------
        self.pinch_threshold.valueChanged.connect(self._on_pinch_threshold)
        self.release_threshold.valueChanged.connect(self._on_release_threshold)
        self.click_cooldown.valueChanged.connect(
            lambda v: self._update(click_cooldown_ms=int(v)))
        self.drag_hold.valueChanged.connect(lambda v: self._update(drag_hold_ms=int(v)))
        self.dbl_window.valueChanged.connect(
            lambda v: self._update(double_click_window_ms=int(v)))
        self.right_threshold.valueChanged.connect(self._on_right_threshold)
        self.scroll_sens.valueChanged.connect(
            lambda v: self._update(scroll_sensitivity=round(v, 3)))
        self.scroll_deadzone.valueChanged.connect(
            lambda v: self._update(scroll_deadzone_px=int(v)))
        self.pause_hold.valueChanged.connect(lambda v: self._update(pause_hold_ms=int(v)))
        self.system_hold.valueChanged.connect(
            lambda v: self._update(system_hold_ms=int(v)))

        pinch.toggle.toggled_bool.connect(lambda v: self._update(enable_left_click=v))
        drag.toggle.toggled_bool.connect(lambda v: self._update(enable_drag=v))
        dbl.toggle.toggled_bool.connect(lambda v: self._update(enable_double_click=v))
        right.toggle.toggled_bool.connect(lambda v: self._update(enable_right_click=v))
        scroll_v.toggle.toggled_bool.connect(self._on_scroll_toggle)
        pause.toggle.toggled_bool.connect(lambda v: self._update(enable_pause=v))
        screenshot.toggle.toggled_bool.connect(
            lambda v: self._update(enable_screenshot=v))
        volume.toggle.toggled_bool.connect(self._on_volume_toggle)
        brightness.toggle.toggled_bool.connect(
            lambda v: self._update(enable_brightness=v))
        media.toggle.toggled_bool.connect(lambda v: self._update(enable_media=v))

        save_btn.clicked.connect(self._save)
        reset_btn.clicked.connect(self._reset)

        self.app.settings.settings_changed.connect(self._on_settings_changed)

    # -- update helpers ---------------------------------------------------------
    def _update(self, **gesture_fields) -> bool:
        return self.app.settings.update(gestures=gesture_fields)

    def _on_pinch_threshold(self, value: float) -> None:
        release = max(value + 0.08, self.release_threshold.value())
        self.release_threshold.set_value(release)
        self._update(pinch_threshold=round(value, 3),
                     release_threshold=round(release, 3))

    def _on_release_threshold(self, value: float) -> None:
        self._update(release_threshold=round(value, 3))

    def _on_right_threshold(self, value: float) -> None:
        self._update(right_pinch_threshold=round(value, 3))

    def _on_scroll_toggle(self, checked: bool) -> None:
        self._rows[C.GESTURE_SCROLL_H].toggle.set_checked(checked)
        self._update(enable_scroll=checked)

    def _on_volume_toggle(self, checked: bool) -> None:
        """Volume and mute share one switch, so mirror it onto the mute row."""
        self._rows[C.GESTURE_SHAKA].toggle.set_checked(checked)
        self._update(enable_volume=checked)

    def _on_settings_changed(self, config) -> None:
        """Reflect external settings changes (e.g. from Calibration) back."""
        cfg = config.gestures
        for control, value in (
            (self.pinch_threshold, cfg.pinch_threshold),
            (self.release_threshold, cfg.release_threshold),
            (self.click_cooldown, cfg.click_cooldown_ms),
            (self.drag_hold, cfg.drag_hold_ms),
            (self.dbl_window, cfg.double_click_window_ms),
            (self.right_threshold, cfg.right_pinch_threshold),
            (self.scroll_sens, cfg.scroll_sensitivity),
            (self.scroll_deadzone, cfg.scroll_deadzone_px),
            (self.pause_hold, cfg.pause_hold_ms),
            (self.system_hold, cfg.system_hold_ms),
        ):
            control.set_value(value)
        self._rows[C.GESTURE_PINCH].toggle.set_checked(cfg.enable_left_click)
        self._rows[C.GESTURE_DRAG].toggle.set_checked(cfg.enable_drag)
        self._rows[C.GESTURE_DOUBLE_CLICK].toggle.set_checked(cfg.enable_double_click)
        self._rows[C.GESTURE_RIGHT_CLICK].toggle.set_checked(cfg.enable_right_click)
        self._rows[C.GESTURE_SCROLL_V].toggle.set_checked(cfg.enable_scroll)
        self._rows[C.GESTURE_OPEN_PALM].toggle.set_checked(cfg.enable_pause)
        self._rows[C.GESTURE_FIST].toggle.set_checked(cfg.enable_screenshot)
        self._rows[C.GESTURE_THUMB_UP].toggle.set_checked(cfg.enable_volume)
        self._rows[C.GESTURE_SHAKA].toggle.set_checked(cfg.enable_volume)
        self._rows[C.GESTURE_THREE_FINGERS].toggle.set_checked(cfg.enable_brightness)
        self._rows[C.GESTURE_FLAT_HAND].toggle.set_checked(cfg.enable_media)

    # -- persistence --------------------------------------------------------------
    def _save(self) -> None:
        problems = self.app.validate_rules()
        if problems:
            self.banner.setText("Fix before saving: " + " ".join(problems))
            self.banner.show()
            return
        self.banner.hide()
        if self.app.db is None or self.app.profiles is None:
            QMessageBox.warning(self, "Gesture Mapping", "Database unavailable.")
            return
        from database.repositories import GestureMappingRepository

        repo = GestureMappingRepository(self.app.db)
        payload = {
            gid: {
                "action": rule.action,
                "enabled": rule.enabled,
                "threshold": rule.threshold,
                "hold_ms": rule.hold_ms,
                "cooldown_ms": rule.cooldown_ms,
            }
            for gid, rule in self.app.rules.items()
        }
        try:
            repo.save(self.app.profiles.active_profile_id, payload)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Gesture Mapping", f"Could not save: {exc}")
            return
        self.validate_label.setText("Saved to profile.")
        QMessageBox.information(self, "Gesture Mapping", "Mappings saved to your profile.")

    def _reset(self) -> None:
        if QMessageBox.question(
            self, "Reset gestures",
            "Reset all gesture mappings to defaults?",
        ) != QMessageBox.StandardButton.Yes:
            return
        self.app.settings.reset_to_defaults()
        self.validate_label.setText("Reset to defaults.")
