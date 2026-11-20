#!/usr/bin/env python3
"""Draws EmuBox's loading picture: the orb in its holder, the EmuBox name beneath, on black.

    python3 loading.py

It replaces Batocera's logo everywhere one shows while something loads:
- files/boot/boot-logo.png: the very first picture at start-up (before the film). The boot guard
  puts it on the boot partition and /boot/boot-custom.sh shows it instead of Batocera's logo.
- files/theme/art/loading.png: the background of the theme's own loading screen (splash.xml),
  shown when the menus reload, shut down or restart.
Made from the theme's own art (run art.py and the Blender scene first), so it always matches.
"""
from pathlib import Path

from PIL import Image

import brand

HERE = Path(__file__).resolve().parent
ART = HERE.parent / "files" / "theme" / "art"
W, H = 1920, 1080
ORB = 0.40          # the orb's height, as a share of the screen's
CENTRE = (W // 2, int(H * 0.44))


def picture() -> Image.Image:
    out = Image.new("RGBA", (W, H), (0, 0, 0, 255))
    orb = int(H * ORB)
    layers = [("rings_a", 1.638, 1.0), ("plasma_glow", 1.79, 0.7), ("plasma_outer", 1.0, 1.0), ("plasma_mid", 1.0, 1.0),
              ("plasma_core", 1.0, 1.0), ("plasma_spot", 1.0, 1.0), ("shell", 1.0, 1.0)]
    for name, scale, alpha in layers:
        size = int(orb * scale)
        layer = Image.open(ART / f"{name}.png").convert("RGBA").resize((size, size), Image.LANCZOS)
        if alpha < 1:
            layer.putalpha(layer.getchannel("A").point(lambda v, a=alpha: int(v * a)))
        out.alpha_composite(layer, (CENTRE[0] - size // 2, CENTRE[1] - size // 2))
    text, behind = brand.wordmark(W, 160, 64, 10)
    top = CENTRE[1] + int(orb * 0.82)
    out.alpha_composite(behind, (0, top))
    out.alpha_composite(text, (0, top))
    return out.convert("RGB")


def main() -> None:
    image = picture()
    boot = HERE.parent / "files" / "boot"
    boot.mkdir(exist_ok=True)
    image.save(boot / "boot-logo.png", optimize=True)
    image.save(ART / "loading.png", optimize=True)
    print(f"loading picture written to {boot / 'boot-logo.png'} and {ART / 'loading.png'}")


if __name__ == "__main__":
    main()
