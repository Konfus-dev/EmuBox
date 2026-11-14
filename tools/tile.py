#!/usr/bin/env python3
"""Draw the picture an app shows in the Ports menu: its name on a green tile.

    python3 tools/tile.py "APPLE MUSIC" apps/apple-music/tile.png

Each word goes on its own line. Needs Pillow. Plain text only, no company logos.
"""
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

FONT = Path(__file__).resolve().parent.parent / "components/look/files/fonts/Michroma-Regular.ttf"
SIZE, LINE = 512, 84


def tile(lines: list[str]) -> Image.Image:
    image = Image.new("RGB", (SIZE, SIZE), "#041a04")
    glow = Image.new("RGB", (SIZE, SIZE), "black")
    ImageDraw.Draw(glow).ellipse((96, 96, SIZE - 96, SIZE - 96), fill="#2f7d1e")
    image = Image.blend(image, glow.filter(ImageFilter.GaussianBlur(70)), 0.75)
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((14, 14, SIZE - 14, SIZE - 14), radius=28, outline="#c8f03c", width=5)
    font = ImageFont.truetype(str(FONT), 58)
    top = (SIZE - LINE * len(lines)) / 2
    for i, line in enumerate(lines):
        width = draw.textlength(line, font=font)
        draw.text(((SIZE - width) / 2, top + LINE * i + 6), line, font=font, fill="#d8ff6a")
    return image


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    tile(sys.argv[1].split()).save(sys.argv[2])
