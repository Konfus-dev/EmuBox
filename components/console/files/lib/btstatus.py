#!/usr/bin/env python3
"""Bluetooth at a glance, for the Guide menu's Bluetooth rows.

    btstatus.py adapter    "On", "Off" or "Not working" (no adapter found: see the log)
    btstatus.py pads       the connected controllers with their battery, e.g. "Xbox Wireless Controller 80%"
    btstatus.py pair       Batocera's own pairing (batocera-bluetooth trust input: a minute of looking
                           for anything in pairing mode); the Guide runs it in EmuBox's wait screen

Stopping "pair" (B in the wait screen) also stops the looking: Batocera's command only cleans up
after Ctrl+C, and left alone its agent would keep pairing whatever input device comes near.
"""
from __future__ import annotations

import os
import re
import signal
import subprocess
import sys


def _ctl(*args: str) -> str:
    try:
        return subprocess.run(["bluetoothctl", *args], capture_output=True, text=True, timeout=4).stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def adapter(show: str | None = None) -> str:
    show = _ctl("show") if show is None else show
    if not show.strip() or "No default controller" in show:
        return "Not working"
    return "On" if re.search(r"^\s*Powered: yes", show, re.M) else "Off"


def battery(info: str) -> str:
    """'Battery Percentage: 0x50 (80)' -> '80%'."""
    found = re.search(r"Battery Percentage: \S+ \((\d+)\)", info)
    return f"{found.group(1)}%" if found else ""


def is_input(info: str) -> bool:
    return bool(re.search(r"Icon: input-(gaming|keyboard|mouse)|UUID: Human Interface Device", info))


def pads() -> str:
    found = []
    for line in _ctl("devices", "Connected").splitlines():
        parts = line.split(" ", 2)
        if len(parts) == 3 and parts[0] == "Device":
            info = _ctl("info", parts[1])
            if is_input(info):
                found.append(" ".join(x for x in (parts[2], battery(info)) if x))
    return ", ".join(found) if found else "None connected"


def pair() -> int:
    child = subprocess.Popen(["batocera-bluetooth", "trust", "input"])

    def stop(*_):
        try:
            child.send_signal(signal.SIGINT)        # its own clean-up: discovery off, saved
            child.wait(timeout=5)
        except (OSError, subprocess.SubprocessError):
            pass
        try:   # and in case it was gone already: the agent stops looking (what its clean-up does)
            os.kill(int(open("/var/run/bluetooth-agent.pid").read().strip()), signal.SIGUSR2)
        except (OSError, ValueError):
            pass
        try:
            os.remove("/var/run/bt_device")
        except OSError:
            pass
        sys.exit(130)

    signal.signal(signal.SIGTERM, stop)
    return child.wait()


def main(argv: list[str]) -> int:
    what = argv[0] if argv else "adapter"
    if what == "adapter":
        print(adapter())
    elif what == "pads":
        print(pads())
    elif what == "pair":
        return pair()
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
