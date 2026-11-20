#!/usr/bin/env python3
"""Keeps sounds out of each other's way.

    audio.py           run until stopped (the emubox service starts it at boot)
    audio.py --once    look once, act, and print what was done

- The menus' own music (music.py plays it) runs in the menus only: it stops for a game, and
  while a music app of yours is playing, and comes back afterwards.
- While an app is using the microphone (a call), your music and the menu music drop to a
  fifth of their volume, and come back when the call ends.

A music app is one whose app.json says "player": true. Each rule has a switch (see
settings.py). Everything is undone when it no longer applies, and only what this program
changed is put back.
"""
from __future__ import annotations

import glob
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import menusounds
import music
import settings

os.environ.setdefault("XDG_RUNTIME_DIR", "/var/run")
ROOT = Path(__file__).resolve().parent.parent
ES_QUIET = Path("/usr/bin/emubox-es")      # Batocera's menu starts without its own music (esquiet.py)
SCREENSAVER = music.RUN / "screensaver"   # there while Batocera's screensaver shows (scripts/screensaver-*)
MENU_MUSIC = "emubox menu music"   # our own player (music.py), as the sound server names it
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


def music_sounding(playing: list[dict], music_words: list[str]) -> bool:
    """Is a music app of yours playing right now?"""
    return any(not s.get("corked") and any(word in who(s) for word in music_words) for s in playing)


def menu_music_wanted(switches: dict[str, str], in_menus: bool, yours_playing: bool, held: bool) -> bool:
    """Should the menus' own music be playing? In the menus only, not over your music, not when
    you paused it by hand."""
    on = lambda name: switches.get(name, "on").lower() in settings.ON   # noqa: E731
    if not on("music.menu") or not in_menus or held:
        return False
    return not (yours_playing and on("music.quiet_menu"))


def plan(playing: list[dict], recording: list[dict], music_words: list[str], switches: dict[str, str],
         state: dict) -> list[list[str]]:
    """The pactl commands that make music give way to a call, and bring it back afterwards.

    `playing` and `recording` are pactl's lists of sink inputs and source outputs.
    `state` remembers what we changed: {"lowered": {index: volume before}}."""
    lowered = state.setdefault("lowered", {})
    on = lambda name: switches.get(name, "").lower() in settings.ON   # noqa: E731
    commands: list[list[str]] = []
    here = {stream["index"] for stream in playing}
    for index in set(lowered) - here:   # streams that ended take their changes with them
        del lowered[index]

    callers = [who(stream) for stream in recording if "peak detect" not in str(stream.get("properties", {})).lower()]
    in_call = bool(callers)
    music = [s for s in playing if any(word in who(s) for word in list(music_words) + [MENU_MUSIC])]
    try:
        level = max(0, min(100, int(switches.get("call.music_volume", "20"))))
    except ValueError:
        level = 20
    for stream in music:
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
    es = music.es_text()
    switches = dict(settings.read())
    # Sound settings > FRONTEND MUSIC. Batocera's own player is kept silent by esquiet.py, which
    # the drive guard's boot-custom.sh puts in place; without that, Batocera plays the music itself.
    ours = music.frontend_music(es) and ES_QUIET.exists()
    switches["music.menu"] = "on" if ours else "off"
    playing = listing("sink-inputs")
    commands = plan(playing, listing("source-outputs"), words, switches, state)
    for command in commands:
        pactl(*command)
    # The menus' own music: start the player the first time it is wanted, then pause and resume it.
    in_menus = menusounds.game_running() is False
    if SCREENSAVER.exists() and music.stops_for_screensaver(es):    # STOP MUSIC ON SCREENSAVER
        in_menus = False
    wanted = menu_music_wanted(switches, in_menus, music_sounding(playing, words), music.HELD.exists())
    paused = music.ask("get_property", "pause")
    player = state.get("player")
    if paused is None and wanted and (player is None or player.poll() is not None):   # never started, or it died
        state["player"] = music.start()
    elif paused is not None and paused == wanted:
        music.ask("set_property", "pause", not wanted)
    if paused is not None:
        follow_music_settings(es, wanted, state)
    return commands


def follow_music_settings(es: str, playing: bool, state: dict) -> None:
    """Batocera's Sound settings, for the music EmuBox plays in its place: MUSIC VOLUME as it
    changes, and DISPLAY SONG TITLES (for SONG TITLE DISPLAY DURATION seconds) at each new song."""
    level = music.volume(es)
    if state.get("volume") != level:
        music.ask("set_property", "volume", level)
        state["volume"] = level
    song = music.title() if playing else ""
    if song and song != state.get("song"):
        seconds = music.song_titles(es)
        if seconds:
            subprocess.Popen(["python3", str(Path(__file__).with_name("toast.py")), f"Now playing: {song}", str(seconds)],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        state["song"] = song


def main(argv: list[str]) -> int:
    import startmenu
    words, state = player_words(), {}
    menu = startmenu.Watch()   # a setting chosen in Batocera's menu: pass it on (lights, sound set)
    if "--once" in argv:
        for command in look(words, state):
            print("pactl", *command)
        return 0
    music.HELD.unlink(missing_ok=True)
    try:
        while True:
            menu.look()
            look(words, state)
            time.sleep(EVERY_S)
    except KeyboardInterrupt:
        pass
    finally:   # leave nothing lowered behind, and no music playing to nobody
        for index, before in state.get("lowered", {}).items():
            pactl("set-sink-input-volume", str(index), f"{before}%")
        music.ask("quit")
    return 0


if __name__ == "__main__":
    import signal
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    sys.exit(main(sys.argv[1:]))
