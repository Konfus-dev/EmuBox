#!/usr/bin/env python3
"""A short note along the top of the screen that goes away by itself.

    toast.py "Signing in? ..." [seconds]

Used for an app's tip (app.json "tip") the first few times the app is opened.
It takes no input and never gets in the way of the app underneath.
"""
import os
import sys

os.environ.setdefault("XDG_RUNTIME_DIR", "/run")
os.environ.setdefault("WAYLAND_DISPLAY", "wayland-0")

import gi  # noqa: E402

gi.require_version("Gdk", "3.0")
gi.require_version("Gtk", "3.0")
gi.require_version("GtkLayerShell", "0.1")
from gi.repository import Gdk, GLib, Gtk, GtkLayerShell  # noqa: E402

CSS = b"""
window { background-color: rgba(2, 18, 2, 0.96); border: 2px solid #68c43c; }
label { font-family: "Rajdhani", sans-serif; font-size: 20px; color: #d6f9b8; padding: 12px 22px; }
"""


def main(argv: list[str]) -> int:
    if not argv:
        sys.exit(__doc__)
    window = Gtk.Window(title="EmuBox")
    GtkLayerShell.init_for_window(window)
    GtkLayerShell.set_namespace(window, "emubox-toast")
    GtkLayerShell.set_layer(window, GtkLayerShell.Layer.OVERLAY)
    GtkLayerShell.set_keyboard_mode(window, GtkLayerShell.KeyboardMode.NONE)
    GtkLayerShell.set_anchor(window, GtkLayerShell.Edge.TOP, True)
    GtkLayerShell.set_margin(window, GtkLayerShell.Edge.TOP, 28)
    provider = Gtk.CssProvider()
    provider.load_from_data(CSS)
    Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
    wide = min(len(argv[0]), 72)   # one line when it fits, else wrapped at a comfortable width
    window.add(Gtk.Label(label=argv[0], wrap=True, width_chars=wide, max_width_chars=wide,
                         justify=Gtk.Justification.CENTER))
    window.show_all()
    GLib.timeout_add_seconds(int(argv[1]) if len(argv) > 1 else 10, Gtk.main_quit)
    Gtk.main()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
