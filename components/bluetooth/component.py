"""Share this PC's Bluetooth controller pairings with a Batocera drive used on the same PC.

A controller remembers one pairing per Bluetooth adapter. When Linux and
Batocera share a PC they share its adapter, so whichever paired last wins and
the other can no longer connect. Giving Batocera the same keys this system
holds lets the controller connect to both.

Offered only when preparing a drive from a Linux PC that has paired input devices.
"""
from __future__ import annotations

import io
import os
import re
import tarfile
import time
from pathlib import Path

HOST_PAIRINGS = Path("/var/lib/bluetooth")
ON_DRIVE = "system/bluetooth/bluetooth.tar"     # Batocera unpacks this over /var/lib at boot
INPUT_SERVICES = ("00001812-", "00001124-")     # HID over GATT (Bluetooth LE) and classic HID


def available(env) -> bool:
    return env.target is not None and not env.target.live and bool(env.host.paired_bluetooth_devices())


def _input_devices() -> list[Path]:
    """Folders of paired keyboards, mice and controllers, as /var/lib/bluetooth/<adapter>/<device>."""
    found = []
    for info in sorted(HOST_PAIRINGS.glob("*/*/info")):
        text = info.read_text(errors="replace")
        paired = "Key=" in text
        if paired and any(service in text for service in INPUT_SERVICES):
            found.append(info.parent)
    return found


def _trusted(info: str) -> str:
    """The pairing, marked trusted so Batocera lets it reconnect without asking."""
    if re.search(r"^Trusted=", info, re.MULTILINE):
        return re.sub(r"^Trusted=.*$", "Trusted=true", info, flags=re.MULTILINE)
    return info.replace("[General]\n", "[General]\nTrusted=true\n", 1)


def _name(info: str) -> str:
    match = re.search(r"^Name=(.*)$", info, re.MULTILINE)
    return match[1] if match else "unnamed device"


def install(env) -> None:
    devices = _input_devices()
    if not devices:
        env.say("  No paired controllers, keyboards or mice found on this PC; nothing copied.")
        return
    archive_path = env.target.path(ON_DRIVE)
    replaced = {f"bluetooth/{d.parent.name}/{d.name}" for d in devices}

    # Keep everything Batocera already has, except the devices we are about to supply.
    kept: list[tuple[tarfile.TarInfo, bytes | None]] = []
    if archive_path.exists():
        with tarfile.open(archive_path) as old:
            for member in old.getmembers():
                if any(member.name == r or member.name.startswith(r + "/") for r in replaced):
                    continue
                kept.append((member, old.extractfile(member).read() if member.isfile() else None))

    env.target.make_dir(archive_path.parent)
    built = io.BytesIO()
    with tarfile.open(fileobj=built, mode="w") as new:
        names = {member.name for member, _ in kept}
        for member, data in kept:
            new.addfile(member, io.BytesIO(data) if data is not None else None)

        def add_folder(name: str, mode: int = 0o700) -> None:
            if name not in names:
                folder = tarfile.TarInfo(name)
                folder.type, folder.mode, folder.mtime = tarfile.DIRTYPE, mode, time.time()
                new.addfile(folder)
                names.add(name)

        add_folder("bluetooth")
        for device in devices:
            add_folder(f"bluetooth/{device.parent.name}")
            add_folder(f"bluetooth/{device.parent.name}/{device.name}")
            info = _trusted((device / "info").read_text())
            for file_name, text in (("info", info), ("attributes", None)):
                source = device / file_name
                if text is None:
                    if not source.exists():
                        continue
                    text = source.read_text()
                data = text.encode()
                entry = tarfile.TarInfo(f"bluetooth/{device.parent.name}/{device.name}/{file_name}")
                # the pairing's own date, so a tool comparing copies (bt-share) knows how new it is
                entry.size, entry.mode, entry.mtime = len(data), 0o600, source.stat().st_mtime if source.exists() else time.time()
                new.addfile(entry, io.BytesIO(data))
            env.say(f"  {_name(info)}")   # the name only; the keys are never shown
    if not save_archive(archive_path, built.getvalue()):
        env.say("  The drive's pairings were kept: the new copy had none (nothing was changed).")


def pairings(data: bytes) -> int:
    """How many pairings (a device's info file holding a key) an archive has; 0 for a damaged one."""
    try:
        with tarfile.open(fileobj=io.BytesIO(data)) as archive:
            return sum(1 for member in archive.getmembers()
                       if member.isfile() and member.name.endswith("/info")
                       and b"Key=" in (archive.extractfile(member).read()))
    except (tarfile.TarError, OSError, EOFError):
        return 0


def save_archive(path: Path, data: bytes) -> bool:
    """Put the archive on the drive, unless it would lose every pairing: once it was saved empty,
    and every controller had to be paired again. An archive with pairings is never replaced by one
    without; and it is written beside and then moved into place, so it is never half-written.
    False when it was left as it was."""
    if path.exists() and pairings(path.read_bytes()) and not pairings(data):
        return False
    part = path.with_name(path.name + ".emubox-part")
    try:
        part.write_bytes(data)
        part.chmod(0o600)
        os.replace(part, path)
    finally:
        part.unlink(missing_ok=True)
    return True
