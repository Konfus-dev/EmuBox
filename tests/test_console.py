"""Console tool tests: the in-game menu's Apps tab.

    python3 -m unittest discover tests
"""
import importlib.util
import json
import re
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from unittest import mock
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "components/console/files/lib"))
import appstore  # noqa: E402
import audio  # noqa: E402
import guide  # noqa: E402
import menusounds  # noqa: E402
import music  # noqa: E402
import startmenu  # noqa: E402
import settings  # noqa: E402

APPS = [
    ("apple-music", {"name": "Apple Music", "player": True}),
    ("discord", {"name": "Discord", "voice": True}),
    ("heroic", {"name": "Heroic", "menu": False}),
]


class GuideTests(unittest.TestCase):
    def setUp(self):
        self.tabs, self.bars = guide.layout(APPS, lights=True)
        self.model = guide.Model(self.tabs, self.bars)
        self.tabs[0].shown = False                        # no game running
        for bar in self.bars:
            bar.shown = False                             # no call, no music
        self.model.open_on("Settings")

    def test_the_tabs_and_what_is_in_them(self):
        self.assertEqual([t.title for t in self.tabs], ["Running", "Settings", "Apps", "Capture"])
        settings = {row.label: row.controls for row in self.tabs[1].rows}
        self.assertEqual(list(settings), ["Sound", "Volume", "Mute", "Sound output", "Menu music", "Menu sounds", "Menu sound volume", "Bluetooth", "Adapter", "Controllers", "Pair a controller",
                                          "RGB Hub", "Follow the game", "PC lights", "Keyboard lights", "PC brightness",
                                          "Keyboard brightness", "Default look",
                                          "System", "Power", "Plane mode", "Stuck emulator?", "Everything else"])
        self.assertEqual(settings["Everything else"][0].do, "hotkeygen --send menu")      # Batocera's main menu
        apps = [(row.label, [c.label for c in row.controls]) for row in self.tabs[2].rows]
        self.assertEqual(apps, [("Apps", []), ("Apple Music", ["Open"]), ("Discord", ["Open"]),      # no Close, no Heroic
                                ("Return", []), ("Hide apps", ["Go back"])])
        self.assertTrue(self.tabs[2].rows[1].controls[0].do.endswith(" detach launch apple-music"))
        with_tools = guide.layout(APPS + [("terminal", {"name": "Terminal", "command": ["xterm"]})], lights=False)[0][2].rows
        self.assertEqual([row.label for row in with_tools], ["Apps", "Apple Music", "Discord", "Tools", "Terminal", "Return", "Hide apps"])
        self.assertFalse(with_tools[3].focusable)                                         # the highlight passes over a heading
        self.assertEqual([t.title for t in guide.layout(APPS, lights=False)[0]], ["Running", "Settings", "Apps", "Capture"])
        self.assertTrue(settings["Default look"][0].confirm)
        self.assertTrue(settings["Default look"][0].do.endswith("/startmenu_rgbhub.py default save"))
        self.assertTrue(settings["Keyboard lights"][0].on.endswith("/startmenu_rgbhub.py set device-enabled keyboard on"))
        self.assertTrue(settings["PC brightness"][0].more.endswith("/startmenu_rgbhub.py step device-brightness pc +10"))
        self.assertNotIn("RGB Hub", [row.label for row in guide.layout(APPS, lights=False)[0][1].rows])
        volumes = [row.label for tab in self.tabs for row in tab.rows if "Volume" == row.label]
        self.assertEqual(volumes, ["Volume"])                                              # the system volume, once

    def test_each_busy_app_gets_a_bar_with_its_controls(self):
        self.assertEqual([bar.label for bar in self.bars], ["Apple Music", "Discord", "Menu music"])
        music, call, menu_music = self.bars
        self.assertEqual([c.do.split()[-1] for c in menu_music.controls if c.kind == "button"], ["previous", "toggle", "next"])
        self.assertEqual([c.label for c in music.controls if c.kind == "button"], ["<", "||", ">"])
        self.assertEqual([c.kind for c in call.controls], ["text", "text", "switch"])
        self.assertIn("status music", music.when)
        self.assertIn("status call", call.when)

    def test_moving_pressing_and_changing_values(self):
        model = self.model
        self.assertEqual(model.shown_tabs()[model.tab].title, "Settings")
        self.assertEqual((model.press("right"), model.ran), ("ran", ["batocera-audio setSystemVolume +5"]))   # a value: left/right
        model.press("down")
        mute = model.current()
        self.assertEqual((model.press("a"), model.ran, mute.value), ("ran", ["batocera-audio setSystemVolume mute"], "true"))
        self.assertEqual((model.press("a"), model.ran), ("ran", ["batocera-audio setSystemVolume unmute"]))
        model.press("up"); model.press("up")                                   # wraps to the last row
        self.assertEqual(model.current().label, "Open full settings")
        self.assertEqual((model.press("a"), model.ran), ("close", ["hotkeygen --send menu"]))
        model.press("up")
        self.assertEqual(model.current().label, "Stop it")
        self.assertEqual((model.press("a"), model.ran), ("moved", []))         # asks first
        self.assertEqual((model.press("a"), model.ran), ("ran", ["curl -s http://127.0.0.1:1234/emukill"]))
        self.assertEqual(model.press("a"), "moved")                            # and asks again next time
        self.assertEqual(model.press("rb"), "moved")
        self.assertEqual((model.page().title, model.current().label), ("Apps", "Open"))
        self.assertEqual(model.press("b"), "close")

    def test_the_bars_are_reachable_only_while_they_show(self):
        model = self.model
        model.press("rb")                                                       # Apps: 3 rows
        self.assertEqual(len(model.rows()), 3)
        self.bars[0].shown = True                                               # music starts
        self.assertEqual(len(model.rows()), 4)
        for _ in range(3):
            model.press("down")
        self.assertEqual(model.current().label, "<")
        model.press("right"); model.press("right"); model.press("right")        # stops at the last button
        self.assertEqual((model.current().label, model.press("a"), model.ran[0].split()[-1]), (">", "ran", "Next"))
        self.bars[0].shown = False                                              # music stops: the highlight falls back
        self.assertIsNotNone(model.current())
        self.assertEqual(len(model.rows()), 3)

    def test_the_game_tab_comes_first_while_a_game_runs(self):
        self.tabs[0].shown = True
        self.model.open_on("Running")
        self.assertEqual([c.label for c in self.model.controls()], ["Resume", "Settings", "Quit", "Force close"])
        self.assertEqual(self.model.controls()[1].do, "hotkeygen --send menu")       # the emulator's own quick settings
        self.model.press("right"); self.model.press("right")
        self.assertEqual(self.model.press("a"), "moved")                        # quitting asks first
        self.assertEqual((self.model.press("a"), self.model.ran), ("close", ["hotkeygen --send exit"]))
        hidden = [row.label for row in self.tabs[1].rows if row.when]
        self.assertEqual(hidden, ["Everything else"])                           # full settings only from the menus

    def test_every_label_is_plain(self):
        for row in [r for t in self.tabs for r in t.rows] + self.bars:
            self.assertTrue(row.label.isascii() and all(c.label.isascii() for c in row.controls), row.label)


class GuideButtonTests(unittest.TestCase):
    """Regression: the Guide opened as the button went down, then Batocera's hotkeys said
    "toggle" as it was let go, and the menu closed again at once (it never seemed to open)."""

    def setUp(self):
        self.now = [100.0]
        self.button = guide.GuideButton(clock=lambda: self.now[0])

    def later(self, seconds: float) -> None:
        self.now[0] += seconds

    def press_and_let_go(self, listened: bool = True, heard_twice: bool = False) -> bool:
        """One press of Guide as the menu hears it; whether it is showing a while afterwards."""
        button = self.button
        if listened and button.showing:                    # pressed inside the open menu: it closes
            button.closed_by_press()
            button.changed(False)
        elif listened and button.went_down() and button.asked_to_show():
            button.changed(True)
        self.later(1.0)                                    # held a moment, let go: Batocera's hotkeys say "toggle"
        for _ in range(2 if heard_twice else 1):
            what = button.toggle()
            if what:
                button.changed(what == "show")
            self.later(0.05)
        self.later(3)
        return button.showing

    def test_a_press_and_its_let_go_leave_the_menu_open(self):
        self.assertTrue(self.press_and_let_go())
        self.assertFalse(self.press_and_let_go())          # the next press closes it, and it stays closed
        self.assertTrue(self.press_and_let_go())

    def test_a_controller_heard_only_on_the_let_go_still_opens_and_closes_it(self):
        self.assertTrue(self.press_and_let_go(listened=False, heard_twice=True))   # one press, two devices
        self.assertFalse(self.press_and_let_go(listened=False))

    def test_an_apps_pad_mapper_asking_for_the_menu_keeps_it_open(self):
        self.assertTrue(self.button.asked_to_show())
        self.button.changed(True)
        self.later(1.0)
        self.assertEqual(self.button.toggle(), "")         # that press being let go
        self.assertFalse(self.button.asked_to_show())      # already open: nothing to do


