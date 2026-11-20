#!/usr/bin/env python3
"""EmuBox's Guide menu: the quick menu the Guide button opens, over the menus or a running game.

    guide.py            start it, hidden (the emubox service does, at boot)
    guide.py --show     start it and show it at once
    bin/emubox-guide    show it, or hide it when it is showing (what the Guide button runs)

Batocera's own quick menu cannot hold controls in its bottom strip, so EmuBox draws
this one itself. Along the top: the time and the network address. Tabs: Running (while a
game or an app is open), Settings (the few settings worth having one press away, and a way
into the full ones), Apps and Capture (a screenshot, or a recording). Along the bottom: a bar for each app that is doing
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
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import space
import sysload

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
APP = ROOT / "bin" / "emubox-app"
PID = Path("/var/run/emubox/guide.pid")
WARM_UP_S = 6   # first reading of the values, while hidden: soon, but not in the busiest seconds of start-up
REFRESH_S = 1.5
TWICE_S = 0.6    # the Guide button heard again this soon after the menu changed is the same press
LET_GO_S = 2.0   # after a press changed the menu, a toggle within this long is that press being let go

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
    busy: str = ""                 # said on the menu itself while `wait` runs, in place of closing at once
    wait: str = ""                 # a command that ends when what the button started is on screen
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


def button(label: str, do: str, close: bool = False, confirm: bool = False, busy: str = "", wait: str = "") -> Control:
    return Control("button", label=label, do=do, close=close, confirm=confirm, busy=busy, wait=wait)


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


# Values asked of EmuBox's own code are read here, in this program. Starting a program for each
# (python, bash, jq: read off a USB drive every time) made every opening of the menu a burst of
# forty of them, which is felt as lag in everything else: the menus, the sounds, the buttons.

_RUNNING: list = [0.0, ""]   # when running_game last asked, and the answer


def running_game() -> str:
    """The name of what Batocera's menu started (a game, or an app from its tile); '' for nothing.
    Several rows ask during one reading of the values, so the answer is kept for a moment."""
    if time.monotonic() - _RUNNING[0] < 1.5:
        return _RUNNING[1]
    _RUNNING[:] = [time.monotonic(), _ask_running_game()]
    return _RUNNING[1]


def _ask_running_game() -> str:
    try:
        with urllib.request.urlopen("http://127.0.0.1:1234/runningGame", timeout=1) as reply:
            game = json.loads(reply.read().decode(errors="replace") or "{}")
    except (OSError, ValueError):
        return ""
    return str(game.get("name") or "") if isinstance(game, dict) else ""


def open_apps(found: list[tuple[str, dict]], run: Path = Path("/var/run/emubox"), proc: Path = Path("/proc")) -> list[str]:
    """The names of the apps that are open now, told from what the system already keeps:
    the processes, the note the opener leaves, and flatpak's list of what it is running."""
    web, flatpaks = set(), set()
    for folder in proc.iterdir():
        if folder.name.isdigit():
            try:
                words = (folder / "cmdline").read_bytes().split(b"\0")
            except OSError:
                continue
            if any(word.endswith(b"webview.py") for word in words) and b"--id" in words:
                web.add(words[words.index(b"--id") + 1].decode(errors="replace"))
    for info in run.parent.glob(".flatpak/*/info"):
        try:
            flatpaks |= {line[5:].strip() for line in info.read_text().splitlines() if line.startswith("name=")}
        except OSError:
            continue
    names = []
    for app_id, app in found:
        if app.get("web"):
            is_open = app_id in web
        elif not (run / f"{app_id}.started").exists():
            is_open = False
        elif app.get("flatpak"):
            is_open = app["flatpak"] in flatpaks
        else:
            try:
                is_open = (proc / (run / f"{app_id}.pid").read_text().strip()).is_dir()
            except OSError:
                is_open = False
        if is_open:
            names.append(app["name"])
    return names


def own(module: str, call: Callable[[object], object]) -> Callable[[], str]:
    """A value from one of EmuBox's own modules beside this file, asked without starting python again."""
    def ask() -> str:
        loaded = sys.modules.get(module) or __import__(module)
        answer = call(loaded)
        return "" if answer is None else str(answer)
    return ask


