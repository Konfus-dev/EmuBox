#!/usr/bin/env python3
"""EmuBox's settings in Batocera's own menu: Start > Game Settings > EmuBox.

    startmenu.py                 write the menu entries (the emubox service does, at boot and shutdown)
    startmenu.py --root <drive>  the same for a drive plugged into a PC (the installer does)

Batocera's menu program takes extra settings from files named es_features_*.cfg
beside its own settings; what you choose is saved in batocera.conf as
global.<name>. This writes es_features_emubox.cfg from the list in settings.py,
with the sound sets found on the drive as the choices for "sound set". The menu
program reads the file when it starts, so a new sound set is offered from the
next start.

Other components add their own sub-menu with a file lib/startmenu_<name>.py that has
    features() -> [(name, xml)]     settings, as <feature ...> elements
    changed(conf) -> None           called when batocera.conf changes ({key: value} of its global.* lines)
"""
from __future__ import annotations

import glob
import importlib.util
import os
import sys
from pathlib import Path
from xml.sax.saxutils import quoteattr

import menusounds
import settings

HERE = Path(__file__).resolve().parent
FILE = "system/configs/emulationstation/es_features_emubox.cfg"
MARK = "<!-- written by EmuBox (lib/startmenu.py); your choices are in batocera.conf -->"
GROUP = "EMUBOX"
SUBMENUS = {"ui.": "MENU SOUNDS", "": "APPS"}   # by the start of a setting's name


def feature(value: str, name: str, submenu: str, description: str, kind: str = "switch",
            choices: list[tuple[str, str]] | None = None, group: str = GROUP) -> str:
    """One setting as Batocera's menu wants it described."""
    start = (f'    <feature name={quoteattr(name)} submenu={quoteattr(submenu)} group={quoteattr(group)} '
             f'value={quoteattr(value)} description={quoteattr(description)}')
    if kind == "switch":
        return start + ' preset="switchon" />'
    if kind == "slider":   # as a list of steps: a real slider shows 0 until it is first moved, which misleads
        choices = [(f"{n}%", str(n)) for n in range(0, 101, 10)]
    lines = [start + ">"]
    lines += [f'      <choice name={quoteattr(label)} value={quoteattr(saved)} />' for label, saved in choices or []]
    return "\n".join(lines + ["    </feature>"])


def add_ons(folder: Path = HERE) -> list:
    found = []
    for path in sorted(glob.glob(str(folder / "startmenu_*.py"))):
        try:
            spec = importlib.util.spec_from_file_location(os.path.basename(path)[:-3], path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            found.append(module)
        except Exception as error:   # noqa: BLE001  one broken add-on must not cost the whole menu
            print(f"startmenu: {path} was left out: {error}", file=sys.stderr)
    return found


def ascii_label(words: str) -> str:
    import unicodedata
    plain = unicodedata.normalize("NFKD", words).encode("ascii", "ignore").decode()
    return plain.strip() or "Sound set"


def build(sound_sets: list[str], extra: list[tuple[str, str]]) -> str:
    """The whole file. `extra` is [(setting name, <feature> xml)] from the add-ons."""
    own: list[tuple[str, str]] = []
    for name, (_, label, kind, what) in settings.KNOWN.items():
        if not kind:
            continue
        submenu = next(title for start, title in SUBMENUS.items() if name.startswith(start))
        # Labels in plain letters: Batocera's menu can crash on others ("Série" is shown as "Serie").
        choices = [(ascii_label(one), one) for one in sound_sets] if name == "ui.sound_set" else None
        own.append((settings.conf_key(name), feature(settings.conf_key(name), label, submenu, what, kind, choices)))
    every = own + extra
    return "\n".join(
        ['<?xml version="1.0"?>', MARK, "<features>", "  <sharedFeatures>"] + [xml for _, xml in every] +
        ["  </sharedFeatures>", "  <globalFeatures>"] + [f'    <sharedFeature value={quoteattr(name)} />' for name, _ in every] +
        ["  </globalFeatures>", "</features>", ""])


def write(root: Path = Path("/userdata")) -> bool:
    """Write the file on the drive at `root`. True when it changed."""
    es = root / "system/configs/emulationstation/es_settings.cfg"
    try:
        text = es.read_text(errors="replace")
    except OSError:
        text = ""
    themes = (root / "themes",) + ((Path("/usr/share/emulationstation/themes"),) if root == Path("/userdata") else ())
    names = list(menusounds.sets(text, root / "system/configs/emubox/sounds", themes)) or [menusounds.BUILT_IN]
    if menusounds.BUILT_IN not in names:
        names.insert(0, menusounds.BUILT_IN)
    extra = [pair for module in add_ons() for pair in module.features()]
    fresh, file = build(names, extra), root / FILE
    try:
        if file.is_file() and file.read_text() == fresh:
            return False
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(fresh)
        return True
    except OSError:
        return False


class Watch:
    """Notices when batocera.conf changes (a setting was chosen in the menu) and passes it on."""

    def __init__(self, conf: Path = settings.BATOCERA):
        self.conf, self.seen, self.modules = conf, None, None

    def look(self) -> bool:
        try:
            stamp = self.conf.stat().st_mtime
        except OSError:
            return False
        if stamp == self.seen:
            return False
        first, self.seen = self.seen is None, stamp
        if self.modules is None:
            self.modules = add_ons()
        try:
            chosen = settings.from_batocera(self.conf.read_text(errors="replace"))
        except OSError:
            return False
        for module in self.modules:
            try:
                module.changed(chosen)
            except Exception as error:   # noqa: BLE001
                print(f"startmenu: {module.__name__}: {error}", file=sys.stderr)
        if not first:
            menusounds.apply()   # the sound set may have changed: its start-up film goes with it
        return True


def main(argv: list[str]) -> int:
    root = Path(argv[argv.index("--root") + 1]) if "--root" in argv else Path("/userdata")
    write(root)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
