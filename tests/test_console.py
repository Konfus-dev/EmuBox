"""Console tool tests: the in-game menu's Apps tab.

    python3 -m unittest discover tests
"""
import importlib.util
import json
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
        self.assertEqual([t.title for t in self.tabs], ["Running", "Settings", "Apps", "Record"])
        settings = {row.label: row.controls for row in self.tabs[1].rows}
        self.assertEqual(list(settings), ["Sound", "Volume", "Mute", "Menu sounds", "Menu sound volume",
                                          "OMEN Lighting", "Lights", "Brightness", "Follow the game",
                                          "System", "Power", "Plane mode", "Stuck emulator?", "Everything else"])
        self.assertEqual(settings["Everything else"][0].do, "hotkeygen --send menu")      # Batocera's main menu
        apps = [(row.label, [c.label for c in row.controls]) for row in self.tabs[2].rows]
        self.assertEqual(apps, [("Apps", []), ("Apple Music", ["Open"]), ("Discord", ["Open"]),      # no Close, no Heroic
                                ("Return", []), ("Hide apps", ["Go back"])])
        self.assertTrue(self.tabs[2].rows[1].controls[0].do.endswith(" detach open apple-music"))
        with_tools = guide.layout(APPS + [("terminal", {"name": "Terminal", "command": ["xterm"]})], lights=False)[0][2].rows
        self.assertEqual([row.label for row in with_tools], ["Apps", "Apple Music", "Discord", "Tools", "Terminal", "Return", "Hide apps"])
        self.assertFalse(with_tools[3].focusable)                                         # the highlight passes over a heading
        self.assertEqual([t.title for t in guide.layout(APPS, lights=False)[0]], ["Running", "Settings", "Apps", "Record"])
        self.assertNotIn("OMEN Lighting", [row.label for row in guide.layout(APPS, lights=False)[0][1].rows])
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
        self.assertTrue(tabs[2].rows[1].controls[0].do.endswith(" detach open youtube"))
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
        text = startmenu.build(["EmuBox", "OG Xbox"], [("omen_x", '    <feature name="X" submenu="OMEN LIGHTING" value="omen_x" preset="switchon" />')])
        root = ET.fromstring(text)
        features = {f.get("value"): f for f in root.find("sharedFeatures")}
        self.assertEqual([f.get("value") for f in root.find("globalFeatures")], list(features))   # each one is switched on globally
        sound_set = features["emubox_ui_sound_set"]
        self.assertEqual((sound_set.get("submenu"), [c.get("value") for c in sound_set]), ("MENU SOUNDS", ["EmuBox", "OG Xbox"]))
        self.assertEqual([c.get("value") for c in features["emubox_ui_sound_volume"]][:3], ["0", "10", "20"])
        self.assertEqual((features["emubox_web_block_ads"].get("submenu"), features["emubox_web_block_ads"].get("preset")), ("APPS", "switchon"))
        self.assertIn("omen_x", features)

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
            conf.write_text("global.omen_lights_enabled=0\n")
            seen = []
            watch = startmenu.Watch(conf)
            watch.modules = [mock.Mock(changed=seen.append, __name__="fake")]
            with mock.patch.object(startmenu.menusounds, "apply"):
                self.assertTrue(watch.look())
                self.assertFalse(watch.look())                       # nothing changed since
            self.assertEqual(seen, [{"omen_lights_enabled": "0"}])


class OmenTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        spec = importlib.util.spec_from_file_location("startmenu_omen", REPO / "components/omen-lights/files/startmenu_omen.py")
        self.omen = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.omen)
        self.omen.HOME = Path(self.folder.name)
        self.omen.FILE = self.omen.HOME / "settings.json"
        self.omen.PICTURES = self.omen.HOME / "pictures"

    def saved(self):
        return json.loads(self.omen.FILE.read_text())

    def test_switches_numbers_and_defaults(self):
        run = self.omen.run
        self.assertEqual((run(["is", "auto-enabled"]), run(["get", "lcd-brightness"])), ("true", "80"))
        run(["set", "auto-enabled", "off"])
        run(["step", "lcd-brightness", "+30"])
        run(["step", "lights-brightness", "-10"])
        self.assertEqual(self.saved(), {"auto-enabled": False, "lcd-brightness": 100, "lights-brightness": 90})
        self.assertEqual(run(["is", "auto-enabled"]), "")

    def test_colours_effects_speed_and_picture(self):
        run = self.omen.run
        run(["colour", "menus", "Blue"])
        run(["colour", "RAM/Stick 1", "#ff0000"])
        run(["colour", "all", "Green"])
        run(["effect", "all", "Rainbow"])    # the case has no rainbow: only the memory takes it
        run(["effect", "case", "Breathing"])
        run(["speed", "100"])
        run(["dim", "min", "25"])
        run(["picture", "/somewhere/dragon.png"])
        saved = self.saved()
        self.assertEqual(saved["auto-idle-colour"], "#1E5BFF")
        self.assertEqual(set(saved["zone-colours"].values()), {"#3CE61E"})
        self.assertEqual(len(saved["zone-colours"]), 6)
        self.assertEqual(saved["device-modes"], {"RAM": "Rainbow", "HP Omen 30L": "Breathing"})
        self.assertEqual(saved["device-speeds"], {"HP Omen 30L": 100, "RAM": 100})
        self.assertEqual(saved["device-min-brightness"]["RAM"], 25)
        self.assertEqual((saved["lcd-image"], saved["auto-idle-image"]), ("/somewhere/dragon.png",) * 2)
        self.assertEqual((run(["colour-of", "menus"]), run(["speed-of"]), run(["picture-of"]), run(["effect-of", "ram"])),
                         ("Blue", "Fast", "dragon", "Rainbow"))
        run(["colour", "menus", "picture"])
        self.assertEqual(run(["colour-of", "menus"]), "From the picture")
        self.assertEqual(self.omen.main(["colour", "all", "mauve-ish"]), 2)
        run(["reset"])
        self.assertEqual(self.saved(), {})

    def test_its_settings_join_batoceras_menu_and_choices_reach_the_lights(self):
        pairs = self.omen.features()
        root = ET.fromstring("<x>" + "\n".join(xml for _, xml in pairs) + "</x>")
        by_value = {f.get("value"): f for f in root}
        self.assertEqual(list(by_value), [name for name, _ in pairs])
        self.assertTrue(all(f.get("submenu") == "OMEN LIGHTING" for f in root))
        self.assertEqual(by_value["omen_lights_enabled"].get("preset"), "switchon")
        self.assertIn("Purple", [c.get("value") for c in by_value["omen_colour_ram_stick_1"]])
        self.omen.changed({"omen_lights_enabled": "0", "omen_lights_brightness": "40.000000", "omen_auto_enabled": "auto",
                           "omen_colour_menus": "Blue", "omen_colour_ram_stick_1": "Purple", "omen_effect_ram": "Rainbow",
                           "omen_speed": "100", "omen_lcd_fit": "fit", "unrelated": "1"})
        saved = self.saved()
        self.assertEqual((saved["lights-enabled"], saved["lights-brightness"], saved["auto-idle-colour"]), (False, 40, "#1E5BFF"))
        self.assertNotIn("auto-enabled", saved)                                  # not chosen: left at its default
        self.assertEqual(saved["zone-colours"], {"RAM/Stick 1": "#9B30FF"})
        self.assertEqual((saved["device-modes"]["RAM"], saved["device-speeds"]["RAM"], saved["lcd-fit"]), ("Rainbow", 100, "fit"))
        self.omen.run(["set", "lights-brightness", "90"])                        # then changed in the Guide menu
        self.omen.changed({"omen_lights_enabled": "0", "omen_lights_brightness": "40.000000"})   # Batocera's menu says nothing new
        self.assertEqual(self.saved()["lights-brightness"], 90)
        self.omen.changed({"omen_lights_brightness": "60"})                      # a new choice there wins again
        self.assertEqual(self.saved()["lights-brightness"], 60)


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
