#!/usr/bin/env python3
"""An app's own icon for its tile, found where the app itself keeps it.

    tileicon.py app <id>      redraw that app's tile on Batocera with its own icon, if one can be found

Nothing here ships with EmuBox: a Flathub program brings its icon with it (flatpak
puts it under exports/share/icons; before it is installed, Flathub's catalogue
has the same icon), and a web app's icon is asked of its own site
(the one its pages name, as a browser would for a bookmark). When neither is to be
had, or there is no network, the tile keeps the drawing from tileart.py.

What says where to look, in an app.json or a tile in a component.json:
    "flatpak": "com.discordapp.Discord"      the program's icon   ("icon_flatpak" on a tile)
    "web": "https://..."                     the site's icon      ("icon_web" on a tile)
    "args": ["--app=https://..."]            a site opened in Chrome: the site's icon, not Chrome's
    "own_icon": false                        none of these: keep the drawing
"""
from __future__ import annotations

import io
import json
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
FLATPAK_ROOTS = [Path("/userdata/saves/flatpak/binaries")]
FONT = Path("/userdata/system/.fonts/Michroma-Regular.ttf")
TILES = Path("/userdata/roms/apps")
SMALLEST = 64            # an icon smaller than this would only be a blur on a tile
AGENT = "Mozilla/5.0 (X11; Linux x86_64) EmuBox"


def get(url: str, limit: int = 3_000_000) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": AGENT, "Accept": "*/*"})
    with urllib.request.urlopen(request, timeout=8) as reply:
        return reply.read(limit)


def picture(data: bytes):
    """Bytes as a Pillow image; None when they are not a picture we can read."""
    from PIL import Image
    try:
        image = Image.open(io.BytesIO(data))
        if getattr(image, "ico", None):             # an .ico holds several sizes: the largest
            image = image.ico.getimage(max(image.ico.sizes()))
        image.load()
        return image.convert("RGBA")
    except Exception:   # noqa: BLE001
        pass
    try:                                              # a drawing (.svg): GTK's loader can turn it into dots
        import gi
        gi.require_version("GdkPixbuf", "2.0")
        from gi.repository import GdkPixbuf, Gio, GLib
        stream = Gio.MemoryInputStream.new_from_bytes(GLib.Bytes.new(data))
        pixbuf = GdkPixbuf.Pixbuf.new_from_stream_at_scale(stream, 256, 256, True, None)
        done, png = pixbuf.save_to_bufferv("png", [], [])
        return Image.open(io.BytesIO(png)).convert("RGBA") if done else None
    except Exception:   # noqa: BLE001
        return None


def links(page: str, address: str) -> list[str]:
    """The icons a page names, best first: the large ones made for a phone's home screen, then the rest."""
    found = []
    for tag in re.findall(r"<link\b[^>]*>", page, re.I):
        rel = re.search(r'rel\s*=\s*["\']?([^"\'>]+)', tag, re.I)
        href = re.search(r'href\s*=\s*["\']?([^"\'\s>]+)', tag, re.I)
        if not rel or not href or "icon" not in rel.group(1).lower() or "mask-icon" in rel.group(1).lower():
            continue
        sizes = re.search(r'sizes\s*=\s*["\']?(\d+)', tag, re.I)
        size = int(sizes.group(1)) if sizes else 0
        touch = "apple-touch" in rel.group(1).lower()
        found.append((touch or size >= 128, size or (180 if touch else 0), urllib.parse.urljoin(address, href.group(1).replace("&amp;", "&"))))
    return [url for _good, _size, url in sorted(found, key=lambda entry: (entry[0], entry[1]), reverse=True)]


def site_icon(address: str, fetch=get):
    """The icon of a web site, as a Pillow image, or None."""
    candidates = []
    try:
        candidates = links(fetch(address, 600_000).decode("utf-8", "replace"), address)
    except Exception:   # noqa: BLE001  (no network, a site that refuses us: try the usual places)
        pass
    candidates += [urllib.parse.urljoin(address, "/apple-touch-icon.png"), urllib.parse.urljoin(address, "/favicon.ico")]
    for url in dict.fromkeys(candidates):
        try:
            image = picture(fetch(url))
        except Exception:   # noqa: BLE001
            continue
        if image is not None and min(image.size) >= SMALLEST:
            return image
    return None


def flatpak_icon(program: str, roots: list[Path] | None = None):
    """The icon a Flathub program installed with it, largest first."""
    for root in roots or FLATPAK_ROOTS:
        icons = Path(root) / "exports/share/icons/hicolor"
        for size in ("512x512", "256x256", "128x128", "scalable", "96x96", "64x64"):
            for kind in ("png", "svg"):
                file = icons / size / "apps" / f"{program}.{kind}"
                if file.is_file():
                    image = picture(file.read_bytes())
                    if image is not None:
                        return image
    return None


def flathub_icon(program: str, fetch=get):
    """The icon Flathub's catalogue shows for a program that is not installed (yet)."""
    try:
        listed = json.loads(fetch(f"https://flathub.org/api/v2/appstream/{program}", 600_000))
        image = picture(fetch(listed["icon"]))
    except Exception:   # noqa: BLE001
        return None
    return image if image is not None and min(image.size) >= SMALLEST else None


def sources(entry: dict) -> tuple[str, str]:
    """(flatpak program, web address) to ask for this app's or tile's icon; either may be empty."""
    if entry.get("own_icon") is False:           # a tile that is not one app or site (the Browser): its drawing stays
        return "", ""
    program = entry.get("icon_flatpak") or entry.get("flatpak", "")
    address = entry.get("icon_web") or entry.get("web", "")
    for word in entry.get("args", []):
        if word.startswith("--app="):          # a site in a Chrome window is that site, not Chrome
            program, address = "", address or word[6:]
    return program, address


def official(entry: dict, roots: list[Path] | None = None, fetch=get):
    program, address = sources(entry)
    image = flatpak_icon(program, roots) if program else None
    if image is None and program:
        image = flathub_icon(program, fetch)
    if image is None and address:
        image = site_icon(address, fetch)
    return image


def upgrade(entry: dict, file: Path, font: Path, roots: list[Path] | None = None, fetch=get) -> bool:
    """Redraw a tile's picture around the app's own icon. False (and nothing changed) when there is none."""
    import tileart
    image = official(entry, roots, fetch)
    return image is not None and tileart.draw(entry["name"], tileart.guess(entry), file, font, image)


def main(argv: list[str]) -> int:
    if len(argv) != 2 or argv[0] != "app":
        sys.exit(__doc__)
    folder = ROOT / "apps" / argv[1]
    app = json.loads((folder / "app.json").read_text())
    done = folder / ".icon"                       # asked once; a later start does not ask again
    if done.exists():
        return 0
    if upgrade(app, TILES / "images" / f"{app['name']}.png", FONT):
        done.write_text("the tile shows the app's own icon\n")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
