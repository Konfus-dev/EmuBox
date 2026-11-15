"""Put an app's program on the drive ahead of time, so Batocera does not have to download it.

Batocera keeps Flatpak programs in saves/flatpak/binaries on its data drive. From a PC we
fill that folder with this PC's own `flatpak` command, pointed at the drive; on Batocera
itself its own `flatpak` does the same job. Either way a failure only means the app
downloads the first time it is opened, as before.

Graphics drivers: a Flatpak program needs the driver that matches the system it runs on.
On a PC we cannot see which one Batocera will use, so we fetch the ones the drive's own
Flatpak folder shows Batocera has already asked for (after one start of any app there),
and tell flatpak that those, not this PC's, are the drivers in use. That matters twice:
flatpak removes driver packages it believes nobody uses. The drivers seen are noted in a
small file beside the programs so the knowledge survives; EMUBOX_GL_DRIVERS=nvidia-590-48-01
adds one by hand.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from typing import Callable

from .target import Target

ON_DRIVE = "saves/flatpak/binaries"
FLATHUB = "https://dl.flathub.org/repo/flathub.flatpakrepo"
DRIVER = "org.freedesktop.Platform.GL."
NOTE = f"{ON_DRIVE}/.emubox-drivers"   # one "name branch" per line
ROOM_NEEDED = 3 * 1024 ** 3   # runtimes are large; do not start what cannot finish


def is_installed(target: Target, app: str) -> bool:
    return target.path(f"{ON_DRIVE}/app/{app}/current").exists()


def runtime_of(target: Target, app: str) -> str:
    """The runtime an installed program says it needs: "org.freedesktop.Platform/x86_64/25.08"."""
    try:
        for line in target.path(f"{ON_DRIVE}/app/{app}/current/active/metadata").read_text().splitlines():
            if line.startswith("runtime="):
                return line.partition("=")[2].strip()
    except OSError:
        pass
    return ""


def wanted_drivers(target: Target) -> list[tuple[str, str]]:
    """Graphics drivers Batocera has asked Flathub for on this drive: [("nvidia-590-48-01", "1.4")]."""
    found: set[tuple[str, str]] = set()
    refs = target.path(f"{ON_DRIVE}/repo/refs/remotes/flathub/runtime")
    for folder in refs.glob(f"{DRIVER}nvidia-*"):
        for branch in folder.glob("x86_64/*"):
            found.add((folder.name.removeprefix(DRIVER), branch.name))
    note = target.path(NOTE)
    try:
        for line in note.read_text().splitlines():
            name, _, branch = line.strip().partition(" ")
            if name:
                found.add((name, branch or "1.4"))
    except OSError:
        pass
    for name in os.environ.get("EMUBOX_GL_DRIVERS", "").replace(":", " ").split():
        found.add((name, "1.4"))
    if found and note.parent.is_dir():
        try:
            note.write_text("".join(f"{name} {branch}\n" for name, branch in sorted(found)))
        except OSError:
            pass
    return sorted(found)


def preinstall(target: Target, apps: list[str], say: Callable[[str], None],
               run: Callable = subprocess.run) -> list[str]:
    """Download these Flathub programs onto the drive. Gives the ones that are there afterwards."""
    waiting = [app for app in apps if not is_installed(target, app)]
    flatpak = shutil.which("flatpak")
    later = "it will download the first time it is opened instead."
    if not flatpak:
        say(f"  No 'flatpak' command on this machine, so {', '.join(waiting)} cannot be fetched now; {later}")
        return [app for app in apps if app not in waiting]
    folder = target.path(ON_DRIVE)
    folder.mkdir(parents=True, exist_ok=True)
    if waiting and shutil.disk_usage(folder).free < ROOM_NEEDED:
        say(f"  Less than 3 GB free on the drive, so {', '.join(waiting)} is not fetched now; {later}")
        return [app for app in apps if app not in waiting]

    env, scope, drivers = dict(os.environ), [], []
    if not target.live:   # a drive plugged into a PC: aim this PC's flatpak at the drive
        drivers = wanted_drivers(target)
        env["FLATPAK_USER_DIR"] = str(folder)
        # Hide this PC's own programs: flatpak counts a runtime the PC has as "already there"
        # and would leave it off the drive, where Batocera then cannot find it.
        env["FLATPAK_SYSTEM_DIR"] = tempfile.mkdtemp(prefix="emubox-no-system-")
        env["FLATPAK_GL_DRIVERS"] = ":".join([name for name, _ in drivers] + ["default"])   # colons, per flatpak(1)
        scope = ["--user"]

    def flat(*args: str) -> bool:
        return run([flatpak, *args[:1], *scope, *args[1:]], env=env, check=False).returncode == 0

    if not flat("remote-add", "--if-not-exists", "flathub", FLATHUB):
        say(f"  Flathub could not be reached, so nothing is fetched now; {later}")
        return [app for app in apps if app not in waiting]
    for name, branch in drivers:
        say(f"  Graphics driver {name} (the one Batocera asked for)...")
        flat("install", "-y", "--noninteractive", "flathub", f"runtime/{DRIVER}{name}/x86_64/{branch}")
    for app in waiting:
        say(f"  Downloading {app} onto the drive (a few minutes on a USB drive)...")
        if not flat("install", "-y", "--noninteractive", "flathub", app):
            say(f"  {app} could not be fetched now; {later}")
    for app in apps:   # each program's runtime, by name: a program without it does not start
        needs = runtime_of(target, app)
        if needs and not target.path(f"{ON_DRIVE}/runtime/{needs}").exists():
            say(f"  Runtime for {app} ({needs.rsplit('/', 1)[-1]})...")
            flat("install", "-y", "--noninteractive", "flathub", f"runtime/{needs}")
    # Whatever the programs on the drive still lack (a driver, an extension) or have a newer version of.
    say("  Checking that the programs on the drive are complete and current...")
    flat("update", "-y", "--noninteractive")
    # The same permissions Batocera gives the folder after installing a program itself.
    for path in [folder, *folder.rglob("*")]:
        try:
            if not path.is_symlink():
                mode = path.stat().st_mode
                path.chmod(mode | 0o444 | (0o111 if path.is_dir() or mode & 0o100 else 0))
        except OSError:
            pass
    return [app for app in apps if is_installed(target, app)]
