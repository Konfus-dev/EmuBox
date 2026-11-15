#!/usr/bin/env python3
"""OMEN lights: their settings in Batocera's menu, Start > Game Settings > OMEN LIGHTING.

The lights program (github.com/Konfus-dev/OmenRGB-Controller) acts on one small
file, /userdata/system/configs/omen-lights/settings.json, the moment it is
saved. This is a front end for that file: `features()` describes the settings
to Batocera's menu and `changed()` carries your choices over. The same can be
done by hand:

    startmenu_omen.py is <setting>              print "true" when a yes/no setting is on
    startmenu_omen.py get <setting>             print a setting
    startmenu_omen.py set <setting> <value>     on/off, a number, or text
    startmenu_omen.py step <setting> <+/-n>     move a percentage, kept within 0..100
    startmenu_omen.py colour <where> <colour>   where: menus, all, or a zone ("RAM/Stick 1");
                                           colour: a name below, #RRGGBB, or "picture" (menus only)
    startmenu_omen.py colour-of <where>
    startmenu_omen.py effect <case|ram|all> <Static|Breathing|Rainbow|Off>
    startmenu_omen.py effect-of <case|ram>
    startmenu_omen.py speed <0..100> / speed-of
    startmenu_omen.py dim <min|max> <0..100> / dim-of <min|max>      how far Breathing fades
    startmenu_omen.py picture <file|theme> / picture-of               what the cooler's screen shows
    startmenu_omen.py reset                     everything back to how it came
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
HOME = Path(os.environ.get("OMEN_LIGHTS_HOME", "/userdata/system/configs/omen-lights"))
FILE = HOME / "settings.json"
PICTURES = HOME / "pictures"

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


# --- Batocera's Start menu ---------------------------------------------------------
# Start > Game Settings > OMEN LIGHTING. Batocera saves each choice in batocera.conf as
# global.omen_<name>; `changed` (called by the console's startmenu.py whenever that file
# changes) carries them over into settings.json, which the lights program acts on.

SUBMENU, GROUP = "OMEN LIGHTING", "EMUBOX"
SWITCHES = {   # setting: (label, what it does)
    "lights-enabled": ("LIGHTS", "The case and memory lights."),
    "auto-enabled": ("FOLLOW THE GAME", "The lights and the cooler's screen take the running game's colours and artwork."),
    "auto-lights": ("LIGHTS FOLLOW IT", "With follow the game on: let the lights follow."),
    "auto-lcd": ("COOLER SCREEN FOLLOWS IT", "With follow the game on: let the cooler's screen follow."),
    "lcd-enabled": ("COOLER SCREEN", "The screen on the cooler. Off shows a black screen."),
}
SLIDERS = {"lights-brightness": ("LIGHT BRIGHTNESS", "How bright the lights are."),
           "lcd-brightness": ("SCREEN BRIGHTNESS", "How bright the cooler's screen is.")}


def key(name: str) -> str:
    return "omen_" + name.replace("-", "_").replace("/", "_").replace(" ", "_").lower()


def features() -> list[tuple[str, str]]:
    from xml.sax.saxutils import quoteattr

    def item(name: str, label: str, what: str, rest: str, choices=()) -> tuple[str, str]:
        start = (f'    <feature name={quoteattr(label)} submenu="{SUBMENU}" group="{GROUP}" value="{key(name)}" '
                 f'description={quoteattr(what)}{rest}')
        if not choices:
            return key(name), start + " />"
        lines = [start + ">"] + [f'      <choice name={quoteattr(shown)} value={quoteattr(saved)} />' for shown, saved in choices]
        return key(name), "\n".join(lines + ["    </feature>"])

    palette = [(name, name) for name in COLOURS]
    out = [item(name, label, what, ' preset="switchon"') for name, (label, what) in SWITCHES.items()]
    steps = [(f"{n}%", str(n)) for n in range(0, 101, 10)]   # a list: a real slider shows 0 until first moved
    out += [item(name, label, what, "", steps) for name, (label, what) in SLIDERS.items()]
    out.append(item("colour-menus", "COLOUR IN THE MENUS", "The lights' colour while no game runs.", "",
                    [("From the picture", "picture")] + palette))
    out.append(item("colour-all", "ALL LIGHTS", "One colour for every light, used when not following the game.", "", palette))
    for zone, name in ZONES.items():
        out.append(item(f"colour-{zone}", name.upper(), f"The colour of the {name.lower()}, used when not following the game.", "", palette))
    out.append(item("effect-case", "CASE EFFECT", "What the case lights do.", "", [(e, e) for e in EFFECTS["case"]]))
    out.append(item("effect-ram", "MEMORY EFFECT", "What the memory lights do.", "", [(e, e) for e in EFFECTS["ram"]]))
    out.append(item("speed", "EFFECT SPEED", "How fast a moving effect goes.", "", [("Slow", "0"), ("Medium", "50"), ("Fast", "100")]))
    out.append(item("dim-min", "BREATHING FADES DOWN TO", "The dimmest point of the Breathing effect.", "",
                    [(f"{n}%", str(n)) for n in (0, 10, 25, 50)]))
    out.append(item("dim-max", "BREATHING RISES UP TO", "The brightest point of the Breathing effect.", "",
                    [(f"{n}%", str(n)) for n in (50, 75, 100)]))
    out.append(item("lcd-fit", "PICTURE FIT", "Fill crops the picture to the round screen; fit shows all of it.", "",
                    [("Fill the screen", "fill"), ("Show all of it", "fit")]))
    out.append(item("picture", "SCREEN PICTURE", "What the cooler's screen shows in the menus. Your pictures go in "
                    "system/configs/omen-lights/pictures.", "", [("The theme's", "theme")] + [(p.stem, str(p)) for p in pictures()]))
    return out


def changed(chosen: dict[str, str]) -> None:
    """Carry what was chosen in Batocera's menu over into the lights' settings file.

    Only what is new there: the Guide menu changes the same settings, and a choice in Batocera's
    menu that we have already carried over must not undo a later change made elsewhere. What we
    have carried over is noted in the file under "_seen" (the lights program ignores it)."""
    values = load()
    seen = dict(values.get("_seen", {}))
    fresh = {name: value for name, value in chosen.items()
             if name.startswith("omen_") and value not in ("", "auto") and seen.get(name) != value}
    if not fresh:
        return

    def picked(name: str) -> str:
        return fresh.get(key(name), "")

    todo = []
    for name in SWITCHES:
        if picked(name):
            todo.append(["set", name, "on" if picked(name) in ON else "off"])
    for name in SLIDERS:
        if picked(name):
            try:
                todo.append(["set", name, str(max(0, min(100, int(float(picked(name))))))])
            except ValueError:
                pass
    if picked("colour-menus"):
        todo.append(["colour", "menus", picked("colour-menus")])
    if picked("colour-all"):
        todo.append(["colour", "all", picked("colour-all")])
    for zone in ZONES:
        if picked(f"colour-{zone}"):
            todo.append(["colour", zone, picked(f"colour-{zone}")])
    for which in ("case", "ram"):
        if picked(f"effect-{which}"):
            todo.append(["effect", which, picked(f"effect-{which}")])
    if picked("speed"):
        todo.append(["speed", picked("speed")])
    for end in ("min", "max"):
        if picked(f"dim-{end}"):
            todo.append(["dim", end, picked(f"dim-{end}")])
    if picked("lcd-fit"):
        todo.append(["set", "lcd-fit", picked("lcd-fit")])
    if picked("picture"):
        todo.append(["picture", picked("picture")])
    for command in todo:
        try:
            run(command)
        except (IndexError, KeyError, ValueError):
            continue
    values = load()
    seen.update(fresh)
    values["_seen"] = seen
    save(values)


def main(argv: list[str]) -> int:
    try:
        said = run(argv)
    except (IndexError, KeyError, ValueError) as error:
        print(f"startmenu_omen: {error}", file=sys.stderr)
        print(__doc__, file=sys.stderr)
        return 2
    if said:
        print(said)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
