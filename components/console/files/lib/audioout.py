#!/usr/bin/env python3
"""Which speakers or headphones sound comes out of, for the Guide menu's "Sound output" row.

    audioout.py show              the current output's name
    audioout.py next | previous   switch to the next / previous one, and keep it for the next start

Batocera's own list (batocera-audio list) is used, so every output it knows is offered, Bluetooth
headphones included once they are connected. The choice is saved as Batocera's audio.device,
which Batocera applies at start-up.
"""
from __future__ import annotations

import re
import subprocess
import sys


def outputs() -> list[tuple[str, str]]:
    """(name, description) of every output, "auto" first."""
    out = subprocess.run(["batocera-audio", "list"], capture_output=True, text=True, timeout=5).stdout
    found = []
    for line in out.splitlines():
        name, _, desc = line.partition("\t")
        if name:
            found.append((name, "Automatic" if name == "auto" else short(desc or name)))
    return found


def short(desc: str) -> str:
    """'Navi 31 HDMI/DP Audio Digital Stereo (HDMI 2)' -> 'Navi 31 HDMI/DP Audio (HDMI 2)'"""
    desc = re.sub(r"\b(Digital|Analog) (Stereo|Surround[^()]*)", "", desc)
    return re.sub(r"\s+", " ", desc).strip()[:40]


def current() -> str:
    chosen = subprocess.run(["batocera-settings-get", "audio.device"], capture_output=True, text=True).stdout.strip()
    if chosen in ("", "auto"):
        return "auto"
    return subprocess.run(["pactl", "get-default-sink"], capture_output=True, text=True).stdout.strip() or chosen


def label(name: str, all_: list[tuple[str, str]]) -> str:
    return next((d for n, d in all_ if n == name), name)


def step(by: int) -> None:
    all_ = outputs()
    if not all_:
        return
    names = [n for n, _ in all_]
    now = current()
    i = names.index(now) if now in names else 0
    target = names[(i + by) % len(names)]
    if subprocess.run(["batocera-audio", "set", target]).returncode == 0:
        subprocess.run(["batocera-settings-set", "audio.device", target])


def main(argv: list[str]) -> int:
    what = argv[0] if argv else "show"
    if what == "show":
        print(label(current(), outputs()))
    elif what in ("next", "previous"):
        step(1 if what == "next" else -1)
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