class MenuLabelGuards(unittest.TestCase):
    """Regressions: an empty label made Batocera reject its whole menu file; a non-ASCII letter
    crashed the menu program started without a language; a second footer (or a fourth thing in
    it) made the menu wider than the screen."""

    def layouts(self):
        for found, lights in ((APPS, True), (guide.apps(REPO / "apps"), True), ([], False)):
            yield guide.layout(found, lights=lights)

    def test_every_tab_row_and_button_has_plain_words(self):
        for tabs, bars in self.layouts():
            for tab in tabs:
                self.assertTrue(tab.title.strip() and tab.title.isascii(), tab.title)
            for row in [r for t in tabs for r in t.rows] + bars:
                self.assertTrue(row.label.isascii(), row.label)
                self.assertTrue(row.label.strip() or row.controls, "a row with neither words nor controls")
                for control in row.controls:
                    self.assertTrue(control.label.isascii(), control.label)
                    if control.kind == "button":
                        self.assertTrue(control.label.strip(), f"a button without words in {row.label}")

    def test_one_footer_and_bars_that_fit_across_the_screen(self):
        for _tabs, bars in self.layouts():
            for bar in bars:
                self.assertLessEqual(len([c for c in bar.controls if c.kind == "button"]), 3, bar.label)
                self.assertLessEqual(len(bar.controls), 4, bar.label)
        source = (REPO / "components/console/files/lib/guide.py").read_text()
        self.assertEqual(source.count('add_class("foot")'), 1)          # one footer, never a second block

    def test_batoceras_menu_file_takes_only_plain_complete_settings(self):
        hub = importlib.util.spec_from_file_location("startmenu_rgbhub", REPO / "components/rgb-hub/files/startmenu_rgbhub.py")
        module = importlib.util.module_from_spec(hub)
        hub.loader.exec_module(module)
        broken = [("global.empty", startmenu.feature("global.empty", "", "X", "words")),
                  ("global.accent", startmenu.feature("global.accent", "Série", "X", "words")),
                  ("global.nochoice", startmenu.feature("global.nochoice", "Pick", "X", "words", "list", [("", "1")])),
                  ("global.broken", "<feature name=")]
        with mock.patch("sys.stderr"):
            text = startmenu.build(["Série", "日本", "", "Xbox 360"], module.features() + broken)
        root = ET.fromstring(text)
        names = [f.get("value") for f in root.iter("feature")]
        self.assertTrue(names)
        for name, _xml in broken:
            self.assertNotIn(name, names)
            self.assertNotIn(name, [f.get("value") for f in root.iter("sharedFeature")])
        for element in list(root.iter("feature")) + list(root.iter("choice")):
            for words in (element.get("name", ""), element.get("description", "-")):
                self.assertTrue(words.strip() and words.isascii(), ET.tostring(element)[:80])   # what the menu shows
        self.assertNotIn('role="footer"', text)
        for name, _xml in module.features():
            self.assertIn(name, names)                                  # the add-on's own settings all made it


class GuideReadingBudget(unittest.TestCase):
    """Regression: every opening of the Guide started some forty programs (python, bash, jq read
    off a USB drive each time) and took about three seconds."""

    def test_one_reading_of_the_settings_tab_starts_few_programs(self):
        started = []

        def run(command, *_args, **_kwargs):
            started.append(command)
            return subprocess.CompletedProcess(command, 0, "", "")

        def popen(command, *_args, **_kwargs):
            started.append(command)
            raise OSError("not in a test")

        with mock.patch.object(subprocess, "run", run), mock.patch.object(subprocess, "Popen", popen), \
                mock.patch.object(subprocess, "check_output", lambda command, *a, **k: started.append(command) or ""), \
                mock.patch("urllib.request.urlopen", side_effect=OSError("no Batocera here")):
            model = guide.Model(*guide.layout(guide.apps(REPO / "apps"), lights=True))
            guide.refresh(model)                      # which tabs show
            model.open_on("Settings")
            started.clear()
            guide.refresh(model)
            self.assertEqual(model.page().title, "Settings")
            self.assertLessEqual(len(started), 12, started)
            started.clear()
            guide.refresh(model, everything=True)    # the first reading, of every tab
            self.assertLessEqual(len(started), 20, started)


class AppStoreTests(unittest.TestCase):
    def test_the_list_of_apps_is_complete_and_plain(self):
        apps, pads = appstore.catalogue()
        self.assertGreaterEqual(len(apps), 6)
        for app in apps:
            self.assertTrue(app["id"] and app["name"] and app["about"], app)
            self.assertTrue(bool(app.get("web")) != bool(app.get("flatpak")), app["id"])     # one kind or the other
            if app.get("pad"):
                self.assertIn(app["pad"], pads)
            if app.get("flatpak"):
                self.assertTrue(app.get("window"), app["id"])                                # the pad mapper needs to find it

    def test_adding_an_app_makes_its_folder_and_its_tile_and_removing_takes_them_away(self):
        apps, pads = appstore.catalogue()
        by_id = {app["id"]: app for app in apps}
        font = REPO / "components/look/files/theme/art/fonts/Michroma-Regular.ttf"
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            appstore.add(by_id["youtube"], pads, folder / "apps", folder / "tiles", Path("/root-here"), font)
            appstore.add(by_id["netflix"], pads, folder / "apps", folder / "tiles", Path("/root-here"), font)
            self.assertTrue(appstore.is_added(by_id["youtube"], folder / "apps"))
            made = json.loads((folder / "apps/netflix/app.json").read_text())
            self.assertEqual((made["flatpak"], made["pad"]["a"], made["added"]), ("com.google.Chrome", ["KEY_ENTER"], True))
            self.assertIn("bin/emubox-app open youtube --wait", (folder / "tiles/YouTube.sh").read_text())
            self.assertIn("emubox-app open netflix --wait", (folder / "tiles/Netflix.sh").read_text())
            self.assertTrue((folder / "tiles/images/YouTube.png").is_file())
            games = ET.parse(folder / "tiles/gamelist.xml").getroot()
            self.assertEqual(sorted(g.findtext("name") for g in games), ["Netflix", "YouTube"])
            appstore.add(by_id["youtube"], pads, folder / "apps", folder / "tiles", Path("/root-here"), font)   # again: still once
            self.assertEqual(len(ET.parse(folder / "tiles/gamelist.xml").getroot()), 2)
            appstore.remove(by_id["youtube"], folder / "apps", folder / "tiles")
            self.assertFalse(appstore.is_added(by_id["youtube"], folder / "apps"))
            self.assertEqual([g.findtext("name") for g in ET.parse(folder / "tiles/gamelist.xml").getroot()], ["Netflix"])
            self.assertFalse((folder / "tiles/YouTube.sh").exists())
        tabs, _ = guide.layout([("youtube", {"name": "YouTube", "web": "https://www.youtube.com"})], lights=False)
        self.assertTrue(tabs[2].rows[1].controls[0].do.endswith(" detach launch youtube"))
        running = {row.label: [c.label for c in row.controls] for row in tabs[0].rows if row.label}   # and, once open, in Running
        self.assertEqual(running["YouTube"], ["Resume", "Hide", "Force close"])


