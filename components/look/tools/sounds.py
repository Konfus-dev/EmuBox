#!/usr/bin/env python3
"""Synthesises the theme's menu sounds.

    python3 sounds.py [theme folder]      (default: ../files/theme)

Every sound is built here from scratch: metallic FM tones, noise pushed through
a sweeping resonant filter (the "wet" part) and a small reverb. Nothing is
sampled from any console. Change the recipes at the bottom and run again.
"""
import math
import random
import struct
import sys
import wave
from pathlib import Path

RATE = 44100
TAU = 2 * math.pi


def silence(seconds: float) -> list[float]:
    return [0.0] * int(seconds * RATE)


def envelope(t: float, attack: float, decay: float) -> float:
    """Quick rise over `attack` seconds, then an exponential fall (`decay` per second)."""
    return min(1.0, t / attack) * math.exp(-decay * max(0.0, t - attack))


def fm(out, start, seconds, f0, f1, ratio, index, attack, decay, volume, index_decay=6.0, wobble=(0.0, 0.0)):
    """A frequency-modulated tone sliding from f0 to f1. `ratio` and `index` set how metallic
    it is; the metal fades faster than the tone (index_decay), which gives the "bloop"."""
    carrier = modulator = 0.0
    first = int(start * RATE)
    for i in range(int(seconds * RATE)):
        if first + i >= len(out):
            break
        t = i / RATE
        f = f0 * (f1 / f0) ** (t / seconds) * (1 + wobble[1] * math.sin(TAU * wobble[0] * t))
        modulator += TAU * f * ratio / RATE
        carrier += TAU * f / RATE
        depth = index * math.exp(-index_decay * t)
        out[first + i] += volume * envelope(t, attack, decay) * math.sin(carrier + depth * math.sin(modulator))


def swept_noise(out, start, seconds, f0, f1, resonance, attack, decay, volume, seed=1):
    """Noise through a band-pass filter whose centre slides from f0 to f1: a breathy, watery sweep."""
    rnd = random.Random(seed)
    low = band = 0.0
    first = int(start * RATE)
    for i in range(int(seconds * RATE)):
        if first + i >= len(out):
            break
        t = i / RATE
        cutoff = f0 * (f1 / f0) ** (t / seconds)
        f = 2 * math.sin(math.pi * min(cutoff, RATE / 6.5) / RATE)
        high = rnd.uniform(-1, 1) - low - band / resonance     # state-variable filter
        band += f * high
        low += f * band
        out[first + i] += volume * envelope(t, attack, decay) * band


def reverb(dry: list[float], amount: float, size: float = 1.0) -> tuple[list[float], list[float]]:
    """A small room (four echo loops and two smearing stages), slightly different left and right."""
    def one_side(spread: int) -> list[float]:
        wet = [0.0] * len(dry)
        for delay, feedback in ((1557, 0.80), (1617, 0.79), (1491, 0.81), (1422, 0.78)):
            d = int((delay + spread) * size)
            line = [0.0] * len(dry)
            for i in range(len(dry)):
                line[i] = dry[i] + (feedback * line[i - d] if i >= d else 0.0)
                wet[i] += line[i] * 0.25
        for delay in (225 + spread, 556 + spread):
            passed = [0.0] * len(wet)
            for i in range(len(wet)):
                behind = wet[i - delay] if i >= delay else 0.0
                behind_out = passed[i - delay] if i >= delay else 0.0
                passed[i] = -0.5 * wet[i] + behind + 0.5 * behind_out
            wet = passed
        return [d_ + amount * w for d_, w in zip(dry, wet)]
    return one_side(0), one_side(23)


