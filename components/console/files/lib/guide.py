#!/usr/bin/env python3
"""EmuBox's Guide menu: the quick menu the Guide button opens, over the menus or a running game.

    guide.py            start it, hidden (the emubox service does, at boot)
    guide.py --show     start it and show it at once
    bin/emubox-guide    show it, or hide it when it is showing (what the Guide button runs)

Batocera's own quick menu cannot hold controls in its bottom strip, so EmuBox draws
this one itself. Along the top: the time and the network address. Tabs: Settings (the
few settings worth having one press away, and a way into the full ones), Apps, Record,
and Game while a game is running. Along the bottom: a bar for each app that is doing
something (a call with its microphone switch, the music with its buttons), then the
processor load and how full the drive is.

Controller: d-pad or left stick moves, A presses, left/right changes a value, LB/RB
change tab, B or Guide closes. A keyboard works too (arrows, Enter, Page Up/Down, Esc).

What is in the menu is described by `layout()` below, in terms of a few kinds of
control whose values and actions are shell commands; `Model` is the part that moves
the highlight, kept free of any drawing so it can be tested.
"""
from __future__ import annotations

import glob
import json
import os
import signal
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import space

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
APP = ROOT / "bin" / "emubox-app"
PID = Path("/var/run/emubox/guide.pid")
RUNNING_GAME = "curl -s -m 1 http://127.0.0.1:1234/runningGame"
REFRESH_S = 1.5

Getter = "str | Callable[[], str]"   # a shell command whose output is the value, or a function


# --- what the menu is made of ---------------------------------------------------------

@dataclass
class Control:
    kind: str                      # "button", "switch", "stepper", "chooser" or "text"
    label: str = ""                # a button's words
    get: object = ""               # Getter: the value shown (switch: anything but ""/0/false/off is on)
    do: str = ""                   # button: the command to run
    on: str = ""                   # switch: commands for on and off
    off: str = ""
    less: str = ""                 # stepper and chooser: commands for left and right
    more: str = ""
    close: bool = False            # hide the menu once pressed
    confirm: bool = False          # a second press is needed
    value: str = ""                # last value read

    @property
    def focusable(self) -> bool:
        return self.kind != "text"


@dataclass
class Row:
    label: str
    controls: list[Control]
    when: object = ""              # Getter: the row exists only while this gives something
    shown: bool = True
    heading: bool = False          # a category's name, not a setting

    @property
    def focusable(self) -> bool:
        return self.shown and any(c.focusable for c in self.controls)


@dataclass
class Tab:
    title: str
    rows: list[Row]
    when: object = ""
    shown: bool = True


def button(label: str, do: str, close: bool = False, confirm: bool = False) -> Control:
    return Control("button", label=label, do=do, close=close, confirm=confirm)


def switch(get: object, on: str, off: str) -> Control:
    return Control("switch", get=get, on=on, off=off)


def stepper(get: object, less: str, more: str) -> Control:
    return Control("stepper", get=get, less=less, more=more)


def chooser(get: object, less: str, more: str) -> Control:
    return Control("chooser", get=get, less=less, more=more)


def text(get: object) -> Control:
    return Control("text", get=get)


def heading(title: str) -> Row:
    """A category's name above its rows; the highlight passes over it."""
    return Row(title, [], heading=True)


def truthy(value: str) -> bool:
    return value.strip().lower() not in ("", "0", "false", "off", "no", "null")


def apps(folder: Path | None = None) -> list[tuple[str, dict]]:
    found = []
    for path in sorted(glob.glob(str((folder or ROOT / "apps") / "*" / "app.json"))):
        try:
            with open(path) as file:
                found.append((os.path.basename(os.path.dirname(path)), json.load(file)))
        except (OSError, ValueError):
            continue
    return found