class GuideReadingTests(unittest.TestCase):
    def test_which_apps_are_open_is_told_without_starting_a_program(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            run, proc = folder / "run/emubox", folder / "proc"
            run.mkdir(parents=True)
            for pid, words in (("10", ["python3", "/x/lib/webview.py", "https://y", "--id", "youtube"]), ("11", ["xterm"]), ("self", ["x"])):
                (proc / pid).mkdir(parents=True)
                (proc / pid / "cmdline").write_bytes(b"\0".join(w.encode() for w in words))
            (run.parent / ".flatpak/123").mkdir(parents=True)
            (run.parent / ".flatpak/123/info").write_text("[Application]\nname=com.discordapp.Discord\n")
            for app in ("discord", "terminal", "apple-music", "files"):
                (run / f"{app}.started").write_text("")
            (run / "terminal.pid").write_text("11\n")
            (run / "files.pid").write_text("999\n")                    # closed since: no such process
            found = [("youtube", {"name": "YouTube", "web": "https://y"}), ("twitch", {"name": "Twitch", "web": "https://t"}),
                     ("discord", {"name": "Discord", "flatpak": "com.discordapp.Discord"}),
                     ("apple-music", {"name": "Apple Music", "flatpak": "com.google.Chrome"}),   # started once, not running now
                     ("terminal", {"name": "Terminal", "command": ["xterm"]}), ("files", {"name": "Files", "command": ["pcmanfm"]})]
            self.assertEqual(guide.open_apps(found, run, proc), ["YouTube", "Discord", "Terminal"])

    def test_only_the_open_tab_is_read_unless_everything_is_asked_for(self):
        asked = []

        def reader(get):
            asked.append(get)
            return "yes"

        tabs = [guide.Tab("One", [guide.Row("a", [guide.text("get-a")])]), guide.Tab("Two", [guide.Row("b", [guide.text("get-b")], when="when-b")])]
        model = guide.Model(tabs, [])
        guide.refresh(model, reader)
        self.assertEqual(sorted(asked), ["get-a", "when-b"])                 # the other tab: only whether its row exists
        asked.clear()
        guide.refresh(model, reader, everything=True)
        self.assertEqual(sorted(asked), ["get-a", "get-b", "when-b"])
        self.assertEqual(tabs[1].rows[0].controls[0].value, "yes")


class HintsAndIconsTests(unittest.TestCase):
    def test_every_app_gets_its_hints_from_its_own_buttons(self):
        import hints
        music_app = json.loads((REPO / "apps/apple-music/app.json").read_text())
        shown = dict(hints.hints(music_app))
        self.assertEqual((shown["dpad"], shown["a"], shown["x"], shown["rb"], shown["select+start"]),
                         ("Move", "Select", "Play/Pause", "Next song", "Quit"))
        self.assertNotIn("start", shown)                                   # the same as X: said once
        self.assertEqual(hints.glyph("select+start"), "SELECT+START")
        self.assertEqual(hints.hints({"pad": {"a": ["KEY_ENTER"]}, "hints": {"a": "Fire", "y": "Jump"}}), [("a", "Fire"), ("y", "Jump")])
        self.assertEqual(hints.hints({"name": "A game launcher"}), [])   # takes the controller itself: no strip
        for file in (REPO / "apps").glob("*/app.json"):                    # nothing the window manager keeps for itself
            for action in (json.loads(file.read_text()).get("pad") or {}).values():
                self.assertNotIn(action, (["KEY_LEFTALT", "KEY_LEFT"], ["KEY_LEFTALT", "KEY_RIGHT"]), file)

    def test_a_tiles_own_icon_comes_from_the_program_or_its_site(self):
        import io
        import tileicon
        from PIL import Image

        def png(size: int) -> bytes:
            data = io.BytesIO()
            Image.new("RGBA", (size, size), "red").save(data, "PNG")
            return data.getvalue()

        self.assertEqual(tileicon.sources({"flatpak": "com.google.Chrome", "args": ["--app=https://music.example/"]}),
                         ("", "https://music.example/"))               # a site in Chrome is the site, not Chrome
        self.assertEqual(tileicon.sources({"flatpak": "com.example.App"}), ("com.example.App", ""))
        page = '<link rel="icon" href="/small.png" sizes="16x16"><link rel="apple-touch-icon" href="big.png">'
        self.assertEqual(tileicon.links(page, "https://music.example/x/"), ["https://music.example/x/big.png", "https://music.example/small.png"])
        asked = []

        def fetch(url, limit=0):
            asked.append(url)
            if url == "https://music.example/":
                return page.encode()
            if url.endswith("big.png"):
                return png(180)
            raise OSError("nothing there")

        self.assertEqual(tileicon.site_icon("https://music.example/", fetch).size, (180, 180))
        self.assertIsNone(tileicon.site_icon("https://other.example/", fetch))     # no icon: the tile keeps its drawing
        with tempfile.TemporaryDirectory() as folder:
            icons = Path(folder) / "exports/share/icons/hicolor/128x128/apps"
            icons.mkdir(parents=True)
            (icons / "com.example.App.png").write_bytes(png(128))
            self.assertEqual(tileicon.flatpak_icon("com.example.App", [Path(folder)]).size, (128, 128))
            font = REPO / "components/look/files/fonts/Michroma-Regular.ttf"
            out = Path(folder) / "tile.png"
            self.assertTrue(tileicon.upgrade({"name": "Example", "flatpak": "com.example.App"}, out, font, [Path(folder)], fetch))
            self.assertEqual(Image.open(out).size, (512, 512))
            self.assertFalse(tileicon.upgrade({"name": "Plain", "command": ["xterm"]}, Path(folder) / "none.png", font, [Path(folder)], fetch))


class PhoneKeyboardTests(unittest.TestCase):
    def test_qr_codes_have_the_right_shape(self):
        import qr
        small = qr.matrix("hi")
        self.assertEqual((len(small), len(small[0])), (21, 21))
        corner = [[small[r][c] for c in range(7)] for r in range(7)]
        ring = lambda r, c: max(abs(r - 3), abs(c - 3)) != 2          # noqa: E731  a finder pattern: dark, light ring, dark
        self.assertEqual(corner, [[ring(r, c) for c in range(7)] for r in range(7)])
        self.assertEqual(len(qr.matrix("http://192.168.1.20:8377/k/abcdefghijkl")), 29)
        self.assertEqual(qr.correction([32, 91, 11, 120, 209, 114, 220, 77, 67, 64, 236, 17, 236, 17, 236, 17], 10),
                         [196, 35, 39, 119, 235, 215, 231, 226, 93, 23])     # the worked example in the QR tutorials
        with self.assertRaises(ValueError):
            qr.matrix("x" * 200)

    def test_the_phone_page_is_only_at_its_one_time_address(self):
        import phonekeys
        import urllib.error
        import urllib.request
        typed, done = [], []
        server = phonekeys.serve("one-time", on_type=lambda text, key: typed.append((text, key)),
                                 on_done=lambda: done.append(True), ports=range(18390, 18399), host="127.0.0.1")
        try:
            base = f"http://127.0.0.1:{server.server_address[1]}"
            self.assertIn(b"EmuBox keyboard", urllib.request.urlopen(base + "/k/one-time").read())
            for path, data in (("/", None), ("/k/other", None), ("/k/other/do", b"{}")):
                with self.assertRaises(urllib.error.HTTPError):
                    urllib.request.urlopen(urllib.request.Request(base + path, data=data))
            for sent in ({"text": "p\u00e4ss word", "key": "enter"}, {"key": "tab"}, {"done": True}):
                urllib.request.urlopen(urllib.request.Request(base + "/k/one-time/do", data=json.dumps(sent).encode()))
            for _ in range(50):
                if done:
                    break
                __import__("time").sleep(0.02)
            self.assertEqual((typed, done), ([("p\u00e4ss word", "enter"), ("", "tab")], [True]))
        finally:
            server.shutdown()
        class Fake:   # what was typed, in order
            def __init__(self):
                self.did = []
            def text(self, words):
                self.did.append(("text", words))
            def key(self, name):
                self.did.append(("key", name))

        fake = Fake()
        phonekeys.typing(fake)("abc", "enter")
        phonekeys.typing(fake)("", "escape")                                       # not one of the page's buttons
        self.assertEqual(fake.did, [("text", "abc"), ("key", "enter")])

    def test_typing_presses_real_keys_and_lets_them_go(self):
        import typer

        class Device:
            def __init__(self):
                self.events = []
            def write(self, kind, code, value):
                self.events.append((code, value))
            def syn(self):
                pass

        try:
            from evdev import ecodes
        except ImportError:
            self.skipTest("python-evdev is not on this PC (it is on Batocera)")
        device = Device()
        typing = typer.Typer(device=device, pause=0)
        typing.text("aB!")
        typing.key("enter")
        a, b, one, shift, enter = ecodes.KEY_A, ecodes.KEY_B, ecodes.KEY_1, ecodes.KEY_LEFTSHIFT, ecodes.KEY_ENTER
        self.assertEqual(device.events, [(a, 1), (a, 0), (shift, 1), (b, 1), (b, 0), (shift, 0),
                                         (shift, 1), (one, 1), (one, 0), (shift, 0), (enter, 1), (enter, 0)])

    def test_what_our_keyboard_has_no_key_for_goes_the_old_way(self):
        import typer
        ran = []
        typing = typer.Typer(own_keyboard=False, run=lambda command, **_: ran.append(command))
        typing.text("é")
        typing.key("tab")
        self.assertEqual(ran, [["wtype", "--", "é"], ["wtype", "-k", "Tab"]])
        with tempfile.TemporaryDirectory() as folder:
            conf = Path(folder) / "batocera.conf"
            conf.write_text("system.kblayout=fr\n")
            self.assertFalse(typer.us_layout(conf))
            conf.write_text("#system.kblayout=fr\nsystem.kblayout=us\n")
            self.assertTrue(typer.us_layout(conf))
            self.assertTrue(typer.us_layout(Path(folder) / "none"))


class StartMenuTests(unittest.TestCase):
    def test_settings_become_entries_in_batoceras_menu(self):
        text = startmenu.build(["EmuBox", "OG Xbox"], [("rgbhub_x", '    <feature name="X" submenu="RGB HUB" value="rgbhub_x" preset="switchon" />')])
        root = ET.fromstring(text)
        features = {f.get("value"): f for f in root.find("sharedFeatures")}
        self.assertEqual([f.get("value") for f in root.find("globalFeatures")], list(features))   # each one is switched on globally
        sound_set = features["emubox_ui_sound_set"]
        self.assertEqual((sound_set.get("submenu"), [c.get("value") for c in sound_set]), ("MENU SOUNDS", ["EmuBox", "OG Xbox"]))
        self.assertEqual([c.get("value") for c in features["emubox_ui_sound_volume"]][:3], ["0", "10", "20"])
        self.assertEqual((features["emubox_web_block_ads"].get("submenu"), features["emubox_web_block_ads"].get("preset")), ("APPS", "switchon"))
        self.assertIn("rgbhub_x", features)

    def test_the_later_change_wins_between_batoceras_menu_and_ours(self):
        with tempfile.TemporaryDirectory() as folder:
            mine, batocera = Path(folder) / "settings.conf", Path(folder) / "batocera.conf"
            batocera.write_text("audio.volume=45\nglobal.emubox_ui_sound_set=OG Xbox\nglobal.emubox_ui_sound_volume=80.000000\n"
                                "global.emubox_ui_sound_back=0\nglobal.emubox_music_quiet_menu=auto\n")
            values = settings.read(mine, batocera)
            self.assertEqual((values["ui.sound_set"], values["ui.sound_volume"], values["ui.sound.back"]), ("OG Xbox", "80", "off"))
            self.assertEqual((values["music.quiet_menu"], values["ui.sound.select"]), ("on", "on"))       # never chosen: defaults
            settings.write("ui.sound_volume", "30", mine, batocera)            # changed in the Guide menu: ours is newer
            self.assertEqual(settings.read(mine, batocera)["ui.sound_volume"], "30")
            self.assertEqual(settings.read(mine, batocera)["ui.sound_set"], "OG Xbox")
            batocera.write_text(batocera.read_text().replace("80.000000", "50.000000"))   # then changed in Batocera's menu
            self.assertEqual(settings.read(mine, batocera)["ui.sound_volume"], "50")
            settings.write("ui.sound_volume", "70", mine, batocera)
            self.assertEqual(settings.read(mine, batocera)["ui.sound_volume"], "70")

    def test_a_change_in_batoceras_menu_is_noticed_and_passed_on(self):
        with tempfile.TemporaryDirectory() as folder:
            conf = Path(folder) / "batocera.conf"
            conf.write_text("global.rgbhub_device_enabled_pc=0\n")
            seen = []
            watch = startmenu.Watch(conf)
            watch.modules = [mock.Mock(changed=seen.append, __name__="fake")]
            with mock.patch.object(startmenu.menusounds, "apply"):
                self.assertTrue(watch.look())
                self.assertFalse(watch.look())                       # nothing changed since
            self.assertEqual(seen, [{"rgbhub_device_enabled_pc": "0"}])


class RgbHubTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        spec = importlib.util.spec_from_file_location("startmenu_rgbhub", REPO / "components/rgb-hub/files/startmenu_rgbhub.py")
        self.hub = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.hub)
        self.hub.HOME = Path(self.folder.name) / "rgb-hub"
        self.hub.FILE = self.hub.HOME / "settings.json"
        self.hub.PICTURES = self.hub.HOME / "pictures"
        self.hub.OLD_HOME = Path(self.folder.name) / "omen-lights"

    def saved(self):
        return json.loads(self.hub.FILE.read_text())

    def test_switches_numbers_and_defaults(self):
        run = self.hub.run
        self.assertEqual((run(["is", "auto-devices", "all"]), run(["get", "lcd-brightness"])), ("true", "80"))
        self.assertEqual((run(["is", "device-enabled", "keyboard"]), run(["get", "device-brightness", "pc"])), ("true", "100"))
        run(["set", "lcd-enabled", "off"])
        run(["step", "lcd-brightness", "+30"])
        self.assertEqual(self.saved(), {"lcd-enabled": False, "lcd-brightness": 100})
        self.assertEqual(run(["is", "lcd-enabled"]), "")

    def test_settings_kept_per_device(self):
        run = self.hub.run
        run(["set", "device-enabled", "keyboard", "off"])
        run(["step", "device-brightness", "pc", "-30"])
        run(["step", "device-brightness", "all", "+10"])
        run(["set", "auto-devices", "pc", "off"])
        saved = self.saved()
        self.assertEqual(saved["device-enabled"], {"IQUNIX-KEYBOARD": False})
        self.assertEqual(saved["device-brightness"], {"OMEN-PC": 80, "IQUNIX-KEYBOARD": 100})
        self.assertEqual(saved["auto-devices"], {"OMEN-PC": False, "IQUNIX-KEYBOARD": True})   # both written: missing is off
        self.assertEqual((run(["is", "device-enabled", "pc"]), run(["is", "device-enabled", "keyboard"])), ("true", ""))
        self.assertEqual((run(["is", "auto-devices", "all"]), run(["is", "auto-devices", "keyboard"])), ("", "true"))
        run(["set", "auto-devices", "all", "on"])
        self.assertEqual(run(["is", "auto-devices", "all"]), "true")
        run(["set", "lights-enabled", "off"])                  # the old names still work: they meant the PC
        self.assertEqual(self.saved()["device-enabled"], {"IQUNIX-KEYBOARD": False, "OMEN-PC": False})
        self.assertEqual(self.hub.main(["set", "device-enabled", "mouse", "on"]), 2)
        self.assertEqual(self.hub.main(["is", "device-enabled"]), 2)

    def test_default_look_is_asked_of_the_lights_program(self):
        self.hub.run(["default", "save"])
        self.assertEqual(self.saved(), {"default-action": "save"})
        self.hub.run(["default", "load"])
        self.assertEqual(self.saved()["default-action"], "load")
        self.assertEqual(self.hub.main(["default", "forget"]), 2)

    def test_colours_effects_speed_and_picture(self):
        run = self.hub.run
        run(["colour", "menus", "Blue"])
        run(["colour", "RAM/Stick 1", "#ff0000"])
        run(["colour", "all", "Green"])
        run(["effect", "all", "Rainbow"])    # the case and the keyboard have no rainbow: only the memory takes it
        run(["effect", "case", "Breathing"])
        run(["effect", "keyboard", "Rain"])
        run(["speed", "100"])
        run(["dim", "min", "25"])
        run(["picture", "/somewhere/dragon.png"])
        saved = self.saved()
        self.assertEqual(saved["auto-idle-colour"], "#1E5BFF")
        self.assertEqual(set(saved["zone-colours"].values()), {"#3CE61E"})
        self.assertEqual(len(saved["zone-colours"]), 7)
        self.assertIn("IQUNIX MG65/All keys", saved["zone-colours"])
        self.assertEqual(saved["device-modes"], {"RAM": "Rainbow", "HP Omen 30L": "Breathing", "IQUNIX MG65": "Rain"})
        self.assertEqual(saved["device-speeds"], {"HP Omen 30L": 100, "RAM": 100, "IQUNIX MG65": 100})
        self.assertEqual(saved["device-min-brightness"]["RAM"], 25)
        self.assertEqual((saved["lcd-image"], saved["auto-idle-image"]), ("/somewhere/dragon.png",) * 2)
        self.assertEqual((run(["colour-of", "menus"]), run(["speed-of"]), run(["picture-of"]), run(["effect-of", "keyboard"])),
                         ("Blue", "Fast", "dragon", "Rain"))
        run(["colour", "menus", "picture"])
        self.assertEqual(run(["colour-of", "menus"]), "From the picture")
        self.assertEqual(self.hub.main(["colour", "all", "mauve-ish"]), 2)
        values = self.saved()
        values["_seen"] = {"rgbhub_x": "1"}
        self.hub.save(values)
        run(["reset"])
        self.assertEqual(self.saved(), {"_seen": {"rgbhub_x": "1"}})          # our own note stays

    def test_until_the_old_folder_is_moved_its_file_is_used(self):
        old = self.hub.OLD_HOME
        old.mkdir()
        (old / "settings.json").write_text('{"lcd-fit": "fit"}')
        self.assertEqual(self.hub.run(["get", "lcd-fit"]), "fit")
        self.hub.run(["set", "device-enabled", "pc", "off"])
        self.assertFalse(self.hub.HOME.exists())                                  # left for the lights program to make
        self.assertEqual(json.loads((old / "settings.json").read_text())["device-enabled"], {"OMEN-PC": False})

    def test_its_settings_join_batoceras_menu(self):
        pairs = self.hub.features()
        root = ET.fromstring("<x>" + "\n".join(xml for _, xml in pairs) + "</x>")
        by_value = {f.get("value"): f for f in root}
        self.assertEqual(list(by_value), [name for name, _ in pairs])
        self.assertTrue(all(f.get("submenu") == "RGB HUB" and f.get("value").startswith("rgbhub_") for f in root))
        labels = [f.get("name") for f in root]
        self.assertEqual(labels[:7], ["FOLLOW THE GAME", "PC FOLLOWS THE GAME", "KEYBOARD FOLLOWS THE GAME", "PC LIGHTS",
                                      "KEYBOARD LIGHTS", "PC LIGHT BRIGHTNESS", "KEYBOARD BRIGHTNESS"])
        self.assertEqual(labels[-3:], ["KEYBOARD COLOUR", "KEYBOARD EFFECT", "DEFAULT LOOK"])
        self.assertEqual(by_value["rgbhub_auto_devices_all"].get("preset"), "switchon")
        self.assertIn("Purple", [c.get("value") for c in by_value["rgbhub_colour_ram_stick_1"]])
        self.assertIn("Purple", [c.get("value") for c in by_value["rgbhub_colour_iqunix_mg65_all_keys"]])
        self.assertEqual([c.get("value") for c in by_value["rgbhub_effect_keyboard"]][:3], ["Static", "Wave", "Colour cloud"])
        self.assertEqual([c.get("value") for c in by_value["rgbhub_default"]], ["none", "save", "load"])

    def test_choices_in_batoceras_menu_reach_the_lights(self):
        changed = self.hub.changed
        changed({"rgbhub_device_enabled_pc": "0", "rgbhub_device_brightness_keyboard": "40.000000",
                 "rgbhub_auto_devices_all": "0", "rgbhub_auto_devices_keyboard": "1", "rgbhub_lcd_brightness": "auto",
                 "rgbhub_colour_menus": "Blue", "rgbhub_colour_iqunix_mg65_all_keys": "Purple", "rgbhub_effect_keyboard": "Wave",
                 "rgbhub_speed": "100", "rgbhub_lcd_fit": "fit", "unrelated": "1",
                 "omen_lights_enabled": "1", "omen_colour_ram_stick_1": "Red"})   # from before the rename: not ours now
        saved = self.saved()
        self.assertEqual((saved["device-enabled"], saved["device-brightness"]), ({"OMEN-PC": False}, {"IQUNIX-KEYBOARD": 40}))
        self.assertEqual(saved["auto-devices"], {"OMEN-PC": False, "IQUNIX-KEYBOARD": True})   # one device's row after "all"
        self.assertNotIn("lcd-brightness", saved)                                # not chosen: left at its default
        self.assertEqual(saved["zone-colours"], {"IQUNIX MG65/All keys": "#9B30FF"})
        self.assertEqual((saved["device-modes"]["IQUNIX MG65"], saved["device-speeds"]["RAM"], saved["lcd-fit"]), ("Wave", 100, "fit"))
        self.assertEqual(saved["auto-idle-colour"], "#1E5BFF")
        self.assertFalse(any(name.startswith("omen_") for name in saved["_seen"]))
        self.hub.run(["set", "device-brightness", "keyboard", "90"])            # then changed in the Guide menu
        changed({"rgbhub_device_brightness_keyboard": "40.000000"})               # Batocera's menu says nothing new
        self.assertEqual(self.saved()["device-brightness"]["IQUNIX-KEYBOARD"], 90)
        changed({"rgbhub_device_brightness_keyboard": "60"})                      # a new choice there wins again
        self.assertEqual(self.saved()["device-brightness"]["IQUNIX-KEYBOARD"], 60)

    def test_default_look_can_be_saved_again_from_batoceras_menu(self):
        def picked(action):
            values = self.saved() if self.hub.FILE.exists() else {}
            values.pop("default-action", None)                                   # the lights program did it and emptied it
            self.hub.save(values)
            self.hub.changed(action)
            return self.saved().get("default-action", "")

        self.assertEqual(picked({"rgbhub_default": "save"}), "save")
        self.assertEqual(picked({"rgbhub_default": "save"}), "")                 # nothing new: once only
        self.assertEqual(picked({"rgbhub_default": "none"}), "")                 # Leave it
        self.assertEqual(picked({"rgbhub_default": "save"}), "save")             # then Save works again
        self.assertEqual(picked({}), "")                                         # AUTO: the choice is gone from batocera.conf
        self.assertEqual(picked({"rgbhub_default": "save"}), "save")
        self.assertEqual(picked({"rgbhub_default": "load"}), "load")


