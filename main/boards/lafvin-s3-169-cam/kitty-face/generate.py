#!/usr/bin/env python3
"""Kitty face generator: draws the Mission Kitty robot-cat face and writes the kitty-gif collection.

Every face is vector art drawn here (no source images): a cream robot-cat head with a dark glass
visor, glowing aqua LED eyes and mouth, pink cheeks and an antenna light. Frames are drawn at 4x
and downsampled, then given a thin white sticker edge so the 1-bit GIF transparency stays clean on
the light and the dark theme.

    python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
    .venv/bin/python generate.py                       # writes ../kitty-gif/*.gif
    .venv/bin/python generate.py --sheet sheet.png     # also a 240x280 contact sheet

The GIFs are 200x200 (shown 1:1 on the 240x280 panel) and loop forever. They use full frames
with disposal 2 (restore to background), which the firmware's gifdec handles without ghosting.
"""

import argparse
import math
from dataclasses import dataclass, field, replace
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

SIZE = 200  # final GIF size (px), sized to read on the 240x280 panel (--size to change)
S = 4  # supersampling factor
W = SIZE * S
# All drawing coordinates below are in a 120x120 design space and scale with SIZE.

OUTLINE = (62, 54, 92)
SHELL = (255, 250, 244)
SHELL_SHADE = (240, 230, 238)
EAR_IN = (255, 166, 200)
VISOR = (30, 33, 58)
LED = (112, 236, 255)
LED_CORE = (214, 251, 255)
PINK = (255, 112, 168)
HEART = (255, 86, 132)
GOLD = (255, 210, 84)
TEAR = (140, 210, 255)
RED = (255, 92, 92)
DIM = (150, 156, 214)
WHITE = (255, 255, 255)
QUESTION = (132, 98, 236)  # violet: reads on the light and the dark theme

HEAD = (12, 34, 108, 106)  # x0, y0, x1, y1
HEAD_R = 27
VISOR_BOX = (22, 46, 98, 96)
VISOR_R = 18
EYE_L = (44, 69)
EYE_R = (76, 69)
MOUTH = (60, 86)
PIVOT = (60, 72)


def p(v):
    return v * S * SIZE / 120


def pts(seq):
    return [(p(x), p(y)) for x, y in seq]


# ---------------------------------------------------------------------------------------------
# Pose: everything a frame needs
# ---------------------------------------------------------------------------------------------


@dataclass
class Pose:
    eyes: tuple = (("open",), ("open",))
    look: tuple = (0.0, 0.0)
    mouth: tuple = ("w",)
    blush: float = 0.75
    dx: float = 0.0
    dy: float = 0.0
    tilt: float = 0.0
    ears: tuple = (0.0, 0.0)  # extra outward rotation (deg) of each ear; negative perks inward
    antenna: tuple = (PINK, 0.6)
    extras: list = field(default_factory=list)  # callables (draw, phase) on the top layer
    visor_extras: list = field(default_factory=list)  # callables drawn inside the visor
    phase: float = 0.0


# ---------------------------------------------------------------------------------------------
# Primitive helpers (coordinates in final px)
# ---------------------------------------------------------------------------------------------


def ellipse(d, cx, cy, rx, ry, fill):
    d.ellipse([p(cx - rx), p(cy - ry), p(cx + rx), p(cy + ry)], fill=fill)


def stroke(d, points, width, fill):
    xy = pts(points)
    d.line(xy, fill=fill, width=int(p(width)), joint="curve")
    r = width / 2
    for x, y in (points[0], points[-1]):
        ellipse(d, x, y, r, r, fill)


def arc_points(cx, cy, rx, ry, a0, a1, n=24):
    out = []
    for i in range(n + 1):
        a = math.radians(a0 + (a1 - a0) * i / n)
        out.append((cx + rx * math.cos(a), cy + ry * math.sin(a)))
    return out


def heart_points(cx, cy, size, n=48):
    out = []
    for i in range(n):
        t = 2 * math.pi * i / n
        x = 16 * math.sin(t) ** 3
        y = 13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t)
        out.append((cx + x * size / 32, cy - y * size / 32))
    return out


def star_points(cx, cy, r, rot=0.0, n=5, inner=0.45):
    out = []
    for i in range(n * 2):
        rr = r if i % 2 == 0 else r * inner
        a = math.radians(rot - 90 + i * 180 / n)
        out.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
    return out


def sparkle_points(cx, cy, r):
    return star_points(cx, cy, r, 0, 4, 0.28)


def rotate_about(points, cx, cy, deg):
    a = math.radians(deg)
    c, s = math.cos(a), math.sin(a)
    return [(cx + (x - cx) * c - (y - cy) * s, cy + (x - cx) * s + (y - cy) * c) for x, y in points]


# ---------------------------------------------------------------------------------------------
# Eyes and mouths (drawn on the LED layer inside the visor)
# ---------------------------------------------------------------------------------------------


