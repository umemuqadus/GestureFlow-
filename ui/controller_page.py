"""Live Controller page: real webcam preview with landmarks and controls."""

from __future__ import annotations

import numpy as np
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app import constants as C
from app.application import Application
from ui.components import Card, Pill, SliderRow, Toggle

try:
    import cv2
except ImportError:  # pragma: no cover - dependency is required at runtime
    cv2 = None  # type: ignore[assignment]


class ClickableLabel(QLabel):
    """A label that reports mouse press/release (used for focus-loss pause)."""

    clicked = Signal()

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt API name
        self.clicked.emit()
        super().mousePressEvent(event)


class ControllerPage(QWidget):
    """Shows the live feed and the primary run controls."""

    def __init__(self, app: Application, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.app = app
        self._last_frame: np.ndarray | None = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(14)

        # -- left: preview ---------------------------------------------------
        left = QVBoxLayout()
        left.setSpacing(10)
        title = QLabel("Live Controller")
        title.setObjectName("PageTitle")
        left.addWidget(title)

        self.preview = ClickableLabel("Press Start Controller to begin")
        self.preview.setMinimumSize(640, 360)
        self.preview.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setStyleSheet(
            "background: #101528; border: 1px solid #282F4C; border-radius: 14px; color: #9AA2C7;"
        )
        left.addWidget(self.preview, stretch=1)

        strip = QLabel("Ready")
        strip.setObjectName("StatusStrip")
        strip.setWordWrap(True)
        strip.setStyleSheet("padding: 8px 12px;")
        left.addWidget(strip)
        self.status_strip = strip
        layout.addLayout(left, stretch=3)

        # -- right: controls -------------------------------------------------
        right = QVBoxLayout()
        right.setSpacing(12)
        right.setContentsMargins(0, 0, 0, 0)
        right_widget = QWidget()
        right_widget.setFixedWidth(320)
        right_widget.setLayout(right)
        layout.addWidget(right_widget, stretch=1)

        controls = Card("Controls")
        buttons = QVBoxLayout()
        buttons.setSpacing(8)
        self.start_btn = QPushButton("Start Controller")
        self.start_btn.setObjectName("PrimaryButton")
        self.stop_btn = QPushButton("Stop")
        self.stop_btn.setEnabled(False)
        self.pause_btn = QPushButton("Pause / Resume")
        self.pause_btn.setEnabled(False)
        self.emergency_btn = QPushButton("Emergency Stop")
        self.emergency_btn.setObjectName("DangerButton")
        for button in (self.start_btn, self.stop_btn, self.pause_btn, self.emergency_btn):
            buttons.addWidget(button)
        controls.body().addLayout(buttons)
        self.status_pill = Pill("Idle", "neutral")
        controls.body().addWidget(self.status_pill)
        right.addWidget(controls)

        camera_card = Card("Camera")
        cam_row = QHBoxLayout()
        cam_row.addWidget(QLabel("Device"))
        self.camera_combo = QComboBox()
        cam_row.addWidget(self.camera_combo)
        camera_card.body().addLayout(cam_row)
        self.refresh_btn = QPushButton("Refresh cameras")
        self.refresh_btn.setObjectName("GhostButton")
        camera_card.body().addWidget(self.refresh_btn)
        right.addWidget(camera_card)

        tune = Card("Feel")
        self.sensitivity = SliderRow("Cursor sensitivity", 0.1, 3.0, 1.0, decimals=2, unit="x")
        self.smoothing = SliderRow("Smoothing", 0.0, 0.95, 0.55, decimals=2)
        self.show_landmarks = Toggle(True, "Show hand landmarks")
        tune.body().addWidget(self.sensitivity)
        tune.body().addWidget(self.smoothing)
        tune.body().addWidget(self.show_landmarks)
        right.addWidget(tune)

        info = Card("Status")
        self.gesture_label = QLabel("Gesture: —")
        self.fps_label = QLabel("FPS: —")
        self.conf_label = QLabel("Confidence: —")
        for label in (self.gesture_label, self.fps_label, self.conf_label):
            label.setObjectName("CardSubtitle")
            info.body().addWidget(label)
        right.addWidget(info)
        right.addStretch(1)

        # -- wiring ----------------------------------------------------------
        self.start_btn.clicked.connect(self.app.start_controller)
        self.stop_btn.clicked.connect(self.app.stop_controller)
        self.pause_btn.clicked.connect(self.app.toggle_pause)
        self.emergency_btn.clicked.connect(lambda: self.app.emergency_stop("controller page"))
        self.refresh_btn.clicked.connect(self._populate_cameras)
        self.camera_combo.currentIndexChanged.connect(self._on_camera_changed)
        self.sensitivity.valueChanged.connect(self._on_sensitivity)
        self.smoothing.valueChanged.connect(self._on_smoothing)
        self.show_landmarks.toggled_bool.connect(self._on_show_landmarks)

        self.app.frame_updated.connect(self._on_frame)
        self.app.metrics_updated.connect(self._on_metrics)
        self.app.controller_started.connect(self._on_started)
        self.app.controller_stopped.connect(self._on_stopped)
        self.app.status_changed.connect(self._on_status)
        self.app.error.connect(self._on_error)
        self.app.paused_changed.connect(self._on_paused)
        self.app.gesture_changed.connect(self._on_gesture)
        self.preview.clicked.connect(lambda: self.preview.setFocus())

        self._load_initial_values()
        self._on_stopped()

    # -- initial load ---------------------------------------------------------
    def _load_initial_values(self) -> None:
        cfg = self.app.config
        self.sensitivity.set_value(cfg.cursor.speed)
        self.smoothing.set_value(cfg.cursor.smoothing)
        self.show_landmarks.set_checked(cfg.ui.show_landmarks)
        self._populate_cameras()

    # -- camera list ----------------------------------------------------------
    def _populate_cameras(self) -> None:
        self.camera_combo.blockSignals(True)
        self.camera_combo.clear()
        try:
            from vision.camera_manager import camera_names, list_cameras

            indices = list_cameras()
            if not indices:
                self.camera_combo.addItem("No camera detected", -1)
            else:
                names = camera_names(indices)
                for index in indices:
                    self.camera_combo.addItem(names.get(index, f"Camera {index}"), index)
                current = self.app.config.camera.device_index
                pos = self.camera_combo.findData(current)
                if pos >= 0:
                    self.camera_combo.setCurrentIndex(pos)
        except Exception as exc:  # noqa: BLE001 - surface, don't crash the UI
            self.camera_combo.addItem(f"Scan failed: {exc}", -1)
        self.camera_combo.blockSignals(False)

    def _on_camera_changed(self, index: int) -> None:
        device = self.camera_combo.itemData(index)
        if not isinstance(device, int) or device < 0:
            return
        self.app.settings.update(camera={"device_index": device})

    def _on_sensitivity(self, value: float) -> None:
        self.app.settings.update(cursor={"speed": round(value, 3)})

    def _on_smoothing(self, value: float) -> None:
        self.app.settings.update(cursor={"smoothing": round(value, 3)})

    def _on_show_landmarks(self, checked: bool) -> None:
        self.app.settings.update(ui={"show_landmarks": checked})

    # -- slots ----------------------------------------------------------------
    def _on_started(self) -> None:
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.pause_btn.setEnabled(True)
        self.status_pill.setText("Running")
        self.status_pill.set_kind("ok")
        self.status_strip.setText("Controller running — show your hand to the camera.")

    def _on_stopped(self) -> None:
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.pause_btn.setEnabled(False)
        self.status_pill.setText("Idle")
        self.status_pill.set_kind("neutral")
        self.status_strip.setText("Controller stopped.")
        self.preview.setText("Press Start Controller to begin")
        self.preview.setPixmap(QPixmap())
        self.gesture_label.setText("Gesture: —")
        self.fps_label.setText("FPS: —")
        self.conf_label.setText("Confidence: —")

    def _on_paused(self, paused: bool) -> None:
        if not self.app.is_running:
            return
        self.status_pill.setText("Paused" if paused else "Running")
        self.status_pill.set_kind("warn" if paused else "ok")
        self.pause_btn.setText("Resume" if paused else "Pause")
        self.status_strip.setText(
            "Paused — mouse control suspended. Press Resume or hold an open palm."
            if paused else "Controller running — show your hand to the camera."
        )

    def _on_status(self, message: str) -> None:
        self.status_strip.setText(message)

    def _on_error(self, message: str) -> None:
        self.status_strip.setText(f"Error: {message}")

    def _on_gesture(self, gesture: str) -> None:
        self.gesture_label.setText(f"Gesture: {C.GESTURE_LABELS.get(gesture, gesture)}")

    def _on_metrics(self, snapshot) -> None:
        self.fps_label.setText(f"FPS: {snapshot.fps:.0f}")
        self.conf_label.setText(f"Confidence: {snapshot.tracking_confidence:.2f}")
        if snapshot.gesture:
            self.gesture_label.setText(
                f"Gesture: {C.GESTURE_LABELS.get(snapshot.gesture, snapshot.gesture)}"
            )

    def _on_frame(self, frame) -> None:
        """Convert one BGR frame to a pixmap and display it."""
        if cv2 is None or frame is None:
            return
        self._last_frame = frame
        try:
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        except Exception:  # noqa: BLE001 - never let a preview error stop the loop
            return
        h, w, ch = rgb.shape
        image = QImage(rgb.data, w, h, ch * w, QImage.Format.Format_RGB888)
        pixmap = QPixmap.fromImage(image)
        scaled = pixmap.scaled(
            self.preview.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.preview.setPixmap(scaled)
