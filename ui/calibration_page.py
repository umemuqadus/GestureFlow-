"""Calibration page: a guided flow that tunes the controller to the user."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app import constants as C
from app.application import Application
from ui.components import Card, Pill, SliderRow, Toggle


class CalibrationPage(QWidget):
    """Step-by-step calibration with live gesture feedback."""

    def __init__(self, app: Application, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.app = app
        self._step = 0

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(14)

        header = QHBoxLayout()
        title_box = QVBoxLayout()
        title = QLabel("Calibration")
        title.setObjectName("PageTitle")
        subtitle = QLabel("Follow the steps to match the controller to your hand and screen.")
        subtitle.setObjectName("CardSubtitle")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        header.addLayout(title_box)
        header.addStretch(1)
        self.run_pill = Pill("Controller stopped", "neutral")
        header.addWidget(self.run_pill)
        layout.addLayout(header)

        # -- live feedback strip --------------------------------------------
        feedback = QFrame()
        feedback.setObjectName("StatusStrip")
        feedback_layout = QHBoxLayout(feedback)
        feedback_layout.setContentsMargins(14, 10, 14, 10)
        feedback_layout.addWidget(QLabel("Live gesture:"))
        self.gesture_label = QLabel("—")
        self.gesture_label.setObjectName("SectionTitle")
        feedback_layout.addWidget(self.gesture_label)
        feedback_layout.addStretch(1)
        feedback_layout.addWidget(QLabel("Pinch distance:"))
        self.pinch_label = QLabel("—")
        self.pinch_label.setObjectName("CardSubtitle")
        feedback_layout.addWidget(self.pinch_label)
        self.start_hint = QLabel("Start the controller to test gestures.")
        self.start_hint.setObjectName("CardSubtitle")
        feedback_layout.addWidget(self.start_hint)
        layout.addWidget(feedback)

        # -- step area --------------------------------------------------------
        self.step_card = Card()
        self.step_body = QVBoxLayout()
        self.step_body.setSpacing(10)
        self.step_card.body().addLayout(self.step_body)
        layout.addWidget(self.step_card, stretch=1)

        # -- navigation -------------------------------------------------------
        nav = QHBoxLayout()
        self.back_btn = QPushButton("Back")
        self.next_btn = QPushButton("Next")
        self.next_btn.setObjectName("PrimaryButton")
        self.save_btn = QPushButton("Save calibration")
        self.save_btn.setObjectName("PrimaryButton")
        self.save_btn.hide()
        self.step_label = QLabel()
        self.step_label.setObjectName("CardSubtitle")
        nav.addWidget(self.back_btn)
        nav.addWidget(self.next_btn)
        nav.addWidget(self.save_btn)
        nav.addStretch(1)
        nav.addWidget(self.step_label)
        layout.addLayout(nav)

        # -- controls (built once, shown per step) -----------------------------
        self.camera_combo = QComboBox()
        self.refresh_cameras_btn = QPushButton("Refresh cameras")
        self.refresh_cameras_btn.setObjectName("GhostButton")

        self.roi_slider = SliderRow("Active tracking region", 0.3, 1.0, 0.62, decimals=2)
        self.invert_x = Toggle(False, "Invert horizontal movement")
        self.invert_y = Toggle(False, "Invert vertical movement")

        self.speed_slider = SliderRow("Cursor speed", 0.1, 3.0, 1.0, decimals=2, unit="x")
        self.smoothing_slider = SliderRow("Smoothing", 0.0, 0.95, 0.55, decimals=2)
        self.test_area = QLabel("Move your index finger — the cursor should follow.")
        self.test_area.setObjectName("CardSubtitle")
        self.test_area.setWordWrap(True)
        self.test_area.setMinimumHeight(90)
        self.test_area.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.test_area.setStyleSheet(
            "background: rgba(91,108,255,0.06); border: 1px dashed rgba(91,108,255,0.35);"
            " border-radius: 10px;"
        )

        self.pinch_slider = SliderRow("Pinch sensitivity (threshold)", 0.05, 0.8, 0.32, decimals=2)
        self.drag_hold_slider = SliderRow("Drag hold time", 0, 1200, 320, decimals=0, unit=" ms")
        self.click_test = QLabel("Pinch thumb + index together once to test a left click.")
        self.click_test.setObjectName("CardSubtitle")
        self.click_test.setWordWrap(True)
        self.click_count_label = QLabel("Clicks this session: 0")
        self.click_count_label.setObjectName("CardSubtitle")

        self.scroll_slider = SliderRow("Scroll sensitivity", 0.1, 5.0, 1.0, decimals=2)
        self.scroll_test = QLabel("Raise index + middle fingers, then move your hand up/down.")
        self.scroll_test.setObjectName("CardSubtitle")
        self.scroll_test.setWordWrap(True)

        self.pause_slider = SliderRow("Pause hold duration", 200, 3000, 900, decimals=0, unit=" ms")

        self.back_btn.clicked.connect(self._back)
        self.next_btn.clicked.connect(self._next)
        self.save_btn.clicked.connect(self._save)
        self.refresh_cameras_btn.clicked.connect(self._populate_cameras)

        self.roi_slider.valueChanged.connect(
            lambda v: self.app.settings.update(cursor={"roi_fraction": round(v, 3)}))
        self.invert_x.toggled_bool.connect(
            lambda v: self.app.settings.update(cursor={"invert_x": v}))
        self.invert_y.toggled_bool.connect(
            lambda v: self.app.settings.update(cursor={"invert_y": v}))
        self.speed_slider.valueChanged.connect(
            lambda v: self.app.settings.update(cursor={"speed": round(v, 3)}))
        self.smoothing_slider.valueChanged.connect(
            lambda v: self.app.settings.update(cursor={"smoothing": round(v, 3)}))
        self.pinch_slider.valueChanged.connect(self._on_pinch_threshold)
        self.drag_hold_slider.valueChanged.connect(
            lambda v: self.app.settings.update(gestures={"drag_hold_ms": int(v)}))
        self.scroll_slider.valueChanged.connect(
            lambda v: self.app.settings.update(gestures={"scroll_sensitivity": round(v, 3)}))
        self.pause_slider.valueChanged.connect(
            lambda v: self.app.settings.update(gestures={"pause_hold_ms": int(v)}))
        self.camera_combo.currentIndexChanged.connect(self._on_camera_changed)

        self.app.gesture_changed.connect(self._on_gesture)
        self.app.metrics_updated.connect(self._on_metrics)
        self.app.controller_started.connect(self._on_controller_started)
        self.app.controller_stopped.connect(self._on_controller_stopped)

        self._load_values()
        self._populate_cameras()
        self._render_step()

    # -- steps ------------------------------------------------------------------
    @property
    def steps(self) -> list[tuple[str, list[QWidget]]]:
        return [
            ("Choose the camera you want to use.",
             [self.camera_combo, self.refresh_cameras_btn]),
            ("Adjust the active region. A smaller region means a shorter hand motion "
             "covers the whole screen. Move your index finger to the edges to check.",
             [self.roi_slider, self.invert_x, self.invert_y]),
            ("Set cursor speed and smoothing, then move your index finger inside the "
             "dashed area. Aim for stable tracking without jitter.",
             [self.speed_slider, self.smoothing_slider, self.test_area]),
            ("Set pinch sensitivity. Pinch thumb + index once: the box below reports "
             "your live pinch distance so you can place the threshold just above it.",
             [self.pinch_slider, self.drag_hold_slider, self.click_test, self.click_count_label]),
            ("Set scroll sensitivity, then raise index + middle fingers and move your "
             "hand vertically.",
             [self.scroll_slider, self.scroll_test]),
            ("Set how long an open palm must be held to pause control.",
             [self.pause_slider]),
        ]

    def _render_step(self) -> None:
        steps = self.steps
        text, widgets = steps[self._step]
        while self.step_body.count():
            item = self.step_body.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
        instruction = QLabel(f"Step {self._step + 1} of {len(steps)}")
        instruction.setObjectName("CardSubtitle")
        detail = QLabel(text)
        detail.setWordWrap(True)
        self.step_card.set_title("Calibration")
        self.step_card.set_subtitle("")
        self.step_body.addWidget(instruction)
        self.step_body.addWidget(detail)
        for widget in widgets:
            self.step_body.addWidget(widget)
        self.step_body.addStretch(1)

        self.step_label.setText(f"{self._step + 1} / {len(steps)}")
        self.back_btn.setEnabled(self._step > 0)
        is_last = self._step == len(steps) - 1
        self.next_btn.setVisible(not is_last)
        self.save_btn.setVisible(is_last)

    def _next(self) -> None:
        if self._step < len(self.steps) - 1:
            self._step += 1
            self._render_step()

    def _back(self) -> None:
        if self._step > 0:
            self._step -= 1
            self._render_step()

    # -- configuration ---------------------------------------------------------
    def _load_values(self) -> None:
        cfg = self.app.config
        self.roi_slider.set_value(cfg.cursor.roi_fraction)
        self.invert_x.set_checked(cfg.cursor.invert_x)
        self.invert_y.set_checked(cfg.cursor.invert_y)
        self.speed_slider.set_value(cfg.cursor.speed)
        self.smoothing_slider.set_value(cfg.cursor.smoothing)
        self.pinch_slider.set_value(cfg.gestures.pinch_threshold)
        self.drag_hold_slider.set_value(cfg.gestures.drag_hold_ms)
        self.scroll_slider.set_value(cfg.gestures.scroll_sensitivity)
        self.pause_slider.set_value(cfg.gestures.pause_hold_ms)

    def _populate_cameras(self) -> None:
        self.camera_combo.blockSignals(True)
        self.camera_combo.clear()
        try:
            from vision.camera_manager import camera_names, list_cameras

            indices = list_cameras()
            if not indices:
                self.camera_combo.addItem("No camera detected", -1)
            else:
                for index in indices:
                    self.camera_combo.addItem(
                        camera_names(indices).get(index, f"Camera {index}"), index)
                pos = self.camera_combo.findData(self.app.config.camera.device_index)
                if pos >= 0:
                    self.camera_combo.setCurrentIndex(pos)
        except Exception as exc:  # noqa: BLE001
            self.camera_combo.addItem(f"Scan failed: {exc}", -1)
        self.camera_combo.blockSignals(False)

    def _on_camera_changed(self, index: int) -> None:
        device = self.camera_combo.itemData(index)
        if isinstance(device, int) and device >= 0:
            self.app.settings.update(camera={"device_index": device})

    def _on_pinch_threshold(self, value: float) -> None:
        # Keep hysteresis valid: release threshold must stay above activation.
        release = max(value + 0.08, self.app.config.gestures.release_threshold)
        self.app.settings.update(
            gestures={"pinch_threshold": round(value, 3), "release_threshold": round(release, 3)}
        )

    def _save(self) -> None:
        if self.app.calibration is None or self.app.profiles is None:
            QMessageBox.warning(self, "Calibration", "Database unavailable; cannot save.")
            return
        name, ok = QtWidgets_input(self)
        if not ok or not name:
            return
        try:
            self.app.calibration.save(name, self.app.profiles.active_profile_id)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Calibration", f"Could not save: {exc}")
            return
        QMessageBox.information(self, "Calibration", f"Saved calibration '{name}'.")

    # -- live feedback ---------------------------------------------------------
    def _on_gesture(self, gesture: str) -> None:
        self.gesture_label.setText(C.GESTURE_LABELS.get(gesture, gesture))

    def _on_metrics(self, snapshot) -> None:
        if snapshot.pinch_distance:
            self.pinch_label.setText(f"{snapshot.pinch_distance:.3f}")
        else:
            self.pinch_label.setText("—")
        if snapshot.clicks:
            self.click_count_label.setText(f"Clicks this session: {snapshot.clicks}")
        if snapshot.state in (C.STATE_SCROLLING,):
            self.scroll_test.setText("Scrolling detected — check the page moves as expected.")

    def _on_controller_started(self) -> None:
        self.run_pill.setText("Controller running")
        self.run_pill.set_kind("ok")
        self.start_hint.setText("Testing live.")

    def _on_controller_stopped(self) -> None:
        self.run_pill.setText("Controller stopped")
        self.run_pill.set_kind("neutral")
        self.start_hint.setText("Start the controller to test gestures.")


def QtWidgets_input(parent: QWidget) -> tuple[str, bool]:
    """Ask for a calibration name without importing QInputDialog at module top."""
    from PySide6.QtWidgets import QInputDialog

    text, ok = QInputDialog.getText(parent, "Save calibration", "Calibration name:")
    return (text.strip(), ok)
