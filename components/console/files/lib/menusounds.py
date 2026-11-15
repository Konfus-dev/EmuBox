#!/usr/bin/env python3
"""Menu sounds: which set, how loud, and the ones Batocera's menu program does not play itself.

    menusounds.py              run until stopped (the emubox service starts it at boot)
    menusounds.py sets         list the sound sets
    menusounds.py set <name>   use a set
    menusounds.py set-now      print the set in use
    menusounds.py next|previous      step to the next or the previous set (round and round)
    menusounds.py volume <+/-n|n>    change or set the volume (0..100)
    menusounds.py on|off <scroll|select|back|menuopen>    one sound's switch
    menusounds.py apply        redraw the scroll sound the menus play (after a change)

Batocera's menus only ever play a theme's scroll sound. This listens to the
controllers and keyboards (without taking them from anyone) and, while the menus are what is
on screen, plays the sounds for the buttons that select, go back and open the
main menu.

A sound set is a folder with any of scroll.wav, select.wav, back.wav and
menuopen.wav, and optionally boot.mp4: the start-up film with that set's
sound (made on a PC with the look's tools/splash.py --sound), used from the
next start while the set is chosen. "EmuBox" is the active theme's own (art/sounds in its folder).
Your own sets go in /userdata/system/configs/emubox/sounds/<Name>/ and show up
by that name; a sound a set lacks is taken from EmuBox. Each sound has its own
on/off switch and they share one volume, all in the in-game menu's Apps tab.

Moving makes its sound here too, for the d-pad, the left stick and the arrow
keys, so it is heard in the pop-up menus as well as in the lists (the menu
program itself only sounds in lists). To keep lists from sounding twice, the
menu program's own copy (art/sounds/scroll-now.wav in the theme) is kept silent.
Every change, to the set, the volume or a switch, is heard at once.

Silent whenever something else has the controller or the screen: during a
game, inside an app, the in-game menu or the on-screen keyboard, and while
your own music has made the menus quiet.
"""
from __future__ import annotations

import array
import json
import os
import re
import selectors
import subprocess
import sys
import time
import urllib.request
import wave
from pathlib import Path

import settings

os.environ.setdefault("XDG_RUNTIME_DIR", "/var/run")
ES_SETTINGS = Path("/userdata/system/configs/emulationstation/es_settings.cfg")
THEMES = (Path("/userdata/themes"), Path("/usr/share/emulationstation/themes"))
MINE = Path("/userdata/system/configs/emubox/sounds")
SPLASH = Path("/userdata/splash")                           # where Batocera looks for a start-up film
OWN_FILM = Path("/userdata/system/emubox/splash/emubox.mp4")   # EmuBox's own, kept to go back to
QUIET_FLAG = Path("/var/run/emubox/menus-quiet")   # kept by audio.py while your music plays
RUNNING_GAME = "http://127.0.0.1:1234/runningGame"
SOUTH, EAST, START = 304, 305, 315                 # BTN_SOUTH, BTN_EAST, BTN_START
ENTER, ESCAPE, SPACE = 28, 1, 57                   # a keyboard's keys for the same three things
DIRECTION_KEYS = (544, 545, 546, 547, 103, 108, 105, 106)   # d-pad buttons, then the arrow keys
# A held direction: the wait, then the pace. These are the menu program's own figures for its
# pop-up menus (half a second, then one row every fifth of a second), so a tick is a row moved.
HOLD_S, REPEAT_S = 0.5, 0.2
KINDS = ("scroll", "select", "back", "menuopen")
BUILT_IN = "EmuBox"
RESCAN_S, LOOK_S = 5.0, 1.0
README = """Sound sets for the menus.

Make a folder here, named as you want it listed (for example "My Sounds"), and put in any of:
  scroll.wav   select.wav   back.wav   menuopen.wav
WAV files, 16-bit. After the next boot the folder is offered under
in-game menu (Guide) > Apps > Menu sounds > Sound set. A sound the folder lacks is taken from EmuBox.
"""


def es_setting(name: str, text: str) -> str:
    found = re.search(rf'<\w+ name="{re.escape(name)}" value="([^"]*)"', text)
    return found.group(1) if found else ""


def es_text() -> str:
    try:
        return ES_SETTINGS.read_text(errors="replace")
    except OSError:
        return ""


def sound_for(code: int, inverted: bool) -> str:
    """Which sound a button makes in the menus: "select", "back", "menuopen" or ""."""
    accept, back = (EAST, SOUTH) if inverted else (SOUTH, EAST)
    return {accept: "select", back: "back", START: "menuopen",
            ENTER: "select", ESCAPE: "back", SPACE: "menuopen"}.get(code, "")


def should_play(kind: str, switches: dict[str, str], in_menus: bool, quiet: bool) -> bool:
    return switches.get(f"ui.sound.{kind}", "on").lower() in settings.ON and in_menus and not quiet


