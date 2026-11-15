#!/usr/bin/env python3
"""Draw the picture a tile shows in the menus: an icon over its name, on a green tile.

    python3 tools/dev/tile.py "Apple Music" music apps/apple-music/tile.png
    python3 tools/dev/tile.py --all          every app's and store tile's picture, from their settings
    python3 tools/dev/tile.py --icons        the names of the icons

The drawing itself is components/console/files/lib/tileart.py (Batocera uses it too, for
apps added from the app list). Icons are plain line drawings, never a company's logo.
Needs Pillow.
"""
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "components/console/files/lib"))
import tileart  # noqa: E402

FONT = REPO / "components/look/files/fonts/Michroma-Regular.ttf"


def everything() -> list[tuple[str, str, Path]]:
    """(name, icon, file) for each app in apps/ and each tile a component puts in a menu."""
    found = []
    for file in sorted(REPO.glob("apps/*/app.json")):
        app = json.loads(file.read_text())
        found.append((app["name"], tileart.guess(app), file.parent / "tile.png"))
    for file in sorted(REPO.glob("components/*/component.json")):
        spec = json.loads(file.read_text())
        for port in spec.get("ports", []):
            if port.get("image"):
                found.append((port["name"], port.get("icon", "window"), file.parent / port["image"]))
        for name, folder in spec.get("folders", {}).items():
            found.append((name, folder.get("icon", "folder"), file.parent / folder["image"]))
    return found


if __name__ == "__main__":
    if sys.argv[1:] == ["--icons"]:
        print(" ".join(tileart.ICONS))
    elif sys.argv[1:] == ["--all"]:
        for name, icon, file in everything():
            tileart.tile(name, icon, FONT).save(file)
            print(f"{file.relative_to(REPO)}: {icon}")
    elif len(sys.argv) == 4:
        tileart.tile(sys.argv[1], sys.argv[2], FONT).save(sys.argv[3])
    else:
        sys.exit(__doc__)
