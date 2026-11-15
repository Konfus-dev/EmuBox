#!/usr/bin/env python3
"""EmuBox's few switches, kept in one small file on the drive.

    settings.py                 list them: name, value, what it does
    settings.py get <name>      print the value
    settings.py is <name>       print "true" when it is on (nothing when off)
    settings.py set <name> <value>

The in-game menu's Apps tab shows them as switches. The file is
/userdata/system/configs/emubox/settings.conf, one name=value per line;
anything not in it has the value given here.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

FILE = Path(os.environ.get("EMUBOX_SETTINGS", "/userdata/system/configs/emubox/settings.conf"))

# name: (value when not set, the switch's label in the menu)
KNOWN = {
    "ui.sound_set": ("EmuBox", ""),          # the folder of sounds in use (see menusounds.py)
    "ui.sound_volume": ("60", ""),           # percent
    "ui.sound.scroll": ("on", ""),
    "ui.sound.select": ("on", ""),
    "ui.sound.back": ("on", ""),
    "ui.sound.menuopen": ("on", ""),
    "music.quiet_menu": ("on", "Quiet the menus while my music plays"),
    "call.lower_music": ("on", "Turn music down during a call"),
    "call.music_volume": ("20", ""),   # percent the music drops to during a call
    "web.block_ads": ("on", "Block ads in web apps"),
}
ON = ("on", "1", "true", "yes")


def read(file: Path | None = None) -> dict[str, str]:
    values = {name: default for name, (default, _) in KNOWN.items()}
    try:
        for line in (file or FILE).read_text().splitlines():
            name, found, value = line.partition("=")
            if found and not line.lstrip().startswith("#"):
                values[name.strip()] = value.strip()
    except OSError:
        pass
    return values


def get(name: str, file: Path | None = None) -> str:
    return read(file).get(name, "")


def on(name: str, file: Path | None = None) -> bool:
    return get(name, file).lower() in ON


def write(name: str, value: str, file: Path | None = None) -> None:
    file = file or FILE
    kept = {n: v for n, v in read(file).items() if (n not in KNOWN or v != KNOWN[n][0]) and n != name}
    if name not in KNOWN or value != KNOWN[name][0]:
        kept[name] = value
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text("".join(f"{n}={v}\n" for n, v in sorted(kept.items())))


def main(argv: list[str]) -> int:
    if not argv:
        for name, value in read().items():
            print(f"{name}\t{value}\t{KNOWN.get(name, ('', ''))[1]}")
    elif argv[0] == "get" and len(argv) == 2:
        print(get(argv[1]))
    elif argv[0] == "is" and len(argv) == 2:
        if on(argv[1]):
            print("true")
    elif argv[0] == "set" and len(argv) == 3:
        write(argv[1], argv[2])
    else:
        print(__doc__, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
