#!/usr/bin/env python3
"""Batocera's free-games catalogue as a console screen, driven with the controller.

    store.py

Lists what `batocera-store` offers (homebrew and freely distributable games),
grouped by system. A installs or removes the highlighted game, LB/RB jump to
the previous/next system, B leaves. Batocera's own tool does the downloading.
"""
import os
import subprocess
import sys
import xml.etree.ElementTree as ET

import gi

os.environ.setdefault("XDG_RUNTIME_DIR", "/run")
os.environ.setdefault("WAYLAND_DISPLAY", "wayland-0")

gi.require_version("Gdk", "3.0")
gi.require_version("Gtk", "3.0")
gi.require_version("GtkLayerShell", "0.1")
from gi.repository import Gdk, GLib, Gtk, GtkLayerShell, Pango  # noqa: E402

from padinput import Pads  # noqa: E402

HERE = os.path.dirname(os.path.realpath(__file__))
STORE = "batocera-store"
VISIBLE_ROWS = 11

CSS = b"""
window { background-color: #021202; }
* { font-family: "Rajdhani", sans-serif; color: #d6f9b8; }
.title { font-family: "Michroma", sans-serif; font-size: 30px; color: #c8f03c; }
.count { font-size: 18px; color: #8fcf6a; }
.row { font-size: 22px; padding: 6px 14px; border: 1px solid transparent; }
.row.focus { background-color: #c8f03c; border-color: #f0ffd7; }
.row.focus label { color: #0a2a00; }
.system { font-size: 15px; color: #8fcf6a; }
.have { font-size: 15px; color: #c8f03c; }
.details { font-size: 20px; }
.panel { background-color: #062606; border: 1px solid #1a5a16; padding: 18px; }
.prompts { background-color: rgba(11, 71, 11, 0.9); padding: 6px 18px; }
.glyph { background-color: #124a10; border: 2px solid #96f550; border-radius: 14px;
         font-family: "Michroma", sans-serif; font-size: 13px; padding: 2px 9px; color: #f0ffd7; }
.prompt { font-size: 18px; margin-right: 16px; }
"""
PROMPTS = (("A", "Install / remove"), ("LB RB", "Previous / next system"), ("B", "Back"))


def label(text: str, style: str, **properties) -> Gtk.Label:
    widget = Gtk.Label(label=text, **properties)
    widget.get_style_context().add_class(style)
    return widget


def megabytes(kilobytes: str) -> str:
    try:
        return f"{int(kilobytes) / 1024:.0f} MB" if int(kilobytes) >= 1024 else f"{int(kilobytes)} KB"
    except ValueError:
        return ""


def system_of(group: str) -> str:
    return group.removeprefix("sys-") or "other"


def catalogue() -> list[dict]:
    """What the store offers, sorted by system then name. Empty when it cannot be reached."""
    listing = subprocess.run([STORE, "list"], capture_output=True, text=True, check=False).stdout
    if "<package>" not in listing:   # first use: the list has to be fetched once
        subprocess.run([STORE, "refresh"], capture_output=True, check=False)
        listing = subprocess.run([STORE, "list"], capture_output=True, text=True, check=False).stdout
    try:
        root = ET.fromstring(listing)
    except ET.ParseError:
        return []
    games = []
    for package in root.findall("package"):
        field = {child.tag: (child.text or "").strip() for child in package}
        if not field.get("group", "").startswith("sys-"):
            continue   # themes, bezels and the like: Batocera's own menus handle those
        about = field.get("description", "")
        system = system_of(field.get("group", ""))
        title, dash, rest = about.partition(" - ")
        if not dash:   # no "Title - what it is": make a title from the package's name
            title, rest = field.get("name", "").removeprefix(f"{system}-").replace("-", " ").title(), about
        games.append({
            "id": field.get("name", ""),
            "title": title,
            "about": rest,
            "system": system,
            "size": megabytes(field.get("installed_size", "")),
            "installed": field.get("status", "none") not in ("none", ""),
        })
    return sorted(games, key=lambda g: (g["system"], g["title"].lower()))