def stream(index, name, corked=False, mute=False, percent=100):
    return {"index": index, "corked": corked, "mute": mute, "volume": {"front-left": {"value_percent": f"{percent}%"}},
            "properties": {"application.name": name}}


class AudioTests(unittest.TestCase):
    ON = {"music.quiet_menu": "on", "call.lower_music": "on", "call.music_volume": "20"}

    def test_the_menu_music_plays_in_the_menus_and_waits_for_yours(self):
        wanted = audio.menu_music_wanted
        self.assertTrue(wanted({}, in_menus=True, yours_playing=False, held=False))
        self.assertFalse(wanted({}, in_menus=False, yours_playing=False, held=False))        # a game is running
        self.assertFalse(wanted({}, in_menus=True, yours_playing=True, held=False))          # Apple Music is playing
        self.assertTrue(wanted({"music.quiet_menu": "off"}, True, True, False))              # unless you want both
        self.assertFalse(wanted({}, True, False, held=True))                                 # paused by hand
        self.assertFalse(wanted({"music.menu": "off"}, True, False, False))
        song = stream(2, "Google Chrome")
        self.assertTrue(audio.music_sounding([stream(1, "EmulationStation"), song], ["chrome"]))
        song["corked"] = True
        self.assertFalse(audio.music_sounding([song], ["chrome"]))

    def test_the_menu_music_player_is_asked_and_answers(self):
        import socket, threading
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "music.sock"
            server = socket.socket(socket.AF_UNIX)
            server.bind(str(path))
            server.listen(4)
            answers = {"pause": False, "media-title": "Bolt Action - Give Me.ogg"}

            def serve():
                for _ in range(2):
                    link, _ = server.accept()
                    asked = json.loads(link.makefile().readline())["command"]
                    link.sendall(b'{"event":"idle"}\n' + json.dumps({"data": answers.get(asked[1]), "error": "success"}).encode() + b"\n")
                    link.close()
            threading.Thread(target=serve, daemon=True).start()
            self.assertEqual(music.ask("get_property", "pause", sock=path), False)
            self.assertEqual(music.title(path), "Bolt Action - Give Me")
            self.assertIsNone(music.ask("get_property", "pause", sock=Path(folder) / "nobody.sock"))   # no player: no answer
            self.assertEqual(music.line(Path(folder) / "nobody.sock"), "")
        self.assertEqual((music.volume('<int name="MusicVolume" value="40" />'), music.volume("")), (40, 65))
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder) / "a.ogg").write_text("x")
            (Path(folder) / "notes.txt").write_text("x")
            self.assertEqual(music.songs((str(Path(folder) / "empty"), folder)), [str(Path(folder) / "a.ogg")])

    def test_music_makes_way_for_a_call_and_returns_to_where_it_was(self):
        state = {}
        song, game, voice = stream(2, "Google Chrome", percent=80), stream(3, "retroarch"), stream(4, "Discord")
        mic = [stream(9, "Discord")]
        ours = stream(5, "EmuBox menu music", percent=65)
        self.assertEqual(audio.plan([song, game, voice, ours], mic, ["chrome"], self.ON, state),
                         [["set-sink-input-volume", "2", "20%"], ["set-sink-input-volume", "5", "20%"]])   # not the game, not the call
        self.assertEqual(audio.plan([song, game, voice], mic, ["chrome"], self.ON, state), [])
        song["volume"]["front-left"]["value_percent"] = "20%"
        self.assertEqual(audio.plan([song, game, voice], mic, ["chrome"], self.ON, state), [])
        self.assertEqual(audio.plan([song, game], [], ["chrome"], self.ON, state), [["set-sink-input-volume", "2", "80%"]])

    def test_switched_off_means_hands_off(self):
        off = {"music.quiet_menu": "off", "call.lower_music": "off"}
        streams = [stream(1, "EmuBox menu music"), stream(2, "Google Chrome")]
        self.assertEqual(audio.plan(streams, [stream(9, "Discord")], ["chrome"], off, {}), [])

    def test_menu_sounds_follow_the_buttons_and_know_when_to_keep_quiet(self):
        self.assertEqual([menusounds.sound_for(code, False) for code in (304, 305, 315, 307)], ["select", "back", "menuopen", ""])
        self.assertEqual([menusounds.sound_for(code, True) for code in (304, 305)], ["back", "select"])
        self.assertEqual([menusounds.sound_for(code, True) for code in (28, 1, 57)], ["select", "back", "menuopen"])   # keyboard
        self.assertTrue(menusounds.should_play("select", {}, in_menus=True))
        self.assertFalse(menusounds.should_play("select", {}, in_menus=False))                 # a game is running
        self.assertFalse(menusounds.should_play("back", {"ui.sound.back": "off"}, True))
        self.assertTrue(menusounds.should_play("select", {"ui.sound.back": "off"}, True))      # each has its own switch

    def test_a_held_direction_is_only_believed_while_the_controller_says_so(self):
        class Info:
            def __init__(self, value, low, high):
                self.value, self.min, self.max = value, low, high

        class Device:   # a controller another program has taken: no events reach us, but it can still be asked
            def __init__(self, keys=(), axes=None):
                self.keys, self.axes = list(keys), axes or {}
            def active_keys(self):
                return self.keys
            def absinfo(self, code):
                return self.axes[code]

        down = menusounds.still_down
        self.assertTrue(down(Device(keys=[545]), "key545"))
        self.assertFalse(down(Device(), "key545"))                                   # let go while we could not hear it
        self.assertEqual((down(Device(axes={17: Info(1, -1, 1)}), "hat17"), down(Device(axes={17: Info(0, -1, 1)}), "hat17")), (True, False))
        self.assertEqual((down(Device(axes={1: Info(30000, -32768, 32767)}), "stick1"), down(Device(axes={1: Info(900, -32768, 32767)}), "stick1")), (True, False))
        self.assertFalse(down(Device(), "hat16"))                                    # unplugged, or cannot be asked: stop

    def test_moving_is_heard_from_the_dpad_the_stick_and_the_arrow_keys(self):
        move = menusounds.direction
        self.assertEqual(move(1, 108, 1), ("key108", True))            # arrow down pressed
        self.assertEqual(move(1, 108, 0), ("key108", False))
        self.assertIsNone(move(1, 108, 2))                              # the keyboard's own repeats are not ours
        self.assertEqual(move(1, 545, 1), ("key545", True))            # a d-pad that is buttons
        self.assertEqual((move(3, 17, -1), move(3, 17, 0)), (("hat17", True), ("hat17", False)))
        self.assertEqual((move(3, 1, 30000, 0, 32768), move(3, 1, 9000, 0, 32768)), (("stick1", True), ("stick1", False)))
        self.assertIsNone(move(1, 304, 1))                              # A is not a direction
        self.assertIsNone(move(3, 3, 30000))                            # nor is the right stick

    def test_sound_sets_volume_and_the_scroll_sound_the_menus_play(self):
        import wave
        with tempfile.TemporaryDirectory() as folder:
            theme, mine = Path(folder) / "themes/emubox/art/sounds", Path(folder) / "mine"
            for where, kinds, level in ((theme, menusounds.KINDS, 1000), (mine / "My Set", ("scroll", "select"), 20000),
                                        (mine / "Empty", (), 0)):
                where.mkdir(parents=True)
                for kind in kinds:
                    with wave.open(str(where / f"{kind}.wav"), "wb") as wav:
                        wav.setnchannels(1), wav.setsampwidth(2), wav.setframerate(8000)
                        wav.writeframes(level.to_bytes(2, "little", signed=True) * 100)
            (theme / "scroll-now.wav").write_bytes((theme / "scroll.wav").read_bytes())
            es = '<config><string name="ThemeSet" value="emubox" /><bool name="InvertButtons" value="true" /></config>'
            themes = (Path(folder) / "themes",)
            self.assertEqual(menusounds.es_setting("InvertButtons", es), "true")
            found = menusounds.sets(es, mine, themes)
            self.assertEqual(list(found), ["EmuBox", "My Set"])            # a folder with no sounds is not a set
            files = menusounds.sounds_of("My Set", found)
            self.assertEqual((files["select"].parent.name, files["back"].parent.name), ("My Set", "sounds"))   # gaps filled

            def scroll_level():
                with wave.open(str(theme / "scroll-now.wav"), "rb") as wav:
                    return int.from_bytes(wav.readframes(1), "little", signed=True)
            self.assertEqual(scroll_level(), 1000)
            self.assertTrue(menusounds.apply(es, mine, themes, {"ui.sound_set": "My Set", "ui.sound_volume": "50"}))
            self.assertEqual(scroll_level(), 0)   # the menu program's own copy is silenced: we play moving ourselves
            self.assertTrue(menusounds.scaled(mine / "My Set/scroll.wav", Path(folder) / "half.wav", 50))
            with wave.open(str(Path(folder) / "half.wav"), "rb") as wav:
                self.assertEqual(int.from_bytes(wav.readframes(1), "little", signed=True), 10000)
            self.assertEqual(menusounds.volume({"ui.sound_volume": "250"}), 100)
            self.assertEqual(menusounds.chosen_set("", found), "EmuBox")                    # nothing chosen, no Xbox set
            self.assertEqual(menusounds.chosen_set("", ["EmuBox", "Battlefront", "OG Xbox"]), "OG Xbox")   # an Xbox set is the default
            self.assertEqual(menusounds.chosen_set("Battlefront", ["EmuBox", "Battlefront", "OG Xbox"]), "Battlefront")
            self.assertEqual(menusounds.chosen_set("Gone", ["EmuBox", "OG Xbox"]), "OG Xbox")
            names = list(found)
            self.assertEqual([menusounds.neighbour("EmuBox", names, True), menusounds.neighbour("My Set", names, True),
                              menusounds.neighbour("EmuBox", names, False), menusounds.neighbour("gone", names, True)],
                             ["My Set", "EmuBox", "My Set", "My Set"])
            # a set with its own start-up film brings it along; going back restores EmuBox's own
            splash, own = Path(folder) / "splash", Path(folder) / "own.mp4"
            splash.mkdir()
            own.write_text("emubox film")
            (splash / "emubox.mp4").write_text("emubox film")
            (mine / "My Set" / "boot.mp4").write_text("my film")
            self.assertTrue(menusounds.start_up_film("My Set", mine, splash, own))
            self.assertEqual((splash / "emubox.mp4").read_text(), "my film")
            self.assertFalse(menusounds.start_up_film("My Set", mine, splash, own))    # already in place
            self.assertTrue(menusounds.start_up_film("EmuBox", mine, splash, own))
            self.assertEqual((splash / "emubox.mp4").read_text(), "emubox film")

    def test_a_setting_written_is_the_setting_read(self):
        with tempfile.TemporaryDirectory() as folder:
            file, none = Path(folder) / "sub" / "settings.conf", Path(folder) / "none.conf"
            self.assertEqual(settings.read(file, none)["web.block_ads"], "on")
            settings.write("web.block_ads", "off", file, none)
            self.assertEqual(settings.read(file, none)["web.block_ads"], "off")
            settings.write("web.block_ads", "on", file, none)
            self.assertEqual(settings.read(file, none)["web.block_ads"], "on")

    def test_adverts_are_turned_into_rules(self):
        import webview
        rules = webview.adblock_rules("# note\nads.example.com\n\n##.ad-banner\n")
        self.assertEqual([rule["action"]["type"] for rule in rules], ["block", "css-display-none"])
        self.assertEqual(rules[0]["trigger"]["load-type"], ["third-party"])
        import re
        pattern = re.compile(rules[0]["trigger"]["url-filter"])
        self.assertTrue(pattern.match("https://cdn.ads.example.com/x.js") and pattern.match("http://ads.example.com:8080/"))
        self.assertFalse(pattern.match("https://notads.example.com.evil.org/") or pattern.match("https://example.com/ads.example.com/"))


