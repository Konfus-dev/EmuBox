#!/usr/bin/env python3
"""Type on your phone, and have it typed here: for signing in without a keyboard.

    phonekeys.py        show the QR code (opened from the on-screen keyboard's PHONE key)

A QR code and an address appear in a corner. Scanning it opens a small page on
the phone; what is typed there and sent is typed into the app in front, as if on
a keyboard. B on the controller (or Done on the phone) ends it.

How private it is, plainly: the page is served by this machine to your own
network only for as long as the code is on screen, and its address holds a
random word made for this one time, so another device has to see the code to
use it. What you send is not encrypted on its way across your network (there is
no way to give a phone a trusted lock for an address like 192.168.1.20). On a
home network that is the same exposure as a wireless keyboard; do not use it on
a network you do not trust.
"""
from __future__ import annotations

import json
import os
import secrets
import socket
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORTS = range(8377, 8387)
KEYS = ("enter", "backspace", "tab")   # the page's buttons
LONGEST = 2000   # characters accepted at once

PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>EmuBox keyboard</title>
<style>
  body { margin: 0; padding: 18px; background: #021202; color: #d6f9b8; font: 18px system-ui, sans-serif; }
  h1 { font-size: 20px; color: #c8f03c; margin: 0 0 4px; }
  p { margin: 0 0 14px; color: #8fcf6a; font-size: 15px; }
  input[type=text], input[type=password] { box-sizing: border-box; width: 100%; padding: 14px; font-size: 20px;
      background: #062606; color: #f0ffd7; border: 2px solid #68c43c; border-radius: 8px; }
  .row { display: flex; gap: 10px; margin-top: 12px; flex-wrap: wrap; }
  button { flex: 1; padding: 14px 8px; font-size: 17px; color: #0a2a00; background: #c8f03c; border: 0; border-radius: 8px; }
  button.plain { background: #124a10; color: #d6f9b8; border: 1px solid #68c43c; }
  label { display: block; margin-top: 12px; font-size: 16px; }
  #said { min-height: 1.4em; margin-top: 14px; color: #c8f03c; }
</style></head><body>
<h1>EmuBox keyboard</h1>
<p>Select the box on the TV first. What you send is typed there.</p>
<form id="form" autocomplete="off">
  <input id="text" type="text" autocapitalize="none" autocorrect="off" spellcheck="false" autofocus>
  <label><input id="hide" type="checkbox"> Hide what I type (for a password)</label>
  <div class="row"><button type="submit">Send</button><button type="button" id="sendenter">Send + Enter</button></div>
  <div class="row">
    <button type="button" class="plain" data-key="tab">Tab</button>
    <button type="button" class="plain" data-key="backspace">Backspace</button>
    <button type="button" class="plain" data-key="enter">Enter</button>
  </div>
  <div class="row"><button type="button" class="plain" id="done">Done</button></div>
</form>
<div id="said"></div>
<script>
  const text = document.getElementById('text'), said = document.getElementById('said');
  async function post(what) {
    try {
      const reply = await fetch(location.pathname + '/do', {method: 'POST', body: JSON.stringify(what)});
      said.textContent = reply.ok ? (what.done ? 'Closed. You can put the phone away.' : 'Sent.') : 'The TV is no longer listening: scan the code again.';
      return reply.ok;
    } catch (error) { said.textContent = 'Could not reach the TV. Same Wi-Fi?'; return false; }
  }
  async function send(enter) {
    if (await post({text: text.value, key: enter ? 'enter' : ''})) text.value = '';
    text.focus();
  }
  document.getElementById('form').addEventListener('submit', event => { event.preventDefault(); send(false); });
  document.getElementById('sendenter').addEventListener('click', () => send(true));
  document.getElementById('done').addEventListener('click', () => post({done: true}));
  document.getElementById('hide').addEventListener('change', event => { text.type = event.target.checked ? 'password' : 'text'; });
  for (const button of document.querySelectorAll('[data-key]'))
    button.addEventListener('click', () => post({key: button.dataset.key}));
</script></body></html>
"""


def address() -> str:
    """This machine's address on the home network ('' when it has none)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.connect(("192.0.2.1", 9))      # nothing is sent: this only asks which address would be used
            found = probe.getsockname()[0]
    except OSError:
        return ""
    return "" if found.startswith("127.") else found


def typing(typer):
    """What to do with what the phone sends: type it into the app in front, as the on-screen
    keyboard does (typer.py). One thing at a time, in the order it arrived."""
    busy = threading.Lock()

    def type_out(text: str = "", key: str = "") -> None:
        with busy:
            if text:
                typer.text(text[:LONGEST])
            if key in KEYS:
                typer.key(key)
    return type_out


def serve(token: str, on_type, on_done=lambda: None, ports=PORTS, host: str = "") -> ThreadingHTTPServer:
    """The page and what it sends, at /k/<token> only. Runs on its own thread; .shutdown() stops it."""
    path = f"/k/{token}"

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args) -> None:   # what is typed never goes into a log
            pass

        def reply(self, status: int, body: bytes = b"", kind: str = "text/plain") -> None:
            self.send_response(status)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:   # noqa: N802
            if self.path == path:
                self.reply(200, PAGE.encode(), "text/html; charset=utf-8")
            else:
                self.reply(404)

        def do_POST(self) -> None:   # noqa: N802
            if self.path != path + "/do":
                self.reply(404)
                return
            try:
                sent = json.loads(self.rfile.read(min(int(self.headers.get("Content-Length", 0)), 4 * LONGEST + 200)))
                if not isinstance(sent, dict):
                    raise ValueError
            except (ValueError, OSError):
                self.reply(400)
                return
            # Typed first, answered after: the page waits for the answer before sending more,
            # so things are typed in the order they were sent.
            if not sent.get("done"):
                on_type(str(sent.get("text") or ""), str(sent.get("key") or ""))
            self.reply(200, b"ok")
            if sent.get("done"):
                on_done()

    for port in ports:
        try:
            server = ThreadingHTTPServer((host, port), Handler)
            break
        except OSError:
            continue
    else:
        raise OSError("no free port for the phone keyboard")
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


CSS = b"""
window { background-color: rgba(2, 18, 2, 0.97); border: 2px solid #68c43c; }
* { font-family: "Rajdhani", sans-serif; color: #d6f9b8; }
.title { font-family: "Michroma", sans-serif; font-size: 20px; color: #c8f03c; }
.words { font-size: 18px; }
.address { font-size: 20px; color: #f0ffd7; }
.small { font-size: 15px; color: #8fcf6a; }
.glyph { background-color: #124a10; border: 2px solid #96f550; border-radius: 12px;
         font-family: "Michroma", sans-serif; font-size: 12px; padding: 1px 8px; color: #f0ffd7; }
"""


def screen() -> int:
    os.environ.setdefault("XDG_RUNTIME_DIR", "/run")
    os.environ.setdefault("WAYLAND_DISPLAY", "wayland-0")
    import gi
    gi.require_version("Gdk", "3.0")
    gi.require_version("Gtk", "3.0")
    gi.require_version("GdkPixbuf", "2.0")
    gi.require_version("GtkLayerShell", "0.1")
    from gi.repository import Gdk, GdkPixbuf, GLib, Gtk, GtkLayerShell

    import qr
    from padinput import Pads
    from typer import Typer
    typer = Typer()

    window = Gtk.Window(title="EmuBox phone keyboard")
    GtkLayerShell.init_for_window(window)
    GtkLayerShell.set_namespace(window, "emubox-phonekeys")
    GtkLayerShell.set_layer(window, GtkLayerShell.Layer.OVERLAY)
    GtkLayerShell.set_keyboard_mode(window, GtkLayerShell.KeyboardMode.NONE)   # the app keeps the typing
    for edge in (GtkLayerShell.Edge.TOP, GtkLayerShell.Edge.RIGHT):               # a corner: the page stays in view
        GtkLayerShell.set_anchor(window, edge, True)
        GtkLayerShell.set_margin(window, edge, 24)
    provider = Gtk.CssProvider()
    provider.load_from_data(CSS)
    Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    def label(text: str, style: str) -> Gtk.Label:
        made = Gtk.Label(label=text, xalign=0, wrap=True, max_width_chars=34)
        made.get_style_context().add_class(style)
        return made

    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, margin=18)
    box.pack_start(label("TYPE FROM YOUR PHONE", "title"), False, False, 0)
    here, server = address(), None
    if here:
        token = secrets.token_urlsafe(9)
        server = serve(token, typing(typer), on_done=lambda: GLib.idle_add(Gtk.main_quit))
        link = f"http://{here}:{server.server_address[1]}/k/{token}"
        picture = qr.image(link, scale=7).convert("RGB")
        pixels = GdkPixbuf.Pixbuf.new_from_data(picture.tobytes(), GdkPixbuf.Colorspace.RGB, False, 8,
                                                picture.width, picture.height, picture.width * 3)
        box.pack_start(Gtk.Image.new_from_pixbuf(pixels.copy()), False, False, 0)
        box.pack_start(label("Scan this with your phone's camera (same Wi-Fi as this PC). Select a box on "
                             "the page here, then type on the phone and press Send.", "words"), False, False, 0)
        box.pack_start(label("It works on your own network only while this is showing. What you send is "
                             "not encrypted on the way.", "small"), False, False, 0)
    else:
        box.pack_start(label("This PC is not on a network, so a phone cannot reach it. "
                             "Start > Network Settings sets up Wi-Fi.", "words"), False, False, 0)
    foot = Gtk.Box(spacing=8)
    foot.pack_start(label("B", "glyph"), False, False, 0)
    foot.pack_start(label("Close", "words"), False, False, 0)
    box.pack_start(foot, False, False, 0)
    window.add(box)
    window.connect("destroy", Gtk.main_quit)
    window.show_all()

    pads = Pads(lambda name: Gtk.main_quit() if name in ("b", "guide", "select") else None)
    try:
        Gtk.main()
    finally:
        pads.release()
        if server:
            server.shutdown()
        typer.close()
    return 0


if __name__ == "__main__":
    sys.exit(screen())
