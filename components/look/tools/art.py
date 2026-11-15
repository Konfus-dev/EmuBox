#!/usr/bin/env python3
"""Generates every image used by the EmuBox theme.  Usage: python3 art.py <theme folder>
All artwork and audio is original and procedural (no console maker's assets are used)."""
import sys, math, os
from PIL import Image, ImageDraw, ImageFilter, ImageOps, ImageChops, ImageFont
ROOT = sys.argv[1]; OUT = f"{ROOT}/art"; W, H = 1920, 1080
os.makedirs(f"{OUT}/help", exist_ok=True); 

def radial(size, center, radius, inner, outer):
    g = Image.radial_gradient("L").resize((int(radius * 2), int(radius * 2)), Image.BICUBIC)
    g = g.point(lambda v: min(255, int(v * 1.4143)))
    canvas = Image.new("L", size, 255); canvas.paste(g, (int(center[0] - radius), int(center[1] - radius)))
    return ImageOps.colorize(canvas, inner, outer)

def vgrad(size, top, bottom):
    g = Image.linear_gradient("L").resize(size)
    return ImageOps.colorize(g, top, bottom).convert("RGBA")

def with_alpha(img, mask, alpha=255):
    img = img.convert("RGBA"); img.putalpha(mask.point(lambda v: v * alpha // 255)); return img

def glow_of(mask, color, blur, strength=1.0):
    g = Image.new("RGBA", mask.size, color + (0,))
    g.putalpha(mask.filter(ImageFilter.GaussianBlur(blur)).point(lambda v: min(255, int(v * strength)))); return g

# The menus' background (the tunnel of cells), the claw and the ring round the orb are 3D:
# tools/blender/scene.py renders them into the same folder.

# ------------------------------------------------------------------ plasma orb layers
# A solid, glossy sphere in the manner of the classic dashboard's: lime at the rim, a creamy
# yellow heart, soft edges, lit from the top left. The theme turns most of these layers all the
# time, so those are drawn the same all the way round; the light and shade, which must stay
# put, are all in shell.png, which does not turn.
def sphere(name, size, radius, stops, alpha, soft):
    """A disc whose colour runs through `stops` (fraction of the radius, colour) from the middle out."""
    s = 2; n = size * s; c = n / 2; r = radius * n
    dist = radial((n, n), (c, c), r, (0, 0, 0), (255, 255, 255)).convert("L")
    ramp = []
    for v in range(256):
        f = v / 255
        for (f0, c0), (f1, c1) in zip(stops, stops[1:]):
            if f0 <= f <= f1:
                k = (f - f0) / (f1 - f0 or 1); ramp.append(tuple(int(a + (b - a) * k) for a, b in zip(c0, c1))); break
        else:
            ramp.append(stops[-1][1])
    colour = Image.merge("RGB", [dist.point([ramp[v][i] for v in range(256)]) for i in range(3)])
    disc = Image.new("L", (n, n), 0); ImageDraw.Draw(disc).ellipse((c - r, c - r, c + r, c + r), fill=255)
    edge = disc.filter(ImageFilter.GaussianBlur(soft * s))
    with_alpha(colour, edge, alpha).resize((size, size), Image.LANCZOS).save(f"{OUT}/{name}")

def swirl(name, size, radius, arms, alpha):
    """Faint bevelled strokes curling inside the sphere (light on one side of each, shade on the
    other), evenly spaced: the theme turns this layer slowly, so the sphere seems to move."""
    s = 2; n = size * s; c = n / 2; r = radius * n
    light = Image.new("L", (n, n), 0); dark = Image.new("L", (n, n), 0)
    for k in range(arms):
        base = k * 2 * math.pi / arms
        pts = []
        for i in range(60):
            t = i / 59
            a = base + t * 2.2; rr = r * (0.18 + 0.68 * t)
            pts.append((c + rr * math.cos(a), c + rr * math.sin(a)))
        ImageDraw.Draw(light).line(pts, fill=255, width=int(7 * s), joint="curve")
        ImageDraw.Draw(dark).line([(x + 5 * s, y + 5 * s) for x, y in pts], fill=255, width=int(9 * s), joint="curve")
    disc = Image.new("L", (n, n), 0); ImageDraw.Draw(disc).ellipse((c - r * 0.92, c - r * 0.92, c + r * 0.92, c + r * 0.92), fill=255)
    disc = disc.filter(ImageFilter.GaussianBlur(20 * s))
    im = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    im.alpha_composite(with_alpha(Image.new("RGB", (n, n), (30, 90, 10)), ImageChops.multiply(dark.filter(ImageFilter.GaussianBlur(4 * s)), disc), alpha))
    im.alpha_composite(with_alpha(Image.new("RGB", (n, n), (240, 250, 190)), ImageChops.multiply(light.filter(ImageFilter.GaussianBlur(3 * s)), disc), alpha))
    im.resize((size, size), Image.LANCZOS).save(f"{OUT}/{name}")

sphere("plasma_outer.png", 900, 0.372, [(0.0, (150, 200, 40)), (0.70, (110, 175, 25)), (0.92, (60, 140, 18)), (1.0, (40, 110, 14))], 255, 9)
swirl("plasma_mid.png", 900, 0.372, 3, 115)
sphere("plasma_core.png", 900, 0.32, [(0.0, (236, 236, 160)), (0.45, (214, 218, 90)), (1.0, (170, 196, 34))], 235, 55)
sphere("plasma_spot.png", 900, 0.12, [(0.0, (250, 252, 215)), (1.0, (225, 232, 140))], 120, 40)

g = radial((1000, 1000), (500, 500), 500, (255, 255, 255), (0, 0, 0)).convert("L")
with_alpha(Image.new("RGB", (1000, 1000), (110, 220, 40)), g.point(lambda v: int((v / 255) ** 2.2 * 150))).save(f"{OUT}/plasma_glow.png")
g = radial((900, 900), (450, 450), 900 * 0.36, (255, 255, 255), (0, 0, 0)).convert("L")
with_alpha(Image.new("RGB", (900, 900), (245, 255, 190)), g.point(lambda v: int((v / 255) ** 0.8 * 255))).save(f"{OUT}/plasma_flash.png")

def shell(size=900, rr=0.372):
    """The light on the sphere, which stays put while the layers under it turn: greener and in
    shade towards the top left, a creamy warmth low on the right, a pale halo all round the
    edge, and a soft white gleam at the top left."""
    s = 2; n = size * s; c = n / 2; r = rr * n
    disc = Image.new("L", (n, n), 0); ImageDraw.Draw(disc).ellipse((c - r, c - r, c + r, c + r), fill=255)
    disc = disc.filter(ImageFilter.GaussianBlur(4 * s))
    im = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    shade = radial((n, n), (c - r * 0.75, c - r * 0.8), r * 1.6, (255, 255, 255), (0, 0, 0)).convert("L")
    im.alpha_composite(with_alpha(Image.new("RGB", (n, n), (20, 120, 30)), ImageChops.multiply(shade.point(lambda v: int(v * 0.55)), disc)))
    warm = radial((n, n), (c + r * 0.35, c + r * 0.45), r * 0.9, (255, 255, 255), (0, 0, 0)).convert("L")
    im.alpha_composite(with_alpha(Image.new("RGB", (n, n), (225, 228, 110)), ImageChops.multiply(warm.point(lambda v: int(v * 0.5)), disc)))
    ring = Image.new("L", (n, n), 0); ImageDraw.Draw(ring).ellipse((c - r, c - r, c + r, c + r), outline=255, width=int(14 * s))
    im.alpha_composite(with_alpha(Image.new("RGB", (n, n), (225, 245, 210)), ring.filter(ImageFilter.GaussianBlur(10 * s)), 150))
    gleam = Image.new("L", (n, n), 0); gd = ImageDraw.Draw(gleam)
    gd.ellipse((c - r * 0.66, c - r * 0.74, c - r * 0.30, c - r * 0.48), fill=200)
    im.alpha_composite(with_alpha(Image.new("RGB", (n, n), (255, 255, 250)), gleam.filter(ImageFilter.GaussianBlur(12 * s))))
    dot = Image.new("L", (n, n), 0); ImageDraw.Draw(dot).ellipse((c - r * 0.58, c - r * 0.60, c - r * 0.50, c - r * 0.52), fill=255)
    im.alpha_composite(with_alpha(Image.new("RGB", (n, n), (255, 255, 255)), dot.filter(ImageFilter.GaussianBlur(2 * s)), 230))
    im.resize((size, size), Image.LANCZOS).save(f"{OUT}/shell.png")
shell()

# ------------------------------------------------------------------ angular glass shapes
def cut_poly(x0, y0, x1, y1, cut):
    """Box with the top-right and bottom-left corners cut."""
    return [(x0, y0), (x1 - cut, y0), (x1, y0 + cut), (x1, y1), (x0 + cut, y1), (x0, y1 - cut)]

def glass(draw_size, pts, top, bottom, fill_alpha, edge, glow, s, edge_w=2.5, glow_blur=7, glow_strength=1.3, canvas=None, gloss=True):
    n = (draw_size[0] * s, draw_size[1] * s); P = [(x * s, y * s) for x, y in pts]
    im = canvas or Image.new("RGBA", n, (0, 0, 0, 0))
    line = Image.new("L", n, 0); ImageDraw.Draw(line).line(P + [P[0]], fill=255, width=int(edge_w * s), joint="curve")
    im.alpha_composite(glow_of(line, glow, glow_blur * s, glow_strength))
    body = Image.new("L", n, 0); ImageDraw.Draw(body).polygon(P, fill=255)
    im.alpha_composite(with_alpha(vgrad(n, top, bottom), body, fill_alpha))
    ys = [p[1] for p in P] if gloss else [0, 0]; band = Image.new("L", n, 0)                                        # glossy strip under the top edge
    ImageDraw.Draw(band).rectangle((0, min(ys), n[0], min(ys) + (max(ys) - min(ys)) * 0.42), fill=255)
    im.alpha_composite(with_alpha(Image.new("RGB", n, (255, 255, 255)), ImageChops.multiply(band, body), 26))
    im.alpha_composite(with_alpha(Image.new("RGB", n, edge), line))
    return im

def pod(im, cx, cy, r, s, bright, socket=True):
    """Small glass sphere at the left of each row, with a dark socket in the middle (without one,
    the theme sets the system's own picture into it)."""
    d = ImageDraw.Draw(im); cx, cy, r = cx * s, cy * s, r * s
    ring = Image.new("L", im.size, 0); ImageDraw.Draw(ring).ellipse((cx - r, cy - r, cx + r, cy + r), outline=255, width=3 * s)
    im.alpha_composite(glow_of(ring, (190, 255, 90) if bright else (120, 240, 60), 6 * s, 1.8 if bright else 1.1))
    disc = Image.new("L", im.size, 0); ImageDraw.Draw(disc).ellipse((cx - r, cy - r, cx + r, cy + r), fill=255)
    inner, outer = ((225, 255, 110), (70, 185, 20)) if bright else ((70, 190, 40), (8, 70, 8))
    im.alpha_composite(with_alpha(radial(im.size, (cx - r * 0.3, cy - r * 0.35), r * 1.5, inner, outer), disc, 245))
    d = ImageDraw.Draw(im)
    d.ellipse((cx - r, cy - r, cx + r, cy + r), outline=(215, 255, 150, 255) if bright else (130, 235, 70, 255), width=3 * s)
    if socket:
        d.ellipse((cx - r * 0.5, cy - r * 0.5, cx + r * 0.5, cy + r * 0.5), fill=(2, 30, 2, 235), outline=(150, 240, 80, 255), width=2 * s)
        d.ellipse((cx - r * 0.2, cy - r * 0.2, cx + r * 0.2, cy + r * 0.2), fill=(235, 255, 150, 255) if bright else (90, 200, 50, 255))
    hi = Image.new("L", im.size, 0); ImageDraw.Draw(hi).ellipse((cx - r * 0.72, cy - r * 0.82, cx - r * 0.05, cy - r * 0.42), fill=170)
    im.alpha_composite(with_alpha(Image.new("RGB", im.size, (255, 255, 255)), hi.filter(ImageFilter.GaussianBlur(2 * s))))

def bar_poly(x0, y0, x1, y1, inset=0):
    """The menu bar's outline, after the classic dashboard's: a raised tab along the left part of
    the top, a step down to the rest of the top, cut corners at both ends. `inset` draws the same
    shape that far inside (the thin inner line)."""
    i = inset
    x0, y0, x1, y1 = x0 + i, y0 + i, x1 - i, y1 - i
    tab_end, drop, cut = x0 + (x1 - x0) * 0.30, 10, 12
    return [(x0, y0 + cut), (x0 + cut, y0), (tab_end, y0), (tab_end + drop, y0 + drop), (x1 - cut, y0 + drop),
            (x1, y0 + drop + cut), (x1, y1 - cut), (x1 - cut, y1), (x0 + cut + 4, y1), (x0, y1 - cut - 4)]

def row(name, bright, w=806, h=119):
    """One line of the console list: the pod, a stepped connector, the tabbed glass bar."""
    s = 3; im = Image.new("RGBA", (w * s, h * s), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    line = (215, 255, 150, 255) if bright else (120, 225, 65, 235); y = h / 2
    x0, y0, x1, y1 = 150, 24, w - 8, h - 24
    pts = bar_poly(x0, y0, x1, y1)
    # The connector: out from the top right of the pod, a step down, along into the bar's top-left corner.
    path = [(80, y - 26), (98, y - 26), (110, y - 14), (128, y - 14), (136, y0 + 10)]
    for a, b in zip(path, path[1:]):
        d.line((a[0] * s, a[1] * s, b[0] * s, b[1] * s), fill=line, width=2 * s)
    for nx, ny in (path[0], path[-1]):
        d.ellipse(((nx - 3.5) * s, (ny - 3.5) * s, (nx + 3.5) * s, (ny + 3.5) * s), fill=line)
    d.line((136 * s, (y0 + 10) * s, x0 * s, (y0 + 12) * s), fill=line, width=2 * s)
    if bright:
        glass((w, h), pts, (226, 250, 84), (150, 214, 28), 250, (245, 255, 185), (200, 255, 80), s, 3, 9, 1.9, im)
    else:
        glass((w, h), pts, (22, 110, 18), (6, 58, 6), 170, (120, 228, 66), (110, 240, 60), s, 2.5, 6, 0.9, im)
    inner = [(px * s, py * s) for px, py in bar_poly(x0, y0, x1, y1, inset=6)]
    ImageDraw.Draw(im).line(inner + [inner[0]], fill=(250, 255, 200, 150) if bright else (140, 235, 80, 110), width=s, joint="curve")
    pod(im, 50, y, 38, s, bright, socket=False)
    im.resize((w, h), Image.LANCZOS).save(f"{OUT}/{name}")
row("row.png", False); row("row_selected.png", True)

def badge(name, draw):
    """A picture for the sphere of a home-screen row whose system has no console picture in
    Batocera's Carbon theme: EmuBox's Store and Apps, and a socket for anything else."""
    s = 4; n = 120; im = Image.new("RGBA", (n * s, n * s), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    ink, deep = (236, 255, 170, 255), (2, 30, 2, 235)
    draw(d, s, ink, deep)
    im = im.resize((n, n), Image.LANCZOS)
    glow = glow_of(im.split()[3], (150, 255, 80), 4, 0.9)
    out = Image.new("RGBA", (n, n), (0, 0, 0, 0)); out.alpha_composite(glow); out.alpha_composite(im)
    os.makedirs(f"{OUT}/badges", exist_ok=True); out.save(f"{OUT}/badges/{name}.png")

def _download(d, s, ink, deep):          # the Store: an arrow down into a tray
    w = 7 * s
    d.line((60 * s, 18 * s, 60 * s, 70 * s), fill=ink, width=w)
    d.polygon([(36 * s, 52 * s), (84 * s, 52 * s), (60 * s, 80 * s)], fill=ink)
    d.line([(22 * s, 74 * s), (22 * s, 96 * s), (98 * s, 96 * s), (98 * s, 74 * s)], fill=ink, width=w, joint="curve")

def _tiles(d, s, ink, deep):             # Apps: a grid of rounded tiles
    for x in (26, 64):
        for y in (26, 64):
            d.rounded_rectangle((x * s, y * s, (x + 30) * s, (y + 30) * s), radius=7 * s, fill=ink)

def _socket(d, s, ink, deep):            # anything else: the sphere's old socket
    d.ellipse((38 * s, 38 * s, 82 * s, 82 * s), fill=deep, outline=(150, 240, 80, 255), width=3 * s)
    d.ellipse((52 * s, 52 * s, 68 * s, 68 * s), fill=(150, 240, 80, 255))

def _camera(d, s, ink, deep):            # Captures: a camera
    d.rounded_rectangle((16 * s, 36 * s, 104 * s, 94 * s), radius=10 * s, fill=ink)
    d.rectangle((40 * s, 26 * s, 66 * s, 38 * s), fill=ink)
    d.ellipse((42 * s, 44 * s, 78 * s, 80 * s), fill=deep)
    d.ellipse((51 * s, 53 * s, 69 * s, 71 * s), fill=ink)

def _film(d, s, ink, deep):              # Recordings: a strip of film with a record dot
    d.rounded_rectangle((14 * s, 30 * s, 106 * s, 90 * s), radius=8 * s, fill=ink)
    for x in range(22, 104, 14):
        d.rectangle((x * s, 34 * s, (x + 7) * s, 40 * s), fill=deep)
        d.rectangle((x * s, 80 * s, (x + 7) * s, 86 * s), fill=deep)
    d.ellipse((47 * s, 47 * s, 73 * s, 73 * s), fill=(214, 40, 30, 255))

badge("store", _download); badge("apps", _tiles); badge("default", _socket); badge("captures", _camera)
# The two folders of Captures get the same pictures (camera, film), larger, for the list's media panel.
for folder, draw in (("screenshots", _camera), ("recordings", _film)):
    badge(f"folder-{folder}", draw)

def shape(name, w, h, cut, top, bottom, alpha, edge=(130, 232, 70), glow=(110, 240, 60), strength=1.1, tab=0):
    s = 2; pts = cut_poly(8, 8, w - 8, h - 8, cut)
    im = glass((w, h), pts, top, bottom, alpha, edge, glow, s, 2.5, 7, strength, gloss=h < 100)
    if tab:                                                    # lighter title strip along the top
        d = ImageDraw.Draw(im); tp = [(8, 8), (w - 8 - cut, 8), (w - 8 - cut + tab, 8 + tab), (8, 8 + tab)]
        m = Image.new("L", im.size, 0); ImageDraw.Draw(m).polygon([(x * s, y * s) for x, y in tp], fill=255)
        im.alpha_composite(with_alpha(vgrad(im.size, (120, 215, 50), (64, 160, 26)), m, 215))
        d.line([(8 * s, (8 + tab) * s), ((w - 8 - cut + tab) * s, (8 + tab) * s)], fill=edge + (255,), width=2 * s)
        d.line([(x * s, y * s) for x, y in pts + [pts[0]]], fill=edge + (255,), width=5)
    im.resize((w, h), Image.LANCZOS).save(f"{OUT}/{name}")
shape("panel_header.png", 1152, 135, 34, (16, 90, 14), (4, 44, 4), 215, tab=46)
shape("panel_list.png", 931, 800, 40, (10, 72, 10), (3, 34, 3), 150)
shape("panel_media.png", 883, 470, 36, (6, 46, 6), (2, 22, 2), 205)
shape("panel_desc.png", 883, 318, 30, (12, 80, 12), (3, 36, 3), 200)
shape("selector.png", 880, 62, 16, (226, 250, 84), (150, 214, 28), 250, (245, 255, 185), (200, 255, 80), 1.6)

def frame(name, top, bottom, edge, size=96, cut=20):               # nine-patch pieces for pop-up menus
    s = 3; n = size * s; im = Image.new("RGBA", (n, n), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    pts = [(x * s, y * s) for x, y in cut_poly(3, 3, size - 3, size - 3, cut)]
    m = Image.new("L", (n, n), 0); ImageDraw.Draw(m).polygon(pts, fill=255)
    im.alpha_composite(with_alpha(vgrad((n, n), top, bottom), m, 244)); d = ImageDraw.Draw(im)
    d.line(pts + [pts[0]], fill=edge, width=3 * s, joint="curve"); im.resize((size, size), Image.LANCZOS).save(f"{OUT}/{name}")
# The pop-up menus' pane, buttons and switches are drawn by menu_art.py (run it after this).
Image.new("RGBA", (8, 8), (255, 255, 255, 255)).save(f"{OUT}/white.png")
# hologram overlays for the whole screen: fine scan lines (tiled) and a soft band of light that rolls down
sl = Image.new("RGBA", (4, 3), (0, 0, 0, 0))
for x in range(4): sl.putpixel((x, 2), (0, 12, 0, 62))
sl.save(f"{OUT}/scanlines.png")
band = Image.new("RGBA", (4, 256), (190, 255, 170, 0))
for y in range(256):
    a_ = int(26 * math.sin(math.pi * y / 255) ** 3)
    for x in range(4): band.putpixel((x, y), (190, 255, 170, a_))
band.save(f"{OUT}/rollband.png")

# ------------------------------------------------------------------ button hints: glowing green controller button + keyboard key
S = 4; HH = 96; hh = HH * S
LIGHT, DARK, EDGE = (214, 255, 170, 255), (3, 38, 3, 255), (150, 245, 80, 255)
def fnt(file, px): return ImageFont.truetype(f"{OUT}/fonts/{file}", px * S)
def pad_button(label=None, draw=None):
    im = Image.new("RGBA", (hh, hh), (0, 0, 0, 0)); m = 4 * S
    ring = Image.new("L", (hh, hh), 0); ImageDraw.Draw(ring).ellipse((m, m, hh - m, hh - m), outline=255, width=6 * S)
    d = ImageDraw.Draw(im)
    d.ellipse((m, m, hh - m, hh - m), fill=(12, 84, 10, 255), outline=EDGE, width=7 * S)
    if label: d.text((hh / 2, hh / 2 - 1 * S), label, font=fnt("Rajdhani-SemiBold.ttf", 78), fill=(240, 255, 215, 255), anchor="mm", stroke_width=1 * S, stroke_fill=(240, 255, 215, 255))
    if draw: draw(d)
    return im
def menu_glyph(d):
    for y in (33, 48, 63): d.rounded_rectangle((28 * S, (y - 4) * S, 68 * S, (y + 4) * S), radius=3 * S, fill=LIGHT)
def view_glyph(d):
    d.rounded_rectangle((31 * S, 33 * S, 55 * S, 52 * S), radius=3 * S, outline=LIGHT, width=4 * S)
    d.rounded_rectangle((41 * S, 44 * S, 65 * S, 63 * S), radius=3 * S, fill=(20, 104, 16, 255), outline=LIGHT, width=4 * S)
def pill(label):
    f = fnt("Michroma-Regular.ttf", 34); w = int(f.getlength(label)) + 44 * S
    im = Image.new("RGBA", (w, hh), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    d.rounded_rectangle((4 * S, 20 * S, w - 4 * S, hh - 20 * S), radius=24 * S, fill=(20, 104, 16, 255), outline=EDGE, width=5 * S)
    d.text((w / 2, hh / 2 - 1 * S), label, font=f, fill=LIGHT, anchor="mm"); return im
def keycap(label=None, arrows=None):
    f = fnt("Rajdhani-SemiBold.ttf", 62)
    inner = int(f.getlength(label)) if label else len(arrows) * 34 * S + (len(arrows) - 1) * 6 * S
    w = max(inner + 36 * S, 78 * S); im = Image.new("RGBA", (w, hh), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    d.rounded_rectangle((3 * S, 7 * S, w - 3 * S, hh - 7 * S), radius=12 * S, fill=(3, 38, 3, 235), outline=(140, 235, 80, 255), width=5 * S)
    if label: d.text((w / 2, hh / 2 - 4 * S), label, font=f, fill=(240, 255, 215, 255), anchor="mm")
    else:
        x = (w - inner) / 2
        for a in arrows:
            cx, cy, r = x + 17 * S, hh / 2, 13 * S
            d.polygon({"u": [(cx, cy - r), (cx - r, cy + r * .8), (cx + r, cy + r * .8)], "d": [(cx, cy + r), (cx - r, cy - r * .8), (cx + r, cy - r * .8)],
                       "l": [(cx - r, cy), (cx + r * .8, cy - r), (cx + r * .8, cy + r)], "r": [(cx + r, cy), (cx - r * .8, cy - r), (cx - r * .8, cy + r)]}[a], fill=LIGHT)
            x += 40 * S
    return im
def dpad(active):
    im = Image.new("RGBA", (hh, hh), (0, 0, 0, 0)); d = ImageDraw.Draw(im); c, a, t = hh / 2, 38 * S, 13 * S
    for k, box in {"u": (c - t, c - a, c + t, c), "d": (c - t, c, c + t, c + a), "l": (c - a, c - t, c, c + t), "r": (c, c - t, c + a, c + t)}.items():
        d.rounded_rectangle(box, radius=5 * S, fill=LIGHT if k in active else (40, 130, 30, 255), outline=EDGE, width=2 * S)
    d.rectangle((c - t, c - t, c + t, c + t), fill=(40, 130, 30, 255)); return im
def join(*parts, gap=10):
    w = sum(p.width for p in parts) + gap * S * (len(parts) - 1); im = Image.new("RGBA", (w, hh), (0, 0, 0, 0)); x = 0
    for p in parts: im.alpha_composite(p, (x, 0)); x += p.width + gap * S
    return im.resize((round(w / S), HH), Image.LANCZOS)
# Batocera's "b" is the bottom face button (Xbox A), "a" the right (Xbox B), "x" the top (Xbox Y), "y" the left (Xbox X).
for name, im in {"confirm_b": join(pad_button("A"), keycap("Enter")), "back_a": join(pad_button("B"), keycap("Esc")),
                 "top_x": join(pad_button("Y"), keycap("=")), "left_y": join(pad_button("X"), keycap("-")),
                 "start": join(pad_button(draw=menu_glyph), keycap("Space")), "select": join(pad_button(draw=view_glyph), keycap("Bksp")),
                 "l": join(pill("LB")), "r": join(pill("RB")), "updown": join(dpad("ud"), keycap(arrows="ud")),
                 "leftright": join(dpad("lr"), keycap(arrows="lr")), "all": join(dpad("udlr"), keycap(arrows="udlr"))}.items():
    im.save(f"{OUT}/help/xk_{name}.png")

# Controller silhouette for the on-screen "controller lights" (white, so the theme can tint it).
def gamepad():
    s = 4; im = Image.new("RGBA", (96 * s, 64 * s), (0, 0, 0, 0)); d = ImageDraw.Draw(im); white, hole = (255, 255, 255, 255), (0, 0, 0, 0)
    d.rounded_rectangle((14 * s, 10 * s, 82 * s, 40 * s), radius=14 * s, fill=white)
    d.ellipse((4 * s, 14 * s, 40 * s, 60 * s), fill=white); d.ellipse((56 * s, 14 * s, 92 * s, 60 * s), fill=white)
    d.ellipse((34 * s, 34 * s, 62 * s, 70 * s), fill=hole)
    d.rectangle((22 * s, 21 * s, 34 * s, 25 * s), fill=hole); d.rectangle((26 * s, 17 * s, 30 * s, 29 * s), fill=hole)
    for cx, cy in ((68, 17), (74, 23), (62, 23), (68, 29)): d.ellipse(((cx - 3) * s, (cy - 3) * s, (cx + 3) * s, (cy + 3) * s), fill=hole)
    im.resize((96, 64), Image.LANCZOS).save(f"{OUT}/gamepad.png")
gamepad()

# ------------------------------------------------------------------ emblems for systems Batocera's theme has none for
def system_logo(system, text):
    """White lettering on clear; the theme tints it like the borrowed logos."""
    os.makedirs(f"{OUT}/logos", exist_ok=True)
    font = ImageFont.truetype(f"{OUT}/fonts/Michroma-Regular.ttf", 150)
    width = int(ImageDraw.Draw(Image.new("L", (1, 1))).textlength(text, font=font))
    image = Image.new("RGBA", (width + 60, 240), (0, 0, 0, 0))
    ImageDraw.Draw(image).text((30, 30), text, font=font, fill=(255, 255, 255, 255))
    image.save(f"{OUT}/logos/{system}.png")
system_logo("store", "STORE")
system_logo("apps", "APPS")
system_logo("captures", "CAPTURES")
print("art written (sounds: see sounds.py)")
