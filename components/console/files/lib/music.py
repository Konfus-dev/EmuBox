#!/usr/bin/env python3
"""The menus' background music, played by EmuBox so that it can be steered.

    music.py line        "Playing: Song" or "Paused: Song" for the Guide menu's bar (nothing when silent)
    music.py toggle      pause, or carry on
    music.py next | previous

Batocera's menu program can play background music but offers no way to ask what is
playing, skip a song or pause it. So its own music is switched off (the installer
does that) and the same songs, /userdata/music and Batocera's own in
/usr/share/batocera/music, are played here with mpv. audio.py decides when: in the
menus only (not during a game), and not while a music app of yours is playing.
Pausing by hand holds until you press play again.
"""
from __future__ import annotations

import glob
import json
import os
import re
import socket
import subprocess
import sys
from pathlib import Path

RUN = Path("/var/run/emubox")
SOCKET = RUN / "music.sock"
HELD = RUN / "music.held"          # paused by hand: stay paused
FOLDERS = ("/userdata/music", "/usr/share/batocera/music")
KINDS = (".ogg", ".mp3", ".flac", ".wav", ".m4a", ".opus")
ES_SETTINGS = Path("/userdata/system/configs/emulationstation/es_settings.cfg")


def songs(folders=FOLDERS) -> list[str]:
    found = []
    for folder in folders:
        found += [f for f in sorted(glob.glob(os.path.join(folder, "**", "*"), recursive=True))
                  if f.lower().endswith(KINDS)]
        if found:
            break   # your own music, when there is some, replaces Batocera's
    return found


def es_text() -> str:
    """Batocera's menu settings file (es_settings.cfg), or nothing when it cannot be read."""
    try:
        return ES_SETTINGS.read_text(errors="replace")
    except OSError:
        return ""


def es_choice(name: str, default: str, text: str | None = None) -> str:
    """One setting of Batocera's menu program, as es_settings.cfg has it."""
    found = re.search(rf'name="{re.escape(name)}" value="([^"]*)"', es_text() if text is None else text)
    return found.group(1) if found else default


def frontend_music(text: str | None = None) -> bool:
    """Batocera's Sound settings > FRONTEND MUSIC switch, which turns this music on and off
    (Batocera's own player finds no songs: esquiet.py). On when never set, like Batocera."""
    return es_choice("audio.bgmusic", "true", text).lower() in ("true", "1", "on")


def stops_for_screensaver(text: str | None = None) -> bool:
    """STOP MUSIC ON SCREENSAVER (on unless turned off, like Batocera)."""
    return es_choice("StopMusicOnScreenSaver", "true", text).lower() != "false"


def song_titles(text: str | None = None) -> int:
    """DISPLAY SONG TITLES: 0 when off, else SONG TITLE DISPLAY DURATION in seconds. The Guide's
    music bar shows the song's name when it is on (instead of a note popping up over the menus)."""
    if es_choice("audio.display_titles", "true", text).lower() == "false":
        return 0
    try:
        return max(1, int(float(es_choice("audio.display_titles_time", "10", text))))
    except ValueError:
        return 10


def volume(text: str | None = None) -> int:
    """MUSIC VOLUME in Batocera's sound settings (65 when never set)."""
    try:
        return max(0, min(100, int(float(es_choice("MusicVolume", "65", text)))))
    except ValueError:
        return 65


def ask(*command, sock: Path = SOCKET):
    """Send mpv one command; gives its answer's "data", or None when it is not there."""
    try:
        with socket.socket(socket.AF_UNIX) as link:
            link.settimeout(1.0)
            link.connect(str(sock))
            link.sendall(json.dumps({"command": list(command)}).encode() + b"\n")
            for line in link.makefile():
                reply = json.loads(line)
                if "error" in reply:          # skip the events mpv also sends
                    return reply.get("data") if reply["error"] == "success" else None
    except (OSError, ValueError):
        pass
    return None


def start(sock: Path = SOCKET, files: list[str] | None = None) -> subprocess.Popen | None:
    """Start the player, paused, with every song in a shuffled, endless list."""
    files = songs() if files is None else files
    if not files:
        return None
    sock.parent.mkdir(parents=True, exist_ok=True)
    try:
        return subprocess.Popen(
            ["mpv", "--no-video", "--idle=yes", "--no-terminal", "--really-quiet", "--pause", "--shuffle",
             "--loop-playlist=inf", f"--volume={volume()}", "--audio-client-name=EmuBox menu music",
             f"--input-ipc-server={sock}", *files],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    except OSError:
        return None


def title(sock: Path = SOCKET) -> str:
    name = ask("get_property", "media-title", sock=sock) or ""
    return Path(name).stem if name.lower().endswith(KINDS) else name


def line(sock: Path = SOCKET) -> str:
    """For the Guide menu: shown while the menu music plays, or waits paused by hand."""
    paused = ask("get_property", "pause", sock=sock)
    if paused is None:
        return ""
    name = title(sock)
    if not name or (paused and not HELD.exists()):
        return ""       # paused by the rules (a game, your own music): not ours to show
    if not song_titles():   # Sound settings > DISPLAY SONG TITLES off: the bar says only that music plays
        return "Paused" if paused else "Playing"
    name = name if len(name) <= 40 else name[:38] + "..."
    return f"{'Paused' if paused else 'Playing'}: {name}"


def main(argv: list[str]) -> int:
    action = argv[0] if argv else ""
    if action == "line":
        print(line())
    elif action == "toggle":
        if HELD.exists():
            HELD.unlink(missing_ok=True)
            ask("set_property", "pause", False)
        else:
            HELD.parent.mkdir(parents=True, exist_ok=True)
            HELD.touch()
            ask("set_property", "pause", True)
    elif action in ("next", "previous"):
        ask("playlist-next" if action == "next" else "playlist-prev", "force")
        HELD.unlink(missing_ok=True)
        ask("set_property", "pause", False)
    else:
        print(__doc__, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
