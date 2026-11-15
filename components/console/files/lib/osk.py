#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""A controller-driven on-screen keyboard for Batocera.

Shown over whatever app is running. While it is open it takes over the
controller: the d-pad or left stick moves between keys, and the buttons do
the common things directly (see PROMPTS below). What you type is sent to the
app underneath as ordinary key presses.

    osk.py            open the keyboard
    osk.py --toggle   open it, or close it if it is already open

Needs a Wayland compositor with layer-shell and virtual-keyboard support
(Batocera's labwc has both), GTK 3 and python-evdev; typing is done by typer.py.
"""

import os
import signal
import sys
import time

import evdev
import gi

# Batocera's display, for when we are started from a hotkey or script with a bare
# environment. GTK connects while it is being imported, so this has to come first.
os.environ.setdefault("XDG_RUNTIME_DIR", "/run")
os.environ.setdefault("WAYLAND_DISPLAY", "wayland-0")

gi.require_version("Gdk", "3.0")
gi.require_version("Gtk", "3.0")
gi.require_version("GtkLayerShell", "0.1")
from gi.repository import Gdk, GLib, Gtk, GtkLayerShell  # noqa: E402

PIDFILE = "/var/run/emubox-osk.pid"
DEBUG = bool(os.environ.get("EMUBOX_DEBUG"))  # log every controller action

# --- the keys -------------------------------------------------------------------
LETTERS = [
    list("1234567890"),
    list("qwertyuiop"),
    list("asdfghjkl'"),
    list("zxcvbnm,.?"),
]
SYMBOLS = [
    list("!@#$%^&*()"),
    list("-_=+[]{}\\|"),
    list(";:\"<>/~`€£"),
    list("…•°©®™¿¡§¶"),
]
# The bottom row: (what the key shows, what it does, how many columns wide)
BOTTOM = [("ABC ⇧", "shift", 2), ("#+=", "symbols", 1), ("space", "space", 2), ("phone", "phone", 2),
          ("⌫", "backspace", 1), ("⏎ enter", "enter", 2)]

# --- the buttons (shown along the bottom, so nobody has to remember them) ---------
PROMPTS = [("A", "Type"), ("B", "Backspace"), ("X", "Space"), ("Y", "Shift"),
           ("☰", "Enter"), ("LB RB", "Move cursor"), ("LT", "Symbols"), ("RT", "Tab"),
           ("⧉", "Close")]

REPEAT_DELAY_MS, REPEAT_EVERY_MS = 380, 95  # holding a direction or backspace
STICK_THRESHOLD = 0.6  # how far the stick must be pushed to count as a direction

CSS = b"""
window { background-color: rgba(2, 18, 2, 0.94); border-top: 2px solid #82e846; }
* { font-family: "Rajdhani", sans-serif; color: #d6f9b8; }
.key { background-color: #062606; border: 1px solid #1a5a16; border-radius: 3px;
       font-size: 26px; font-weight: 600; min-height: 54px; }
.key.wide { font-size: 20px; }
.key.focus { background-color: #c8f03c; border-color: #f0ffd7; color: #0a2a00; }
.key.focus label { color: #0a2a00; }
.key.on { border-color: #c8f03c; }
.prompts { background-color: rgba(11, 71, 11, 0.9); padding: 6px 18px; }
.glyph { background-color: #124a10; border: 2px solid #96f550; border-radius: 14px;
         font-family: "Michroma", sans-serif; font-size: 13px; padding: 2px 9px; color: #f0ffd7; }
.prompt { font-size: 18px; margin-right: 16px; }
"""


TYPER = None   # our keyboard for typing into the app underneath (typer.py), made when the screen opens


class Keyboard(Gtk.Window):
    def __init__(self):
        super().__init__(title="EmuBox Keyboard")
        GtkLayerShell.init_for_window(self)
        GtkLayerShell.set_layer(self, GtkLayerShell.Layer.OVERLAY)
        GtkLayerShell.set_keyboard_interactivity(self, False)  # never steal the app's focus
        for edge in (GtkLayerShell.Edge.BOTTOM, GtkLayerShell.Edge.LEFT, GtkLayerShell.Edge.RIGHT):
            GtkLayerShell.set_anchor(self, edge, True)

        provider = Gtk.CssProvider()
        provider.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        self.phone = False  # set when the PHONE key ends the keyboard: the phone keyboard follows
        self.shift = 0  # 0 off, 1 next letter only, 2 locked
        self.symbols = False
        self.row, self.col = 1, 0
        self.rows: list[list[tuple[Gtk.Widget, str]]] = []  # (widget, action or character)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.grid = Gtk.Grid(column_homogeneous=True, column_spacing=6, row_spacing=6,
                             margin=14, margin_start=120, margin_end=120)
        box.pack_start(self.grid, True, True, 0)
        box.pack_start(self._prompt_bar(), False, False, 0)
        self.add(box)
        self._build()
        self.show_all()

        self.pads = self._grab_pads()
        self.held: dict[str, int] = {}  # action being repeated -> GLib timer
        self.stick = {"x": 0, "y": 0}

    # --- drawing ----------------------------------------------------------------

    def _prompt_bar(self) -> Gtk.Widget:
        bar = Gtk.Box(spacing=6, halign=Gtk.Align.CENTER)
        bar.get_style_context().add_class("prompts")
        for glyph, meaning in PROMPTS:
            g = Gtk.Label(label=glyph)
            g.get_style_context().add_class("glyph")
            m = Gtk.Label(label=meaning)
            m.get_style_context().add_class("prompt")
            bar.pack_start(g, False, False, 0)
            bar.pack_start(m, False, False, 0)
        return bar

    def _key(self, text: str, action: str, left: int, top: int, width: int = 1) -> Gtk.Widget:
        key = Gtk.Label(label=text)
        frame = Gtk.EventBox()
        frame.add(key)
        frame.get_style_context().add_class("key")
        if width > 1:
            frame.get_style_context().add_class("wide")
        self.grid.attach(frame, left, top, width, 1)
        return frame

    def _build(self) -> None:
        for child in self.grid.get_children():
            self.grid.remove(child)
        self.rows = []
        for top, chars in enumerate(SYMBOLS if self.symbols else LETTERS):
            row = []
            for left, char in enumerate(chars):
                shown = char.upper() if self.shift and not self.symbols else char
                row.append((self._key(shown, shown, left, top), shown))
            self.rows.append(row)
        row, left = [], 0
        for text, action, width in BOTTOM:
            widget = self._key(text, action, left, len(self.rows), width)
            if (action == "shift" and self.shift) or (action == "symbols" and self.symbols):
                widget.get_style_context().add_class("on")
            # A wide key is reachable from every column it spans.
            row.extend([(widget, action)] * width)
            left += width
        self.rows.append(row)
        self.grid.show_all()
        self._focus()

    def _focus(self) -> None:
        for row in self.rows:
            for widget, _ in row:
                widget.get_style_context().remove_class("focus")
        self.rows[self.row][self.col][0].get_style_context().add_class("focus")

    # --- what the keys and buttons do ---------------------------------------------

    def move(self, dx: int, dy: int) -> None:
        self.row = (self.row + dy) % len(self.rows)
        width = len(self.rows[self.row])
        if dx:
            here = self.rows[self.row][self.col][0]
            # Step over the extra columns of a wide key instead of "moving" within it.
            for _ in range(width):
                self.col = (self.col + dx) % width
                if self.rows[self.row][self.col][0] is not here:
                    break
        self.col = min(self.col, width - 1)
        self._focus()

    def press(self, action: str) -> None:
        if action == "shift":
            self.shift = (self.shift + 1) % 3
            self._build()
        elif action == "symbols":
            self.symbols = not self.symbols
            self._build()
        elif action == "phone":   # type on a phone instead: a QR code to scan (phonekeys.py)
            self.phone = True
            Gtk.main_quit()
        elif action in ("space", "backspace", "enter", "tab", "left", "right"):
            TYPER.key(action)
        else:  # an ordinary character
            TYPER.text(action)
            if self.shift == 1:  # shift was for one letter only
                self.shift = 0
                self._build()

    def press_focused(self) -> None:
        self.press(self.rows[self.row][self.col][1])

    # --- the controller -------------------------------------------------------------

    def _grab_pads(self) -> list[evdev.InputDevice]:
        """Take over every gamepad, so the app underneath does not also react."""
        pads = []
        for path in evdev.list_devices():
            try:
                device = evdev.InputDevice(path)
                if evdev.ecodes.BTN_SOUTH not in device.capabilities().get(evdev.ecodes.EV_KEY, []):
                    device.close()
                    continue
                device.grab()
            except OSError:
                continue
            pads.append(device)
            GLib.io_add_watch(device.fd, GLib.IO_IN, self._on_pad, device)
        return pads

    def release_pads(self) -> None:
        for device in self.pads:
            try:
                device.ungrab()
                device.close()
            except OSError:
                pass

    BUTTONS = {
        evdev.ecodes.BTN_SOUTH: "type", evdev.ecodes.BTN_EAST: "backspace",
        evdev.ecodes.BTN_WEST: "shift", evdev.ecodes.BTN_NORTH: "space",
        evdev.ecodes.BTN_TL: "left", evdev.ecodes.BTN_TR: "right",
        evdev.ecodes.BTN_START: "enter", evdev.ecodes.BTN_SELECT: "close",
        evdev.ecodes.BTN_THUMBL: "close", evdev.ecodes.BTN_MODE: "close",
        evdev.ecodes.BTN_TL2: "symbols", evdev.ecodes.BTN_TR2: "tab",
    }
    REPEATING = ("backspace", "left", "right", "up", "down", "move-left", "move-right")

    def _do(self, what: str) -> None:
        if DEBUG:
            print("pad:", what, file=sys.stderr, flush=True)
        if what == "close":
            Gtk.main_quit()
        elif what == "type":
            self.press_focused()
        elif what.startswith("move-") or what in ("up", "down"):
            dx = {"move-left": -1, "move-right": 1}.get(what, 0)
            dy = {"up": -1, "down": 1}.get(what, 0)
            self.move(dx, dy)
        else:
            self.press(what)

    def _start(self, what: str) -> None:
        self._stop(what)
        self._do(what)
        if what in self.REPEATING:
            def repeat():
                # The release may already be waiting unread (a slow frame delays us):
                # catch up on the pad first, so a tap never turns into a run of repeats.
                self.held[what] = 0
                for device in self.pads:
                    self._read(device)
                if self.held.get(what) != 0:  # let go, or pressed afresh, meanwhile
                    return False
                self._do(what)
                self.held[what] = GLib.timeout_add(REPEAT_EVERY_MS, repeat)
                return False
            self.held[what] = GLib.timeout_add(REPEAT_DELAY_MS, repeat)

    def _stop(self, what: str) -> None:
        timer = self.held.pop(what, None)
        if timer:
            GLib.source_remove(timer)

    def _direction(self, axis: str, value: int) -> None:
        """A d-pad or stick axis changed to -1, 0 or 1."""
        names = ("move-left", "move-right") if axis == "x" else ("up", "down")
        for name in names:
            self._stop(name)
        if value:
            self._start(names[0] if value < 0 else names[1])

    def _on_pad(self, _fd, _condition, device) -> bool:
        return self._read(device)

    def _read(self, device) -> bool:
        """Handle everything the pad has sent so far; False once it is unplugged."""
        try:
            events = list(device.read())
        except BlockingIOError:
            return True  # nothing waiting
        except OSError:
            return False  # unplugged
        e = evdev.ecodes
        for event in events:
            if event.type == e.EV_KEY and event.code in self.BUTTONS:
                what = self.BUTTONS[event.code]
                self._start(what) if event.value == 1 else self._stop(what) if event.value == 0 else None
            elif event.type == e.EV_ABS:
                if event.code in (e.ABS_HAT0X, e.ABS_HAT0Y):
                    self._direction("x" if event.code == e.ABS_HAT0X else "y", event.value)
                elif event.code in (e.ABS_X, e.ABS_Y):
                    info = device.absinfo(event.code)
                    middle = (info.max + info.min) / 2
                    pushed = (event.value - middle) / ((info.max - info.min) / 2 or 1)
                    value = -1 if pushed < -STICK_THRESHOLD else 1 if pushed > STICK_THRESHOLD else 0
                    axis = "x" if event.code == e.ABS_X else "y"
                    if value != self.stick[axis]:
                        self.stick[axis] = value
                        self._direction(axis, value)
                elif event.code in (e.ABS_Z, e.ABS_RZ) and e.BTN_TL2 not in self.BUTTONS_PRESENT(device):
                    # Triggers that report as axes (Xbox pads): treat a firm pull as a press.
                    name = "symbols" if event.code == e.ABS_Z else "tab"
                    info = device.absinfo(event.code)
                    pulled = event.value > (info.max + info.min) / 2
                    key = f"trigger-{name}"
                    if pulled and key not in self.held:
                        self.held[key] = 0
                        self._do(name)
                    elif not pulled:
                        self.held.pop(key, None)
        return True

    @staticmethod
    def BUTTONS_PRESENT(device) -> list[int]:
        return device.capabilities().get(evdev.ecodes.EV_KEY, [])


def running_pid() -> int | None:
    try:
        pid = int(open(PIDFILE).read())
        os.kill(pid, 0)
        return pid
    except (OSError, ValueError):
        return None


def main() -> int:
    pid = running_pid()
    if pid:
        if "--toggle" in sys.argv:
            os.kill(pid, signal.SIGTERM)
        return 0
    with open(PIDFILE, "w") as f:
        f.write(str(os.getpid()))
    global TYPER
    from typer import Typer
    TYPER = Typer()
    keyboard = Keyboard()
    GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGTERM, Gtk.main_quit)
    try:
        Gtk.main()
    finally:
        keyboard.release_pads()
        TYPER.close()
        time.sleep(0.05)
        try:
            os.unlink(PIDFILE)
        except OSError:
            pass
    if keyboard.phone:
        # In our place, as the same process: whoever opened the keyboard (an app's pad
        # mapper, the web view) is waiting for it to end, and now waits for this instead.
        keyboard.destroy()
        while Gtk.events_pending():
            Gtk.main_iteration()
        here = os.path.dirname(os.path.realpath(__file__))
        os.execv(sys.executable, [sys.executable, os.path.join(here, "phonekeys.py")])
    return 0


if __name__ == "__main__":
    sys.exit(main())
