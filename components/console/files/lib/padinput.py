"""Controller input for the console's own screens (the download notice, the store).

Takes over every connected gamepad while a screen is up, so presses do not
also reach whatever is underneath, and reports them by the names printed on an
Xbox-style pad: a b x y lb rb start select guide, and up down left right from
the d-pad or the left stick. Directions repeat while held.

Needs a running GLib main loop (GTK's will do).
"""
from __future__ import annotations

from collections.abc import Callable

import evdev
from evdev import ecodes as e
from gi.repository import GLib

REPEAT_DELAY_MS, REPEAT_EVERY_MS = 380, 95
STICK_THRESHOLD = 0.6

# xpad reports the X button as BTN_NORTH and Y as BTN_WEST; we follow the labels.
BUTTONS = {
    e.BTN_SOUTH: "a", e.BTN_EAST: "b", e.BTN_NORTH: "x", e.BTN_WEST: "y",
    e.BTN_TL: "lb", e.BTN_TR: "rb", e.BTN_START: "start", e.BTN_SELECT: "select", e.BTN_MODE: "guide",
    e.BTN_DPAD_UP: "up", e.BTN_DPAD_DOWN: "down", e.BTN_DPAD_LEFT: "left", e.BTN_DPAD_RIGHT: "right",
}
DIRECTIONS = {"x": ("left", "right"), "y": ("up", "down")}


class Pads:
    def __init__(self, on_press: Callable[[str], None], paths: list[str] | None = None):
        """Take the controllers: those at `paths` when the caller already knows them (opening every
        input device to find them is slow on a PC with many), otherwise every one there is."""
        self.on_press = on_press
        self.devices: list[evdev.InputDevice] = []
        self.timers: dict[str, int] = {}
        self.stick = {"x": 0, "y": 0}
        for path in paths or evdev.list_devices():
            try:
                device = evdev.InputDevice(path)
                if e.BTN_SOUTH not in device.capabilities().get(e.EV_KEY, []):
                    device.close()
                    continue
                device.grab()
            except OSError:
                continue
            self.devices.append(device)
            GLib.io_add_watch(device.fd, GLib.IO_IN, self._on_events, device)

    def release(self) -> None:
        for name in list(self.timers):
            self._stop(name)
        for device in self.devices:
            try:
                device.ungrab()
                device.close()
            except OSError:
                pass
        self.devices = []

    # --- held directions repeat ---------------------------------------------------

    def _start(self, name: str) -> None:
        self._stop(name)
        self.on_press(name)

        def again() -> bool:
            self.on_press(name)
            self.timers[name] = GLib.timeout_add(REPEAT_EVERY_MS, again)
            return False

        self.timers[name] = GLib.timeout_add(REPEAT_DELAY_MS, again)

    def _stop(self, name: str) -> None:
        timer = self.timers.pop(name, None)
        if timer:
            GLib.source_remove(timer)

    def _direction(self, axis: str, value: int) -> None:
        for name in DIRECTIONS[axis]:
            self._stop(name)
        if value:
            self._start(DIRECTIONS[axis][0 if value < 0 else 1])

    def _on_events(self, _fd, _condition, device) -> bool:
        try:
            events = list(device.read())
        except BlockingIOError:
            return True
        except OSError:
            return False  # unplugged
        for event in events:
            if event.type == e.EV_KEY and event.code in BUTTONS:
                name = BUTTONS[event.code]
                if name in ("up", "down", "left", "right"):
                    self._start(name) if event.value == 1 else self._stop(name) if event.value == 0 else None
                elif event.value == 1:
                    self.on_press(name)
            elif event.type == e.EV_ABS and event.code in (e.ABS_HAT0X, e.ABS_HAT0Y):
                self._direction("x" if event.code == e.ABS_HAT0X else "y", event.value)
            elif event.type == e.EV_ABS and event.code in (e.ABS_X, e.ABS_Y):
                info = device.absinfo(event.code)
                pushed = (event.value - (info.max + info.min) / 2) / ((info.max - info.min) / 2 or 1)
                value = -1 if pushed < -STICK_THRESHOLD else 1 if pushed > STICK_THRESHOLD else 0
                axis = "x" if event.code == e.ABS_X else "y"
                if value != self.stick[axis]:
                    self.stick[axis] = value
                    self._direction(axis, value)
        return True
