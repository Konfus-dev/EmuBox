#!/usr/bin/env python3
"""Any web page as a full-screen console app, driven with the controller.

    webview.py <address> [--id name]

Uses the web engine Batocera already has (WebKit), so nothing is downloaded.
In every page webnav.js makes the d-pad move between links and buttons, and
pad.py turns the rest of the controller into keys and a pointer (web-pad.json
says which). A keyboard and mouse work as well. Sign-ins are remembered per
--id, under /userdata/system/emubox-web/<id>.

Other screens can put the same view inside their own window: see Browser,
used by vault.py.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.parse
from pathlib import Path

os.environ.setdefault("XDG_RUNTIME_DIR", "/run")
os.environ.setdefault("WAYLAND_DISPLAY", "wayland-0")
os.environ.setdefault("WEBKIT_DISABLE_DMABUF_RENDERER", "1")   # blank pages on some graphics cards otherwise

import gi  # noqa: E402

gi.require_version("Gdk", "3.0")
gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, GLib, Gtk, Pango  # noqa: E402

import settings  # noqa: E402

HERE = Path(__file__).resolve().parent
WebKit2 = None   # the web engine: big, so loaded only when a page is about to be shown (see engine)


def engine():
    """Load the web engine. Takes a moment the first time, so show something first."""
    global WebKit2
    if WebKit2 is None:
        gi.require_version("WebKit2", "4.1")
        from gi.repository import WebKit2 as loaded
        WebKit2 = loaded
    return WebKit2
DATA = "/userdata/system/emubox-web"

CSS = b"""
window { background-color: #021202; }
* { font-family: "Rajdhani", sans-serif; color: #d6f9b8; }
.title { font-family: "Michroma", sans-serif; font-size: 30px; color: #c8f03c; }
.count { font-size: 18px; color: #8fcf6a; }
.row { font-size: 24px; padding: 8px 16px; border: 1px solid transparent; }
.row.focus { background-color: #c8f03c; border-color: #f0ffd7; }
.row.focus label { color: #0a2a00; }
.side { font-size: 16px; color: #8fcf6a; }
.have { font-size: 15px; color: #c8f03c; }
.details { font-size: 20px; }
.bar { background-color: #062606; padding: 4px 18px; }
.where { font-size: 17px; color: #8fcf6a; }
.status { font-size: 17px; color: #c8f03c; }
.prompts { background-color: rgba(11, 71, 11, 0.95); padding: 6px 18px; }
.glyph { background-color: #124a10; border: 2px solid #96f550; border-radius: 14px;
         font-family: "Michroma", sans-serif; font-size: 13px; padding: 2px 9px; color: #f0ffd7; }
.prompt { font-size: 18px; margin-right: 16px; }
.opening { font-family: "Michroma", sans-serif; font-size: 26px; color: #c8f03c; }
progressbar trough { background-color: #062606; border: none; min-height: 4px; }
progressbar progress { background-color: #c8f03c; border: none; min-height: 4px; }
"""
WEB_PROMPTS = (("D-PAD", "Move"), ("A", "Select"), ("B", "Back"), ("X", "Keyboard"), ("Y", "Home"),
               ("R", "Pointer"), ("R3", "Click"), ("L", "Scroll"), ("SELECT+START", "Leave"))


def name_window(app_id: str) -> None:
    """Give our window its name for the compositor. Call before making the window."""
    GLib.set_prgname(app_id)
    Gdk.set_program_class(app_id)


def use_style() -> None:
    provider = Gtk.CssProvider()
    provider.load_from_data(CSS)
    Gtk.StyleContext.add_provider_for_screen(
        Gdk.Screen.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)


def label(text: str, style: str, **properties) -> Gtk.Label:
    widget = Gtk.Label(label=text, **properties)
    widget.get_style_context().add_class(style)
    return widget


class Prompts(Gtk.Box):
    """The strip at the bottom: what the buttons do, and a status line that clears itself."""

    def __init__(self):
        super().__init__()
        self.get_style_context().add_class("prompts")
        self.buttons = Gtk.Box(spacing=8)
        self.pack_start(self.buttons, False, False, 0)
        self.status = label("", "status", xalign=1, ellipsize=Pango.EllipsizeMode.MIDDLE)
        self.pack_end(self.status, True, True, 0)
        self.resting = ""   # shown when no message is up (download progress, say)
        self.timer = 0

    def show_buttons(self, pairs) -> None:
        for child in self.buttons.get_children():
            self.buttons.remove(child)
        for glyph, text in pairs:
            self.buttons.pack_start(label(glyph, "glyph"), False, False, 0)
            self.buttons.pack_start(label(text, "prompt"), False, False, 0)
        self.buttons.show_all()

    def say(self, text: str, seconds: int = 8) -> None:
        self.status.set_text(text)
        if self.timer:
            GLib.source_remove(self.timer)
        self.timer = GLib.timeout_add_seconds(seconds, self._clear)

    def rest(self, text: str) -> None:
        self.resting = text
        if not self.timer:
            self.status.set_text(text)

    def _clear(self) -> bool:
        self.timer = 0
        self.status.set_text(self.resting)
        return False


class Opening(Gtk.Box):
    """What is on screen while the web engine loads: the name and a moving bar, so it never looks frozen."""

    def __init__(self, name: str = ""):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=22,
                         halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER)
        self.title = label("", "opening")
        self.bar = Gtk.ProgressBar()
        self.bar.set_size_request(520, -1)
        self.pack_start(self.title, False, False, 0)
        self.pack_start(self.bar, False, False, 0)
        self.set_name_shown(name)
        self.timer = GLib.timeout_add(120, self._pulse)

    def set_name_shown(self, name: str) -> None:
        self.title.set_text(f"OPENING {name.upper()}" if name else "OPENING")

    def _pulse(self) -> bool:
        self.bar.pulse()
        return True


def adblock_rules(text: str) -> list[dict]:
    """A list in adblock.txt's format, as rules for the web engine's content blocker."""
    rules = []
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("##") and len(line) > 2:
            rules.append({"trigger": {"url-filter": ".*"},
                          "action": {"type": "css-display-none", "selector": line[2:]}})
        elif line and not line.startswith("#"):
            site = re.escape(line.lower()).replace("\\-", "-")
            rules.append({"trigger": {"url-filter": f"^https?://([^/:]+\\.)?{site}[/:]", "load-type": ["third-party"]},
                          "action": {"type": "block"}})
    return rules


def given_name(disposition: str) -> str:
    """The file name in a Content-Disposition header, or "" when it has none."""
    coded = re.search(r"filename\*\s*=\s*[\w-]*'[^']*'([^;]+)", disposition, re.I)
    if coded:
        return urllib.parse.unquote(coded.group(1).strip())
    plain = re.search(r'filename\s*=\s*(?:"([^"]*)"|([^;]+))', disposition, re.I)
    return (plain.group(1) or plain.group(2) or "").strip() if plain else ""


class Browser(Gtk.Box):
    """A web page under a thin bar that says where you are.

    data      folder for sign-ins and the cache
    on_leave  called when Back is pressed with nowhere to go back to
    on_home   called for the Home key (Y); without it, the first address is loaded again
    on_download  called with each WebKit download as it starts; without it downloads are refused
    say       called with one line of text when something needs telling
    """

    def __init__(self, data: str | os.PathLike, on_leave, on_home=None, on_download=None, say=None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        engine()
        self.on_leave, self.on_home, self.on_download = on_leave, on_home, on_download
        self.say = say or (lambda text, seconds=8: None)
        self.start = ""
        self.editing = False   # a text box in the page has the focus
        self.names: dict[str, str] = {}   # address of a download -> the file name its site gave

        bar = Gtk.Box(spacing=24)
        bar.get_style_context().add_class("bar")
        self.where = label("", "where", xalign=0, ellipsize=Pango.EllipsizeMode.END)
        bar.pack_start(self.where, True, True, 0)
        self.pack_start(bar, False, False, 0)
        self.loading = Gtk.ProgressBar()   # a thin line under the bar while a page is on its way
        self.pack_start(self.loading, False, False, 0)

        data = Path(data)
        manager = WebKit2.WebsiteDataManager(base_data_directory=str(data), base_cache_directory=str(data / "cache"))
        context = WebKit2.WebContext.new_with_website_data_manager(manager)
        context.get_cookie_manager().set_persistent_storage(   # stay signed in
            str(data / "cookies.sqlite"), WebKit2.CookiePersistentStorage.SQLITE)
        context.connect("download-started", self._on_download)

        content = WebKit2.UserContentManager()
        try:   # controller navigation in every page
            content.add_script(WebKit2.UserScript.new(
                (HERE / "webnav.js").read_text(), WebKit2.UserContentInjectedFrames.TOP_FRAME,
                WebKit2.UserScriptInjectionTime.END, None, None))
        except OSError:
            pass   # without it there is still the pointer
        if settings.on("web.block_ads"):
            self._block_ads(content, data)
        content.register_script_message_handler("emubox")
        content.connect("script-message-received::emubox", self._on_page_message)

        self.view = WebKit2.WebView(web_context=context, user_content_manager=content)
        self.view.get_settings().set_enable_smooth_scrolling(True)
        self.view.get_settings().set_javascript_can_open_windows_automatically(False)
        self.view.connect("decide-policy", self._on_policy)
        self.view.connect("create", self._on_new_window)
        self.view.connect("load-changed", self._on_load_changed)
        self.view.connect("load-failed", self._on_load_failed)
        for what in ("title", "uri", "estimated-load-progress"):
            self.view.connect(f"notify::{what}", lambda *_: self._draw_where())
        self.pack_start(self.view, True, True, 0)

    def open(self, address: str) -> None:
        self.start = address if "://" in address or address.startswith("about:") else "https://" + address
        self.view.load_uri(self.start)
        self.view.grab_focus()

    def blank(self) -> None:
        """Empty the view (stops sound and video)."""
        self.view.load_uri("about:blank")

    def back(self) -> None:
        if self.view.can_go_back():
            self.view.go_back()
        else:
            self.on_leave()

    def key(self, event) -> bool:
        """Handle a key press meant for the browser itself. False: it is for the page."""
        name = Gdk.keyval_name(event.keyval) or ""
        alt = bool(event.state & Gdk.ModifierType.MOD1_MASK)
        ctrl = bool(event.state & Gdk.ModifierType.CONTROL_MASK)
        if name == "Escape" and self.editing:
            return False   # B first leaves the text box
        if name == "Escape" or (alt and name == "Left"):
            self.back()
        elif alt and name == "Right":
            self.view.go_forward()
        elif alt and name == "Home":
            self.on_home() if self.on_home else self.view.load_uri(self.start)
        elif ctrl and name in ("equal", "plus", "minus"):
            step = -0.1 if name == "minus" else 0.1
            self.view.set_zoom_level(max(0.5, min(3.0, self.view.get_zoom_level() + step)))
        elif name == "F5":
            self.view.reload()
        else:
            return False
        return True

    def _block_ads(self, content, data: Path) -> None:
        """Keep adverts and trackers out of every page (the list is adblock.txt)."""
        text = ""
        for file in (HERE / "adblock.txt", Path(DATA) / "adblock.txt"):
            try:
                text += file.read_text() + "\n"
            except OSError:
                pass
        rules = adblock_rules(text)
        if not rules:
            return
        store = WebKit2.UserContentFilterStore(path=str(data / "filters"))

        def ready(_store, result) -> None:
            try:
                content.add_filter(store.save_finish(result))
            except GLib.Error as error:   # pages still work, with their adverts
                print(f"webview: the ad list could not be used: {error.message}", file=sys.stderr)

        store.save("emubox-adblock", GLib.Bytes.new(json.dumps(rules).encode()), None, ready)

    def _draw_where(self) -> None:
        loading = self.view.get_estimated_load_progress()
        busy_now = self.view.is_loading() and loading < 1
        self.loading.set_fraction(loading if busy_now else 0)
        self.loading.set_opacity(1 if busy_now else 0)
        busy = f"   loading {loading * 100:.0f}%" if self.view.is_loading() and loading < 1 else ""
        address = (self.view.get_uri() or "").split("://", 1)[-1]
        self.where.set_text(f"{self.view.get_title() or ''}   {address}{busy}".strip())

    def _on_page_message(self, _content, result) -> None:
        self.editing = result.get_js_value().to_string() == "editing"

    def _on_load_changed(self, _view, event) -> None:
        if event == WebKit2.LoadEvent.COMMITTED:
            self.editing = False

    def _on_load_failed(self, _view, _event, uri, error) -> bool:
        if error.code not in (102, 302):   # a download taking over, or us going elsewhere: not failures
            self.say(f"Could not open {uri.split('://', 1)[-1][:60]}: {error.message}")
        return False

    def _on_policy(self, _view, decision, kind) -> bool:
        if kind == WebKit2.PolicyDecisionType.RESPONSE:
            headers = decision.get_response().get_http_headers()
            attached = bool(headers) and (headers.get_one("Content-Disposition") or "").lower().startswith("attachment")
            if attached or not decision.is_mime_type_supported():
                name = given_name(headers.get_one("Content-Disposition") or "") if headers else ""
                if name:   # keep the name as the site gave it: WebKit's own suggestion loses the spaces
                    self.names[decision.get_response().get_uri()] = name
                decision.download()
                return True
        elif kind == WebKit2.PolicyDecisionType.NEW_WINDOW_ACTION:   # links that want a new tab
            self.view.load_request(decision.get_navigation_action().get_request())
            decision.ignore()
            return True
        return False

    def _on_new_window(self, _view, action):
        self.view.load_request(action.get_request())
        return None

    def download_name(self, download, suggested: str) -> str:
        """What to call a downloaded file."""
        return self.names.pop(download.get_request().get_uri(), None) or suggested

    def _on_download(self, _context, download) -> None:
        if self.on_download:
            self.on_download(download)
        else:
            download.cancel()
            self.say("Downloads are switched off here")


def start_pad(app_id: str) -> subprocess.Popen | None:
    """The controller, as keys and a pointer, for as long as the window named app_id is in front."""
    try:
        config = {"id": app_id, "window": app_id, "pad": json.loads((HERE / "web-pad.json").read_text()),
                  "strip": False,   # the web view draws the row of hints itself
                  "hold_b": False}  # B is the web view's own Back; holding it means nothing more here
        with tempfile.NamedTemporaryFile("w", prefix=f"{app_id}-", suffix=".json", delete=False) as file:
            json.dump(config, file)
        pad = subprocess.Popen([sys.executable, str(HERE / "pad.py"), file.name],
                               stdout=subprocess.DEVNULL, start_new_session=True)
        subprocess.run(["wlrctl", "toplevel", "focus", f"app_id:{app_id}"], capture_output=True, check=False)
        return pad
    except (OSError, ValueError):
        return None   # not on Batocera: keyboard and mouse still work


def run(window: Gtk.Window, app_id: str) -> None:
    """Show the window full screen with the controller attached, until it is closed."""
    window.connect("destroy", Gtk.main_quit)
    window.fullscreen()
    window.show_all()
    pad = start_pad(app_id)
    try:
        Gtk.main()
    finally:
        if pad:
            pad.terminate()


def main(argv: list[str]) -> int:
    app_id = "emubox-web"
    if "--id" in argv:
        at = argv.index("--id")
        app_id = "emubox-web-" + "".join(c for c in argv[at + 1].lower() if c.isalnum() or c == "-")
        argv = argv[:at] + argv[at + 2:]
    if len(argv) != 1:
        print(__doc__, file=sys.stderr)
        return 2
    name_window(app_id)
    use_style()
    window = Gtk.Window(title=app_id)
    prompts = Prompts()
    prompts.show_buttons(WEB_PROMPTS)
    opening = Opening(argv[0].split("://", 1)[-1].split("/", 1)[0])
    shown: list[Browser] = []

    def on_key(_window, event) -> bool:
        if event.state & Gdk.ModifierType.CONTROL_MASK and (Gdk.keyval_name(event.keyval) or "").lower() == "q":
            window.close()
            return True
        return shown[0].key(event) if shown else True

    page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    page.pack_start(opening, True, True, 0)
    page.pack_end(prompts, False, False, 0)
    window.add(page)
    window.connect("key-press-event", on_key)

    def load() -> bool:   # after the first frame is up
        browser = Browser(Path(DATA) / app_id, on_leave=window.close, say=prompts.say)
        page.remove(opening)
        page.pack_start(browser, True, True, 0)
        browser.show_all()
        shown.append(browser)
        browser.open(argv[0])
        return False

    GLib.timeout_add(150, load)
    run(window, app_id)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