def layout(found: list[tuple[str, dict]] | None = None, lights: bool | None = None) -> tuple[list[Tab], list[Row]]:
    """The tabs and the bars along the bottom."""
    found = apps() if found is None else found
    lights = (HERE / "startmenu_rgbhub.py").is_file() if lights is None else lights
    a, lib = str(APP), str(HERE)
    sounds, hub = f"python3 {lib}/menusounds.py", f"python3 {lib}/startmenu_rgbhub.py"
    in_menus = lambda: "" if running_game() else "yes"   # noqa: E731
    memo: dict[str, tuple[float, list[str]]] = {}

    def open_now_names() -> list[str]:   # asked by several rows in one reading: looked up once
        if "apps" not in memo or time.monotonic() - memo["apps"][0] > 0.5:
            memo["apps"] = (time.monotonic(), open_apps(found))
        return memo["apps"][1]

    def hub_switch(name: str, which: str) -> Control:   # a setting of the lights program, per device
        return switch(own("startmenu_rgbhub", lambda m: m.run(["is", name, which])),
                      f"{hub} set {name} {which} on", f"{hub} set {name} {which} off")

    def hub_stepper(name: str, which: str) -> Control:
        return stepper(own("startmenu_rgbhub", lambda m: m.run(["get", name, which])),
                       f"{hub} step {name} {which} -10", f"{hub} step {name} {which} +10")

    settings = [
        heading("Sound"),
        Row("Volume", [stepper("batocera-audio getSystemVolume", "batocera-audio setSystemVolume -5",
                               "batocera-audio setSystemVolume +5")]),
        Row("Mute", [switch("batocera-audio getSystemMute", "batocera-audio setSystemVolume mute",
                            "batocera-audio setSystemVolume unmute")]),
        Row("Sound output", [chooser(f"python3 {lib}/audioout.py show",
                                     f"python3 {lib}/audioout.py previous", f"python3 {lib}/audioout.py next")]),
        Row("Menu music", [switch(own("settings", lambda m: "true" if m.on("music.menu") else ""),
                                  f"python3 {lib}/settings.py set music.menu on",
                                  f"python3 {lib}/settings.py set music.menu off")]),
        Row("Menu sounds", [chooser(own("menusounds", lambda m: m.chosen_set(m.settings.get("ui.sound_set"), m.sets(m.es_text()))),
                                    f"{sounds} previous", f"{sounds} next")]),
        Row("Menu sound volume", [stepper(own("settings", lambda m: m.get("ui.sound_volume")),
                                          f"{sounds} volume -10", f"{sounds} volume +10")]),
    ]
    pair = (f"python3 {lib}/notice.py 'Pairing: hold the pair button on the controller until its light flashes "
            f"(B stops looking)' -- python3 {lib}/btstatus.py pair")
    settings += [
        heading("Bluetooth"),
        Row("Adapter", [text(own("btstatus", lambda m: m.adapter()))]),
        Row("Controllers", [text(own("btstatus", lambda m: m.pads()))]),
        Row("Pair a controller", [button("Pair", pair, close=True)]),
    ]
    if lights:
        settings += [
            heading("RGB Hub"),
            Row("Follow the game", [hub_switch("auto-devices", "all")]),
            Row("PC lights", [hub_switch("device-enabled", "pc")]),
            Row("Keyboard lights", [hub_switch("device-enabled", "keyboard")]),
            Row("PC brightness", [hub_stepper("device-brightness", "pc")]),
            Row("Keyboard brightness", [hub_stepper("device-brightness", "keyboard")]),
            Row("Default look", [button("Save look as Default", f"{hub} default save", confirm=True)]),
        ]
    settings += [
        heading("System"),
        Row("Power", [chooser(lambda: Path("/sys/devices/system/cpu/cpufreq/policy0/scaling_governor").read_text().strip(),
                              f"{a} power previous", f"{a} power next")]),
        Row("Plane mode", [switch("batocera-planemode status", "batocera-planemode enable", "batocera-planemode disable")]),
        Row("Stuck emulator?", [button("Stop it", "curl -s http://127.0.0.1:1234/emukill", confirm=True)]),
        Row("Everything else", [button("Open full settings", "hotkeygen --send menu", close=True)], when=in_menus),
    ]

    listed = [(app_id, app) for app_id, app in found if app.get("menu", True)]
    def opening(app_id: str, app: dict) -> str:
        # Through Batocera's menu when it is free, so it knows an app is running (no screensaver
        # behind it); the menu says "Opening ..." itself, at once.
        return f"EMUBOX_NOTICE=no {a} detach launch {app_id}"

    def open_button(words: str, app_id: str, app: dict) -> Control:
        return button(words, opening(app_id, app), close=True, busy=f"Opening {app['name']}", wait=f"{a} await {app_id}")

    def opens(which: list[tuple[str, dict]]) -> list[Row]:
        return [Row(app["name"], [open_button("Open", app_id, app)]) for app_id, app in which]

    # Programs Batocera already has (Terminal, Files, Claude) are tools; the rest are apps.
    tools = [(app_id, app) for app_id, app in listed if app.get("command")]
    app_rows = [heading("Apps")] + opens([entry for entry in listed if entry not in tools])
    if tools:
        app_rows += [heading("Tools")] + opens(tools)
    app_rows += [heading("Return"), Row("Hide apps", [button("Go back", f"{a} back", close=True)])]

    # The Running tab: whatever is running now, an emulator Batocera started or an app of ours,
    # each with what you would want to reach for (go back to it, its settings, close it).
    app_names = {app["name"] for _id, app in found}
    def in_emulator() -> str:   # what Batocera started, unless that is one of our apps opened from its tile
        name = running_game()
        return "" if name in app_names else name

    game = [
        Row("Now running", [text(in_emulator)], when=in_emulator),
        Row("", [button("Resume", "true", close=True),
                 button("Settings", "hotkeygen --send menu", close=True),
                 button("Quit", "hotkeygen --send exit", close=True, confirm=True),
                 button("Force close", "curl -s http://127.0.0.1:1234/emukill", close=True, confirm=True)],
            when=in_emulator),
    ]
    for app_id, app in found:
        open_now = lambda name=app["name"]: "yes" if name in open_now_names() else ""   # noqa: E731
        game.append(Row(app["name"], [open_button("Resume", app_id, app),
                                      button("Hide", f"{a} back {app_id}", close=True),
                                      button("Force close", f"{a} close {app_id}", confirm=True)],
                        when=open_now))
    something_running = lambda: running_game() or " ".join(open_now_names())   # noqa: E731
    # Screenshots go to /userdata/screenshots and recordings to /userdata/recordings (Batocera's own
    # places), both shown under Captures on the home screen. The menu closes first, so it is not in
    # the picture; a note says where the picture went.
    reload = "curl -s -m 5 http://127.0.0.1:1234/reloadgames >/dev/null"
    shot = (f"sleep 0.7; batocera-screenshot >/dev/null 2>&1 && {{ python3 {lib}/toast.py 'Screenshot saved to Captures' 3 & {reload}; }}")
    record = [Row("Screenshot", [button("Take one", shot, close=True)]),
              Row("Recording", [switch("batocera-record is_running | grep true", "batocera-record start",
                                       f"batocera-record stop; {reload}")])]
    tabs = [Tab("Running", game, when=something_running), Tab("Settings", settings), Tab("Apps", app_rows), Tab("Capture", record)]

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
    music_line = own("music", lambda m: m.line())
    bars.append(Row("Menu music", [text(music_line), button("<", f"{music} previous"), button("||", f"{music} toggle"),
                                   button(">", f"{music} next")], when=music_line))
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

