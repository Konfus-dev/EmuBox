#!/usr/bin/env python3
"""Warn when Batocera is only guessing a controller's buttons.

    padcheck.py /dev/input/eventN     check one controller (menusounds.py runs this when one connects)

Batocera's menus look a controller up in their list (es_input.cfg) by its id. When the id is not
there but a controller of the same name is, they use that one's button numbers, and for another
model or another connection (USB, Bluetooth) those can all be wrong: A does nothing, B goes
nowhere. That happened with the Xbox pad (2026-11-19). This notices that case and says how to fix
it, once per controller per start.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

LISTS = (Path("/userdata/system/configs/emulationstation/es_input.cfg"),
         Path("/usr/share/emulationstation/es_input.cfg"))
TOLD = Path("/var/run/emubox")
FIX = "Start > Controller settings > Controller mapping"


def guid(bus: int, vendor: int, product: int, version: int) -> str:
    """The id Batocera's menus (SDL) give a controller: each number as 16-bit little-endian, padded."""
    return "".join(f"{n & 0xff:02x}{(n >> 8) & 0xff:02x}0000" for n in (bus, vendor, product, version))


def entries(lists=LISTS) -> list[tuple[str, str]]:
    """(name, id) of every controller in the menus' lists."""
    found = []
    for path in lists:
        try:
            text = path.read_text(errors="replace")
        except OSError:
            continue
        for tag in re.findall(r"<inputConfig\b[^>]*>", text):
            name, gid = re.search(r'deviceName="([^"]*)"', tag), re.search(r'deviceGUID="([^"]*)"', tag)
            if name and gid:
                found.append((name.group(1), gid.group(1).lower()))
    return found


def guessed(name: str, gid: str, known: list[tuple[str, str]]) -> bool:
    """No entry for this id, but one with the same name: the menus will borrow its buttons."""
    return not any(g == gid for _n, g in known) and any(n == name for n, _g in known)


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    import evdev
    try:
        device = evdev.InputDevice(argv[0])
    except OSError:
        return 1
    info = device.info
    gid = guid(info.bustype, info.vendor, info.product, info.version)
    if not guessed(device.name, gid, entries()):
        return 0
    note = TOLD / f"padcheck-{gid}"
    if note.exists():
        return 0
    TOLD.mkdir(parents=True, exist_ok=True)
    note.touch()
    print(f"padcheck: {device.name} ({gid}) has no layout of its own; the menus borrow one by name", file=sys.stderr)
    subprocess.Popen(["python3", str(Path(__file__).with_name("toast.py")),
                      f"{device.name}: Batocera does not know this controller exactly, so its buttons may be wrong. "
                      f"If they are, set them up in {FIX}.", "12"],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
