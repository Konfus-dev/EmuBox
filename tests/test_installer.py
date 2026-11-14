"""Installer tests: run against a pretend Batocera drive in a temporary folder.

    python3 -m unittest discover tests
"""
import io
import json
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


COMPONENT_QUESTIONS = 9   # asked on a PC without the OMEN lights


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
            mock.patch.object(cli.Host, "usb_devices", return_value=set()):
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
        self.target.enable_service("retrobox")
        self.target.enable_service("retrobox")
        self.assertEqual(self.target.services(), ["old_one", "console_apps", "retrobox"])
        self.target.disable_service("console_apps")
        self.assertEqual(self.target.services(), ["old_one", "retrobox"])

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

    def test_apps_pull_in_the_runtime(self):
        everything = components.discover(REPO)
        self.assertEqual(components.with_requirements(["discord"], everything), ["runtime", "discord"])

    def test_install_everything_then_remove_an_app(self):
        code, out = run(self.root, "--yes", "--with", "look,discord,apple-music,rom-patcher,tweaks,pc-launchers")
        self.assertEqual(code, 0, out)
        for path in ("themes/retrobox/theme.xml", "system/retrobox/bin/retrobox-app", "system/retrobox/lib/pad.py",
                     "system/retrobox/apps/discord/app.json", "roms/ports/Discord.sh", "roms/ports/images/Apple Music.png",
                     "system/services/retrobox", "system/retrobox/tools/apply-patches.py",
                     "roms/ports/Install Steam and Heroic.sh"):
            self.assertTrue((self.root / path).is_file(), path)
        self.assertIn("retrobox-app open discord --wait", (self.root / "roms/ports/Discord.sh").read_text())
        self.assertEqual(self.target.services(), ["old_one", "retrobox", "rom_patcher", "tidy_folders"])
        self.assertEqual(self.target.conf_get("global.shaderset"), "zfast")
        self.assertEqual((self.root / "roms/ports/gamelist.xml").read_text().count("<game>"), 3)

        code, out = run(self.root, "--remove", "discord")
        self.assertEqual(code, 0, out)
        self.assertFalse((self.root / "roms/ports/Discord.sh").exists())
        self.assertFalse((self.root / "system/retrobox/apps/discord").exists())
        self.assertTrue((self.root / "system/retrobox/bin/retrobox-app").exists())   # Apple Music still needs it
        code, out = run(self.root, "--remove", "apple-music")
        self.assertFalse((self.root / "system/retrobox/bin").exists())
        self.assertNotIn("retrobox", self.target.services())

    def test_installing_twice_changes_nothing_more(self):
        run(self.root, "--yes", "--with", "discord")
        before = sorted(p.relative_to(self.root).as_posix() for p in self.root.rglob("*"))
        run(self.root, "--yes", "--with", "discord")
        self.assertEqual(before, sorted(p.relative_to(self.root).as_posix() for p in self.root.rglob("*")))
        self.assertEqual((self.root / "roms/ports/gamelist.xml").read_text().count("<game>"), 1)

    def test_lights_are_not_offered_without_the_hardware(self):
        code, out = run(self.root, "--yes", "--with", "omen-lights")
        self.assertEqual(code, 1)
        self.assertIn("Not available here", out)
        _code, out = run(self.root, answers="n\n" * 20)
        self.assertNotIn("OMEN", out)

    def test_questions_are_asked_and_answered(self):
        # look n, apple-music n, discord y, six more n, bios n, games n, go ahead y
        code, out = run(self.root, answers="n\nn\ny\n" + "n\n" * 6 + "n\nn\ny\n")
        self.assertEqual(code, 0, out)
        self.assertTrue((self.root / "roms/ports/Discord.sh").exists())
        self.assertFalse((self.root / "themes/retrobox").exists())


class TypedAnswerTests(Drive):
    def test_wifi_is_asked_for_and_written(self):
        # look n, apple-music n, discord n, wifi y + name + password, five more n, bios n, games n, go ahead y
        code, out = run(self.root, answers="n\nn\nn\ny\nHome Net\np@ss {word}\n" + "n\n" * 5 + "n\nn\ny\n")
        self.assertEqual(code, 0, out)
        self.assertEqual(self.target.conf_get("wifi.ssid"), "Home Net")
        self.assertEqual(self.target.conf_get("wifi.key"), "p@ss {word}")
        self.assertEqual(self.target.conf_get("wifi.enabled"), "1")
        self.assertNotIn("p@ss", (self.root / "system/retrobox/installed.json").read_text())

    def test_answers_can_be_given_ahead(self):
        with mock.patch.dict("os.environ", {"RETROBOX_SCRAPER_PASSWORD": "s3cret"}):
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
            for key in ("name", "flatpak", "args", "window", "pad", "description"):
                self.assertIn(key, app, f"{path}: {key}")
            self.assertTrue((path.parent / "tile.png").exists())


if __name__ == "__main__":
    unittest.main()