if __name__ == "__main__":
    unittest.main()


class SysLoad(unittest.TestCase):
    """The Guide menu's memory and graphics card figures."""

    def setUp(self):
        import sysload
        self.sysload = sysload
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def test_memory_in_use_is_total_minus_available(self):
        info = Path(self.tmp.name) / "meminfo"
        info.write_text("MemTotal:       8000000 kB\nMemFree:  100 kB\nMemAvailable:   6000000 kB\n")
        self.assertEqual(self.sysload.memory(str(info)), (2000000 * 1024, 8000000 * 1024))
        self.assertEqual(self.sysload.memory(str(Path(self.tmp.name) / "missing")), (0, 0))

    def test_gpu_from_the_kernel_or_nothing(self):
        busy = Path(self.tmp.name) / "card0" / "device"
        busy.mkdir(parents=True)
        (busy / "gpu_busy_percent").write_text("37\n")
        gpu = self.sysload.Gpu(sysfs=str(Path(self.tmp.name) / "card*/device/gpu_busy_percent"), nvml="libnot-there.so")
        self.assertEqual((gpu.source, gpu.percent()), ("kernel", 37))
        none = self.sysload.Gpu(sysfs=str(Path(self.tmp.name) / "nothing*"), nvml="libnot-there.so")
        self.assertIsNone(none.percent())


