"""Installer tests: run against a pretend Batocera drive in a temporary folder.

    python3 -m unittest discover tests
"""
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from installer import cli, components, gamelist, library  # noqa: E402
from installer.fetch import without_secrets  # noqa: E402
from installer.library import Library  # noqa: E402
from installer.prompts import parse_numbers  # noqa: E402
from installer.target import Target  # noqa: E402


os.environ["EMUBOX_DOWNLOAD_LATER"] = "1"   # the tests never fetch programs from Flathub
os.environ["EMUBOX_SOUNDS"] = "none"        # nor pick up sound sets that happen to sit beside the repository
COMPONENT_QUESTIONS = 10   # asked on a PC without the OMEN lights


def make_drive(root: Path) -> Target:
    (root / "system").mkdir(parents=True)
    (root / "roms" / "ports").mkdir(parents=True)
    (root / "system" / "batocera.conf").write_text("audio.volume=45\nsystem.services=old_one console_apps\n")
    return Target(root)


def make_file(path: Path, size: int = 10) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x" * size)
    return path


def run(drive: Path, *args: str, answers: str = "") -> tuple[int, str]:
    out = io.StringIO()
    with mock.patch("sys.stdin", io.StringIO(answers)), mock.patch("sys.stdout", out), \
            mock.patch.object(cli.Host, "usb_devices", return_value=set()), \
            mock.patch.object(cli.Host, "paired_bluetooth_devices", return_value=[]):
        code = cli.main(["--target", str(drive), *args])
    return code, out.getvalue()


