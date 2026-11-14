"""Facts about the PC the installer is running on."""
from __future__ import annotations

import os
import pwd
from pathlib import Path


class Host:
    def usb_devices(self) -> set[str]:
        """Connected USB devices as 'vendor:product' ids, e.g. '03f0:7397'."""
        found = set()
        for device in Path("/sys/bus/usb/devices").glob("*"):
            try:
                vendor = (device / "idVendor").read_text().strip()
                product = (device / "idProduct").read_text().strip()
            except OSError:
                continue
            found.add(f"{vendor}:{product}")
        return found


def expand(location: str) -> Path:
    """Turn '~/Games' into a real path, also when we were restarted through sudo or pkexec."""
    if location.startswith("~"):
        user = os.environ.get("SUDO_USER")
        if not user and os.environ.get("PKEXEC_UID"):
            user = pwd.getpwuid(int(os.environ["PKEXEC_UID"])).pw_name
        if user and (location == "~" or location.startswith("~/")):
            return Path(pwd.getpwnam(user).pw_dir) / location[2:]
    return Path(os.path.expanduser(location))
