"""The Batocera data folder we install into, and the few files of it we edit.

Inside Batocera it is /userdata; from another PC it is wherever the drive's
SHARE partition is mounted. Everything RetroBox installs lives here, which
is the part Batocera's own updates leave alone.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from xml.sax.saxutils import quoteattr

LIVE_ROOT = Path("/userdata")
MOUNT_PARENTS = ("/run/media", "/media", "/mnt")
MANIFEST = "system/retrobox/installed.json"


class Target:
    def __init__(self, root: Path):
        self.root = Path(root).resolve()
        self._owner_cache: dict[Path, tuple[int, int]] = {}

    # --- finding it ---------------------------------------------------------------

    @staticmethod
    def looks_right(path: Path) -> bool:
        return (path / "system" / "batocera.conf").is_file() and (path / "roms").is_dir()

    @classmethod
    def find(cls) -> list[Path]:
        """Batocera data folders on this machine: /userdata itself, or mounted drives."""
        if cls.looks_right(LIVE_ROOT):
            return [LIVE_ROOT]
        found = []
        for parent in MOUNT_PARENTS:
            for pattern in ("*", "*/*"):
                found += [p for p in sorted(Path(parent).glob(pattern)) if cls.looks_right(p)]
        return list(dict.fromkeys(found))

    @property
    def live(self) -> bool:
        """True when we are running on Batocera itself, not preparing a drive."""
        return self.root == LIVE_ROOT and Path("/usr/bin/batocera-info").exists()

    def writable(self) -> bool:
        return os.access(self.root / "system", os.W_OK) and os.access(self.root / "roms", os.W_OK)

    def free_bytes(self) -> int:
        return shutil.disk_usage(self.root).free

    # --- files ----------------------------------------------------------------------

    def path(self, relative: str) -> Path:
        full = (self.root / relative).resolve()
        if full != self.root and self.root not in full.parents:
            raise ValueError(f"{relative} is outside the Batocera folder")
        return full

    def _adopt(self, path: Path) -> None:
        """Give a new file the owner of the folder it joined (drives are often not root's)."""
        if os.geteuid() != 0:
            return
        parent = path.parent
        if parent not in self._owner_cache:
            info = parent.stat()
            self._owner_cache[parent] = (info.st_uid, info.st_gid)
        os.chown(path, *self._owner_cache[parent])

    def make_dir(self, path: Path) -> None:
        missing = []
        while not path.exists():
            missing.append(path)
            path = path.parent
        for folder in reversed(missing):
            folder.mkdir()
            self._adopt(folder)

    def copy_file(self, source: Path, relative: str, mode: int | None = None) -> str:
        """Copy one file in. Returns the relative path, for the record of what we installed."""
        destination = self.path(relative)
        self.make_dir(destination.parent)
        shutil.copyfile(source, destination)
        os.chmod(destination, mode if mode is not None else 0o644)
        self._adopt(destination)
        return relative

    def copy(self, source: Path, relative: str, mode: int | None = None) -> list[str]:
        """Copy a file or a whole folder in."""
        if source.is_file():
            return [self.copy_file(source, relative, mode)]
        written = []
        for item in sorted(source.rglob("*")):
            if item.is_file() and "__pycache__" not in item.parts:
                written.append(self.copy_file(item, f"{relative}/{item.relative_to(source).as_posix()}", mode))
        return written

    def write_text(self, relative: str, text: str, mode: int = 0o644) -> str:
        destination = self.path(relative)
        self.make_dir(destination.parent)
        destination.write_text(text)
        os.chmod(destination, mode)
        self._adopt(destination)
        return relative

    def remove(self, relative: str) -> bool:
        path = self.path(relative)
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path)
        elif path.exists() or path.is_symlink():
            path.unlink()
        else:
            return False
        return True

    # --- batocera.conf ----------------------------------------------------------------

    @property
    def _conf(self) -> Path:
        return self.root / "system" / "batocera.conf"

    def conf_get(self, key: str) -> str | None:
        value = None
        for line in self._conf.read_text().splitlines():
            if line.startswith(f"{key}="):
                value = line.split("=", 1)[1]   # the last one wins, as in Batocera
        return value

    def conf_set(self, key: str, value: str) -> None:
        lines = self._conf.read_text().splitlines()
        seen = False
        for index, line in enumerate(lines):
            if line.startswith(f"{key}="):
                lines[index] = f"{key}={value}"
                seen = True
        if not seen:
            lines.append(f"{key}={value}")
        self._conf.write_text("\n".join(lines) + "\n")

    def services(self) -> list[str]:
        return (self.conf_get("system.services") or "").split()

    def enable_service(self, name: str) -> None:
        """Switch a service on, as Main menu > System Settings > Services would."""
        if name not in self.services():
            self.conf_set("system.services", " ".join([*self.services(), name]))
        if self.live:
            subprocess.run(["batocera-services", "start", name], check=False)

    def disable_service(self, name: str) -> None:
        if name in self.services():
            if self.live:
                subprocess.run(["batocera-services", "stop", name], check=False)
            self.conf_set("system.services", " ".join(s for s in self.services() if s != name))

    # --- EmulationStation settings ------------------------------------------------------

    def es_setting(self, name: str, value: str | bool | int) -> None:
        """Set a setting of the menu program (the theme, the scraper account...)."""
        path = self.path("system/configs/emulationstation/es_settings.cfg")
        kind = "bool" if isinstance(value, bool) else "int" if isinstance(value, int) else "string"
        shown = str(value).lower() if isinstance(value, bool) else str(value)
        line = f"\t<{kind} name={quoteattr(name)} value={quoteattr(shown)} />"
        if path.exists():
            text = path.read_text()
        else:
            self.make_dir(path.parent)
            text = '<?xml version="1.0"?>\n<config>\n</config>\n'
        pattern = re.compile(rf'^[ \t]*<\w+ name="{re.escape(name)}" .*$', re.MULTILINE)
        if pattern.search(text):
            text = pattern.sub(lambda _: line, text)
        else:
            text = text.replace("</config>", f"{line}\n</config>")
        path.write_text(text)
        self._adopt(path)

    # --- our own record of what is installed ----------------------------------------------

    def manifest(self) -> dict:
        path = self.path(MANIFEST)
        return json.loads(path.read_text()) if path.exists() else {"components": {}}

    def save_manifest(self, manifest: dict) -> None:
        self.write_text(MANIFEST, json.dumps(manifest, indent=2, sort_keys=True) + "\n")