def draw_eye(d, cx, cy, spec, side):
    kind = spec[0]
    if kind in ("open", "blink"):
        sx = spec[1] if kind == "open" and len(spec) > 1 else 1.0
        sy = spec[2] if kind == "open" and len(spec) > 2 else sx
        close = spec[1] if kind == "blink" else 0.0
        rx, ry = 8.2 * sx, 10.6 * sy * (1 - close)
        if ry < 1.6:
            stroke(d, [(cx - 7.5, cy + 1), (cx + 7.5, cy + 1)], 3.0, LED)
            return
        ellipse(d, cx, cy, rx, ry, LED)
        if close < 0.4:
            ellipse(d, cx - rx * 0.32, cy - ry * 0.36, 2.9 * sx, 2.9 * sx * (1 - close), WHITE)
            ellipse(d, cx + rx * 0.34, cy + ry * 0.34, 1.3 * sx, 1.3 * sx, LED_CORE)
    elif kind == "happy":  # ^ closed, smiling
        stroke(d, arc_points(cx, cy + 4, 8, 7.5, 200, 340), 3.4, LED)
    elif kind == "content":  # u closed, relaxed or asleep
        stroke(d, arc_points(cx, cy - 2, 7.5, 5.5, 20, 160), 3.2, LED)
    elif kind == "line":
        stroke(d, [(cx - 7.5, cy + 1), (cx + 7.5, cy + 1)], 3.2, LED)
    elif kind == "heart":
        scale = spec[1] if len(spec) > 1 else 1.0
        d.polygon(pts(heart_points(cx, cy + 1, 22 * scale)), fill=HEART)
        ellipse(d, cx - 4 * scale, cy - 3 * scale, 2.2 * scale, 2.2 * scale, (255, 214, 228))
    elif kind == "star":
        scale = spec[1] if len(spec) > 1 else 1.0
        rot = spec[2] if len(spec) > 2 else 0.0
        d.polygon(pts(star_points(cx, cy, 11 * scale, rot)), fill=GOLD)
    elif kind == "squeeze":  # > on the left eye, < on the right
        k = 1 if side == "L" else -1
        stroke(d, [(cx - 6 * k, cy - 7), (cx + 6 * k, cy), (cx - 6 * k, cy + 7)], 3.4, LED)
    elif kind == "ring":
        r = spec[1] if len(spec) > 1 else 10.0
        ellipse(d, cx, cy, r, r, LED)
        ellipse(d, cx, cy, r - 3.2, r - 3.2, (0, 0, 0, 0))
        ellipse(d, cx, cy, 2.4, 2.4, LED)
    elif kind == "dot":
        r = spec[1] if len(spec) > 1 else 4.5
        ellipse(d, cx, cy, r, r, LED)
        ellipse(d, cx - r * 0.3, cy - r * 0.35, r * 0.35, r * 0.35, WHITE)
    elif kind == "lid":  # open eye with a slanted lid; slope > 0 lowers the inner corner
        slope = spec[1]
        ellipse(d, cx, cy, 8.2, 10.6, LED)
        ellipse(d, cx - 2.6, cy + 1.5, 2.4, 2.4, WHITE)
        k = slope if side == "L" else -slope
        top = cy - 3.5
        d.polygon(pts([(cx - 12, top - 12 * k - 20), (cx + 12, top - 20 + 12 * k),
                       (cx + 12, top + 12 * k), (cx - 12, top - 12 * k)]), fill=(0, 0, 0, 0))
    elif kind == "half":  # half-lidded, confident or sleepy
        cut = spec[1] if len(spec) > 1 else 0.0
        ellipse(d, cx, cy, 8.2, 10.6, LED)
        d.rectangle([p(cx - 10), p(cy - 14), p(cx + 10), p(cy + cut)], fill=(0, 0, 0, 0))
        stroke(d, [(cx - 8, cy + cut), (cx + 8, cy + cut)], 2.6, LED)
    elif kind == "spiral":
        rot = spec[1] if len(spec) > 1 else 0.0
        sp = []
        for i in range(60):
            t = i / 59
            a = math.radians(rot + t * 600)
            r = 1 + 8.5 * t
            sp.append((cx + r * math.cos(a), cy + r * math.sin(a)))
        stroke(d, sp, 2.4, LED)


