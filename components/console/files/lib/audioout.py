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
import time


def _pactl_json(*what: str) -> list[dict]:
    try:
        found = json.loads(subprocess.run(["pactl", "-f", "json", "list", *what], capture_output=True,
                                          text=True, timeout=5).stdout or "[]")
    except (OSError, subprocess.SubprocessError, ValueError):
        return []
    return found if isinstance(found, list) else []


def outputs(sinks: list[dict] | None = None, cards: list[dict] | None = None) -> list[tuple[str, str]]:
    """(name, friendly name) of every output, "auto" first. A sound card switched off (its profile
    "off", as an HDMI card can be) has no output yet: it is offered as "card:<card>:<profile>",
    its best plugged-in output profile, and switched on when chosen."""
    sinks = _pactl_json("sinks") if sinks is None else sinks
    cards = _pactl_json("cards") if cards is None else cards
    found = [("auto", "Automatic")] + [(s["name"], friendly(s)) for s in sinks if s.get("name")]
    for card in cards:
        if card.get("active_profile") != "off":
            continue
        profiles = card.get("profiles", {})
        usable = [n for n, p in profiles.items()
                  if n.startswith("output:") and "+input" not in n and p.get("available", True)]
        if usable:
            best = sorted(usable, key=lambda n: (not n.endswith("hdmi-stereo"), "extra" in n, n))[0]
            props = card.get("properties", {})
            fake_sink = {"name": f"{card.get('name', '')}.{best.split(':', 1)[1]}",
                         "description": props.get("device.description", card.get("name", "")),
                         "properties": {"device.bus": props.get("device.bus", ""), "node.nick": ""}}
            found.append((f"card:{card['name']}:{best}", friendly(fake_sink)))
    return found


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
    if target.startswith("card:"):           # switch the card on first; its output then appears
        _, card, profile = target.split(":", 2)
        subprocess.run(["pactl", "set-card-profile", card, profile])
        target = ""
        for _ in range(20):
            sink = next((s["name"] for s in _pactl_json("sinks")
                         if s.get("properties", {}).get("device.name") == card), "")
            if sink:
                target = sink
                break
            time.sleep(0.1)
        if not target:
            return
    if subprocess.run(["batocera-audio", "set", target]).returncode == 0:
        subprocess.run(["batocera-settings-set", "audio.device", target])
        move_playing(target)


def move_playing(sink: str) -> None:
    """Sounds already playing (the menu music, a game, an app) move to the new output too;
    otherwise they would stay on the old one until they start again."""
    if sink == "auto":
        return
    for stream in _pactl_json("sink-inputs"):
        if "index" in stream:
            subprocess.run(["pactl", "move-sink-input", str(stream["index"]), sink], capture_output=True)


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