def theme_folder(text: str, themes=THEMES) -> Path | None:
    name = es_setting("ThemeSet", text)
    for root in themes:
        if name and (Path(root) / name / "art" / "sounds").is_dir():
            return Path(root) / name / "art" / "sounds"
    return None


def sets(text: str, mine: Path = MINE, themes=THEMES) -> dict[str, Path]:
    """Every sound set by name: the theme's own first, then the folders of yours that hold a sound."""
    found: dict[str, Path] = {}
    built_in = theme_folder(text, themes)
    if built_in:
        found[BUILT_IN] = built_in
    try:
        for folder in sorted(mine.iterdir()):
            if folder.is_dir() and folder.name != BUILT_IN and any((folder / f"{k}.wav").is_file() for k in KINDS):
                found[folder.name] = folder
    except OSError:
        pass
    return found


def neighbour(chosen: str, names: list[str], forward: bool) -> str:
    """The set after (or before) the chosen one, going round; the built-in one when there is no list."""
    if not names:
        return BUILT_IN
    at = names.index(chosen) if chosen in names else 0
    return names[(at + (1 if forward else -1)) % len(names)]


def sounds_of(chosen: str, all_sets: dict[str, Path]) -> dict[str, Path]:
    """The file for each kind of sound: from the chosen set, else from the built-in one."""
    files: dict[str, Path] = {}
    for kind in KINDS:
        for name in (chosen, BUILT_IN):
            file = all_sets.get(name, Path("/nonexistent")) / f"{kind}.wav"
            if file.is_file():
                files[kind] = file
                break
    return files


def volume(switches: dict[str, str]) -> int:
    try:
        return max(0, min(100, int(switches.get("ui.sound_volume", "60"))))
    except ValueError:
        return 60


