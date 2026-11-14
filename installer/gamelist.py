"""Batocera's per-system game lists (gamelist.xml): names, pictures, descriptions."""
from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path


def _load(path: Path) -> ET.ElementTree:
    if path.exists():
        return ET.parse(path)
    return ET.ElementTree(ET.Element("gameList"))


def _save(tree: ET.ElementTree, path: Path) -> None:
    ET.indent(tree, "\t")
    tree.write(path, encoding="utf-8", xml_declaration=True)


def _entry_for(root: ET.Element, game_path: str) -> ET.Element | None:
    for game in root.findall("game"):
        if game.findtext("path") == game_path:
            return game
    return None


def set_entry(path: Path, file_name: str, fields: dict[str, str]) -> None:
    """Add or replace the entry for one file in a game list."""
    tree = _load(path)
    root = tree.getroot()
    old = _entry_for(root, f"./{file_name}")
    if old is not None:
        root.remove(old)
    game = ET.SubElement(root, "game")
    ET.SubElement(game, "path").text = f"./{file_name}"
    for tag, text in fields.items():
        ET.SubElement(game, tag).text = text
    _save(tree, path)


def remove_entry(path: Path, file_name: str) -> None:
    if not path.exists():
        return
    tree = _load(path)
    old = _entry_for(tree.getroot(), f"./{file_name}")
    if old is not None:
        tree.getroot().remove(old)
        _save(tree, path)


def merge(source: Path, destination: Path, file_names: set[str]) -> None:
    """Copy the entries for these files from one game list into another, keeping what is there."""
    if not source.exists():
        return
    tree = _load(destination)
    root = tree.getroot()
    changed = False
    for game in ET.parse(source).getroot().findall("game"):
        game_path = game.findtext("path") or ""
        if game_path.removeprefix("./") in file_names and _entry_for(root, game_path) is None:
            root.append(game)
            changed = True
    if changed:
        _save(tree, destination)
