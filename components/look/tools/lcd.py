#!/usr/bin/env python3
"""Renders the plasma ball as an animation for the OMEN cooler LCD.

    python3 lcd.py            (writes ../files/theme/omen-lights)

OmenRGB-Controller plays any theme's `omen-lights/` folder on the LCD while
Batocera is in its menus: LCD-ready frames (480x480 JPEG) plus a `frame_ms`
file. This script builds that folder from the same layers the theme uses on
screen, moving the way theme.xml moves them, with the EmuBox name across the ball.

The loop is 24 seconds long. Every motion below is fitted to a whole number
of turns or pulses in that time, so the last frame flows into the first.
"""

import math
import shutil
from pathlib import Path

from PIL import Image

import brand

HERE = Path(__file__).resolve().parent
ART = HERE.parent / "files" / "theme" / "art"
OUT = HERE.parent / "files" / "theme" / "omen-lights"

LCD = 480  # the screen is 480x480 (and round)
BALL = 280  # diameter of the orb on the LCD (the claw round it reaches 1.64 times that)
FPS = 10
LOOP_S = 24
JPEG_QUALITY = 82
MAX_BYTES = 60000  # the LCD's limit for one frame

# name, size relative to the shell, turns per loop (+ = clockwise),
# (scale from, scale to, seconds per pulse), (opacity from, to, seconds per pulse)
LAYERS = [
    ("plasma_glow", 1.793, 0, (1.06, 0.94, 8), (1.0, 0.65, 6)),
    ("plasma_outer", 1.0, 1, (1.06, 0.94, 12), None),
    ("plasma_mid", 1.0, -1, (1.06, 0.93, 8), None),
    ("plasma_core", 1.0, 2, (1.05, 0.95, 6), None),
    ("plasma_spot", 1.0, -3, None, (1.0, 0.35, 4.8)),
    ("shell", 1.0, 0, None, None),
    ("rings_a", 1.638, 0, None, None),          # the claw, in front of the orb's edge
]
# The rings sit where theme.xml leaves them after its opening turn.
RESTING_ANGLE = {"rings_a": 90}


def pulse(start: float, end: float, period: float, t: float) -> float:
    """Glide from `start` to `end` and back, once every `period` seconds."""
    return start + (end - start) * (0.5 - 0.5 * math.cos(2 * math.pi * t / period))


def load(name: str, relative_size: float) -> Image.Image:
    size = round(BALL * relative_size)
    return Image.open(ART / f"{name}.png").convert("RGBA").resize((size, size), Image.LANCZOS)


def main() -> None:
    backdrop = Image.open(ART / "bg_system.jpg").convert("RGB")
    side = min(backdrop.size)
    left, top = (backdrop.width - side) // 2, (backdrop.height - side) // 2
    backdrop = backdrop.crop((left, top, left + side, top + side)).resize((LCD, LCD), Image.LANCZOS)
    backdrop = Image.eval(backdrop, lambda v: v * 55 // 100)  # dimmed, so the ball stands out

    layers = [(name, load(name, size), turns, scale, opacity)
              for name, size, turns, scale, opacity in LAYERS]
    name_text, name_behind = brand.wordmark(LCD, LCD, 42)   # inside the round screen with room to spare

    shutil.rmtree(OUT, ignore_errors=True)
    OUT.mkdir()
    total = FPS * LOOP_S
    biggest = 0
    for index in range(total):
        t = index / FPS
        frame = backdrop.convert("RGBA")
        for name, image, turns, scale, opacity in layers:
            angle = RESTING_ANGLE.get(name, 0) + 360 * turns * t / LOOP_S
            if angle:
                image = image.rotate(-angle, Image.BICUBIC)  # PIL turns anticlockwise
            if scale:
                size = round(image.width * pulse(*scale, t))
                image = image.resize((size, size), Image.BICUBIC)
            if opacity:
                level = pulse(*opacity, t)
                image.putalpha(image.getchannel("A").point(lambda a, level=level: round(a * level)))
            corner = ((LCD - image.width) // 2, (LCD - image.height) // 2)
            frame.alpha_composite(image, corner) if min(corner) >= 0 else frame.paste(
                image, corner, image)
        glow = pulse(0.75, 1.0, 6, t)   # the name breathes a little with the ball
        behind = name_behind.copy()
        behind.putalpha(behind.getchannel("A").point(lambda a, glow=glow: round(a * glow)))
        frame.alpha_composite(behind)
        frame.alpha_composite(name_text)
        path = OUT / f"{index:03d}.jpg"
        frame.convert("RGB").save(path, "JPEG", quality=JPEG_QUALITY)
        biggest = max(biggest, path.stat().st_size)
    (OUT / "frame_ms").write_text(f"{1000 // FPS}\n")
    print(f"{total} frames in {OUT}, largest {biggest} bytes (limit {MAX_BYTES})")
    if biggest > MAX_BYTES:
        raise SystemExit("A frame is too big for the LCD; lower JPEG_QUALITY.")


if __name__ == "__main__":
    main()
