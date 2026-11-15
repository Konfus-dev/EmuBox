#!/usr/bin/env python3
"""Draws the start-up film: the theme's plasma orb waking, then the EmuBox name in front of it.

    python3 splash.py [output.mp4]      (default: ../files/splash/emubox.mp4)

Batocera plays an .mp4 found in /userdata/splash while it starts. Everything in the film is
made here: the pictures are the theme's own orb artwork (from art.py) and the sound is
synthesised with the recipes' building blocks in sounds.py. Nothing is taken from any console.
Needs Pillow and GStreamer (gst-launch-1.0 with x264enc, mp4mux and an AAC encoder).
"""
import math
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageChops

import brand
import sounds

HERE = Path(__file__).resolve().parent
ART = HERE.parent / "files" / "theme" / "art"
W, H, FPS, SECONDS = 1280, 720, 30, 5.4
ORB = 430          # the orb's size on screen once it is awake
WAKE, LAND, FADE = 0.35, 2.3, 4.7   # seconds: the orb starts to grow, the name lands, everything fades


def ease(x: float) -> float:
    x = max(0.0, min(1.0, x))
    return 1 - (1 - x) ** 3


def layer(name: str, size: int) -> Image.Image:
    return Image.open(ART / name).convert("RGBA").resize((size, size), Image.LANCZOS)


def faded(image: Image.Image, alpha: float) -> Image.Image:
    if alpha >= 0.999:
        return image
    out = image.copy()
    out.putalpha(out.getchannel("A").point(lambda v: int(v * max(0.0, alpha))))
    return out


