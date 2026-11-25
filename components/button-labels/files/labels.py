#!/usr/bin/env python3
"""Xbox button labels in Batocera's standalone Nintendo emulators (3DS, Switch, Wii U, GameCube, DS).

Batocera binds the Xbox pad by position, so in Nintendo games the Xbox A button is the console's B.
For RetroArch systems the component sets that right in batocera.conf. The standalone emulators get
their buttons from tables in Batocera's own launcher code, rewritten at every launch, with no
setting for it; this swaps A/B and X/Y in those tables, in memory (Batocera's system is read-only
on disk and comes back as it was at the next start). Run at every start by the emubox_buttonlabels
service, before any game.

Each table is changed only where it matches exactly what was checked (Batocera 43). When an update
changes one, that emulator is left alone and the log says so; nothing is guessed.

    labels.py            apply (once per start)
    labels.py --check    say what would happen, change nothing
"""
from __future__ import annotations

import sys
from pathlib import Path

GENERATORS = Path("/usr/lib/python3.12/site-packages/configgen/generators")
MARK = "# EMUBOX: Xbox button labels"
LOG = Path("/var/log/emubox-boot.log")

# file: (the start of the table, [(line as Batocera has it, line with the label's button)])
PATCHES = {
    "azahar/azaharGenerator.py": ('"button_a":', [
        ('"button_a":      "a",', '"button_a":      "b",'), ('"button_b":      "b",', '"button_b":      "a",'),
        ('"button_x":      "x",', '"button_x":      "y",'), ('"button_y":      "y",', '"button_y":      "x",')]),
    "citron/citronGenerator.py": ('"button_a":', [
        ('"button_a":      "a",', '"button_a":      "b",'), ('"button_b":      "b",', '"button_b":      "a",'),
        ('"button_x":      "x",', '"button_x":      "y",'), ('"button_y":      "y",', '"button_y":      "x",')]),
    "melonds/melondsGenerator.py": ('"a":        "A",', [
        ('"a":        "A",', '"a":        "B",'), ('"b":        "B",', '"b":        "A",'),
        ('"x":        "X",', '"x":        "Y",'), ('"y":        "Y"', '"y":        "X"')]),
    "dolphin/dolphinControllers.py": ("gamecubeMapping = {", [
        ("'b':             'Buttons/B',", "'b':             'Buttons/A',"), ("'a':             'Buttons/A',", "'a':             'Buttons/B',"),
        ("'y':             'Buttons/Y',", "'y':             'Buttons/X',"), ("'x':             'Buttons/X',", "'x':             'Buttons/Y',")]),
    "cemu/cemuControllers.py": ("buttonMappingsSDL = {", [
        ('"1":  "1",', '"1":  "0",'), ('"2":  "0",', '"2":  "1",'), ('"3":  "3",', '"3":  "2",'), ('"4":  "2",', '"4":  "3",')]),
}


def patched(text: str, start: str, pairs: list[tuple[str, str]]) -> str | None:
    """The file with the table's lines swapped, or None when the table is not what was checked.
    Only the table that begins at `start` (up to its closing brace) is touched."""
    begin = text.find(start)
    if begin < 0:
        return None
    end = text.find("}", begin)
    table = text[begin:end]
    if any(table.count(old) != 1 for old, _new in pairs):
        return None
    for old, new in pairs:   # every line keeps its own key, so one swap can never match another's line
        table = table.replace(old, new, 1)
    return text[:begin] + table + text[end:] + ("" if text.endswith("\n") else "\n") + MARK + "\n"


def apply(generators: Path = GENERATORS, check: bool = False) -> list[str]:
    notes = []
    for name, (start, pairs) in PATCHES.items():
        path = generators / name
        try:
            text = path.read_text()
        except OSError:
            notes.append(f"{name}: not there, left alone")
            continue
        if MARK in text:
            notes.append(f"{name}: already done")
            continue
        new = patched(text, start, pairs)
        if new is None:
            notes.append(f"{name}: not as expected (a Batocera update?), left alone")
            continue
        if not check:
            path.write_text(new)
        notes.append(f"{name}: labels {'would be ' if check else ''}set")
    return notes


def main(argv: list[str]) -> int:
    notes = apply(check="--check" in argv)
    text = "".join(f"button labels: {n}\n" for n in notes)
    print(text, end="")
    if "--check" not in argv:
        try:
            with LOG.open("a") as log:
                log.write(text)
        except OSError:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
