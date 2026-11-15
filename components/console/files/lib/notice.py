#!/usr/bin/env python3
"""A full-screen "please wait" for something slow, in the console's own style.

    notice.py "Downloading Apple Music" -- some-command with arguments

Runs the command, shows the title with the command's latest line of output
under it and a moving bar, and closes when the command ends. B on any
controller cancels (the command is stopped). Exits with the command's status,
or 130 when cancelled.

Used for an app's first download, so the screen never looks frozen or crashed.
"""
import os
import signal
import subprocess
import sys

import gi

# Batocera's display, for when we are started from a menu with a bare
# environment. GTK connects while it is being imported, so this comes first.
os.environ.setdefault("XDG_RUNTIME_DIR", "/run")
os.environ.setdefault("WAYLAND_DISPLAY", "wayland-0")
ARGV = list(sys.argv)  # as given: loading GTK below takes the "--" out of sys.argv

gi.require_version("Gdk", "3.0")
gi.require_version("Gtk", "3.0")
gi.require_version("GtkLayerShell", "0.1")
from gi.repository import Gdk, GLib, Gtk, GtkLayerShell  # noqa: E402

from padinput import Pads  # noqa: E402

CANCELLED = 130
LINGER_MS = 2500  # how long the final message stays up

CSS = b"""
window { background-color: rgba(2, 18, 2, 0.96); }
* { font-family: "Rajdhani", sans-serif; color: #d6f9b8; }
.title { font-family: "Michroma", sans-serif; font-size: 34px; color: #c8f03c; }
.status { font-size: 22px; }
.hint { font-size: 18px; color: #8fcf6a; }
.glyph { background-color: #124a10; border: 2px solid #96f550; border-radius: 14px;
         font-family: "Michroma", sans-serif; font-size: 13px; padding: 2px 9px; color: #f0ffd7; }
progressbar trough { background-color: #062606; border: 1px solid #1a5a16; min-height: 10px; min-width: 520px; }
progressbar progress { background-color: #c8f03c; border: none; min-height: 10px; }
"""


def tidy(line: str) -> str:
    """One line of a download tool's output, cut down to something readable."""
    line = line.strip().split("\r")[-1].strip()
    return line if len(line) <= 90 else line[:87] + "..."


class Notice(Gtk.Window):
    def __init__(self, title: str, command: list[str]):
        super().__init__(title="EmuBox")
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

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=22,
                      halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER)
        self.title_label = self._label(title, "title")
        self.status = self._label("Starting...", "status")
        self.bar = Gtk.ProgressBar(halign=Gtk.Align.CENTER)
        hint = Gtk.Box(spacing=10, halign=Gtk.Align.CENTER)
        hint.pack_start(self._label("B", "glyph"), False, False, 0)
        hint.pack_start(self._label("Cancel", "hint"), False, False, 0)
        self.hint = hint
        for widget in (self.title_label, self.bar, self.status, hint):
            box.pack_start(widget, False, False, 0)
        self.add(box)
        self.show_all()

        self.result: int | None = None
        self.process = subprocess.Popen(
            command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            errors="replace", start_new_session=True)
        GLib.io_add_watch(self.process.stdout, GLib.IO_IN | GLib.IO_HUP, self._on_output)
        GLib.timeout_add(120, self._pulse)
        self.pads = Pads(self._on_pad)

    @staticmethod
    def _label(text: str, style: str) -> Gtk.Label:
        label = Gtk.Label(label=text)
        label.get_style_context().add_class(style)
        return label

    def _pulse(self) -> bool:
        if self.result is None:
            self.bar.pulse()
        return self.result is None

    def _on_output(self, source, _condition) -> bool:
        line = source.readline()
        if line:
            if tidy(line):
                self.last = tidy(line)
                self.status.set_text(self.last)
            return True
        self._finish(self.process.wait())
        return False

    def _finish(self, status: int) -> None:
        if self.result is not None:
            return
        self.result = status
        self.bar.set_fraction(1.0 if status == 0 else 0.0)
        self.hint.hide()
        if status == CANCELLED:
            self.status.set_text("Cancelled.")
        elif status != 0:
            said = getattr(self, "last", "")
            self.status.set_text(f"That did not work: {said}" if said and "ready" not in said
                                 else "That did not work. Check the internet connection and try again.")
        GLib.timeout_add(LINGER_MS * 2 if status not in (0, CANCELLED) else LINGER_MS if status else 900, Gtk.main_quit)

    def cancel(self) -> None:
        if self.result is None:
            try:
                os.killpg(self.process.pid, signal.SIGTERM)
            except OSError:
                pass
            self._finish(CANCELLED)

    def _on_pad(self, button: str) -> None:
        if button == "b":
            self.cancel()


def main() -> int:
    if "--" not in ARGV or len(ARGV) < 4:
        print(__doc__, file=sys.stderr)
        return 2
    split = ARGV.index("--")
    notice = Notice(" ".join(ARGV[1:split]), ARGV[split + 1:])
    GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGTERM, notice.cancel)
    try:
        Gtk.main()
    finally:
        notice.pads.release()
    return notice.result if notice.result is not None else CANCELLED


if __name__ == "__main__":
    sys.exit(main())