class Drive(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "SHARE"
        self.target = make_drive(self.root)


class TargetTests(Drive):
    def test_conf_set_replaces_or_adds(self):
        self.target.conf_set("audio.volume", "60")
        self.target.conf_set("nes.rewind", "1")
        self.assertEqual(self.target.conf_get("audio.volume"), "60")
        self.assertEqual(self.target.conf_get("nes.rewind"), "1")

    def test_services_are_added_once_and_removed(self):
        self.target.enable_service("emubox")
        self.target.enable_service("emubox")
        self.assertEqual(self.target.services(), ["old_one", "console_apps", "emubox"])
        self.target.disable_service("console_apps")
        self.assertEqual(self.target.services(), ["old_one", "emubox"])

    def test_es_setting_is_created_then_replaced(self):
        self.target.es_setting("ThemeSet", "one")
        self.target.es_setting("ThemeSet", "two")
        text = (self.root / "system/configs/emulationstation/es_settings.cfg").read_text()
        self.assertEqual(text.count("ThemeSet"), 1)
        self.assertIn('value="two"', text)

    def test_paths_cannot_leave_the_drive(self):
        with self.assertRaises(ValueError):
            self.target.path("../outside")


class ComponentTests(Drive):
    def test_every_component_file_exists(self):
        for component in components.discover(REPO).values():
            for item in component.spec.get("files", []):
                self.assertTrue((component.folder / item["from"]).exists(), f"{component.id}: {item['from']}")
            for port in component.spec.get("ports", []):
                for key in ("script", "image"):
                    if key in port:
                        self.assertTrue((component.folder / port[key]).exists(), f"{component.id}: {port[key]}")

    def test_apps_pull_in_the_console_tools(self):
        everything = components.discover(REPO)
        self.assertEqual(components.with_requirements(["discord"], everything),
                         ["console", "discord", "claude", "files", "terminal"])   # the last three come with the console tools

    def test_install_everything_then_remove_an_app(self):
        code, out = run(self.root, "--yes", "--with", "look,discord,apple-music,rom-patcher,tweaks,store,vault")
        self.assertEqual(code, 0, out)
        for path in ("themes/emubox/theme.xml", "system/emubox/bin/emubox-app", "system/emubox/lib/pad.py",
                     "system/emubox/apps/discord/app.json", "roms/apps/Discord.sh", "roms/apps/images/Apple Music.png", "system/configs/emulationstation/es_systems_apps.cfg",
                     "system/services/emubox", "system/emubox/tools/apply-patches.py",
                     "roms/store/Games/Steam.sh", "roms/store/images/Free Games.png", "roms/store/Games/Vault.sh", "roms/store/Games/itch.io.sh",
                     "roms/store/Apps/Flathub.sh", "roms/store/images/itch.io.png",
                     "system/emubox/bin/vault", "system/emubox/lib/vault.py", "system/emubox/lib/webview.py", "system/emubox/lib/webnav.js", "system/emubox/apps/heroic/app.json",
                     "system/configs/emulationstation/es_systems_store.cfg"):
            self.assertTrue((self.root / path).is_file(), path)
        self.assertIn("emubox-app open discord --wait", (self.root / "roms/apps/Discord.sh").read_text())
        self.assertEqual(self.target.services(), ["old_one", "emubox", "rom_patcher", "tidy_folders"])
        entries = (self.root / "system/configs/emulationstation/es_features_emubox.cfg").read_text()
        self.assertIn('submenu="MENU SOUNDS"', entries)     # EmuBox's settings are in Batocera's menu from the first start
        self.assertEqual(self.target.conf_get("global.shaderset"), "zfast")
        self.assertEqual((self.root / "roms/apps/gamelist.xml").read_text().count("<game>"), 5)   # two chosen, and Claude, Files and Terminal
        self.assertEqual((self.root / "roms/store/gamelist.xml").read_text().count("<game>"), 6)

        code, out = run(self.root, "--remove", "discord")
        self.assertEqual(code, 0, out)
        self.assertFalse((self.root / "roms/apps/Discord.sh").exists())
        self.assertFalse((self.root / "system/emubox/apps/discord").exists())
        self.assertTrue((self.root / "system/emubox/bin/emubox-app").exists())   # Apple Music still needs it
        menu = self.root / "system/configs/controlcenter/controlcenter.xml"   # as built on Batocera at boot
        make_file(menu).write_text("<features><!-- emubox apps --></features>")
        code, out = run(self.root, "--remove", "apple-music", "store", "vault")
        self.assertFalse((self.root / "roms/store/Games/Steam.sh").exists())
        self.assertFalse((self.root / "roms/store/Games").exists())      # an emptied sub-section goes too
        self.assertFalse((self.root / "system/emubox/bin").exists())
        self.assertFalse(menu.exists())
        self.assertNotIn("emubox", self.target.services())

    def test_a_drive_installed_under_the_old_name_is_moved_over(self):
        old = {
            "sources": {"games": "/somewhere/games"},
            "components": {
                "look": {"title": "Xbox-style look", "files": ["themes/retrobox/theme.xml"], "services": [], "ports": []},
                "console": {"title": "Console tools", "services": ["retrobox"], "ports": [],
                            "files": ["system/retrobox/bin/retrobox-app", "system/services/retrobox"],
                            "generated": [{"path": "system/configs/controlcenter/controlcenter.xml",
                                           "contains": "<!-- retrobox apps -->"}]},
                "discord": {"title": "Discord", "services": [], "ports": ["Discord"],
                            "files": ["system/retrobox/apps/discord/app.json", "roms/ports/Discord.sh"]},
            },
        }
        for entry in old["components"].values():
            for file in entry["files"]:
                make_file(self.root / file).write_text("old")
        make_file(self.root / "system/retrobox/installed.json").write_text(json.dumps(old))
        make_file(self.root / "system/configs/controlcenter/controlcenter.xml").write_text("<!-- retrobox apps -->")
        make_file(self.root / "roms/ports/My Own Port.sh").write_text("mine")
        self.target.enable_service("retrobox")

        code, out = run(self.root, "--yes", "--with", "look")
        self.assertEqual(code, 0, out)
        self.assertIn("Taken off: Console tools, Discord, Xbox-style look", out)
        self.assertIn("no longer installed: Console tools, Discord", out)
        for gone in ("system/retrobox", "themes/retrobox", "system/services/retrobox", "roms/ports/Discord.sh",
                     "system/configs/controlcenter/controlcenter.xml"):
            self.assertFalse((self.root / gone).exists(), gone)
        self.assertNotIn("retrobox", self.target.services())
        self.assertTrue((self.root / "themes/emubox/theme.xml").is_file())
        self.assertTrue((self.root / "roms/ports/My Own Port.sh").is_file())
        manifest = self.target.manifest()
        self.assertEqual((list(manifest["components"]), manifest["sources"]), (["look"], {"games": "/somewhere/games"}))

    def test_an_apps_program_is_fetched_onto_the_drive_with_batoceras_driver(self):
        from installer import flatpak
        refs = self.root / "saves/flatpak/binaries/repo/refs/remotes/flathub/runtime"
        (refs / "org.freedesktop.Platform.GL.nvidia-590-48-01/x86_64/1.4").mkdir(parents=True)
        (refs / "org.freedesktop.Platform.GL.default/x86_64/25.08").mkdir(parents=True)
        self.assertEqual(flatpak.wanted_drivers(self.target), [("nvidia-590-48-01", "1.4")])
        calls, said = [], []

        def run(command, env, check):
            calls.append((command[1:], env.get("FLATPAK_USER_DIR"), env.get("FLATPAK_GL_DRIVERS")))
            if command[-1] == "com.example.Works":
                make_file(self.root / "saves/flatpak/binaries/app/com.example.Works/current/active/metadata").write_text(
                    "[Application]\nruntime=org.example.Platform/x86_64/1\n")
            return mock.Mock(returncode=0 if command[-1] != "com.example.Fails" else 1)

        with mock.patch.object(flatpak.shutil, "which", return_value="/usr/bin/flatpak"), \
             mock.patch.object(flatpak.shutil, "disk_usage", return_value=mock.Mock(free=50 * 1024 ** 3)):
            done = flatpak.preinstall(self.target, ["com.example.Works", "com.example.Fails"], said.append, run)
            self.assertEqual(done, ["com.example.Works"])
            self.assertEqual(calls[0][0], ["remote-add", "--user", "--if-not-exists", "flathub", flatpak.FLATHUB])
            self.assertEqual(calls[1][0][-1], "runtime/org.freedesktop.Platform.GL.nvidia-590-48-01/x86_64/1.4")
            self.assertEqual(calls[2], (["install", "--user", "-y", "--noninteractive", "flathub", "com.example.Works"],
                                        str(self.root / "saves/flatpak/binaries"), "nvidia-590-48-01:default"))
            self.assertTrue(any("first time it is opened" in line for line in said))
            self.assertEqual(calls[-2][0][-1], "runtime/org.example.Platform/x86_64/1")   # asked for by name
            self.assertEqual(calls[-1][0], ["update", "--user", "-y", "--noninteractive"])   # drivers and the rest
            # flatpak forgets a driver it removed; the note beside the programs does not
            import shutil as real_shutil
            real_shutil.rmtree(refs / "org.freedesktop.Platform.GL.nvidia-590-48-01")
            self.assertEqual(flatpak.wanted_drivers(self.target), [("nvidia-590-48-01", "1.4")])
        with mock.patch.object(flatpak.shutil, "which", return_value=None):
            self.assertEqual(flatpak.preinstall(self.target, ["com.example.Other"], said.append, run), [])

    def test_your_own_sound_sets_are_copied_and_named_files_decide_what_does_what(self):
        with tempfile.TemporaryDirectory() as folder:
            mine = Path(folder) / "Sounds"
            make_file(mine / "My Set" / "select.wav")
            make_file(mine / "My Set" / "boot.wav")
            make_file(mine / "My Set" / "notes.txt")
            (mine / "Empty").mkdir()
            films = []

            def make_film(sound, out):
                films.append(sound.name)
                out.write_text("film")
                return True
            self.assertEqual(cli.copy_sound_sets(self.target, mine, make_film=make_film), [])   # nothing there to play them yet
            make_file(self.root / "system/emubox/lib/menusounds.py")
            self.assertEqual(cli.copy_sound_sets(self.target, mine, make_film=make_film), ["My Set"])
            on_drive = self.root / "system/configs/emubox/sounds/My Set"
            self.assertEqual(sorted(p.name for p in on_drive.iterdir()), ["boot.mp4", "select.wav"])   # the film is made from boot.wav
            cli.copy_sound_sets(self.target, mine, make_film=make_film)
            self.assertEqual(films, ["boot.wav"])                         # and not made again while the sound is unchanged
            said = []
            (on_drive / "boot.mp4").unlink()
            cli.copy_sound_sets(self.target, mine, said.append, make_film=lambda sound, out: False)
            self.assertIn("keeps EmuBox's own film", said[-1])

    def test_a_setup_file_answers_everything(self):
        with tempfile.TemporaryDirectory() as folder:
            make_file(Path(folder) / "mine/Arcade/select.wav")
            setup = Path(folder) / "setups/me.json"
            make_file(setup).write_text(json.dumps({
                "with": ["discord", "store", "vault"], "sounds": "../mine", "download_later": True,
                "vault_pages": [{"name": "Indie", "url": "https://itch.io/games/free"}]}))
            for _ in range(2):   # a second run adds nothing twice
                code, out = run(self.root, "--setup", str(setup))
                self.assertEqual(code, 0, out)
            self.assertTrue((self.root / "roms/apps/Discord.sh").is_file())
            self.assertFalse((self.root / "roms/apps/Apple Music.sh").exists())
            self.assertTrue((self.root / "system/configs/emubox/sounds/Arcade/select.wav").is_file())   # relative to the file
            pages = json.loads((self.root / "system/vault/vault.json").read_text())["pages"]
            self.assertEqual(pages, [{"name": "Indie", "url": "https://itch.io/games/free"}])
            setup.write_text(json.dumps({"with": ["discord"], "sounds": "../moved-away", "download_later": True}))
            code, out = run(self.root, "--setup", str(setup))   # a folder that is not on this PC is no reason to stop
            self.assertEqual(code, 0, out)
            self.assertIn("moved-away is not here; left out", out)
            setup.write_text('{"wiht": []}')
            code, out = run(self.root, "--setup", str(setup))
            self.assertEqual(code, 1)
            self.assertIn("not understood: wiht", out)

    def test_the_installer_asks_for_your_sounds_and_remembers_the_folder(self):
        with tempfile.TemporaryDirectory() as folder, mock.patch.dict("os.environ", {"EMUBOX_SOUNDS": ""}), \
             mock.patch.object(cli, "SOUNDS_BESIDE", Path(folder) / "nowhere"):
            make_file(Path(folder) / "mine" / "Arcade" / "scroll.wav")
            # look n, apple-music n, discord y, seven more n, bios n, games n, sounds y + folder, go ahead y
            code, out = run(self.root, answers="n\nn\ny\n" + "n\n" * 7 + "n\nn\ny\n" + f"{folder}/mine\ny\n")
            self.assertEqual(code, 0, out)
            self.assertIn("scroll.wav", out)      # the names are explained when asked
            self.assertIn("Arcade", out)
            self.assertTrue((self.root / "system/configs/emubox/sounds/Arcade/scroll.wav").is_file())
            self.assertEqual(self.target.manifest()["sources"]["sounds"], f"{folder}/mine")
            code, out = run(self.root, "--yes", "--with", "discord")      # next time it is used without asking
            self.assertIn("Arcade", out)

    def test_the_plain_form_of_the_xbox_pad_is_added_to_the_controllers_list(self):
        run(self.root, "--yes", "--with", "discord")
        file = self.root / "system/configs/emulationstation/es_input.cfg"
        self.assertEqual(file.read_text().count("050000005e040000220b000023050000"), 1)
        file.write_text('<?xml version="1.0"?>\n<inputList>\n\t<inputConfig deviceName="Mine" deviceGUID="abc" />\n</inputList>\n')
        run(self.root, "--yes", "--with", "discord")
        text = file.read_text()
        self.assertIn('deviceName="Mine"', text)                 # yours stay
        self.assertEqual(text.count("220b000023050000"), 1)
        import xml.etree.ElementTree as ET
        self.assertEqual(len(ET.fromstring(text)), 2)
        run(self.root, "--yes", "--with", "discord")
        self.assertEqual(file.read_text(), text)                 # and it is added once

    def test_installing_twice_changes_nothing_more(self):
        run(self.root, "--yes", "--with", "discord")
        before = sorted(p.relative_to(self.root).as_posix() for p in self.root.rglob("*"))
        run(self.root, "--yes", "--with", "discord")
        self.assertEqual(before, sorted(p.relative_to(self.root).as_posix() for p in self.root.rglob("*")))
        self.assertEqual((self.root / "roms/apps/gamelist.xml").read_text().count("<game>"), 4)   # the one chosen, and Claude, Files and Terminal

    def test_lights_are_not_offered_without_the_hardware(self):
        code, out = run(self.root, "--yes", "--with", "omen-lights")
        self.assertEqual(code, 1)
        self.assertIn("Not available here", out)
        _code, out = run(self.root, answers="n\n" * 20)
        self.assertNotIn("OMEN", out)

    def test_questions_are_asked_and_answered(self):
        # look n, apple-music n, discord y, seven more n, bios n, games n, go ahead y
        code, out = run(self.root, answers="n\nn\ny\n" + "n\n" * 7 + "n\nn\ny\n")
        self.assertEqual(code, 0, out)
        self.assertTrue((self.root / "roms/apps/Discord.sh").exists())
        self.assertFalse((self.root / "themes/emubox").exists())


class TypedAnswerTests(Drive):
    def test_wifi_is_asked_for_and_written(self):
        # look, apple-music, discord, store, vault n; wifi y + name + password; four more n; bios n, games n; go ahead y
        code, out = run(self.root, answers="n\nn\nn\nn\nn\ny\nHome Net\np@ss {word}\n" + "n\n" * 4 + "n\nn\ny\n")
        self.assertEqual(code, 0, out)
        self.assertEqual(self.target.conf_get("wifi.ssid"), "Home Net")
        self.assertEqual(self.target.conf_get("wifi.key"), "p@ss {word}")
        self.assertEqual(self.target.conf_get("wifi.enabled"), "1")
        self.assertNotIn("p@ss", (self.root / "system/emubox/installed.json").read_text())

    def test_answers_can_be_given_ahead(self):
        with mock.patch.dict("os.environ", {"EMUBOX_SCRAPER_PASSWORD": "s3cret"}):
            code, out = run(self.root, "--yes", "--with", "scraper", "--set", "scraper.user=me")
        self.assertEqual(code, 0, out)
        settings = (self.root / "system/configs/emulationstation/es_settings.cfg").read_text()
        self.assertIn('<string name="ScreenScraperUser" value="me" />', settings)
        self.assertIn('<string name="ScreenScraperPass" value="s3cret" />', settings)
        self.assertIn('<bool name="ScrapeVideos" value="true" />', settings)

    def test_missing_answers_stop_an_unattended_run(self):
        code, out = run(self.root, "--yes", "--with", "achievements")
        self.assertEqual(code, 1)
        self.assertIsNone(self.target.conf_get("global.retroachievements"))

    def test_a_password_batocera_cannot_store_is_refused(self):
        code, out = run(self.root, "--yes", "--with", "wifi", "--set", "wifi.ssid=Home", "--set", "wifi.key=a\\b")
        self.assertEqual(code, 1)
        self.assertIn("backslash", out)


class LibraryTests(Drive):
    def setUp(self):
        super().setUp()
        self.games = Path(self.tmp.name) / "games"
        make_file(self.games / "psx/Quest (USA) (Disc 1).chd", 300)
        make_file(self.games / "psx/Quest (USA) (Disc 2).chd", 300)
        make_file(self.games / "psx/Quest (USA).m3u", 20)
        make_file(self.games / "psx/Racer.chd", 100)
        make_file(self.games / "psx/images/Racer-image.png", 5)
        make_file(self.games / "psx/images/Quest (USA)-image.png", 5)
        make_file(self.games / "snes/Platformer.sfc", 50)
        make_file(self.games / "empty/_info.txt")
        (self.games / "psx/gamelist.xml").write_text(
            "<gameList><game><path>./Racer.chd</path><name>Racer</name></game>"
            "<game><path>./Quest (USA).m3u</path><name>Quest</name></game></gameList>")
        self.bios = Path(self.tmp.name) / "bios"
        make_file(self.bios / "psx/scph5501.bin")
        make_file(self.bios / "ps2/ps2/bios.bin")

    def test_discs_and_playlist_are_one_game(self):
        psx = {s.id: s for s in Library(self.games, "games").systems()}["psx"]
        self.assertEqual([g.name for g in psx.items], ["Quest (USA)", "Racer"])
        self.assertEqual(len(psx.items[0].files), 3)

    def test_empty_systems_are_not_listed(self):
        self.assertEqual([s.id for s in Library(self.games, "games").systems()], ["psx", "snes"])

    def test_one_game_brings_its_picture_and_list_entry(self):
        # no to every component, bios n, games y, where, system 1 (psx), all games n, game 2 (Racer), go ahead y
        code, out = run(self.root, answers="n\n" * COMPONENT_QUESTIONS + f"n\ny\n{self.games}\n1\nn\n2\ny\n")
        self.assertEqual(code, 0, out)
        self.assertTrue((self.root / "roms/psx/Racer.chd").exists())
        self.assertTrue((self.root / "roms/psx/images/Racer-image.png").exists())
        self.assertFalse((self.root / "roms/psx/Quest (USA).m3u").exists())
        self.assertFalse((self.root / "roms/snes").exists())
        listed = (self.root / "roms/psx/gamelist.xml").read_text()
        self.assertIn("Racer", listed)
        self.assertNotIn("Quest", listed)

    def test_bios_keeps_each_systems_layout(self):
        code, out = run(self.root, "--yes", "--with", "", "--bios", str(self.bios), "--bios-systems", "ps2")
        self.assertEqual(code, 0, out)
        self.assertTrue((self.root / "bios/ps2/bios.bin").exists())
        self.assertFalse((self.root / "bios/scph5501.bin").exists())

    def test_a_batocera_drive_works_as_a_games_library(self):
        other = Path(self.tmp.name) / "other"
        make_drive(other)
        make_file(other / "roms/snes/Game.sfc")
        self.assertEqual([s.id for s in Library(other, "games").systems()], ["snes"])

    def test_backup_writes_an_index(self):
        make_file(self.root / "roms/snes/Game.sfc", 40)
        make_file(self.root / "roms/snes/images/Game-image.png", 4)
        destination = Path(self.tmp.name) / "backup"
        code, out = run(self.root, "--yes", "--backup-games", str(destination))
        self.assertEqual(code, 0, out)
        self.assertTrue((destination / "snes/images/Game-image.png").exists())
        rows = (destination / "MANIFEST.tsv").read_text().splitlines()
        self.assertEqual(len(rows), 2)
        self.assertTrue(rows[1].endswith("\tsnes/Game.sfc"))

    def test_not_enough_space_is_refused_before_copying(self):
        with mock.patch.object(Target, "free_bytes", return_value=10):
            code, out = run(self.root, "--yes", "--with", "", "--games", str(self.games))
        self.assertEqual(code, 1)
        self.assertIn("free", out)
        self.assertFalse((self.root / "roms/psx/Racer.chd").exists())


class SmallThings(unittest.TestCase):
    def test_number_ranges(self):
        self.assertEqual(parse_numbers("1, 3-4", 5), [0, 2, 3])
        for bad in ("0", "6", "x", "3-2"):
            with self.assertRaises(ValueError):
                parse_numbers(bad, 5)

    def test_tokens_are_not_remembered(self):
        self.assertEqual(without_secrets("https://secret@github.com/me/games"), "https://github.com/me/games")

    def test_app_files_are_complete(self):
        for path in (REPO / "apps").glob("*/app.json"):
            app = json.loads(path.read_text())
            for key in ("name", "window", "pad", "description"):
                self.assertIn(key, app, f"{path}: {key}")
            # A Flathub program with its arguments, or a program Batocera already has.
            self.assertTrue(("flatpak" in app and "args" in app) != ("command" in app), path)
            # The buttons every app shares, so the controller always behaves the same way.
            for button, action in (("a", ["KEY_ENTER"]), ("guide", "menu"), ("l3", "osk"),
                                   ("select+b", "back"), ("select+start", "close")):
                self.assertEqual(app["pad"].get(button), action, f"{path}: {button}")
            self.assertTrue((path.parent / "tile.png").exists())


if __name__ == "__main__":
    unittest.main()


class BluetoothSharing(Drive):
    def test_pairings_are_merged_into_batoceras_archive(self):
        import importlib.util
        import io
        import tarfile
        spec = importlib.util.spec_from_file_location("bt", REPO / "components/bluetooth/component.py")
        bt = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(bt)

        host = Path(self.tmp.name) / "host"
        pad = host / "AA:AA:AA:AA:AA:AA" / "11:11:11:11:11:11"
        make_file(pad / "info").write_text(
            "[General]\nName=Pad\nTrusted=false\nServices=00001812-0000-1000-8000-00805f9b34fb;\n\n[LongTermKey]\nKey=NEWKEY\n")
        make_file(host / "AA:AA:AA:AA:AA:AA" / "22:22:22:22:22:22" / "info").write_text(
            "[General]\nName=Speaker\nServices=0000110b-0000-1000-8000-00805f9b34fb;\n\n[LinkKey]\nKey=SPK\n")

        archive = self.root / "system/bluetooth/bluetooth.tar"
        archive.parent.mkdir(parents=True)
        with tarfile.open(archive, "w") as old:
            for name, text in (("bluetooth/AA:AA:AA:AA:AA:AA/11:11:11:11:11:11/info", "Key=OLDKEY\n"),
                               ("bluetooth/AA:AA:AA:AA:AA:AA/33:33:33:33:33:33/info", "Key=OTHER\n")):
                entry = tarfile.TarInfo(name)
                entry.size = len(text)
                old.addfile(entry, io.BytesIO(text.encode()))

        said = []
        env = components.Env(target=self.target, repo=REPO, host=None, fetch=None, say=said.append)
        with mock.patch.object(bt, "HOST_PAIRINGS", host):
            bt.install(env)

        with tarfile.open(archive) as new:
            names = new.getnames()
            info = new.extractfile("bluetooth/AA:AA:AA:AA:AA:AA/11:11:11:11:11:11/info").read().decode()
        self.assertIn("Key=NEWKEY", info)                       # this PC's pairing replaced the stale one
        self.assertIn("Trusted=true", info)
        self.assertIn("bluetooth/AA:AA:AA:AA:AA:AA/33:33:33:33:33:33/info", names)   # Batocera's others are kept
        self.assertFalse(any("22:22:22" in n for n in names))   # a speaker is not an input device
        self.assertEqual(names.count("bluetooth/AA:AA:AA:AA:AA:AA/11:11:11:11:11:11/info"), 1)
        self.assertFalse(any("KEY" in line for line in said))   # keys are never printed
