"""Console tools: one extra step while installing.

Earlier versions added the test VM's form of the Xbox Wireless Controller to the drive's list of
controllers. On real hardware Batocera matched the real pad to it by name, and every face button
was wrong. That layout now lives in lib/vmpads.py and is added at start-up inside a VM only; this
takes it off a drive that still has it, leaving everything else in the list alone.
"""
import importlib.util
import json
import re
from pathlib import Path

FILE = "system/configs/emulationstation/es_input.cfg"
MUSIC_MOVED = "system/emubox/music-switch-moved"   # the switch below was moved once already
EMUBOX_SETTINGS = "system/configs/emubox/settings.conf"

_spec = importlib.util.spec_from_file_location("vmpads", Path(__file__).parent / "files/lib/vmpads.py")
vmpads = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(vmpads)


def install(env) -> None:
    path = env.target.path(FILE)
    if path.is_file():
        before = path.read_text()
        after = vmpads.without_layout(before)
        if after != before:
            env.target.write_text(FILE, after)
    move_music_switch(env)
    set_up_rpg_maker_games(env)


def move_music_switch(env) -> None:
    """Once: Sound settings > FRONTEND MUSIC becomes the switch for EmuBox's menu music.

    Earlier versions turned that switch off (Batocera's own player would have played over
    EmuBox's) and had a switch of their own, MENU MUSIC. Now Batocera's player finds no songs
    (lib/esquiet.py), so its switch is set to what MENU MUSIC was, and left to you after that."""
    if env.target.path(MUSIC_MOVED).exists():
        return
    own = env.target.path(EMUBOX_SETTINGS)
    was_off = own.is_file() and any(line.replace(" ", "") in ("music.menu=off", "music.menu=0")
                                    for line in own.read_text().splitlines())
    env.target.es_setting("audio.bgmusic", not was_off)
    env.target.write_text(MUSIC_MOVED, "FRONTEND MUSIC switches EmuBox's menu music (set once by the installer).\n")


RPG_MAKER_KEYS = Path(__file__).parent / "files/padto/rpgmaker-xp.keys"
MKXP_FULL_SCREEN = {"fullscreen": True, "fixedAspectRatio": True, "smoothScaling": False}


def rpg_maker_game(folder: Path) -> bool:
    """An RPG Maker XP/VX/VX Ace game: its Game.ini names an RGSS library."""
    ini = folder / "Game.ini"
    try:
        return bool(re.search(r"^\s*Library\s*=\s*RGSS", ini.read_text(errors="replace"), re.M | re.I))
    except OSError:
        return False


def runs_on_mkxp(folder: Path) -> bool:
    """Its Game.exe is mkxp-z (which reads mkxp.json), not RPG Maker's own player."""
    try:
        return b"mkxp.json" in (folder / "Game.exe").read_bytes()
    except OSError:
        return False


def set_up_rpg_maker_games(env) -> None:
    """RPG Maker games (fan games like Pokemon Essentials ones) under Windows (Wine):
    - padto.keys: Batocera has no controller mapping for Windows games, and these games read
      only the keyboard, so the controller did nothing (2026-11-24). Xbox A confirms (Enter),
      B goes back (Esc), X runs (Shift), d-pad and left stick move.
    - mkxp.json: a game on mkxp-z opens in a small window over the menus; this starts it full
      screen, scaled with its shape kept.
    - emubox-start.bat: a game on mkxp-z is started with Wine's GLX (see start_with_glx).
    A file the game already has is never replaced (yours, or the game's own)."""
    windows = env.target.path("roms/windows")
    if not windows.is_dir():
        return
    for game in sorted(p for p in windows.iterdir() if p.is_dir() and rpg_maker_game(p)):
        relative = game.relative_to(env.target.root)
        if not (game / "padto.keys").exists():
            env.target.write_text(f"{relative}/padto.keys", RPG_MAKER_KEYS.read_text())
            env.say(f"  {game.name}: controller set up (A confirm, B back, X run)")
        if runs_on_mkxp(game):
            own = game / "mkxp.json"
            if not own.exists():
                env.target.write_text(f"{relative}/mkxp.json", json.dumps(MKXP_FULL_SCREEN, indent=4) + "\n")
                env.say(f"  {game.name}: starts full screen")
            else:
                text = own.read_text(errors="replace")
                changed = with_full_screen(text)
                if changed != text:
                    if not (game / "mkxp.json.before-emubox").exists():
                        env.target.write_text(f"{relative}/mkxp.json.before-emubox", text)
                    env.target.write_text(f"{relative}/mkxp.json", changed)
                    env.say(f"  {game.name}: starts full screen (its own mkxp.json, original kept beside it)")
            start_with_glx(env, game, relative)