class Store(Gtk.Window):
    def __init__(self):
        super().__init__(title="RetroBox Store")
        GtkLayerShell.init_for_window(self)
        GtkLayerShell.set_layer(self, GtkLayerShell.Layer.OVERLAY)
        GtkLayerShell.set_keyboard_interactivity(self, False)
        for edge in (GtkLayerShell.Edge.TOP, GtkLayerShell.Edge.BOTTOM,
                     GtkLayerShell.Edge.LEFT, GtkLayerShell.Edge.RIGHT):
            GtkLayerShell.set_anchor(self, edge, True)
        provider = Gtk.CssProvider()
        provider.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        self.games: list[dict] = []
        self.cursor = 0
        self.changed = False   # something was installed or removed: the game lists need a refresh

        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        head = Gtk.Box(margin=24, margin_bottom=10)
        head.pack_start(label("FREE GAMES", "title", xalign=0), True, True, 0)
        self.count = label("", "count", xalign=1)
        head.pack_end(self.count, False, False, 0)
        page.pack_start(head, False, False, 0)

        body = Gtk.Box(spacing=24, margin_start=24, margin_end=24)
        self.list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self.list.set_size_request(560, -1)
        body.pack_start(self.list, False, False, 0)
        panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        panel.get_style_context().add_class("panel")
        self.name = label("", "title", xalign=0, wrap=True)
        self.facts = label("", "count", xalign=0)
        self.about = label("", "details", xalign=0, yalign=0, wrap=True)
        for widget in (self.name, self.facts, self.about):
            panel.pack_start(widget, False, False, 0)
        body.pack_start(panel, True, True, 0)
        page.pack_start(body, True, True, 0)

        prompts = Gtk.Box(spacing=8, halign=Gtk.Align.CENTER)
        prompts.get_style_context().add_class("prompts")
        for glyph, text in PROMPTS:
            prompts.pack_start(label(glyph, "glyph"), False, False, 0)
            prompts.pack_start(label(text, "prompt"), False, False, 0)
        page.pack_end(prompts, False, False, 0)
        self.add(page)
        self.show_all()

        self.name.set_text("Loading the catalogue...")
        self.pads = Pads(self._on_pad)
        GLib.idle_add(self._load)

    def _load(self) -> bool:
        self.games = catalogue()
        self.cursor = min(self.cursor, max(0, len(self.games) - 1))
        self._draw()
        return False

    def _draw(self) -> None:
        for child in self.list.get_children():
            self.list.remove(child)
        if not self.games:
            self.name.set_text("The catalogue could not be loaded")
            self.facts.set_text("")
            self.about.set_text("Check the internet connection, then open the store again.")
            self.count.set_text("")
            return
        first = max(0, min(self.cursor - VISIBLE_ROWS // 2, len(self.games) - VISIBLE_ROWS))
        for index in range(first, min(first + VISIBLE_ROWS, len(self.games))):
            game = self.games[index]
            row = Gtk.Box(spacing=12)
            row.get_style_context().add_class("row")
            if index == self.cursor:
                row.get_style_context().add_class("focus")
            row.pack_start(label(game["title"], "name", xalign=0, ellipsize=Pango.EllipsizeMode.END), True, True, 0)
            if game["installed"]:
                row.pack_end(label("INSTALLED", "have"), False, False, 0)
            row.pack_end(label(game["system"].upper(), "system"), False, False, 0)
            self.list.pack_start(row, False, False, 0)
        game = self.games[self.cursor]
        self.name.set_text(game["title"])
        self.facts.set_text("   ".join(filter(None, (game["system"].upper(), game["size"],
                                                      "Installed" if game["installed"] else ""))))
        self.about.set_text(game["about"])
        self.count.set_text(f"{self.cursor + 1} of {len(self.games)}")
        self.list.show_all()

    def _jump_system(self, step: int) -> None:
        """Move to the first game of the previous or next system."""
        here = self.games[self.cursor]["system"]
        index = self.cursor
        while 0 <= index + step < len(self.games):
            index += step
            if self.games[index]["system"] != here:
                break
        if step < 0:   # land on the first game of that system, not its last
            target = self.games[index]["system"]
            while index > 0 and self.games[index - 1]["system"] == target:
                index -= 1
        self.cursor = index

    def _toggle(self) -> None:
        game = self.games[self.cursor]
        action, word = ("remove", "Removing") if game["installed"] else ("install", "Downloading")
        self.pads.release()   # the notice takes the controller while it is up
        self.hide()
        status = subprocess.run([sys.executable, os.path.join(HERE, "notice.py"), f"{word} {game['title']}",
                                 "--", STORE, action, game["id"]], check=False).returncode
        self.changed = self.changed or status == 0
        self.show()
        self.pads = Pads(self._on_pad)
        self._load()

    def _on_pad(self, button: str) -> None:
        if button == "b":
            Gtk.main_quit()
        if not self.games:
            return
        if button in ("up", "down"):
            self.cursor = (self.cursor + (1 if button == "down" else -1)) % len(self.games)
        elif button in ("lb", "rb"):
            self._jump_system(1 if button == "rb" else -1)
        elif button == "a":
            self._toggle()
            return
        self._draw()


def main() -> int:
    store = Store()
    try:
        Gtk.main()
    finally:
        store.pads.release()
    if store.changed:   # have the menu notice the new games
        subprocess.run(["curl", "-s", "http://127.0.0.1:1234/reloadgames"], capture_output=True, check=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