def draw_mouth(d, spec):
    cx, cy = MOUTH
    kind = spec[0]
    if kind == "w":  # cat mouth
        stroke(d, arc_points(cx - 3.6, cy - 1, 3.6, 3.4, 10, 170), 2.4, LED)
        stroke(d, arc_points(cx + 3.6, cy - 1, 3.6, 3.4, 10, 170), 2.4, LED)
    elif kind == "talk":  # cat mouth with an open jaw: spec[1] = how open (0..1)
        h = 2 + 6 * spec[1]
        d.chord([p(cx - 6), p(cy - h), p(cx + 6), p(cy + h)], 0, 180, fill=LED)
        d.chord([p(cx - 4.2), p(cy - h + 2), p(cx + 4.2), p(cy + h - 1.5)], 0, 180,
                fill=(255, 128, 168))
        stroke(d, arc_points(cx - 3.6, cy - 1, 3.6, 3.0, 10, 170), 2.2, LED)
        stroke(d, arc_points(cx + 3.6, cy - 1, 3.6, 3.0, 10, 170), 2.2, LED)
    elif kind == "smile":
        w = spec[1] if len(spec) > 1 else 8
        stroke(d, arc_points(cx, cy - 4, w, 5.5, 25, 155), 2.6, LED)
    elif kind == "open":  # big happy D
        w = spec[1] if len(spec) > 1 else 9
        h = spec[2] if len(spec) > 2 else 8
        d.chord([p(cx - w), p(cy - h - 2), p(cx + w), p(cy + h - 2)], 0, 180, fill=LED)
        d.chord([p(cx - w + 2.2), p(cy - h + 0.6), p(cx + w - 2.2), p(cy + h - 4)], 0, 180,
                fill=VISOR)
        ellipse(d, cx, cy + h * 0.45, w * 0.45, h * 0.32, (255, 128, 168))
    elif kind == "o":
        r = spec[1] if len(spec) > 1 else 3.5
        ellipse(d, cx, cy, r, r * 1.15, LED)
        ellipse(d, cx, cy, r - 2.2, r * 1.15 - 2.2, (0, 0, 0, 0))
    elif kind == "flat":
        w = spec[1] if len(spec) > 1 else 5
        stroke(d, [(cx - w, cy), (cx + w, cy)], 2.4, LED)
    elif kind == "frown":
        w = spec[1] if len(spec) > 1 else 6
        stroke(d, arc_points(cx, cy + 5, w, 4.5, 205, 335), 2.4, LED)
    elif kind == "smirk":
        stroke(d, [(cx - 6, cy + 1)] + arc_points(cx + 1, cy - 3, 6, 4, 90, 10, 10), 2.4, LED)
    elif kind == "tongue":  # cat mouth with a tongue; spec[1] = sideways offset
        off = spec[1] if len(spec) > 1 else 0
        ellipse(d, cx + off, cy + 4.5, 3.4, 4.2, (255, 128, 168))
        stroke(d, [(cx + off, cy + 2.6), (cx + off, cy + 6.5)], 1.0, (226, 84, 130))
        draw_mouth(d, ("w",))
    elif kind == "kiss":  # a little "3"
        stroke(d, arc_points(cx, cy - 2.5, 3.2, 2.6, -90, 90, 12), 2.4, LED)
        stroke(d, arc_points(cx, cy + 2.7, 3.2, 2.6, -90, 90, 12), 2.4, LED)
    elif kind == "wavy":
        w = []
        for i in range(17):
            x = cx - 8 + i
            w.append((x, cy + 1.6 * math.sin(i / 16 * 4 * math.pi)))
        stroke(d, w, 2.2, LED)


# ---------------------------------------------------------------------------------------------
# Extras (top layer, final px)
# ---------------------------------------------------------------------------------------------


def sparkles(positions):
    def draw(d, ph):
        for i, (x, y, r) in enumerate(positions):
            s = 0.35 + 0.65 * abs(math.sin(math.pi * (ph + i / len(positions))))
            d.polygon(pts(sparkle_points(x, y, r * s)), fill=GOLD)
    return draw


def zzz(d, ph):
    for i in range(3):
        t = (ph + i / 3) % 1.0
        size = 2.2 + 2.2 * t
        x = 106 + 7 * t + 1.2 * math.sin(t * 6)
        y = 50 - 40 * t
        col = tuple(int(c + (255 - c) * max(0, t - 0.7) * 1.6) for c in (96, 104, 190))
        stroke(d, [(x - size, y - size), (x + size, y - size), (x - size, y + size),
                   (x + size, y + size)], 2.6, col)


def question(d, ph):
    bob = 2.5 * math.sin(2 * math.pi * ph)
    x, y = 100, 16 + bob
    stroke(d, arc_points(x, y, 5.5, 5, 190, 400, 20) + [(x, y + 8)], 3.4, QUESTION)
    ellipse(d, x, y + 13.5, 2.3, 2.3, QUESTION)


def thought_dots(d, ph):
    for i in range(3):
        on = ph * 4 > i + 0.5
        r = (2.4 + 0.6 * i) if on else 1.6
        col = GOLD if on else (220, 214, 232)
        ellipse(d, 104 + i * 5, 44 - i * 11, r, r, col)


def floating_hearts(d, ph):
    for i, (x0, side) in enumerate(((10, -1), (110, 1))):
        t = (ph + i * 0.5) % 1.0
        x = x0 + side * 2 * math.sin(t * 2 * math.pi)
        y = 70 - 46 * t
        size = 9 + 5 * math.sin(t * math.pi)
        d.polygon(pts(heart_points(x, y, size)), fill=HEART)