def layout(found: list[tuple[str, dict]] | None = None, lights: bool | None = None) -> tuple[list[Tab], list[Row]]:
    """The tabs and the bars along the bottom."""
    found = apps() if found is None else found
    lights = (HERE / "startmenu_omen.py").is_file() if lights is None else lights
    a, lib = str(APP), str(HERE)
    sounds, omen = f"python3 {lib}/menusounds.py", f"python3 {lib}/startmenu_omen.py"
    in_game = f"{RUNNING_GAME} | jq -r '.name // empty' 2>/dev/null"
    in_menus = f"[ -z \"$({in_game})\" ] && echo yes"

    settings = [
        heading("Sound"),
        Row("Volume", [stepper("batocera-audio getSystemVolume", "batocera-audio setSystemVolume -5",
                               "batocera-audio setSystemVolume +5")]),
        Row("Mute", [switch("batocera-audio getSystemMute", "batocera-audio setSystemVolume mute",
                            "batocera-audio setSystemVolume unmute")]),
        Row("Menu sounds", [chooser(f"{sounds} set-now", f"{sounds} previous", f"{sounds} next")]),
        Row("Menu sound volume", [stepper(f"python3 {lib}/settings.py get ui.sound_volume",
                                          f"{sounds} volume -10", f"{sounds} volume +10")]),
    ]
    if lights:
        settings += [
            heading("OMEN Lighting"),
            Row("Lights", [switch(f"{omen} is lights-enabled", f"{omen} set lights-enabled on", f"{omen} set lights-enabled off")]),
            Row("Brightness", [stepper(f"{omen} get lights-brightness", f"{omen} step lights-brightness -10",
                                       f"{omen} step lights-brightness +10")]),
            Row("Follow the game", [switch(f"{omen} is auto-enabled", f"{omen} set auto-enabled on",
                                           f"{omen} set auto-enabled off")]),
        ]
    settings += [
        heading("System"),
        Row("Power", [chooser("cat /sys/devices/system/cpu/cpufreq/policy0/scaling_governor 2>/dev/null",
                              f"{a} power previous", f"{a} power next")]),
        Row("Plane mode", [switch("batocera-planemode status", "batocera-planemode enable", "batocera-planemode disable")]),
        Row("Stuck emulator?", [button("Stop it", "curl -s http://127.0.0.1:1234/emukill", confirm=True)]),
        Row("Everything else", [button("Open full settings", "hotkeygen --send menu", close=True)], when=in_menus),
    ]

    listed = [(app_id, app) for app_id, app in found if app.get("menu", True)]
    def opening(app_id: str, app: dict) -> str:
        if app.get("web"):   # a site in EmuBox's own web view
            return f"setsid python3 {lib}/webview.py '{app['web']}' --id {app_id} >/dev/null 2>&1 &"
        return f"{a} detach open {app_id}"

    def opens(which: list[tuple[str, dict]]) -> list[Row]:
        return [Row(app["name"], [button("Open", opening(app_id, app), close=True)]) for app_id, app in which]

    # Programs Batocera already has (Terminal, Files, Claude) are tools; the rest are apps.
    tools = [(app_id, app) for app_id, app in listed if app.get("command")]
    app_rows = [heading("Apps")] + opens([entry for entry in listed if entry not in tools])
    if tools:
        app_rows += [heading("Tools")] + opens(tools)
    app_rows += [heading("Game"), Row("Game", [button("Back to game", f"{a} back", close=True)])]

    game = [
        Row("Playing", [text(in_game)]),
        Row("Game", [button("Resume", "true", close=True),
                     button("Emulator options", "hotkeygen --send menu", close=True),
                     button("Quit game", "hotkeygen --send exit", close=True, confirm=True)]),
    ]
    record = [Row("Recording", [switch("batocera-record is_running | grep true", "batocera-record start", "batocera-record stop")])]
    tabs = [Tab("Game", game, when=in_game), Tab("Settings", settings), Tab("Apps", app_rows), Tab("Record", record)]

    # One bar for each app that is doing something, with what you would want to reach for.
    bars = []
    for app_id, app in listed:
        if app.get("voice"):
            bars.append(Row(app["name"], [text(f"{a} status call"), text("echo Mute microphone"),
                                          switch(f"{a} mic muted", f"{a} mic mute", f"{a} mic unmute")],
                            when=f"{a} status call"))
        if app.get("player"):
            bars.append(Row(app["name"], [text(f"{a} status music"),
                                          button("<", f"{a} media Previous"), button("||", f"{a} media PlayPause"),
                                          button(">", f"{a} media Next")],
                            when=f"{a} status music"))
    # The menus' own music, while it is what you hear (music.py goes quiet for a game or your music app).
    music = f"python3 {lib}/music.py"
    bars.append(Row("Menu music", [text(f"{music} line"), button("<", f"{music} previous"), button("||", f"{music} toggle"),
                                   button(">", f"{music} next")], when=f"{music} line"))
    return tabs, bars


