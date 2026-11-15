#!/usr/bin/env python3
"""Drive Vault and the web view from start to finish against a pretend shop, with no screen.

    tools/dev/headless python3 tools/dev/webcheck.py

Checks, in a temporary folder: the "Opening" screen comes first, the d-pad moves between
links, A presses, a text box keeps the arrows, adverts are kept out, a download is asked
about straight away and moved into the chosen system, a file dropped into downloads is
noticed too, and the refresh runs on leaving. Needs GTK 3 and WebKitGTK 4.1 on this PC.
"""
import http.server
import importlib.util
import os
import sys
import tempfile
import threading
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "components/console/files/lib"))
WORK = Path(tempfile.mkdtemp(prefix="webcheck-"))
for folder in ("roms/psx", "roms/gba", "roms/snes", "home", "web"):
    (WORK / folder).mkdir(parents=True)
(WORK / "es.cfg").write_text(
    "<systemList><system><name>psx</name><fullname>PlayStation</fullname><extension>.cue .chd</extension></system>"
    "<system><name>gba</name><fullname>Game Boy Advance</fullname><extension>.gba</extension></system></systemList>")
(WORK / "web/adblock.txt").write_text("localhost\n")   # the page is 127.0.0.1, so localhost is "another site"
os.environ["VAULT_GAMES"] = str(WORK / "roms")
os.environ["EMUBOX_SETTINGS"] = str(WORK / "settings.conf")

HITS: list[str] = []
PAGE = """<!doctype html><title>Test Shop</title><body style="font:20px sans-serif">
<h1>Shop</h1>
<p><a id=a1 href="#1">One</a> &nbsp; <a id=a2 href="#2">Two</a> &nbsp; <a id=a3 href="#3">Three</a></p>
<p><a id=b1 href="#4">Four</a> <span style="display:inline-block;width:90px"></span><span id=b2
 onclick="document.title='clicked five'" style="display:inline-block">Five</span></p>
<p><input id=q placeholder="search"></p>
<p><a id=dl href="/file">Download</a></p>
<script src="http://localhost:PORT/ad.js"></script><script src="/ok.js"></script>
<div style="height:3000px"></div><a id=far href="#far">Far away</a></body>"""


class Shop(http.server.BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def do_GET(self):
        HITS.append(self.path)
        kind, extra = "text/html", []
        if self.path == "/file":
            body, kind = b"x" * 300000, "application/octet-stream"
            extra = [("Content-Disposition", 'attachment; filename="My Game (USA).chd"')]
        elif self.path.endswith(".js"):
            body, kind = b"", "text/javascript"
        else:
            body = PAGE.replace("PORT", str(self.server.server_port)).encode()
        self.send_response(200)
        for name, value in [("Content-Type", kind), ("Content-Length", str(len(body)))] + extra:
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)


server = http.server.ThreadingHTTPServer(("0.0.0.0", 0), Shop)
threading.Thread(target=server.serve_forever, daemon=True).start()
SHOP = f"http://127.0.0.1:{server.server_port}/"

spec = importlib.util.spec_from_file_location("vault", REPO / "components/vault/files/vault.py")
vault = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vault)
vault.systems.__defaults__ = (vault.GAMES, (str(WORK / "es.cfg"),))
settings = vault.Settings(WORK / "home")
settings.data = {"pages": [{"name": "Test Shop", "url": SHOP}, {"name": "Second", "url": "about:blank"}],
                 "refresh": 'touch "$VAULT_DOWNLOADS/../refreshed"'}
settings.save()

import webview  # noqa: E402
from webview import Gdk, GLib, Gtk  # noqa: E402

webview.DATA = str(WORK / "web")
RESULTS: list[tuple[str, bool]] = []


def check(what: str, ok) -> None:
    RESULTS.append((what, bool(ok)))
    print("ok  " if ok else "FAIL", what, flush=True)


PRESS = ("(k=>{document.dispatchEvent(new KeyboardEvent('keydown',{key:k,bubbles:true,cancelable:true}));"
         "const c=document.querySelector('.emubox-nav-focus');return (c?c.id:'none')+'|'+document.title+'|'+Math.round(scrollY)})")


