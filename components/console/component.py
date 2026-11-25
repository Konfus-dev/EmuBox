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
    A file the game already has is never replaced (yours, or the game's own)."""
    windows = env.target.path("roms/windows")
    if not windows.is_dir():
        return
    for game in sorted(p for p in windows.iterdir() if p.is_dir() and rpg_maker_game(p)):
        relative = game.relative_to(env.target.root)
        if not (game / "padto.keys").exists():
            env.target.write_text(f"{relative}/padto.keys", RPG_MAKER_KEYS.read_text())
            env.say(f"  {game.name}: controller set up (A confirm, B back, X run)")
        if runs_on_mkxp(game) and not (game / "mkxp.json").exists():
            env.target.write_text(f"{relative}/mkxp.json", json.dumps(MKXP_FULL_SCREEN, indent=4) + "\n")
            env.say(f"  {game.name}: starts full screen")
