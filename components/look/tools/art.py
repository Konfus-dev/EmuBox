#!/usr/bin/env python3
"""Generates every image used by the EmuBox theme.  Usage: python3 art.py <theme folder>
All artwork and audio is original and procedural (no console maker's assets are used)."""
import sys, math, random, struct, wave, os
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

# ------------------------------------------------------------------ backgrounds
def globe_grid(size, center, R, alpha):
    """Thin curved lines like the inside of a huge wireframe sphere."""
    s = 2; layer = Image.new("RGBA", (size[0] * s, size[1] * s), (0, 0, 0, 0)); d = ImageDraw.Draw(layer)
    cx, cy = center[0] * s, center[1] * s; R *= s; col = (150, 255, 110, alpha)
    for a in range(6, 90, 7):                                   # meridians
        rx = R * math.sin(math.radians(a))
        d.ellipse((cx - rx, cy - R, cx + rx, cy + R), outline=col, width=2 * s)
    for b in range(-84, 85, 7):                                 # parallels (tilted towards the viewer)
        y = cy + R * math.sin(math.radians(b)) * 0.92; rx = R * math.cos(math.radians(b)); ry = rx * 0.16
        d.ellipse((cx - rx, y - ry, cx + rx, y + ry), outline=col, width=2 * s)
    return layer.resize(size, Image.LANCZOS).rotate(-9, resample=Image.BICUBIC).filter(ImageFilter.GaussianBlur(0.5))

def background(name, glow_center, inner, outer, radius, grid_center, grid_alpha):
    bg = radial((W, H), glow_center, radius, inner, outer).convert("RGBA")
    bg.alpha_composite(globe_grid((W, H), grid_center, 1500, grid_alpha))
    # big soft "tube" arcs in the distance
    tubes = Image.new("RGBA", (W, H), (0, 0, 0, 0)); td = ImageDraw.Draw(tubes)
    td.arc((-700, 250, 900, 1850), 250, 340, fill=(90, 220, 50, 26), width=90)
    td.arc((1100, -900, 2700, 700), 60, 160, fill=(90, 220, 50, 22), width=120)
    bg.alpha_composite(tubes.filter(ImageFilter.GaussianBlur(14)))
    # the sweeping line that carries the button hints, bottom left
    sweep = Image.new("RGBA", (W * 2, H * 2), (0, 0, 0, 0)); sd = ImageDraw.Draw(sweep)
    sd.arc((-1500, 1150, 2300, 3400), 200, 318, fill=(150, 255, 90, 120), width=5)
    sd.arc((-1500, 1186, 2300, 3436), 200, 300, fill=(150, 255, 90, 50), width=3)
    bg.alpha_composite(sweep.resize((W, H), Image.LANCZOS))
    v = radial((W, H), (W / 2, H / 2), W * 0.74, (0, 0, 0), (165, 165, 165)).convert("L")
    Image.composite(Image.new("RGB", (W, H), (0, 6, 0)), bg.convert("RGB"), v).save(f"{OUT}/{name}", quality=92)

background("bg_system.jpg", (520, 470), (44, 150, 18), (2, 26, 2), 1150, (520, 470), 34)
background("bg_list.jpg", (960, 560), (40, 140, 16), (5, 50, 5), 1300, (960, 520), 38)

# ------------------------------------------------------------------ plasma orb layers
def blob(name, size, base, lumps, seed, inner, outer, alpha, blur):
    s = 2; n = size * s; c = n / 2; rnd = random.Random(seed)
    terms = [(k, rnd.uniform(0.02, lumps) / (1 + 0.35 * k), rnd.uniform(0, 6.283)) for k in range(2, 7)]
    pts = []
    for i in range(720):
        t = i / 720 * 6.283185; r = base * n * (1 + sum(a * math.sin(k * t + ph) for k, a, ph in terms))
        pts.append((c + r * math.cos(t), c + r * math.sin(t)))
    m = Image.new("L", (n, n), 0); ImageDraw.Draw(m).polygon(pts, fill=255)
    body = with_alpha(radial((n, n), (c, c), base * n * 1.25, inner, outer), m.filter(ImageFilter.GaussianBlur(blur * s)), alpha)
    body.resize((size, size), Image.LANCZOS).save(f"{OUT}/{name}")
