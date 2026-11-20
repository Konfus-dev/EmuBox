"""Console tools: one extra step while installing.

Earlier versions added the test VM's form of the Xbox Wireless Controller to the drive's list of
controllers. On real hardware Batocera matched the real pad to it by name, and every face button
was wrong. That layout now lives in lib/vmpads.py and is added at start-up inside a VM only; this
takes it off a drive that still has it, leaving everything else in the list alone.
"""
import importlib.util
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
