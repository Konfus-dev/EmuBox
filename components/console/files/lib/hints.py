#!/usr/bin/env python3
"""The strip along the bottom of an app: what the controller's buttons do in it.

    hints.py <app.json>          show the strip until stopped
    hints.py <app.json> --list   print the hints, one per line (no screen needed)

The web view draws the same strip for web apps; this is for every other app
(a Flathub program, the terminal, the file manager). The words come from the
app's own button map, so a new app gets its strip without writing anything:
keys and actions it uses are named in KEYS and ACTIONS below, and an app can
say it better itself with "hints": {"x": "Mute", "lt": ""} ("" hides one).

The strip keeps its own row of the screen: the app's window is maximized
above it (see emubox-app), so nothing of the app is covered.
"""
from __future__ import annotations

import json
import os
import sys

HEIGHT = 40
GLYPHS = {"dpad": "D-PAD", "a": "A", "b": "B", "x": "X", "y": "Y", "lb": "LB", "rb": "RB", "lt": "LT", "rt": "RT",
          "start": "START", "select": "SELECT", "guide": "GUIDE", "l3": "L3", "r3": "R3",
          "left_stick": "L", "right_stick": "R"}
ORDER = ["dpad", "a", "b", "x", "y", "lb", "rb", "lt", "rt", "start", "left_stick", "right_stick", "l3", "r3",
         "select+a", "select+x", "select+r3", "select+up", "select+down", "select+b", "select+start"]
ACTIONS = {"osk": "Keyboard", "click": "Click", "rightclick": "Right-click", "menu": "Menu", "back": "Hide",
           "close": "Quit", "scroll": "Scroll", "pointer": "Pointer", "dpad": "Move", "web-back": "Back"}
KEYS = {   # keys pressed together -> what that usually means
    ("KEY_ENTER",): "Select", ("KEY_ESC",): "Back", ("KEY_BACKSPACE",): "Delete", ("KEY_TAB",): "Next",
    ("KEY_LEFTSHIFT", "KEY_TAB"): "Previous", ("KEY_SPACE",): "Play/Pause", ("KEY_F11",): "Full screen",
    ("KEY_LEFTALT", "KEY_LEFT"): "Back", ("KEY_LEFTALT", "KEY_RIGHT"): "Forward", ("KEY_LEFTALT", "KEY_UP"): "Up a folder",
    ("KEY_LEFTCTRL", "KEY_C"): "Stop", ("KEY_F2",): "Rename", ("KEY_LEFTSHIFT", "KEY_F10"): "Options",
    ("KEY_LEFTSHIFT", "KEY_PAGEUP"): "Scroll up", ("KEY_LEFTSHIFT", "KEY_PAGEDOWN"): "Scroll down", ("KEY_F5",): "Reload",
}
LEAVING = ("select+b", "select+start")
DROP_FIRST = ["r3", "left_stick", "select+a", "select+r3", "right_stick", "l3", "lt", "rt", "select+x", "lb", "rb", "start", "y", "x"]
MEDIA = {"PlayPause": "Play/Pause", "Next": "Next song", "Previous": "Previous song"}


def word(action) -> str:
    """What an action from the button map is called on the strip ("" when it has no short name)."""
    if isinstance(action, str):
        return ACTIONS.get(action, "")
    if isinstance(action, list):
        return KEYS.get(tuple(action), "")
    if isinstance(action, dict):
        if "media" in action:
            return MEDIA.get(action["media"], "")
        run = action.get("run", "")
        return "Volume -" if "setSystemVolume -" in run else "Volume +" if "setSystemVolume +" in run else ""
    return ""


def hints(app: dict) -> list[tuple[str, str]]:
    """(button, what it does) for the strip, in a steady order."""
    pad, own = app.get("pad") or {}, app.get("hints") or {}
    found = []
    if all(pad.get(way) for way in ("up", "down", "left", "right")):
        found.append(("dpad", own.get("dpad", "Move")))
    for button in ORDER[1:] + sorted(set(pad) - set(ORDER) - {"up", "down", "left", "right", "guide", "select+guide"}):
        if button not in pad and button not in own:
            continue
        text = own[button] if button in own else word(pad[button])
        if text:
            found.append((button, text))
    # The same thing on two buttons is said once (Start and X both play, say).
    seen, kept = set(), []
    for button, text in found:
        if text not in seen:
            kept.append((button, text))
            seen.add(text)
    return kept


def glyph(button: str) -> str:
    return "+".join(GLYPHS.get(part, part.upper()) for part in button.split("+"))


CSS = b"""
window { background-color: rgba(11, 71, 11, 0.97); }
* { font-family: "Rajdhani", sans-serif; color: #d6f9b8; }
.glyph { background-color: #124a10; border: 2px solid #96f550; border-radius: 12px;
         font-family: "Michroma", sans-serif; font-size: 11px; padding: 1px 8px; color: #f0ffd7; }
.prompt { font-size: 17px; margin-right: 12px; }
"""


def screen(app: dict) -> int:
    os.environ.setdefault("XDG_RUNTIME_DIR", "/run")
    os.environ.setdefault("WAYLAND_DISPLAY", "wayland-0")
    import gi
    gi.require_version("Gdk", "3.0")
    gi.require_version("Gtk", "3.0")
    gi.require_version("GtkLayerShell", "0.1")
    from gi.repository import Gdk, Gtk, GtkLayerShell

    window = Gtk.Window(title="EmuBox hints")
    GtkLayerShell.init_for_window(window)
    GtkLayerShell.set_namespace(window, "emubox-hints")
    GtkLayerShell.set_layer(window, GtkLayerShell.Layer.TOP)
    for edge in (GtkLayerShell.Edge.BOTTOM, GtkLayerShell.Edge.LEFT, GtkLayerShell.Edge.RIGHT):
        GtkLayerShell.set_anchor(window, edge, True)
    GtkLayerShell.set_exclusive_zone(window, HEIGHT)   # windows are laid out above the strip
    window.set_size_request(-1, HEIGHT)
    provider = Gtk.CssProvider()
    provider.load_from_data(CSS)
    Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    def strip(pairs) -> Gtk.Box:
        row = Gtk.Box(spacing=7, margin_start=16, margin_end=16)
        for button, text in pairs:
            end = button in LEAVING   # how to leave sits at the right-hand end
            for words, style in ((text, "prompt"), (glyph(button), "glyph")) if end else ((glyph(button), "glyph"), (text, "prompt")):
                label = Gtk.Label(label=words, valign=Gtk.Align.CENTER)
                label.get_style_context().add_class(style)
                (row.pack_end if end else row.pack_start)(label, False, False, 0)
        row.show_all()
        return row

    # On a narrow screen the least needed hints go, until the row fits.
    display = Gdk.Display.get_default()
    monitor = display.get_primary_monitor() or display.get_monitor(0)
    width = monitor.get_geometry().width if monitor else 1280
    pairs = hints(app)
    for button in [None] + DROP_FIRST:
        pairs = [pair for pair in pairs if pair[0] != button]
        row = strip(pairs)
        if row.get_preferred_width()[1] <= width:
            break
    window.add(row)
    window.connect("destroy", Gtk.main_quit)
    window.show_all()
    Gtk.main()
    return 0


def main(argv: list[str]) -> int:
    if not argv:
        sys.exit(__doc__)
    with open(argv[0]) as file:
        app = json.load(file)
    if "--list" in argv:
        for button, text in hints(app):
            print(f"{glyph(button)}  {text}")
        return 0
    return screen(app) if hints(app) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
