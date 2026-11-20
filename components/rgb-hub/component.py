"""RGB Hub: offered only on a PC that has its hardware; installed by its own script.

The lights program (it was called OMEN Lights) drives the HP OMEN PC's cooler screen,
case and memory lights, and the IQUNIX keyboard's lights. It lives in its own
repository (see "source" in component.json). We fetch it and run the installer it
ships, so EmuBox never carries a copy.
"""
from __future__ import annotations

import subprocess
from pathlib import Path


INSTALLER = Path("install") / "install-batocera.sh"
OLD_NAME = "OmenRGB-Controller"   # what a checkout made before the rename is called


def _local_checkout(repo: Path, name: str) -> Path | None:
    """The lights program's installer, when its repository is checked out near EmuBox."""
    for folder in (repo.parent, repo.parent.parent):
        for checkout in (name, OLD_NAME):
            if (folder / checkout / INSTALLER).is_file():
                return folder / checkout / INSTALLER
    return None


def available(env) -> bool:
    """True when this PC has the OMEN cooler screen or case-light board, or the IQUNIX keyboard."""
    wanted = set(env.component.spec["usb_devices"])
    return bool(wanted & env.host.usb_devices())


def install(env) -> None:
    source = env.component.spec["source"]
    script = _local_checkout(env.repo, source["sibling"]) or env.fetch(source["url"], "rgb-hub") / INSTALLER
    subprocess.run(["bash", str(script), str(env.target.root)], check=True, stdout=subprocess.DEVNULL)
