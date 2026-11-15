"""The picture a tile shows in the menus: an icon over the name, on a green tile.

    tileart.draw("Apple Music", "music", "tile.png", font)

The icons are simple line drawings made here (a note, a folder, a globe...), never a
company's logo. `ICONS` lists them; an app picks one with "icon" in its app.json, and
`guess()` picks for an app that does not say. Used on the PC by tools/dev/tile.py and
on Batocera by the app list (appstore.py) for apps added there. Needs Pillow.
"""
from __future__ import annotations

import math
from pathlib import Path

SIZE, S = 512, 4            # the tile, and how much larger it is drawn before being smoothed down
LIME, PALE, DARK = "#c8f03c", "#d8ff6a", "#041a04"
W = 13 * S                  # line width of the icons


def _p(*numbers: float) -> list[float]:
    return [n * S for n in numbers]


def _line(d, points, width=W):
    d.line(_p(*points), fill=LIME, width=width, joint="curve")
    r = width / 2
    for x, y in zip(points[::2], points[1::2]):   # round ends and corners
        d.ellipse((x * S - r, y * S - r, x * S + r, y * S + r), fill=LIME)


def _ring(d, cx, cy, r, width=W):
    d.ellipse(_p(cx - r, cy - r, cx + r, cy + r), outline=LIME, width=width)


def _box(d, x0, y0, x1, y1, radius=14, fill=None, width=W):
    d.rounded_rectangle(_p(x0, y0, x1, y1), radius=radius * S, outline=LIME, fill=fill, width=width)


# Each icon draws itself inside a 200 x 200 square whose top-left corner is (0, 0).

def music(d):
    _line(d, (78, 150, 78, 48, 160, 30, 160, 132))
    d.ellipse(_p(34, 128, 84, 172), fill=LIME)
    d.ellipse(_p(116, 110, 166, 154), fill=LIME)


def chat(d):
    _box(d, 20, 28, 180, 138, radius=26)
    d.polygon(_p(58, 132, 58, 178, 102, 134), fill=LIME)
    for x in (66, 100, 134):
        d.ellipse(_p(x - 9, 74, x + 9, 92), fill=LIME)


def terminal(d):
    _box(d, 14, 30, 186, 170, radius=16)
    _line(d, (46, 74, 80, 100, 46, 126))
    _line(d, (98, 130, 150, 130))


def folder(d):
    _line(d, (20, 160, 20, 44, 82, 44, 100, 66, 180, 66, 180, 160, 20, 160))


