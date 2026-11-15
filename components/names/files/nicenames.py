#!/usr/bin/env python3
"""Tidy game names: what the menus show, not the files.

    nicenames.py [DATA_FOLDER]                   tidy every system (default /userdata)
    nicenames.py [DATA_FOLDER] --dry-run         show what would change
    nicenames.py [DATA_FOLDER] --set SYSTEM FILE NAME     give one game a name of your own

"Pokemon - Emerald Version (USA, Europe) [!].gba" is shown as "Pokémon Emerald Version",
"Legend of Zelda, The - A Link to the Past (U) (V1.1).sfc" as "The Legend of Zelda: A Link to the Past",
and the discs of a multi-disc game are hidden behind its .m3u playlist.
Only the <name> in each system's gamelist.xml is written; files are never renamed, so saves,
scraped pictures and the like stay attached.

Names you set yourself (in Batocera's "Edit this game's metadata", or with --set) are never
changed again: every name this tool writes is noted in system/emubox/names.json, and a name that
differs from the note was changed by someone else.
"""
from __future__ import annotations

import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

SKIP_SYSTEMS = {"apps", "store"}            # EmuBox's own tiles, named already
MEDIA = {"images", "videos", "manuals", "media", "downloaded_images", "downloaded_videos", "screenshots"}
ES_SYSTEMS = Path("/usr/share/emulationstation/es_systems.cfg")   # on Batocera itself
EXTENSIONS = Path(__file__).resolve().parent / "extensions.json"  # a copy of its file types, for a PC
SMALL_WORDS = {"a", "an", "and", "as", "at", "but", "by", "for", "in", "of", "on", "or", "the", "to", "vs", "with"}
ROMAN = re.compile(r"^(?=[MDCLXVI])M*(C[MD]|D?C{0,3})(X[CL]|L?X{0,3})(I[XV]|V?I{0,3})$", re.IGNORECASE)
RECORD = "system/emubox/names.json"


# --- the tidying itself -------------------------------------------------------------------------

def tidy(raw: str) -> str:
    """A clean title from a file name or a messy name."""
    s = raw.strip()
    disc = re.search(r"[\(\[]\s*(?:Disc|Disk|CD)\s*([0-9A-Z]+)(?:\s*of\s*\d+)?\s*[\)\]]", s, re.IGNORECASE)
    s = re.sub(r"\s*[\(\[\{][^\)\]\}]*[\)\]\}]", " ", s)              # (USA), [!], {beta}, [1.2.1]
    s = s.replace("_", " ")
    if " " not in s.strip() and s.count(".") >= 2:                    # Some.Game.Name
        s = s.replace(".", " ")
    s = re.sub(r"\s+v\d+(?:[.\-]\d+)*[a-z]?(?=\s|$)", " ", s, flags=re.IGNORECASE)    # v1.2.1
    s = re.sub(r"\s+(?:rev|revision)\s*[0-9a-z.]{1,4}(?=\s|$)", " ", s, flags=re.IGNORECASE)
    s = re.sub(r"\s+\d+(?:\.\d+){1,3}(?=\s|$)", " ", s)                # a bare 1.2.1
    s = re.sub(r"\s*-{2,}\s*", " - ", s)
    s = re.sub(r"\s+", " ", s).strip(" -_,")

    parts = [p.strip(" -_,") for p in re.split(r"\s+-\s+|\s*:\s+", s) if p.strip(" -_,")]
    parts = [re.sub(r"^(.+), (The|A|An)$", r"\2 \1", p, flags=re.IGNORECASE) for p in parts]
    parts = [re.sub(r"^(.+), (The|A|An)\b(.*)$", r"\2 \1\3", p, flags=re.IGNORECASE) for p in parts]
    if not parts:
        return raw.strip()
    if len(parts) > 1 and re.fullmatch(r"pok[eé]mon", parts[0], re.IGNORECASE) and parts[1].lower().endswith("version"):
        parts = [f"{parts[0]} {parts[1]}", *parts[2:]]                 # "Pokemon - Emerald Version"
    s = parts[0] + "".join(f": {p}" for p in parts[1:])

    letters = [c for c in s if c.isalpha()]
    if letters and (all(c.islower() for c in letters) or (len(letters) > 4 and all(c.isupper() for c in letters))):
        s = title_case(s)
    s = re.sub(r"\bpokemon\b", "Pokémon", s, flags=re.IGNORECASE)
    if disc:
        s += f" (Disc {disc.group(1).upper()})"
    return s or raw.strip()


