#!/usr/bin/env python3
"""Draws the start-up film: backing out of the green tunnel while the plasma wakes, a flare, the
orb in its holder locking in, the EmuBox name beneath, and the tunnel fading away.

    python3 splash.py [output.mp4]      (default: ../files/splash/emubox.mp4)
    python3 splash.py --sound my.wav output.mp4      the same film with a sound of your own
                                        (16-bit WAV; cut or padded to the film's length)

Batocera plays an .mp4 found in /userdata/splash while it starts. Everything in the film is
EmuBox's own: the tunnel is rendered by tools/blender/scene.py ("film"), the orb and holder are
the theme's own art, and the sound is synthesised with the recipes' building blocks in sounds.py.
It ends on exactly the loading picture (tools/loading.py), which the menus' loading screen and
the very first picture at start-up also show, so start-up runs on without a jump or a black gap.
Needs Blender, Pillow and GStreamer (gst-launch-1.0 with x264enc, mp4mux and an AAC encoder).
"""
import math
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image

import brand
import sounds

HERE = Path(__file__).resolve().parent
ART = HERE.parent / "files" / "theme" / "art"
W, H, FPS, SECONDS = 1280, 720, 30, 5.4
WAKE, FLARE, FADE = 0.25, 2.6, 4.8  # seconds: the tunnel starts to light, the plasma flares, everything fades
LAND = FLARE + 0.3                  # the orb is there (the sound's chord lands with it)
ORB = (0.5 * W, 0.44 * H)           # where the loading picture has the orb (tools/loading.py)
ORB_SIZE = 0.40 * H                 # and how big


def ease(x: float) -> float:
    x = max(0.0, min(1.0, x))
    return 1 - (1 - x) ** 3


def faded(image: Image.Image, alpha: float) -> Image.Image:
    if alpha >= 0.999:
        return image
    out = image.copy()
    out.putalpha(out.getchannel("A").point(lambda v: int(v * max(0.0, alpha))))
    return out


def layer(name: str, scale: float) -> Image.Image:
    size = int(ORB_SIZE * scale)
    return Image.open(ART / f"{name}.png").convert("RGBA").resize((size, size), Image.LANCZOS)


def put(frame: Image.Image, image: Image.Image, alpha: float = 1.0, scale: float = 1.0, turn: float = 0.0) -> None:
    """Lays a picture centred on the orb's place, faded, scaled and turned."""
    if alpha <= 0.003:
        return
    if scale != 1.0:
        image = image.resize((max(1, int(image.width * scale)), max(1, int(image.height * scale))), Image.BILINEAR)
    if turn:
        image = image.rotate(turn, resample=Image.BICUBIC)
    frame.alpha_composite(faded(image, alpha), (int(ORB[0] - image.width / 2), int(ORB[1] - image.height / 2)))


def tunnel(folder: Path) -> None:
    """The moving tunnel, one picture per frame (t0000.jpg ...), rendered by Blender."""
    subprocess.run(["blender", "-b", "-P", str(HERE / "blender" / "scene.py"), "--", str(folder), "film"],
                   check=True, stdout=subprocess.DEVNULL)


def frames(folder: Path) -> int:
    tunnel(folder)
    holder = layer("rings_a", 1.638)
    glow = layer("plasma_glow", 1.79)
    orb = [layer(name, 1.0) for name in ("plasma_outer", "plasma_mid", "plasma_core", "plasma_spot", "shell")]
    text, behind = brand.wordmark(W, 107, 43, 7)                   # as in the loading picture, at this size
    name_at = (0, int(ORB[1] + ORB_SIZE * 0.82))
    ending = Image.open(ART / "loading.png").convert("RGBA").resize((W, H), Image.LANCZOS)
    count = int(SECONDS * FPS)
    for n in range(count):
        t = n / FPS
        frame = Image.open(folder / f"t{n:04d}.jpg").convert("RGBA")
        light = ease((t - WAKE) / (FLARE - WAKE))
        if light < 1:                                                # the tunnel lights up as the plasma wakes
            frame = Image.blend(Image.new("RGBA", (W, H), (0, 0, 0, 255)), frame, light)
        # The plasma: a glow that swells and quivers until the flare.
        swell = light * (0.94 + 0.06 * math.sin(t * 21) * math.sin(t * 6))
        put(frame, glow, alpha=min(1.0, 1.15 * swell), scale=0.35 + 0.65 * light)
        flare = t - FLARE
        if flare > -0.15:
            # The orb forms inside the flash; its holder swings in round it and locks.
            lock = ease(flare / 0.9)
            put(frame, holder, alpha=lock, scale=1.35 - 0.35 * lock, turn=-120 * (1 - lock))   # behind the orb, as on the home screen
            shown = ease((flare + 0.15) / 0.45)
            for picture in orb:
                put(frame, picture, alpha=shown, scale=0.8 + 0.2 * shown)
            white = max(0.0, 1 - abs(flare - 0.12) / 0.26) * 0.75
            if white > 0:
                frame = Image.blend(frame, Image.new("RGBA", (W, H), (225, 255, 200, 255)), white)
            # The name, beneath the orb, there to stay.
            if flare > 0.3:
                show = ease((flare - 0.3) / 0.5)
                frame.alpha_composite(faded(behind, 0.95 * show), name_at)
                frame.alpha_composite(faded(text, show), name_at)
        if t > FADE - 0.6:                                           # the tunnel fades away: the loading picture is left
            frame = Image.blend(frame, ending, ease((t - (FADE - 0.6)) / (SECONDS - FADE + 0.4)))
        frame.convert("RGB").save(folder / f"f{n:04d}.png", compress_level=1)
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