def put(frame: Image.Image, image: Image.Image, scale: float = 1.0, turn: float = 0.0, alpha: float = 1.0) -> None:
    if alpha <= 0.003 or scale <= 0.01:
        return
    if turn:
        image = image.rotate(turn, resample=Image.BICUBIC)
    if abs(scale - 1) > 0.002:
        side = max(2, int(image.width * scale))
        image = image.resize((side, side), Image.BILINEAR)
    frame.alpha_composite(faded(image, alpha), ((W - image.width) // 2, (H - image.height) // 2))


def name_picture() -> tuple[Image.Image, Image.Image]:
    """The name, and a soft glow of it to sit behind."""
    return brand.wordmark(W, H, 96, 14)


def frames(folder: Path) -> int:
    big = int(ORB * 1.11)
    art = {name: layer(f"{name}.png", ORB) for name in ("plasma_outer", "plasma_mid", "plasma_core", "plasma_spot", "shell", "plasma_flash")}
    art["plasma_glow"] = layer("plasma_glow.png", int(ORB * 1.75))
    for ring in ("rings_a", "rings_b", "rings_c"):
        art[ring] = layer(f"{ring}.png", int(big * 1.5))
    text, behind = name_picture()
    vignette = Image.radial_gradient("L").resize((W * 2, H * 2)).crop((W // 2, H // 2, W // 2 + W, H // 2 + H))
    count = int(SECONDS * FPS)
    for n in range(count):
        t = n / FPS
        frame = Image.new("RGBA", (W, H), (0, 0, 0, 255))
        awake = ease((t - WAKE) / 1.7)                         # 0: dark, 1: the orb at full size
        breathe = 1 + 0.02 * math.sin(t * 2.2)
        size = (0.04 + 0.96 * awake) * breathe
        if awake > 0:
            wash = Image.new("RGBA", (W, H), (10, 70, 8, 255))  # the room lights up a little, darker at the edges
            wash.putalpha(ImageChops.invert(vignette).point(lambda v: int(v * 0.55 * awake)))
            frame.alpha_composite(wash)
            put(frame, art["plasma_glow"], size, 0, 0.9 * awake)
            rings = ease((t - 1.3) / 1.2)
            put(frame, art["rings_c"], 0.8 + 0.2 * rings, t * 9, 0.75 * rings)
            put(frame, art["rings_b"], 0.85 + 0.15 * rings, -t * 14, 0.85 * rings)
            put(frame, art["rings_a"], 0.9 + 0.1 * rings, t * 22, 0.9 * rings)
            put(frame, art["plasma_outer"], size, t * 16, awake)
            put(frame, art["plasma_mid"], size, -t * 27, awake)
            put(frame, art["plasma_core"], size * (1 + 0.04 * math.sin(t * 5)), t * 41, awake)
            put(frame, art["plasma_spot"], size, t * 60, 0.8 * awake)
            put(frame, art["shell"], size, 0, awake)
        landed = t - LAND
        if landed > -0.05:
            put(frame, art["plasma_flash"], 1.0 + 0.9 * ease(landed / 0.5), 0, max(0.0, 1 - landed / 0.55))
            shown = ease(landed / 0.45)
            grow = 1.12 - 0.12 * shown
            for picture, alpha in ((behind, 0.95 * shown), (text, shown)):
                if grow > 1.002:
                    w, h = int(W * grow), int(H * grow)
                    picture = picture.resize((w, h), Image.BILINEAR).crop(((w - W) // 2, (h - H) // 2, (w - W) // 2 + W, (h - H) // 2 + H))
                frame.alpha_composite(faded(picture, alpha))
        out = frame.convert("RGB")
        if t > FADE:
            out = Image.blend(out, Image.new("RGB", (W, H)), ease((t - FADE) / (SECONDS - FADE - 0.1)))
        out.save(folder / f"f{n:04d}.png", compress_level=1)
    return count


def sound(folder: Path) -> None:
    """A low swell that rises with the orb, a struck chord as the name lands, and a long ring-out."""
    s = sounds.silence(SECONDS)
    rise = LAND - WAKE
    sounds.fm(s, WAKE, rise + 0.3, 38, 98, ratio=1.0, index=2.2, attack=rise * 0.8, decay=3.0, volume=1.0, index_decay=0.6, wobble=(4, 0.012))
    sounds.fm(s, WAKE, rise + 0.3, 57, 147, ratio=2.0, index=1.8, attack=rise * 0.85, decay=3.2, volume=0.5, index_decay=0.7, wobble=(5, 0.01))
    sounds.swept_noise(s, WAKE, rise, 140, 6400, resonance=7, attack=rise * 0.9, decay=6.0, volume=0.85, seed=11)
    sounds.fm(s, LAND, 1.4, 98, 49, ratio=1.0, index=3.0, attack=0.006, decay=3.2, volume=1.0, index_decay=6)          # the thump
    for note, level in ((196, 0.5), (293.7, 0.42), (392, 0.36), (587.3, 0.2), (784, 0.12)):                           # the chord
        sounds.fm(s, LAND, 2.8, note, note, ratio=2.0, index=1.6, attack=0.012, decay=1.25, volume=level, index_decay=2.2, wobble=(5.5, 0.004))
    sounds.fm(s, LAND + 0.02, 1.6, 1568, 1568, ratio=2.76, index=1.4, attack=0.004, decay=3.2, volume=0.1, index_decay=5)  # a glint on top
    sounds.swept_noise(s, LAND, 1.2, 5200, 500, resonance=5, attack=0.01, decay=3.4, volume=0.4, seed=12)
    sounds.save(folder, "boot", s, room=0.55, size=1.35, gain=0.9)


def main() -> int:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE.parent / "files" / "splash" / "emubox.mp4"
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as temp:
        folder = Path(temp)
        count = frames(folder)
        sound(folder)
        subprocess.run([
            "gst-launch-1.0", "-q", "mp4mux", "name=film", "faststart=true", "!", "filesink", f"location={out}",
            "multifilesrc", f"location={folder}/f%04d.png", "index=0", f"stop-index={count - 1}",
            f"caps=image/png,framerate={FPS}/1", "!", "pngdec", "!", "videoconvert", "!", "video/x-raw,format=I420", "!",
            "x264enc", "bitrate=3500", "speed-preset=slow", "key-int-max=30", "!", "video/x-h264,profile=high", "!", "film.",
            "filesrc", f"location={folder}/boot.wav", "!", "wavparse", "!", "audioconvert", "!", "audioresample", "!",
            "avenc_aac", "bitrate=160000", "!", "film.",
        ], check=True)
    print(f"{out}: {out.stat().st_size // 1024} KB, {SECONDS} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
