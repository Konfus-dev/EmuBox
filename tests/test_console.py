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
import audio  # noqa: E402
import menu  # noqa: E402
import menusounds  # noqa: E402
import startmenu  # noqa: E402
import settings  # noqa: E402

BATOCERA_MENU = """<features>
\t<feature name="shortcuts_tabs">
\t\t<tab display="Shortcuts" target="Shortcuts" />
\t</feature>
\t<hgroup name="Shortcuts" display="Shortcuts"></hgroup>
\t<vgroup name="Bottom bar" role="footer">
\t\t<feature display="CPU:">
\t\t\t<text display="12" />
\t\t</feature>
\t\t<feature display="Temp:">
\t\t\t<text display="40" />
\t\t</feature>
\t\t<feature display="Resolution:">
\t\t\t<text display="1280x720" />
\t\t</feature>
\t</vgroup>
</features>
"""
APPS = [
    ("apple-music", {"name": "Apple Music", "player": True}),
    ("discord", {"name": "Discord", "voice": True}),
    ("heroic", {"name": "Heroic", "menu": False}),
]


class MenuTests(unittest.TestCase):
    def test_the_apps_tab_has_the_apps_then_the_quick_controls(self):
        root = ET.fromstring(menu.build(BATOCERA_MENU, APPS))
        apps = next(group for group in root.iter("hgroup") if group.get("name") == "Apps")
        rows = [(row.get("display"), [b.get("display") for b in row.iter("button")]) for row in apps.iter("feature")]
        self.assertEqual(rows, [("Apple Music", ["Open", "Play", "Close"]), ("Discord", ["Open", "Close"]),
                                ("Music", ["<", "||", ">"]), ("Mute my microphone", []), ("Volume", ["-", "+"]),
                                ("Options and settings", ["Open the menu", "Back to game"])])
        actions = {b.get("display"): b.get("action") for b in apps.iter("button")}
        self.assertTrue(actions["Open"].endswith(" detach open discord"))       # the menu's 3-second limit
        self.assertEqual(actions["Open the menu"], "hotkeygen --send menu")      # the emulator's menu, or Batocera's
        self.assertEqual([tab.get("display") for tab in root.iter("tab")], ["Shortcuts", "Apps"])

    def test_what_is_going_on_is_shown_in_batoceras_own_bottom_bar(self):
        root = ET.fromstring(menu.build(BATOCERA_MENU, APPS))
        bars = [group for group in root.iter("vgroup") if group.get("role") == "footer"]
        self.assertEqual(len(bars), 1)                       # a second bar pushes the menu off the screen
        columns = list(bars[0].iter("feature"))
        self.assertEqual(len(columns), 3)                    # and so do more than three things in it
        self.assertEqual(columns[0].get("display"), "CPU:")
        self.assertEqual([t.get("display").split(" status ")[1].rstrip("}") for t in bars[0].iter("text")
                          if " status " in t.get("display")], ["music", "call"])
        plain = "<features><feature name=\"shortcuts_tabs\"></feature></features>"
        self.assertNotIn("status music", menu.build(plain, APPS))   # no bar we know: nothing is added

    def test_nothing_in_the_menu_is_left_blank_or_fancy(self):
        # Batocera refuses a whole menu over one empty label, and crashes on a label that is not
        # plain ASCII when no language is set; either way the Guide button then does nothing.
        for element in ET.fromstring(menu.build(BATOCERA_MENU, APPS)).iter():
            for name in ("display", "action", "value"):
                if name in element.attrib:
                    self.assertTrue(element.get(name).strip(), ET.tostring(element, encoding="unicode")[:120])
                    self.assertTrue(element.get(name).isascii(), element.get(name))


class StartMenuTests(unittest.TestCase):
    def test_settings_become_entries_in_batoceras_menu(self):
        text = startmenu.build(["EmuBox", "OG Xbox"], [("omen_x", '    <feature name="X" submenu="OMEN LIGHTS" value="omen_x" preset="switchon" />')])
        root = ET.fromstring(text)
        features = {f.get("value"): f for f in root.find("sharedFeatures")}
        self.assertEqual([f.get("value") for f in root.find("globalFeatures")], list(features))   # each one is switched on globally
        sound_set = features["emubox_ui_sound_set"]
        self.assertEqual((sound_set.get("submenu"), [c.get("value") for c in sound_set]), ("MENU SOUNDS", ["EmuBox", "OG Xbox"]))
        self.assertEqual([c.get("value") for c in features["emubox_ui_sound_volume"]][:3], ["0", "10", "20"])
        self.assertEqual((features["emubox_web_block_ads"].get("submenu"), features["emubox_web_block_ads"].get("preset")), ("APPS", "switchon"))
        self.assertIn("omen_x", features)

    def test_what_is_chosen_in_batoceras_menu_wins(self):
        with tempfile.TemporaryDirectory() as folder:
            mine, batocera = Path(folder) / "settings.conf", Path(folder) / "batocera.conf"
            mine.write_text("ui.sound_volume=30\nweb.block_ads=off\n")
            batocera.write_text("audio.volume=45\nglobal.emubox_ui_sound_set=OG Xbox\nglobal.emubox_ui_sound_volume=80.000000\n"
                                "global.emubox_ui_sound_back=0\nglobal.emubox_music_quiet_menu=auto\n")
            values = settings.read(mine, batocera)
            self.assertEqual((values["ui.sound_set"], values["ui.sound_volume"], values["ui.sound.back"]), ("OG Xbox", "80", "off"))
            self.assertEqual((values["web.block_ads"], values["music.quiet_menu"], values["ui.sound.select"]), ("off", "on", "on"))
            settings.write("ui.sound.back", "on", mine, batocera)      # a script's change reaches Batocera's line too
            self.assertIn("global.emubox_ui_sound_back=1", batocera.read_text())
            self.assertEqual(settings.read(mine, batocera)["ui.sound.back"], "on")

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
        self.assertTrue(all(f.get("submenu") == "OMEN LIGHTS" for f in root))
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
        self.omen.changed({"omen_colour_all": "Red", "omen_colour_ram_stick_1": "Purple"})
        zones = self.saved()["zone-colours"]
        self.assertEqual((zones["HP Omen 30L/Omen Logo"], zones["RAM/Stick 1"]), ("#FF1A1A", "#9B30FF"))   # one light keeps its own


