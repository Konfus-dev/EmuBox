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

import audioout
import menusounds
import music
import settings

os.environ.setdefault("XDG_RUNTIME_DIR", "/var/run")
ROOT = Path(__file__).resolve().parent.parent
ES_QUIET = Path("/usr/bin/emubox-es")      # Batocera's menu starts without its own music (esquiet.py)
SEEN_FRONTEND = Path("/userdata/system/configs/emubox/frontend-music.seen")   # FRONTEND MUSIC when last looked
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


def chosen_output(conf: Path = Path("/userdata/system/batocera.conf")) -> str:
    """audio.device in batocera.conf ("auto" when not set)."""
    import re
    try:
        found = re.search(r"^audio\.device=(.*)$", conf.read_text(errors="replace"), re.M)
    except OSError:
        return "auto"
    return found.group(1).strip() if found else "auto"


def look(words: list[str], state: dict) -> list[list[str]]:
    audioout.prefer_headphones(chosen_output())   # "Automatic": headphones when connected, else HDMI
    es = music.es_text()
    follow_frontend_music(es)
    switches = dict(settings.read())
    if not ES_QUIET.exists():   # Batocera's own player is not kept silent here: leave the music to it
        switches["music.menu"] = "off"
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


def follow_frontend_music(es: str, seen: Path | None = None) -> bool:
    """Two switches, one meaning: EmuBox's MENU MUSIC (the Guide's Sound section) decides, and
    Batocera's Sound settings > FRONTEND MUSIC, when you change it there, is copied onto it.
    (Batocera's menu keeps its settings in memory and writes them all back, so EmuBox can never
    safely change FRONTEND MUSIC itself: it only notices when you did.) True when it copied."""
    seen = SEEN_FRONTEND if seen is None else seen
    now = "on" if music.frontend_music(es) else "off"
    try:
        before = seen.read_text().strip()
    except OSError:
        before = ""
    if before == now:
        return False
    try:
        seen.parent.mkdir(parents=True, exist_ok=True)
        seen.write_text(now + "\n")
    except OSError:
        return False
    if before:              # first sight (no note yet): nothing was changed, keep MENU MUSIC as it is
        settings.write("music.menu", now)
        return True
    return False


def follow_music_settings(es: str, playing: bool, state: dict) -> None:
    """MUSIC VOLUME from Batocera's Sound settings, applied as it changes."""
    level = music.volume(es)
    if state.get("volume") != level:
        music.ask("set_property", "volume", level)
        state["volume"] = level


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