def title_case(s: str) -> str:
    words = s.split(" ")
    out = []
    for i, word in enumerate(words):
        bare = word.strip(":")
        if ROMAN.match(bare) and len(bare) <= 4 and i > 0:
            out.append(word.upper())
        elif i > 0 and bare.lower() in SMALL_WORDS and not words[i - 1].endswith(":"):
            out.append(word.lower())
        else:
            out.append(word[:1].upper() + word[1:].lower())
    return " ".join(out)


# --- the drive's game lists -----------------------------------------------------------------------

def stem(entry: str) -> str:
    name = Path(entry).name
    return name.rsplit(".", 1)[0] if "." in name.strip(".") else name


def file_types() -> dict[str, list[str]]:
    """Each system's game file endings, as Batocera's menu knows them."""
    try:
        import xml.etree.ElementTree as ElementTree
        top = ElementTree.parse(ES_SYSTEMS).getroot()
        return {s.findtext("name"): (s.findtext("extension") or "").lower().split() for s in top.findall("system")}
    except (OSError, ElementTree.ParseError):
        return json.loads(EXTENSIONS.read_text())


def is_game(name: str, endings: list[str]) -> bool:
    return any(name.lower().endswith(e) for e in endings) and not name.startswith("ZZZ(notgame)")


def games_in(system: Path, endings: list[str], below: str = ".") -> list[str]:
    """Game paths as the game list writes them ("./x.sfc", "./sub/y.chd"): only files (or game
    folders such as Game.pc) of a type this system plays."""
    found = []
    for item in sorted(system.iterdir()):
        if item.name.startswith(".") or item.name.lower() in MEDIA:
            continue
        rel = f"{below}/{item.name}"
        if is_game(item.name, endings):
            found.append(rel)
        elif item.is_dir() and below.count("/") < 3:
            found += games_in(item, endings, rel)
    return found


def load(path: Path) -> ET.ElementTree:
    if path.exists():
        try:
            return ET.parse(path)
        except ET.ParseError:
            return None
    return ET.ElementTree(ET.Element("gameList"))


