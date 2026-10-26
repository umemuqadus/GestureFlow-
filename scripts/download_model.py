"""Download the MediaPipe hand-landmark model (explicit one-time setup).

Run this once during installation:

    python scripts/download_model.py

The model is saved to ``assets/models/hand_landmarker.task`` and is then used
entirely offline.  The application NEVER downloads anything at runtime; if the
file is missing the app reports a clear error instead of fetching it.

The model file comes from Google's official MediaPipe model storage and is the
same artifact referenced by the MediaPipe documentation.
"""

from __future__ import annotations

import hashlib
import sys
import urllib.error
import urllib.request
from pathlib import Path

MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/hand_landmarker/"
    "hand_landmarker/float16/latest/hand_landmarker.task"
)

ROOT = Path(__file__).resolve().parent.parent
DEST_DIR = ROOT / "assets" / "models"
DEST = DEST_DIR / "hand_landmarker.task"


def download(url: str = MODEL_URL, dest: Path = DEST, timeout: float = 60.0) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 1024:
        print(f"Model already present: {dest} ({dest.stat().st_size:,} bytes)")
        return dest

    print(f"Downloading hand-landmark model from:\n  {url}")
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            total = response.headers.get("Content-Length")
            chunks: list[bytes] = []
            read = 0
            while True:
                chunk = response.read(64 * 1024)
                if not chunk:
                    break
                chunks.append(chunk)
                read += len(chunk)
                if total:
                    pct = 100 * read / int(total)
                    print(f"\r  {read:,} / {int(total):,} bytes ({pct:5.1f}%)",
                          end="", flush=True)
        data = b"".join(chunks)
    except (urllib.error.URLError, TimeoutError) as exc:
        print(f"\nDownload failed: {exc}", file=sys.stderr)
        print("Check your connection and re-run this script.", file=sys.stderr)
        raise SystemExit(1) from exc

    if len(data) < 1024:
        raise SystemExit("Download produced an implausibly small file; aborting.")

    dest.write_bytes(data)
    digest = hashlib.sha256(data).hexdigest()
    print(f"\nSaved {len(data):,} bytes to {dest}")
    print(f"SHA-256: {digest}")
    return dest


if __name__ == "__main__":
    download()
