#!/usr/bin/env python3
"""Drive a desktop app (Discord, a web player...) with a game controller.

Usage: pad.py <apps/NAME/app.json>

While the app's window has the focus, this takes over every gamepad and turns
its buttons into the keys, pointer movement and commands listed under "pad" in
the app's JSON file. The moment something else wants the controller (the
on-screen keyboard, Batocera's Control Center) or another window has the
focus (your game), it lets go, so nothing ever receives a press twice.

Button names are the ones printed on an Xbox-style pad:
    a b x y lb rb lt rt start select guide l3 r3 up down left right
A name can be joined to "select" to make a second layer: "select+start".

What a button can do:
    ["KEY_LEFTCTRL", "KEY_K"]   press these keys together (held while held)
    "click" / "rightclick"      mouse buttons
    "osk"                       open the on-screen keyboard
    "menu"                      open Batocera's Control Center
    "back"                      hide the app and return to the game
    "close"                     quit the app
    {"media": "Next"}           PlayPause, Next or Previous for whatever is playing
    {"run": "some command"}     run a shell command
Sticks ("left_stick", "right_stick"): "pointer", "scroll" or "dpad".
"""
from __future__ import annotations

import json
import os
import selectors
import subprocess
import sys
import time

import evdev
from evdev import UInput, ecodes as e

HERE = os.path.dirname(os.path.realpath(__file__))
EMUBOX_APP = os.path.join(os.path.dirname(HERE), "bin", "emubox-app")
OSK = os.path.join(HERE, "osk.py")
DEBUG = bool(os.environ.get("EMUBOX_DEBUG"))

FOCUS_POLL_S = 0.4        # how often we ask the compositor who has the focus
HANDOVER_S = 1.2          # time we give the keyboard / Control Center to take the pad
GONE_AFTER_S = 20         # quit this long after the app's window has vanished
STARTUP_GRACE_S = 90      # ...but allow this long for it to appear in the first place
TICK_S = 1 / 60           # pointer and scroll updates while a stick is pushed
STICK_DEADZONE = 0.18
POINTER_SPEED = 1100      # pixels per second with the stick fully over
SCROLL_SPEED = 14         # wheel notches per second with the stick fully over
TRIGGER_PULLED = 0.5

# xpad reports the X button as BTN_NORTH and Y as BTN_WEST; we follow the labels.
BUTTONS = {
    e.BTN_SOUTH: "a", e.BTN_EAST: "b", e.BTN_NORTH: "x", e.BTN_WEST: "y",
    e.BTN_TL: "lb", e.BTN_TR: "rb", e.BTN_TL2: "lt", e.BTN_TR2: "rt",
    e.BTN_START: "start", e.BTN_SELECT: "select", e.BTN_MODE: "guide",
    e.BTN_THUMBL: "l3", e.BTN_THUMBR: "r3",
    e.BTN_DPAD_UP: "up", e.BTN_DPAD_DOWN: "down", e.BTN_DPAD_LEFT: "left", e.BTN_DPAD_RIGHT: "right",
}
MOUSE_BUTTONS = {"click": e.BTN_LEFT, "rightclick": e.BTN_RIGHT}


def log(*words) -> None:
    if DEBUG:
        print(*words, file=sys.stderr, flush=True)


def wlrctl(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["wlrctl", "toplevel", *args], capture_output=True, text=True, check=False)


class App:
    """The window we serve, found by the start of its app id."""

    def __init__(self, prefix: str):
        self.prefix = prefix

    def window(self) -> str | None:
        for line in wlrctl("list").stdout.splitlines():
            app_id = line.split(": ", 1)[0]
            if app_id.startswith(self.prefix):
                return app_id
        return None

    def focused(self, app_id: str) -> bool:
        return wlrctl("find", f"app_id:{app_id}", "state:focused").returncode == 0