def run(root: Path, dry_run: bool = False, say=print) -> int:
    """Tidy every system's names. Returns how many names changed."""
    record_file = root / RECORD
    try:
        record = json.loads(record_file.read_text())
    except (OSError, ValueError):
        record = {}
    changed = 0
    roms = root / "roms"
    types = file_types()
    for system in sorted(p for p in roms.iterdir() if p.is_dir() and p.name not in SKIP_SYSTEMS and not p.name.startswith(".")) if roms.is_dir() else []:
        list_file = system / "gamelist.xml"
        tree = load(list_file)
        endings = types.get(system.name)
        if not endings:
            continue                                      # a folder Batocera does not know: leave it
        if tree is None:
            say(f"{system.name}: gamelist.xml is damaged; left alone")
            continue
        top = tree.getroot()
        entries = {g.findtext("path"): g for g in top.findall("game")}
        touched = False
        for path in sorted(set(games_in(system, endings)) | {p for p in entries if p and is_game(Path(p).name, endings)}):
            if not (system / path).exists():
                continue
            key = f"{system.name}/{path}"
            entry = entries.get(path)
            current = (entry.findtext("name") if entry is not None else None) or ""
            if current.startswith("ZZZ(notgame)"):
                continue                                  # Batocera's own placeholder rows
            if key in record and current and current != record[key]:
                continue                                  # someone named it themselves
            if key in record and record[key] is None:
                continue                                  # set by hand with --set: theirs
            raw = current or stem(path)
            if current and current == tidy(current) and key not in record:
                continue                                  # already a clean name (scraped, say)
            new = tidy(raw if current else stem(path))
            if new == current or (not current and new == stem(path)):
                record[key] = new                         # already right (the menu shows the file's name)
                continue
            say(f"{system.name}: {current or stem(path)!r} -> {new!r}")
            changed += 1
            record[key] = new
            if dry_run:
                continue
            if entry is None:
                entry = ET.SubElement(top, "game")
                ET.SubElement(entry, "path").text = path
                entries[path] = entry
            name = entry.find("name")
            if name is None:
                name = ET.SubElement(entry, "name")
            name.text = new
            touched = True
        # A multi-disc game shows once: the discs a .m3u playlist lists are hidden (Batocera's own
        # "hidden" flag, which its menu can show again).
        for playlist in sorted(system.rglob("*.m3u")):
            try:
                lines = playlist.read_text(errors="replace").splitlines()
            except OSError:
                continue
            for line in lines:
                disc = line.strip()
                if not disc or disc.startswith("#") or not (playlist.parent / disc).exists():
                    continue
                path = "./" + (playlist.parent / disc).relative_to(system).as_posix()
                entry = entries.get(path)
                if entry is not None and entry.findtext("hidden") == "true":
                    continue
                say(f"{system.name}: hiding {path[2:]!r} (a disc of {playlist.name!r})")
                changed += 1
                if dry_run:
                    continue
                if entry is None:
                    entry = ET.SubElement(top, "game")
                    ET.SubElement(entry, "path").text = path
                    entries[path] = entry
                ET.SubElement(entry, "hidden").text = "true"
                touched = True
        if touched:
            ET.indent(tree, "\t")
            tree.write(list_file, encoding="utf-8", xml_declaration=True)
    if not dry_run:
        record_file.parent.mkdir(parents=True, exist_ok=True)
        record_file.write_text(json.dumps(record, indent=1, ensure_ascii=False, sort_keys=True) + "\n")
    return changed


def set_name(root: Path, system: str, file_name: str, name: str) -> str:
    """Give one game a name of your own; this tool will not change it again."""
    folder = root / "roms" / system
    path = file_name if file_name.startswith("./") else f"./{file_name}"
    if not (folder / path).exists():
        raise FileNotFoundError(f"No {path[2:]} in roms/{system}")
    list_file = folder / "gamelist.xml"
    tree = load(list_file)
    if tree is None:
        raise ValueError(f"roms/{system}/gamelist.xml is damaged")
    top = tree.getroot()
    entry = next((g for g in top.findall("game") if g.findtext("path") == path), None)
    if entry is None:
        entry = ET.SubElement(top, "game")
        ET.SubElement(entry, "path").text = path
    node = entry.find("name")
    if node is None:
        node = ET.SubElement(entry, "name")
    node.text = name
    ET.indent(tree, "\t")
    tree.write(list_file, encoding="utf-8", xml_declaration=True)
    record_file = root / RECORD
    try:
        record = json.loads(record_file.read_text())
    except (OSError, ValueError):
        record = {}
    record[f"{system}/{path}"] = None
    record_file.parent.mkdir(parents=True, exist_ok=True)
    record_file.write_text(json.dumps(record, indent=1, ensure_ascii=False, sort_keys=True) + "\n")
    return path


if __name__ == "__main__":
    args = sys.argv[1:]
    if args[:1] in (["-h"], ["--help"]):
        sys.exit(__doc__)
    folder = Path(args.pop(0)) if args and not args[0].startswith("--") else Path("/userdata")
    if args[:1] == ["--set"]:
        if len(args) != 4:
            sys.exit("usage: nicenames.py [DATA_FOLDER] --set SYSTEM FILE NAME")
        print(f"{args[1]}/{set_name(folder, args[1], args[2], args[3])[2:]} is now called {args[3]!r}")
    else:
        count = run(folder, dry_run="--dry-run" in args)
        print(f"{count} name{'s' if count != 1 else ''} {'would change' if '--dry-run' in args else 'tidied'}.")
        sys.exit(0 if count or "--dry-run" in args else 3)   # 3: nothing changed (the service skips the reload)
