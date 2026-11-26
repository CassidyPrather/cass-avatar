"""The bot itself: where its bones are, what its parts look like and how they are painted.

All positions are in pixels (bot_geo.PX metres each), Blender axes: +Z up, the bot faces -Y and
its left side is +X. The left limbs are modelled and the right ones mirrored from them, sharing
their texels. Every part follows one bone rigidly, like a toy with ball joints; only the hologram
ears and tail bend.

Plain Python on top of bot_geo; nothing here needs bpy.
"""

import math

import numpy as np

import bot_face
from bot_geo import PX, frame, ngon, place, rrect, swatch, unit, vec

X, Y, Z = vec(1, 0, 0), vec(0, 1, 0), vec(0, 0, 1)
FRONT = vec(0, -1, 0)

# --- measurements the face contract needs -----------------------------------------------------

HEAD_HALF_WIDTH, HEAD_CHAMFER = 26.0, 2.0
HEAD_Z0, HEAD_Z1 = 148.0, 192.0
HEAD_FRONT, HEAD_BACK = -20.0, 18.0
SCREEN_HALF_WIDTH = bot_face.SCREEN_W / 2.0
SCREEN_Z0 = 158.0
SCREEN_Z1 = SCREEN_Z0 + bot_face.SCREEN_H
EYES_Z0 = SCREEN_Z1 - bot_face.EYES_H
# How far the backing plate sits behind the front of the head: room for every sprite to stand in front of it.
RECESS = 2.25
PLATE_Y = HEAD_FRONT + RECESS

EAR_BASE, EAR_TIP = vec(10.0, 2.0, 196.0), vec(15.5, 4.0, 238.0)
EAR_SECTIONS = ((0.0, 2.2, 1.2), (0.12, 4.6, 2.2), (0.5, 6.6, 2.8), (0.82, 5.2, 2.2), (1.0, 1.6, 0.8))  # (along, half width, half depth)
EAR_ISLAND = (14, 42)
TAIL_CENTRE, TAIL_RADIUS, TAIL_ISLAND = vec(0.0, 22.0, 93.0), 7.0, 16

FINGERS = {  # name -> (y of the knuckle, segment lengths)
    "Index": (-4.65, (4.5, 3.5, 3.0)),
    "Middle": (-1.55, (5.0, 3.5, 3.0)),
    "Ring": (1.55, (4.5, 3.5, 3.0)),
    "Little": (4.65, (3.5, 3.0, 2.5)),
}
FINGER_X, FINGER_Z = 88.5, 131.0
THUMB_ROOT, THUMB_DIRECTION, THUMB_LENGTHS = vec(81.5, -6.5, 130.5), unit(vec(0.55, -0.8, -0.22)), (4.5, 3.5, 3.0)


def sides(function):
    function.per_side = True
    return function


# --- bones --------------------------------------------------------------------------------------


def bones():
    """[(name, head, tail, roll axis)] in pixels for the left side and the middle; `.R` bones are mirrored by the build."""
    table = [
        ("Hips", (0, 0, 88), (0, 0, 96), FRONT),
        ("Spine", (0, 0, 96), (0, 0, 103), FRONT),
        ("Chest", (0, 0, 103), (0, 0, 137), FRONT),
        ("Neck", (0, 0, 137), (0, 0, 146), FRONT),
        ("Head", (0, 0, 146), (0, 0, 192), FRONT),
        # Behind the eyes of the neutral face, pointing up with Z forward like the cass eye bones. Nothing is weighted to them.
        ("Eye.L", (8, -14, 178), (8, -14, 182), FRONT),
        ("Shoulder.L", (4, 0, 131), (25.5, 0, 131), Z),
        ("UpperArm.L", (25.5, 0, 131), (52.5, 0.5, 131), Z),
        ("LowerArm.L", (52.5, 0.5, 131), (78.5, 0, 131), Z),
        ("Hand.L", (78.5, 0, 131), (88.5, 0, 131), Z),
        ("UpperLeg.L", (12, 0, 84), (12, -0.6, 48), FRONT),
        ("LowerLeg.L", (12, -0.6, 48), (12, 1, 9.5), FRONT),
        ("Foot.L", (12, 1, 9.5), (12, -10, 2.5), Z),
        ("Toes.L", (12, -10, 2.5), (12, -21, 2.5), Z),
    ]
    for finger, (y, lengths) in FINGERS.items():
        x = FINGER_X
        for number, length in enumerate(lengths, start=1):
            table.append((f"{finger}{number}.L", (x, y, FINGER_Z), (x + length, y, FINGER_Z), Z))
            x += length
    point = THUMB_ROOT
    for number, length in enumerate(THUMB_LENGTHS, start=1):
        table.append((f"Thumb{number}.L", tuple(point), tuple(point + THUMB_DIRECTION * length), Z))
        point = point + THUMB_DIRECTION * length
    middle = EAR_BASE + (EAR_TIP - EAR_BASE) * 0.5
    table += [
        ("Ear.L", (EAR_BASE[0], EAR_BASE[1], HEAD_Z1 + 1.5), tuple(middle), FRONT),
        ("Ear.L.001", tuple(middle), tuple(EAR_TIP), FRONT),
        ("Tail", (0, 13, 91), (0, 19.5, 92.5), Z),
        ("Tail.001", (0, 19.5, 92.5), (0, 29, 94.5), Z),
    ]
    return table


