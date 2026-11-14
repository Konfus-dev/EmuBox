"""BIOS and game libraries: a folder with one sub-folder per system.

    <library>/psx/Some Game (USA).cue          games: laid out like Batocera's roms folder
    <library>/psx/scph5501.bin                 BIOS: each system's files, as they sit in Batocera's bios folder

A library is just files, so it can live on a drive, on a NAS, or in a git
repository. For games, a Batocera drive itself (or its roms folder) also works.
"""
from __future__ import annotations

import hashlib
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from . import gamelist, systems
from .target import Target

MEDIA_FOLDERS = ("images", "videos", "manuals")
NOT_CONTENT = {"_info.txt", "gamelist.xml", "MANIFEST.tsv", "README.md", "README.txt", "LICENSE", *MEDIA_FOLDERS}
DISC_TAG = re.compile(r"\s*\((?:Disc|Disk|CD|Side)\s*\w+\)", re.IGNORECASE)
TOO_BIG_FOR_GIT = 95 * 1024 * 1024   # GitHub refuses files of 100 MB and more


class NotEnoughSpace(Exception):
    pass


def human(size: int) -> str:
    for unit in ("B", "KB", "MB"):
        if size < 1024:
            return f"{size:.0f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"


@dataclass
class Item:
    """One thing to pick: a game (all its discs and files), or one BIOS file."""
    name: str
    files: list[Path]

    @property
    def size(self) -> int:
        return sum(f.stat().st_size for f in self.files)


@dataclass
class System:
    id: str
    folder: Path
    items: list[Item]

    @property
    def size(self) -> int:
        return sum(item.size for item in self.items)

    def label(self, noun: str) -> str:
        count = len(self.items)
        return f"{systems.name(self.id)} ({count} {noun}{'' if count == 1 else 's'}, {human(self.size)})"


def _content(folder: Path) -> list[Path]:
    return sorted(p for p in folder.iterdir() if p.name not in NOT_CONTENT and not p.name.startswith("."))


def _files(path: Path) -> list[Path]:
    return [path] if path.is_file() else sorted(p for p in path.rglob("*") if p.is_file())


def _games(folder: Path) -> list[Item]:
    """Group a system's files into games: 'Game (Disc 1).iso', '(Disc 2)' and 'Game.m3u' are one game."""
    games: dict[str, Item] = {}
    for entry in _content(folder):
        name = entry.name if entry.is_dir() else entry.stem
        name = DISC_TAG.sub("", name)
        games.setdefault(name, Item(name, [])).files += _files(entry)
    return list(games.values())


def _bios_files(folder: Path) -> list[Item]:
    return [Item(f.relative_to(folder).as_posix(), [f]) for entry in _content(folder) for f in _files(entry)]


class Library:
    def __init__(self, root: Path, kind: str):
        """kind is 'games' or 'bios'."""
        if kind == "games" and (root / "roms").is_dir():
            root = root / "roms"   # a Batocera drive was given; its games are in roms/
        self.root, self.kind = root, kind

    @property
    def noun(self) -> str:
        return "game" if self.kind == "games" else "file"

    def systems(self) -> list[System]:
        read = _games if self.kind == "games" else _bios_files
        found = []
        for folder in sorted(p for p in self.root.iterdir() if p.is_dir() and not p.name.startswith(".")):
            items = read(folder)
            if items:
                found.append(System(folder.name, folder, items))
        return found


# --- putting a selection onto the drive ------------------------------------------------

Selection = list[tuple[System, list[Item]]]


def needed_bytes(selection: Selection, target: Target, kind: str) -> int:
    total = 0
    for system, items in selection:
        for item in items:
            for file in item.files:
                if not _already_there(file, target.path(_destination(kind, system, file))):
                    total += file.stat().st_size
    return total


def _destination(kind: str, system: System, file: Path) -> str:
    inside = file.relative_to(system.folder).as_posix()
    return f"bios/{inside}" if kind == "bios" else f"roms/{system.id}/{inside}"


