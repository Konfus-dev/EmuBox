#!/usr/bin/env python3
"""How full the drive is: for the indicator in the menus and for anything about to download.

    space.py                          print "41.2 GB free of 58.0 GB"
    space.py --theme                  redraw the indicator at the top right of the menus
    space.py --need <bytes> [folder]  exit 1 with a message when that much would not fit

The indicator is a small file the theme includes (space.xml in the theme's
folder). The menu program reads it when it starts and whenever the game lists
are refreshed, so it is redrawn at boot, at shutdown and after every install.
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

DATA = "/userdata"
THEMES = "/userdata/themes"
RESERVE = 300 * 1024 * 1024   # never fill the drive to the brim: saves and settings live on it too
NEARLY_FULL = 0.90
MARK = "<!-- drawn by space.py -->"

INDICATOR = """<?xml version="1.0"?>
{mark}
<theme>
  <formatVersion>7</formatVersion>
  <!-- In the top row, left of the clock: a bar that fills as the drive does, with what is free right beside it. -->
  <view name="system, basic, detailed, video, grid">
    <image name="spaceTrack" extra="static">
      <path>./art/white.png</path>
      <color>124a10ff</color>
      <pos>0.718 0.0335</pos>
      <origin>0 0</origin>
      <size>0.055 0.007</size>
      <zIndex>70</zIndex>
    </image>
    <image name="spaceFill" extra="static">
      <path>./art/white.png</path>
      <color>{colour}</color>
      <pos>0.718 0.0335</pos>
      <origin>0 0</origin>
      <size>{width:.4f} 0.007</size>
      <zIndex>71</zIndex>
    </image>
    <text name="spaceText" extra="static">
      <text>{words}</text>
      <fontPath>./art/fonts/Rajdhani-Medium.ttf</fontPath>
      <fontSize>0.022</fontSize>
      <color>{text_colour}</color>
      <pos>0.781 0.012</pos>
      <origin>0 0</origin>
      <size>0.085 0.05</size>
      <alignment>left</alignment>
      <verticalAlignment>center</verticalAlignment>
      <zIndex>71</zIndex>
    </text>
  </view>
</theme>
"""


def usage(folder: str | os.PathLike = DATA) -> tuple[int, int]:
    """(total, free) bytes on the drive that holds the folder; zeros when it cannot be read."""
    path = Path(folder)
    while not path.exists() and path != path.parent:
        path = path.parent
    try:
        disk = shutil.disk_usage(path)
    except OSError:
        return 0, 0
    return disk.total, disk.free


def size(count: float) -> str:
    """A number of bytes the way people say it: 740 MB, 1.4 GB, 58 GB."""
    for unit, step in (("TB", 1024 ** 4), ("GB", 1024 ** 3), ("MB", 1024 ** 2), ("KB", 1024)):
        if count >= step:
            amount = count / step
            return f"{amount:.1f} {unit}" if amount < 10 and unit in ("TB", "GB") else f"{amount:.0f} {unit}"
    return f"{int(count)} bytes"


def summary(folder: str | os.PathLike = DATA) -> str:
    total, free = usage(folder)
    return f"{size(free)} free of {size(total)}" if total else ""


def no_room(needed: int, folder: str | os.PathLike = DATA, what: str = "this") -> str:
    """Why `needed` more bytes would not fit on the folder's drive, or "" when they do."""
    total, free = usage(folder)
    if not total or needed + RESERVE <= free:
        return ""
    if free <= RESERVE:
        return f"The drive is full ({size(free)} free). Remove some games to make room for {what}."
    return f"Not enough room for {what}: it needs {size(needed)} and {size(max(0, free - RESERVE))} can be used."


def draw_indicator(themes: str | os.PathLike = THEMES, folder: str | os.PathLike = DATA) -> list[Path]:
    """Rewrite the indicator in every theme that has one. Gives the files written."""
    total, free = usage(folder)
    if not total:
        return []
    full = 1 - free / total
    nearly = full >= NEARLY_FULL or free <= RESERVE
    text = INDICATOR.format(
        mark=MARK, width=max(0.002, 0.055 * full), words=f"{size(free)} FREE".upper(),
        colour="ff7a3cff" if nearly else "c8f03cff", text_colour="ffb08aff" if nearly else "8fc878ff")
    written = []
    try:
        candidates = sorted(Path(themes).glob("*/space.xml"))
    except OSError:
        return []
    for file in candidates:
        try:
            if MARK in file.read_text():   # only ever a file of ours
                file.write_text(text)
                written.append(file)
        except OSError:
            continue   # a full or read-only drive: the old picture stays
    return written


def main(argv: list[str]) -> int:
    if not argv:
        print(summary())
    elif argv[0] == "--theme":
        draw_indicator()
    elif argv[0] == "--need" and len(argv) in (2, 3) and argv[1].isdigit():
        problem = no_room(int(argv[1]), argv[2] if len(argv) == 3 else DATA)
        if problem:
            print(problem)
            return 1
    else:
        print(__doc__, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