def sweat(d, ph):
    y = 40 + 4 * ph
    d.polygon(pts([(103, y - 7), (99, y + 1), (107, y + 1)]), fill=TEAR)
    ellipse(d, 103, y + 1.5, 4, 4, TEAR)
    ellipse(d, 102, y + 0.5, 1.2, 1.2, WHITE)


def anger_mark(d, ph):
    s = 1 + 0.18 * math.sin(2 * math.pi * ph * 2)
    cx, cy = 100, 30
    for a in (45, 135, 225, 315):
        r = math.radians(a)
        ox, oy = cx + 4.2 * s * math.cos(r), cy + 4.2 * s * math.sin(r)
        stroke(d, arc_points(ox, oy, 3 * s, 3 * s, a + 90, a + 270, 8), 2.4, RED)


def sound_waves(d, ph):
    for i in range(2):
        t = (ph + i * 0.5) % 1.0
        r = 7 + 9 * t
        col = tuple(int(c + (255 - c) * t * 0.85) for c in (70, 196, 230))
        stroke(d, arc_points(10, 72, r * 0.6, r, 120, 240, 14), 2.6, col)
        stroke(d, arc_points(110, 72, r * 0.6, r, -60, 60, 14), 2.6, col)


def tears(d, ph):
    for i, ex in enumerate((EYE_L[0], EYE_R[0])):
        t = (ph + i * 0.5) % 1.0
        y = 80 + 16 * t
        ellipse(d, ex - 6, y, 2.3, 3.0, TEAR)
        stroke(d, [(ex - 6, 77), (ex - 6, y - 2)], 2.0, (110, 180, 236))


def drool(d, ph):
    y = MOUTH[1] + 4 + 4 * ph
    ellipse(d, MOUTH[0] + 7, y, 1.6, 2.2 + ph, TEAR)


def sunglasses(d, ph):
    shine = ph
    for cx in (EYE_L[0], EYE_R[0]):
        d.rounded_rectangle([p(cx - 13), p(60), p(cx + 13), p(78)], radius=p(7), fill=LED)
    d.rectangle([p(EYE_L[0] + 10), p(63), p(EYE_R[0] - 10), p(67)], fill=LED)
    for cx in (EYE_L[0], EYE_R[0]):
        d.rounded_rectangle([p(cx - 11), p(62), p(cx + 11), p(76)], radius=p(5.5),
                            fill=(18, 18, 26))
    for cx in (EYE_L[0], EYE_R[0]):
        x = cx - 10 + 20 * shine
        d.polygon(pts([(x, 62), (x + 4, 62), (x - 2, 76), (x - 6, 76)]), fill=(120, 130, 170))


def cheeks_big(d, ph):
    for cx in (30, 90):
        ellipse(d, cx, 83, 7, 4.5, (255, 110, 160))


# ---------------------------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------------------------


def ear_polygon(side, extra):
    if side == "L":
        base_a, tip, base_b = (15, 58), (19, 11), (54, 38)
    else:
        base_a, tip, base_b = (105, 58), (101, 11), (66, 38)
    pivot = ((base_a[0] + base_b[0]) / 2, (base_a[1] + base_b[1]) / 2)
    deg = -extra if side == "L" else extra
    return rotate_about([base_a, tip, base_b], pivot[0], pivot[1], deg)


def shrink(poly, k):
    cx = sum(x for x, _ in poly) / len(poly)
    cy = sum(y for _, y in poly) / len(poly)
    return [(cx + (x - cx) * k, cy + (y - cy) * k) for x, y in poly]


