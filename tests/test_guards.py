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


# --- lint: rules every file in the repository keeps ---------------------------------------

def repo_texts():
    """(path, text) of every text file in the repository, the tests left out (they quote the
    very things the rules forbid)."""
    for path in sorted(REPO.rglob("*")):
        parts = path.relative_to(REPO).parts
        if not path.is_file() or parts[0] in (".git", "tests") or "__pycache__" in parts:
            continue
        try:
            yield path, path.read_text()
        except (UnicodeDecodeError, OSError):
            continue


def process_patterns(text: str) -> list[str]:
    """The pattern of every `pkill -f` / `pgrep -f` in a file, shell or Python."""
    import shlex
    found = []
    for line in text.splitlines():
        for match in re.finditer(r"""(["']?)\b(pkill|pgrep)\b\1""", line):
            before = line[:match.start()]
            if before.lstrip().startswith("#") or " # " in before:   # a comment about them
                continue
            rest = line[match.end():]
            if match.group(1):                                  # Python: ["pkill", "-f", pattern]
                words = [a or b for a, b in re.findall(r'"([^"]*)"|\'([^\']*)\'', rest.split("]")[0])]
            else:
                try:
                    words = shlex.split(rest, comments=True)
                except ValueError:
                    words = rest.split()
            options, pattern = [], None
            for word in words:
                if word == "--" or not word.startswith("-"):
                    if word != "--":
                        pattern = word
                        break
                    continue
                options.append(word)
            if any(o.startswith("-") and not o.startswith("--") and "f" in o for o in options) or "--full" in options:
                found.append(pattern or "")
    return found


class LintTests(unittest.TestCase):
    def test_process_patterns_cannot_match_their_own_command_line(self):
        """`pkill -f wsdd` also matches the shell running it (and an editor or a log line holding
        the word): it killed the wrong programs five times. Anchored (^...) or one bracketed
        letter ([w]sdd) and it can only match the program meant."""
        safe = lambda pattern: pattern.startswith("^") or re.search(r"\[[^\]]\]", pattern)   # noqa: E731
        self.assertEqual(process_patterns('pkill -f -- "[w]ebview.py .*--id $1"\npgrep -f ^qemu x'), ["[w]ebview.py .*--id $1", "^qemu"])
        self.assertEqual(process_patterns('subprocess.run(["pkill", "-9", "-f", "mpv --x"])'), ["mpv --x"])
        self.assertFalse(safe("/usr/bin/wsdd"))
        checked = 0
        for path, text in repo_texts():
            for pattern in process_patterns(text):
                checked += 1
                self.assertTrue(safe(pattern), f"{path.relative_to(REPO)}: pkill/pgrep -f {pattern!r} can match itself")
        self.assertGreater(checked, 5)

    def test_nothing_renames_or_relabels_a_partition(self):
        """A data partition renamed from SHARE hid every game; EmuBox never changes a label."""
        relabel = re.compile(r"\b(e2label|tune2fs\s[^\n]*-L|fatlabel|dosfslabel|exfatlabel|ntfslabel|mlabel|swaplabel|"
                             r"btrfs\s+filesystem\s+label|set-label|sgdisk\s[^\n]*(-c|--change-name)|parted\s[^\n]*\bname\b)")
        for path, text in repo_texts():
            for number, line in enumerate(text.splitlines(), 1):
                code = line.split("#")[0] if path.suffix != ".md" else ""
                self.assertIsNone(relabel.search(code), f"{path.relative_to(REPO)}:{number}: {line.strip()}")


# --- Batocera never touches the PC's other disks ------------------------------------------

