#!/usr/bin/env python3
"""Draws the start-up film: a dark chamber lit by a waking plasma, which flares into the EmuBox name.

    python3 splash.py [output.mp4]      (default: ../files/splash/emubox.mp4)
    python3 splash.py --sound my.wav output.mp4      the same film with a sound of your own
                                        (16-bit WAV; cut or padded to the film's length)

Batocera plays an .mp4 found in /userdata/splash while it starts. Everything in the film is
made here: the pictures are drawn below (the chamber and the plasma are original shapes) and the sound is
synthesised with the recipes' building blocks in sounds.py. Nothing is taken from any console.
Needs Pillow and GStreamer (gst-launch-1.0 with x264enc, mp4mux and an AAC encoder).
"""
import math
import random
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter

import brand
import sounds

HERE = Path(__file__).resolve().parent
W, H, FPS, SECONDS = 1280, 720, 30, 5.4
WAKE, FLARE, FADE = 0.25, 2.6, 4.8  # seconds: the plasma starts to glow, flares into the name, everything fades
LAND = FLARE + 0.3                  # the name is there (the sound's chord lands with it)


def ease(x: float) -> float:
    x = max(0.0, min(1.0, x))
    return 1 - (1 - x) ** 3


def faded(image: Image.Image, alpha: float) -> Image.Image:
    if alpha >= 0.999:
        return image
    out = image.copy()
    out.putalpha(out.getchannel("A").point(lambda v: int(v * max(0.0, alpha))))
    return out


def name_picture() -> tuple[Image.Image, Image.Image]:
    """The name, and a soft glow of it to sit behind."""
    return brand.wordmark(W, H, 96, 14)


def chamber() -> tuple[Image.Image, Image.Image]:
    """The room the plasma wakes in, as if lit only by it: dark machinery around a central space.
    Gives the room and a mask of where its surfaces face the light (for their bright rims).
    Original shapes: ribbed pillars, a ring overhead, a cradle below, tubes in front."""
    s = 2; w, h = W * s, H * s; cx = w // 2
    body = Image.new("L", (w, h), 0); d = ImageDraw.Draw(body)
    rim = Image.new("L", (w, h), 0); r = ImageDraw.Draw(rim)
    for side in (-1, 1):                                             # two ribbed pillars each side, bowing in
        for k, (x0, bend, thick) in enumerate(((0.30, 0.09, 54), (0.42, 0.05, 34))):
            pts = []
            for i in range(41):
                v = i / 40
                x = cx + side * w * (x0 - bend * math.sin(v * math.pi))
                pts.append((x, h * (-0.05 + 1.1 * v)))
            d.line(pts, fill=150 - 40 * k, width=thick * s)
            inner = [(x - side * thick * s * 0.42, y) for x, y in pts]
            r.line(inner, fill=255 - 60 * k, width=3 * s)
            for i in range(3, 38, 5):                                # bands round the pillar
                x, y = pts[i]
                d.ellipse((x - thick * s * 0.62, y - 9 * s, x + thick * s * 0.62, y + 9 * s), fill=175 - 40 * k)
                r.arc((x - thick * s * 0.62, y - 9 * s, x + thick * s * 0.62, y + 9 * s), 200, 340, fill=220, width=2 * s)
    for k, (rx, ry, y) in enumerate(((0.20, 0.07, 0.06), (0.15, 0.05, 0.10), (0.10, 0.034, 0.135))):   # the ring overhead
        box = (cx - w * rx, h * y - h * ry, cx + w * rx, h * y + h * ry)
        d.ellipse(box, outline=170 - 30 * k, width=(16 - 4 * k) * s)
        r.arc(box, 20, 160, fill=255, width=3 * s)
    for i in range(12):                                              # small lamps round it
        a = i / 12 * 2 * math.pi
        x, y = cx + math.cos(a) * w * 0.15, h * 0.10 + math.sin(a) * h * 0.05
        d.ellipse((x - 7 * s, y - 7 * s, x + 7 * s, y + 7 * s), fill=210)
    for k, (rx, ry, y) in enumerate(((0.17, 0.05, 0.86), (0.23, 0.07, 0.90))):   # the cradle below
        box = (cx - w * rx, h * y - h * ry, cx + w * rx, h * y + h * ry)
        d.ellipse(box, outline=160, width=(14 + 6 * k) * s)
        r.arc(box, 190, 350, fill=255, width=3 * s)
    for x in (-0.13, 0.0, 0.13):                                     # posts on the cradle
        d.rectangle((cx + w * x - 6 * s, h * 0.76, cx + w * x + 6 * s, h * 0.86), fill=150)
    for k, (x, y, rr) in enumerate(((0.14, 1.02, 0.17), (0.86, 1.04, 0.19), (0.30, 1.10, 0.14), (0.70, 1.12, 0.15))):
        box = (w * x - w * rr, h * y - h * rr * 1.2, w * x + w * rr, h * y + h * rr * 1.2)   # tubes in the foreground
        d.ellipse(box, outline=60, width=int(w * 0.035))
        r.arc(box, 220, 320, fill=140, width=3 * s)
    body = body.resize((W, H), Image.LANCZOS).filter(ImageFilter.GaussianBlur(1.2))
    rim = rim.resize((W, H), Image.LANCZOS).filter(ImageFilter.GaussianBlur(1))
    return body, rim