def draw_head(pose):
    layer = Image.new("RGBA", (W, W), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)

    # Ears: shell with an even, round-jointed outline, and a pink inner ear.
    for side, extra in (("L", pose.ears[0]), ("R", pose.ears[1])):
        poly = ear_polygon(side, extra)
        d.polygon(pts(poly), fill=SHELL)
        stroke(d, poly + [poly[0], poly[1]], 3.0, OUTLINE)
        inner = [(x, y + 3) for x, y in shrink(poly, 0.56)]
        d.polygon(pts(inner), fill=EAR_IN)
        stroke(d, inner + [inner[0], inner[1]], 1.6, EAR_IN)

    # Antenna.
    col, ant_glow = pose.antenna
    stroke(d, [(60, 36), (60, 22)], 3.0, OUTLINE)
    ellipse(d, 60, 18, 6.2, 6.2, OUTLINE)
    ellipse(d, 60, 18, 4.4, 4.4, col)
    ellipse(d, 58.6, 16.6, 1.4, 1.4, WHITE)

    # Head shell with a soft lower shade.
    x0, y0, x1, y1 = HEAD
    d.rounded_rectangle([p(x0), p(y0), p(x1), p(y1)], radius=p(HEAD_R), fill=OUTLINE)
    d.rounded_rectangle([p(x0 + 3), p(y0 + 3), p(x1 - 3), p(y1 - 3)], radius=p(HEAD_R - 3),
                        fill=SHELL_SHADE)
    d.rounded_rectangle([p(x0 + 3), p(y0 + 3), p(x1 - 3), p(y1 - 7)], radius=p(HEAD_R - 3),
                        fill=SHELL)

    # Whiskers on the shell.
    for sgn in (-1, 1):
        cx = 60 + sgn * 44
        stroke(d, [(cx - sgn * 3, 80), (cx + sgn * 9, 77)], 1.8, OUTLINE)
        stroke(d, [(cx - sgn * 3, 85), (cx + sgn * 9, 86)], 1.8, OUTLINE)

    # Visor: dark glass.
    vx0, vy0, vx1, vy1 = VISOR_BOX
    d.rounded_rectangle([p(vx0), p(vy0), p(vx1), p(vy1)], radius=p(VISOR_R), fill=VISOR)
    visor_mask = Image.new("L", (W, W), 0)
    ImageDraw.Draw(visor_mask).rounded_rectangle([p(vx0), p(vy0), p(vx1), p(vy1)],
                                                 radius=p(VISOR_R), fill=255)

    # Glass reflection.
    glass = Image.new("RGBA", (W, W), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glass)
    stroke(gd, arc_points(vx0 + 18, vy0 + 17, 12, 10, 190, 255, 12), 2.6, (255, 255, 255, 46))

    # LED layer: eyes, mouth, cheeks, with a glow.
    led = Image.new("RGBA", (W, W), (0, 0, 0, 0))
    ld = ImageDraw.Draw(led)
    lx, ly = pose.look
    draw_eye(ld, EYE_L[0] + lx, EYE_L[1] + ly, pose.eyes[0], "L")
    draw_eye(ld, EYE_R[0] + lx, EYE_R[1] + ly, pose.eyes[1], "R")
    draw_mouth(ld, pose.mouth)
    for fn in pose.visor_extras:
        fn(ld, pose.phase)

    cheeks = Image.new("RGBA", (W, W), (0, 0, 0, 0))
    if pose.blush > 0:
        cd = ImageDraw.Draw(cheeks)
        a = int(255 * pose.blush)
        for cx in (30.5, 89.5):
            ellipse(cd, cx, 84, 5.6, 3.4, PINK + (a,))
        cheeks = cheeks.filter(ImageFilter.GaussianBlur(p(0.8)))

    glow = led.filter(ImageFilter.GaussianBlur(p(2.2)))
    glow.putalpha(glow.getchannel("A").point(lambda v: int(v * 0.7)))
    content = Image.alpha_composite(glow, cheeks)
    content = Image.alpha_composite(content, led)
    content = Image.alpha_composite(content, glass)
    content.putalpha(ImageChops.multiply(content.getchannel("A"), visor_mask))
    layer = Image.alpha_composite(layer, content)

    # Antenna glow (outside the visor, kept small).
    if ant_glow > 0:
        halo = Image.new("RGBA", (W, W), (0, 0, 0, 0))
        ellipse(ImageDraw.Draw(halo), 60, 18, 7.5, 7.5, col + (int(150 * ant_glow),))
        halo = halo.filter(ImageFilter.GaussianBlur(p(2.0)))
        layer = Image.alpha_composite(halo, layer)

    if pose.tilt:
        layer = layer.rotate(pose.tilt, resample=Image.BICUBIC, center=(p(PIVOT[0]), p(PIVOT[1])))
    if pose.dx or pose.dy:
        moved = Image.new("RGBA", (W, W), (0, 0, 0, 0))
        moved.paste(layer, (int(round(p(pose.dx))), int(round(p(pose.dy)))))
        layer = moved
    return layer


def render(pose):
    """One 120x120 RGBA frame with a white sticker edge and a clean 1-bit alpha."""
    big = draw_head(pose)
    if pose.extras:
        top = Image.new("RGBA", (W, W), (0, 0, 0, 0))
        td = ImageDraw.Draw(top)
        for fn in pose.extras:
            fn(td, pose.phase)
        big = Image.alpha_composite(big, top)

    half = big.resize((SIZE * 2, SIZE * 2), Image.LANCZOS)
    edge = half.getchannel("A").point(lambda v: 255 if v > 40 else 0).filter(ImageFilter.MaxFilter(5))
    edge = edge.resize((SIZE, SIZE), Image.BOX)
    small = big.resize((SIZE, SIZE), Image.LANCZOS)
    sticker = Image.new("RGBA", (SIZE, SIZE), WHITE + (0,))
    sticker.putalpha(edge)
    frame = Image.alpha_composite(sticker, small)
    # Flatten partial alpha against white (the sticker edge is white) and make alpha 1-bit.
    alpha = frame.getchannel("A")
    flat = Image.alpha_composite(Image.new("RGBA", (SIZE, SIZE), WHITE + (255,)), frame)
    flat.putalpha(alpha.point(lambda v: 255 if v >= 110 else 0))
    return flat


