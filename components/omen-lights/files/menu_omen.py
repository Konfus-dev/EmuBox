#!/usr/bin/env python3
"""OMEN lights: their settings, as rows in the in-game menu's Apps tab.

The lights program (github.com/Konfus-dev/OmenRGB-Controller) acts on one small
file, /userdata/system/configs/omen-lights/settings.json, the moment it is
saved. This is a front end for that file: `rows()` gives the menu its rows,
and the rows call back into the commands below.

    menu_omen.py is <setting>              print "true" when a yes/no setting is on
    menu_omen.py get <setting>             print a setting
    menu_omen.py set <setting> <value>     on/off, a number, or text
    menu_omen.py step <setting> <+/-n>     move a percentage, kept within 0..100
    menu_omen.py colour <where> <colour>   where: menus, all, or a zone ("RAM/Stick 1");
                                           colour: a name below, #RRGGBB, or "picture" (menus only)
    menu_omen.py colour-of <where>
    menu_omen.py effect <case|ram|all> <Static|Breathing|Rainbow|Off>
    menu_omen.py effect-of <case|ram>
    menu_omen.py speed <0..100> / speed-of
    menu_omen.py dim <min|max> <0..100> / dim-of <min|max>      how far Breathing fades
    menu_omen.py picture <file|theme> / picture-of               what the cooler's screen shows
    menu_omen.py reset                     everything back to how it came
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from xml.sax.saxutils import quoteattr

HOME = Path(os.environ.get("OMEN_LIGHTS_HOME", "/userdata/system/configs/omen-lights"))
FILE = HOME / "settings.json"
PICTURES = HOME / "pictures"
GROUP = "OMEN lights"

CASE, RAM = "HP Omen 30L", "RAM"
DEVICES = {"case": CASE, "ram": RAM}
ZONES = {   # as the lights program names them: what to call them here
    f"{CASE}/Omen Logo": "Front logo", f"{CASE}/Front Top Fan": "Top fan",
    f"{CASE}/Front Middle Fan": "Middle fan", f"{CASE}/Front Bottom Fan": "Bottom fan",
    f"{RAM}/Stick 1": "Left memory stick", f"{RAM}/Stick 2": "Right memory stick",
}
EFFECTS = {"case": ("Static", "Breathing"), "ram": ("Static", "Breathing", "Rainbow", "Off")}
COLOURS = {
    "Green": "#3CE61E", "Lime": "#C8F03C", "White": "#FFFFFF", "Warm white": "#FFD9A0", "Red": "#FF1A1A",
    "Orange": "#FF7A00", "Yellow": "#FFD500", "Cyan": "#00E5FF", "Blue": "#1E5BFF", "Purple": "#9B30FF",
    "Pink": "#FF3DBB",
}
# What each setting is when the file does not mention it (the lights program's own defaults on Batocera).
DEFAULTS = {
    "lights-enabled": True, "lights-brightness": 100, "device-modes": {RAM: "Static"}, "zone-colours": {},
    "device-speeds": {}, "device-min-brightness": {}, "device-max-brightness": {},
    "lcd-enabled": True, "lcd-brightness": 80, "lcd-image": "", "lcd-fit": "fill",
    "auto-enabled": True, "auto-lights": True, "auto-lcd": True, "auto-idle-image": "", "auto-idle-colour": "",
}
ON = ("on", "1", "true", "yes")


def load() -> dict:
    try:
        found = json.loads(FILE.read_text())
        return found if isinstance(found, dict) else {}
    except (OSError, ValueError):
        return {}


def save(values: dict) -> None:
    """Written in one go: the lights program reads the file the moment it changes."""
    HOME.mkdir(parents=True, exist_ok=True)
    fresh = FILE.with_suffix(".new")
    fresh.write_text(json.dumps(values, indent=4) + "\n")
    os.replace(fresh, FILE)


def get(name: str):
    return load().get(name, DEFAULTS.get(name, ""))


def put(name: str, value) -> None:
    values = load()
    values[name] = value
    save(values)


def typed(name: str, text: str):
    """What was typed, as the kind of value the setting holds."""
    kind = DEFAULTS.get(name)
    if isinstance(kind, bool):
        return text.lower() in ON
    if isinstance(kind, int):
        return max(0, min(100, int(text)))
    return text


def colour_value(word: str) -> str:
    by_name = {name.lower(): value for name, value in COLOURS.items()}
    if word.lower() in by_name:
        return by_name[word.lower()]
    if len(word) == 7 and word.startswith("#") and all(c in "0123456789abcdefABCDEF" for c in word[1:]):
        return word.upper()
    raise ValueError(f"not a colour: {word}")


def colour_name(value: str) -> str:
    for name, known in COLOURS.items():
        if known.lower() == str(value).lower():
            return name
    return str(value)


def set_colour(where: str, word: str) -> None:
    values = load()
    if where == "menus":
        values["auto-idle-colour"] = "" if word.lower() == "picture" else colour_value(word)
    else:
        zones = dict(values.get("zone-colours", {}))
        for zone in (ZONES if where == "all" else [where]):
            if zone not in ZONES:
                raise ValueError(f"no such light: {zone}")
            zones[zone] = colour_value(word)
        values["zone-colours"] = zones
    save(values)


def colour_of(where: str) -> str:
    if where == "menus":
        return colour_name(get("auto-idle-colour")) or "From the picture"
    return colour_name(get("zone-colours").get(where, "")) or "Not set"


def for_devices(name: str, which: str, value) -> None:
    values = load()
    table = dict(values.get(name, DEFAULTS[name]))
    for key in (DEVICES if which == "all" else [which]):
        table[DEVICES[key]] = value
    values[name] = table
    save(values)


def of_device(name: str, which: str, fallback):
    return get(name).get(DEVICES[which], fallback)


def pictures() -> list[Path]:
    try:
        return sorted(p for p in PICTURES.iterdir() if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp", ".gif"))[:12]
    except OSError:
        return []


def run(argv: list[str]) -> str:
    """Do one command; what it gives back is printed."""
    action, rest = argv[0], argv[1:]
    if action == "is":
        return "true" if get(rest[0]) is True else ""
    if action == "get":
        return str(get(rest[0]))
    if action == "set":
        put(rest[0], typed(rest[0], rest[1]))
    elif action == "step":
        put(rest[0], max(0, min(100, int(get(rest[0])) + int(rest[1]))))
    elif action == "colour":
        set_colour(rest[0], rest[1])
    elif action == "colour-of":
        return colour_of(rest[0])
    elif action == "effect":
        for which in (DEVICES if rest[0] == "all" else [rest[0]]):
            if rest[1] in EFFECTS[which]:
                for_devices("device-modes", which, rest[1])
    elif action == "effect-of":
        return of_device("device-modes", rest[0], "Static")
    elif action == "speed":
        for_devices("device-speeds", "all", max(0, min(100, int(rest[0]))))
    elif action == "speed-of":
        return {0: "Slow", 50: "Medium", 100: "Fast"}.get(of_device("device-speeds", "case", 50), "Custom")
    elif action == "dim":
        for_devices(f"device-{rest[0]}-brightness", "all", max(0, min(100, int(rest[1]))))
    elif action == "dim-of":
        return f"{of_device(f'device-{rest[0]}-brightness', 'case', 0 if rest[0] == 'min' else 100)}%"
    elif action == "picture":
        values = load()
        values["lcd-image"] = values["auto-idle-image"] = "" if rest[0] == "theme" else rest[0]
        save(values)
    elif action == "picture-of":
        return Path(get("auto-idle-image") or get("lcd-image")).stem or "The theme's"
    elif action == "reset":
        save({})
    else:
        raise IndexError(action)
    return ""


# --- the menu rows -----------------------------------------------------------------

def rows() -> list[str]:
    """Rows for the Apps tab (lib/menu.py asks every lib/menu_*.py for these)."""
    me = f"python3 {Path(__file__).resolve()}"

    def row(label: str, *items: str) -> list[str]:
        return [f'\t\t<feature display={quoteattr(label)} group={quoteattr(GROUP)}>', *items, '\t\t</feature>']

    def switch(name: str) -> str:
        return (f'\t\t\t<switch value="${{{me} is {name}}}" action_on="{me} set {name} on" '
                f'action_off="{me} set {name} off" />')

    def shows(command: str) -> str:
        return f'\t\t\t<text display="${{{me} {command}}}" refresh="2" />'

    def choice(label: str, command: str) -> str:
        return f'\t\t\t<choice display={quoteattr(label)} action={quoteattr(f"{me} {command}")} afterclick="bcc_refresh" />'

    def percent(name: str) -> list[str]:
        return [f'\t\t\t<button display="-" action="{me} step {name} -10" />',
                f'\t\t\t<progressbar display="${{{me} get {name}}}" min="0" max="100" refresh="1" />',
                f'\t\t\t<button display="+" action="{me} step {name} +10" />']

    def palette(where: str) -> list[str]:
        return [choice(name, f"colour '{where}' '{name}'") for name in COLOURS]

    out: list[str] = [f'\t\t<feature display="—  OMEN LIGHTS  —">\n\t\t\t<text display="·" />\n\t\t</feature>']
    out += row("Lights", switch("lights-enabled"))
    out += row("Light brightness", *percent("lights-brightness"))
    out += row("Follow the game", switch("auto-enabled"))
    out += row("Lights follow it", switch("auto-lights"))
    out += row("Cooler screen follows it", switch("auto-lcd"))
    out += row("Colour in the menus", shows("colour-of menus"),
               choice("From the picture", "colour menus picture"), *palette("menus"))
    out += row("All lights (when not following)", choice("Pick a colour for every light", "colour all Green"),
               *palette("all"))
    for zone, name in ZONES.items():
        out += row(name, shows(f"colour-of '{zone}'"), *palette(zone))
    out += row("Case effect", shows("effect-of case"), *(choice(e, f"effect case {e}") for e in EFFECTS["case"]))
    out += row("Memory effect", shows("effect-of ram"), *(choice(e, f"effect ram {e}") for e in EFFECTS["ram"]))
    out += row("Effect speed", shows("speed-of"),
               choice("Slow", "speed 0"), choice("Medium", "speed 50"), choice("Fast", "speed 100"))
    out += row("Breathing fades down to", shows("dim-of min"), *(choice(f"{n}%", f"dim min {n}") for n in (0, 10, 25, 50)))
    out += row("Breathing rises up to", shows("dim-of max"), *(choice(f"{n}%", f"dim max {n}") for n in (50, 75, 100)))
    out += row("Cooler screen", switch("lcd-enabled"))
    out += row("Screen brightness", *percent("lcd-brightness"))
    out += row("Screen picture", shows("picture-of"), choice("The theme's", "picture theme"),
               *(choice(p.stem, f"picture '{p}'") for p in pictures()))
    out += row("Picture fit", shows("get lcd-fit"), choice("Fill the screen", "set lcd-fit fill"),
               choice("Show all of it", "set lcd-fit fit"))
    out += row("Start over", f'\t\t\t<button_confirm display="Reset the lights" action="{me} reset" align="left" />')
    return out


def main(argv: list[str]) -> int:
    try:
        said = run(argv)
    except (IndexError, KeyError, ValueError) as error:
        print(f"menu_omen: {error}", file=sys.stderr)
        print(__doc__, file=sys.stderr)
        return 2
    if said:
        print(said)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
