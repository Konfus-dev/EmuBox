"""Guards against the worst outcomes: a wiped drive, a drive that cannot start, menus that never
come up. Each test proves one guard holds; see docs/details.md (Safety) for why each exists."""
import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
BOOT_CUSTOM = REPO / "components/drive-guard/files/boot-custom.sh"
GRUB = Path(__file__).parent / "fixtures/batocera-grub.cfg"

import sys  # noqa: E402
sys.path.insert(0, str(REPO))
from installer.target import Target  # noqa: E402


def block(start: str, end: str) -> str:
    """The lines of boot-custom.sh from the one starting with `start` to the next `end` line."""
    lines = BOOT_CUSTOM.read_text().splitlines()
    first = next(i for i, line in enumerate(lines) if line.strip().startswith(start))
    last = next(i for i in range(first + 1, len(lines)) if lines[i].strip() == end)
    return "\n".join(lines[first:last + 1])


class DriveTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        for folder in ("system", "roms/snes", "saves", "bios", "system/emubox/old"):
            (self.root / folder).mkdir(parents=True, exist_ok=True)
        (self.root / "system/batocera.conf").write_text("")
        (self.root / "roms/snes/game.sfc").write_text("a game")
        self.target = Target(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_games_saves_bios_and_the_drive_itself_are_never_removed_whole(self):
        for gone in ("", ".", "roms", "roms/snes", "saves", "bios", "system", "roms/../saves"):
            with self.assertRaises(ValueError, msg=gone):
                self.target.remove(gone)
        self.assertTrue((self.root / "roms/snes/game.sfc").exists())

    def test_nothing_outside_the_drive_is_touched(self):
        with self.assertRaises(ValueError):
            self.target.remove("../outside")
        with self.assertRaises(ValueError):
            self.target.path("/etc/passwd")

    def test_ordinary_leftovers_still_go(self):
        self.assertTrue(self.target.remove("system/emubox/old"))
        (self.root / "roms/snes/old-tile.sh").write_text("")
        self.assertTrue(self.target.remove("roms/snes/old-tile.sh"))   # one file inside a games folder is fine

    def test_only_a_real_batocera_folder_is_a_target(self):
        self.assertTrue(Target.looks_right(self.root))
        self.assertFalse(Target.looks_right(Path("/")))
        self.assertFalse(Target.looks_right(Path.home()))


class BootTests(unittest.TestCase):
    def test_boot_custom_is_valid_shell_and_always_finishes(self):
        subprocess.run(["bash", "-n", str(BOOT_CUSTOM)], check=True)
        text = BOOT_CUSTOM.read_text()
        self.assertNotIn("set -e", text)          # one failing step must not stop the rest of start-up
        self.assertRegex(text, r"exit 0\s*$")

    def _edit_grub(self, original: str, sed_damage: str = "") -> tuple[str, str]:
        """Run boot-custom.sh's boot-menu edit on a copy of `original`; optionally damage the edit."""
        with tempfile.TemporaryDirectory() as folder:
            g = Path(folder) / "grub.cfg"
            g.write_text(original)
            code = block("for g in /boot/EFI", "done")
            code = re.sub(r"^\s*for g in [^;]*;", 'for g in "$G";', code, count=1)
            if sed_damage:
                code = code.replace("sed -e ", f"sed -e '{sed_damage}' -e ", 1)
            code = code.replace("/var/log/emubox-boot.log", str(Path(folder) / "boot.log"))
            script = "mount() { return 0; }\nsync() { :; }\n" + code
            env = {**os.environ, "G": str(g)}
            subprocess.run(["bash", "-c", script], check=True, env=env, cwd=folder,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            log = (Path(folder) / "boot.log").read_text() if (Path(folder) / "boot.log").exists() else ""
            return g.read_text(), "\n".join(sorted(p.name for p in Path(folder).iterdir())) + "\n" + log

    def test_the_boot_menu_edit_keeps_every_entry(self):
        original = GRUB.read_text()
        edited, files = self._edit_grub(original)
        self.assertNotIn("echo Booting Batocera", edited)
        self.assertIn("set timeout_style=hidden", edited)
        self.assertEqual(edited.count("menuentry"), original.count("menuentry"))
        self.assertEqual(edited.count("linux /boot/linux"), original.count("linux /boot/linux"))
        self.assertIn("grub.cfg.emubox-before", files)                  # the original is kept beside it
        again, _ = self._edit_grub(edited)
        self.assertEqual(again, edited)                                 # and it is done once

    def test_a_damaging_edit_is_never_put_in_place(self):
        original = GRUB.read_text()
        for damage in ("/linux/d", "/menuentry/d", "$d", "s/initrd/initrX/", "/^}/d"):
            edited, files = self._edit_grub(original, damage)
            self.assertEqual(edited, original, damage)
            self.assertNotIn("grub.cfg.emubox-new", files)
            self.assertNotIn("emubox-want", files)
            self.assertIn("did not check out", files)                    # and the log says so

    def test_the_menus_start_even_when_the_music_helper_is_broken(self):
        wrapper = block("cat > /usr/bin/emubox-es", "ES").splitlines()[1:-1]
        with tempfile.TemporaryDirectory() as folder:
            helper = Path(folder) / "esquiet.py"
            script = Path(folder) / "emubox-es"
            script.write_text("\n".join(wrapper).replace("/userdata/system/emubox/lib/esquiet.py", str(helper)))
            for broken in ("this is not python (", None):     # damaged file, missing file
                if broken is None:
                    helper.unlink(missing_ok=True)
                else:
                    helper.write_text(broken)
                out = subprocess.run(["sh", str(script), "echo", "menus started"], capture_output=True, text=True)
                self.assertEqual(out.stdout.strip(), "menus started")