def note(words: str) -> None:
    """A line for the log (logs/emubox.log), with the time: how long things took, for finding lag."""
    print(f"{time.strftime('%F %T')} guide: {words}", file=sys.stderr, flush=True)


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


def refresh(model: Model, reader=read, everything: bool = False) -> None:
    """Read the values the menu is showing: which tabs and rows exist, and what is on the open
    tab (every tab with `everything`, for the first reading: changing tab then shows last time's
    values at once and reads its own). What still needs a program is run a few at a time, side
    by side (call this off the screen's thread)."""
    seen: dict[object, str] = {}

    def fetch(getters) -> None:
        wanted = [get for get in dict.fromkeys(getters) if get and get not in seen]
        if not wanted:
            return
        with ThreadPoolExecutor(max_workers=4) as pool:
            for get, result in zip(wanted, pool.map(reader, wanted)):
                seen[get] = result

    rows = [row for tab in model.tabs for row in tab.rows] + model.bars
    fetch([tab.when for tab in model.tabs] + [row.when for row in rows])
    for tab in model.tabs:
        tab.shown = truthy(seen[tab.when]) if tab.when else True
    for row in rows:
        row.shown = truthy(seen[row.when]) if row.when else True
    looked_at = rows if everything else model.page().rows + model.bars
    fetch(control.get for row in looked_at if row.shown for control in row.controls)   # only what can be seen
    for row in looked_at:
        if row.shown:
            for control in row.controls:
                if control.get:
                    control.value = seen[control.get]


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
.tab.open { color: #0a2a00; font-weight: bold; border-color: #f0ffd7; border-top: 3px solid #f0ffd7;
            background-image: linear-gradient(to bottom, #f0ff8c, #9adc20);
            box-shadow: 0 0 14px rgba(200, 255, 80, 0.55); }
.hint { font-size: 16px; color: #8fcf6a; }
.page { padding: 14px 28px; border-top: 1px solid rgba(150, 245, 80, 0.4); }
.row { padding: 3px 10px; border: 1px solid transparent; }
.row.at { background-color: rgba(150, 245, 80, 0.08); border-color: rgba(150, 245, 80, 0.35); }
.name { font-size: 20px; }
.opening { font-family: "Michroma", sans-serif; font-size: 28px; color: #c8f03c; }
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
.foot progressbar trough { min-width: 120px; }
progressbar progress { background-image: linear-gradient(to bottom, #f0ff8c, #9adc20); border: none; min-height: 10px; }
"""


def screen(show_now: bool) -> int:
    # One Guide at a time. The boot service and the Guide button (bin/emubox-guide) can both start
    # one while the other is still loading; the second hands its request to the first and goes.
    import fcntl
    PID.parent.mkdir(parents=True, exist_ok=True)
    lock = open(PID.with_suffix(".lock"), "w")   # noqa: SIM115 (held for as long as we run)
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        if show_now:
            for _ in range(80):              # until the first one has said who it is
                try:
                    os.kill(int(PID.read_text()), signal.SIGUSR2)
                    break
                except (OSError, ValueError):
                    time.sleep(0.1)
        return 0
    # Known from now on, so the Guide button reaches us while we are still loading; a press
    # that arrives before the screen is ready is kept and answered once it is.
    pending: list[str] = []
    signal.signal(signal.SIGUSR1, lambda *_: pending.append("toggle"))
    signal.signal(signal.SIGUSR2, lambda *_: pending.append("show"))
    PID.write_text(str(os.getpid()))
    os.environ.setdefault("XDG_RUNTIME_DIR", "/var/run")
    os.environ.setdefault("WAYLAND_DISPLAY", "wayland-0")
    if os.environ.get("HOME", "/") == "/":
        os.environ["HOME"] = "/userdata/system"   # where the look's fonts are; a boot service has no home
    import gi
    gi.require_version("Gdk", "3.0")
    gi.require_version("Gtk", "3.0")
    gi.require_version("GtkLayerShell", "0.1")
    from gi.repository import Gdk, GLib, Gtk, GtkLayerShell, Pango

    import evdev
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
            self.deaf_until = 0.0
            self.changed_at = 0.0
            self.waiting = None          # set while "Opening ..." is up
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
            # Processor, memory and graphics card load on the left (each a word, a bar and a figure),
            # how full the drive is on the right. The GPU is left out where the PC cannot tell it.
            def meter(word: str) -> tuple:
                parts = (label(word, "small"), Gtk.ProgressBar(valign=Gtk.Align.CENTER), label("", "small", width_chars=4, xalign=0))
                for part in parts:
                    foot.pack_start(part, False, False, 0)
                return parts

            _, self.cpu, self.cpu_text = meter("CPU")
            _, self.ram, self.ram_text = meter("RAM")
            self.gpu_parts = meter("GPU")
            for part in self.gpu_parts:      # shown or not by _footer alone, not by show_all()
                part.set_no_show_all(True)
            _, self.gpu, self.gpu_text = self.gpu_parts
            self.gpu_load = sysload.Gpu()
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
            GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGUSR2, self._asked_to_show)
            GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGTERM, self._quit)
            self.watched: dict[str, object] = {}
            self.not_pads: set[str] = set()   # input devices already looked at that are no controller
            self.other_pads: set[str] = set() # controllers without a Guide button: taken too when open
            self._watch_pads()
            GLib.timeout_add_seconds(3, self._watch_pads)
            # Read everything once while hidden, so the first opening is ready; not straight away,
            # while the system is still starting and has better things to do.
            GLib.timeout_add_seconds(WARM_UP_S, self._read_soon, True)
            if show_now:
                self._show()

        # --- the Guide button, heard directly -------------------------------------------

        def _watch_pads(self) -> bool:
            """Listen to every controller's Guide button ourselves, so the menu opens the moment it
            is pressed. (Batocera's hotkeys only tell us when it is let go; that later word is then
            ignored, see _toggle.) Controllers come and go, so this looks again every few seconds."""
            present = set(evdev.list_devices())
            self.not_pads &= present          # a device that went away may come back as something else
            self.other_pads &= present
            for path in sorted(present - self.not_pads - self.other_pads - set(self.watched)):
                try:
                    device = evdev.InputDevice(path)
                    keys = device.capabilities().get(evdev.ecodes.EV_KEY, [])
                    if evdev.ecodes.BTN_MODE in keys and evdev.ecodes.BTN_SOUTH in keys:
                        self.watched[path] = device
                        GLib.io_add_watch(device.fd, GLib.IO_IN | GLib.IO_HUP | GLib.IO_ERR, self._on_watched, device)
                    else:
                        device.close()
                        (self.other_pads if evdev.ecodes.BTN_SOUTH in keys else self.not_pads).add(path)
                except OSError:
                    continue
            return True

        def _on_watched(self, _fd, _condition, device) -> bool:
            try:
                events = list(device.read())
            except BlockingIOError:
                return True
            except OSError:                               # unplugged, or gone to sleep
                self.watched.pop(device.path, None)
                try:
                    device.close()
                except OSError:
                    pass
                return False
            for event in events:
                if event.type == evdev.ecodes.EV_KEY and event.code == evdev.ecodes.BTN_MODE and event.value == 1 \
                        and not self.showing and time.monotonic() - self.changed_at > TWICE_S:
                    self._asked_to_show()
            return True

        # --- showing and hiding ---------------------------------------------------------

        def _toggle(self) -> bool:
            """The Guide button, from Batocera's hotkeys: it tells us when the button is let go.
            When a press has just opened or closed the menu (an app's pad mapper asking for it, or
            Guide pressed in the menu itself), this is that same press being let go: not a new one."""
            now = time.monotonic()
            if now < self.deaf_until:
                self.deaf_until = 0.0
                return True
            if now - self.changed_at < TWICE_S:   # the same press, heard twice (a controller that shows up
                return True                        # as two devices): opening and closing at once otherwise
            self._hide() if self.showing else self._show()
            return True

        def _asked_to_show(self) -> bool:
            """An app's pad mapper, at the moment Guide is pressed."""
            if not self.showing:
                self._show()
            self.deaf_until = time.monotonic() + LET_GO_S
            return True

        def _quit(self) -> bool:
            self._hide()
            Gtk.main_quit()
            return False

        def _show(self) -> None:
            asked = time.monotonic()
            steps: list[str] = []

            def step(name: str, since: list[float] = [asked]) -> None:
                now = time.monotonic()
                steps.append(f"{name} {(now - since[0]) * 1000:.0f}")
                since[0] = now

            def opened() -> bool:
                took = (time.monotonic() - asked) * 1000
                # The steps are worth a line only when opening was slow: they say where the time went.
                note(f"opened in {took:.0f} ms" + (f" ({', '.join(steps)} ms)" if took > 400 else ""))
                return False

            GLib.idle_add(opened)
            self.showing = True
            self.changed_at = time.monotonic()
            # Drawn at once with what was last read (reading runs a dozen commands); fresh values follow.
            self.model.open_on("Running" if self.model.tabs[0].when and self.model.tabs[0].shown and self.read_once else "Settings")
            self._draw()
            step("draw")
            self._read_soon()
            self._footer()
            step("footer")
            GtkLayerShell.set_keyboard_mode(self, GtkLayerShell.KeyboardMode.EXCLUSIVE)
            self.show_all()
            step("show")
            self._take_pads(20)
            step("pads")
            if getattr(self, "ticking", None):     # shown again before the last timer noticed the hide
                GLib.source_remove(self.ticking)
            self.ticking = GLib.timeout_add(int(REFRESH_S * 1000), self._tick)

        def _take_pads(self, tries: int) -> bool:
            """Take the controllers. Whoever had them (an app's pad mapper) lets go a moment after
            asking for the menu, so try for a couple of seconds."""
            if not self.showing:
                return False
            if self.pads:
                self.pads.release()
            self.pads = Pads(self._on_pad, [*self.watched, *sorted(self.other_pads)] or None)
            if not self.pads.devices and tries > 0:
                GLib.timeout_add(100, self._take_pads, tries - 1)
            return False

        def _hide(self) -> None:
            self.waiting = None
            self.showing = False
            self.changed_at = time.monotonic()
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
            if not self.read_once:    # opened before anything could be read (straight after start-up)
                self.page_box.pack_start(label("Loading...", "name", xalign=0), False, False, 12)
            for row in model.page().rows if self.read_once else []:
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
            used, total = sysload.memory()
            self.ram.set_fraction(used / total if total else 0)
            self.ram_text.set_text(f"{round(100 * used / total)}%" if total else "")
            gpu = self.gpu_load.percent()
            for part in self.gpu_parts:
                part.set_visible(gpu is not None)
            if gpu is not None:
                self.gpu.set_fraction(gpu / 100)
                self.gpu_text.set_text(f"{gpu}%")
            total, free = space.usage()
            self.free.set_fraction(1 - free / total if total else 0)
            self.free_text.set_text(f"{space.size(free)} free" if total else "")

        # --- keeping the values fresh -----------------------------------------------------

        def _tick(self) -> bool:
            if not self.showing:
                self.ticking = None
                return False
            self._footer()
            self._read_soon()
            return True

        def _read_soon(self, hidden_too: bool = False) -> bool:
            if self.busy or not (self.showing or hidden_too):
                return False
            self.busy = True

            def work() -> None:
                began = time.monotonic()
                refresh(self.model, everything=not self.read_once)
                took = time.monotonic() - began
                if took > 0.4:   # worth knowing about: this is what makes the values arrive late
                    note(f"values read in {took * 1000:.0f} ms")
                address = read("ip -4 -o addr show scope global 2>/dev/null | awk '{print $2 \": \" $4}' | cut -d/ -f1 | head -1")
                GLib.idle_add(done, address)

            def done(address: str) -> bool:
                self.busy = False
                if not self.read_once:   # first reading: now we know whether to start on the Game tab
                    self.read_once = True
                    if self.model.tabs[0].shown:
                        self.model.open_on("Running")
                self.network.set_text(address or "No network")
                if self.showing and self.waiting is None:
                    self._draw()
                return False

            threading.Thread(target=work, daemon=True).start()
            return False

        def _wait_for(self, control: Control) -> None:
            """Stay up saying what is being opened until it is on screen (its window is there), so
            the press is answered at once; then get out of the way. B stops waiting."""
            self.waiting = token = object()
            for box in (self.page_box, self.bar_box):
                for child in box.get_children():
                    box.remove(child)
            words = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18, valign=Gtk.Align.CENTER, halign=Gtk.Align.CENTER)
            words.pack_start(label(control.busy, "opening"), False, False, 0)
            bar = Gtk.ProgressBar()
            words.pack_start(bar, False, False, 0)
            words.pack_start(label("B  stop waiting", "hint"), False, False, 0)
            self.page_box.pack_start(words, True, True, 60)
            self.page_box.show_all()

            def moving() -> bool:
                if self.waiting is token:
                    bar.pulse()
                return self.waiting is token

            def finished() -> bool:
                if self.waiting is token:
                    self._hide()
                return False

            def work() -> None:
                try:
                    subprocess.run(["bash", "-c", control.wait], timeout=75, check=False,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                except (OSError, subprocess.TimeoutExpired):
                    pass
                GLib.idle_add(finished)

            GLib.timeout_add(90, moving)
            threading.Thread(target=work, daemon=True).start()

        # --- input ---------------------------------------------------------------------------

        def _act(self, key: str) -> None:
            if not self.showing:
                return
            if self.waiting is not None:        # "Opening ...": only B, to stop waiting
                if key in ("b", "guide"):
                    self._hide()
                return
            pressed = self.model.current()
            result = self.model.press(key)
            for command in self.model.ran:
                if command:
                    subprocess.Popen(["bash", "-c", command], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                     start_new_session=True)
            if result == "close" and key == "a" and pressed is not None and pressed.wait:
                self._wait_for(pressed)
                return
            if result == "close":
                if key == "guide":
                    self.deaf_until = time.monotonic() + LET_GO_S
                self._hide()
                return
            self._draw()
            if key in ("lb", "rb"):
                self._read_soon()                         # the tab turned to: its own values, now
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

    guide = Guide()
    if pending and not guide.showing:
        guide._show()
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