def scaled(source: Path, target: Path, percent: int) -> bool:
    """Write the sound at a volume (0 = silence of the same length). 16-bit WAV only."""
    try:
        with wave.open(str(source), "rb") as wav:
            params, frames = wav.getparams(), wav.readframes(wav.getnframes())
        if params.sampwidth != 2:
            return False
        samples = array.array("h")
        samples.frombytes(frames[:len(frames) // 2 * 2])
        if sys.byteorder == "big":
            samples.byteswap()
        gain = percent / 100
        samples = array.array("h", (max(-32768, min(32767, int(v * gain))) for v in samples))
        if sys.byteorder == "big":
            samples.byteswap()
        fresh = target.with_suffix(".new")
        with wave.open(str(fresh), "wb") as wav:
            wav.setparams(params)
            wav.writeframes(samples.tobytes())
        os.replace(fresh, target)
        return True
    except (OSError, wave.Error, EOFError):
        return False


def apply(text: str | None = None, mine: Path = MINE, themes=THEMES, switches: dict[str, str] | None = None) -> bool:
    """Silence the scroll sound the menu program would play itself (see below)."""
    text = es_text() if text is None else text
    switches = settings.read() if switches is None else switches
    folder = theme_folder(text, themes)
    if not folder or not (folder / "scroll-now.wav").exists():
        return False   # a theme that is not ours: its scroll sound is its own business
    source = sounds_of(switches.get("ui.sound_set", BUILT_IN), sets(text, mine, themes)).get("scroll")
    if not source:
        return False
    # We play the moving sound ourselves, everywhere (lists and pop-up menus alike), so the
    # menu program's copy is kept silent: otherwise lists would sound twice.
    start_up_film(switches.get("ui.sound_set", BUILT_IN), mine)
    return scaled(source, folder / "scroll-now.wav", 0)


def start_up_film(chosen: str, mine: Path = MINE, splash: Path = SPLASH, own: Path = OWN_FILM) -> bool:
    """A set may bring its own start-up film (boot.mp4: the same pictures with that set's sound).
    Put the chosen set's in place for the next start, or EmuBox's own back. True when it changed."""
    wanted = mine / chosen / "boot.mp4"
    if not wanted.is_file():
        wanted = own
    target = splash / "emubox.mp4"
    try:
        if not wanted.is_file() or not target.is_file():
            return False   # no film of ours on this drive: nothing to swap
        if wanted.stat().st_size == target.stat().st_size and wanted.read_bytes() == target.read_bytes():
            return False
        fresh = target.with_suffix(".new")
        fresh.write_bytes(wanted.read_bytes())
        os.replace(fresh, target)
        return True
    except OSError:
        return False


def game_running() -> bool | None:
    """True while a game (or an app started like one) runs; None when the menus cannot be asked."""
    try:
        with urllib.request.urlopen(RUNNING_GAME, timeout=1) as reply:
            text = reply.read().decode(errors="replace").strip()
    except OSError:
        return None
    try:
        game = json.loads(text) if text else None
    except ValueError:
        return False
    return bool(isinstance(game, dict) and (game.get("path") or game.get("name")))


def direction(kind: int, code: int, value: int, centre: float = 0.0, span: float = 1.0) -> tuple[str, bool] | None:
    """A d-pad, stick or arrow-key event as (what moved, is it held now); None for anything else.
    `kind` is the event type (1 = key, 3 = axis); sticks need their centre and half-range."""
    if kind == 1 and code in DIRECTION_KEYS and value in (0, 1):
        return f"key{code}", value == 1
    if kind == 3 and code in (16, 17):                    # the d-pad as a "hat"
        return f"hat{code}", value != 0
    if kind == 3 and code in (0, 1):                      # left stick, pushed well over
        return f"stick{code}", abs((value - centre) / (span or 1)) > 0.6
    return None


def listen() -> int:
    import evdev   # Batocera has it; kept out of the top so the rest can be tried anywhere

    try:
        MINE.mkdir(parents=True, exist_ok=True)
        if not (MINE / "README.txt").exists():
            (MINE / "README.txt").write_text(README)
    except OSError:
        pass
    apply()
    selector = selectors.DefaultSelector()
    pads: dict[str, object] = {}
    files: dict[str, Path] = {}
    inverted, in_menus = False, False
    next_scan = next_look = 0.0
    playing: dict[str, subprocess.Popen] = {}   # one voice for moving, one for the rest
    held: dict[str, float] = {}                 # a direction being held -> when it next ticks

    def play(kind: str) -> None:
        switches = settings.read()
        if kind not in files or not should_play(kind, switches, in_menus, QUIET_FLAG.exists()):
            return
        voice = "scroll" if kind == "scroll" else "button"
        before = playing.get(voice)
        if before and before.poll() is None:
            before.kill()   # a fresh press cuts the last sound short rather than piling up
        try:
            playing[voice] = subprocess.Popen(
                ["paplay", f"--volume={int(65536 * volume(switches) / 100)}", str(files[kind])],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError:
            pass

    while True:
        now = time.monotonic()
        if now >= next_scan:
            next_scan = now + RESCAN_S
            for path in evdev.list_devices():
                if path in pads:
                    continue
                try:
                    device = evdev.InputDevice(path)
                    keys = device.capabilities().get(evdev.ecodes.EV_KEY, [])
                    ours = "EmuBox" in device.name or "hotkeys" in device.name   # pretend devices: never real presses
                    if (SOUTH in keys or (ENTER in keys and ESCAPE in keys)) and not ours:
                        pads[path] = device
                        selector.register(device, selectors.EVENT_READ)
                    else:
                        device.close()
                except OSError:
                    continue
            text = es_text()
            files = sounds_of(settings.get("ui.sound_set"), sets(text))
            inverted = es_setting("InvertButtons", text) == "true"
        if now >= next_look:
            next_look = now + LOOK_S
            in_menus = game_running() is False
        for name, due in list(held.items()):   # a held direction keeps ticking, as the menus keep moving
            if now >= due:
                play("scroll")
                held[name] = now + REPEAT_S
        wait = min([LOOK_S] + [max(0.0, due - time.monotonic()) for due in held.values()])
        for key, _ in selector.select(timeout=wait):
            device = key.fileobj
            try:
                events = list(device.read())
            except BlockingIOError:
                continue
            except OSError:   # unplugged
                selector.unregister(device)
                pads.pop(device.path, None)
                for name in [n for n in held if n.startswith(device.path)]:
                    del held[name]
                continue
            for event in events:
                centre = span = 0.0
                if event.type == 3 and event.code in (0, 1):
                    info = device.absinfo(event.code)
                    centre, span = (info.max + info.min) / 2, (info.max - info.min) / 2
                moved = direction(event.type, event.code, event.value, centre, span)
                if moved:
                    name, down = f"{device.path}:{moved[0]}", moved[1]
                    if down and name not in held:
                        play("scroll")
                        held[name] = time.monotonic() + HOLD_S
                    elif not down:
                        held.pop(name, None)
                elif event.type == evdev.ecodes.EV_KEY and event.value == 1:
                    play(sound_for(event.code, inverted))
    return 0


def main(argv: list[str]) -> int:
    if not argv:
        return listen()
    action, rest = argv[0], argv[1:]
    if action == "sets":
        print("\n".join(sets(es_text())))
    elif action == "set-now":
        chosen = settings.get("ui.sound_set")
        print(chosen if chosen in sets(es_text()) else BUILT_IN)
    elif action in ("next", "previous"):
        settings.write("ui.sound_set", neighbour(settings.get("ui.sound_set"), list(sets(es_text())), action == "next"))
        apply()
    elif action == "set" and rest:
        settings.write("ui.sound_set", rest[0])
        apply()
    elif action == "volume" and rest:
        now = volume(settings.read())
        wanted = now + int(rest[0]) if rest[0][:1] in "+-" else int(rest[0])
        settings.write("ui.sound_volume", str(max(0, min(100, wanted))))
        apply()
    elif action in ("on", "off") and rest and rest[0] in KINDS:
        settings.write(f"ui.sound.{rest[0]}", action)
        apply()
    elif action == "apply":
        return 0 if apply() else 1
    else:
        print(__doc__, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except KeyboardInterrupt:
        sys.exit(0)
