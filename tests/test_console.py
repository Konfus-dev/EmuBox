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
        self.assertEqual([t.title for t in self.tabs], ["Game", "Settings", "Apps", "Record"])
        settings = {row.label: row.controls for row in self.tabs[1].rows}
        self.assertEqual(list(settings), ["Volume", "Mute", "Menu sounds", "Menu sound volume", "Lights", "Light brightness",
                                          "Lights follow the game", "Power", "Plane mode", "Stuck emulator?", "Everything else"])
        self.assertEqual(settings["Everything else"][0].do, "hotkeygen --send menu")      # Batocera's main menu
        apps = [(row.label, [c.label for c in row.controls]) for row in self.tabs[2].rows]
        self.assertEqual(apps, [("Apple Music", ["Open"]), ("Discord", ["Open"]), ("Game", ["Back to game"])])   # no Close, no Heroic
        self.assertTrue(self.tabs[2].rows[0].controls[0].do.endswith(" detach open apple-music"))
        self.assertEqual([t.title for t in guide.layout(APPS, lights=False)[0]], ["Game", "Settings", "Apps", "Record"])
        self.assertNotIn("Lights", [row.label for row in guide.layout(APPS, lights=False)[0][1].rows])
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
        self.model.open_on("Game")
        self.assertEqual([c.label for c in self.model.controls()], ["Resume", "Emulator options", "Quit game"])
        self.model.press("right"); self.model.press("right")
        self.assertEqual(self.model.press("a"), "moved")                        # quitting asks first
        self.assertEqual((self.model.press("a"), self.model.ran), ("close", ["hotkeygen --send exit"]))
        hidden = [row.label for row in self.tabs[1].rows if row.when]
        self.assertEqual(hidden, ["Everything else"])                           # full settings only from the menus

    def test_every_label_is_plain(self):
        for row in [r for t in self.tabs for r in t.rows] + self.bars:
            self.assertTrue(row.label.isascii() and all(c.label.isascii() for c in row.controls), row.label)


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
