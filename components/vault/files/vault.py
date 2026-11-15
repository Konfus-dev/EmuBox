#!/usr/bin/env python3
"""Vault: your own list of store pages, browsed with the controller.

    vault                         open Vault (what the Store tile does)
    vault pages                   list the pages
    vault add "Name" https://...  add a page, or change the address of one with that name
    vault remove "Name"           take a page off the list
    vault command ['shell line']  show or set what runs for each download
    vault refresh ['shell line']  show or set what runs once on leaving, after any install
    vault downloads [folder]      show or set where downloads are saved
    vault reset                   back to the built-in command, refresh and downloads folder
    vault show                    everything that is set

Pick a page and it opens full screen. Whatever you download there is saved to
Vault's downloads folder; the moment a finished file is noticed in that folder
Vault asks "Install to which system?" and runs the command for it. The command
is one shell line and is given:

    $VAULT_FILE       the downloaded file
    $VAULT_SYSTEM     the system picked (the folder name under the games folder, e.g. psx)
    $VAULT_GAMES      the games folder (/userdata/roms)
    $VAULT_DOWNLOADS  the downloads folder

Settings live in /userdata/system/vault/vault.json (another place: --home <folder>
or the VAULT_HOME variable, e.g. to edit a drive plugged into a PC).

The controller is turned into keys and a pointer by pad.py (see pad.json), so a
keyboard and mouse work just as well.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_HOME = "/userdata/system/vault"
GAMES = "/userdata/roms"
ES_SYSTEMS = ("/userdata/system/configs/emulationstation/es_systems.cfg",
              "/usr/share/emulationstation/es_systems.cfg")
DEFAULT_COMMAND = 'mv -n -- "$VAULT_FILE" "$VAULT_GAMES/$VAULT_SYSTEM/"'
DEFAULT_REFRESH = "curl -s -m 10 http://127.0.0.1:1234/reloadgames"
DEFAULT_PAGES = [{"name": "itch.io", "url": "https://itch.io/games"}]
PARTIAL = (".part", ".crdownload", ".tmp", ".download")
NOT_GAME_FOLDERS = {"store"}      # system folders that are menus of ours, not places for games
SETTLE_S = 2.0                    # a file must sit unchanged this long before we ask about it


# --- settings ---------------------------------------------------------------------

class Settings:
    def __init__(self, home: str | os.PathLike | None = None):
        self.home = Path(home or os.environ.get("VAULT_HOME") or DEFAULT_HOME)
        self.file = self.home / "vault.json"
        try:
            self.data = json.loads(self.file.read_text())
        except (OSError, ValueError):
            self.data = {}

    def save(self) -> None:
        self.home.mkdir(parents=True, exist_ok=True)
        self.file.write_text(json.dumps(self.data, indent=2) + "\n")

    @property
    def pages(self) -> list[dict]:
        return self.data.get("pages", DEFAULT_PAGES)

    @property
    def command(self) -> str:
        return self.data.get("command", DEFAULT_COMMAND)

    @property
    def refresh(self) -> str:
        return self.data.get("refresh", DEFAULT_REFRESH)

    @property
    def downloads(self) -> Path:
        return Path(self.data.get("downloads") or self.home / "downloads")

    def add_page(self, name: str, url: str) -> None:
        if "://" not in url:
            url = "https://" + url
        pages = [dict(p) for p in self.pages]
        for page in pages:
            if page["name"].lower() == name.lower():
                page["url"] = url
                break
        else:
            pages.append({"name": name, "url": url})
        self.data["pages"] = pages

    def remove_page(self, name: str) -> bool:
        kept = [p for p in self.pages if p["name"].lower() != name.lower()]
        found = len(kept) != len(self.pages)
        self.data["pages"] = kept
        return found


# --- systems and downloads ---------------------------------------------------------

def systems(games: str | os.PathLike = GAMES, configs=ES_SYSTEMS) -> list[dict]:
    """The systems a game can go to: every folder under the games folder, with the
    name and file types Batocera knows for it. Sorted by name."""
    known: dict[str, dict] = {}
    for config in reversed(configs):   # the user's own file wins
        try:
            root = ET.parse(config).getroot()
        except (OSError, ET.ParseError):
            continue
        for system in root.findall("system"):
            folder = (system.findtext("name") or "").strip()
            if folder:
                known[folder] = {
                    "name": (system.findtext("fullname") or folder).strip(),
                    "types": set((system.findtext("extension") or "").lower().split()),
                }
    found = []
    try:
        folders = sorted(p.name for p in Path(games).iterdir() if p.is_dir())
    except OSError:
        folders = []
    for folder in folders:
        if folder.startswith(".") or folder in NOT_GAME_FOLDERS:
            continue
        info = known.get(folder, {"name": folder, "types": set()})
        found.append({"folder": folder, "name": info["name"], "types": info["types"]})
    return sorted(found, key=lambda s: s["name"].lower())


def likely_first(all_systems: list[dict], filename: str) -> tuple[list[dict], int]:
    """The systems that play this kind of file first, then the rest. Also how many are likely.
    Archives fit nearly everything, so they say nothing."""
    kind = Path(filename).suffix.lower()
    if kind in ("", ".zip", ".7z", ".rar"):
        return list(all_systems), 0
    likely = [s for s in all_systems if kind in s["types"]]
    if len(likely) > 12:
        return list(all_systems), 0
    return likely + [s for s in all_systems if kind not in s["types"]], len(likely)


def free_name(folder: Path, name: str) -> Path:
    """A path in the folder that is not taken: "Game.zip", then "Game (1).zip"..."""
    name = name.replace("/", "_").lstrip(".") or "download"
    path, n = folder / name, 0
    while path.exists():
        n += 1
        path = folder / f"{Path(name).stem} ({n}){Path(name).suffix}"
    return path


class Watcher:
    """Notices finished files in the downloads folder. A file counts once it has
    stopped changing and nobody is known to be writing it."""

    def __init__(self, folder: Path):
        self.folder = folder
        self.writing: set[str] = set()     # names being downloaded right now
        self.left: set[str] = set()        # names the player said "not now" to
        self.seen: dict[str, tuple] = {}   # name -> (size, mtime, first time seen like that)

    def ready(self, now: float | None = None) -> list[Path]:
        now = time.monotonic() if now is None else now
        done = []
        try:
            entries = sorted(self.folder.iterdir())
        except OSError:
            return []
        for path in entries:
            name = path.name
            if (name.startswith(".") or name.endswith(PARTIAL) or name in self.writing
                    or name in self.left or not path.is_file()):
                continue
            stat = path.stat()
            before = self.seen.get(name)
            if not before or before[:2] != (stat.st_size, stat.st_mtime):
                self.seen[name] = (stat.st_size, stat.st_mtime, now)
            elif now - before[2] >= SETTLE_S:
                done.append(path)
        return done


def run_command(line: str, settings: Settings, file: Path | None = None, system: str = "",
                games: str = GAMES) -> tuple[bool, str]:
    """Run a shell line with Vault's variables. Gives (worked, last line it printed)."""
    env = dict(os.environ, VAULT_FILE=str(file or ""), VAULT_SYSTEM=system,
               VAULT_GAMES=games, VAULT_DOWNLOADS=str(settings.downloads))
    try:
        result = subprocess.run(["bash", "-c", line], env=env, capture_output=True, text=True,
                                timeout=3600, check=False)
    except (OSError, subprocess.TimeoutExpired) as error:
        return False, str(error)
    said = (result.stderr.strip() or result.stdout.strip()).splitlines()
    return result.returncode == 0, said[-1] if said else ""