class PhoneKeys(unittest.TestCase):
    def test_the_vm_passes_the_pcs_address(self):
        import phonekeys
        with tempfile.NamedTemporaryFile("w", suffix="cmdline") as cmdline:
            cmdline.write("label=BATOCERA quiet emubox.phonehost=192.168.0.70 loglevel=0\n")
            cmdline.flush()
            self.assertEqual(phonekeys.address(cmdline.name), "192.168.0.70")

    def test_an_unknown_address_gets_a_page_not_an_empty_one(self):
        import urllib.error
        import urllib.request
        import phonekeys
        server = phonekeys.serve("right", lambda *_: None, host="127.0.0.1")
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        port = server.server_address[1]
        with self.assertRaises(urllib.error.HTTPError) as gone:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/k/wrong")
        with gone.exception:
            self.assertIn(b"This code has expired", gone.exception.read())


class PointerInApps(unittest.TestCase):
    """Regression: in web apps (Apple Music) the pointer was gone. Batocera's hide shortcut parks
    it in the bottom-right corner, behind the row of hints, and showing it again left it there;
    and the strip dropped "R Pointer" first, so nothing said how to bring it back."""

    def test_the_strip_keeps_the_pointer_hint_when_space_runs_out(self):
        import hints
        music = json.loads((REPO / "apps/apple-music/app.json").read_text())
        everything = hints.hints(music)
        self.assertIn(("right_stick", "Pointer"), everything)
        droppable = {button for button, _ in everything} & set(hints.DROP_FIRST) - {"right_stick"}
        for room in range(1, len(everything) + 1):   # however narrow: of the hints that can go, it goes last
            kept = {button for button, _ in hints.fit(everything, lambda pairs: len(pairs) <= room)}
            if "right_stick" not in kept:
                self.assertFalse(droppable & kept, f"room for {room}: {sorted(droppable & kept)} kept instead")
        self.assertIn("right_stick", {b for b, _ in hints.fit(everything, lambda pairs: len(pairs) <= 8)})   # as on a TV

    def test_taking_the_controller_shows_the_pointer_in_the_middle(self):
        try:
            import evdev
            from evdev import ecodes as e
        except ImportError:
            self.skipTest("python-evdev is not on this PC (it is on Batocera)")
        import pad

        made, happened = [], []   # the devices made; everything sent or waited, in order

        class Recorder:   # a virtual device that only remembers what was sent through it
            def __init__(self, capabilities, name=""):
                self.name, self.capabilities, self.sent = name, capabilities, []
                made.append(self)

            def write(self, kind, code, value):
                self.sent.append((kind, code, value))
                happened.append(("sent", self.name))

            def syn(self):
                pass

            def close(self):
                pass

        music = json.loads((REPO / "apps/apple-music/app.json").read_text())
        with mock.patch.object(pad, "UInput", Recorder), mock.patch.object(evdev, "list_devices", return_value=[]), \
                mock.patch.object(pad.time, "sleep", side_effect=lambda s: happened.append(("waited", s))):
            app_pad = pad.Pad({"id": "apple-music", **music})
            app_pad._show_pointer(True)   # straight away, as when the app is already in front
        # Brand-new devices are not heard at once (opened from the Guide menu the shortcut was lost):
        # the first thing done is waiting for them, then the shortcut and the placing.
        self.assertEqual(happened[0][0], "waited")
        self.assertGreater(happened[0][1], 0.5)
        out, placer = (next(d for d in made if d.name == name) for name in ("EmuBox app controller", "EmuBox pointer placer"))
        presses = [code for kind, code, value in out.sent if kind == e.EV_KEY and value == 1]
        self.assertEqual(presses, [e.KEY_LEFTALT, e.KEY_LEFTMETA, e.KEY_S])          # the window manager's "show pointer"
        middle = pad.PLACE_MAX // 2 + pad.PLACE_MAX % 2
        self.assertEqual([(code, value) for kind, code, value in placer.sent if kind == e.EV_ABS],
                         [(e.ABS_X, middle), (e.ABS_Y, middle)])                    # and in the middle of the screen
        self.assertIn((e.ABS_X, mock.ANY), placer.capabilities[e.EV_ABS])


