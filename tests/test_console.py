"""Console tool tests: the in-game menu's Apps tab.

    python3 -m unittest discover tests
"""
import importlib.util
import json
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "components/console/files/lib"))
import audio  # noqa: E402
import menu  # noqa: E402
import menusounds  # noqa: E402
import settings  # noqa: E402

BATOCERA_MENU = """<features>
\t<feature name="shortcuts_tabs">
\t\t<tab display="Shortcuts" target="Shortcuts" />
\t</feature>
\t<hgroup name="Shortcuts" display="Shortcuts"></hgroup>
</features>
"""
APPS = [
    ("apple-music", {"name": "Apple Music", "player": True}),
    ("discord", {"name": "Discord", "voice": True}),
    ("heroic", {"name": "Heroic", "menu": False}),
]


class MenuTests(unittest.TestCase):
    def test_apps_get_open_and_close_and_a_player_its_now_playing_row(self):
        root = ET.fromstring(menu.build(BATOCERA_MENU, APPS))
        apps = next(group for group in root.iter("hgroup") if group.get("name") == "Apps")
        rows = [(row.get("display"), [b.get("display") for b in row.iter("button")])
                for row in apps.iter("feature") if not list(row.iter("switch")) and "—" not in row.get("display")]
        self.assertEqual(rows[5:], [("Sound set", []), ("Volume", ["-", "+"])])
        self.assertEqual(rows[:5], [("Apple Music", ["Open", "Play", "Close"]), ("Apple Music", ["Open", "Close"]),
                                ("Now Playing:", ["<", "||", ">"]),   # right under its app
                                ("Discord", ["Open", "Close"]), ("Game", ["Back to game"])])
        with_play, without = [row.get("if") for row in apps.iter("feature") if row.get("display") == "Apple Music"]
        self.assertIn("media silent", with_play)      # the menu builds one of the two:
        self.assertIn("media sounding", without)      # quick Play only while nothing is playing
        playing = next(row for row in apps.iter("feature") if row.get("display") == "Now Playing:")
        self.assertIn("media title", playing.get("if"))                    # only while there is music
        self.assertIn("media playing", next(playing.iter("text")).get("display"))
        opens = [b.get("action") for b in apps.iter("button") if b.get("display") == "Open"]
        self.assertTrue(all(" detach open " in action for action in opens), opens)   # the menu's 3-second limit

    def test_the_call_tab_shows_only_during_a_call(self):
        root = ET.fromstring(menu.build(BATOCERA_MENU, APPS))
        tabs = {tab.get("display"): tab.get("if", "") for tab in root.iter("tab")}
        self.assertEqual(list(tabs), ["Shortcuts", "Apps", "Call"])
        self.assertEqual(tabs["Apps"], "")
        self.assertIn("mic in-use", tabs["Call"])
        call = next(group for group in root.iter("hgroup") if group.get("name") == "Call")
        self.assertIn("mic mute", next(call.iter("switch")).get("action_on"))

    def test_without_a_voice_app_there_is_no_extra_tab(self):
        root = ET.fromstring(menu.build(BATOCERA_MENU, [("notes", {"name": "Notes"})]))
        self.assertEqual([tab.get("display") for tab in root.iter("tab")], ["Shortcuts", "Apps"])


    def test_nothing_in_the_menu_is_left_blank(self):
        # Batocera refuses a whole menu over one empty label, and then the Guide button does nothing.
        omen = (REPO / "components/omen-lights/files/menu_omen.py").read_text()
        with tempfile.TemporaryDirectory() as lib:
            (Path(lib) / "menu_omen.py").write_text(omen)
            extra = "<x>" + "\n".join(menu.extra_rows(lib)) + "</x>"
        for text in (menu.build(BATOCERA_MENU, APPS), extra):
            for element in ET.fromstring(text).iter():
                for name in ("display", "action", "value"):
                    if name in element.attrib:
                        self.assertTrue(element.get(name).strip(), ET.tostring(element, encoding="unicode")[:120])

    def test_the_apps_tab_ends_with_the_settings_switches(self):
        root = ET.fromstring(menu.build(BATOCERA_MENU, APPS))
        apps = next(group for group in root.iter("hgroup") if group.get("name") == "Apps")
        switches = {row.get("display"): next(row.iter("switch")) for row in apps.iter("feature") if list(row.iter("switch"))}
        self.assertEqual(list(switches)[:3], ["Quiet the menus while my music plays", "Turn music down during a call",
                                          "Block ads in web apps"])
        self.assertEqual(list(switches)[3:], ["Moving through a list", "Choosing", "Going back", "Opening the menu"])
        self.assertIn("Sound set", [row.get("display") for row in apps.iter("feature")])
        ads = switches["Block ads in web apps"]
        self.assertIn("setting is web.block_ads", ads.get("value"))
        self.assertTrue(ads.get("action_off").endswith("setting set web.block_ads off"))


class OmenTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        spec = importlib.util.spec_from_file_location("menu_omen", REPO / "components/omen-lights/files/menu_omen.py")
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

    def test_its_rows_join_the_apps_tab(self):
        with tempfile.TemporaryDirectory() as lib:
            (Path(lib) / "menu_omen.py").write_text((REPO / "components/omen-lights/files/menu_omen.py").read_text())
            (Path(lib) / "menu_broken.py").write_text("def rows(): raise RuntimeError('no')\n")
            rows = menu.extra_rows(lib)
        root = ET.fromstring("<x>" + "\n".join(rows) + "</x>")
        labels = [row.get("display") for row in root.iter("feature")]
        self.assertEqual(labels[:4], ["—  OMEN LIGHTS  —", "Lights", "Light brightness", "Follow the game"])
        self.assertIn("Left memory stick", labels)
        stick = next(row for row in root.iter("feature") if row.get("display") == "Left memory stick")
        self.assertIn("colour 'RAM/Stick 1' 'Purple'", [c.get("action").split("menu_omen.py ")[1] for c in stick.iter("choice")])


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
            self.assertTrue(menusounds.apply(es, mine, themes, {"ui.sound_set": "My Set", "ui.sound_volume": "50"}))
            self.assertEqual(scroll_level(), 10000)
            menusounds.apply(es, mine, themes, {"ui.sound_set": "EmuBox", "ui.sound_volume": "50"})
            self.assertEqual(scroll_level(), 500)
            menusounds.apply(es, mine, themes, {"ui.sound.scroll": "off"})
            self.assertEqual(scroll_level(), 0)
            self.assertEqual(menusounds.volume({"ui.sound_volume": "250"}), 100)

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