def blob_mask(t: float, size: float, seed: int, wobble: float) -> Image.Image:
    """The plasma's outline at time t: a disc whose edge heaves in slow, overlapping waves."""
    rnd = random.Random(seed)
    waves = [(k, rnd.uniform(0.4, 1.0) * wobble / k ** 0.8, rnd.uniform(0.6, 1.9) * rnd.choice((-1, 1)), rnd.uniform(0, 6.3))
             for k in range(2, 7)]
    n = 720
    pts = []
    for i in range(n):
        a = i / n * 2 * math.pi
        r = size * (1 + sum(amp * math.sin(k * a + speed * t + phase) for k, amp, speed, phase in waves))
        pts.append((W / 2 + r * math.cos(a), H * 0.48 + r * math.sin(a) * 0.92))
    mask = Image.new("L", (W, H), 0)
    ImageDraw.Draw(mask).polygon(pts, fill=255)
    return mask


def frames(folder: Path) -> int:
    room, rims = chamber()
    text, behind = name_picture()
    fog = Image.effect_noise((W // 16, H // 16), 60).resize((W, H), Image.BICUBIC).filter(ImageFilter.GaussianBlur(30))
    count = int(SECONDS * FPS)
    for n in range(count):
        t = n / FPS
        light = ease((t - 0.25) / (FLARE - 0.25)) * (0.92 + 0.08 * math.sin(t * 23) * math.sin(t * 7))   # with a flicker
        size = 14 + 90 * ease((t - 0.2) / (FLARE - 0.2))
        frame = Image.new("RGB", (W, H), (0, 0, 0))
        if light > 0:
            # The room: its surfaces lit by the plasma, brighter near it, with a haze in the air.
            near = Image.radial_gradient("L").resize((int(W * 1.6), int(W * 1.6))).crop(
                (int(W * 0.3), int(W * 0.8 - H * 0.48), int(W * 0.3) + W, int(W * 0.8 - H * 0.48) + H))
            # Light falls off fast away from the plasma: the far corners stay in shadow.
            reach = ImageChops.invert(near).point(lambda v, l=light: int(255 * min(1.0, (v / 255) ** 2.2 * (0.15 + 1.1 * l))))
            lit = ImageChops.multiply(room, reach).point(lambda v: int(v * 0.8))
            frame.paste(Image.new("RGB", (W, H), (40, 170, 30)), mask=lit)
            frame.paste(Image.new("RGB", (W, H), (160, 255, 110)), mask=ImageChops.multiply(rims, reach.point(lambda v, l=light: int(v * l))))
            haze = ImageChops.multiply(fog, reach).point(lambda v, l=light: int(v * 0.9 * l))
            frame.paste(Image.new("RGB", (W, H), (40, 150, 25)), mask=haze)
            # The plasma: a wide green glow, a heaving body, and a white-hot heart.
            glow = blob_mask(t, size * 2.4, 3, 0.10).filter(ImageFilter.GaussianBlur(size * 0.9 + 10))
            frame.paste(Image.new("RGB", (W, H), (90, 230, 40)), mask=glow.point(lambda v, l=light: int(v * 0.85 * l)))
            body = blob_mask(t, size, 5, 0.16)
            drops = ImageDraw.Draw(body)
            for k in range(3):                                       # droplets thrown off, drifting round it
                a = t * (0.9 + 0.4 * k) + k * 2.1
                x = W / 2 + math.cos(a) * size * (1.45 + 0.3 * k)
                y = H * 0.48 + math.sin(a * 1.3) * size * (1.15 + 0.2 * k)
                rr = max(2, size * (0.13 - 0.025 * k))
                drops.ellipse((x - rr, y - rr, x + rr, y + rr), fill=255)
            bloom = body.filter(ImageFilter.GaussianBlur(size * 0.35 + 6))
            frame.paste(Image.new("RGB", (W, H), (150, 255, 70)), mask=bloom.point(lambda v, l=light: int(v * 0.9 * l)))
            body = body.filter(ImageFilter.GaussianBlur(max(1.5, size * 0.04)))
            frame.paste(Image.new("RGB", (W, H), (200, 255, 130)), mask=body.point(lambda v, l=light: int(v * min(1, 0.6 + l))))
            heart = blob_mask(t * 1.3, size * 0.7, 9, 0.2).filter(ImageFilter.GaussianBlur(max(3, size * 0.16)))
            frame.paste(Image.new("RGB", (W, H), (250, 255, 230)), mask=heart.point(lambda v, l=light: int(v * l)))
        # The flare: the plasma floods the room with light, and the name is there as it clears.
        flare = t - FLARE
        if flare > 0:
            white = max(0.0, 1 - abs(flare - 0.28) / 0.28) if flare < 0.56 else 0.0
            frame = Image.blend(frame, Image.new("RGB", (W, H), (225, 255, 200)), min(1.0, white))
            if flare > 0.3:
                clear = ease((flare - 0.3) / 0.6)
                dark = Image.blend(frame, Image.new("RGB", (W, H), (0, 0, 0)), clear * 0.85).convert("RGBA")
                shown = ease((flare - 0.3) / 0.5)
                for picture, alpha in ((behind, 0.95 * shown), (text, shown)):
                    dark.alpha_composite(faded(picture, alpha))
                frame = dark.convert("RGB")
        if t > FADE:
            frame = Image.blend(frame, Image.new("RGB", (W, H)), ease((t - FADE) / (SECONDS - FADE - 0.1)))
        frame.save(folder / f"f{n:04d}.png", compress_level=1)
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


def own_sound(source: Path, folder: Path) -> None:
    """Someone's own WAV as the film's sound: stereo, 44.1 kHz, the film's length, faded out at the end."""
    import array
    import wave
    with wave.open(str(source), "rb") as wav:
        channels, rate, width = wav.getnchannels(), wav.getframerate(), wav.getsampwidth()
        data = array.array("h")
        data.frombytes(wav.readframes(wav.getnframes()))
    if width != 2:
        raise SystemExit(f"{source}: only 16-bit WAV files can be used")
    left, right = (data[0::2], data[1::2]) if channels == 2 else (data, data)
    total = int(SECONDS * sounds.RATE)
    out = array.array("h", bytes(4 * total))
    fade = int(0.4 * sounds.RATE)
    for i in range(min(total, int(len(left) * sounds.RATE / rate))):
        at = i * rate / sounds.RATE                       # plain linear resampling: fine for a jingle
        j, part = int(at), at - int(at)
        k = min(j + 1, len(left) - 1)
        level = min(1.0, (total - i) / fade)
        out[2 * i] = int((left[j] * (1 - part) + left[k] * part) * level)
        out[2 * i + 1] = int((right[j] * (1 - part) + right[k] * part) * level)
    with wave.open(str(folder / "boot.wav"), "wb") as wav:
        wav.setnchannels(2), wav.setsampwidth(2), wav.setframerate(sounds.RATE)
        wav.writeframes(out.tobytes())


def main() -> int:
    args = sys.argv[1:]
    given = None
    if args[:1] == ["--sound"] and len(args) >= 2:
        given, args = Path(args[1]), args[2:]
    out = Path(args[0]) if args else HERE.parent / "files" / "splash" / "emubox.mp4"
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as temp:
        folder = Path(temp)
        count = frames(folder)
        own_sound(given, folder) if given else sound(folder)
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