# --- the screen ---------------------------------------------------------------------

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
"""
PROMPTS = {
    "pages": (("A", "Open"), ("B", "Leave Vault")),
    "web": (("L", "Pointer"), ("A", "Click"), ("R", "Scroll"), ("X", "Keyboard"), ("B", "Back"),
            ("Y", "Pages"), ("LT RT", "Zoom"), ("SELECT+START", "Leave")),
    "systems": (("A", "Install here"), ("LB RB", "Jump"), ("B", "Not now")),
}
VISIBLE_ROWS = 11


def ui(settings: Settings) -> int:
    os.environ.setdefault("XDG_RUNTIME_DIR", "/run")
    os.environ.setdefault("WAYLAND_DISPLAY", "wayland-0")
    os.environ.setdefault("WEBKIT_DISABLE_DMABUF_RENDERER", "1")   # blank pages on some graphics cards otherwise
    import gi
    gi.require_version("Gdk", "3.0")
    gi.require_version("Gtk", "3.0")
    gi.require_version("WebKit2", "4.1")
    from gi.repository import Gdk, GLib, Gtk, Pango, WebKit2

    APP_ID = "retrobox-vault"
    GLib.set_prgname(APP_ID)   # the window's name for the compositor; pad.json looks for it
    Gdk.set_program_class(APP_ID)

    def label(text: str, style: str, **properties) -> Gtk.Label:
        widget = Gtk.Label(label=text, **properties)
        widget.get_style_context().add_class(style)
        return widget

    class Vault(Gtk.Window):
        def __init__(self):
            super().__init__(title="Vault")
            provider = Gtk.CssProvider()
            provider.load_from_data(CSS)
            Gtk.StyleContext.add_provider_for_screen(
                Gdk.Screen.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

            self.mode = "pages"
            self.before_asking = "pages"       # where to return after "which system?"
            self.cursor = {"pages": 0, "systems": 0}
            self.asking: Path | None = None    # the download we are asking about
            self.choices: list[dict] = []
            self.likely = 0
            self.installed = 0
            self.progress: dict[str, float] = {}
            self.status_timer = 0
            settings.downloads.mkdir(parents=True, exist_ok=True)
            self.watcher = Watcher(settings.downloads)

            page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            self.stack = Gtk.Stack()
            page.pack_start(self.stack, True, True, 0)

            # A list screen, used for both the pages and the systems.
            lists = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            head = Gtk.Box(margin=24, margin_bottom=10, spacing=24)
            self.heading = label("VAULT", "title", xalign=0)
            head.pack_start(self.heading, False, False, 0)
            self.count = label("", "count", xalign=1)
            head.pack_end(self.count, False, False, 0)
            lists.pack_start(head, False, False, 0)
            self.about = label("", "details", xalign=0, wrap=True, margin_start=24, margin_end=24, margin_bottom=10)
            lists.pack_start(self.about, False, False, 0)
            self.rows = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, margin_start=24, margin_end=24)
            lists.pack_start(self.rows, True, True, 0)
            self.stack.add_named(lists, "list")

            # The web page, under a thin bar that says where you are.
            web = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            bar = Gtk.Box(spacing=24)
            bar.get_style_context().add_class("bar")
            self.where = label("", "where", xalign=0, ellipsize=Pango.EllipsizeMode.END)
            bar.pack_start(self.where, True, True, 0)
            web.pack_start(bar, False, False, 0)
            data = WebKit2.WebsiteDataManager(base_data_directory=str(settings.home / "web"),
                                              base_cache_directory=str(settings.home / "web" / "cache"))
            context = WebKit2.WebContext.new_with_website_data_manager(data)
            context.get_cookie_manager().set_persistent_storage(   # stay signed in
                str(settings.home / "web" / "cookies.sqlite"), WebKit2.CookiePersistentStorage.SQLITE)
            context.connect("download-started", self._on_download)
            self.view = WebKit2.WebView.new_with_context(context)
            self.view.get_settings().set_enable_smooth_scrolling(True)
            self.view.get_settings().set_javascript_can_open_windows_automatically(False)
            self.view.connect("decide-policy", self._on_policy)
            self.view.connect("create", self._on_new_window)
            self.view.connect("notify::title", lambda *_: self._draw_where())
            self.view.connect("notify::uri", lambda *_: self._draw_where())
            self.view.connect("notify::estimated-load-progress", lambda *_: self._draw_where())
            self.view.connect("load-failed", self._on_load_failed)
            web.pack_start(self.view, True, True, 0)
            self.stack.add_named(web, "web")

            foot = Gtk.Box()
            foot.get_style_context().add_class("prompts")
            self.prompts = Gtk.Box(spacing=8)
            foot.pack_start(self.prompts, False, False, 0)
            self.status = label("", "status", xalign=1, ellipsize=Pango.EllipsizeMode.MIDDLE)
            foot.pack_end(self.status, True, True, 0)
            page.pack_end(foot, False, False, 0)
            self.add(page)

            self.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)
            self.connect("key-press-event", self._on_key)
            self.connect("button-press-event", self._on_click)
            self.connect("destroy", Gtk.main_quit)
            self.fullscreen()
            self.show_all()
            self._show("pages")
            GLib.timeout_add(1000, self._look_for_downloads)

        # --- drawing --------------------------------------------------------------

        def _show(self, mode: str) -> None:
            self.mode = mode
            self.stack.set_visible_child_name("web" if mode == "web" else "list")
            for child in self.prompts.get_children():
                self.prompts.remove(child)
            for glyph, text in PROMPTS[mode]:
                self.prompts.pack_start(label(glyph, "glyph"), False, False, 0)
                self.prompts.pack_start(label(text, "prompt"), False, False, 0)
            self.prompts.show_all()
            window = self.get_window()
            if window:   # no stray pointer over the lists
                window.set_cursor(None if mode == "web" else Gdk.Cursor.new_for_display(
                    window.get_display(), Gdk.CursorType.BLANK_CURSOR))
            if mode == "web":
                self.view.grab_focus()
            else:
                self._draw_list()

        def _items(self) -> list[dict]:
            return settings.pages if self.mode == "pages" else self.choices

        def _draw_list(self) -> None:
            for child in self.rows.get_children():
                self.rows.remove(child)
            items = self._items()
            if self.mode == "pages":
                self.heading.set_text("VAULT")
                self.about.set_text("" if items else
                                    'No pages yet. Add one with:  vault add "Name" https://address')
            else:
                self.heading.set_text("INSTALL TO WHICH SYSTEM?")
                self.about.set_text(self.asking.name if self.asking else "")
            if not items:
                self.count.set_text("")
                self.rows.show_all()
                return
            cursor = self.cursor[self.mode] = min(self.cursor[self.mode], len(items) - 1)
            first = max(0, min(cursor - VISIBLE_ROWS // 2, len(items) - VISIBLE_ROWS))
            for index in range(first, min(first + VISIBLE_ROWS, len(items))):
                item = items[index]
                row = Gtk.Box(spacing=12)
                row.get_style_context().add_class("row")
                if index == cursor:
                    row.get_style_context().add_class("focus")
                row.pack_start(label(item["name"], "name", xalign=0, ellipsize=Pango.EllipsizeMode.END), True, True, 0)
                if self.mode == "pages":
                    side = item["url"].split("://", 1)[-1].rstrip("/")
                else:
                    side = item["folder"]
                    if index < self.likely:
                        row.pack_end(label("PLAYS THIS FILE", "have"), False, False, 0)
                row.pack_end(label(side, "side", ellipsize=Pango.EllipsizeMode.END, max_width_chars=48), False, False, 0)
                self.rows.pack_start(row, False, False, 0)
            self.count.set_text(f"{cursor + 1} of {len(items)}")
            self.rows.show_all()

        def _draw_where(self) -> None:
            loading = self.view.get_estimated_load_progress()
            busy = f"   loading {loading * 100:.0f}%" if self.view.is_loading() and loading < 1 else ""
            address = (self.view.get_uri() or "").split("://", 1)[-1]
            self.where.set_text(f"{self.view.get_title() or ''}   {address}{busy}".strip())

        def say(self, text: str, seconds: int = 8) -> None:
            """A line at the bottom right; it clears itself."""
            self.status.set_text(text)
            if self.status_timer:
                GLib.source_remove(self.status_timer)
            self.status_timer = GLib.timeout_add_seconds(seconds, self._clear_status) if seconds else 0

        def _clear_status(self) -> bool:
            self.status_timer = 0
            self._draw_downloading()
            return False

        def _draw_downloading(self) -> None:
            if self.status_timer:
                return   # a message is up; the timer brings the progress back
            self.status.set_text("   ".join(
                f"Downloading {name} {done * 100:.0f}%" for name, done in self.progress.items()))

        # --- downloads ----------------------------------------------------------------

        def _on_policy(self, _view, decision, kind) -> bool:
            if kind == WebKit2.PolicyDecisionType.RESPONSE:
                response = decision.get_response()
                headers = response.get_http_headers()
                attached = bool(headers) and (headers.get_one("Content-Disposition") or "").lower().startswith("attachment")
                if attached or not decision.is_mime_type_supported():
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

        def _on_load_failed(self, _view, _event, uri, error) -> bool:
            if "download" not in error.message.lower() and not error.matches(
                    WebKit2.policy_error_quark(), WebKit2.PolicyError.FRAME_LOAD_INTERRUPTED_BY_POLICY_CHANGE):
                self.say(f"Could not open {uri.split('://', 1)[-1][:60]}: {error.message}")
            return False

        def _on_download(self, _context, download) -> None:
            state = {"name": None}

            def destination(_download, suggested: str) -> bool:
                path = free_name(settings.downloads, suggested)
                state["name"] = path.name
                self.watcher.writing.add(path.name)
                self.progress[path.name] = 0.0
                download.set_destination(path.as_uri())
                self.say(f"Downloading {path.name}", 4)
                return True

            def received(_download, _length) -> None:
                if state["name"]:
                    self.progress[state["name"]] = download.get_estimated_progress()
                    self._draw_downloading()

            def failed(_download, error) -> None:
                name = state["name"]
                if name:   # no half file left behind to be asked about
                    try:
                        (settings.downloads / name).unlink()
                    except OSError:
                        pass
                self.say(f"Download failed: {name or ''} {error.message}".strip())

            def finished(_download) -> None:
                name = state["name"]
                if name:
                    self.progress.pop(name, None)
                    self.watcher.writing.discard(name)
                    self.watcher.seen[name] = (-1, -1, 0)   # ours and complete: ask without the settling wait
                    self._draw_downloading()
                    self._look_for_downloads()

            download.connect("decide-destination", destination)
            download.connect("received-data", received)
            download.connect("failed", failed)
            download.connect("finished", finished)

        def _look_for_downloads(self) -> bool:
            """Anything finished in the downloads folder? Ask where it goes, one file at a time."""
            if self.mode != "systems":
                now = time.monotonic()
                waiting = []
                for path in self.watcher.ready(now + SETTLE_S):   # our own finished downloads first
                    if self.watcher.seen.get(path.name, (0,))[0] == -1:
                        waiting.append(path)
                waiting = waiting or self.watcher.ready(now)
                if waiting:
                    self._ask(waiting[0])
            return True

        def _ask(self, path: Path) -> None:
            self.asking = path
            self.choices, self.likely = likely_first(systems(), path.name)
            self.cursor["systems"] = 0
            if self.mode != "systems":
                self.before_asking = self.mode
            if not self.choices:
                self.watcher.left.add(path.name)
                self.say(f"No system folders found in {GAMES}; {path.name} stays in downloads")
                return
            self._show("systems")

        def _install(self, system: dict) -> None:
            path = self.asking
            worked, said = run_command(settings.command, settings, path, system["folder"])
            if worked:
                self.installed += 1
                self.say(f"{path.name} installed to {system['name']}")
            else:
                self.say(f"Could not install {path.name}: {said or 'the command failed'}", 15)
            if path.exists():   # the command left it (or failed): do not ask again this time
                self.watcher.left.add(path.name)
            self._done_asking()

        def _done_asking(self) -> None:
            self.asking = None
            self._show(self.before_asking)
            self._look_for_downloads()   # the next file, if there is one

        # --- input ------------------------------------------------------------------

        def _open(self, page: dict) -> None:
            self._show("web")
            self.view.load_uri(page["url"])

        def _back(self) -> None:
            if self.view.can_go_back():
                self.view.go_back()
            else:
                self._to_pages()

        def _to_pages(self) -> None:
            self.view.load_uri("about:blank")   # stops sound and video
            self._show("pages")

        def _choose(self) -> None:
            items = self._items()
            if not items:
                return
            item = items[self.cursor[self.mode]]
            self._open(item) if self.mode == "pages" else self._install(item)

        def _on_click(self, _window, event) -> bool:
            if self.mode == "web":
                return False
            if event.type == Gdk.EventType.BUTTON_PRESS and event.button == 1:
                self._choose()   # A is a click, wherever the hidden pointer happens to be
            return True

        def _on_key(self, _window, event) -> bool:
            key = Gdk.keyval_name(event.keyval) or ""
            alt = bool(event.state & Gdk.ModifierType.MOD1_MASK)
            ctrl = bool(event.state & Gdk.ModifierType.CONTROL_MASK)
            if ctrl and key.lower() == "q":
                self.close()
                return True
            if self.mode == "web":
                if key == "Escape" or (alt and key == "Left"):
                    self._back()
                elif alt and key == "Right":
                    self.view.go_forward()
                elif alt and key == "Home":
                    self._to_pages()
                elif ctrl and key in ("equal", "plus", "minus"):
                    step = -0.1 if key == "minus" else 0.1
                    self.view.set_zoom_level(max(0.5, min(3.0, self.view.get_zoom_level() + step)))
                elif key == "F5":
                    self.view.reload()
                else:
                    return False   # everything else is for the page
                return True
            items = self._items()
            step = {"Up": -1, "Down": 1, "Page_Up": -VISIBLE_ROWS, "Page_Down": VISIBLE_ROWS}.get(key)
            if alt and key in ("Left", "Right"):   # LB / RB
                step = -VISIBLE_ROWS if key == "Left" else VISIBLE_ROWS
            if step and items:
                cursor = self.cursor[self.mode] + step
                self.cursor[self.mode] = cursor % len(items) if abs(step) == 1 else max(0, min(len(items) - 1, cursor))
                self._draw_list()
            elif key in ("Return", "KP_Enter", "space"):
                self._choose()
            elif key == "Escape":
                if self.mode == "pages":
                    self.close()
                else:   # not now: the file stays in downloads and is asked about next time
                    self.watcher.left.add(self.asking.name)
                    self.say(f"{self.asking.name} left in downloads")
                    self._done_asking()
            return True

    vault = Vault()
    pad = None
    try:   # the controller, as keys and a pointer, for as long as our window is in front
        pad = subprocess.Popen([sys.executable, str(HERE / "pad.py"), str(HERE / "vault-pad.json")],
                               stdout=subprocess.DEVNULL, start_new_session=True)
        subprocess.run(["wlrctl", "toplevel", "focus", f"app_id:{APP_ID}"], capture_output=True, check=False)
    except OSError:
        pass
    try:
        Gtk.main()
    finally:
        if pad:
            pad.terminate()
    if vault.installed:   # have the menu notice the new games
        run_command(settings.refresh, settings)
    return 0


# --- the commands -------------------------------------------------------------------

def main(argv: list[str]) -> int:
    home = None
    if argv[:1] == ["--home"] and len(argv) > 1:
        home, argv = argv[1], argv[2:]
    settings = Settings(home)
    action, rest = (argv[0] if argv else "open"), argv[1:]

    def setting(key: str, current: str) -> int:
        if rest:
            settings.data[key] = rest[0]
            settings.save()
        print(rest[0] if rest else current)
        return 0

    if action == "open":
        return ui(settings)
    if action == "pages":
        for page in settings.pages:
            print(f"{page['name']}\t{page['url']}")
    elif action == "add" and len(rest) == 2:
        settings.add_page(rest[0], rest[1])
        settings.save()
    elif action == "remove" and len(rest) == 1:
        if not settings.remove_page(rest[0]):
            print(f"vault: no page called '{rest[0]}'", file=sys.stderr)
            return 1
        settings.save()
    elif action == "command":
        return setting("command", settings.command)
    elif action == "refresh":
        return setting("refresh", settings.refresh)
    elif action == "downloads":
        return setting("downloads", str(settings.downloads))
    elif action == "reset":
        for key in ("command", "refresh", "downloads"):
            settings.data.pop(key, None)
        settings.save()
    elif action == "show":
        print(f"settings   {settings.file}")
        print(f"downloads  {settings.downloads}")
        print(f"command    {settings.command}")
        print(f"refresh    {settings.refresh}")
        for page in settings.pages:
            print(f"page       {page['name']}  {page['url']}")
    else:
        print(__doc__, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
