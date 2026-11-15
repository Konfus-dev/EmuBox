#!/usr/bin/env python3
"""How busy the machine is, for the Guide menu's bottom row: memory in use, and the graphics
card's load where the system can tell it.

    sysload.py        print what it can read (for checking on a new PC)

Memory comes from /proc/meminfo. The graphics card's load comes from the kernel for AMD cards
(and others that offer gpu_busy_percent), or from NVIDIA's driver library (NVML, the one behind
nvidia-smi) for NVIDIA cards. Where neither is there (a virtual machine, most Intel graphics)
there is no figure, and the menu leaves the GPU out rather than show a wrong one.
"""
from __future__ import annotations

import ctypes
import glob


def memory(meminfo: str = "/proc/meminfo") -> tuple[int, int]:
    """(bytes in use, bytes in all); (0, 0) when it cannot be read."""
    values = {}
    try:
        with open(meminfo) as file:
            for line in file:
                name, _, rest = line.partition(":")
                values[name] = int(rest.split()[0]) * 1024
    except (OSError, ValueError, IndexError):
        return 0, 0
    total = values.get("MemTotal", 0)
    available = values.get("MemAvailable", values.get("MemFree", 0))
    return (max(0, total - available), total) if total else (0, 0)


class Gpu:
    """The graphics card's load in percent, read the cheapest way this PC offers."""

    def __init__(self, sysfs: str = "/sys/class/drm/card*/device/gpu_busy_percent", nvml: str = "libnvidia-ml.so.1"):
        self.source = ""
        self._read = None
        found = sorted(glob.glob(sysfs))
        if found:
            self.source, path = "kernel", found[0]
            self._read = lambda: int(open(path).read().strip())
            return
        try:
            self._nvml(ctypes.CDLL(nvml))
        except (OSError, AttributeError):
            pass

    def _nvml(self, lib) -> None:
        if lib.nvmlInit_v2() != 0:
            return
        handle = ctypes.c_void_p()
        if lib.nvmlDeviceGetHandleByIndex_v2(0, ctypes.byref(handle)) != 0:
            return

        class Rates(ctypes.Structure):
            _fields_ = [("gpu", ctypes.c_uint), ("memory", ctypes.c_uint)]

        def read() -> int:
            rates = Rates()
            if lib.nvmlDeviceGetUtilizationRates(handle, ctypes.byref(rates)) != 0:
                raise OSError("NVML could not read the load")
            return rates.gpu

        self.source, self._read = "nvidia", read

    def percent(self) -> int | None:
        """0-100, or None when this PC cannot tell."""
        if not self._read:
            return None
        try:
            return max(0, min(100, int(self._read())))
        except (OSError, ValueError):
            return None


if __name__ == "__main__":
    used, total = memory()
    gpu = Gpu()
    print(f"memory: {used / 2**30:.1f} of {total / 2**30:.1f} GB in use")
    print(f"gpu: {gpu.percent()}% (from {gpu.source})" if gpu.source else "gpu: no figure on this PC")
