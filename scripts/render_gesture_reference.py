"""Render reference images for every gesture, from the app's own geometry.

Reuses the synthetic 21-landmark poses in ``tests/conftest.py`` (the exact
geometry the classifier is tested against) and draws each one with MediaPipe's
standard hand topology.  Output: one PNG per gesture plus a contact sheet, into
``docs/gestures/``.  Fully offline — no webcam, no network.

Run:  python scripts/render_gesture_reference.py
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from conftest import (  # noqa: E402  (path setup above)
    fist,
    flat_hand_pose,
    open_palm,
    pinch,
    point,
    right_pinch,
    scroll_vertical,
    shaka_pose,
    three_fingers_pose,
    thumb_down_pose,
    thumb_up_pose,
)

# MediaPipe HAND_CONNECTIONS (palm + digits).
CONNECTIONS = [
    (0, 1), (1, 2), (2, 3), (3, 4),        # thumb
    (0, 5), (5, 6), (6, 7), (7, 8),        # index
    (5, 9), (9, 10), (10, 11), (11, 12),   # middle
    (9, 13), (13, 14), (14, 15), (15, 16), # ring
    (13, 17), (17, 18), (18, 19), (19, 20),# pinky
    (0, 17), (0, 5),                       # palm
]
FINGERTIPS = {4, 8, 12, 16, 20}

# (label, action, pose) — order matches the README gesture reference.
POSES = [
    ("Point", "Move cursor", point()),
    ("Pinch (tap)", "Left click", pinch(0.05)),
    ("Middle pinch", "Right click", right_pinch(0.05)),
    ("Two fingers up", "Scroll (vertical)", scroll_vertical()),
    ("Open palm", "Pause", open_palm()),
    ("Fist", "Screenshot", fist()),
    ("Thumb up", "Volume up", thumb_up_pose()),
    ("Thumb down", "Volume down", thumb_down_pose()),
    ("Thumb + pinky", "Mute", shaka_pose()),
    ("Three fingers up", "Brightness", three_fingers_pose()),
    ("Flat hand", "Play / pause", flat_hand_pose()),
]

BG = (18, 22, 30)
BONE = (90, 200, 250)
JOINT = (230, 240, 250)
TIP = (255, 190, 60)
TEXT = (235, 240, 245)
SUB = (150, 165, 185)


def _font(size: int) -> ImageFont.FreeTypeFont:
    for name in ("segoeui.ttf", "arial.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def render_hand(obs, size: int = 440) -> Image.Image:
    """Draw one 21-landmark hand, antialiased via 3x supersampling."""
    S = 3  # supersample factor
    pad = int(0.10 * size * S)
    span = size * S - 2 * pad
    img = Image.new("RGB", (size * S, size * S), BG)
    d = ImageDraw.Draw(img)

    def xy(i: int) -> tuple[int, int]:
        x, y, _ = obs.landmarks[i]
        # Normalised -> pixels, with a little margin; y already increases downward.
        return (pad + int(x * span), pad + int(y * span))

    for a, b in CONNECTIONS:
        d.line([xy(a), xy(b)], fill=BONE, width=int(4 * S))
    for i in range(21):
        x, y = xy(i)
        r = int((9 if i in FINGERTIPS else 6) * S)
        color = TIP if i in FINGERTIPS else JOINT
        d.ellipse([x - r, y - r, x + r, y + r], fill=color)

    return img.resize((size, size), Image.LANCZOS)


def label_bar(title: str, action: str, width: int, height: int = 92) -> Image.Image:
    img = Image.new("RGB", (width, height), BG)
    d = ImageDraw.Draw(img)
    d.text((width // 2, 26), title, font=_font(30), fill=TEXT, anchor="mm")
    d.text((width // 2, 62), action, font=_font(24), fill=SUB, anchor="mm")
    return img


def main() -> None:
    out = ROOT / "docs" / "gestures"
    out.mkdir(parents=True, exist_ok=True)

    tile_w, hand_px = 440, 440
    cells = []
    for title, action, obs in POSES:
        hand = render_hand(obs, hand_px)
        card = Image.new("RGB", (tile_w, hand_px + 92), BG)
        card.paste(hand, (0, 0))
        card.paste(label_bar(title, action, tile_w), (0, hand_px))
        card.save(out / f"{title.lower().replace(' ', '_').replace('+', 'and').replace('(', '').replace(')', '')}.png")
        cells.append(card)

    # Contact sheet: 3 columns.
    cols = 3
    rows = (len(cells) + cols - 1) // cols
    gap = 16
    sheet_w = cols * tile_w + (cols + 1) * gap
    sheet_h = rows * (hand_px + 92) + (rows + 1) * gap
    sheet = Image.new("RGB", (sheet_w, sheet_h), (10, 13, 18))
    for idx, cell in enumerate(cells):
        r, c = divmod(idx, cols)
        sheet.paste(cell, (gap + c * (tile_w + gap), gap + r * (hand_px + 92 + gap)))
    sheet.save(out / "all_gestures.png")

    print(f"Wrote {len(cells)} gesture images + contact sheet to {out}")


if __name__ == "__main__":
    main()