# ---------------------------------------------------------------------------------------------
# Moods
# ---------------------------------------------------------------------------------------------


def blink_cycle(base, hold=2200, after=900, blink_eyes=None):
    """Hold, blink once, hold again: the looping blink every open-eyed face has."""
    frames = [(base, hold)]
    for t, ms in ((0.5, 40), (1.0, 70), (0.5, 40)):
        eyes = blink_eyes(t) if blink_eyes else (("blink", t), ("blink", t))
        frames.append((replace(base, eyes=eyes), ms))
    frames.append((base, after))
    return frames


def moods():
    m = {}
    base = Pose()

    # Idle: soft blink, an ear twitch now and then.
    m["neutral"] = blink_cycle(base, 2000, 700) + [
        (replace(base, ears=(0, 7)), 90), (replace(base, ears=(0, -3)), 90), (base, 900)]

    # Listening (board face): big eyes, ears up, sound waves, cyan antenna.
    lis = Pose(eyes=(("open", 1.12), ("open", 1.12)), mouth=("o", 2.6), ears=(-6, -6),
               antenna=(LED, 1.0), extras=[sound_waves])
    frames = []
    for i in range(8):
        ph = i / 8
        frames.append((replace(lis, phase=ph, dy=-0.6 * math.sin(2 * math.pi * ph)), 90))
    frames[3] = (replace(frames[3][0], eyes=(("blink", 1.0), ("blink", 1.0))), 90)
    m["listening"] = frames

    # Happy (the server's default reply emotion, so it doubles as the speaking face).
    hap = Pose(mouth=("smile", 7), blush=0.95)
    talk = [0.0, 0.7, 0.3, 1.0, 0.2, 0.8, 0.0, 0.5]
    m["happy"] = [(replace(hap, mouth=("talk", t), dy=-0.8 * t), 110) for t in talk] + \
        [(replace(hap, eyes=(("happy",), ("happy",))), 600), (hap, 500)]

    # Laughing / celebrate: ^^ eyes, open mouth, bounce, sparkles.
    lau = Pose(eyes=(("happy",), ("happy",)), mouth=("open", 9, 8), blush=1.0, antenna=(GOLD, 1.0),
               extras=[sparkles([(8, 30, 6), (110, 26, 7), (104, 92, 5), (14, 96, 5)])])
    m["laughing"] = [(replace(lau, phase=i / 8, dy=-2.5 * abs(math.sin(math.pi * i / 4))), 80)
                     for i in range(8)]

    # Funny: >< eyes, open mouth, shaking with laughter.
    fun = Pose(eyes=(("squeeze",), ("squeeze",)), mouth=("open", 8, 7), blush=1.0)
    m["funny"] = [(replace(fun, tilt=(-4 if i % 2 else 4), dy=-1 if i % 2 else 0), 90)
                  for i in range(8)]

    # Sad: lids slope down outward, frown, ears droop.
    sad = Pose(eyes=(("lid", -0.35), ("lid", -0.35)), look=(0, 2), mouth=("frown", 5), blush=0.4,
               ears=(14, 14), antenna=(DIM, 0.2))
    m["sad"] = blink_cycle(sad, 1800, 700,
                           blink_eyes=lambda t: (("blink", max(t, 0.35)), ("blink", max(t, 0.35))))

    # Angry (cute): lids slope down inward, puffed cheeks, vein mark, red antenna.
    ang = Pose(eyes=(("lid", 0.45), ("lid", 0.45)), mouth=("frown", 4), blush=0.0,
               visor_extras=[cheeks_big], antenna=(RED, 1.0), extras=[anger_mark])
    m["angry"] = [(replace(ang, phase=i / 6, dx=(0.8 if i % 2 else -0.8)), 110) for i in range(6)]

    # Crying: closed sad eyes with tears.
    cry = Pose(eyes=(("happy",), ("happy",)), mouth=("frown", 6), blush=0.6, ears=(16, 16),
               antenna=(DIM, 0.2), extras=[tears])
    cry = replace(cry, eyes=(("content",), ("content",)))
    m["crying"] = [(replace(cry, phase=i / 8, dy=0.6 * (i % 2)), 100) for i in range(8)]

    # Loving: heart eyes that pulse, floating hearts.
    lov = Pose(mouth=("w",), blush=1.0, extras=[floating_hearts], antenna=(HEART, 0.8))
    m["loving"] = [(replace(lov, phase=i / 10,
                            eyes=(("heart", 1.0 + 0.14 * math.sin(i / 10 * 4 * math.pi)),) * 2), 100)
                   for i in range(10)]

    # Embarrassed: eyes look aside, big blush, sweat drop.
    emb = Pose(eyes=(("happy",), ("happy",)), look=(3, 1), mouth=("wavy",), blush=1.0,
               visor_extras=[cheeks_big], extras=[sweat])
    m["embarrassed"] = [(replace(emb, phase=i / 6, tilt=3 * math.sin(i / 6 * 2 * math.pi)), 120)
                        for i in range(6)]

    # Surprised: round eyes, small o, ears up, a hop.
    sur = Pose(eyes=(("open", 1.15, 1.15),) * 2, mouth=("o", 3.4), ears=(-8, -8), blush=0.5)
    m["surprised"] = blink_cycle(replace(sur, dy=-2), 1300, 300) + [(sur, 400)]

    # Shocked: hollow ring eyes, big O, shaking.
    sho = Pose(eyes=(("ring", 10.5),) * 2, mouth=("o", 5.5), ears=(-10, -10), blush=0.0,
               antenna=(RED, 0.8))
    m["shocked"] = [(replace(sho, dx=[-1.5, 1.5, -1, 1, 0, 0][i]), 60 if i < 4 else 500)
                    for i in range(6)]

    # Thinking: eyes look up-right, flat mouth, dots, gold antenna blinking.
    thi = Pose(look=(3, -3), mouth=("flat", 4), blush=0.5, tilt=-4, dx=-3,
               extras=[thought_dots])
    m["thinking"] = []
    for i in range(8):
        ph = i / 8
        pose = replace(thi, phase=ph, antenna=(GOLD, 1.0 if i % 2 == 0 else 0.2))
        if i == 5:
            pose = replace(pose, eyes=(("blink", 1.0),) * 2)
        m["thinking"].append((pose, 70 if i == 5 else 220))

    # Winking: one eye ^, sparkle.
    win = Pose(eyes=(("open",), ("happy",)), mouth=("smile", 7), blush=0.95,
               extras=[sparkles([(106, 40, 6)])])
    m["winking"] = [(replace(win, phase=i / 6, tilt=-3 if i < 3 else -1), 160) for i in range(6)]

    # Cool: sunglasses with a moving shine, smirk.
    coo = Pose(eyes=(("open",),) * 2, mouth=("smirk",), blush=0.3, visor_extras=[sunglasses],
               tilt=-3)
    m["cool"] = [(replace(coo, phase=i / 7), 110 if i < 7 else 900) for i in range(8)]

    # Relaxed: closed content eyes, gentle breathing.
    rel = Pose(eyes=(("content",),) * 2, mouth=("smile", 5), blush=0.8)
    m["relaxed"] = [(replace(rel, dy=1.2 * math.sin(i / 8 * 2 * math.pi)), 160) for i in range(8)]

    # Delicious: ^^ eyes, tongue, drool.
    dee = Pose(eyes=(("happy",),) * 2, mouth=("tongue", 2), blush=1.0, visor_extras=[drool])
    m["delicious"] = [(replace(dee, phase=i / 6, dy=-0.8 * (i % 2)), 130) for i in range(6)]

    # Kissy: wink plus a pucker, floating hearts.
    kis = Pose(eyes=(("open",), ("happy",)), mouth=("kiss",), blush=1.0, extras=[floating_hearts])
    m["kissy"] = [(replace(kis, phase=i / 8), 110) for i in range(8)]

    # Confident: half-lidded eyes, smirk, a little nod.
    con = Pose(eyes=(("half", -2),) * 2, mouth=("smirk",), blush=0.4, tilt=4)
    m["confident"] = blink_cycle(con, 1500, 500,
                                 blink_eyes=lambda t: (("half", -2 + 9 * t),) * 2) + \
        [(replace(con, dy=1.2), 160), (con, 300)]

    # Sleepy: closed eyes, Zzz, slow sway, dim antenna.
    sle = Pose(eyes=(("content",),) * 2, mouth=("o", 2.2), blush=0.6, ears=(8, 8),
               antenna=(DIM, 0.1), extras=[zzz])
    m["sleepy"] = [(replace(sle, phase=i / 10, tilt=3 * math.sin(i / 10 * 2 * math.pi),
                            dy=1 + math.sin(i / 10 * 2 * math.pi)), 150) for i in range(10)]

    # Silly: mismatched eyes, tongue to the side, wobble.
    sil = Pose(eyes=(("open", 1.15), ("open", 0.7)), mouth=("tongue", 4), blush=0.9)
    m["silly"] = [(replace(sil, tilt=7 * math.sin(i / 8 * 2 * math.pi), phase=i / 8), 110)
                  for i in range(8)]
    m["silly"][5] = (replace(m["silly"][5][0], eyes=(("blink", 1.0), ("open", 0.7))), 110)

    # Confused ("I can't see"): one squinting eye, wavy mouth, head tilt, bobbing "?".
    cnf = Pose(eyes=(("open", 1.1), ("half", 1)), mouth=("wavy",), blush=0.4, tilt=8,
               ears=(4, -6), extras=[question], antenna=(GOLD, 0.6))
    m["confused"] = []
    for i in range(10):
        pose = replace(cnf, phase=i / 10, tilt=8 + 2 * math.sin(i / 10 * 2 * math.pi))
        if i == 6:
            pose = replace(pose, eyes=(("blink", 1.0), ("half", 1)))
        m["confused"].append((pose, 70 if i == 6 else 150))

    return m