def balanced(events) -> list[str]:
    """What is wrong with a stream of (code, 1 down / 0 up) key events: a key let go that was
    never pressed, or a key still held at the end. Empty when every press has its let-go."""
    held, wrong = [], []
    for code, value in events:
        if value == 1:
            held.append(code)
        elif value == 0:
            if code in held:
                held.remove(code)
            else:
                wrong.append(f"{code} let go, never pressed")
    return wrong + [f"{code} still held" for code in held]


class ControllerGuards(unittest.TestCase):
    """Regressions: the pointer and the controller went dead in apps four times. Batocera's
    batocera-mouse (and wtype) make a keyboard of their own that leaves Alt and Super held as far
    as the app can tell, so every key after was ignored; and wtype left keys repeating."""

    CONSOLE = REPO / "components/console/files"

    def test_nothing_runs_batocera_mouse_or_wtype_but_the_typers_last_resort(self):
        import io
        import tokenize
        used = []
        for path in sorted(p for p in self.CONSOLE.rglob("*") if p.is_file() and "__pycache__" not in p.parts):
            try:
                text = path.read_text()
            except UnicodeDecodeError:
                continue
            where = path.relative_to(self.CONSOLE).as_posix()
            if path.suffix == ".py" or text.startswith("#!/usr/bin/env python"):
                for token in tokenize.generate_tokens(io.StringIO(text).readline):
                    if token.type == tokenize.STRING and re.match(r"""^[rbf]*['"]{1,3}(wtype|batocera-mouse)\b""", token.string):
                        used.append((where, token.start[0]))
            else:
                for number, line in enumerate(text.splitlines(), 1):
                    if re.search(r"\b(wtype|batocera-mouse)\b", line.split("#")[0]):
                        used.append((where, number))
        # typer.py's one call: a character its own keyboard has no key for (an accent, a non-US layout).
        allowed = [("lib/typer.py", n) for n, line in enumerate((self.CONSOLE / "lib/typer.py").read_text().splitlines(), 1)
                   if 'self.run(["wtype", *words]' in line]
        self.assertEqual(len(allowed), 1)
        self.assertEqual(used, allowed)

    def test_the_typer_lets_go_of_every_key_it_presses_and_never_falls_back_for_them(self):
        try:
            from evdev import ecodes  # noqa: F401
        except ImportError:
            self.skipTest("python-evdev is not on this PC (it is on Batocera)")
        import typer

        class Device:
            def __init__(self):
                self.events = []
            def write(self, kind, code, value):
                self.events.append((code, value))
            def syn(self):
                pass

        ran = []
        device = Device()
        typing = typer.Typer(device=device, pause=0, run=lambda command, **_: ran.append(command))
        typing.text("".join(typer.US))
        for name in typer.NAMED:
            typing.key(name)
        self.assertEqual(balanced(device.events), [])
        self.assertEqual(ran, [])                                     # wtype never ran for a key the keyboard has

    def make_pad(self, app: str):
        import evdev
        import pad

        class Recorder:
            def __init__(self, capabilities, name=""):
                self.name, self.sent = name, []
            def write(self, kind, code, value):
                if kind == pad.e.EV_KEY:
                    self.sent.append((code, value))
            def syn(self):
                pass
            def close(self):
                pass

        config = json.loads((REPO / f"apps/{app}/app.json").read_text())
        with mock.patch.object(pad, "UInput", Recorder), mock.patch.object(evdev, "list_devices", return_value=[]):
            made = pad.Pad({"id": app, **config})
        made.grabbed = True                                           # holding the controller, as in the app
        return made, pad

    def test_every_button_of_every_app_lets_go_of_what_it_pressed(self):
        try:
            import evdev  # noqa: F401
        except ImportError:
            self.skipTest("python-evdev is not on this PC (it is on Batocera)")
        apps = [p.parent.name for p in sorted((REPO / "apps").glob("*/app.json")) if "pad" in json.loads(p.read_text())]
        self.assertTrue(apps)
        for app in apps:
            app_pad, pad = self.make_pad(app)
            buttons = sorted({name.split("+")[-1] for name in app_pad.map if not name.endswith("_stick")})
            with mock.patch.object(pad.subprocess, "Popen"), mock.patch.object(pad.time, "sleep"), \
                    mock.patch.object(app_pad.app, "title", return_value="page"):
                for button in buttons:                                # one at a time
                    app_pad._button(button, True)
                    app_pad._button(button, False)
                    app_pad.grabbed = True
                app_pad._button("select", True)                       # the second layer
                for button in buttons:
                    app_pad._button(button, True)
                    app_pad._button(button, False)
                    app_pad.grabbed = True
                app_pad._button("select", False)
                for button in buttons:                                # all held, then the pad is handed over
                    app_pad._button(button, True)
                app_pad.grabbed = True
                app_pad.release()
                app_pad._show_pointer(True)
                app_pad._show_pointer(False)
            self.assertEqual(balanced(app_pad.out.sent), [], app)


