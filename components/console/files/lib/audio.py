#!/usr/bin/env python3
"""Keeps sounds out of each other's way.

    audio.py           run until stopped (the emubox service starts it at boot)
    audio.py --once    look once, act, and print what was done

Two rules, each with a switch in the in-game menu's Apps tab (see settings.py):

  - While a music app is playing, the menus are silent: Batocera's menu music
    does not play over yours. (Its menu sounds come out of the same pipe, so
    they are silent too.) They come back when the music pauses or stops.
  - While an app is using the microphone (a call), music and the menus drop to
    a fifth of their volume, and come back when the call ends.

A music app is one whose app.json says "player": true. Everything here is
undone when it no longer applies, and only what this program changed is put back.
"""
from __future__ import annotations

import glob
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import settings

os.environ.setdefault("XDG_RUNTIME_DIR", "/var/run")
ROOT = Path(__file__).resolve().parent.parent
MENU = "emulationstation"
QUIET_FLAG = Path("/var/run/emubox/menus-quiet")
EVERY_S = 2.0


def player_words(apps: str | os.PathLike | None = None) -> list[str]:
    """Words that mark a sound as coming from a music app: "chrome" for com.google.Chrome."""
    words = []
    for path in sorted(glob.glob(os.path.join(apps or ROOT / "apps", "*", "app.json"))):
        try:
            with open(path) as file:
                app = json.load(file)
        except (OSError, ValueError):
            continue
        if app.get("player") and app.get("flatpak"):
            words.append(app["flatpak"].rsplit(".", 1)[-1].lower())
    return words


def who(stream: dict) -> str:
    """Everything a stream says about the program behind it, in lower case."""
    properties = stream.get("properties", {})
    return " ".join(str(properties.get(key, "")) for key in (
        "application.name", "application.process.binary", "application.id", "node.name")).lower()


def volume(stream: dict) -> int:
    for channel in stream.get("volume", {}).values():
        try:
            return int(str(channel.get("value_percent", "100%")).rstrip("%"))
        except (ValueError, AttributeError):
            break
    return 100


def plan(playing: list[dict], recording: list[dict], music_words: list[str], switches: dict[str, str],
         state: dict) -> list[list[str]]:
    """The pactl commands that bring the sound in line with the rules.

    `playing` and `recording` are pactl's lists of sink inputs and source outputs.
    `state` remembers what we changed: {"muted": {index}, "lowered": {index: volume before}}."""
    muted, lowered = state.setdefault("muted", set()), state.setdefault("lowered", {})
    on = lambda name: switches.get(name, "").lower() in settings.ON   # noqa: E731
    commands: list[list[str]] = []
    here = {stream["index"] for stream in playing}
    muted &= here                       # streams that ended take their changes with them
    for index in set(lowered) - here:
        del lowered[index]

    callers = [who(stream) for stream in recording if "peak detect" not in str(stream.get("properties", {})).lower()]
    in_call = bool(callers)
    menus = [s for s in playing if MENU in who(s)]
    music = [s for s in playing if MENU not in who(s) and any(word in who(s) for word in music_words)]
    music_sounding = any(not s.get("corked") for s in music)

    for stream in menus:                # rule one: the menus are silent under your music
        index = stream["index"]
        if on("music.quiet_menu") and music_sounding:
            if not stream.get("mute"):
                commands.append(["set-sink-input-mute", str(index), "1"])
                muted.add(index)
        elif index in muted:
            commands.append(["set-sink-input-mute", str(index), "0"])
            muted.discard(index)

    try:
        level = max(0, min(100, int(switches.get("call.music_volume", "20"))))
    except ValueError:
        level = 20
    for stream in music + menus:        # rule two: music makes way for a call
        index = stream["index"]
        if on("call.lower_music") and in_call:
            if index not in lowered and volume(stream) > level:
                lowered[index] = volume(stream)
                commands.append(["set-sink-input-volume", str(index), f"{level}%"])
        elif index in lowered:
            commands.append(["set-sink-input-volume", str(index), f"{lowered.pop(index)}%"])
    return commands


def pactl(*args: str) -> str:
    try:
        return subprocess.run(["pactl", *args], capture_output=True, text=True, timeout=5, check=False).stdout
    except (OSError, subprocess.TimeoutExpired):
        return ""


def listing(what: str) -> list[dict]:
    try:
        found = json.loads(pactl("-f", "json", "list", what) or "[]")
    except ValueError:
        return []
    return found if isinstance(found, list) else []


def look(words: list[str], state: dict) -> list[list[str]]:
    commands = plan(listing("sink-inputs"), listing("source-outputs"), words, settings.read(), state)
    for command in commands:
        pactl(*command)
    try:   # menusounds.py keeps quiet while the menus are muted
        QUIET_FLAG.parent.mkdir(parents=True, exist_ok=True)
        QUIET_FLAG.touch() if state.get("muted") else QUIET_FLAG.unlink(missing_ok=True)
    except OSError:
        pass
    return commands


def main(argv: list[str]) -> int:
    import startmenu
    words, state = player_words(), {}
    menu = startmenu.Watch()   # a setting chosen in Batocera's menu: pass it on (lights, sound set)
    if "--once" in argv:
        for command in look(words, state):
            print("pactl", *command)
        return 0
    try:
        while True:
            menu.look()
            look(words, state)
            time.sleep(EVERY_S)
    except KeyboardInterrupt:
        pass
    finally:   # leave nothing muted or lowered behind
        for index in state.get("muted", set()):
            pactl("set-sink-input-mute", str(index), "0")
        for index, before in state.get("lowered", {}).items():
            pactl("set-sink-input-volume", str(index), f"{before}%")
    return 0


if __name__ == "__main__":
    import signal
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    sys.exit(main(sys.argv[1:]))
