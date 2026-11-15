"""Vault tests: its settings, the downloads watcher and the install command (no screen needed).

    python3 -m unittest discover tests
"""
import importlib.util
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "components/console/files/lib"))   # where vault.py finds the console tools
import space  # noqa: E402
spec = importlib.util.spec_from_file_location("vault", REPO / "components/vault/files/vault.py")
vault = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vault)

ES_SYSTEMS = """<systemList>
  <system><name>psx</name><fullname>PlayStation</fullname><extension>.cue .chd .zip</extension></system>
  <system><name>gba</name><fullname>Game Boy Advance</fullname><extension>.gba .zip</extension></system>
</systemList>"""


class VaultTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.home = self.root / "vault"
        self.games = self.root / "roms"
        for folder in ("psx", "gba", "homemade", "store", ".roms_base"):
            (self.games / folder).mkdir(parents=True)
        self.config = self.root / "es_systems.cfg"
        self.config.write_text(ES_SYSTEMS)

    def run_vault(self, *args):
        return vault.main(["--home", str(self.home), *args])

    def test_pages_are_added_changed_and_removed(self):
        self.assertEqual(vault.Settings(self.home).pages, vault.DEFAULT_PAGES)
        self.run_vault("add", "Shop", "shop.example/games")
        self.run_vault("add", "shop", "https://shop.example/new")
        pages = vault.Settings(self.home).pages
        self.assertEqual(pages, [{"name": "Shop", "url": "https://shop.example/new"}])
        self.run_vault("add", "Other", "https://other.example")
        self.assertEqual(self.run_vault("rename", "other", "My Favourite Shop"), 0)
        self.assertEqual(self.run_vault("rename", "Nope", "X"), 1)
        self.assertEqual(vault.Settings(self.home).pages[-1]["name"], "My Favourite Shop")
        self.run_vault("rename", "My Favourite Shop", "Other")
        self.assertEqual(self.run_vault("remove", "Shop"), 0)
        self.assertEqual(self.run_vault("remove", "Shop"), 1)
        self.assertEqual([p["name"] for p in vault.Settings(self.home).pages], ["Other"])

    def test_command_and_downloads_can_be_set_and_reset(self):
        self.run_vault("command", "echo hi")
        self.run_vault("downloads", str(self.root / "dl"))
        settings = vault.Settings(self.home)
        self.assertEqual((settings.command, settings.downloads), ("echo hi", self.root / "dl"))
        self.run_vault("reset")
        settings = vault.Settings(self.home)
        self.assertEqual((settings.command, settings.downloads), (vault.DEFAULT_COMMAND, self.home / "downloads"))

    def test_systems_are_the_game_folders_with_batoceras_names(self):
        found = vault.systems(self.games, (str(self.root / "missing.cfg"), str(self.config)))
        self.assertEqual([(s["folder"], s["name"]) for s in found],
                         [("gba", "Game Boy Advance"), ("homemade", "homemade"), ("psx", "PlayStation")])
        ordered, likely = vault.likely_first(found, "Game.CHD")
        self.assertEqual((ordered[0]["folder"], likely, len(ordered)), ("psx", 1, 3))
        self.assertEqual(vault.likely_first(found, "Game.zip")[1], 0)

    def test_the_console_is_read_off_the_page(self):
        found = vault.systems(self.games, (str(self.config),))
        found += [{"folder": "ps2", "name": "PlayStation 2", "types": set()}, {"folder": "gb", "name": "Game Boy", "types": set()}]
        pick = lambda page: (vault.from_page(found, page) or {}).get("folder")   # noqa: E731
        self.assertEqual(pick("Vimm's Lair: The Vault - PLAYSTATION 2 - Some Game https://site.example/vault/123"), "ps2")
        self.assertEqual(pick("Some Game (playstation) download"), "psx")
        self.assertEqual(pick("Great GBA roms https://site.example/"), "gba")          # a short name the system also goes by
        self.assertEqual(pick("Game Boy Advance - Some Game"), "gba")                  # the longer name wins over "Game Boy"
        self.assertEqual(pick("Game Boy - Some Game"), "gb")
        self.assertIsNone(vault.from_page(found, "A page about cooking, with gbazaar in its address"))

    def test_a_download_is_noticed_once_it_stops_changing(self):
        downloads = self.home / "downloads"
        downloads.mkdir(parents=True)
        watcher = vault.Watcher(downloads)
        (downloads / "game.chd").write_text("x")
        (downloads / "other.zip.part").write_text("x")
        (downloads / "busy.iso").write_text("x")
        watcher.writing.add("busy.iso")
        self.assertEqual(watcher.ready(now=100), [])
        self.assertEqual(watcher.ready(now=101), [])
        self.assertEqual(watcher.ready(now=100 + vault.SETTLE_S), [downloads / "game.chd"])
        (downloads / "game.chd").write_text("more")   # still growing after all
        self.assertEqual(watcher.ready(now=110), [])
        watcher.writing.discard("busy.iso")
        watcher.finished.add("busy.iso")              # our own download: no waiting
        self.assertEqual(watcher.ready(now=110.1), [downloads / "busy.iso"])
        watcher.left.update(("busy.iso", "game.chd"))
        self.assertEqual(watcher.ready(now=200), [])

    def test_the_command_moves_the_download_into_the_system(self):
        settings = vault.Settings(self.home)
        settings.downloads.mkdir(parents=True)
        file = settings.downloads / "My Game (USA).chd"
        file.write_text("x")
        worked, said = vault.run_command(settings.command, settings, file, "psx", str(self.games))
        self.assertTrue(worked, said)
        self.assertTrue((self.games / "psx" / file.name).is_file())
        self.assertFalse(file.exists())
        worked, said = vault.run_command("echo no >&2; exit 3", settings, file, "psx", str(self.games))
        self.assertEqual((worked, said), (False, "no"))

    def test_a_full_drive_is_explained_not_crashed_into(self):
        gb = 1024 ** 3
        with mock.patch.object(space.shutil, "disk_usage", return_value=mock.Mock(total=58 * gb, free=2 * gb)):
            self.assertEqual(space.summary(self.root), "2.0 GB free of 58 GB")
            self.assertEqual(space.no_room(1 * gb, self.root), "")
            self.assertIn("needs 5.0 GB and 1.7 GB can be used", space.no_room(5 * gb, self.root, "Game.iso"))
        with mock.patch.object(space.shutil, "disk_usage", return_value=mock.Mock(total=58 * gb, free=10 * 1024 ** 2)):
            self.assertIn("The drive is full (10 MB free)", space.no_room(1, self.root, "Game.iso"))
        with mock.patch.object(space.shutil, "disk_usage", side_effect=OSError):
            self.assertEqual((space.summary(self.root), space.no_room(1, self.root)), ("", ""))   # unknown: do not block
        missing = self.home / "downloads" / "gone.chd"
        self.assertIn("no longer in downloads", vault.move_problem(missing, self.games / "psx"))

    def test_the_menu_indicator_is_redrawn_only_in_themes_that_have_one(self):
        ours, other = self.root / "themes/emubox/space.xml", self.root / "themes/other/space.xml"
        for file, text in ((ours, space.MARK), (other, "<theme/>")):
            file.parent.mkdir(parents=True)
            file.write_text(text)
        gb = 1024 ** 3
        with mock.patch.object(space.shutil, "disk_usage", return_value=mock.Mock(total=50 * gb, free=5 * gb)):
            self.assertEqual(space.draw_indicator(self.root / "themes", self.root), [ours])
        text = ours.read_text()
        self.assertIn("5.0 GB FREE", text)
        self.assertIn("ff7a3cff", text)                  # nine tenths full: the warning colour
        self.assertEqual(other.read_text(), "<theme/>")
        ET.fromstring(text)

    def test_an_archive_is_unpacked_where_the_system_does_not_play_archives(self):
        import zipfile
        disc = {"folder": "gamecube", "name": "GameCube", "types": {".iso", ".ciso"}}
        cartridge = {"folder": "gba", "name": "Game Boy Advance", "types": {".gba", ".zip", ".7z"}}
        self.assertTrue(vault.needs_unpacking(Path("Game.7z"), disc))
        self.assertTrue(vault.needs_unpacking(Path("Game.ZIP"), disc))
        self.assertFalse(vault.needs_unpacking(Path("Game.zip"), cartridge))      # played as it is
        self.assertFalse(vault.needs_unpacking(Path("Game.iso"), disc))
        self.assertFalse(vault.needs_unpacking(Path("Game.zip"), {"folder": "x", "name": "x", "types": set()}))   # unknown system: leave it
        folder = self.games / "gamecube"
        folder.mkdir()
        archive = folder / "Game (USA).zip"
        with zipfile.ZipFile(archive, "w") as packed:
            packed.writestr("Game (USA).ciso", "disc")
            packed.writestr("Site Note.txt", "hello")
        ok, what = vault.unpack(archive)
        self.assertEqual((ok, what), (True, "Game (USA).ciso"))
        self.assertEqual(sorted(p.name for p in folder.iterdir()), ["Game (USA).ciso"])   # the archive and the note are gone
        broken = folder / "Broken.zip"
        broken.write_text("not an archive")
        ok, what = vault.unpack(broken)
        self.assertFalse(ok)
        self.assertTrue(broken.exists())                                              # nothing is lost when it fails

    def test_names_do_not_collide(self):
        (self.home).mkdir()
        (self.home / "a.zip").write_text("x")
        self.assertEqual(vault.free_name(self.home, "a.zip").name, "a (1).zip")
        self.assertEqual(vault.free_name(self.home, "../../etc/x").name, "_.._etc_x")


if __name__ == "__main__":
    unittest.main()