def globe(d):
    _ring(d, 100, 100, 80)
    d.ellipse(_p(64, 20, 136, 180), outline=LIME, width=W * 3 // 4)
    _line(d, (22, 100, 178, 100), W * 3 // 4)
    _line(d, (100, 20, 100, 180), W * 3 // 4)


def spark(d):
    for angle in range(0, 180, 45):
        long = 84 if angle % 90 == 0 else 52
        dx, dy = math.cos(math.radians(angle)) * long, math.sin(math.radians(angle)) * long
        _line(d, (100 - dx, 100 - dy, 100 + dx, 100 + dy))


def gamepad(d):
    _box(d, 12, 52, 188, 152, radius=46)
    _line(d, (44, 102, 84, 102))
    _line(d, (64, 82, 64, 122))
    d.ellipse(_p(120, 104, 142, 126), fill=LIME)
    d.ellipse(_p(144, 78, 166, 100), fill=LIME)


def gift(d):
    _box(d, 26, 84, 174, 176, radius=8)
    _box(d, 14, 56, 186, 88, radius=8)
    _line(d, (100, 56, 100, 176))
    _line(d, (100, 54, 70, 24, 54, 44, 100, 54, 130, 24, 146, 44, 100, 54), W * 3 // 4)


def shield(d):
    _line(d, (100, 18, 172, 44, 172, 98, 100, 182, 28, 98, 28, 44, 100, 18))
    _line(d, (70, 96, 92, 120, 134, 70))


def joystick(d):
    _box(d, 26, 132, 174, 176, radius=12)
    _line(d, (100, 132, 100, 70))
    d.ellipse(_p(70, 20, 130, 80), fill=LIME)


def vault(d):
    _ring(d, 100, 100, 82)
    _ring(d, 100, 100, 30)
    for angle in range(0, 360, 60):
        dx, dy = math.cos(math.radians(angle)), math.sin(math.radians(angle))
        _line(d, (100 + dx * 30, 100 + dy * 30, 100 + dx * 62, 100 + dy * 62), W * 3 // 4)


def package(d):
    _line(d, (100, 18, 176, 58, 176, 142, 100, 182, 24, 142, 24, 58, 100, 18))
    _line(d, (24, 58, 100, 98, 176, 58))
    _line(d, (100, 98, 100, 182))


def play(d):
    _box(d, 14, 34, 186, 166, radius=30)
    d.polygon(_p(80, 68, 80, 132, 134, 100), fill=LIME)


def broadcast(d):
    d.ellipse(_p(84, 84, 116, 116), fill=LIME)
    for r in (46, 80):
        d.arc(_p(100 - r, 100 - r, 100 + r, 100 + r), -50, 50, fill=LIME, width=W)
        d.arc(_p(100 - r, 100 - r, 100 + r, 100 + r), 130, 230, fill=LIME, width=W)


def film(d):
    _box(d, 20, 30, 180, 170, radius=10)
    for y in (52, 86, 120, 150):
        d.rectangle(_p(32, y - 8, 48, y + 8), fill=LIME)
        d.rectangle(_p(152, y - 8, 168, y + 8), fill=LIME)
    _line(d, (62, 30, 62, 170), W // 2)
    _line(d, (138, 30, 138, 170), W // 2)


def cloud(d):
    d.arc(_p(22, 84, 94, 156), 90, 270, fill=LIME, width=W)
    d.arc(_p(52, 40, 136, 124), 180, 330, fill=LIME, width=W)
    d.arc(_p(106, 72, 184, 156), 250, 90, fill=LIME, width=W)
    _line(d, (58, 156, 146, 156))


def moon(d):
    d.ellipse(_p(22, 22, 178, 178), fill=LIME)
    d.ellipse(_p(64, 6, 204, 146), fill=DARK)


def window(d):
    _box(d, 16, 30, 184, 170, radius=14)
    _line(d, (16, 66, 184, 66), W * 3 // 4)


def bag(d):
    _line(d, (30, 66, 170, 66, 180, 176, 20, 176, 30, 66))
    d.arc(_p(64, 22, 136, 104), 180, 360, fill=LIME, width=W)


def apps(d):
    for x in (24, 112):
        for y in (24, 112):
            _box(d, x, y, x + 64, y + 64, radius=12)


ICONS = {f.__name__: f for f in (music, chat, terminal, folder, globe, spark, gamepad, gift, shield, joystick, vault,
                                 package, play, broadcast, film, cloud, moon, window, bag, apps)}


def guess(app: dict) -> str:
    """An icon for an app that names none: by what kind of app it is."""
    if app.get("icon") in ICONS:
        return app["icon"]
    if app.get("player"):
        return "music"
    if app.get("voice"):
        return "chat"
    return "globe" if app.get("web") or "Chrome" in app.get("flatpak", "") else "window"


def tile(name: str, icon: str, font: Path, picture=None):
    """The tile as an image. `picture` (a Pillow image) takes the icon's place: the app's own
    icon, when it could be found on this machine or fetched from the app's site (tileicon.py)."""
    from PIL import Image, ImageDraw, ImageFilter, ImageFont
    image = Image.new("RGB", (SIZE, SIZE), DARK)
    glow = Image.new("RGB", (SIZE, SIZE), "black")
    ImageDraw.Draw(glow).ellipse((96, 96, SIZE - 96, SIZE - 96), fill="#2f7d1e")
    image = Image.blend(image, glow.filter(ImageFilter.GaussianBlur(70)), 0.75)
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((14, 14, SIZE - 14, SIZE - 14), radius=28, outline=LIME, width=5)

    words = name.upper().split()
    if len(words) > 2:                      # three short words still take two lines at most
        words = [" ".join(words[:-1]), words[-1]] if len(" ".join(words[:-1])) <= 12 else [words[0], " ".join(words[1:])]
    letters = 44
    face = ImageFont.truetype(str(font), letters)
    while letters > 22 and max(draw.textlength(w, font=face) for w in words) > SIZE - 70:
        letters -= 2
        face = ImageFont.truetype(str(font), letters)
    line = letters * 1.4
    text_top = int(SIZE - 52 - line * len(words))
    for i, word in enumerate(words):
        draw.text(((SIZE - draw.textlength(word, font=face)) / 2, text_top + line * i), word, font=face, fill=PALE)

    # The icon: drawn large and smoothed down, centred in the room above the name.
    room = text_top - 44
    side = int(min(200, room - 16))
    where = ((SIZE - side) // 2, 44 + int(room - side) // 2)
    if picture is not None:
        own = picture.convert("RGBA")
        grow = min(side / max(own.size), 2.0)          # a small icon is enlarged, but not into a blur
        own = own.resize((max(1, round(own.width * grow)), max(1, round(own.height * grow))), Image.LANCZOS)
        spot = (where[0] + (side - own.width) // 2, where[1] + (side - own.height) // 2)
        image.paste(own, spot, own)
        return image
    art = Image.new("RGBA", (200 * S, 200 * S), (0, 0, 0, 0))
    pen = ImageDraw.Draw(art)
    ICONS.get(icon, window)(pen)
    if icon == "moon":                      # its cut-out is drawn in the tile's colour: make that clear instead
        pixels = art.load()
        dark = tuple(int(DARK[i:i + 2], 16) for i in (1, 3, 5))
        for x in range(art.width):
            for y in range(art.height):
                if pixels[x, y][:3] == dark:
                    pixels[x, y] = (0, 0, 0, 0)
    art = art.resize((side, side), Image.LANCZOS)
    halo = Image.new("RGBA", image.size, (0, 0, 0, 0))
    halo.paste(art, where, art)
    soft = halo.filter(ImageFilter.GaussianBlur(9))
    image.paste(soft, (0, 0), soft)
    image.paste(halo, (0, 0), halo)
    return image


def draw(name: str, icon: str, file: Path | str, font: Path | str, picture=None) -> bool:
    """Write the tile's picture. False when it cannot be made (no Pillow, no font): a tile without one still works."""
    try:
        made = tile(name, icon, Path(font), picture)
        Path(file).parent.mkdir(parents=True, exist_ok=True)
        made.save(file)
        return True
    except Exception:   # noqa: BLE001
        return False
