#!/usr/bin/env python3
"""The Flathub tile in the Store: apps EmuBox knows how to set up, browsed with the controller.

    appstore.py

Opened from Store > Flathub. A adds the highlighted app (or takes it off again): it
then has a tile in the Apps section of the home screen and a row in the Guide
menu's Apps tab. B leaves. The list is apps-catalogue.json beside this file:
web sites shown in EmuBox's own web view, sites that need Chrome (protected
video, cloud gaming) and programs from Flathub. A program is downloaded the
moment it is added; a web site needs nothing.

An added app is a folder apps/<id>/ with an app.json, exactly like the ones the
installer puts there, plus the usual tile: a script, a picture and a line in
/userdata/roms/apps/gamelist.xml.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
TILES = Path(os.environ.get("EMUBOX_APP_TILES", "/userdata/roms/apps"))
FONT = Path("/userdata/system/.fonts/Michroma-Regular.ttf")
REFRESH = "curl -s -m 10 http://127.0.0.1:1234/reloadgames"


def catalogue(file: Path | None = None) -> tuple[list[dict], dict]:
    try:
        data = json.loads((file or HERE / "apps-catalogue.json").read_text())
    except (OSError, ValueError):
        return [], {}
    return data.get("apps", []), data.get("pads", {})


def is_added(app: dict, apps: Path | None = None) -> bool:
    return ((apps or ROOT / "apps") / app["id"] / "app.json").is_file()


def app_json(app: dict, pads: dict) -> dict:
    """What goes in the app's app.json (see docs/extending.md)."""
    made = {"name": app["name"], "description": app.get("about", ""), "added": True}
    if app.get("icon"):
        made["icon"] = app["icon"]
    if app.get("tip"):
        made["tip"] = app["tip"]
    if app.get("web"):
        made["web"] = app["web"]
        return made
    made.update({"flatpak": app["flatpak"], "args": app.get("args", []), "window": app.get("window", "")})
    if app.get("player"):
        made["player"] = True
    if app.get("pad"):
        made["pad"] = pads.get(app["pad"], {})
    return made


def tile_script(app: dict, root: Path = ROOT) -> str:
    run = f"exec {root}/bin/emubox-app open {app['id']} --wait"   # web apps too: the opener knows both kinds
    return f"#!/bin/bash\n# {app['name']}, added from EmuBox's app list.\n{run}\n"


def draw_tile(app: dict, file: Path, font: Path = FONT) -> bool:
    """The app's picture for the menus: an icon over its name (see tileart.py)."""
    import tileart
    return tileart.draw(app["name"], tileart.guess(app), file, font)


def _games(tiles: Path) -> tuple[ET.ElementTree, ET.Element]:
    file = tiles / "gamelist.xml"
    try:
        tree = ET.parse(file)
        return tree, tree.getroot()
    except (OSError, ET.ParseError):
        root = ET.Element("gameList")
        return ET.ElementTree(root), root