class DriveGuardTests(unittest.TestCase):
    """The near-miss: booted from the PC's own disk, Batocera mounted Ubuntu read-write and ran
    ntfsfix on Windows. boot-custom.sh puts a guard in front of Batocera's storage helper; this runs
    that guard against a pretend PC (its /sys, lsblk and blkid) and watches what gets through."""

    PCI = "devices/pci0000:00"
    DISKS = {   # disk -> where the kernel has it, and its partitions' labels
        "nvme0n1": (f"{PCI}/0000:00:1d.0/0000:03:00.0/nvme/nvme0/nvme0n1", {"nvme0n1p2": "", "nvme0n1p6": "BATOCERA", "nvme0n1p7": "SHARE"}),
        "sda": (f"{PCI}/0000:00:17.0/ata1/host0/target0:0:0/0:0:0:0/block/sda", {"sda1": "Windows"}),
        "sdb": (f"{PCI}/0000:00:14.0/usb2/2-1/2-1:1.0/host6/target6:0:0/6:0:0:0/block/sdb", {"sdb1": "GAMES"}),
        "sdc": (f"{PCI}/0000:00:14.0/usb2/2-2/2-2:1.0/host7/target7:0:0/7:0:0:0/block/sdc", {"sdc1": "BATOCERA", "sdc2": "SHARE"}),
    }

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="guardtest")
        self.root = Path(self.tmp.name)
        self.assertNotIn("usb", str(self.root))           # the guard looks for "usb" in the path
        stubs = self.root / "bin"
        stubs.mkdir()
        labels = self.root / "labels"
        labels.mkdir()
        for disk, (where, parts) in self.DISKS.items():
            (self.root / "sys/block").mkdir(parents=True, exist_ok=True)
            (self.root / "sys/class/block").mkdir(parents=True, exist_ok=True)
            (self.root / where).mkdir(parents=True)
            os.symlink(self.root / where, self.root / f"sys/block/{disk}")
            os.symlink(self.root / where, self.root / f"sys/class/block/{disk}")
            (labels / disk).write_text("".join(f"{label}\n" for label in parts.values()))   # lsblk lists them all
            for part, label in parts.items():
                (self.root / where / part).mkdir()
                (self.root / where / part / "partition").write_text("1\n")
                os.symlink(self.root / where / part, self.root / f"sys/class/block/{part}")
                (labels / part).write_text(f"{label}\n")
        for tool in ("lsblk", "blkid"):                  # each prints the labels of the device it is given
            (stubs / tool).write_text(f'#!/bin/sh\nfor a; do last=$a; done\ncat "{labels}/$(basename "$last")" 2>/dev/null\n')
            (stubs / tool).chmod(0o755)
        (stubs / "real").write_text(f'#!/bin/sh\necho "$@" >> "{self.root}/passed"\n')
        (stubs / "real").chmod(0o755)
        guard = block("cat > \"$H\" <<'GUARD'", "GUARD").splitlines()[1:-1]
        text = "\n".join(guard)
        for real, fake in (("/usr/bin/batocera-storage-udev.real", str(stubs / "real")),
                           ("/sys/class/block/", f"{self.root}/sys/class/block/"),
                           ("/sys/block/", f"{self.root}/sys/block/"),
                           ("/var/log/emubox-drive-guard.log", f"{self.root}/guard.log")):
            self.assertIn(real, text)
            text = text.replace(real, fake)
        self.assertEqual(re.findall(r"(?<![\w.-])/(?:sys|usr|var)/", text.replace(str(self.root), "FAKE")), [])   # nothing real
        self.guard = self.root / "guard"
        self.guard.write_text(text + "\n")
        self.guard.chmod(0o755)
        self.env = {**os.environ, "PATH": f"{stubs}:{os.environ['PATH']}"}
        self.env.pop("ID_FS_LABEL", None)

    def tearDown(self):
        self.tmp.cleanup()

    def offer(self, device: str, action: str = "add", **env) -> bool:
        """Batocera's udev rule offering a device to its storage helper: did it get through?"""
        passed = self.root / "passed"
        passed.unlink(missing_ok=True)
        subprocess.run(["bash", str(self.guard), action, device], env={**self.env, **env}, check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return passed.exists() and passed.read_text().split() == [action, device]

    def test_the_pcs_own_disks_are_left_alone(self):
        for device in ("nvme0n1", "nvme0n1p2", "nvme0n1p6", "nvme0n1p7", "sda", "sda1"):
            self.assertFalse(self.offer(device), device)
        self.assertIn("left alone: sda1 (not a USB drive", (self.root / "guard.log").read_text())

    def test_other_batocera_drives_on_usb_are_left_alone(self):
        for device in ("sdc", "sdc1", "sdc2"):
            self.assertFalse(self.offer(device), device)
        self.assertFalse(self.offer("sdb1", ID_FS_LABEL="SHARE"))       # told by udev itself

    def test_a_plain_usb_drive_is_passed_on(self):
        self.assertTrue(self.offer("sdb1"))
        self.assertTrue(self.offer("sdb"))
        self.assertTrue(self.offer("nvme0n1p2", action="remove"))       # only adding is guarded

    def test_batoceras_own_helper_is_kept_once_however_often_the_guard_is_written(self):
        start = block('H=/usr/bin/batocera-storage-udev', "GUARD")
        helper = self.root / "helper"
        helper.write_text("batocera's own\n")
        script = start.replace("H=/usr/bin/batocera-storage-udev", f"H={helper}", 1)
        for _ in range(2):
            subprocess.run(["bash", "-c", script], check=True)
        self.assertEqual((self.root / "helper.real").read_text(), "batocera's own\n")
        self.assertIn("EmuBox drive guard", helper.read_text())


# --- the data partition keeps its label SHARE -----------------------------------------------

class LabelTests(unittest.TestCase):
    """The worst day: the data partition was renamed from SHARE, Batocera took it for a second
    drive, merged /userdata over it and moved every game into .roms_base."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "drive"
        for folder in ("system", "roms/snes"):
            (self.root / folder).mkdir(parents=True)
        self.conf = "audio.volume=45\n"
        (self.root / "system/batocera.conf").write_text(self.conf)

    def tearDown(self):
        self.tmp.cleanup()

    def parts(self, label: str) -> list[dict]:
        return [{"path": "/dev/sdz2", "uuid": "u", "label": label, "fstype": "ext4", "size": "20G",
                 "removable": True, "mounts": [str(self.root)]},
                {"path": "/dev/sdz1", "uuid": "b", "label": "BATOCERA", "fstype": "vfat", "size": "8G",
                 "removable": True, "mounts": []}]

    def test_only_a_partition_labelled_share_is_worked_on(self):
        from installer.target import label_problem
        self.assertEqual(label_problem(self.root, self.parts("SHARE")), "")
        self.assertIn("not SHARE", label_problem(self.root, self.parts("GAMES")))
        self.assertIn("without a label", label_problem(self.root, self.parts("")))
        self.assertEqual(label_problem(self.root / "roms", self.parts("GAMES")), "")   # a folder inside, not the drive
        self.assertEqual(label_problem(self.root, []), "")                               # a plain folder

    def test_the_installer_refuses_a_renamed_data_partition_and_changes_nothing(self):
        import io
        from unittest import mock
        from installer import cli, target as target_module
        out = io.StringIO()
        with mock.patch.object(target_module, "partitions", return_value=self.parts("GAMES")), \
                mock.patch("sys.stdout", out), mock.patch("sys.stdin", io.StringIO("")):
            code = cli.main(["--target", str(self.root), "--yes", "--with", "tweaks"])
        self.assertEqual(code, 1)
        self.assertIn("not SHARE", out.getvalue())
        self.assertEqual((self.root / "system/batocera.conf").read_text(), self.conf)
        self.assertEqual(sorted(p.name for p in (self.root / "system").iterdir()), ["batocera.conf"])

    def test_batocera_drive_refuses_it_too(self):
        stubs = Path(self.tmp.name) / "bin"
        stubs.mkdir()
        listing = {"blockdevices": [{"path": "/dev/sdz", "rm": True, "children": [
            {"path": "/dev/sdz2", "uuid": "u", "label": "GAMES", "fstype": "ext4", "size": "20G", "rm": True,
             "mountpoints": [str(self.root)]}]}]}
        import json
        (stubs / "lsblk").write_text(f"#!/bin/sh\ncat <<'END'\n{json.dumps(listing)}\nEND\n")
        (stubs / "lsblk").chmod(0o755)
        env = {**os.environ, "PATH": f"{stubs}:{os.environ['PATH']}"}
        env.pop("BATOCERA_DRIVE", None)
        done = subprocess.run([sys.executable, str(REPO / "tools/batocera-drive"), str(self.root)],
                              capture_output=True, text=True, env=env)
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("not SHARE", done.stderr)
        listing["blockdevices"][0]["children"][0]["label"] = "SHARE"
        (stubs / "lsblk").write_text(f"#!/bin/sh\ncat <<'END'\n{json.dumps(listing)}\nEND\n")
        done = subprocess.run([sys.executable, str(REPO / "tools/batocera-drive"), str(self.root)],
                              capture_output=True, text=True, env=env)
        self.assertEqual((done.returncode, done.stdout.strip()), (0, str(self.root)))

    def merged_warning(self, roms_base: bool, boot_conf: str) -> str:
        """Run the boot guard's label check against a pretend /userdata and /boot; what it logged."""
        text = (REPO / "components/drive-guard/files/emubox_bootguard").read_text()
        start = text.index("# --- the data partition's label")
        code = text[start:text.index("\nexit 0", start)]
        folder = Path(self.tmp.name)
        for real, fake in (("/userdata/.roms_base", folder / "userdata/.roms_base"),
                           ("/boot/batocera-boot.conf", folder / "batocera-boot.conf"),
                           ("/var/log/emubox-boot.log", folder / "boot.log")):
            self.assertIn(real, code)
            code = code.replace(real, str(fake))
        (folder / "userdata").mkdir(exist_ok=True)
        if roms_base:
            (folder / "userdata/.roms_base").mkdir(exist_ok=True)
        elif (folder / "userdata/.roms_base").exists():
            (folder / "userdata/.roms_base").rmdir()
        (folder / "batocera-boot.conf").write_text(boot_conf)
        for log in ("emubox.log", "boot.log"):
            (folder / log).unlink(missing_ok=True)
        script = f'LOG={folder}/emubox.log\nsay() {{ echo "$*" >> "$LOG"; }}\n{code}\n'
        subprocess.run(["bash", "-c", script], check=True)
        logged = [(folder / log).read_text() if (folder / log).exists() else "" for log in ("emubox.log", "boot.log")]
        self.assertEqual("WARNING" in logged[0], "WARNING" in logged[1])
        return logged[0]

    def test_a_merged_games_folder_is_warned_about_loudly_at_start_up(self):
        self.assertEqual(self.merged_warning(False, "autoresize=false\n"), "")
        self.assertIn("label must be SHARE", self.merged_warning(True, ""))
        self.assertIn("WARNING", self.merged_warning(False, "autoresize=false\nmergerfs.roms=/media/x\n"))
        self.assertEqual(self.merged_warning(False, "#mergerfs.roms=/media/x\n"), "")


# --- nothing made for testing stays on a real drive ------------------------------------------

def install(root: Path, *args: str) -> tuple[int, str]:
    """Run the installer on the pretend drive, as from a PC without the special hardware."""
    import io
    from unittest import mock
    from installer import cli
    out = io.StringIO()
    with mock.patch("sys.stdin", io.StringIO("")), mock.patch("sys.stdout", out), \
            mock.patch.object(cli.Host, "usb_devices", return_value=set()), \
            mock.patch.object(cli.Host, "paired_bluetooth_devices", return_value=[]), \
            mock.patch.dict(os.environ, {"EMUBOX_DOWNLOAD_LATER": "1", "EMUBOX_SOUNDS": "none", "EMUBOX_OFFLINE": "1"}):
        code = cli.main(["--target", str(root), *args])
    return code, out.getvalue()


class TestLeftoverTests(unittest.TestCase):
    """Three times things from testing reached a real drive: the VM's pad layout (every face
    button of the real Xbox pad wrong), temporary root SSH keys, batocera-vm leftovers."""

    VM_LAYOUT = ('\t<inputConfig type="joystick" deviceName="Xbox Wireless Controller" deviceGUID="050000005e040000220b000023050000">\n'
                 '\t\t<input name="b" type="button" id="107" value="1" code="304" />\n\t</inputConfig>\n')
    NAMED_LIKE_IT = ('\t<inputConfig type="joystick" deviceName="Xbox Wireless Controller" deviceGUID="0300aaaa">\n'
                     '\t\t<input name="a" type="button" id="108" value="1" code="305" />\n\t</inputConfig>\n')
    REAL_PAD = ('\t<inputConfig type="joystick" deviceName="Xbox Wireless Controller" deviceGUID="050000005e040000e002000003090000">\n'
                '\t\t<input name="b" type="button" id="0" value="1" code="304" />\n\t</inputConfig>\n')
    MINE = '\t<inputConfig type="keyboard" deviceName="Keyboard" deviceGUID="-1" />\n'

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "SHARE"
        for folder in ("system/configs/emulationstation", "system/.ssh", "roms/ports"):
            (self.root / folder).mkdir(parents=True)
        (self.root / "system/batocera.conf").write_text("")
        self.pads = self.root / "system/configs/emulationstation/es_input.cfg"
        self.keys = self.root / "system/.ssh/authorized_keys"

    def tearDown(self):
        self.tmp.cleanup()

    def test_the_vms_pad_layout_is_taken_off_after_any_install(self):
        self.pads.write_text('<?xml version="1.0"?>\n<inputList>\n' + self.MINE + self.VM_LAYOUT + self.REAL_PAD +
                             self.NAMED_LIKE_IT + "</inputList>\n")
        code, said = install(self.root, "--yes", "--with", "tweaks")     # not the console tools
        self.assertEqual(code, 0, said)
        text = self.pads.read_text()
        self.assertNotIn("220b000023050000", text)
        self.assertNotIn('id="108"', text)                               # numbered like the VM's form
        self.assertIn(self.MINE, text)
        self.assertIn(self.REAL_PAD, text)                               # the real pad's own entry stays
        import xml.etree.ElementTree as ET
        self.assertEqual(len(ET.fromstring(text)), 2)
        self.assertIn("test VM's controller layout", said)

    def test_inside_the_vm_itself_its_layout_stays(self):
        from installer import audit
        from installer.target import Target
        self.pads.write_text('<inputList>\n' + self.VM_LAYOUT + "</inputList>\n")
        self.assertEqual(audit.audit(Target(self.root), in_vm=True), [])
        self.assertIn("220b000023050000", self.pads.read_text())

    def test_ssh_keys_emubox_did_not_put_there_are_set_aside(self):
        self.keys.write_text("# a comment\nssh-ed25519 AAAAtest root@vm-test\nssh-ed25519 AAAAmine me@pc emubox-keep\n")
        code, said = install(self.root, "--yes", "--with", "tweaks")
        self.assertEqual(code, 0, said)
        self.assertEqual(self.keys.read_text(), "# a comment\nssh-ed25519 AAAAmine me@pc emubox-keep\n")
        aside = self.root / "system/.ssh/authorized_keys.emubox-removed"
        self.assertEqual(aside.read_text(), "ssh-ed25519 AAAAtest root@vm-test\n")   # set aside, not lost
        self.assertEqual(aside.stat().st_mode & 0o777, 0o600)
        self.keys.write_text("ssh-rsa AAAAother root@vm\n")
        install(self.root, "--remove", "tweaks")                         # also after taking something off
        self.assertFalse(self.keys.exists())
        self.assertEqual(aside.read_text().count("ssh-"), 2)


class VmToolTests(unittest.TestCase):
    """tools/batocera-vm boots the stick in a window: in test mode nothing reaches the stick, and
    it never starts (or writes) the PC's own disk."""

    VM = REPO / "tools/batocera-vm"

    def test_test_mode_is_the_default_and_only_write_mode_writes(self):
        text = self.VM.read_text()
        self.assertIn("\nMODE=test\n", text)
        self.assertEqual(re.findall(r"MODE=write", text), ["MODE=write"])
        self.assertIn("--write) MODE=write ;;", text)
        self.assertIn("\nsnap=on\n", text)
        self.assertEqual(re.findall(r"snap=off", text), ["snap=off"])
        self.assertIn('if [ "$MODE" = write ]; then snap=off;', text)
        self.assertIn("snapshot=$snap", text)
        self.assertEqual(len(re.findall(r"-drive ", text)), 1)              # the stick is the only disk it is given
        self.assertIn('need=r; [ "$MODE" = write ] && need=rw', text)       # read access only, unless writing

    def choose(self, *args: str, disks: dict) -> subprocess.CompletedProcess:
        """Run the part of batocera-vm that picks the drive, against a pretend lsblk."""
        text = self.VM.read_text()
        code = text[text.index("\nMODE=test\n"):text.index("# --- (the tests run")]
        with tempfile.TemporaryDirectory() as folder:
            stub = Path(folder) / "lsblk"
            rows = "\n".join(f"/dev/{p} BATOCERA" for disk, (_rm, parts) in disks.items() for p in parts)
            parents = "".join(f"*/{p}) echo {disk} ;;\n" for disk, (_rm, parts) in disks.items() for p in parts)
            removable = "".join(f"*/{disk}) echo {rm} ;;\n" for disk, (rm, _parts) in disks.items())
            stub.write_text(f'#!/bin/bash\ncase "$*" in\n-rno*) printf "%s\\n" "{rows}" ;;\n'
                            f'-no\\ PKNAME*) case "$3" in\n{parents}esac ;;\n'
                            f'-dno\\ RM*) case "$3" in\n{removable}esac ;;\nesac\n')
            stub.chmod(0o755)
            env = {**os.environ, "PATH": f"{folder}:{os.environ['PATH']}"}
            script = "set -euo pipefail\n" + code + '\necho "chose $MODE $disk"\n'
            return subprocess.run(["bash", "-c", script, "batocera-vm", *args], capture_output=True, text=True, env=env)

    def test_the_pcs_own_disk_is_never_chosen(self):
        both = {"nvme0n1": (0, ["nvme0n1p6"]), "sdb": (1, ["sdb1"])}
        done = self.choose(disks=both)
        self.assertEqual(done.stdout.strip(), "chose test /dev/sdb")
        self.assertEqual(self.choose("--write", disks=both).stdout.strip(), "chose write /dev/sdb")
        done = self.choose(disks={"nvme0n1": (0, ["nvme0n1p6"])})                # only Batocera on the PC's own disk
        self.assertNotEqual(done.returncode, 0)
        self.assertNotIn("chose", done.stdout)
        self.assertIn("No removable drive", done.stderr)
        self.assertNotEqual(self.choose("--wrte", disks=both).returncode, 0)    # a typo is not write mode


# --- a file of yours is replaced only by a checked copy ---------------------------------------

class CopyTests(unittest.TestCase):
    """Games, BIOS files and backups: nothing is deleted or replaced until its copy is checked
    (size and checksum, read back from the drive), and a source is only ever read."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.folder = Path(self.tmp.name)
        self.source = self.folder / "library/snes/Game.sfc"
        self.source.parent.mkdir(parents=True)
        self.source.write_bytes(b"the new, longer version of the game")

    def tearDown(self):
        self.tmp.cleanup()

    def corrupted(self):
        """The drive hands back something else than was written (failing, or a fake-capacity stick)."""
        from unittest import mock
        from installer import target as target_module
        real = target_module._sha256_of
        return mock.patch.object(target_module, "_sha256_of",
                                 side_effect=lambda path: "0" * 64 if ".emubox-part" in Path(path).name else real(path))

    def leftovers(self) -> list[str]:
        return [p.name for p in self.folder.rglob("*.emubox-part")]

    def test_a_bad_copy_never_replaces_what_was_there(self):
        from installer.target import verified_copy
        destination = self.folder / "drive/Game.sfc"
        destination.parent.mkdir()
        destination.write_bytes(b"old game")
        with self.corrupted(), self.assertRaises(OSError):
            verified_copy(self.source, destination)
        self.assertEqual(destination.read_bytes(), b"old game")
        self.assertEqual(self.source.read_bytes(), b"the new, longer version of the game")
        self.assertEqual(self.leftovers(), [])
        verified_copy(self.source, destination)                       # a good copy does replace it
        self.assertEqual(destination.read_bytes(), self.source.read_bytes())
        self.assertEqual(self.leftovers(), [])

    def test_installing_games_and_backing_them_up_check_every_copy(self):
        from installer import library
        from installer.target import Target
        drive = self.folder / "drive"
        for part in ("system", "roms/snes"):
            (drive / part).mkdir(parents=True)
        (drive / "system/batocera.conf").write_text("")
        (drive / "roms/snes/Game.sfc").write_bytes(b"old game")      # another size: it would be replaced
        games = library.Library(self.folder / "library", "games")
        selection = [(system, system.items) for system in games.systems()]
        with self.corrupted(), self.assertRaises(OSError):
            library.install(games, selection, Target(drive), lambda _line: None)
        self.assertEqual((drive / "roms/snes/Game.sfc").read_bytes(), b"old game")
        backup = self.folder / "backup"
        (backup / "snes").mkdir(parents=True)
        (backup / "snes/Game.sfc").write_bytes(b"an older backup")
        on_drive = library.Library(drive, "games")
        with self.corrupted(), self.assertRaises(OSError):
            library.backup([(s, s.items) for s in on_drive.systems()], backup, lambda _line: None)
        self.assertEqual((backup / "snes/Game.sfc").read_bytes(), b"an older backup")
        self.assertEqual(self.leftovers(), [])

    def test_batocera_add_replaces_a_game_only_with_a_checked_copy(self):
        import importlib.machinery
        import importlib.util
        import io
        from unittest import mock
        loader = importlib.machinery.SourceFileLoader("batocera_add", str(REPO / "tools/batocera-add"))
        spec = importlib.util.spec_from_loader("batocera_add", loader)
        tool = importlib.util.module_from_spec(spec)
        loader.exec_module(tool)
        drive = self.folder / "drive"
        (drive / "roms/snes").mkdir(parents=True)
        (drive / "roms/snes/Game.sfc").write_bytes(b"old game")
        folder_game = self.folder / "library/psx/Big Game"
        folder_game.mkdir(parents=True)
        (folder_game / "disc.bin").write_bytes(b"disc")
        args = ["batocera-add", "--force", "-s", "snes", str(self.source)]
        with mock.patch.object(tool, "find_drive", return_value=str(drive)), mock.patch("sys.stdout", io.StringIO()) as out:
            with self.corrupted(), mock.patch("sys.argv", args):
                tool.main()
            self.assertIn("FAILED Game.sfc", out.getvalue())
            self.assertEqual((drive / "roms/snes/Game.sfc").read_bytes(), b"old game")
            with mock.patch("sys.argv", args):
                tool.main()
            self.assertEqual((drive / "roms/snes/Game.sfc").read_bytes(), self.source.read_bytes())
            with mock.patch("sys.argv", ["batocera-add", "-s", "snes", str(folder_game)]):
                tool.main()                                             # a game that is a folder
            self.assertEqual((drive / "roms/snes/Big Game/disc.bin").read_bytes(), b"disc")
        self.assertTrue(self.source.exists() and (folder_game / "disc.bin").exists())   # sources stay
        self.assertEqual(self.leftovers(), [])

    def test_batocera_backup_never_deletes_and_never_writes_over_a_backup(self):
        script = "\n".join(line for line in (REPO / "tools/batocera-backup").read_text().splitlines()
                           if not line.lstrip().startswith("#"))
        for never in ("--delete", "--remove-source-files", "rm ", "rmdir", "mv "):
            self.assertNotIn(never, script)
        import datetime
        drive = self.folder / "drive"
        for part in ("system/configs", "roms", "saves", "screenshots"):
            (drive / part).mkdir(parents=True)
        (drive / "system/batocera.conf").write_text("")
        (drive / "saves/game.srm").write_text("my save")
        home = self.folder / "home"
        now = datetime.datetime.now()
        earlier = []
        for moment in (now, now + datetime.timedelta(minutes=1)):     # whichever minute it runs in
            backup = home / "Batocera-Backups" / moment.strftime("%Y-%m-%d_%H%M")
            (backup / "saves").mkdir(parents=True, exist_ok=True)
            (backup / "saves/game.srm").write_text("an earlier save")
            earlier.append(backup / "saves/game.srm")
        done = subprocess.run(["bash", str(REPO / "tools/batocera-backup"), str(drive)], capture_output=True, text=True,
                              env={**os.environ, "HOME": str(home)})
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("already", done.stderr)
        self.assertEqual([p.read_text() for p in earlier], ["an earlier save"] * 2)
        self.assertEqual((drive / "saves/game.srm").read_text(), "my save")