blob("plasma_outer.png", 900, 0.300, 0.15, 11, (120, 230, 30), (30, 140, 10), 170, 16)
blob("plasma_mid.png",   900, 0.265, 0.19, 23, (200, 250, 70), (90, 200, 10), 200, 10)
blob("plasma_core.png",  900, 0.215, 0.14, 37, (238, 255, 130), (165, 230, 34), 255, 7)
blob("plasma_spot.png",  900, 0.110, 0.30, 51, (252, 255, 195), (218, 250, 100), 150, 14)

g = radial((1000, 1000), (500, 500), 500, (255, 255, 255), (0, 0, 0)).convert("L")
with_alpha(Image.new("RGB", (1000, 1000), (130, 255, 40)), g.point(lambda v: int((v / 255) ** 1.6 * 210))).save(f"{OUT}/plasma_glow.png")
g = radial((900, 900), (450, 450), 900 * 0.36, (255, 255, 255), (0, 0, 0)).convert("L")
with_alpha(Image.new("RGB", (900, 900), (245, 255, 190)), g.point(lambda v: int((v / 255) ** 0.8 * 255))).save(f"{OUT}/plasma_flash.png")

def shell(size=900, rr=0.372):
    """Glass ball around the plasma: darker towards the rim, bright edge, soft highlights."""
    s = 2; n = size * s; c = n / 2; r = rr * n
    disc = Image.new("L", (n, n), 0); ImageDraw.Draw(disc).ellipse((c - r, c - r, c + r, c + r), fill=255)
    limb = radial((n, n), (c, c), r, (0, 0, 0), (255, 255, 255)).convert("L").point(lambda v: int((v / 255) ** 3.2 * 215))
    im = with_alpha(Image.new("RGB", (n, n), (8, 78, 8)), ImageChops.multiply(limb, disc))
    edge = Image.new("L", (n, n), 0); ImageDraw.Draw(edge).ellipse((c - r, c - r, c + r, c + r), outline=255, width=4 * s)
    im.alpha_composite(glow_of(edge, (150, 255, 90), 7 * s, 1.6)); im.alpha_composite(with_alpha(Image.new("RGB", (n, n), (200, 255, 150)), edge, 230))
    hi = Image.new("L", (n, n), 0); hd = ImageDraw.Draw(hi)
    hd.ellipse((c - r * 0.74, c - r * 0.86, c - r * 0.02, c - r * 0.38), fill=150)          # top-left highlight
    hd.ellipse((c - r * 0.80, c - r * 0.70, c + r * 0.10, c - r * 0.20), fill=0)
    hd.arc((c - r * 0.9, c - r * 0.9, c + r * 0.9, c + r * 0.9), 30, 75, fill=110, width=10 * s)   # bounce light, lower right
    im.alpha_composite(with_alpha(Image.new("RGB", (n, n), (240, 255, 220)), hi.filter(ImageFilter.GaussianBlur(9 * s))))
    im.resize((size, size), Image.LANCZOS).save(f"{OUT}/shell.png")
shell()

