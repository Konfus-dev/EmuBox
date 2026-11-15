#!/usr/bin/env python3
"""EmuBox's settings.

    settings.py                 list them: name, value, what it does
    settings.py get <name>      print the value
    settings.py is <name>       print "true" when it is on (nothing when off)
    settings.py set <name> <value>

You change them in Batocera's own menu: Start > Game Settings > EmuBox (the
entries are put there by startmenu.py). Batocera keeps what you choose in
batocera.conf, as global.emubox_<name>; that is read here, and wins. Anything
not chosen there has the value given below. `set` is for scripts: it writes
/userdata/system/configs/emubox/settings.conf and, when Batocera already has a
line for the setting, that line too.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

FILE = Path(os.environ.get("EMUBOX_SETTINGS", "/userdata/system/configs/emubox/settings.conf"))
BATOCERA = Path(os.environ.get("EMUBOX_BATOCERA_CONF", "/userdata/system/batocera.conf"))

# name: (value when not set, label in the menu, kind, what it does)
# kind: "switch", "slider" (0..100), "choice" (startmenu.py supplies the choices) or "" (not shown)
KNOWN = {
    "ui.sound_set": ("", "SOUND SET", "choice", "Which set of sounds the menus use. Your own sets are the folders the installer copied. Auto: your Xbox set when there is one, else EmuBox's."),
    "ui.sound_volume": ("60", "VOLUME", "slider", "How loud the menu sounds are."),
    "ui.sound.scroll": ("on", "MOVING", "switch", "A sound when you move through a list or a menu."),
    "ui.sound.select": ("on", "CHOOSING", "switch", "A sound when you choose something."),
    "ui.sound.back": ("on", "GOING BACK", "switch", "A sound when you go back."),
    "ui.sound.menuopen": ("on", "OPENING THE MENU", "switch", "A sound when the main menu opens."),
    "music.quiet_menu": ("on", "QUIET MENUS UNDER MY MUSIC", "switch", "While a music app plays, the menu music and sounds are silent."),
    "call.lower_music": ("on", "TURN MUSIC DOWN DURING A CALL", "switch", "While an app uses the microphone, music and menus drop in volume."),
    "call.music_volume": ("20", "MUSIC VOLUME DURING A CALL", "slider", "How loud music stays during a call."),
    "web.block_ads": ("on", "BLOCK ADS IN WEB APPS", "switch", "Keeps adverts and trackers out of Vault and other web apps."),
}
ON = ("on", "1", "true", "yes")


def conf_key(name: str) -> str:
    """The name Batocera's menu saves a setting under."""
    return "emubox_" + name.replace(".", "_")


def from_batocera(text: str, prefix: str = "global.") -> dict[str, str]:
    """Every "global.key=value" line of batocera.conf, as {key: value}."""
    found = {}
    for line in text.splitlines():
        if line.startswith(prefix) and "=" in line:
            key, _, value = line[len(prefix):].partition("=")
            found[key.strip()] = value.strip()
    return found


def read(file: Path | None = None, batocera: Path | None = None) -> dict[str, str]:
    values = {name: known[0] for name, known in KNOWN.items()}
    try:
        for line in (file or FILE).read_text().splitlines():
            name, found, value = line.partition("=")
            if found and not line.lstrip().startswith("#"):
                values[name.strip()] = value.strip()
    except OSError:
        pass
    try:
        chosen = from_batocera((batocera or BATOCERA).read_text(errors="replace"))
    except OSError:
        chosen = {}
    for name, known in KNOWN.items():
        value = chosen.get(conf_key(name), "")
        if value in ("", "auto"):
            continue
        if known[2] == "switch":
            values[name] = "on" if value in ON else "off"
        elif known[2] == "slider":
            try:
                values[name] = str(int(float(value)))
            except ValueError:
                pass
        else:
            values[name] = value
    return values


def get(name: str, file: Path | None = None) -> str:
    return read(file).get(name, "")


def on(name: str, file: Path | None = None) -> bool:
    return get(name, file).lower() in ON


def write(name: str, value: str, file: Path | None = None, batocera: Path | None = None) -> None:
    file = file or FILE
    kept = {}
    try:
        for line in file.read_text().splitlines():
            key, found, old = line.partition("=")
            if found and key.strip() != name:
                kept[key.strip()] = old.strip()
    except OSError:
        pass
    if name not in KNOWN or value != KNOWN[name][0]:
        kept[name] = value
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text("".join(f"{n}={v}\n" for n, v in sorted(kept.items())))
    # Batocera's own line, when there is one, or it would go on winning.
    batocera = batocera or BATOCERA
    try:
        text = batocera.read_text(errors="replace")
        pattern = re.compile(rf"^global\.{re.escape(conf_key(name))}=.*$", re.MULTILINE)
        if pattern.search(text):
            shown = ("1" if value.lower() in ON else "0") if KNOWN.get(name, ("", "", ""))[2] == "switch" else value
            batocera.write_text(pattern.sub(lambda _: f"global.{conf_key(name)}={shown}", text))
    except OSError:
        pass


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
