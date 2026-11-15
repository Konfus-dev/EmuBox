#!/usr/bin/env python3
"""Draws the pieces of the pop-up menus: glass panes with clipped corners, in the manner of
early-2000s console dashboards. All of it is drawn here; nothing is copied from any console.

    python3 menu_art.py [theme folder]      (default: ../files/theme)

frame.png            the pane behind a menu (stretched from its corners: a "nine-patch")
button.png / button_filled.png      a menu's buttons, at rest and chosen
The in-game menu (controlcenter/style.css) uses the same pane and buttons.
"""
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

S = 4   # drawn large, then shrunk, for clean edges
LIME, EDGE, DIM = (200, 240, 60), (168, 246, 92), (58, 140, 44)


def clipped(x0, y0, x1, y1, big, small):
    """A box whose top-left and bottom-right corners are cut deep and the other two only nicked."""
    return [(x0 + big, y0), (x1 - small, y0), (x1, y0 + small), (x1, y1 - big),
            (x1 - big, y1), (x0 + small, y1), (x0, y1 - small), (x0, y0 + big)]


def pane(size, big, small, top, bottom, alpha, edge=EDGE, glow=14, inner=True, margin=7):
    n = size * S
    points = [(x * S, y * S) for x, y in clipped(margin, margin, size - margin, size - margin, big, small)]
    mask = Image.new("L", (n, n), 0)
    ImageDraw.Draw(mask).polygon(points, fill=255)
    image = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    # a soft light around the pane, as if its edge were lit
    halo = Image.new("L", (n, n), 0)
    ImageDraw.Draw(halo).line(points + [points[0]], fill=255, width=3 * S, joint="curve")
    halo = halo.filter(ImageFilter.GaussianBlur(glow * S / 4))
    image.paste(Image.new("RGBA", (n, n), (120, 255, 60, 255)), (0, 0), halo.point(lambda v: int(v * 0.75)))
    # the glass: darker towards the bottom, and see-through
    body = Image.new("RGBA", (n, n))
    for y in range(n):
        t = y / (n - 1)
        colour = tuple(int(a + (b - a) * t) for a, b in zip(top, bottom))
        ImageDraw.Draw(body).line([(0, y), (n, y)], fill=colour + (alpha,))
    image.paste(body, (0, 0), mask)
    draw = ImageDraw.Draw(image)
    if inner:   # a second, fainter line just inside the edge
        inset = [(x * S, y * S) for x, y in clipped(margin + 5, margin + 5, size - margin - 5, size - margin - 5,
                                                      max(2, big - 3), max(1, small - 1))]
        draw.line(inset + [inset[0]], fill=DIM + (190,), width=S, joint="curve")
    draw.line(points + [points[0]], fill=edge + (255,), width=2 * S, joint="curve")
    if big >= 12:   # bright ticks across the two deep corners
        for (ax, ay), (bx, by) in ((points[7], points[0]), (points[3], points[4])):
            draw.line([(ax, ay), (bx, by)], fill=(236, 255, 190, 255), width=3 * S)
    return image.resize((size, size), Image.LANCZOS)


def main() -> None:
    theme = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent / "files" / "theme"
    art = theme / "art"
    pane(128, 26, 6, (12, 78, 10), (1, 22, 1), 208).save(art / "frame.png")
    pane(48, 10, 3, (16, 84, 14), (6, 44, 6), 235, edge=(104, 196, 60), glow=6, inner=False, margin=3).save(art / "button.png")
    pane(48, 10, 3, (232, 252, 100), (150, 214, 28), 255, edge=(244, 255, 180), glow=10, inner=False, margin=3).save(art / "button_filled.png")
    print(f"menu art written to {art}")


if __name__ == "__main__":
    main()