# ---------------------------------------------------------------------------------------------
# GIF writing and the contact sheet
# ---------------------------------------------------------------------------------------------


def write_gif(path, frames):
    rgba = [render(pose) for pose, _ in frames]
    durations = [ms for _, ms in frames]
    # One palette for all frames (255 colours); index 255 is transparent.
    mosaic = Image.new("RGB", (SIZE * len(rgba), SIZE), WHITE)
    for i, im in enumerate(rgba):
        mosaic.paste(im.convert("RGB"), (i * SIZE, 0), im.getchannel("A"))
    pal_img = mosaic.quantize(colors=255, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    palette = pal_img.getpalette()[: 255 * 3]
    palette += [255, 0, 255] * (256 - len(palette) // 3)
    pal_img.putpalette(palette)
    out = []
    for im in rgba:
        q = im.convert("RGB").quantize(palette=pal_img, dither=Image.Dither.NONE)
        mask = im.getchannel("A").point(lambda v: 255 if v == 0 else 0)
        q.paste(255, mask=mask)
        q.info["transparency"] = 255
        out.append(q)
    out[0].save(path, save_all=True, append_images=out[1:], duration=durations, loop=0,
                disposal=2, transparency=255, optimize=False, background=255)
    return rgba


def key_frame(frames):
    """The longest-held frame: the face a child sees most."""
    longest = max(ms for _, ms in frames)
    return max(i for i, (_, ms) in enumerate(frames) if ms == longest)


def contact_sheet(path, all_frames, dark=False):
    tile_w, tile_h, cols = 240, 280, 6
    names = list(all_frames)
    rows = math.ceil(len(names) / cols)
    label_h = 22
    sheet = Image.new("RGB", (cols * (tile_w + 8) + 8, rows * (tile_h + label_h + 8) + 8),
                      (90, 90, 96))
    font = ImageFont.load_default(14)
    small = ImageFont.load_default(12)
    for n, name in enumerate(names):
        frames = all_frames[name]
        img = render(frames[key_frame(frames)][0])
        x = 8 + (n % cols) * (tile_w + 8)
        y = 8 + (n // cols) * (tile_h + label_h + 8)
        bg = (0, 0, 0) if dark else (255, 255, 255)
        fg = (255, 255, 255) if dark else (0, 0, 0)
        screen = Image.new("RGB", (tile_w, tile_h), bg)
        sd = ImageDraw.Draw(screen)
        # Mock of the default LcdDisplay layout: status text on top, chat line at the bottom.
        status = {"listening": "Listening...", "thinking": "Speaking...", "neutral": "Standby"}
        sd.text((tile_w // 2, 12), status.get(name, "Speaking..."), fill=fg, font=small, anchor="mm")
        screen.paste(img, ((tile_w - SIZE) // 2, (tile_h - SIZE) // 2), img.getchannel("A"))
        sd.text((tile_w // 2, tile_h - 14), "Hi! I'm Kitty.", fill=fg, font=small, anchor="mm")
        sheet.paste(screen, (x, y))
        ImageDraw.Draw(sheet).text((x + tile_w // 2, y + tile_h + 11), name, fill=(255, 255, 255),
                                   font=font, anchor="mm")
    sheet.save(path)


def main():
    global SIZE, W
    here = Path(__file__).resolve().parent
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=here.parent / "kitty-gif")
    ap.add_argument("--sheet", type=Path, help="write a 240x280 contact sheet PNG here")
    ap.add_argument("--dark-sheet", type=Path, help="the same sheet on the dark theme")
    ap.add_argument("--only", nargs="*", help="render only these moods")
    ap.add_argument("--size", type=int, default=SIZE, help="GIF size in px (default 200)")
    args = ap.parse_args()
    SIZE, W = args.size, args.size * S

    all_frames = moods()
    if args.only:
        all_frames = {k: v for k, v in all_frames.items() if k in args.only}
    args.out.mkdir(parents=True, exist_ok=True)
    total = 0
    for name, frames in all_frames.items():
        path = args.out / f"{name}.gif"
        write_gif(path, frames)
        total += path.stat().st_size
        print(f"{name:12s} {len(frames):2d} frames {sum(ms for _, ms in frames):5d} ms "
              f"{path.stat().st_size:6d} bytes")
    print(f"total {total} bytes in {len(all_frames)} GIFs")
    if args.sheet:
        contact_sheet(args.sheet, all_frames)
    if args.dark_sheet:
        contact_sheet(args.dark_sheet, all_frames, dark=True)


if __name__ == "__main__":
    main()