def _already_there(source: Path, destination: Path) -> bool:
    return destination.is_file() and destination.stat().st_size == source.stat().st_size


def _copy(source: Path, relative: str, target: Target, say: Callable[[str], None]) -> None:
    if _already_there(source, target.path(relative)):
        return
    say(f"    {source.name} ({human(source.stat().st_size)})")
    target.copy_file(source, relative)
    if not _already_there(source, target.path(relative)):
        raise OSError(f"{relative} did not copy completely")


def install(library: Library, selection: Selection, target: Target, say: Callable[[str], None]) -> None:
    need = needed_bytes(selection, target, library.kind)
    if need > target.free_bytes():
        raise NotEnoughSpace(f"Needs {human(need)}, but the drive has {human(target.free_bytes())} free.")
    for system, items in selection:
        say(f"  {systems.name(system.id)}")
        chosen_files: set[str] = set()
        for item in items:
            for file in item.files:
                _copy(file, _destination(library.kind, system, file), target, say)
                chosen_files.add(file.relative_to(system.folder).as_posix())
        if library.kind == "games":
            _copy_extras(system, chosen_files, target, say)


def _copy_extras(system: System, chosen_files: set[str], target: Target, say: Callable[[str], None]) -> None:
    """The pictures, videos, manuals and game-list entries that belong to the chosen games."""
    stems = tuple(Path(name).stem for name in chosen_files)
    for media in MEDIA_FOLDERS:
        folder = system.folder / media
        if folder.is_dir():
            for file in sorted(folder.iterdir()):
                if file.is_file() and file.name.startswith(stems):
                    _copy(file, f"roms/{system.id}/{media}/{file.name}", target, lambda _line: None)
    gamelist.merge(system.folder / "gamelist.xml", target.path(f"roms/{system.id}/gamelist.xml"), chosen_files)


# --- making a games library from a drive (backup) -----------------------------------------

def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def backup(selection: Selection, destination: Path, say: Callable[[str], None]) -> None:
    """Copy whole system folders (games, pictures, game lists) into a library folder."""
    destination.mkdir(parents=True, exist_ok=True)
    for system, _items in selection:
        say(f"  {systems.name(system.id)}")
        for file in _files(system.folder):
            inside = file.relative_to(system.folder)
            if inside.name == "_info.txt" or any(part.startswith(".") for part in inside.parts):
                continue
            copy_to = destination / system.id / inside
            if _already_there(file, copy_to):
                continue
            say(f"    {inside} ({human(file.stat().st_size)})")
            copy_to.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(file, copy_to)
    write_index(destination, say)


def write_index(library_root: Path, say: Callable[[str], None]) -> None:
    """MANIFEST.tsv (size, checksum, path of every game file) and a .gitignore for files git hosts refuse."""
    manifest = library_root / "MANIFEST.tsv"
    known = {}
    if manifest.exists():
        for line in manifest.read_text().splitlines()[1:]:
            size, checksum, path = line.split("\t", 2)
            known[(path, int(size))] = checksum
    rows, too_big = [], []
    for system in Library(library_root, "games").systems():
        for item in system.items:
            for file in item.files:
                path, size = file.relative_to(library_root).as_posix(), file.stat().st_size
                if (path, size) not in known:
                    say(f"    checksum {file.name}")
                rows.append((size, known.get((path, size)) or _sha256(file), path))
                if size >= TOO_BIG_FOR_GIT:
                    too_big.append(path)
    manifest.write_text("size\tsha256\tpath\n" + "".join(f"{s}\t{c}\t{p}\n" for s, c, p in rows))
    lines = ["# Written by RetroBox's backup-games. Files of 95 MB and more cannot go to GitHub;",
             "# they stay in this folder only. MANIFEST.tsv lists them with checksums.",
             *(f"/{_escape(path)}" for path in too_big)]
    (library_root / ".gitignore").write_text("\n".join(lines) + "\n")


def _escape(path: str) -> str:
    return re.sub(r"([\[\]*?!#\\ ])", r"\\\1", path)
