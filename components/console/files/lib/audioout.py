#!/usr/bin/env python3
"""Which speakers or headphones sound comes out of, for the Guide menu's "Sound output" row.

    audioout.py show              the current output's name
    audioout.py next | previous   switch to the next / previous one, and keep it for the next start

Every output the sound server has is offered (Bluetooth headphones once connected), by the name
a person would use: the TV's own name for HDMI, the headphones' for Bluetooth. The choice is saved as Batocera's audio.device,
which Batocera applies at start-up.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys


def outputs() -> list[tuple[str, str]]:
    """(name, friendly name) of every output, "auto" first."""
    try:
        sinks = json.loads(subprocess.run(["pactl", "-f", "json", "list", "sinks"], capture_output=True,
                                          text=True, timeout=5).stdout or "[]")
    except (OSError, subprocess.SubprocessError, ValueError):
        sinks = []
    return [("auto", "Automatic")] + [(s["name"], friendly(s)) for s in sinks if s.get("name")]


def friendly(sink: dict) -> str:
    """What a person calls an output: the TV's own name for HDMI, the headphones' name for
    Bluetooth, the product for USB; Batocera's long technical description only as a last resort."""
    props = sink.get("properties", {})
    name, desc = sink.get("name", ""), sink.get("description", "") or sink.get("name", "")
    nick = props.get("node.nick", "")
    port = re.search(r"\((HDMI[^)]*)\)", desc)
    if props.get("device.bus") == "bluetooth" or name.startswith("bluez_"):
        return f"{props.get('device.description') or desc} (Bluetooth)"
    if "hdmi" in name.lower():
        tv = nick if nick and not nick.upper().startswith("HDMI") else "TV"
        return f"{tv} ({port.group(1) if port else 'HDMI'})"
    if props.get("device.bus") == "usb":
        return nick or short(desc)
    if "analog" in name.lower():
        return "Speakers / headphone socket"
    return short(desc)


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