# --- moving the highlight ---------------------------------------------------------------

@dataclass
class Model:
    tabs: list[Tab]
    bars: list[Row]
    tab: int = 0
    row: int = 0
    column: int = 0
    armed: Control | None = None       # a "confirm" button that has been pressed once
    ran: list[str] = field(default_factory=list)

    def shown_tabs(self) -> list[Tab]:
        return [t for t in self.tabs if t.shown]

    def page(self) -> Tab:
        tabs = self.shown_tabs()
        self.tab = max(0, min(self.tab, len(tabs) - 1))
        return tabs[self.tab]

    def rows(self) -> list[Row]:
        """Every row the highlight can land on: the tab's own, then the bars."""
        return [r for r in self.page().rows + self.bars if r.focusable]

    def controls(self) -> list[Control]:
        rows = self.rows()
        if not rows:
            return []
        self.row = max(0, min(self.row, len(rows) - 1))
        return [c for c in rows[self.row].controls if c.focusable]

    def current(self) -> Control | None:
        controls = self.controls()
        if not controls:
            return None
        self.column = max(0, min(self.column, len(controls) - 1))
        return controls[self.column]

    def open_on(self, title: str) -> None:
        """Start on a tab by name (when it is showing), at the top."""
        for index, tab in enumerate(self.shown_tabs()):
            if tab.title == title:
                self.tab = index
        self.row = self.column = 0
        self.armed = None

    def press(self, key: str) -> str:
        """Act on a key: up down left right a b lb rb. Gives "close" when the menu should go away,
        "moved" when only the highlight changed, "ran" when a command was started (in .ran)."""
        self.ran = []
        armed, self.armed = self.armed, None
        control = self.current()
        if key in ("b", "guide"):
            return "close"
        if key in ("lb", "rb"):
            count = len(self.shown_tabs())
            self.tab = (self.tab + (1 if key == "rb" else -1)) % max(1, count)
            self.row = self.column = 0
            return "moved"
        if key in ("up", "down"):
            count = len(self.rows())
            if count:
                self.row = (self.row + (1 if key == "down" else -1)) % count
                self.column = min(self.column, max(0, len(self.controls()) - 1))
            return "moved"
        if control is None:
            return "moved"
        if key in ("left", "right"):
            if control.kind in ("stepper", "chooser"):
                self.ran = [control.less if key == "left" else control.more]
                return "ran"
            self.column = max(0, min(len(self.controls()) - 1, self.column + (1 if key == "right" else -1)))
            return "moved"
        if key == "a":
            if control.kind == "switch":
                self.ran = [control.off if truthy(control.value) else control.on]
                control.value = "" if truthy(control.value) else "true"   # shows at once; the next reading confirms
                return "ran"
            if control.kind == "button":
                if control.confirm and armed is not control:
                    self.armed = control
                    return "moved"
                self.ran = [control.do]
                return "close" if control.close else "ran"
        return "moved"


# --- reading values -----------------------------------------------------------------------

def read(get: object) -> str:
    if callable(get):
        try:
            return str(get())
        except Exception:   # noqa: BLE001
            return ""
    if not get:
        return ""
    try:
        return subprocess.run(["bash", "-c", get], capture_output=True, text=True, timeout=3, check=False).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return ""


