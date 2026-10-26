"""Camera diagnostic: probe every OpenCV backend x device index.

Run this when the app says "could not open camera".  It tries each backend
(DSHOW, MSMF, ANY) against indices 0..5, actually reads frames (opening alone
is not proof of a working camera), and reports real measured numbers.

Usage:  python scripts/camera_probe.py
"""

from __future__ import annotations

import sys
import time

import cv2
import numpy as np

BACKENDS = [
    ("MSMF", cv2.CAP_MSMF),
    ("DSHOW", cv2.CAP_DSHOW),
    ("ANY", cv2.CAP_ANY),
]
MAX_INDEX = 6


def probe() -> list[dict]:
    results: list[dict] = []
    for backend_name, backend_id in BACKENDS:
        for index in range(MAX_INDEX):
            cap = cv2.VideoCapture(index, backend_id)
            if not cap.isOpened():
                cap.release()
                continue
            # Opening succeeded; now prove we can actually read frames.
            frames = []
            t0 = time.perf_counter()
            for _ in range(15):
                ok, frame = cap.read()
                if ok and frame is not None:
                    frames.append(frame)
                else:
                    time.sleep(0.02)
            elapsed = time.perf_counter() - t0
            cap.release()
            if not frames:
                results.append({
                    "backend": backend_name, "index": index,
                    "opens": True, "reads": 0, "note": "OPENS BUT CANNOT READ (busy? no signal?)",
                })
                continue
            f = frames[0]
            mean = float(np.mean(f))
            std = float(np.std(f))
            fps = len(frames) / max(elapsed, 1e-3)
            note = "OK"
            if std < 2.0:
                note = "FLAT/BLACK FRAME (lens covered or muted by OS)"
            elif mean < 8.0:
                note = "VERY DARK FRAME"
            results.append({
                "backend": backend_name, "index": index,
                "opens": True, "reads": len(frames),
                "size": f"{f.shape[1]}x{f.shape[0]}",
                "fps": round(fps, 1), "mean": round(mean, 1),
                "std": round(std, 1), "note": note,
            })
    return results


def main() -> int:
    print(f"OpenCV {cv2.__version__}")
    print("Probing backends MSMF / DSHOW / ANY over indices 0..5 ...\n")
    results = probe()
    if not results:
        print("RESULT: NO camera opened on any backend/index.")
        print("\nLikely causes (all software-side, no app bug):")
        print("  - Windows privacy: Settings > Privacy & security > Camera")
        print("      -> 'Allow apps to access your camera' must be ON")
        print("      -> Desktop apps access must be ON")
        print("  - Physical privacy shutter closed, or a hardware mute key (Fn+F__)")
        print("  - Another app (Teams/Zoom/browser) currently holding the camera")
        print("  - Camera driver missing (Device Manager > Cameras / Imaging devices)")
        return 1
    print(f"{'BACKEND':8} {'IDX':3} {'READS':5} {'SIZE':10} {'FPS':5} {'MEAN':6} {'STD':6} NOTE")
    ok_count = 0
    for r in results:
        if r["reads"] == 0:
            print(f"{r['backend']:8} {r['index']:<3} {r['reads']:<5} {'-':10} {'-':5} {'-':6} {'-':6} {r['note']}")
        else:
            print(f"{r['backend']:8} {r['index']:<3} {r['reads']:<5} {r['size']:10} {r['fps']:<5} {r['mean']:<6} {r['std']:<6} {r['note']}")
            if r["note"] == "OK":
                ok_count += 1
    print()
    if ok_count:
        best = next(r for r in results if r["note"] == "OK")
        print(f"RESULT: {ok_count} working configuration(s) found.")
        print(f"RECOMMENDATION: use backend={best['backend']} index={best['index']} "
              f"({best['size']}, measured {best['fps']} fps).")
        return 0
    print("RESULT: cameras opened but none produced a usable frame.")
    return 2


if __name__ == "__main__":
    sys.exit(main())
