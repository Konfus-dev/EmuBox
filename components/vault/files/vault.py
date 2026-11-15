#!/usr/bin/env python3
"""Vault: your own list of store pages, browsed with the controller.

    vault                         open Vault (what the Store tile does)
    vault go https://...          open straight on one address, as a store of its own (no page list)
    vault pages                   list the pages
    vault add "Name" https://...  add a page, or change the address of one with that name
    vault rename "Name" "New"     give a page another name
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

The pages are shown by the console's web view (webview.py), which brings the
controller navigation; a keyboard and mouse work just as well.
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
# The console tools: beside this file on Batocera, in the console component in the repository.
sys.path[:0] = [str(HERE), str(HERE.parents[1] / "console" / "files" / "lib")]

import space  # noqa: E402  (how full the drive is)

DEFAULT_HOME = "/userdata/system/vault"
GAMES = os.environ.get("VAULT_GAMES", "/userdata/roms")   # the variable is for trying Vault on a PC
ES_SYSTEMS = ("/userdata/system/configs/emulationstation/es_systems.cfg",
              "/usr/share/emulationstation/es_systems.cfg")
DEFAULT_COMMAND = 'mv -n -- "$VAULT_FILE" "$VAULT_GAMES/$VAULT_SYSTEM/"'
DEFAULT_REFRESH = "curl -s -m 10 http://127.0.0.1:1234/reloadgames"
DEFAULT_PAGES: list[dict] = []    # yours to fill: vault add "Name" https://address
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

    def rename_page(self, name: str, new: str) -> bool:
        pages = [dict(p) for p in self.pages]
        found = [p for p in pages if p["name"].lower() == name.lower()]
        for page in found:
            page["name"] = new
        self.data["pages"] = pages
        return bool(found)

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
        self.finished: set[str] = set()    # names we downloaded ourselves and know are complete
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
            if name in self.finished:
                done.append(path)
                continue
            stat = path.stat()
            before = self.seen.get(name)
            if not before or before[:2] != (stat.st_size, stat.st_mtime):
                self.seen[name] = (stat.st_size, stat.st_mtime, now)
            elif now - before[2] >= SETTLE_S:
                done.append(path)
        return done


def move_problem(file: Path, folder: Path) -> str:
    """Why the file cannot go to the folder, or "". Moving within one drive needs no room."""
    try:
        if not file.is_file():
            return f"{file.name} is no longer in downloads"
        if file.stat().st_dev == folder.stat().st_dev:
            return ""
        return space.no_room(file.stat().st_size, folder, file.name)
    except OSError as error:
        return f"Cannot reach {folder}: {error.strerror}"


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

PROMPTS = {
    "pages": (("A", "Open"), ("B", "Leave Vault")),
    "systems": (("A", "Install here"), ("LB RB", "Jump"), ("B", "Not now")),
}
VISIBLE_ROWS = 11
APP_ID = "emubox-vault"


def ui(settings: Settings, direct: str = "") -> int:
    """The screen. With `direct`, it opens on that address and leaving the page leaves Vault."""
    import webview   # the console's web view; needs Batocera's GTK and WebKit
    from webview import Gdk, GLib, Gtk, Pango, label

    webview.name_window(APP_ID)
    webview.use_style()

    class Vault(Gtk.Window):
        def __init__(self):
            super().__init__(title="Vault")
            self.mode = "pages"
            self.before_asking = "pages"       # where to return after "which system?"
            self.cursor = {"pages": 0, "systems": 0}
            self.asking: Path | None = None    # the download we are asking about
            self.choices: list[dict] = []
            self.likely = 0
            self.installed = 0
            self.progress: dict[str, float] = {}
            settings.downloads.mkdir(parents=True, exist_ok=True)
            self.watcher = Watcher(settings.downloads)

            page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            self.stack = Gtk.Stack()
            page.pack_start(self.stack, True, True, 0)
            self.prompts = webview.Prompts()
            self.say = self.prompts.say
            page.pack_end(self.prompts, False, False, 0)

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

            # The web view is made when the first page is opened: loading the engine takes a
            # moment, and until then there is this to look at.
            self.browser = None
            self.opening = webview.Opening()
            self.stack.add_named(self.opening, "opening")
            self.add(page)

            self.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)
            self.connect("key-press-event", self._on_key)
            self.connect("button-press-event", self._on_click)
            self.connect("realize", lambda *_: self._start())
            GLib.timeout_add(1000, self._look_for_downloads)

        # --- drawing --------------------------------------------------------------

        def _show(self, mode: str) -> None:
            self.mode = mode
            self.stack.set_visible_child_name(mode if mode in ("web", "opening") else "list")
            self.prompts.show_buttons(webview.WEB_PROMPTS if mode == "web" else PROMPTS.get(mode, ()))
            window = self.get_window()
            if window:   # no stray pointer over the lists
                window.set_cursor(None if mode == "web" else Gdk.Cursor.new_for_display(
                    window.get_display(), Gdk.CursorType.BLANK_CURSOR))
            if mode == "web":
                self.browser.view.grab_focus()
            elif mode != "opening":
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
                self.count.set_text(space.summary(settings.downloads))
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
            self.count.set_text(f"{cursor + 1} of {len(items)}      {space.summary(settings.downloads)}")
            self.rows.show_all()

        def _draw_downloading(self) -> None:
            self.prompts.rest("   ".join(
                f"Downloading {name} {done * 100:.0f}%" for name, done in self.progress.items()))

        # --- downloads ----------------------------------------------------------------

        def _on_download(self, download) -> None:
            state = {"name": None}

            def destination(_download, suggested: str) -> bool:
                path = free_name(settings.downloads, self.browser.download_name(download, suggested))
                response = download.get_response()
                problem = space.no_room(response.get_content_length() if response else 0, settings.downloads, path.name)
                if problem:   # refuse now rather than fill the drive and fail half way
                    state["refused"] = True
                    download.cancel()
                    self.say(problem, 15)
                    return True
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
                name, state["name"] = state["name"], None
                if name:   # no half file left behind to be asked about
                    self.progress.pop(name, None)
                    self.watcher.writing.discard(name)
                    try:
                        (settings.downloads / name).unlink()
                    except OSError:
                        pass
                    self._draw_downloading()
                if state.get("refused"):
                    return   # we stopped it ourselves and have said why
                total, free = space.usage(settings.downloads)
                if total and free <= space.RESERVE:
                    self.say(f"Download stopped: the drive is full ({space.size(free)} free). "
                             f"Remove some games to make room for {name or 'it'}.", 15)
                else:
                    self.say(f"Download failed: {name or ''} {error.message}".strip())

            def finished(_download) -> None:
                name = state["name"]
                if name:
                    self.progress.pop(name, None)
                    self.watcher.writing.discard(name)
                    self.watcher.finished.add(name)   # ours and complete: ask without the settling wait
                    self._draw_downloading()
                    self._look_for_downloads()

            download.connect("decide-destination", destination)
            download.connect("received-data", received)
            download.connect("failed", failed)
            download.connect("finished", finished)

        def _look_for_downloads(self) -> bool:
            """Anything finished in the downloads folder? Ask where it goes, one file at a time."""
            if self.mode not in ("systems", "opening"):
                waiting = self.watcher.ready()
                if waiting:
                    self._ask(waiting[0])
            return True

        def _ask(self, path: Path) -> None:
            self.choices, self.likely = likely_first(systems(), path.name)
            if not self.choices:
                self.watcher.left.add(path.name)
                self.say(f"No system folders found in {GAMES}; {path.name} stays in downloads")
                return
            self.asking = path
            self.cursor["systems"] = 0
            self.before_asking = self.mode
            self._show("systems")

        def _install(self, system: dict) -> None:
            path = self.asking
            problem = move_problem(path, Path(GAMES) / system["folder"])
            if problem:   # stays in downloads; asked about again next time
                self.say(problem, 15)
                self.watcher.left.add(path.name)
                self._done_asking()
                return
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

        def _start(self) -> None:
            if direct:
                self._open(direct.split("://", 1)[-1].split("/", 1)[0], direct)
            else:
                self._show("pages")

        def _open(self, name: str, address: str) -> None:
            """Show the page; the first time, "Opening..." while the web engine loads."""
            def go() -> bool:
                if self.browser is None:
                    self.browser = webview.Browser(
                        settings.home / "web", on_leave=self._to_pages,
                        on_home=None if direct else self._to_pages,   # Y: the store's first page
                        on_download=self._on_download, say=self.say)
                    self.stack.add_named(self.browser, "web")
                    self.browser.show_all()
                self._show("web")
                self.browser.open(address)
                return False

            if self.browser is None:
                self.opening.set_name_shown(name)
                self._show("opening")
                GLib.timeout_add(150, go)   # after "Opening..." has been drawn
            else:
                go()

        def _to_pages(self) -> None:
            if self.browser:
                self.browser.blank()
            if direct:
                self.close()
            else:
                self._show("pages")

        def _choose(self) -> None:
            items = self._items()
            if not items:
                return
            item = items[self.cursor[self.mode]]
            if self.mode == "pages":
                self._open(item["name"], item["url"])
            else:
                self._install(item)

        def _on_click(self, _window, event) -> bool:
            if self.mode == "web":
                return False
            if event.type == Gdk.EventType.BUTTON_PRESS and event.button == 1:
                self._choose()   # a click chooses, wherever the hidden pointer happens to be
            return True

        def _on_key(self, _window, event) -> bool:
            key = Gdk.keyval_name(event.keyval) or ""
            alt = bool(event.state & Gdk.ModifierType.MOD1_MASK)
            if event.state & Gdk.ModifierType.CONTROL_MASK and key.lower() == "q":
                self.close()
                return True
            if self.mode == "web":
                return self.browser.key(event)
            if self.mode == "opening":
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
                elif self.asking:   # not now: the file stays in downloads and is asked about next time
                    self.watcher.left.add(self.asking.name)
                    self.say(f"{self.asking.name} left in downloads")
                    self._done_asking()
            return True

    vault = Vault()
    webview.run(vault, APP_ID)
    if vault.installed:   # have the menu notice the new games, and how much room is left
        space.draw_indicator()
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
    if action == "go" and len(rest) == 1:
        return ui(settings, rest[0])
    if action == "pages":
        for page in settings.pages:
            print(f"{page['name']}\t{page['url']}")
    elif action == "add" and len(rest) == 2:
        settings.add_page(rest[0], rest[1])
        settings.save()
    elif action == "rename" and len(rest) == 2:
        if not settings.rename_page(rest[0], rest[1]):
            print(f"vault: no page called '{rest[0]}'", file=sys.stderr)
            return 1
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