def refresh(model: Model) -> None:
    """Read every value the menu shows (slow: commands are run; call it off the screen's thread)."""
    seen: dict[object, str] = {}

    def value(get: object) -> str:
        if get not in seen:
            seen[get] = read(get)
        return seen[get]

    for tab in model.tabs:
        tab.shown = truthy(value(tab.when)) if tab.when else True
    page = model.page()
    for row in page.rows + model.bars:
        row.shown = truthy(value(row.when)) if row.when else True
        if row.shown:
            for control in row.controls:
                if control.get:
                    control.value = value(control.get)


class Load:
    """Processor load since the last look, in percent."""

    def __init__(self):
        self.before = self._now()

    @staticmethod
    def _now() -> tuple[int, int]:
        try:
            parts = [int(x) for x in open("/proc/stat").readline().split()[1:8]]
        except (OSError, ValueError):
            return 0, 0
        return sum(parts), parts[3] + parts[4]

    def percent(self) -> int:
        total, idle = self._now()
        was_total, was_idle = self.before
        self.before = (total, idle)
        spent = total - was_total
        return max(0, min(100, round(100 * (spent - (idle - was_idle)) / spent))) if spent > 0 else 0


# --- the screen ----------------------------------------------------------------------------

CSS = b"""
window { background-color: rgba(1, 12, 1, 0.55); }
* { font-family: "Rajdhani", sans-serif; color: #d6f9b8; }
.pane { background-color: rgba(2, 20, 2, 0.93); border: 2px solid #a8f65c;
        box-shadow: inset 0 0 0 5px rgba(2, 18, 2, 0), inset 0 0 0 6px rgba(58, 140, 44, 0.75), inset 0 0 30px rgba(120, 255, 60, 0.14); }
.top { padding: 10px 28px 6px 28px; border-bottom: 1px solid rgba(150, 245, 80, 0.4); }
.brand { font-family: "Michroma", sans-serif; font-size: 22px; color: #c8f03c; }
.small { font-size: 18px; color: #8fcf6a; }
.tabs { padding: 14px 28px 0 28px; }
.tab { font-family: "Michroma", sans-serif; font-size: 17px; color: #6fa85c; padding: 9px 26px; margin-right: 8px;
       border: 1px solid #2f7d1e; border-top: 3px solid #2f7d1e; border-bottom: none; background-color: rgba(4, 30, 4, 0.8); }
.tab.open { color: #f0ffd7; border-color: #a8f65c; border-top-color: #c8f03c;
            background-image: linear-gradient(to bottom, rgba(120, 255, 60, 0.30), rgba(4, 30, 4, 0)); }
.hint { font-size: 16px; color: #8fcf6a; }
.page { padding: 14px 28px; border-top: 1px solid rgba(150, 245, 80, 0.4); }
.row { padding: 3px 10px; border: 1px solid transparent; }
.row.at { background-color: rgba(150, 245, 80, 0.08); border-color: rgba(150, 245, 80, 0.35); }
.name { font-size: 20px; }
.heading { padding: 12px 10px 2px 10px; border-bottom: 1px solid rgba(150, 245, 80, 0.3); margin-bottom: 3px; }
.heading label { font-family: "Michroma", sans-serif; font-size: 14px; color: #c8f03c; }
.value { font-size: 20px; color: #c8f03c; }
.control { font-size: 18px; padding: 3px 16px; margin-left: 10px; border: 1px solid #68c43c; border-left-width: 3px;
           background-color: rgba(8, 52, 8, 0.85); }
.control.focus { background-image: linear-gradient(to bottom, #f0ff8c, #9adc20); border-color: #f4ffb4; color: #0a2a00;
                 box-shadow: 0 0 10px rgba(180, 255, 70, 0.75); }
.control.focus label { color: #0a2a00; }
.control.armed { background-image: linear-gradient(to bottom, #ffd27a, #e08a1e); border-color: #ffe9b0; }
.control.on { border-color: #c8f03c; }
.bars { padding: 4px 28px; }
scrolledwindow, viewport { background-color: transparent; border: none; }
.bar { padding: 6px 10px; margin-top: 6px; border: 1px solid rgba(150, 245, 80, 0.45); background-color: rgba(8, 52, 8, 0.6); }
.bar.at { border-color: #c8f03c; background-color: rgba(150, 245, 80, 0.10); }
.foot { padding: 8px 28px 10px 28px; border-top: 1px solid rgba(150, 245, 80, 0.4); margin-top: 8px; }
progressbar trough { background-color: rgba(4, 30, 4, 0.9); border: 1px solid #2f7d1e; min-height: 10px; min-width: 180px; }
progressbar progress { background-image: linear-gradient(to bottom, #f0ff8c, #9adc20); border: none; min-height: 10px; }
"""


