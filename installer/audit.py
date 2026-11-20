"""After every install: nothing made for testing stays on a real drive.

Things from testing reached a drive more than once and did harm there:
- the test VM's layout of the Xbox pad (GUID 050000005e040000220b000023050000, button numbers
  from 107) in es_input.cfg: Batocera matched the real pad to it by name, and every face button
  was wrong;
- temporary SSH keys for the administrator, left in system/.ssh/authorized_keys.
So the installer looks once more when it has finished (and after --remove), and takes them off.
(tools/batocera-vm writes nothing to the drive unless asked to with --write; see its tests.)

EmuBox never puts an SSH key on a drive, so every key found there came from testing and is set
aside (into authorized_keys.emubox-removed beside it, where nothing reads it), not deleted. A key
of your own stays when its line ends with the word `emubox-keep`.
"""
from __future__ import annotations

import re
from pathlib import Path

from .target import Target

ES_INPUT = "system/configs/emulationstation/es_input.cfg"
VM_PAD_GUID = "050000005e040000220b000023050000"
VM_FIRST_BUTTON = 107          # the VM's plain form of the pad numbers its buttons from here
SSH_KEYS = "system/.ssh/authorized_keys"
SSH_SET_ASIDE = "system/.ssh/authorized_keys.emubox-removed"
KEEP_WORD = "emubox-keep"
ENTRY = re.compile(r"[ \t]*<inputConfig\b[^>]*?(?:/>|>.*?</inputConfig>)[ \t]*\n?", re.S)


def is_vm_layout(entry: str) -> bool:
    """The test VM's pad layout: its GUID, or the Xbox pad's name with buttons numbered from 107."""
    if f'deviceGUID="{VM_PAD_GUID}"' in entry:
        return True
    if "Xbox Wireless Controller" not in entry:
        return False
    buttons = [int(n) for n in re.findall(r'type="button"\s+id="(\d+)"', entry)]
    return any(n >= VM_FIRST_BUTTON for n in buttons)


def without_vm_layouts(text: str) -> tuple[str, int]:
    """The controllers file without the test VM's layout; and how many entries were taken out."""
    taken = 0

    def drop(match: re.Match) -> str:
        nonlocal taken
        if is_vm_layout(match.group()):
            taken += 1
            return ""
        return match.group()

    return ENTRY.sub(drop, text), taken


def test_keys(text: str) -> tuple[list[str], list[str]]:
    """authorized_keys split into (lines kept, keys to set aside)."""
    kept, removed = [], []
    for line in text.splitlines():
        words = line.split()
        if not words or line.lstrip().startswith("#") or words[-1] == KEEP_WORD:
            kept.append(line)
        else:
            removed.append(line)
    return kept, removed


def audit(target: Target, in_vm: bool = False, say=lambda text: None) -> list[str]:
    """Take testing's leftovers off the drive. What was done, one line each (empty: nothing found).
    Inside the test VM itself (in_vm) its pad layout belongs there and is left alone."""
    done = []
    controllers = target.path(ES_INPUT)
    if not in_vm and controllers.is_file():
        before = controllers.read_text()
        after, taken = without_vm_layouts(before)
        if taken:
            target.write_text(ES_INPUT, after)
            done.append(f"took the test VM's controller layout out of {ES_INPUT} ({taken})")
    keys = target.path(SSH_KEYS)
    if keys.is_file() and not keys.is_symlink():
        kept, removed = test_keys(keys.read_text(errors="replace"))
        if removed:
            aside = target.path(SSH_SET_ASIDE)
            earlier = aside.read_text(errors="replace") if aside.is_file() else ""
            # Set aside first, then the keys file rewritten: a key is never only in memory.
            target.write_text(SSH_SET_ASIDE, earlier + "".join(f"{line}\n" for line in removed), mode=0o600)
            if any(line.strip() and not line.lstrip().startswith("#") for line in kept):
                target.write_text(SSH_KEYS, "".join(f"{line}\n" for line in kept), mode=0o600)
            else:
                keys.unlink()
            done.append(f"set {len(removed)} SSH key(s) aside that EmuBox did not put there "
                        f"({SSH_SET_ASIDE}; end a key's line with '{KEEP_WORD}' to keep it)")
    for line in done:
        say(f"  Testing leftovers: {line}.")
    return done


def running_in_vm() -> bool:
    """Is this Batocera itself, running in the test VM?"""
    try:
        return "QEMU" in Path("/sys/class/dmi/id/sys_vendor").read_text() or \
            "emubox.vm" in Path("/proc/cmdline").read_text()
    except OSError:
        return False