class Pad:
    def __init__(self, config: dict):
        self.name = config["id"]
        self.map: dict = config["pad"]
        self.app = App(config["window"])
        self.devices: list[evdev.InputDevice] = []
        self.selector = selectors.DefaultSelector()
        self.grabbed = False
        self.hands_off_until = 0.0
        self.waiting_for: subprocess.Popen | None = None  # the on-screen keyboard, while open
        self.down: dict[str, object] = {}                 # button -> the action it started
        self.sticks = {"left_stick": [0.0, 0.0], "right_stick": [0.0, 0.0]}
        self.stick_dirs: dict[str, str | None] = {}
        self.carry = {"x": 0.0, "y": 0.0, "wheel": 0.0}
        keys = {e.ecodes[k] for action in self.map.values() if isinstance(action, list) for k in action}
        self.out = UInput(
            {e.EV_KEY: sorted(keys | set(MOUSE_BUTTONS.values())), e.EV_REL: [e.REL_X, e.REL_Y, e.REL_WHEEL]},
            name="EmuBox app controller",
        )

    # --- taking and releasing the controllers -----------------------------------

    def _open_pads(self) -> None:
        known = {d.path for d in self.devices}
        for path in evdev.list_devices():
            if path in known:
                continue
            try:
                device = evdev.InputDevice(path)
            except OSError:
                continue
            if e.BTN_SOUTH in device.capabilities().get(e.EV_KEY, []) and device.name != self.out.name:
                self.devices.append(device)
                self.selector.register(device, selectors.EVENT_READ)
            else:
                device.close()

    def _forget(self, device: evdev.InputDevice) -> None:
        self.selector.unregister(device)
        self.devices.remove(device)
        device.close()

    def grab(self) -> bool:
        """Take the pads. False when somebody else is holding one (keyboard, Control Center)."""
        self._open_pads()
        taken = []
        for device in list(self.devices):
            try:
                device.grab()
                taken.append(device)
            except OSError as error:
                if error.errno == 19:  # unplugged
                    self._forget(device)
                    continue
                for other in taken:
                    other.ungrab()
                return False
        self.grabbed = bool(taken)
        if self.grabbed:
            log("took the controller")
        return self.grabbed

    def release(self) -> None:
        if not self.grabbed:
            return
        self.grabbed = False
        for button in list(self.down):
            self._button(button, False)
        for stick in self.sticks.values():
            stick[:] = [0.0, 0.0]
        for device in self.devices:
            try:
                device.ungrab()
            except OSError:
                pass
        log("let go of the controller")

    def hand_over(self) -> None:
        """Let go and stay away long enough for another program to take the pad."""
        self.release()
        self.hands_off_until = time.monotonic() + HANDOVER_S

    # --- what buttons do ----------------------------------------------------------

    def _button(self, name: str, pressed: bool) -> None:
        if pressed:
            if name != "select" and "select" in self.down and f"select+{name}" in self.map:
                name_used = f"select+{name}"
            else:
                name_used = name
            action = self.map.get(name_used)
            self.down[name] = action
            log("press", name_used, action)
            self._act(action, True)
        elif name in self.down:
            self._act(self.down.pop(name), False)

    def _act(self, action, pressed: bool) -> None:
        if action is None:
            return
        if isinstance(action, list):  # keys, held for as long as the button is
            for key in (action if pressed else reversed(action)):
                self.out.write(e.EV_KEY, e.ecodes[key], int(pressed))
            self.out.syn()
        elif action in MOUSE_BUTTONS:
            self.out.write(e.EV_KEY, MOUSE_BUTTONS[action], int(pressed))
            self.out.syn()
        elif not pressed:
            return
        elif isinstance(action, dict) and "media" in action:
            subprocess.Popen([EMUBOX_APP, "media", action["media"]], start_new_session=True)
        elif isinstance(action, dict):
            subprocess.Popen(action["run"], shell=True, start_new_session=True)
        elif action == "osk":
            self.hand_over()
            self.waiting_for = subprocess.Popen([sys.executable, OSK])
        elif action == "menu":
            self.hand_over()
            subprocess.Popen([os.path.join(os.path.dirname(HERE), "bin", "emubox-guide")], start_new_session=True)
        elif action in ("back", "close"):
            self.hand_over()
            subprocess.Popen([EMUBOX_APP, action, self.name], start_new_session=True)

    def _stick_as_dpad(self, stick: str) -> None:
        x, y = self.sticks[stick]
        for axis, value, names in (("x", x, ("left", "right")), ("y", y, ("up", "down"))):
            now = names[0] if value < -0.6 else names[1] if value > 0.6 else None
            key = f"{stick}{axis}"
            before = self.stick_dirs.get(key)
            if now != before:
                if before:
                    self._button(before, False)
                if now:
                    self._button(now, True)
                self.stick_dirs[key] = now

    def _event(self, device: evdev.InputDevice, event) -> None:
        if event.type == e.EV_KEY and event.code in BUTTONS and event.value in (0, 1):
            self._button(BUTTONS[event.code], bool(event.value))
        elif event.type == e.EV_ABS:
            if event.code in (e.ABS_HAT0X, e.ABS_HAT0Y):
                names = ("left", "right") if event.code == e.ABS_HAT0X else ("up", "down")
                for name in names:
                    self._button(name, False)
                if event.value:
                    self._button(names[0] if event.value < 0 else names[1], True)
                return
            info = device.absinfo(event.code)
            span = (info.max - info.min) or 1
            if event.code in (e.ABS_Z, e.ABS_RZ) and e.BTN_TL2 not in device.capabilities().get(e.EV_KEY, []):
                name = "lt" if event.code == e.ABS_Z else "rt"  # triggers that are axes
                pulled = (event.value - info.min) / span > TRIGGER_PULLED
                if pulled != (name in self.down):
                    self._button(name, pulled)
                return
            where = {e.ABS_X: ("left_stick", 0), e.ABS_Y: ("left_stick", 1),
                     e.ABS_RX: ("right_stick", 0), e.ABS_RY: ("right_stick", 1)}.get(event.code)
            if where:
                stick, index = where
                value = (event.value - info.min) / span * 2 - 1
                self.sticks[stick][index] = 0.0 if abs(value) < STICK_DEADZONE else value
                if self.map.get(stick) == "dpad":
                    self._stick_as_dpad(stick)

    def _move(self, dt: float) -> bool:
        """Pointer and wheel movement from the sticks. True while there is any."""
        moving = False
        for stick, (x, y) in self.sticks.items():
            use = self.map.get(stick)
            if use == "pointer" and (x or y):
                moving = True
                for axis, value, code in (("x", x, e.REL_X), ("y", y, e.REL_Y)):
                    # Squared, so a small push is precise and a full push is fast.
                    self.carry[axis] += value * abs(value) * POINTER_SPEED * dt
                    whole = int(self.carry[axis])
                    if whole:
                        self.carry[axis] -= whole
                        self.out.write(e.EV_REL, code, whole)
            elif use == "scroll" and y:
                moving = True
                self.carry["wheel"] -= y * abs(y) * SCROLL_SPEED * dt
                whole = int(self.carry["wheel"])
                if whole:
                    self.carry["wheel"] -= whole
                    self.out.write(e.EV_REL, e.REL_WHEEL, whole)
        if moving:
            self.out.syn()
        return moving

    # --- main loop ------------------------------------------------------------------

    def _wanted(self) -> bool | None:
        """Should we be holding the pad? None once the app has gone for good."""
        now = time.monotonic()
        window = self.app.window()
        if window:
            self.last_seen = now
        elif now - self.last_seen > (GONE_AFTER_S if self.seen else STARTUP_GRACE_S):
            return None
        self.seen = self.seen or bool(window)
        if self.waiting_for and self.waiting_for.poll() is not None:
            self.waiting_for = None
        if self.waiting_for or now < self.hands_off_until:
            return False
        return bool(window) and self.app.focused(window)

    def run(self) -> None:
        self.seen, self.last_seen = False, time.monotonic()
        next_poll, last_tick, moving = 0.0, time.monotonic(), False
        try:
            while True:
                now = time.monotonic()
                if now >= next_poll:
                    next_poll = now + FOCUS_POLL_S
                    wanted = self._wanted()
                    if wanted is None:
                        return
                    if wanted and not self.grabbed:
                        self.grab()  # fails quietly while someone else holds the pad
                    elif not wanted and self.grabbed:
                        self.release()
                timeout = TICK_S if moving else max(0.0, next_poll - time.monotonic())
                for key, _ in self.selector.select(timeout):
                    device = key.fileobj
                    try:
                        events = list(device.read())
                    except BlockingIOError:
                        continue
                    except OSError:
                        self._forget(device)
                        continue
                    if self.grabbed:  # otherwise the presses belong to someone else
                        for event in events:
                            self._event(device, event)
                now = time.monotonic()
                moving = self.grabbed and self._move(min(now - last_tick, 0.05))
                last_tick = now
        finally:
            self.release()
            self.out.close()


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    with open(sys.argv[1]) as f:
        config = json.load(f)
    config.setdefault("id", os.path.basename(os.path.dirname(os.path.realpath(sys.argv[1]))))
    Pad(config).run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
