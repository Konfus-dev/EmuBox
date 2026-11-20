#!/usr/bin/env python3
"""Start Batocera's menu program without its own music player finding any songs.

    esquiet.py emulationstation [its options]

EmuBox plays the menus' music itself (music.py: the Guide can show, pause and skip it). Batocera's
menu program has a player of its own, switched by Sound settings > FRONTEND MUSIC; EmuBox makes
that switch turn EmuBox's music on and off instead (audio.py). For that, the menu program must
not play anything itself, and the only way to stop it is to give it no songs: it is started in a
private view of the folders (a mount namespace) where its music folders are empty. Everything
else, EmuBox's player included, still sees the real folders, and drives plugged in later still
show up inside (the view follows the rest of the system).

Called by emubox-es, which /boot/boot-custom.sh puts in Batocera's start-up (in memory). When
anything here fails, the menu program starts as usual.
"""
from __future__ import annotations

import ctypes
import os
import sys

EMPTY = "/var/run/emubox/no-music"
FOLDERS = ("/userdata/music", "/usr/share/batocera/music")   # where the menu program looks
LOG = "/var/log/emubox-boot.log"

MS_RDONLY, MS_REMOUNT, MS_BIND, MS_REC, MS_SLAVE = 1, 32, 4096, 16384, 1 << 19


def _mount(libc, source: str | None, target: str, flags: int) -> None:
    if libc.mount(source.encode() if source else None, target.encode(), None, flags, None) != 0:
        raise OSError(ctypes.get_errno(), f"mount {target}: {os.strerror(ctypes.get_errno())}")


def hide_music(folders=FOLDERS, empty: str = EMPTY) -> list[str]:
    """In a view of the folders of our own, cover each music folder with an empty, read-only one."""
    libc = ctypes.CDLL(None, use_errno=True)
    os.makedirs(empty, exist_ok=True)
    os.unshare(os.CLONE_NEWNS)
    _mount(libc, None, "/", MS_REC | MS_SLAVE)        # mounts made outside still reach us; ours stay here
    covered = []
    for folder in folders:
        if os.path.isdir(folder):
            _mount(libc, empty, folder, MS_BIND)
            _mount(libc, None, folder, MS_REMOUNT | MS_BIND | MS_RDONLY)
            covered.append(folder)
    return covered


def note(message: str) -> None:
    try:
        with open(LOG, "a") as log:
            log.write(f"esquiet: {message}\n")
    except OSError:
        pass


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    try:
        note("music folders hidden from the menu program: " + ", ".join(hide_music()))
    except Exception as e:      # never keep the menus from starting
        note(f"could not hide the music folders ({e}); Batocera's own player may play too")
    os.execvp(argv[0], argv)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