def sym_ring(name, parts, size=1000):
    """Glass shards in evenly repeated segments, so turning one step looks identical to the start."""
    s = 2; n = size * s; c = n / 2; im = Image.new("RGBA", (n, n), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    for (count, radius, width, span, offset, alpha) in parts:
        r = radius * n; box = (c - r, c - r, c + r, c + r); step = 360 / count
        mid = (box[0] + width * s * 0.45, box[1] + width * s * 0.45, box[2] - width * s * 0.45, box[3] - width * s * 0.45)
        inner = (box[0] + width * s, box[1] + width * s, box[2] - width * s, box[3] - width * s)
        for k in range(count):
            a0 = offset + k * step; a1 = a0 + span
            d.arc(box, a0, a1, fill=(40, 180, 30, alpha), width=width * s)                    # glass body
            d.arc(mid, a0 + 1, a1 - 1, fill=(110, 235, 60, alpha), width=int(width * s * 0.3))  # lighter band inside
            d.arc(box, a0, a1, fill=(205, 255, 140, min(255, alpha + 90)), width=4 * s)       # bright outer edge
            d.arc(inner, a0, a1, fill=(14, 96, 14, min(255, alpha + 40)), width=4 * s)        # dark inner edge
    im.resize((size, size), Image.LANCZOS).save(f"{OUT}/{name}")
sym_ring("rings_a.png", [(6, 0.425, 54, 41, 8, 120)])                              # turns 60 degrees per move
sym_ring("rings_b.png", [(8, 0.468, 18, 30, 0, 95)])                               # turns 45
sym_ring("rings_c.png", [(12, 0.497, 8, 17, 3, 85)])                               # turns 30

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

def pod(im, cx, cy, r, s, bright):
    """Small glass sphere at the left of each row, with a dark socket in the middle."""
    d = ImageDraw.Draw(im); cx, cy, r = cx * s, cy * s, r * s
    ring = Image.new("L", im.size, 0); ImageDraw.Draw(ring).ellipse((cx - r, cy - r, cx + r, cy + r), outline=255, width=3 * s)
    im.alpha_composite(glow_of(ring, (190, 255, 90) if bright else (120, 240, 60), 6 * s, 1.8 if bright else 1.1))
    disc = Image.new("L", im.size, 0); ImageDraw.Draw(disc).ellipse((cx - r, cy - r, cx + r, cy + r), fill=255)
    inner, outer = ((225, 255, 110), (70, 185, 20)) if bright else ((70, 190, 40), (8, 70, 8))
    im.alpha_composite(with_alpha(radial(im.size, (cx - r * 0.3, cy - r * 0.35), r * 1.5, inner, outer), disc, 245))
    d = ImageDraw.Draw(im)
    d.ellipse((cx - r, cy - r, cx + r, cy + r), outline=(215, 255, 150, 255) if bright else (130, 235, 70, 255), width=3 * s)
    d.ellipse((cx - r * 0.5, cy - r * 0.5, cx + r * 0.5, cy + r * 0.5), fill=(2, 30, 2, 235), outline=(150, 240, 80, 255), width=2 * s)
    d.ellipse((cx - r * 0.2, cy - r * 0.2, cx + r * 0.2, cy + r * 0.2), fill=(235, 255, 150, 255) if bright else (90, 200, 50, 255))
    hi = Image.new("L", im.size, 0); ImageDraw.Draw(hi).ellipse((cx - r * 0.72, cy - r * 0.82, cx - r * 0.05, cy - r * 0.42), fill=170)
    im.alpha_composite(with_alpha(Image.new("RGB", im.size, (255, 255, 255)), hi.filter(ImageFilter.GaussianBlur(2 * s))))

def row(name, bright, w=806, h=119):
    """One line of the console list: sphere, circuit-style connector, angular glass bar."""
    s = 3; im = Image.new("RGBA", (w * s, h * s), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    line = (215, 255, 150, 255) if bright else (120, 225, 65, 235); y = h / 2
    for a, b in [((92, y), (112, y)), ((112, y), (124, y - 14)), ((124, y - 14), (142, y - 14)), ((112, y), (124, y + 14)), ((124, y + 14), (142, y + 14))]:
        d.line((a[0] * s, a[1] * s, b[0] * s, b[1] * s), fill=line, width=2 * s)
    for nx, ny in [(112, y), (124, y - 14), (124, y + 14)]:
        d.ellipse(((nx - 3) * s, (ny - 3) * s, (nx + 3) * s, (ny + 3) * s), fill=line)
    pts = cut_poly(142, 27, w - 8, h - 27, 20)
    if bright:
        glass((w, h), pts, (226, 250, 84), (150, 214, 28), 250, (245, 255, 185), (200, 255, 80), s, 3, 9, 1.9, im)
    else:
        glass((w, h), pts, (22, 110, 18), (6, 58, 6), 170, (120, 228, 66), (110, 240, 60), s, 2.5, 6, 0.9, im)
    pod(im, 50, y, 38, s, bright)
    im.resize((w, h), Image.LANCZOS).save(f"{OUT}/{name}")
row("row.png", False); row("row_selected.png", True)

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
print("art written (sounds: see sounds.py)")