def save(folder: Path, name: str, dry: list[float], room: float, size: float = 1.0, gain: float = 0.8) -> None:
    left, right = reverb(dry, room, size)
    fade = int(0.02 * RATE)
    for side in (left, right):
        for i in range(fade):
            side[-1 - i] *= i / fade
    peak = max(1e-9, max(max(abs(v) for v in left), max(abs(v) for v in right)))
    scale = gain * 32767 / peak
    with wave.open(str(folder / f"{name}.wav"), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(b"".join(struct.pack("<hh", int(l * scale), int(r * scale)) for l, r in zip(left, right)))


def main() -> None:
    theme = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent / "files" / "theme"
    folder = theme / "art" / "sounds"
    folder.mkdir(parents=True, exist_ok=True)

    # scroll: a short, hollow, slightly wet "tok" that drops in pitch. Heard constantly, so quiet and brief.
    s = silence(0.30)
    fm(s, 0, 0.11, 640, 300, ratio=1.41, index=2.6, attack=0.002, decay=34, volume=1.0, index_decay=40)
    fm(s, 0, 0.09, 150, 90, ratio=1.0, index=0.6, attack=0.003, decay=40, volume=0.55)
    swept_noise(s, 0, 0.05, 2600, 900, resonance=3, attack=0.001, decay=70, volume=0.35)
    save(folder, "scroll", s, room=0.22, size=0.6, gain=0.28)   # heard hundreds of times: keep it soft

    # select: a low "bwom" that opens upward into a glassy chime.
    s = silence(0.95)
    fm(s, 0, 0.30, 110, 260, ratio=2.0, index=3.2, attack=0.012, decay=9, volume=1.0, index_decay=9)
    fm(s, 0.07, 0.55, 520, 780, ratio=3.01, index=1.8, attack=0.02, decay=6.5, volume=0.45, index_decay=5, wobble=(7, 0.006))
    fm(s, 0.07, 0.55, 783, 1170, ratio=2.0, index=0.9, attack=0.03, decay=7.5, volume=0.22, index_decay=6)
    swept_noise(s, 0, 0.32, 300, 2800, resonance=6, attack=0.02, decay=10, volume=0.5, seed=2)
    save(folder, "select", s, room=0.38, gain=0.5)

    # back: the same voice falling and closing.
    s = silence(0.80)
    fm(s, 0, 0.28, 300, 100, ratio=2.0, index=2.8, attack=0.008, decay=10, volume=1.0, index_decay=10)
    fm(s, 0.02, 0.40, 660, 390, ratio=3.01, index=1.4, attack=0.012, decay=9, volume=0.35, index_decay=8)
    swept_noise(s, 0, 0.26, 2400, 260, resonance=6, attack=0.01, decay=12, volume=0.45, seed=3)
    save(folder, "back", s, room=0.34, gain=0.45)

    # menuopen: a quick breath of air sliding up, with a faint ring on top.
    s = silence(0.75)
    swept_noise(s, 0, 0.36, 240, 3600, resonance=8, attack=0.05, decay=8, volume=1.0, seed=4)
    fm(s, 0.03, 0.34, 200, 520, ratio=1.5, index=2.2, attack=0.03, decay=9, volume=0.55, index_decay=7)
    fm(s, 0.16, 0.40, 1040, 1100, ratio=2.76, index=1.2, attack=0.02, decay=9, volume=0.16, index_decay=6)
    save(folder, "menuopen", s, room=0.36, gain=0.5)

    # launch: a deep swell that rises, shimmers and washes out as the game takes over.
    s = silence(2.1)
    fm(s, 0, 1.25, 55, 196, ratio=1.0, index=2.4, attack=0.35, decay=2.6, volume=1.0, index_decay=1.2, wobble=(5, 0.01))
    fm(s, 0, 1.25, 82.5, 294, ratio=2.0, index=2.0, attack=0.45, decay=2.8, volume=0.55, index_decay=1.4, wobble=(6, 0.012))
    fm(s, 0.35, 1.0, 392, 1176, ratio=3.01, index=2.6, attack=0.4, decay=3.4, volume=0.28, index_decay=2.2, wobble=(8, 0.01))
    swept_noise(s, 0, 1.3, 160, 5200, resonance=7, attack=0.6, decay=3.0, volume=0.9, seed=5)
    fm(s, 0.95, 0.5, 1568, 1568, ratio=2.76, index=1.5, attack=0.01, decay=8, volume=0.14, index_decay=7)
    save(folder, "launch", s, room=0.5, size=1.25, gain=0.95)

    # What the menus actually play for scrolling: redrawn on Batocera by the console's menusounds.py.
    (folder / "scroll-now.wav").write_bytes((folder / "scroll.wav").read_bytes())
    print(f"sounds written to {folder}")


if __name__ == "__main__":
    main()