# --- paints -------------------------------------------------------------------------------------


def ribs(c):
    """The dark bellows of a joint."""
    c.fill("ink")
    for y in range(0, c.h, 3):
        c.hline(y, "grey-dark")


def joint(c):
    c.fill("ink")
    c.rect(0, c.h // 2 - 1, c.w, c.h // 2 + 1, "grey-dark")
    for x in range(1, c.w, 3):
        c.px(x, c.h // 2 - 2, "night-3")


def pauldron(c):
    """A shoulder cap: the pale shell with a band round it."""
    c.fill("paper")
    c.rect(0, c.h // 2 - 1, c.w, c.h // 2 + 1, "lavender")
    c.hline(c.h // 2 - 2, "lilac-0")
    c.hline(c.h // 2 + 1, "lilac-0")
    c.rect(0, c.h - 3, c.w, c.h, "lilac-4")


def rivets(c, colour="lilac-0", inset=1):
    for x, y in ((inset, inset), (c.w - 1 - inset, inset), (inset, c.h - 1 - inset), (c.w - 1 - inset, c.h - 1 - inset)):
        c.px(x, y, colour)


def head_front(c):
    c.fill("paper")
    c.rect(0, 0, c.w, 2, "lavender")
    c.hline(c.h - 1, "lilac-4")
    # The bezel round the opening for the screen (columns 4..44, rows 4..32).
    c.frame(1, 1, 47, 35, "lilac-0")
    c.rect(2, 2, 46, 34, "ink")
    c.frame(3, 3, 45, 33, "night-1")
    # The chin: a speaker grille between two pairs of lamps.
    c.dots(17, 36, 32, 39, "lilac-0", 2)
    c.rect(5, 36, 7, 38, "banana", glow=True)
    c.rect(8, 36, 10, 38, "cyan", glow=True)
    c.rect(38, 36, 43, 38, "lilac-4")
    c.rect(39, 36, 42, 38, "orange")


def head_side(c):
    """The left of the picture is the front of the head."""
    c.fill("paper")
    for x in range(c.w):
        depth = 2 + round(11 * x / (c.w - 1))
        c.rect(x, 0, x + 1, depth, "lavender")
        c.px(x, depth, "lilac-1")
        # The colour breaks up below its edge, a dither rather than a line.
        c.dither(x, depth + 1, x + 1, depth + 3, "lavender", 0.5)
        c.dither(x, depth + 3, x + 1, depth + 5, "lavender", 0.25)
    c.hline(c.h - 1, "lilac-4")
    c.vline(0, "white", 2, c.h - 1)
    # A seat for the ear cup, and a seam below it.
    c.ring(17.0, 20.0, 10.2, 9.0, "lilac-0")
    c.hline(33, "lilac-4", 3, c.w - 3)
    c.dots(4, 35, 13, 38, "lilac-0", 2)
    c.px(c.w - 3, 36, "lilac-0")
    c.px(c.w - 3, 30, "lilac-0")


def head_top(c):
    """The top of the picture is the back of the head."""
    c.fill("lavender")
    c.frame(1, 1, c.w - 1, c.h - 1, "lilac-1")
    # A checkered stripe from front to back, and a seat round each emitter.
    c.checker(c.w // 2 - 3, 0, c.w // 2 + 3, c.h, "ink", "paper", 2)
    c.vline(c.w // 2 - 4, "lilac-1")
    c.vline(c.w // 2 + 3, "lilac-1")
    for cx in (c.w / 2.0 - 10.0, c.w / 2.0 + 10.0):
        c.ring(cx, 14.0, 5.4, 4.2, "lilac-1")
    rivets(c, "pink", 3)


def head_back(c):
    c.fill("paper")
    c.rect(0, 0, c.w, 13, "lavender")
    c.hline(13, "lilac-1")
    c.dither(0, 14, c.w, 16, "lavender", 0.5)
    c.dither(0, 16, c.w, 18, "lavender", 0.25)
    c.hline(c.h - 1, "lilac-4")
    # A vent of dots, a plate with the model number, and a tag.
    c.rect(11, 17, 37, 30, "ink")
    c.rect(12, 18, 36, 29, "grey-dark")
    c.dots(13, 19, 36, 29, "lilac-0", 2)
    c.text(11, 33, "WN-01", "lilac-0")
    c.rect(35, 33, 37, 38, "orange")
    c.checker(4, 4, 44, 8, "lilac-1", "lavender", 2)
    rivets(c, "lilac-0", 2)


def ear_cup(c):
    """Target rings."""
    cx, cy = c.w / 2.0, c.h / 2.0
    c.fill("ink")
    c.disc(cx, cy, 6.2, "paper")
    c.ring(cx, cy, 4.6, 2.9, "orange")
    c.disc(cx, cy, 1.3, "ink")


def emitter(c):
    c.fill("ink")
    c.disc(c.w / 2.0, c.h / 2.0, 2.4, "cyan", glow=True)
    c.disc(c.w / 2.0, c.h / 2.0, 1.0, "ice", glow=True)


def chest_front(c):
    c.fill("paper")
    c.fade(0, c.h - 8, c.w, c.h, "lilac-4", 0.0, 0.8)
    c.hline(c.h - 1, "lilac-4")
    c.hline(0, "white")
    x0 = (c.w - 23) // 2
    # A small display with the three primitives lit on it.
    c.rect(x0, 4, x0 + 23, 15, "ink")
    c.rect(x0 + 1, 5, x0 + 22, 14, "night-0")
    legend = {"C": "cyan", "O": "orange", "M": "magenta"}
    c.art(x0 + 3, 7, (".CCC.", "C...C", "C...C", "C...C", ".CCC."), legend, glow="C")
    c.art(x0 + 9, 7, ("..O..", "..O..", ".O.O.", ".O.O.", "OOOOO"), legend, glow="O")
    c.art(x0 + 15, 7, ("MMMMM", "M...M", "M...M", "M...M", "MMMMM"), legend, glow="M")
    # Vent slots and a lamp.
    for y in (18, 20, 22):
        c.hline(y, "lilac-0", x0 + 3, x0 + 14)
    c.rect(x0 + 17, 19, x0 + 20, 22, "lilac-0")
    c.rect(x0 + 18, 20, x0 + 19, 21, "banana", glow=True)
    c.px(x0, 25, "lilac-0")
    c.px(x0 + 22, 25, "lilac-0")


def chest_side(c):
    c.fill("paper")
    c.fade(0, c.h - 8, c.w, c.h, "lilac-4", 0.0, 0.8)
    c.hline(c.h - 1, "lilac-4")
    c.frame(2, c.h - 12, c.w - 2, c.h - 3, "lilac-4")
    c.dots(4, c.h - 10, c.w - 3, c.h - 4, "lilac-0", 2)


def chest_back(c):
    c.fill("paper")
    c.fade(0, c.h - 8, c.w, c.h, "lilac-4", 0.0, 0.8)
    c.hline(c.h - 1, "lilac-4")
    c.frame(2, 2, c.w - 2, c.h - 2, "lilac-4")
    rivets(c, "lilac-0", 3)


def collar(c):
    c.fill("lavender")
    c.hline(c.h - 1, "lilac-1")
    c.hline(0, "pink")


def pack_back(c):
    c.fill("lavender")
    c.frame(0, 0, c.w, c.h, "lilac-1")
    c.rect(3, 3, c.w - 3, 11, "ink")
    c.dots(4, 4, c.w - 4, 10, "lilac-0", 2)
    c.rect(3, c.h - 5, c.w - 3, c.h - 3, "orange")


def belt(buckle):
    def paint(c):
        c.fill("lavender")
        c.rect(0, 0, c.w, 2, "ink")
        c.hline(2, "lilac-1")
        c.hline(c.h - 1, "lilac-1")
        if buckle:
            c.rect(c.w // 2 - 3, 0, c.w // 2 + 3, 3, "orange")
            c.rect(c.w // 2 - 1, 1, c.w // 2 + 1, 2, "banana")
            # Contour lines, like a map of a small hill.
            for inset, y in ((6, 5), (8, 7)):
                c.hline(y, "lilac-1", inset, c.w - inset)
    return paint


def thigh(c):
    c.fill("paper")
    c.fade(0, 5, c.w, 14, "lavender", 0.9, 0.0)
    c.rect(0, 2, c.w, 5, "lavender")
    c.hline(1, "lilac-0")
    c.hline(c.h - 1, "lilac-0")
    c.hline(c.h - 2, "lilac-4")


def shin(front):
    def paint(c):
        c.fill("lavender")
        c.fade(0, c.h - 16, c.w, c.h - 7, "lilac-1", 0.0, 0.7)
        c.hline(0, "lilac-1")
        c.checker(0, c.h - 6, c.w, c.h - 2, "ink", "paper", 2)
        c.hline(c.h - 7, "lilac-1")
        c.hline(c.h - 2, "lilac-1")
        c.hline(c.h - 1, "lilac-1")
        if front:
            c.rect(1, 3, c.w - 1, 14, "paper")
            c.frame(1, 3, c.w - 1, 14, "lilac-0")
            c.px(c.w // 2, 5, "orange")
    return paint


def rim(c):
    """The band round the mouth of a boot or a gauntlet."""
    c.fill("paper")
    c.hline(c.h - 1, "lilac-0")
    c.hline(0, "orange")


def sole(c):
    c.fill("ink")
    for x in range(1, c.w, 3):
        c.vline(x, "grey-dark")
    for y in range(1, c.h, 3):
        c.hline(y, "grey-dark")


def foot_side(c):
    c.fill("paper")
    c.hline(c.h - 1, "lilac-0")
    c.hline(c.h - 2, "lilac-4")


def toe(c):
    c.fill("lavender")
    c.hline(c.h - 1, "lilac-1")
    c.hline(0, "lilac-1")


def upper_arm(under):
    def paint(c):
        c.fill("lilac-4" if under else "paper")
        c.fade(0, c.h - 13, c.w, c.h - 5, "lilac-1" if under else "lavender", 0.0, 0.9)
        c.rect(0, c.h - 5, c.w, c.h - 2, "lilac-1" if under else "lavender")
        c.hline(c.h - 1, "lilac-0")
        c.hline(0, "lilac-0")
    return paint


def gauntlet(under):
    def paint(c):
        c.fill("lilac-1" if under else "lavender")
        c.checker(0, 1, c.w, 5, "ink", "lilac-4" if under else "paper", 2)
        c.hline(0, "lilac-1")
        c.hline(5, "lilac-1")
        c.hline(c.h - 1, "lilac-1")
    return paint


def hand_back(c):
    c.fill("paper")
    c.frame(2, 2, c.w - 2, c.h - 2, "lilac-0")
    c.rect(3, 3, c.w - 3, c.h - 3, "lavender")
    c.px(c.w // 2, c.h // 2, "orange")


def hand_palm(c):
    c.fill("lilac-4")
    c.dots(1, 1, c.w - 1, c.h - 1, "lilac-1", 2)


def finger(tip, under):
    def paint(c):
        if tip:
            c.fill("lilac-1" if under else "lavender")
        else:
            c.fill("lilac-4" if under else "paper")
        c.hline(c.h - 1, "lilac-1" if tip else "lilac-0")
    return paint


def hologram(half_width, taper):
    """Scanlines inside an outline. `half_width(t)` is the outline at t along the picture from bottom (0) to top (1)."""
    def paint(c):
        c.fill("black")
        for y in range(c.h):
            t = 1.0 - (y + 0.5) / c.h
            w = half_width(t)
            for x in range(c.w):
                a = abs(x + 0.5 - c.w / 2.0)
                if w <= 0.0 or a > w + 0.5:
                    continue
                if a > w - 1.3 or (taper and (t > 0.97 or t < 0.02)):
                    c.px(x, y, "ice", True)
                elif a < w * 0.45 and 0.12 < t < 0.86:
                    c.px(x, y, "magenta" if y % 2 == 0 else "violet", True)
                    if (x + y // 2) % 2 == 0 and y % 2 == 0:
                        c.px(x, y, "pink", True)
                elif y % 2 == 0:
                    c.px(x, y, "cyan", True)
                else:
                    c.px(x, y, "night-2", True)
                    if (x + y // 2) % 4 == 0:
                        c.px(x, y, "blue", True)
    return paint


def ear_half_width(t):
    for (t0, w0, _d0), (t1, w1, _d1) in zip(EAR_SECTIONS, EAR_SECTIONS[1:]):
        if t <= t1:
            return w0 + (w1 - w0) * (t - t0) / (t1 - t0)
    return EAR_SECTIONS[-1][1]


def tail_half_width(t):
    r = TAIL_RADIUS
    return math.sqrt(max(0.0, r * r - ((t - 0.5) * TAIL_ISLAND) ** 2))


def picture(rows):
    """A sprite's paint: the characters of bot_face, lit everywhere but on the background."""
    def paint(c):
        c.fill(bot_face.BACKGROUND)
        glowing = "".join(ch for ch in bot_face.LEGEND if ch != ".")
        c.art(0, 0, rows, bot_face.LEGEND, glow=glowing)
    return paint


# --- parts --------------------------------------------------------------------------------------


def build_head(b):
    a, c = HEAD_HALF_WIDTH, HEAD_CHAMFER
    zc, hh = (HEAD_Z0 + HEAD_Z1) / 2.0, (HEAD_Z1 - HEAD_Z0) / 2.0
    ea, eb = frame(-Y, -Z)

    def ring(y, inset):
        return place(rrect(a - inset, hh - inset, c), (0.0, y, zc), ea, eb)

    rings = [ring(HEAD_BACK, c), ring(HEAD_BACK - c, 0.0), ring(HEAD_FRONT + c, 0.0), ring(HEAD_FRONT, c)]

    @sides
    def wall(k, i):
        if k == 1 and i in (2, 6):
            return head_side, "side"
        if k == 1 and i == 4:
            return head_top
        if i in (3, 4, 5):
            return swatch("lavender")
        if i in (0, 1, 7):
            return swatch("lilac-4")
        return swatch("paper")

    def up(k, i):
        if k == 1 and i in (2, 6):
            return Z
        if k == 1 and i == 4:
            return Y
        return None

    with b.solid("head", bone="Head"):
        b.loft(rings, wall, cap0=head_back, up0=Z, up=up, key="head")
        o = rings[3]
        sw, z0, z1 = SCREEN_HALF_WIDTH, SCREEN_Z0, SCREEN_Z1
        i = [vec(-sw, HEAD_FRONT, z0), vec(sw, HEAD_FRONT, z0), vec(sw, HEAD_FRONT, z1), vec(-sw, HEAD_FRONT, z1)]
        p = [q + Y * RECESS for q in i]
        b.planar([[o[0], o[1], i[1], i[0]], [o[1], o[2], i[1]], [o[2], o[3], i[2], i[1]], [o[3], o[4], i[2]],
                  [o[4], o[5], i[3], i[2]], [o[5], o[6], i[3]], [o[6], o[7], i[0], i[3]], [o[7], o[0], i[0]]],
                 Z, head_front, "head/front")
        dark = swatch("night-1")
        b.poly([i[0], i[1], p[1], p[0]], Y, dark)
        b.poly([i[1], i[2], p[2], p[1]], Y, dark)
        b.poly([i[2], i[3], p[3], p[2]], Y, dark)
        b.poly([i[3], i[0], p[0], p[3]], Y, dark)
        b.poly(p, Z, swatch(bot_face.BACKGROUND))

    def cups_and_emitters():
        ea, eb = frame(X, FRONT)
        with b.solid("earcup", bone="Head"):
            outline = ngon(8, 7.5)
            b.loft([place(outline, (a - 0.5, -1.0, 170.0), ea, eb), place(outline, (a + 3.0, -1.0, 170.0), ea, eb)],
                   swatch("grey-dark"), cap0=swatch("ink"), cap1=ear_cup, up1=Z, key="earcup")
        ea, eb = frame(Z, FRONT)
        with b.solid("emitter", bone="Head"):
            outline = ngon(6, 3.5)
            b.loft([place(outline, (EAR_BASE[0], EAR_BASE[1], HEAD_Z1 - 0.5), ea, eb), place(outline, (EAR_BASE[0], EAR_BASE[1], HEAD_Z1 + 1.5), ea, eb)],
                   swatch("ink"), cap0=swatch("ink"), cap1=emitter, up1=Y, key="emitter")

    cups_and_emitters()
    with b.mirrored():
        cups_and_emitters()


def build_torso(b):
    ea, eb = frame(Z, FRONT)
    with b.solid("neck", bone="Neck"):
        outline = ngon(8, 6.0)
        b.loft([place(outline, (0, 0, 135.0), ea, eb), place(outline, (0, 0, 150.0), ea, eb)], (ribs, "ribs"),
               cap0=swatch("ink"), cap1=swatch("ink"), key="neck")

    with b.solid("chest", bone="Chest"):
        rings = [place(rrect(12.0, 9.0, 2.5), (0, 0, 100.0), ea, eb), place(rrect(15.0, 12.0, 3.0, cy=-0.5), (0, 0, 104.0), ea, eb),
                 place(rrect(19.5, 13.5, 3.0, cy=-0.5), (0, 0, 132.0), ea, eb), place(rrect(15.0, 9.5, 2.5), (0, 0, 139.0), ea, eb)]

        @sides
        def wall(k, i):
            if k == 0:
                return swatch("lilac-0")
            if k == 2:
                return (collar, "collar") if i in (0, 4) else swatch("lavender")
            if i == 0:
                return chest_front
            if i == 4:
                return chest_back
            if i in (2, 6):
                return chest_side, "side"
            return swatch("lilac-4")

        b.loft(rings, wall, cap0=swatch("lilac-0"), cap1=swatch("lavender"), key="chest")

    with b.solid("pack", bone="Chest"):
        pa, pb = frame(Y, -Z)
        rings = [place(rrect(9.0, 10.0, 2.0), (0, 11.0, 119.0), pa, pb), place(rrect(9.0, 10.0, 2.0), (0, 17.5, 119.0), pa, pb),
                 place(rrect(7.5, 8.5, 2.0), (0, 19.0, 119.0), pa, pb)]

        @sides
        def wall(k, i):
            if i in (0, 1, 7) or k == 1:
                return swatch("lilac-1")
            return swatch("lavender")

        b.loft(rings, wall, cap0=swatch("lilac-1"), cap1=pack_back, up1=Z, key="pack")

    with b.solid("waist", bone="Spine"):
        outline = ngon(8, 9.5)
        b.loft([place(outline, (0, 0, 93.0), ea, eb), place(outline, (0, 0, 103.0), ea, eb)], (ribs, "ribs"),
               cap0=swatch("ink"), cap1=swatch("ink"), key="waist")

    with b.solid("pelvis", bone="Hips"):
        rings = [place(rrect(10.0, 7.5, 2.5), (0, 0, 78.0), ea, eb), place(rrect(16.5, 11.0, 3.0), (0, 0, 84.0), ea, eb),
                 place(rrect(17.5, 11.5, 3.0), (0, 0, 93.0), ea, eb), place(rrect(13.0, 8.5, 2.5), (0, 0, 96.5), ea, eb)]

        @sides
        def wall(k, i):
            if k == 0:
                return swatch("lilac-1")
            if k == 2:
                return swatch("ink")
            if i == 0:
                return belt(True)
            if i in (2, 4, 6):
                return belt(False), ("belt-back" if i == 4 else "belt-side")
            return belt(False), "belt-corner"

        b.loft(rings, wall, cap0=swatch("lilac-1"), cap1=swatch("ink"), key="pelvis")

    with b.solid("tail-emitter", bone="Hips"):
        ta, tb = frame(Y, -Z)
        outline = ngon(6, 3.0)
        b.loft([place(outline, (0, 10.5, 91.0), ta, tb), place(outline, (0, 13.0, 91.0), ta, tb)], swatch("ink"),
               cap0=swatch("ink"), cap1=emitter, up1=Z, key="tail-emitter")


def build_leg(b):
    ea, eb = frame(Z, FRONT)
    with b.solid("hip", bone="Hips"):
        b.ball((12.0, 0.0, 84.0), 7.5, joint, "joint", axis=X, front=FRONT)
    with b.solid("thigh", bone="UpperLeg.L"):
        b.loft([place(ngon(8, 6.2), (12.0, -0.4, 52.0), ea, eb), place(ngon(8, 7.0), (12.0, 0.0, 79.5), ea, eb)], (thigh, "wall"),
               cap0=swatch("ink"), cap1=swatch("ink"), key="thigh")
    with b.solid("knee", bone="UpperLeg.L"):
        b.ball((12.0, -0.6, 48.0), 6.6, joint, "joint", axis=X, front=FRONT)
    with b.solid("shin", bone="LowerLeg.L"):
        @sides
        def wall(k, i):
            if k == 0:
                return rim, "rim"
            return (shin(True), "front") if i == 0 else (shin(False), "side")

        b.loft([place(ngon(8, 10.0), (12.0, 0.8, 12.0), ea, eb), place(ngon(8, 10.0), (12.0, 0.8, 16.0), ea, eb),
                place(ngon(8, 6.2), (12.0, -0.4, 44.5), ea, eb)], wall, cap0=swatch("ink"), cap1=swatch("ink"), key="shin")
    with b.solid("ankle", bone="LowerLeg.L"):
        b.ball((12.0, 1.0, 9.5), 5.0, joint, "joint", axis=X, front=FRONT)

    fa, fb = frame(-Y, -Z)
    with b.solid("foot", bone="Foot.L"):
        @sides
        def wall(k, i):
            if i in (0, 1, 7):
                return (sole, "sole") if (k == 1 and i == 0) else swatch("ink")
            if k == 0:
                return swatch("lilac-4")
            return (foot_side, "side") if i in (2, 6) else swatch("paper")

        b.loft([place(rrect(6.5, 3.25, 1.5, cx=12.0, cy=3.25), (0, 11.0, 0), fa, fb), place(rrect(8.5, 4.5, 1.5, cx=12.0, cy=4.5), (0, 9.0, 0), fa, fb),
                place(rrect(8.5, 4.5, 1.5, cx=12.0, cy=4.5), (0, -10.0, 0), fa, fb)], wall, cap0=swatch("lilac-4"), cap1=swatch("ink"),
               up=lambda k, i: Z if i in (2, 6) else None, key="foot")
    with b.solid("toes", bone="Toes.L"):
        @sides
        def wall(k, i):
            if i in (0, 1, 7):
                return (sole, "sole") if (k == 0 and i == 0) else swatch("ink")
            if k == 1:
                return swatch("lilac-1")
            return (toe, "top") if i == 4 else (toe, "side") if i in (2, 6) else swatch("lavender")

        b.loft([place(rrect(8.5, 4.5, 1.5, cx=12.0, cy=4.5), (0, -10.0, 0), fa, fb), place(rrect(8.5, 4.0, 1.5, cx=12.0, cy=4.0), (0, -18.0, 0), fa, fb),
                place(rrect(6.5, 2.75, 1.5, cx=12.0, cy=2.75), (0, -21.5, 0), fa, fb)], wall, cap0=swatch("ink"), cap1=swatch("lilac-1"),
               up=lambda k, i: Z if i in (2, 6) else None, key="toes")


def build_arm(b):
    ea, eb = frame(X, FRONT)  # ea is down, eb is back: sides 1..3 of a tube face the ground
    with b.solid("shoulder-mount", bone="Shoulder.L"):
        outline = ngon(8, 6.0)
        b.loft([place(outline, (16.0, 0, 131.0), ea, eb), place(outline, (23.5, 0, 131.0), ea, eb)], (ribs, "ribs"),
               cap0=swatch("ink"), cap1=swatch("ink"), key="shoulder-mount")
    with b.solid("shoulder", bone="Shoulder.L"):
        b.ball((25.5, 0.0, 131.0), 7.0, pauldron, "pauldron", axis=X, front=FRONT)
    with b.solid("upper-arm", bone="UpperArm.L"):
        outline = ngon(8, 5.2)
        b.loft([place(outline, (29.5, 0, 131.0), ea, eb), place(outline, (49.0, 0.4, 131.0), ea, eb)],
               sides(lambda k, i: (upper_arm(True), "under") if i in (1, 2, 3) else (upper_arm(False), "over")),
               cap0=swatch("ink"), cap1=swatch("ink"), key="upper-arm")
    with b.solid("elbow", bone="UpperArm.L"):
        b.ball((52.5, 0.5, 131.0), 5.8, joint, "joint", axis=X, front=FRONT)
    with b.solid("forearm", bone="LowerArm.L"):
        @sides
        def wall(k, i):
            if k == 1:
                return rim, "rim"
            return (gauntlet(True), "under") if i in (1, 2, 3) else (gauntlet(False), "over")

        b.loft([place(ngon(8, 5.2), (56.0, 0.4, 131.0), ea, eb), place(ngon(8, 8.0), (71.5, 0, 131.0), ea, eb),
                place(ngon(8, 8.0), (75.5, 0, 131.0), ea, eb)], wall, cap0=swatch("ink"), cap1=swatch("ink"), key="forearm")
    with b.solid("wrist", bone="LowerArm.L"):
        b.ball((78.5, 0.0, 131.0), 4.2, joint, "joint", axis=X, front=FRONT)

    with b.solid("palm", bone="Hand.L"):
        @sides
        def wall(k, i):
            if k == 1 and i == 6:
                return hand_back
            if k == 1 and i == 2:
                return hand_palm
            return swatch("lilac-4") if i in (1, 2, 3) or k == 0 else swatch("paper")

        b.loft([place(rrect(1.8, 5.5, 1.0), (79.0, 0, FINGER_Z), ea, eb), place(rrect(2.5, 6.5, 1.0), (81.0, 0, FINGER_Z), ea, eb),
                place(rrect(2.5, 6.5, 1.0), (FINGER_X, 0, FINGER_Z), ea, eb)], wall, cap0=swatch("ink"), cap1=swatch("lilac-0"), key="palm")

    def digit(name, root, direction, lengths, da, db, half_a, half_b, under):
        point = np.asarray(root, dtype=np.float64)
        for number, length in enumerate(lengths, start=1):
            tip = number == len(lengths)
            end = point + direction * length
            with b.solid(f"{name}{number}", bone=f"{name}{number}.L"):
                b.loft([place(rrect(half_a, half_b), point, da, db), place(rrect(half_a * (0.8 if tip else 1.0), half_b * (0.85 if tip else 1.0)), end, da, db)],
                       sides(lambda k, i, tip=tip: (finger(tip, i == under), "under" if i == under else "over")),
                       cap0=swatch("ink"), cap1=swatch("lilac-1" if tip else "ink"), key=f"digit{'-tip' if tip else ''}")
            point = end

    # A finger is 3.4 thick and 2.6 wide, so that there is a gap between it and the next.
    for name, (y, lengths) in FINGERS.items():
        digit(name, (FINGER_X, y, FINGER_Z), X, lengths, ea, eb, 1.7, 1.3, under=1)
    ta, tb = frame(THUMB_DIRECTION, -Z)
    digit("Thumb", THUMB_ROOT, THUMB_DIRECTION, THUMB_LENGTHS, ta, tb, 1.5, 1.7, under=0)


def build_holograms(b):
    """The projected ears and tail: thin shells on the second material, bent by their own bones."""
    axis = unit(EAR_TIP - EAR_BASE)
    length = float(np.linalg.norm(EAR_TIP - EAR_BASE))
    ea, eb = frame(axis, FRONT)
    w, h = EAR_ISLAND

    def ear_weights(point):
        t = float((np.asarray(point) - EAR_BASE) @ axis) / length
        upper = min(1.0, max(0.0, (t - 0.3) / 0.4))
        return {"Ear.L": 1.0 - upper, "Ear.L.001": upper} if 0.0 < upper < 1.0 else ({"Ear.L.001": 1.0} if upper >= 1.0 else {"Ear.L": 1.0})

    def ear():
        with b.solid("ear", weights=ear_weights, material=1):
            island = b.atlas.island("holo/ear", w, h, hologram(ear_half_width, True))
            rings = []
            for t, half_width, half_depth in EAR_SECTIONS:
                outline = [(half_width, 0.0), (0.0, half_depth), (-half_width, 0.0), (0.0, -half_depth)]
                rings.append([(EAR_BASE + axis * (t * length) + a * ea + c * eb, (w / 2.0 + a, (1.0 - t) * h)) for a, c in outline])
            for lower, upper in zip(rings, rings[1:]):
                for i in range(4):
                    j = (i + 1) % 4
                    corners = (lower[i], lower[j], upper[j], upper[i])
                    b.face_uv([p for p, _uv in corners], [uv for _p, uv in corners], island)
            b.face_uv([p for p, _uv in rings[0]][::-1], [uv for _p, uv in rings[0]][::-1], island)
            b.face_uv([p for p, _uv in rings[-1]], [uv for _p, uv in rings[-1]], island)

    ear()
    with b.mirrored():
        ear()

    def tail_weights(point):
        outer = min(1.0, max(0.0, (float(point[1]) - 16.5) / 9.0))
        return {"Tail": 1.0 - outer, "Tail.001": outer} if 0.0 < outer < 1.0 else ({"Tail.001": 1.0} if outer >= 1.0 else {"Tail": 1.0})

    with b.solid("tail", weights=tail_weights, material=1):
        b.ball(TAIL_CENTRE, TAIL_RADIUS, hologram(tail_half_width, False), "holo/tail", segments=6, rings=4, axis=Y, front=-Z,
               project=(-X, Z, TAIL_ISLAND))


def build_face(b, keys):
    """The sprites: a neutral quad per layer resting shown, and a hidden quad for every key that shows one.

    Returns {key name: (hidden depth, shown depth)} in metres for the keys that show a sprite."""
    sw = SCREEN_HALF_WIDTH
    rects = {"eyes": (-sw, sw, EYES_Z0, SCREEN_Z1), "mouth": (-sw, sw, SCREEN_Z0, EYES_Z0),
             "lid-left": (0.0, sw, EYES_Z0, SCREEN_Z1), "lid-right": (-sw, 0.0, EYES_Z0, SCREEN_Z1),
             bot_face.BLUESCREEN: (-sw, sw, SCREEN_Z0, SCREEN_Z1)}
    (c0, c1), (r0, r1) = bot_face.BLUSH_COLUMNS, bot_face.BLUSH_ROWS
    blush = [(-sw + c0, -sw + c1, SCREEN_Z1 - r1, SCREEN_Z1 - r0), (sw - c1, sw - c0, SCREEN_Z1 - r1, SCREEN_Z1 - r0)]

    def quad(tag, layer, sprite, rect, depth):
        x0, x1, z0, z1 = rect
        y = PLATE_Y - depth / PX
        with b.solid(f"sprite:{tag}", bone="Head", closed=False, tag=tag, sprite=True):
            b.poly([(x0, y, z0), (x1, y, z0), (x1, y, z1), (x0, y, z1)], Z, picture(bot_face.sprite_picture(layer, sprite)),
                   f"sprite/{layer}.{sprite}")

    for layer in ("eyes", "mouth"):
        quad(f"neutral:{layer}", layer, bot_face.NEUTRAL[layer], rects[layer], bot_face.NEUTRAL_SHOWN)
    depths, copies = {}, {}
    for name, _group, layer, sprite in keys:
        if layer is None:
            continue
        copy = copies.get((layer, sprite), 0)
        copies[(layer, sprite)] = copy + 1
        hidden = bot_face.hidden_depth(layer, sprite) + copy * bot_face.COPY_STEP
        depths[name] = (hidden, bot_face.shown_depth(layer, sprite))
        if sprite == "blush":
            # Two marks, one solid each so that neither is welded to anything.
            for n, rect in enumerate(blush):
                quad(f"key:{name}", layer, sprite, rect, -hidden)
        else:
            quad(f"key:{name}", layer, sprite, rects[layer if layer != "overlay" else sprite], -hidden)
    # A hidden triangle in the middle of the head for the keys that show nothing to move.
    with b.solid("anchor", bone="Head", closed=False, tag="anchor", sprite=True):
        b.poly([(-1.0, 0.0, 170.0), (1.0, 0.0, 170.0), (0.0, 0.0, 171.5)], Z, swatch(bot_face.BACKGROUND))
    return depths


def build(b, keys):
    build_head(b)
    build_torso(b)
    build_leg(b)
    build_arm(b)
    with b.mirrored():
        build_leg(b)
        build_arm(b)
    build_holograms(b)
    return build_face(b, keys)