GLX_START = "emubox-start.bat"
GLX_START_TEXT = (
    "@echo off\r\n"
    "rem EmuBox: this Wine draws OpenGL through EGL, which NVIDIA cards under Batocera (XWayland) do not offer:\r\n"
    'rem "No matching GL pixel format available". Use GLX instead, then start the game.\r\n'
    'reg add "HKCU\\Software\\Wine\\X11 Driver" /v UseEGL /t REG_SZ /d N /f >nul\r\n'
    "rem EmuBox: the controller reaches the game as keys (padto.keys). mkxp-z also reads it itself, with\r\n"
    "rem Xbox A as cancel and B as confirm: every press was both at once. Wine keeps controllers from the\r\n"
    "rem game (from the next start on: its controller service is already running by now).\r\n"
    'reg add "HKLM\\System\\CurrentControlSet\\Services\\winebus" /v DisableInput /t REG_DWORD /d 1 /f >nul\r\n'
    'reg add "HKLM\\System\\CurrentControlSet\\Services\\winebus" /v "Enable SDL" /t REG_DWORD /d 0 /f >nul\r\n'
    "{command}\r\n"
)


def start_with_glx(env, game: Path, relative: Path) -> None:
    """mkxp-z draws with OpenGL, and Batocera's Wine (wine-tkg 10.20) asks for it through EGL.
    Batocera 43 has NVIDIA's EGL for Wayland only, not for X11 (Wine runs under XWayland), so on
    an NVIDIA card the game stopped at "No matching GL pixel format available" (2026-11-27, RTX
    5070 Ti; the test VM's Mesa was fine). Wine's UseEGL=N goes back to GLX, which works on both.
    It is a registry value in the game's bottle, which belongs to root and is made on first
    launch, so the game is started through a small .bat that sets it first. Batocera's own way in
    (system/wine/regs) cannot be used: it calls a wine64 that wine-tkg does not have.
    The same .bat keeps the controller itself from the game: mkxp-z
    reads joystick buttons by number, 0 (Xbox A) as cancel and 1 (Xbox B) as confirm (the table is
    in Game.exe), while padto.keys sends A as Enter and B as Esc. Every press was confirm and
    cancel at once and cancel is looked at first, so "yes" could never be chosen (2026-11-27).
    Wine finds controllers three ways and each has its own switch in winebus: SDL ("Enable
    SDL", on by default), and when that is off udev's input devices (DisableInput) and hidraw
    (DisableHidraw, which Batocera sets itself). DisableInput alone changed nothing: SDL was
    still on (2026-11-27).
    Left alone: a game that starts from another folder (DIR=). One that already starts this way
    has its .bat brought up to date, keeping the command it starts."""
    autorun = game / "autorun.cmd"
    text = autorun.read_text(errors="replace").replace("\r\n", "\n") if autorun.exists() else ""
    lines = text.splitlines()
    commands = [line for line in lines if line.startswith("CMD=")]
    if any(line.startswith("DIR=") and line[4:].strip() for line in lines) or len(commands) > 1:
        return
    command = commands[0][4:].strip() if commands else "Game.exe"
    if not command:
        return
    if GLX_START in command:   # ours already: only the .bat may be an older one
        bat = game / GLX_START
        old = bat.read_text(errors="replace") if bat.exists() else ""
        started = [line.strip() for line in old.splitlines() if line.strip()]
        new = GLX_START_TEXT.format(command=started[-1] if started else "Game.exe")
        if new != old.replace("\r\n", "\n").replace("\n", "\r\n"):
            env.target.write_text(f"{relative}/{GLX_START}", new)
            env.say(f"  {game.name}: its start file brought up to date")
        return
    env.target.write_text(f"{relative}/{GLX_START}", GLX_START_TEXT.format(command=command))
    if autorun.exists() and not (game / "autorun.cmd.before-emubox").exists():
        env.target.write_text(f"{relative}/autorun.cmd.before-emubox", autorun.read_text(errors="replace"))
    start = f"CMD=cmd /c {GLX_START}"
    kept = [start if line.startswith("CMD=") else line for line in lines] if commands else lines + [start]
    env.target.write_text(f"{relative}/autorun.cmd", "\n".join(kept) + "\n")
    env.say(f"  {game.name}: starts with GLX (NVIDIA cards have no EGL for Wine here)")


def with_full_screen(text: str) -> str:
    """A game's own mkxp.json (JSON with // comments) with full screen switched on, everything
    else (its soundfont, its keys) kept. One that already says "fullscreen" itself is left alone."""
    if re.search(r'^\s*"fullscreen"\s*:', text, re.M):
        return text
    return re.sub(r"\{", '{\n    "fullscreen": true,', text, count=1)
