"""Captures: the two folders (which the emubox_captures service fills from where Batocera keeps
screenshots and recordings), and Batocera's own "Screenshots" entry hidden, as the same pictures
would show twice."""
import os
import re

SETTINGS = "system/configs/emulationstation/es_settings.cfg"


def _drop_folder_rows(file, paths: set) -> None:
    import xml.etree.ElementTree as ET
    if not file.exists():
        return
    tree = ET.parse(file)
    gone = [f for f in tree.getroot().findall("folder") if f.findtext("path") in paths]
    for folder in gone:
        tree.getroot().remove(folder)
    if gone:
        ET.indent(tree, "\t")
        tree.write(file, encoding="utf-8", xml_declaration=True)


def install(env) -> None:
    target = env.target
    for old in ("Screenshots", "Recordings"):    # an earlier version's names (the menu skips "Screenshots")
        path = target.root / "roms" / "captures" / old    # not target.path(): that follows the link
        if os.path.islink(path):
            path.unlink()
        elif path.is_dir() and not any(path.iterdir()):
            path.rmdir()
    _drop_folder_rows(target.path("roms/captures/gamelist.xml"), {"./Screenshots", "./Recordings"})
    for name, dest in (("Shots", "screenshots"), ("Clips", "recordings")):
        target.make_dir(target.path(dest))
        folder = target.path(f"roms/captures/{name}")
        if os.path.islink(folder):          # an earlier version made links, which the menu skips
            folder.unlink()
        target.make_dir(folder)             # filled by the emubox_captures service on Batocera
    file = target.path(SETTINGS)
    text = file.read_text() if file.exists() else ""
    found = re.search(r'name="HiddenSystems" value="([^"]*)"', text)
    hidden = [s for s in (found.group(1) if found else "").split(";") if s]
    if "imageviewer" not in hidden:
        target.es_setting("HiddenSystems", ";".join([*hidden, "imageviewer"]))
