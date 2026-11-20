#!/usr/bin/env python3
"""RGB Hub: the lights' settings in Batocera's menu, Start > Game Settings > RGB HUB.

The lights program, RGB Hub (github.com/Konfus-dev/RGB-Hub, once called OMEN Lights),
drives two devices: the OMEN PC (its cooler screen, case and memory lights) and the
IQUNIX keyboard. It acts on one small file, /userdata/system/configs/rgb-hub/settings.json,
the moment it is saved. This is a front end for that file: `features()` describes the
settings to Batocera's menu and `changed()` carries your choices over. The same can be
done by hand:

    startmenu_rgbhub.py is <setting>                  print "true" when a yes/no setting is on
    startmenu_rgbhub.py get <setting>                 print a setting
    startmenu_rgbhub.py set <setting> <value>         on/off, a number, or text
    startmenu_rgbhub.py step <setting> <+/-n>         move a percentage, kept within 0..100
  Settings kept per device (device-enabled, device-brightness, auto-devices) take the device:
    startmenu_rgbhub.py is device-enabled <pc|keyboard>
    startmenu_rgbhub.py is auto-devices <all|pc|keyboard>       "all": true only when both are on
    startmenu_rgbhub.py get device-brightness <pc|keyboard>
    startmenu_rgbhub.py set device-enabled <pc|keyboard|all> <on|off>
    startmenu_rgbhub.py step device-brightness <pc|keyboard|all> <+/-n>
    startmenu_rgbhub.py colour <where> <colour>       where: menus, all, or a zone ("RAM/Stick 1");
                                                 colour: a name below, #RRGGBB, or "picture" (menus only)
    startmenu_rgbhub.py colour-of <where>
    startmenu_rgbhub.py effect <case|ram|keyboard|all> <Static|Breathing|Rainbow|Off|Wave|Rain|...>
    startmenu_rgbhub.py effect-of <case|ram|keyboard>
    startmenu_rgbhub.py speed <0..100> / speed-of
    startmenu_rgbhub.py dim <min|max> <0..100> / dim-of <min|max>    how far Breathing fades
    startmenu_rgbhub.py picture <file|theme> / picture-of             what the cooler's screen shows
    startmenu_rgbhub.py default save                  the look now becomes the Default (shown when
                                                 the program stops, as Batocera shuts down)
    startmenu_rgbhub.py default load                  go back to the Default look
    startmenu_rgbhub.py reset                         everything back to how it came
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path


HOME = Path(os.environ.get("RGB_HUB_HOME") or os.environ.get("OMEN_LIGHTS_HOME") or "/userdata/system/configs/rgb-hub")
FILE = HOME / "settings.json"
# Where the settings were before the rename. The lights program moves that folder here when it
# first starts, but only while this one is missing: until then the settings are read and saved there.
OLD_HOME = None if {"RGB_HUB_HOME", "OMEN_LIGHTS_HOME"} & set(os.environ) else Path("/userdata/system/configs/omen-lights")
PICTURES = HOME / "pictures"

# The hub's devices, by the word used here.
PC, KEYBOARD = "OMEN-PC", "IQUNIX-KEYBOARD"
HUB = {"pc": PC, "keyboard": KEYBOARD}
# The lights inside them, as the lights program names them.
CASE, RAM, KEYS = "HP Omen 30L", "RAM", "IQUNIX MG65"
DEVICES = {"case": CASE, "ram": RAM, "keyboard": KEYS}
PC_ZONES = {   # as the lights program names them: what to call them here
    f"{CASE}/Omen Logo": "Front logo", f"{CASE}/Front Top Fan": "Top fan",
    f"{CASE}/Front Middle Fan": "Middle fan", f"{CASE}/Front Bottom Fan": "Bottom fan",
    f"{RAM}/Stick 1": "Left memory stick", f"{RAM}/Stick 2": "Right memory stick",
}
KEYBOARD_ZONE = f"{KEYS}/All keys"
ZONES = {**PC_ZONES, KEYBOARD_ZONE: "Keyboard"}
# The keyboard's effects have no names yet: its firmware only numbers them.
EFFECTS = {"case": ("Static", "Breathing"), "ram": ("Static", "Breathing", "Rainbow", "Off"),
           # as RGB-Hub names them (service/rgbhub/iqunix_mg65.py there)
           "keyboard": ("Static", "Wave", "Colour cloud", "Vortex", "Mixed colours", "Breathe", "Slowly off",
                        "Stone", "Laser", "Starry", "Flowers opening", "Traverse", "Wave bar", "Meteor", "Rain",
                        "Scan", "Colour on keypress", "Centre spread")}
COLOURS = {
    "Green": "#3CE61E", "Lime": "#C8F03C", "White": "#FFFFFF", "Warm white": "#FFD9A0", "Red": "#FF1A1A",
    "Orange": "#FF7A00", "Yellow": "#FFD500", "Cyan": "#00E5FF", "Blue": "#1E5BFF", "Purple": "#9B30FF",
    "Pink": "#FF3DBB",
}
# What each setting is when the file does not mention it (the lights program's own defaults on Batocera).
DEFAULTS = {
    "device-enabled": {}, "device-brightness": {}, "auto-devices": {PC: True, KEYBOARD: True},
    "device-modes": {RAM: "Static"}, "zone-colours": {},
    "device-speeds": {}, "device-min-brightness": {}, "device-max-brightness": {},
    "lcd-enabled": True, "lcd-brightness": 80, "lcd-image": "", "lcd-fit": "fill",
    "auto-lights": True, "auto-lcd": True, "auto-idle-image": "", "auto-idle-colour": "",
    "default-look": "{}", "default-action": "",
}
# Settings kept per device, and what a device missing from the table has.
PER_DEVICE = {"device-enabled": True, "device-brightness": 100, "auto-devices": False}
# The names these had before the lights program kept them per device, still understood.
OLD_NAMES = {"lights-enabled": ("device-enabled", "pc"), "lights-brightness": ("device-brightness", "pc"),
             "auto-enabled": ("auto-devices", "all")}
ON = ("on", "1", "true", "yes")


def where() -> Path:
    """The settings file: ours, or the old one while it waits to be moved here."""
    if OLD_HOME is not None and OLD_HOME.is_dir() and not HOME.exists():
        return OLD_HOME / "settings.json"
    return FILE


def load() -> dict:
    try:
        found = json.loads(where().read_text())
        return found if isinstance(found, dict) else {}
    except (OSError, ValueError):
        return {}


def save(values: dict) -> None:
    """Written in one go: the lights program reads the file the moment it changes."""
    file = where()
    file.parent.mkdir(parents=True, exist_ok=True)
    fresh = file.with_suffix(".new")
    fresh.write_text(json.dumps(values, indent=4) + "\n")
    os.replace(fresh, file)


def get(name: str):
    return load().get(name, DEFAULTS.get(name, ""))


def put(name: str, value) -> None:
    values = load()
    values[name] = value
    save(values)


def clamp(number) -> int:
    return max(0, min(100, int(number)))


def typed(name: str, text: str):
    """What was typed, as the kind of value the setting holds."""
    kind = PER_DEVICE.get(name, DEFAULTS.get(name))
    if isinstance(kind, bool):
        return text.lower() in ON
    if isinstance(kind, int):
        return clamp(text)
    return text


def table(name: str, values: dict) -> dict:
    found = values.get(name)
    return dict(found if isinstance(found, dict) else DEFAULTS[name])


def change_table(name: str, keys: list[str], change) -> None:
    """Change some entries of a table setting; `change` is given each one's value now.
    The whole table is written: one not in the file at all is taken from DEFAULTS first."""
    values = load()
    entries = table(name, values)
    for key in keys:
        entries[key] = change(entries.get(key, PER_DEVICE.get(name)))
    values[name] = entries
    save(values)


def hub_devices(which: str) -> list[str]:
    return [HUB[word] for word in (HUB if which == "all" else [which])]


def of_hub(name: str, which: str) -> list:
    entries = table(name, load())
    return [entries.get(device, PER_DEVICE[name]) for device in hub_devices(which)]


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
    change_table(name, [DEVICES[key] for key in (DEVICES if which == "all" else [which])], lambda _now: value)


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
    if action in ("is", "get", "set", "step") and rest and rest[0] in OLD_NAMES:
        rest = list(OLD_NAMES[rest[0]]) + rest[1:]
    per_device = action in ("is", "get", "set", "step") and rest[0] in PER_DEVICE
    if action == "is":
        on = all(value is True for value in of_hub(rest[0], rest[1])) if per_device else get(rest[0]) is True
        return "true" if on else ""
    if action == "get":
        return str(of_hub(rest[0], rest[1])[0] if per_device else get(rest[0]))
    if action == "set" and per_device:
        value = typed(rest[0], rest[2])
        change_table(rest[0], hub_devices(rest[1]), lambda _now: value)
    elif action == "set":
        put(rest[0], typed(rest[0], rest[1]))
    elif action == "step" and per_device:
        change_table(rest[0], hub_devices(rest[1]), lambda now: clamp(int(now) + int(rest[2])))
    elif action == "step":
        put(rest[0], clamp(int(get(rest[0])) + int(rest[1])))
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
        for_devices("device-speeds", "all", clamp(rest[0]))
    elif action == "speed-of":
        return {0: "Slow", 50: "Medium", 100: "Fast"}.get(of_device("device-speeds", "case", 50), "Custom")
    elif action == "dim":
        for_devices(f"device-{rest[0]}-brightness", "all", clamp(rest[1]))
    elif action == "dim-of":
        return f"{of_device(f'device-{rest[0]}-brightness', 'case', 0 if rest[0] == 'min' else 100)}%"
    elif action == "picture":
        values = load()
        values["lcd-image"] = values["auto-idle-image"] = "" if rest[0] == "theme" else rest[0]
        save(values)
    elif action == "picture-of":
        return Path(get("auto-idle-image") or get("lcd-image")).stem or "The theme's"
    elif action == "default":
        if rest[0] not in ("save", "load"):
            raise ValueError(f"default save or default load, not {rest[0]}")
        put("default-action", rest[0])   # the lights program does it, then empties it again
    elif action == "reset":
        save({name: value for name, value in load().items() if name.startswith("_")})   # our own notes stay
    else:
        raise IndexError(action)
    return ""


# --- Batocera's Start menu ---------------------------------------------------------
# Start > Game Settings > RGB HUB. Batocera saves each choice in batocera.conf as
# global.rgbhub_<name>; `changed` (called by the console's startmenu.py whenever that file
# changes) carries them over into settings.json, which the lights program acts on.
# Choices saved as global.omen_<name> by the menu before the rename are left alone: their
# settings have been renamed or moved since, and the lights program carried them over itself.

SUBMENU, GROUP, PREFIX = "RGB HUB", "EMUBOX", "rgbhub_"
PER_DEVICE_SWITCHES = {   # (setting, device word): (label, what it does)
    ("auto-devices", "all"): ("FOLLOW THE GAME", "Every device takes the running game's colours (the cooler's screen "
                              "its artwork). Sets the two rows below."),
    ("auto-devices", "pc"): ("PC FOLLOWS THE GAME", "The OMEN PC's lights and cooler screen follow the game."),
    ("auto-devices", "keyboard"): ("KEYBOARD FOLLOWS THE GAME", "The keyboard's lights follow the game."),
    ("device-enabled", "pc"): ("PC LIGHTS", "The case and memory lights."),
    ("device-enabled", "keyboard"): ("KEYBOARD LIGHTS", "The keyboard's lights."),
}
PER_DEVICE_SLIDERS = {("device-brightness", "pc"): ("PC LIGHT BRIGHTNESS", "How bright the case and memory lights are."),
                      ("device-brightness", "keyboard"): ("KEYBOARD BRIGHTNESS", "How bright the keyboard's lights are.")}
SWITCHES = {   # setting: (label, what it does)
    "auto-lights": ("PC LIGHTS FOLLOW IT", "With the PC following the game: let its lights follow."),
    "auto-lcd": ("COOLER SCREEN FOLLOWS IT", "With the PC following the game: let the cooler's screen follow."),
    "lcd-enabled": ("COOLER SCREEN", "The screen on the cooler. Off shows a black screen."),
}
SLIDERS = {"lcd-brightness": ("SCREEN BRIGHTNESS", "How bright the cooler's screen is.")}
DEFAULT_CHOICES = [("Leave it", "none"), ("Save the current look", "save"), ("Go back to it", "load")]


def key(name: str) -> str:
    return PREFIX + name.replace("-", "_").replace("/", "_").replace(" ", "_").lower()


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
    steps = [(f"{n}%", str(n)) for n in range(0, 101, 10)]   # a list: a real slider shows 0 until first moved
    out = [item(f"{name}-{which}", label, what, ' preset="switchon"') for (name, which), (label, what) in PER_DEVICE_SWITCHES.items()]
    out += [item(f"{name}-{which}", label, what, "", steps) for (name, which), (label, what) in PER_DEVICE_SLIDERS.items()]
    out += [item(name, label, what, ' preset="switchon"') for name, (label, what) in SWITCHES.items()]
    out += [item(name, label, what, "", steps) for name, (label, what) in SLIDERS.items()]
    out.append(item("colour-menus", "COLOUR IN THE MENUS", "The lights' colour while no game runs.", "",
                    [("From the picture", "picture")] + palette))
    out.append(item("colour-all", "ALL LIGHTS", "One colour for every light, the keyboard's too, used when not following "
                    "the game.", "", palette))
    for zone, name in PC_ZONES.items():
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
                    "system/configs/rgb-hub/pictures.", "", [("The theme's", "theme")] + [(p.stem, str(p)) for p in pictures()]))
    out.append(item(f"colour-{KEYBOARD_ZONE}", "KEYBOARD COLOUR", "The colour of the keyboard's keys, used when not "
                    "following the game.", "", palette))
    out.append(item("effect-keyboard", "KEYBOARD EFFECT", "What the keyboard's lights do. Its effects are only numbered "
                    "for now: try them.", "", [(e, e) for e in EFFECTS["keyboard"]]))
    out.append(item("default", "DEFAULT LOOK", "The look every device is put back to when Batocera shuts down, so what "
                    "starts next does not show the last game. Save makes the look now the Default; go back shows it "
                    "again. To do the same again later, pick Leave it first.", "", DEFAULT_CHOICES))
    return out


def number(text: str) -> str:
    """Batocera saves a number from a list as typed, or as 40.000000 from a slider."""
    try:
        return str(clamp(float(text)))
    except ValueError:
        return text


def changed(chosen: dict[str, str]) -> None:
    """Carry what was chosen in Batocera's menu over into the lights' settings file.

    Only what is new there: the Guide menu changes the same settings, and a choice in Batocera's
    menu that we have already carried over must not undo a later change made elsewhere. What we
    have carried over is noted in the file under "_seen" (the lights program keeps it, unused).

    DEFAULT LOOK is an action, not a setting: Batocera only tells us of a choice that differs
    from the one before, so picking Save twice in a row reaches us once. Once it is set back
    (to Leave it, or AUTO), it is forgotten here, and the next Save is new again."""
    values = load()
    seen = {name: value for name, value in values.get("_seen", {}).items() if name.startswith(PREFIX)}
    action = chosen.get(key("default"), "")
    if action not in ("save", "load"):
        seen.pop(key("default"), None)
    fresh = {name: value for name, value in chosen.items()
             if name.startswith(PREFIX) and value not in ("", "auto") and seen.get(name) != value}
    if not fresh and seen == values.get("_seen", {}):
        return

    def picked(name: str) -> str:
        return fresh.get(key(name), "")

    todo = []
    for (name, which) in PER_DEVICE_SWITCHES:   # "all" first: a row for one device then has the last word
        if picked(f"{name}-{which}"):
            todo.append(["set", name, which, "on" if picked(f"{name}-{which}") in ON else "off"])
    for (name, which) in PER_DEVICE_SLIDERS:
        if picked(f"{name}-{which}"):
            todo.append(["set", name, which, number(picked(f"{name}-{which}"))])
    for name in SWITCHES:
        if picked(name):
            todo.append(["set", name, "on" if picked(name) in ON else "off"])
    for name in SLIDERS:
        if picked(name):
            todo.append(["set", name, number(picked(name))])
    if picked("colour-menus"):
        todo.append(["colour", "menus", picked("colour-menus")])
    if picked("colour-all"):
        todo.append(["colour", "all", picked("colour-all")])
    for zone in ZONES:
        if picked(f"colour-{zone}"):
            todo.append(["colour", zone, picked(f"colour-{zone}")])
    for which in DEVICES:
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
    if picked("default") in ("save", "load"):
        todo.append(["default", picked("default")])   # last: what to save is the look just chosen
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
        print(f"startmenu_rgbhub: {error}", file=sys.stderr)
        print(__doc__, file=sys.stderr)
        return 2
    if said:
        print(said)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
