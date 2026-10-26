"""Live end-to-end verification on a REAL webcam.

Runs the actual ControllerEngine (camera -> MediaPipe -> classify -> state
machine -> mouse) for a fixed duration.  By default all mouse actions are
RECORDED, not executed, so your real cursor is untouched while you watch the
pipeline work.  Pass --real-mouse to actually drive the cursor (same as the app).

Modes
-----
  Headless (default): runs N seconds, prints a real measured summary.
  --preview:          opens a live window with landmarks + gesture HUD so you
                      can hold up your hand and watch it track.

Usage
-----
  python scripts/live_verify.py                 # 12s, records actions only
  python scripts/live_verify.py --seconds 20 --preview
  python scripts/live_verify.py --real-mouse    # actually control the cursor
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

# Allow running from the repo root without installing the package.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cv2  # noqa: E402
from PySide6.QtCore import QCoreApplication, QTimer  # noqa: E402

from app import constants as C  # noqa: E402
from app.config import AppConfig  # noqa: E402
from controller.engine import ControllerEngine  # noqa: E402
from controller.mouse_controller import MouseController  # noqa: E402
from controller.safety_manager import SafetyManager  # noqa: E402
from gestures.gesture_config import default_rules  # noqa: E402
from vision.hand_tracker import model_available  # noqa: E402


class RecordingBackend:
    """Stands in for PyAutoGUI: records actions, never touches the OS cursor."""

    FAILSAFE = True
    PAUSE = 0.0

    def __init__(self, width: int = 1920, height: int = 1080) -> None:
        self.calls: list[tuple] = []
        self._pos = (0, 0)
        self._size = (width, height)

    def moveTo(self, x, y, _pause=False):  # noqa: N802 - mirrors pyautogui
        self.calls.append(("moveTo", int(x), int(y)))
        self._pos = (int(x), int(y))

    def click(self, button="left", _pause=False):
        self.calls.append(("click", button))

    def doubleClick(self, _pause=False):  # noqa: N802
        self.calls.append(("doubleClick",))

    def mouseDown(self, button="left", _pause=False):  # noqa: N802
        self.calls.append(("mouseDown", button))

    def mouseUp(self, button="left", _pause=False):  # noqa: N802
        self.calls.append(("mouseUp", button))

    def scroll(self, amount, _pause=False):
        self.calls.append(("scroll", int(amount)))

    def hscroll(self, amount, _pause=False):  # noqa: N802
        self.calls.append(("hscroll", int(amount)))

    def size(self):
        class _S:
            width = self._size[0]
            height = self._size[1]
        return _S()

    def position(self):
        class _P:
            x = self._pos[0]
            y = self._pos[1]
        return _P()


class RecordingSystem:
    """Stands in for SystemController: records system actions, never fires them.

    Keeps the diagnostic fully side-effect free — no screenshots are written,
    volume/brightness are untouched, and no media keys are sent.
    """

    def __init__(self) -> None:
        self.calls: list[str] = []
        self._level = 50  # pretend brightness, so up/down steps are observable

    def screenshot(self):
        self.calls.append("screenshot")
        return None

    def volume_up(self):
        self.calls.append("volume_up")

    def volume_down(self):
        self.calls.append("volume_down")

    def volume_mute(self):
        self.calls.append("volume_mute")

    def media_toggle(self):
        self.calls.append("media_toggle")

    def brightness_up(self, amount: int = 5) -> bool:
        self.calls.append("brightness_up")
        self._level = min(100, self._level + amount)
        return True

    def brightness_down(self, amount: int = 5) -> bool:
        self.calls.append("brightness_down")
        self._level = max(0, self._level - amount)
        return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Live webcam end-to-end verification.")
    parser.add_argument("--seconds", type=int, default=12, help="How long to run.")
    parser.add_argument("--index", type=int, default=None, help="Camera index override.")
    parser.add_argument("--preview", action="store_true", help="Show a live annotated window.")
    parser.add_argument("--real-mouse", action="store_true",
                        help="Actually move the real cursor (default: record only).")
    args = parser.parse_args()

    ok, detail = model_available()
    if not ok:
        print(f"ERROR: {detail}")
        return 1

    qapp = QCoreApplication.instance() or QCoreApplication([])

    config = AppConfig()
    if args.index is not None:
        config.camera.device_index = args.index
    rules = default_rules(config.gestures)

    if args.real_mouse:
        backend = None  # MouseController will import the real pyautogui
        print("REAL MOUSE: the controller will actually move your cursor.")
    else:
        backend = RecordingBackend()
        print("SAFE MODE: mouse actions are recorded only; your cursor is untouched.")

    # System actions (screenshot/volume/brightness/media) are ALWAYS recorded,
    # never executed, so the diagnostic has zero side effects on your machine.
    recording_system = RecordingSystem()

    mouse = MouseController(failsafe=config.safety.pyautogui_failsafe, backend=backend)
    safety = SafetyManager(mouse, config.safety)
    engine = ControllerEngine(config, mouse, safety, rules, system=recording_system)

    gesture_counts: Counter[str] = Counter()
    state_counts: Counter[str] = Counter()
    hands_frames = {"seen": 0, "total": 0}
    last_metrics = {"snapshot": None}
    errors: list[str] = []

    def on_gesture(g: str) -> None:
        gesture_counts[g] += 1

    def on_state(s: str) -> None:
        state_counts[s] += 1

    def on_metrics(snap) -> None:
        last_metrics["snapshot"] = snap
        hands_frames["total"] += 1
        if snap.hands_detected:
            hands_frames["seen"] += 1

    def on_error(msg: str) -> None:
        errors.append(msg)

    def on_frame(frame) -> None:
        if args.preview:
            cv2.imshow("GestureFlow live verification (q to stop)", frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                engine.request_stop()

    engine.gesture_changed.connect(on_gesture)
    engine.state_changed.connect(on_state)
    engine.metrics_ready.connect(on_metrics)
    engine.error_occurred.connect(on_error)
    engine.frame_ready.connect(on_frame)

    QTimer.singleShot(args.seconds * 1000, engine.request_stop)
    engine.start()
    engine.finished.connect(qapp.quit)
    qapp.exec()
    engine.wait(5000)
    cv2.destroyAllWindows()

    print("\n" + "=" * 56)
    print("LIVE VERIFICATION SUMMARY (real webcam, real MediaPipe)")
    print("=" * 56)
    if errors:
        for msg in errors:
            print(f"  ERROR: {msg}")
        return 2

    snap = last_metrics["snapshot"]
    if snap is None:
        print("  No metrics were produced (engine may have exited immediately).")
        return 2

    print(f"  Duration:            {args.seconds}s requested")
    print(f"  Frames processed:    {snap.frames_processed}")
    print(f"  Measured FPS:        {snap.fps:.1f}")
    lat = getattr(snap, "latency_ms", None)
    if lat:
        print(f"  Avg latency:         {lat:.1f} ms")
    print(f"  Frames with a hand:  {hands_frames['seen']}/{hands_frames['total']}")
    if hands_frames["seen"] == 0:
        print("    -> no hand was seen. Hold your hand up to the camera ~50-70cm away,")
        print("       palm facing it, well lit, and re-run with --preview.")
    print(f"  Gesture frames:      {dict(gesture_counts)}")
    print(f"  States seen:         {dict(state_counts)}")

    if backend is not None:
        clicks = [c for c in backend.calls if c[0] in ("click", "doubleClick")]
        drags = [c for c in backend.calls if c[0] == "mouseDown"]
        scrolls = [c for c in backend.calls if c[0] in ("scroll", "hscroll")]
        moves = [c for c in backend.calls if c[0] == "moveTo"]
        print(f"  Cursor moves:        {len(moves)}")
        print(f"  Clicks:              {len(clicks)} {clicks[:8]}")
        print(f"  Drag starts:         {len(drags)}")
        print(f"  Scroll events:       {len(scrolls)}")
        if scrolls:
            vals = [c[1] for c in scrolls]
            print(f"    scroll values:     {vals[:16]}{' ...' if len(vals) > 16 else ''}")

    sys_calls = recording_system.calls
    if sys_calls:
        tally: Counter[str] = Counter(sys_calls)
        print("  System actions (recorded, not fired):")
        for name, n in tally.most_common():
            print(f"    {name:<16} x{n}")
    else:
        print("  System actions:      none recorded")
    print("=" * 56)
    if hands_frames["seen"] == 0:
        print("RESULT: pipeline ran with no errors, but no hand was in view.")
        return 3
    print("RESULT: OK - real camera + MediaPipe produced live hand tracking.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