class AppsOpenThroughTheMenu(unittest.TestCase):
    """Regression: an app opened from the Guide menu left Batocera's menu thinking nothing ran; it
    heard no controller and started its screensaver, game previews playing behind the app."""

    def test_the_guides_open_goes_through_batoceras_menu(self):
        import guide
        tabs, _bars = guide.layout(APPS, lights=False)
        apps = next(tab for tab in tabs if tab.title == "Apps")
        opens = [control.do for row in apps.rows for control in row.controls if control.label == "Open"]
        self.assertTrue(opens)
        for command in opens:
            self.assertIn(" detach launch ", command)
        script = (REPO / "components/console/files/bin/emubox-app").read_text()
        self.assertIn("NO GAME RUNNING", script)          # the menu is asked only when it is free
        self.assertIn('http://127.0.0.1:1234/launch', script)


class FrontendMusicTests(unittest.TestCase):
    def test_batoceras_frontend_music_switch_turns_emuboxs_music_on_and_off(self):
        self.assertTrue(music.frontend_music('<config>\n</config>'))            # on when never set
        self.assertFalse(music.frontend_music('\t<bool name="audio.bgmusic" value="false" />'))
        self.assertTrue(music.frontend_music('\t<bool name="audio.bgmusic" value="true" />'))

    def test_batoceras_other_sound_settings_are_followed(self):
        off = '<bool name="EnableSounds" value="false" />'
        self.assertFalse(menusounds.should_play("select", {}, True, off))       # ENABLE NAVIGATION SOUNDS
        self.assertTrue(menusounds.should_play("select", {}, True, ""))
        self.assertTrue(music.stops_for_screensaver(""))
        self.assertFalse(music.stops_for_screensaver('<bool name="StopMusicOnScreenSaver" value="false" />'))
        self.assertEqual(music.song_titles(""), 10)
        self.assertEqual(music.song_titles('<bool name="audio.display_titles" value="false" />'), 0)
        self.assertEqual(music.song_titles('<int name="audio.display_titles_time" value="4" />'), 4)

    def test_music_volume_follows_as_it_changes(self):
        said, state = [], {}
        with mock.patch.object(music, "ask", lambda *a, **k: said.append(a)):
            for level in ("30", "30", "50"):
                audio.follow_music_settings(f'<int name="MusicVolume" value="{level}" />', True, state)
        self.assertEqual(said, [("set_property", "volume", 30), ("set_property", "volume", 50)])

    def test_frontend_music_changes_are_copied_onto_the_guides_switch(self):
        on, off = '<bool name="audio.bgmusic" value="true" />', '<bool name="audio.bgmusic" value="false" />'
        with tempfile.TemporaryDirectory() as folder:
            seen, conf = Path(folder) / "seen", Path(folder) / "settings.conf"
            with mock.patch.object(settings, "FILE", conf), mock.patch.object(settings, "BATOCERA", Path(folder) / "none"):
                settings.write("music.menu", "off")                         # switched off in the Guide
                self.assertFalse(audio.follow_frontend_music(on, seen))      # first look: nothing changed
                self.assertFalse(audio.follow_frontend_music(on, seen))      # Batocera writes its old value back
                self.assertEqual(settings.get("music.menu"), "off")          # the Guide's choice stays
                self.assertTrue(audio.follow_frontend_music(off, seen))      # changed in Batocera's menu
                self.assertTrue(audio.follow_frontend_music(on, seen))
                self.assertEqual(settings.get("music.menu"), "on")           # copied onto the Guide's switch


class PadCheckTests(unittest.TestCase):
    def test_a_controller_known_only_by_name_is_noticed(self):
        import padcheck
        self.assertEqual(padcheck.guid(0x5, 0x45e, 0xb22, 0x523), "050000005e040000220b000023050000")
        known = [("Xbox Wireless Controller", "050000005e040000220b000023050000")]
        real_pad = padcheck.guid(0x5, 0x45e, 0x28e, 0x1130)
        self.assertTrue(padcheck.guessed("Xbox Wireless Controller", real_pad, known))      # borrowed by name
        self.assertFalse(padcheck.guessed("Xbox Wireless Controller", known[0][1], known))  # its own entry
        self.assertFalse(padcheck.guessed("Some Other Pad", real_pad, known))               # nothing to borrow
        with tempfile.TemporaryDirectory() as folder:
            cfg = Path(folder) / "es_input.cfg"
            cfg.write_text('<inputList>\n\t<inputConfig type="joystick" deviceName="Pad" deviceGUID="ABC">\n</inputList>\n')
            self.assertEqual(padcheck.entries([cfg, Path(folder) / "none"]), [("Pad", "abc")])


class SoundOutputTests(unittest.TestCase):
    def test_outputs_have_names_you_know_and_a_switched_off_tv_is_offered(self):
        import audioout
        sinks = [{"name": "alsa_output.pci-0000_02_00.1.hdmi-stereo", "description": "GB203 Digital Stereo (HDMI)",
                  "properties": {"node.nick": "LG TV SSCR2", "device.bus": "pci"}},
                 {"name": "bluez_output.88_C9.1", "description": "WH-1000XM5", "properties": {"device.bus": "bluetooth"}}]
        self.assertEqual(audioout.outputs(sinks, []), [("auto", "Automatic"),
                                                       ("alsa_output.pci-0000_02_00.1.hdmi-stereo", "LG TV SSCR2 (HDMI)"),
                                                       ("bluez_output.88_C9.1", "WH-1000XM5 (Bluetooth)")])
        off = [{"name": "alsa_card.pci-0000_02_00.1", "active_profile": "off", "properties": {"device.bus": "pci"},
                "profiles": {"off": {}, "output:hdmi-stereo-extra1": {"available": False},
                             "output:hdmi-stereo": {"available": True}}}]
        self.assertEqual(audioout.outputs([], off)[1], ("card:alsa_card.pci-0000_02_00.1:output:hdmi-stereo", "TV (HDMI)"))


class PadTakingTests(unittest.TestCase):
    def test_a_controller_is_taken_only_once_its_buttons_are_let_go(self):
        # The Guide opens on the Guide button's press. Taking the controller then would keep the
        # release from a game underneath (RetroArch's hotkey would stay "held" and its menus would
        # ignore the controller): it is taken once nothing is held.
        import padinput
        from evdev import ecodes as e

        class FakePad:
            __hash__ = None                    # like evdev.InputDevice: it cannot go in a set
            def __eq__(self, other):
                return self is other
            def __init__(self, held):
                self.held, self.grabbed, self.fd = list(held), False, 99
            def capabilities(self):
                return {e.EV_KEY: [e.BTN_SOUTH, e.BTN_MODE]}
            def active_keys(self):
                return self.held
            def grab(self):
                self.grabbed = True
            def ungrab(self):
                self.grabbed = False
            def close(self):
                pass
            def read(self):
                return []

        held, free = FakePad([e.BTN_MODE]), FakePad([])
        pads_by_path = {"/dev/input/event1": held, "/dev/input/event2": free}
        with mock.patch.object(padinput.evdev, "InputDevice", lambda path: pads_by_path[path]), \
             mock.patch.object(padinput.GLib, "io_add_watch", lambda *a: 1), \
             mock.patch.object(padinput.GLib, "timeout_add", lambda *a: 1):
            pads = padinput.Pads(lambda name: None, list(pads_by_path))
            self.assertFalse(held.grabbed)               # Guide still down: not taken yet
            self.assertTrue(free.grabbed)
            pads._on_events(None, None, held)
            self.assertFalse(held.grabbed)               # still held
            held.held = []                               # Guide let go (everyone saw it)
            pads._on_events(None, None, held)
            self.assertTrue(held.grabbed)
            stuck = FakePad([e.BTN_SOUTH])
            pads_by_path["/dev/input/event3"] = stuck
            later = padinput.Pads(lambda name: None, ["/dev/input/event3"])
            later._grab_rest()                           # held for seconds: taken anyway
            self.assertTrue(stuck.grabbed)
