"""OMEN Lights: offered only on a PC that has the hardware; installed by its own script.

The program lives in its own repository (see "source" in component.json). We
fetch it and run the installer it ships, so EmuBox never carries a copy.
"""
from __future__ import annotations

import subprocess
from pathlib import Path


INSTALLER = Path("install") / "install-batocera.sh"


def _local_checkout(repo: Path, name: str) -> Path | None:
    """The lights program's installer, when its repository is checked out near EmuBox."""
    for folder in (repo.parent, repo.parent.parent):
        if (folder / name / INSTALLER).is_file():
            return folder / name / INSTALLER
    return None


def available(env) -> bool:
    """True when this PC has the OMEN cooler screen or case-light board."""
    wanted = set(env.component.spec["usb_devices"])
    return bool(wanted & env.host.usb_devices())


def install(env) -> None:
    source = env.component.spec["source"]
    script = _local_checkout(env.repo, source["sibling"]) or env.fetch(source["url"], "omen-lights") / INSTALLER
    subprocess.run(["bash", str(script), str(env.target.root)], check=True, stdout=subprocess.DEVNULL)
