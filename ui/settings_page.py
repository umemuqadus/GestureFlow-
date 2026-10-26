"""Settings page: persistent, genuinely effective configuration."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from app.application import Application
from ui.components import SliderRow, Toggle


class SettingsPage(QWidget):
    def __init__(self, app: Application, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.app = app

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

        title = QLabel("Settings")
        title.setObjectName("PageTitle")
        body.addWidget(title)
        subtitle = QLabel("Changes apply immediately and persist per profile.")
        subtitle.setObjectName("CardSubtitle")
        body.addWidget(subtitle)

        self.banner = QLabel("")
        self.banner.setObjectName("BannerError")
        self.banner.setWordWrap(True)
        self.banner.hide()
        body.addWidget(self.banner)

        cfg = self.app.config

        # -- camera -------------------------------------------------------------
        camera = self._section("Camera")
        self.device_combo = QComboBox()
        camera.body().addWidget(self._row("Device", self.device_combo))
        self.refresh_btn = QPushButton("Refresh cameras")
        self.refresh_btn.setObjectName("GhostButton")
        camera.body().addWidget(self.refresh_btn)

        self.resolution_combo = QComboBox()
        for label, res in (
            ("640 x 480", (640, 480)),
            ("1280 x 720", (1280, 720)),
            ("1920 x 1080", (1920, 1080)),
        ):
            self.resolution_combo.addItem(label, res)
        camera.body().addWidget(self._row("Capture resolution", self.resolution_combo))

        self.fps_spin = QSpinBox()
        self.fps_spin.setRange(5, 60)
        self.fps_spin.setValue(cfg.camera.max_fps)
        camera.body().addWidget(self._row("Max FPS", self.fps_spin))

        self.mirror_toggle = Toggle(cfg.camera.mirror_preview, "Mirror preview (selfie view)")
        camera.body().addWidget(self.mirror_toggle)
        self.landmarks_toggle = Toggle(cfg.ui.show_landmarks, "Show hand landmarks overlay")
        camera.body().addWidget(self.landmarks_toggle)
        body.addWidget(camera)

        # -- tracking -------------------------------------------------------------
        tracking = self._section("Hand tracking")
        self.detection_slider = SliderRow("Detection confidence", 0.1, 0.95,
                                          cfg.tracking.detection_confidence, decimals=2)
        self.tracking_slider = SliderRow("Tracking confidence", 0.1, 0.95,
                                         cfg.tracking.tracking_confidence, decimals=2)
        tracking.body().addWidget(self.detection_slider)
        tracking.body().addWidget(self.tracking_slider)
        body.addWidget(tracking)

        # -- cursor ----------------------------------------------------------------
        cursor = self._section("Cursor")
        self.speed_slider = SliderRow("Cursor speed", 0.1, 3.0, cfg.cursor.speed,
                                      decimals=2, unit="x")
        self.smoothing_slider = SliderRow("Smoothing", 0.0, 0.95, cfg.cursor.smoothing,
                                          decimals=2)
        self.roi_slider = SliderRow("Tracking region", 0.3, 1.0, cfg.cursor.roi_fraction,
                                    decimals=2)
        self.deadzone_slider = SliderRow("Movement dead zone", 0.0, 0.05,
                                         cfg.cursor.movement_deadzone, decimals=3)
        self.one_euro_toggle = Toggle(cfg.cursor.use_one_euro, "One Euro filter (adaptive)")
        cursor.body().addWidget(self.speed_slider)
        cursor.body().addWidget(self.smoothing_slider)
        cursor.body().addWidget(self.roi_slider)
        cursor.body().addWidget(self.deadzone_slider)
        cursor.body().addWidget(self.one_euro_toggle)
        body.addWidget(cursor)

        # -- gestures ---------------------------------------------------------------
        gestures = self._section("Gestures")
        self.pinch_slider = SliderRow("Pinch sensitivity", 0.05, 0.8,
                                      cfg.gestures.pinch_threshold, decimals=2)
        self.cooldown_slider = SliderRow("Click cooldown", 0, 1200,
                                         cfg.gestures.click_cooldown_ms, decimals=0, unit=" ms")
        self.hold_slider = SliderRow("Drag hold time", 0, 1500, cfg.gestures.drag_hold_ms,
                                     decimals=0, unit=" ms")
        self.scroll_slider = SliderRow("Scroll sensitivity", 0.1, 5.0,
                                       cfg.gestures.scroll_sensitivity, decimals=2)
        gestures.body().addWidget(self.pinch_slider)
        gestures.body().addWidget(self.cooldown_slider)
        gestures.body().addWidget(self.hold_slider)
        gestures.body().addWidget(self.scroll_slider)
        body.addWidget(gestures)

        # -- safety -------------------------------------------------------------------
        safety = self._section("Safety")
        self.focus_loss_toggle = Toggle(cfg.safety.pause_on_focus_loss,
                                        "Pause when the window loses focus")
        self.failsafe_toggle = Toggle(cfg.safety.pyautogui_failsafe,
                                      "PyAutoGUI failsafe (move to top-left corner to abort)")
        safety.body().addWidget(self.focus_loss_toggle)
        safety.body().addWidget(self.failsafe_toggle)
        hotkeys = QLabel(
            f"Start/stop: {cfg.safety.start_stop_hotkey}   "
            f"Pause: {cfg.safety.pause_hotkey}   "
            f"Emergency stop: {cfg.safety.emergency_stop_hotkey}   "
            f"Calibration: {cfg.safety.calibration_hotkey}   "
            f"Keyboard: {cfg.safety.keyboard_hotkey}   "
            f"Quit: {cfg.safety.quit_hotkey}"
        )
        hotkeys.setObjectName("CardSubtitle")
        hotkeys.setWordWrap(True)
        safety.body().addWidget(hotkeys)
        body.addWidget(safety)

        # -- appearance ----------------------------------------------------------------
        appearance = self._section("Appearance")
        self.theme_combo = QComboBox()
        self.theme_combo.addItem("Light", "light")
        self.theme_combo.addItem("Dark", "dark")
        appearance.body().addWidget(self._row("Theme", self.theme_combo))
        self.start_min_toggle = Toggle(cfg.ui.start_minimized, "Start with window minimized")
        appearance.body().addWidget(self.start_min_toggle)
        body.addWidget(appearance)

        # -- actions --------------------------------------------------------------------
        actions = QHBoxLayout()
        save_btn = QPushButton("Save settings")
        save_btn.setObjectName("PrimaryButton")
        reset_btn = QPushButton("Reset to defaults")
        actions.addWidget(save_btn)
        actions.addWidget(reset_btn)
        actions.addStretch(1)
        body.addLayout(actions)
        body.addStretch(1)

        scroll.setWidget(content)
        layout.addWidget(scroll)

        # -- wiring --------------------------------------------------------------------
        self.refresh_btn.clicked.connect(self._populate_cameras)
        self.device_combo.currentIndexChanged.connect(self._on_device)
        self.resolution_combo.currentIndexChanged.connect(self._on_resolution)
        self.fps_spin.valueChanged.connect(lambda v: self._update(camera={"max_fps": v}))
        self.mirror_toggle.toggled_bool.connect(
            lambda v: self._update(camera={"mirror_preview": v}))
        self.landmarks_toggle.toggled_bool.connect(
            lambda v: self._update(ui={"show_landmarks": v}))
        self.detection_slider.valueChanged.connect(
            lambda v: self._update(tracking={"detection_confidence": round(v, 3)}))
        self.tracking_slider.valueChanged.connect(
            lambda v: self._update(tracking={"tracking_confidence": round(v, 3)}))
        self.speed_slider.valueChanged.connect(lambda v: self._update(cursor={"speed": round(v, 3)}))
        self.smoothing_slider.valueChanged.connect(
            lambda v: self._update(cursor={"smoothing": round(v, 3)}))
        self.roi_slider.valueChanged.connect(
            lambda v: self._update(cursor={"roi_fraction": round(v, 3)}))
        self.deadzone_slider.valueChanged.connect(
            lambda v: self._update(cursor={"movement_deadzone": round(v, 4)}))
        self.one_euro_toggle.toggled_bool.connect(
            lambda v: self._update(cursor={"use_one_euro": v}))
        self.pinch_slider.valueChanged.connect(self._on_pinch)
        self.cooldown_slider.valueChanged.connect(
            lambda v: self._update(gestures={"click_cooldown_ms": int(v)}))
        self.hold_slider.valueChanged.connect(
            lambda v: self._update(gestures={"drag_hold_ms": int(v)}))
        self.scroll_slider.valueChanged.connect(
            lambda v: self._update(gestures={"scroll_sensitivity": round(v, 3)}))
        self.focus_loss_toggle.toggled_bool.connect(
            lambda v: self._update(safety={"pause_on_focus_loss": v}))
        self.failsafe_toggle.toggled_bool.connect(self._on_failsafe)
        self.theme_combo.currentIndexChanged.connect(self._on_theme)
        self.start_min_toggle.toggled_bool.connect(
            lambda v: self._update(ui={"start_minimized": v}))
        save_btn.clicked.connect(self._save)
        reset_btn.clicked.connect(self._reset)

        self._populate_cameras()
        self._load_values()

    # -- helpers ----------------------------------------------------------------------
    def _section(self, title: str):
        from ui.components import Card

        card = Card(title)
        return card

    @staticmethod
    def _row(label: str, widget: QWidget) -> QFrame:
        frame = QFrame()
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(0, 0, 0, 0)
        label_widget = QLabel(label)
        label_widget.setObjectName("CardTitle")
        layout.addWidget(label_widget)
        layout.addStretch(1)
        layout.addWidget(widget)
        return frame

    def _update(self, **sections) -> bool:
        ok = self.app.settings.update(**sections)
        if not ok:
            self.banner.setText("A value was rejected as invalid; check the ranges.")
            self.banner.show()
        else:
            self.banner.hide()
        return ok

    def _populate_cameras(self) -> None:
        self.device_combo.blockSignals(True)
        self.device_combo.clear()
        try:
            from vision.camera_manager import camera_names, list_cameras

            indices = list_cameras()
            if not indices:
                self.device_combo.addItem("No camera detected", -1)
            else:
                for index in indices:
                    self.device_combo.addItem(camera_names(indices).get(index, f"Camera {index}"), index)
                pos = self.device_combo.findData(self.app.config.camera.device_index)
                if pos >= 0:
                    self.device_combo.setCurrentIndex(pos)
        except Exception as exc:  # noqa: BLE001
            self.device_combo.addItem(f"Scan failed: {exc}", -1)
        self.device_combo.blockSignals(False)

    def _load_values(self) -> None:
        cfg = self.app.config
        pos = self.resolution_combo.findData((cfg.camera.width, cfg.camera.height))
        if pos >= 0:
            self.resolution_combo.setCurrentIndex(pos)
        self.fps_spin.setValue(cfg.camera.max_fps)
        self.mirror_toggle.set_checked(cfg.camera.mirror_preview)
        self.landmarks_toggle.set_checked(cfg.ui.show_landmarks)
        self.detection_slider.set_value(cfg.tracking.detection_confidence)
        self.tracking_slider.set_value(cfg.tracking.tracking_confidence)
        self.speed_slider.set_value(cfg.cursor.speed)
        self.smoothing_slider.set_value(cfg.cursor.smoothing)
        self.roi_slider.set_value(cfg.cursor.roi_fraction)
        self.deadzone_slider.set_value(cfg.cursor.movement_deadzone)
        self.one_euro_toggle.set_checked(cfg.cursor.use_one_euro)
        self.pinch_slider.set_value(cfg.gestures.pinch_threshold)
        self.cooldown_slider.set_value(cfg.gestures.click_cooldown_ms)
        self.hold_slider.set_value(cfg.gestures.drag_hold_ms)
        self.scroll_slider.set_value(cfg.gestures.scroll_sensitivity)
        self.focus_loss_toggle.set_checked(cfg.safety.pause_on_focus_loss)
        self.failsafe_toggle.set_checked(cfg.safety.pyautogui_failsafe)
        theme_pos = self.theme_combo.findData(cfg.ui.theme)
        if theme_pos >= 0:
            self.theme_combo.setCurrentIndex(theme_pos)
        self.start_min_toggle.set_checked(cfg.ui.start_minimized)

    # -- change handlers ---------------------------------------------------------------
    def _on_device(self, index: int) -> None:
        device = self.device_combo.itemData(index)
        if isinstance(device, int) and device >= 0:
            self._update(camera={"device_index": device})

    def _on_resolution(self, index: int) -> None:
        res = self.resolution_combo.itemData(index)
        if isinstance(res, tuple) and len(res) == 2:
            self._update(camera={"width": int(res[0]), "height": int(res[1])})

    def _on_pinch(self, value: float) -> None:
        release = max(value + 0.08, self.app.config.gestures.release_threshold)
        self._update(gestures={"pinch_threshold": round(value, 3),
                               "release_threshold": round(release, 3)})

    def _on_failsafe(self, checked: bool) -> None:
        if not checked:
            answer = QMessageBox.question(
                self, "Disable failsafe",
                "Turning off the PyAutoGUI failsafe removes the corner abort. "
                "You can still use the Emergency Stop button and Esc. Continue?",
            )
            if answer != QMessageBox.StandardButton.Yes:
                self.failsafe_toggle.set_checked(True)
                return
        self._update(safety={"pyautogui_failsafe": checked})

    def _on_theme(self, index: int) -> None:
        theme = self.theme_combo.itemData(index)
        if theme in ("light", "dark"):
            self._update(ui={"theme": theme})

    def _save(self) -> None:
        if self.app.settings.save():
            QMessageBox.information(self, "Settings", "Settings saved.")
        else:
            QMessageBox.warning(self, "Settings", "Settings were invalid and not saved.")

    def _reset(self) -> None:
        if QMessageBox.question(self, "Reset", "Reset all settings to defaults?") \
                != QMessageBox.StandardButton.Yes:
            return
        self.app.settings.reset_to_defaults()
        self._load_values()