def screen(show_now: bool) -> int:
    os.environ.setdefault("XDG_RUNTIME_DIR", "/var/run")
    os.environ.setdefault("WAYLAND_DISPLAY", "wayland-0")
    if os.environ.get("HOME", "/") == "/":
        os.environ["HOME"] = "/userdata/system"   # where the look's fonts are; a boot service has no home
    import gi
    gi.require_version("Gdk", "3.0")
    gi.require_version("Gtk", "3.0")
    gi.require_version("GtkLayerShell", "0.1")
    from gi.repository import Gdk, GLib, Gtk, GtkLayerShell, Pango

    from padinput import Pads

    def label(words: str, style: str, **properties) -> Gtk.Label:
        widget = Gtk.Label(label=words, **properties)
        widget.get_style_context().add_class(style)
        return widget

    class Guide(Gtk.Window):
        def __init__(self):
            super().__init__(title="EmuBox Guide")
            GtkLayerShell.init_for_window(self)
            GtkLayerShell.set_layer(self, GtkLayerShell.Layer.OVERLAY)
            GtkLayerShell.set_namespace(self, "emubox-guide")
            for edge in (GtkLayerShell.Edge.TOP, GtkLayerShell.Edge.BOTTOM, GtkLayerShell.Edge.LEFT, GtkLayerShell.Edge.RIGHT):
                GtkLayerShell.set_anchor(self, edge, True)
            provider = Gtk.CssProvider()
            provider.load_from_data(CSS)
            Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

            self.model = Model(*layout())
            self.load = Load()
            self.pads = None
            self.showing = False
            self.busy = False            # a reading of the values is under way
            self.read_once = False       # until then we do not know whether a game is running
            self.model.tabs[0].shown = False

            pane = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, margin=36)
            pane.get_style_context().add_class("pane")
            top = Gtk.Box()
            top.get_style_context().add_class("top")
            self.clock = label("", "small", xalign=0)
            self.network = label("", "small", xalign=1)
            top.pack_start(self.clock, True, True, 0)
            top.set_center_widget(label("EMUBOX", "brand"))
            top.pack_end(self.network, True, True, 0)
            pane.pack_start(top, False, False, 0)

            self.tab_box = Gtk.Box()
            self.tab_box.get_style_context().add_class("tabs")
            pane.pack_start(self.tab_box, False, False, 0)
            self.page_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            self.page_box.get_style_context().add_class("page")
            self.scroller = Gtk.ScrolledWindow()      # a long tab scrolls under the bars rather than pushing them off
            self.scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
            self.scroller.add(self.page_box)
            pane.pack_start(self.scroller, True, True, 0)

            foot = Gtk.Box(spacing=18)
            foot.get_style_context().add_class("foot")
            foot.pack_start(label("CPU", "small"), False, False, 0)
            self.cpu = Gtk.ProgressBar(valign=Gtk.Align.CENTER)
            foot.pack_start(self.cpu, False, False, 0)
            self.cpu_text = label("", "small")
            foot.pack_start(self.cpu_text, False, False, 0)
            self.free_text = label("", "small")
            foot.pack_end(self.free_text, False, False, 0)
            self.free = Gtk.ProgressBar(valign=Gtk.Align.CENTER)
            foot.pack_end(self.free, False, False, 0)
            foot.pack_end(label("Storage", "small"), False, False, 0)
            pane.pack_end(foot, False, False, 0)
            self.bar_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            self.bar_box.get_style_context().add_class("bars")
            pane.pack_end(self.bar_box, False, False, 0)
            self.add(pane)
            self.connect("key-press-event", self._on_key)
            GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGUSR1, self._toggle)
            GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGTERM, self._quit)
            if show_now:
                self._show()

        # --- showing and hiding ---------------------------------------------------------

        def _toggle(self) -> bool:
            self._hide() if self.showing else self._show()
            return True

        def _quit(self) -> bool:
            self._hide()
            Gtk.main_quit()
            return False

        def _show(self) -> None:
            self.showing = True
            # Drawn at once with what was last read (reading runs a dozen commands); fresh values follow.
            self.model.open_on("Game" if self.model.tabs[0].when and self.model.tabs[0].shown and self.read_once else "Settings")
            self._draw()
            self._read_soon()
            self._footer()
            GtkLayerShell.set_keyboard_mode(self, GtkLayerShell.KeyboardMode.EXCLUSIVE)
            self.show_all()
            self._take_pads(20)
            GLib.timeout_add(int(REFRESH_S * 1000), self._tick)

        def _take_pads(self, tries: int) -> bool:
            """Take the controllers. Whoever had them (an app's pad mapper) lets go a moment after
            asking for the menu, so try for a couple of seconds."""
            if not self.showing:
                return False
            if self.pads:
                self.pads.release()
            self.pads = Pads(self._on_pad)
            if not self.pads.devices and tries > 0:
                GLib.timeout_add(100, self._take_pads, tries - 1)
            return False

        def _hide(self) -> None:
            self.showing = False
            if self.pads:
                self.pads.release()
                self.pads = None
            self.hide()

        # --- drawing ------------------------------------------------------------------------

        def _control_widget(self, control: Control, focused: bool) -> Gtk.Widget:
            if control.kind == "text":
                return label(control.value, "value", xalign=0, ellipsize=Pango.EllipsizeMode.END)
            box = Gtk.Box(spacing=10)
            style = box.get_style_context()
            style.add_class("control")
            if control.kind == "button":
                words = "Press again to confirm" if self.model.armed is control else control.label
                box.pack_start(label(words, "words"), False, False, 0)
                if self.model.armed is control:
                    style.add_class("armed")
            elif control.kind == "switch":
                on = truthy(control.value)
                box.pack_start(label("ON" if on else "OFF", "words"), False, False, 0)
                if on:
                    style.add_class("on")
            elif control.kind == "stepper":
                try:
                    amount = max(0, min(100, int(float(control.value or 0))))
                except ValueError:
                    amount = 0
                bar = Gtk.ProgressBar(valign=Gtk.Align.CENTER)
                bar.set_fraction(amount / 100)
                box.pack_start(label("<", "words"), False, False, 0)
                box.pack_start(bar, False, False, 0)
                box.pack_start(label(f"{amount}%", "words"), False, False, 0)
                box.pack_start(label(">", "words"), False, False, 0)
            else:   # chooser
                box.pack_start(label("<", "words"), False, False, 0)
                box.pack_start(label(control.value or "-", "words"), False, False, 0)
                box.pack_start(label(">", "words"), False, False, 0)
            if focused:
                style.add_class("focus")
            return box

        def _row_widget(self, row: Row, style: str, at: bool, current: Control | None) -> Gtk.Widget:
            box = Gtk.Box(spacing=14)
            box.get_style_context().add_class(style)
            if row.heading:
                box.get_style_context().add_class("heading")
                box.pack_start(label(row.label.upper(), "category", xalign=0), False, False, 0)
                return box
            if at:
                box.get_style_context().add_class("at")
            name = label(row.label, "name", xalign=0)
            name.set_size_request(300, -1)
            box.pack_start(name, False, False, 0)
            for control in row.controls:
                widget = self._control_widget(control, control is current)
                box.pack_start(widget, control.kind == "text" and style == "bar", control.kind == "text" and style == "bar", 0)
            return box

        def _draw(self) -> None:
            model = self.model
            current, rows = model.current(), model.rows()
            at = rows[model.row] if rows else None
            for box in (self.tab_box, self.page_box, self.bar_box):
                for child in box.get_children():
                    box.remove(child)
            for index, tab in enumerate(model.shown_tabs()):
                tab_label = label(tab.title.upper(), "tab")
                if index == model.tab:
                    tab_label.get_style_context().add_class("open")
                self.tab_box.pack_start(tab_label, False, False, 0)
            self.tab_box.pack_end(label("LB / RB  tabs      A  select      B  close", "hint"), False, False, 0)
            focused = None
            for row in model.page().rows:
                if row.shown:
                    widget = self._row_widget(row, "row", row is at, current)
                    self.page_box.pack_start(widget, False, False, 0)
                    focused = widget if row is at else focused
            for row in model.bars:
                if row.shown:
                    self.bar_box.pack_start(self._row_widget(row, "bar", row is at, current), False, False, 0)
            for box in (self.tab_box, self.page_box, self.bar_box):
                box.show_all()
            if focused:
                GLib.idle_add(self._keep_in_view, focused)

        def _keep_in_view(self, widget) -> bool:
            """Scroll the tab so the highlighted row can be seen."""
            where = widget.translate_coordinates(self.page_box, 0, 0)
            if where:
                top, height = where[1], widget.get_allocated_height()
                moving = self.scroller.get_vadjustment()
                rows = [r for r in self.model.page().rows if r.focusable]
                if rows and self.model.rows()[self.model.row] is rows[0]:
                    moving.set_value(0)                     # the first setting: show its heading too
                elif top < moving.get_value():
                    moving.set_value(top)
                elif top + height > moving.get_value() + moving.get_page_size():
                    moving.set_value(top + height - moving.get_page_size())
            return False

        def _footer(self) -> None:
            self.clock.set_text(time.strftime("%H:%M"))
            percent = self.load.percent()
            self.cpu.set_fraction(percent / 100)
            self.cpu_text.set_text(f"{percent}%")
            total, free = space.usage()
            self.free.set_fraction(1 - free / total if total else 0)
            self.free_text.set_text(f"{space.size(free)} free" if total else "")

        # --- keeping the values fresh -----------------------------------------------------

        def _tick(self) -> bool:
            if not self.showing:
                return False
            self._footer()
            self._read_soon()
            return True

        def _read_soon(self) -> bool:
            if self.busy or not self.showing:
                return False
            self.busy = True

            def work() -> None:
                refresh(self.model)
                address = read("ip -4 -o addr show scope global 2>/dev/null | awk '{print $2 \": \" $4}' | cut -d/ -f1 | head -1")
                GLib.idle_add(done, address)

            def done(address: str) -> bool:
                self.busy = False
                if not self.read_once:   # first reading: now we know whether to start on the Game tab
                    self.read_once = True
                    if self.model.tabs[0].shown:
                        self.model.open_on("Game")
                self.network.set_text(address or "No network")
                if self.showing:
                    self._draw()
                return False

            threading.Thread(target=work, daemon=True).start()
            return False

        # --- input ---------------------------------------------------------------------------

        def _act(self, key: str) -> None:
            if not self.showing:
                return
            result = self.model.press(key)
            for command in self.model.ran:
                if command:
                    subprocess.Popen(["bash", "-c", command], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                     start_new_session=True)
            if result == "close":
                self._hide()
                return
            self._draw()
            if result == "ran":
                GLib.timeout_add(350, self._read_soon)   # show the new value as soon as it can be read

        def _on_pad(self, name: str) -> None:
            self._act({"start": "a"}.get(name, name))

        def _on_key(self, _window, event) -> bool:
            key = {"Up": "up", "Down": "down", "Left": "left", "Right": "right", "Return": "a", "KP_Enter": "a",
                   "space": "a", "Escape": "b", "BackSpace": "b", "Page_Up": "lb", "Page_Down": "rb",
                   "Tab": "rb"}.get(Gdk.keyval_name(event.keyval) or "")
            if key:
                self._act(key)
            return True

    PID.parent.mkdir(parents=True, exist_ok=True)
    PID.write_text(str(os.getpid()))
    guide = Guide()
    try:
        Gtk.main()
    finally:
        if guide.pads:
            guide.pads.release()
        try:
            if PID.read_text().strip() == str(os.getpid()):
                PID.unlink()
        except OSError:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(screen("--show" in sys.argv))