def stream(index, name, corked=False, mute=False, percent=100):
    return {"index": index, "corked": corked, "mute": mute, "volume": {"front-left": {"value_percent": f"{percent}%"}},
            "properties": {"application.name": name}}


class AudioTests(unittest.TestCase):
    ON = {"music.quiet_menu": "on", "call.lower_music": "on", "call.music_volume": "20"}

    def test_the_menus_go_quiet_under_music_and_come_back(self):
        state = {}
        menus, song = stream(1, "EmulationStation"), stream(2, "Google Chrome")
        self.assertEqual(audio.plan([menus], [], ["chrome"], self.ON, state), [])
        self.assertEqual(audio.plan([menus, song], [], ["chrome"], self.ON, state), [["set-sink-input-mute", "1", "1"]])
        menus["mute"] = True
        self.assertEqual(audio.plan([menus, song], [], ["chrome"], self.ON, state), [])
        song["corked"] = True   # paused
        self.assertEqual(audio.plan([menus, song], [], ["chrome"], self.ON, state), [["set-sink-input-mute", "1", "0"]])

    def test_a_menu_someone_else_muted_is_left_muted(self):
        state = {}
        menus = stream(1, "EmulationStation", mute=True)
        self.assertEqual(audio.plan([menus, stream(2, "Google Chrome")], [], ["chrome"], self.ON, state), [])
        self.assertEqual(audio.plan([menus], [], ["chrome"], self.ON, state), [])

    def test_music_makes_way_for_a_call_and_returns_to_where_it_was(self):
        state = {}
        song, game, voice = stream(2, "Google Chrome", percent=80), stream(3, "retroarch"), stream(4, "Discord")
        mic = [stream(9, "Discord")]
        self.assertEqual(audio.plan([song, game, voice], mic, ["chrome"], self.ON, state),
                         [["set-sink-input-volume", "2", "20%"]])    # not the game, not the call itself
        song["volume"]["front-left"]["value_percent"] = "20%"
        self.assertEqual(audio.plan([song, game, voice], mic, ["chrome"], self.ON, state), [])
        self.assertEqual(audio.plan([song, game], [], ["chrome"], self.ON, state), [["set-sink-input-volume", "2", "80%"]])

    def test_switched_off_means_hands_off(self):
        off = {"music.quiet_menu": "off", "call.lower_music": "off"}
        streams = [stream(1, "EmulationStation"), stream(2, "Google Chrome")]
        self.assertEqual(audio.plan(streams, [stream(9, "Discord")], ["chrome"], off, {}), [])

    def test_menu_sounds_follow_the_buttons_and_know_when_to_keep_quiet(self):
        self.assertEqual([menusounds.sound_for(code, False) for code in (304, 305, 315, 307)], ["select", "back", "menuopen", ""])
        self.assertEqual([menusounds.sound_for(code, True) for code in (304, 305)], ["back", "select"])
        self.assertEqual([menusounds.sound_for(code, True) for code in (28, 1, 57)], ["select", "back", "menuopen"])   # keyboard
        self.assertTrue(menusounds.should_play("select", {}, in_menus=True, quiet=False))
        self.assertFalse(menusounds.should_play("select", {}, in_menus=False, quiet=False))    # a game is running
        self.assertFalse(menusounds.should_play("select", {}, in_menus=True, quiet=True))      # your music is playing
        self.assertFalse(menusounds.should_play("back", {"ui.sound.back": "off"}, True, False))
        self.assertTrue(menusounds.should_play("select", {"ui.sound.back": "off"}, True, False))   # each has its own switch

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

    def test_settings_are_kept_only_when_they_differ(self):
        with tempfile.TemporaryDirectory() as folder:
            file = Path(folder) / "sub" / "settings.conf"
            self.assertTrue(settings.on("web.block_ads", file))
            settings.write("web.block_ads", "off", file)
            self.assertFalse(settings.on("web.block_ads", file))
            self.assertEqual(file.read_text(), "web.block_ads=off\n")
            settings.write("web.block_ads", "on", file)
            self.assertEqual(file.read_text(), "")

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
