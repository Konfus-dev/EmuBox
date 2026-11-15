#!/usr/bin/env python3
"""EmuBox's settings.

    settings.py                 list them: name, value, what it does
    settings.py get <name>      print the value
    settings.py is <name>       print "true" when it is on (nothing when off)
    settings.py set <name> <value>

You change them in Batocera's own menu, Start > Game Settings > EmuBox (the
entries are put there by startmenu.py; Batocera keeps those choices in
batocera.conf as global.emubox_<name>), or in EmuBox's Guide menu, which keeps
its changes in /userdata/system/configs/emubox/settings.conf. Whichever was
changed last wins. Anything never chosen has the value given below.
"""
from __future__ import annotations

import os
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
    "music.menu": ("on", "MENU MUSIC", "switch", "Background music in the menus (Batocera's songs, or yours in the music folder)."),
    "music.quiet_menu": ("on", "PAUSE IT WHILE MY MUSIC PLAYS", "switch", "While a music app plays, the menu music waits."),
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


def _own(file: Path) -> dict[str, str]:
    found = {}
    try:
        for line in file.read_text().splitlines():
            name, has, value = line.partition("=")
            if has and not line.lstrip().startswith("#"):
                found[name.strip()] = value.strip()
    except OSError:
        pass
    return found


def _chosen(name: str, raw: str) -> str:
    """A value as Batocera's menu saves it, in our terms ("" when nothing is chosen there)."""
    kind = KNOWN[name][2]
    if raw in ("", "auto"):
        return ""
    if kind == "switch":
        return "on" if raw in ON else "off"
    if kind == "slider":
        try:
            return str(int(float(raw)))
        except ValueError:
            return ""
    return raw


def read(file: Path | None = None, batocera: Path | None = None) -> dict[str, str]:
    """Every setting's value. Two places can change one: Batocera's menu (batocera.conf) and
    EmuBox itself (the Guide menu, scripts: our own file). Whichever changed it last wins: we note
    what Batocera's menu said when we last looked ("seen.<name>"), so a different value there now
    is a newer choice."""
    file = file or FILE
    own = _own(file)
    try:
        theirs = from_batocera((batocera or BATOCERA).read_text(errors="replace"))
    except OSError:
        theirs = {}
    values, noted = {}, False
    for name, known in KNOWN.items():
        chosen = _chosen(name, theirs.get(conf_key(name), ""))
        if chosen and chosen != own.get(f"seen.{name}", ""):
            own[name], own[f"seen.{name}"], noted = chosen, chosen, True
        values[name] = own.get(name, known[0])
    for name, value in own.items():           # settings of other tools that keep theirs here
        if name not in values and not name.startswith("seen."):
            values[name] = value
    if noted:
        _save(file, own)
    return values


def _save(file: Path, own: dict[str, str]) -> None:
    try:
        file.parent.mkdir(parents=True, exist_ok=True)
        # Written aside and then moved into place: several programs read this file all the time,
        # and one must never see it half written (and save that back over the real one).
        part = file.with_name(f".{file.name}.{os.getpid()}")
        part.write_text("".join(f"{n}={v}\n" for n, v in sorted(own.items())))
        os.replace(part, file)
    except OSError:
        pass


def get(name: str, file: Path | None = None) -> str:
    return read(file).get(name, "")


def on(name: str, file: Path | None = None) -> bool:
    return get(name, file).lower() in ON


def write(name: str, value: str, file: Path | None = None, batocera: Path | None = None) -> None:
    file = file or FILE
    read(file, batocera)          # first take note of what Batocera's menu says now, so ours counts as newer
    own = _own(file)
    own[name] = value
    _save(file, own)


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