def add(app: dict, pads: dict, apps: Path | None = None, tiles: Path = TILES, root: Path = ROOT, font: Path = FONT) -> None:
    folder = (apps or ROOT / "apps") / app["id"]
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "app.json").write_text(json.dumps(app_json(app, pads), indent=2) + "\n")
    tiles.mkdir(parents=True, exist_ok=True)
    script = tiles / f"{app['name']}.sh"
    script.write_text(tile_script(app, root))
    script.chmod(0o755)
    pictured = draw_tile(app, tiles / "images" / f"{app['name']}.png", font)
    if pictured and tiles == TILES:   # then its own icon, asked of its site or Flathub, without holding the screen up
        subprocess.Popen([sys.executable, str(ROOT / "lib" / "tileicon.py"), "app", app["id"]],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    tree, games = _games(tiles)
    for old in [g for g in games.findall("game") if g.findtext("path") == f"./{script.name}"]:
        games.remove(old)
    game = ET.SubElement(games, "game")
    for tag, value in (("path", f"./{script.name}"), ("name", app["name"]), ("desc", app.get("about", "")), ("genre", "Apps"),
                       ("image", f"./images/{app['name']}.png" if pictured else "")):
        if value:
            ET.SubElement(game, tag).text = value
    tree.write(tiles / "gamelist.xml", encoding="unicode", xml_declaration=True)


def remove(app: dict, apps: Path | None = None, tiles: Path = TILES) -> None:
    folder = (apps or ROOT / "apps") / app["id"]
    (folder / "app.json").unlink(missing_ok=True)
    try:
        folder.rmdir()
    except OSError:
        pass
    (tiles / f"{app['name']}.sh").unlink(missing_ok=True)
    (tiles / "images" / f"{app['name']}.png").unlink(missing_ok=True)
    tree, games = _games(tiles)
    for old in [g for g in games.findall("game") if g.findtext("path") == f"./{app['name']}.sh"]:
        games.remove(old)
    if (tiles / "gamelist.xml").exists():
        tree.write(tiles / "gamelist.xml", encoding="unicode", xml_declaration=True)


# --- the screen ---------------------------------------------------------------------------

CSS = b"""
window { background-color: #021202; }
* { font-family: "Rajdhani", sans-serif; color: #d6f9b8; }
.title { font-family: "Michroma", sans-serif; font-size: 30px; color: #c8f03c; }
.count { font-size: 18px; color: #8fcf6a; }
.row { font-size: 22px; padding: 6px 14px; border: 1px solid transparent; }
.row.focus { background-color: #c8f03c; border-color: #f0ffd7; }
.row.focus label { color: #0a2a00; }
.kind { font-size: 15px; color: #8fcf6a; }
.have { font-size: 15px; color: #c8f03c; }
.details { font-size: 20px; }
.panel { background-color: #062606; border: 1px solid #1a5a16; padding: 18px; }
.prompts { background-color: rgba(11, 71, 11, 0.9); padding: 6px 18px; }
.glyph { background-color: #124a10; border: 2px solid #96f550; border-radius: 14px;
         font-family: "Michroma", sans-serif; font-size: 13px; padding: 2px 9px; color: #f0ffd7; }
.prompt { font-size: 18px; margin-right: 16px; }
"""


def screen() -> int:
    os.environ.setdefault("XDG_RUNTIME_DIR", "/var/run")
    os.environ.setdefault("WAYLAND_DISPLAY", "wayland-0")
    import gi
    gi.require_version("Gdk", "3.0")
    gi.require_version("Gtk", "3.0")
    gi.require_version("GtkLayerShell", "0.1")
    from gi.repository import Gdk, Gtk, GtkLayerShell, Pango

    from padinput import Pads

    def label(words: str, style: str, **properties) -> Gtk.Label:
        widget = Gtk.Label(label=words, **properties)
        widget.get_style_context().add_class(style)
        return widget

    class Store(Gtk.Window):
        def __init__(self):
            super().__init__(title="EmuBox Apps")
            GtkLayerShell.init_for_window(self)
            GtkLayerShell.set_layer(self, GtkLayerShell.Layer.OVERLAY)
            GtkLayerShell.set_keyboard_mode(self, GtkLayerShell.KeyboardMode.EXCLUSIVE)
            for edge in (GtkLayerShell.Edge.TOP, GtkLayerShell.Edge.BOTTOM, GtkLayerShell.Edge.LEFT, GtkLayerShell.Edge.RIGHT):
                GtkLayerShell.set_anchor(self, edge, True)
            provider = Gtk.CssProvider()
            provider.load_from_data(CSS)
            Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
            self.apps, self.pad_maps = catalogue()
            self.cursor, self.changed = 0, False

            page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            head = Gtk.Box(margin=24, margin_bottom=10)
            head.pack_start(label("FLATHUB", "title", xalign=0), True, True, 0)
            page.pack_start(head, False, False, 0)
            body = Gtk.Box(spacing=24, margin_start=24, margin_end=24)
            self.list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            self.list.set_size_request(520, -1)
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
            for glyph, words in (("A", "Add / take off"), ("B", "Back")):
                prompts.pack_start(label(glyph, "glyph"), False, False, 0)
                prompts.pack_start(label(words, "prompt"), False, False, 0)
            page.pack_end(prompts, False, False, 0)
            self.add(page)
            self.connect("key-press-event", self._on_key)
            self.show_all()
            self._draw()
            self.pads = Pads(self._on_pad)

        def _draw(self) -> None:
            for child in self.list.get_children():
                self.list.remove(child)
            for index, app in enumerate(self.apps):
                row = Gtk.Box(spacing=12)
                row.get_style_context().add_class("row")
                if index == self.cursor:
                    row.get_style_context().add_class("focus")
                row.pack_start(label(app["name"], "name", xalign=0, ellipsize=Pango.EllipsizeMode.END), True, True, 0)
                if is_added(app):
                    row.pack_end(label("ADDED", "have"), False, False, 0)
                self.list.pack_start(row, False, False, 0)
            if self.apps:
                app = self.apps[self.cursor]
                kind = "Web site" if app.get("web") else "Needs Chrome (downloaded once)" if "Chrome" in app.get("flatpak", "") else "Program from Flathub (downloaded when added)"
                self.name.set_text(app["name"])
                self.facts.set_text(kind + ("      Added" if is_added(app) else ""))
                self.about.set_text(app.get("about", ""))
            else:
                self.name.set_text("The list of apps could not be read")
            self.list.show_all()

        def _toggle(self) -> None:
            app = self.apps[self.cursor]
            if is_added(app):
                remove(app)
            else:
                add(app, self.pad_maps)
                if app.get("flatpak"):   # fetch its program now, behind the usual notice (B cancels)
                    self.pads.release()
                    self.hide()
                    subprocess.run([str(ROOT / "bin" / "emubox-app"), "install", app["id"]], check=False)
                    self.show()
                    self.pads = Pads(self._on_pad)
            self.changed = True

        def _on_pad(self, button: str) -> None:
            if button == "b":
                Gtk.main_quit()
                return
            if not self.apps:
                return
            if button in ("up", "down"):
                self.cursor = (self.cursor + (1 if button == "down" else -1)) % len(self.apps)
            elif button == "a":
                self._toggle()
            self._draw()

        def _on_key(self, _window, event) -> bool:
            key = {"Up": "up", "Down": "down", "Return": "a", "Escape": "b"}.get(Gdk.keyval_name(event.keyval) or "")
            if key:
                self._on_pad(key)
            return True

    store = Store()
    try:
        Gtk.main()
    finally:
        store.pads.release()
    if store.changed:   # once the menu is back in front, have it notice the new tiles
        subprocess.Popen(["bash", "-c", f"sleep 5; {REFRESH}; sleep 6; {REFRESH}"], stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, start_new_session=True)
    return 0


if __name__ == "__main__":
    sys.exit(screen())