def drive(direct: bool) -> None:
    win = [w for w in Gtk.Window.list_toplevels() if w.get_title() == "Vault" and w.get_visible()][-1]
    steps: list[tuple[int, object]] = []

    def key(name: str, state=0) -> None:
        event = Gdk.Event.new(Gdk.EventType.KEY_PRESS)
        event.keyval, event.state = Gdk.keyval_from_name(name), state
        win._on_key(win, event)

    def js(code: str, then) -> None:
        def done(view, result):
            try:
                then(view.evaluate_javascript_finish(result).to_string())
            except Exception as error:   # noqa: BLE001
                then(f"ERR {error}")
        win.browser.view.evaluate_javascript(code, -1, None, None, None, done)

    def step(delay: int, action) -> None:
        steps.append((delay, action))

    def nav(arrow: str, expect: str, what: str) -> None:
        step(250, lambda: js(PRESS + f"('{arrow}')", lambda r: check(f"{what}: {r}", r.split("|")[0] == expect)))

    def run_next() -> bool:
        if not steps:
            return False
        delay, action = steps.pop(0)

        def go() -> bool:
            try:
                action()
            except Exception as error:   # noqa: BLE001
                check(f"step crashed: {error!r}", False)
            run_next()
            return False
        GLib.timeout_add(delay, go)
        return False

    if direct:
        step(60, lambda: check("a store of its own shows Opening first", win.mode == "opening"))
        step(3500, lambda: check("then its page", win.mode == "web" and win.browser.view.get_title() == "Test Shop"))
        step(100, lambda: key("Escape"))
        step(6000, lambda: (check("B on the first page leaves", False), Gtk.main_quit()))
    else:
        def start():
            check("starts on the page list, at once", win.mode == "pages" and win.browser is None)
            key("Down")
            check("down moves", win.cursor["pages"] == 1)
            key("Up")
            key("Return")
            check("A shows Opening while the engine loads", win.mode == "opening")
        step(400, start)
        step(3500, lambda: check("page loaded", win.mode == "web" and win.browser.view.get_title() == "Test Shop"))
        step(100, lambda: check(f"adverts kept out, the page's own script loaded: {sorted(set(HITS))}",
                                "/ok.js" in HITS and "/ad.js" not in HITS))
        nav("ArrowDown", "a1", "first press highlights the first link")
        nav("ArrowRight", "a2", "right")
        nav("ArrowRight", "a3", "right again")
        nav("ArrowDown", "b2", "down goes to the nearest below")
        step(250, lambda: js(PRESS + "('Enter')", lambda r: check(f"A presses a plain clickable: {r}", "clicked five" in r)))
        nav("ArrowLeft", "b1", "left keeps to the row")
        nav("ArrowDown", "q", "down into the text box")
        step(400, lambda: check("the view knows a text box has the focus", win.browser.editing))
        nav("ArrowLeft", "q", "left stays in the text box")
        step(250, lambda: js(PRESS + "('Escape')", lambda r: None))
        step(400, lambda: check("B leaves the text box", not win.browser.editing))
        nav("ArrowDown", "dl", "down to the download link")
        step(250, lambda: js(PRESS + "('ArrowDown')", lambda r: check(f"nothing near below: {r}", r.startswith("dl|"))))
        step(600, lambda: js("Math.round(scrollY)", lambda r: check(f"so the page scrolls ({r})", int(r) > 100)))
        step(250, lambda: js("document.getElementById('dl').click(); 1", lambda r: None))

        def asked():
            check(f"asked right away: {win.mode} {win.asking and win.asking.name}",
                  win.mode == "systems" and win.asking.name == "My Game (USA).chd")
            check("the system that plays .chd is first", win.choices[0]["folder"] == "psx" and win.likely == 1)
            key("Return")
            check("moved into roms/psx", (WORK / "roms/psx/My Game (USA).chd").stat().st_size == 300000)
            check("downloads is empty again", not list((WORK / "home/downloads").iterdir()))
            check("back in the page", win.mode == "web")
            (WORK / "home/downloads/dropped.gba").write_text("x")
        step(2500, asked)

        def dropped():
            check("a dropped file is noticed too", win.mode == "systems" and win.asking.name == "dropped.gba"
                  and win.choices[0]["folder"] == "gba")
            key("Escape")
            check("B = not now, the file stays", win.mode == "web" and (WORK / "home/downloads/dropped.gba").exists())
        step(4500, dropped)

        def end():
            check("not asked again this time", win.mode == "web")
            key("Home", Gdk.ModifierType.MOD1_MASK)
            check("Y goes to the pages", win.mode == "pages")
            key("Escape")
        step(2500, end)
    run_next()
    REAL_MAIN()


REAL_MAIN = Gtk.main
Gtk.main = lambda: drive(False)
vault.ui(settings)
check("the refresh ran on leaving", (WORK / "home/refreshed").exists())
(WORK / "home/downloads/dropped.gba").unlink()   # or the next start would, rightly, ask about it again
Gtk.main = lambda: drive(True)
vault.ui(settings, SHOP)
check("and it left by itself", True)
bad = [what for what, ok in RESULTS if not ok]
print(f"RESULT {len(RESULTS)} checks:", "all passed" if not bad else f"FAILED {bad}")
sys.exit(1 if bad else 0)
