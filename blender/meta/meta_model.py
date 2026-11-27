"""The meta figure itself: where its bones are, what its parts look like and how they are painted.

A game master in a hooded robe. The hood is deep and there is nothing in it. Over the shoulders a
short mantle; under it a long robe with a belt, wide sleeves, wrapped hands and boots. The trim,
the runes and the gems are one colour, the wearer's signature, which the game changes.

All positions are in pixels (PX metres each), Blender axes: +Z up, the figure faces -Y and its
left side is +X. Cloth is built as its left half and mirrored into the same solid.

Plain Python on top of meta_geo and the robot's kit; nothing here needs bpy.
"""

import math

import numpy as np

from bot_geo import frame, ngon, place, rrect
from meta_geo import edge_along, edge_distance, facepaint, sides, swatch, unit, vec

X, Y, Z = vec(1, 0, 0), vec(0, 1, 0), vec(0, 0, 1)
FRONT = vec(0, -1, 0)

# --- measurements ---------------------------------------------------------------------------------

HIP_Z, KNEE_Z, ANKLE_Z = 114.0, 62.0, 10.0
LEG_X = 11.0
SHOULDER = vec(20.0, 0.0, 174.0)
ELBOW_X, WRIST_X, KNUCKLE_X = 54.0, 86.0, 96.0
ARM_Z = 174.0
HEAD_Z = 190.0
HOOD_TOP = 224.0

FINGERS = {  # name -> (y of the knuckle, segment lengths)
    "Index": (-4.65, (5.0, 3.5, 3.0)),
    "Middle": (-1.55, (5.5, 4.0, 3.0)),
    "Ring": (1.55, (5.0, 3.5, 3.0)),
    "Little": (4.65, (4.0, 3.0, 2.5)),
}
THUMB_ROOT, THUMB_DIRECTION, THUMB_LENGTHS = vec(89.0, -6.5, 173.5), unit(vec(0.55, -0.8, -0.22)), (4.5, 3.5, 3.0)

# The robe below the belt: (z, half width, half depth, centre y, depth of the pleats).
SKIRT = ((11.0, 30.0, 27.0, 1.5, 2.8), (36.0, 26.0, 23.5, 1.0, 2.3), (62.0, 22.5, 20.0, 0.5, 1.6),
         (90.0, 20.0, 17.0, 0.3, 0.8), (112.0, 18.5, 14.5, 0.0, 0.0), (121.0, 15.5, 12.5, 0.0, 0.0))
SKIRT_SIDES = 14
TORSO = ((117.0, 15.0, 12.0), (126.0, 15.5, 12.3), (142.0, 17.5, 13.2), (160.0, 19.0, 13.8), (172.0, 17.5, 12.5), (181.0, 10.0, 8.5))
TORSO_SIDES = 10
BELT_Z0, BELT_Z1 = 116.0, 123.0

# The mantle, as rows of points from the middle of the front, round the left shoulder, to the
# middle of the back: its edge, the line of the shoulders, and the collar it hangs from.
MANTLE_EDGE = ((0.0, -17.5, 150.0), (10.5, -16.5, 156.0), (27.0, -13.0, 168.0), (40.0, 0.0, 181.5),
               (27.0, 13.5, 167.0), (11.0, 17.0, 154.0), (0.0, 18.0, 145.0))
MANTLE_MID = ((0.0, -14.5, 173.0), (7.5, -13.8, 174.5), (18.0, -10.5, 180.0), (27.0, 0.0, 183.8),
              (18.0, 11.0, 180.0), (7.5, 14.0, 174.5), (0.0, 14.8, 173.0))
MANTLE_TOP = ((0.0, -10.5, 184.0), (5.0, -9.5, 184.0), (9.5, -5.5, 184.0), (11.0, 0.0, 184.0),
              (9.5, 5.5, 184.0), (5.0, 9.5, 184.0), (0.0, 10.5, 184.0))

# The hood, as cross-sections from its rim back to its tip:
# (y at the bottom, y at the top, half width, bottom, height of the widest point, top).
HOOD_RIM_OUTER = (-11.0, -22.0, 16.5, 188.5, 202.0, 221.0)
# The inner edge of the lip lies in the plane of the rim, and the back of the dark inside in a
# plane parallel to it, VOID_DEPTH behind: (half width, bottom, height of the widest point, top).
HOOD_RIM_INNER = (15.2, 189.8, 202.0, 219.5)
HOOD_VOID = (13.5, 191.5, 202.0, 217.5)
VOID_DEPTH = 13.0
HOOD_SHELL = ((-8.0, -13.0, 18.5, 187.0, 203.0, 223.0), (2.0, 2.0, 19.5, 185.5, 203.5, HOOD_TOP),
              (12.0, 12.0, 18.0, 187.0, 204.5, 222.5), (20.0, 20.0, 14.0, 191.5, 206.0, 218.0),
              (26.5, 26.5, 8.5, 195.5, 204.0, 211.5))
# The hood ends in a point that droops a little.
HOOD_TIP = vec(0.0, 34.0, 197.0)
# Where the bone that carries the hanging lobe of the left cuff ends.
SLEEVE_SWAY_END = (84, 0, 154)
VOID_CENTRE = vec(0.0, -8.0, 204.0)

# The sleeve, as sections along the arm: (x, centre y, centre z, half depth, up, down).
SLEEVE = ((16.0, 0.0, 174.0, 6.5, 6.0, 7.0), (30.0, 0.0, 173.5, 7.0, 6.2, 8.5), (46.0, 0.3, 173.2, 7.8, 7.0, 9.5),
          (54.0, 0.5, 173.0, 8.0, 7.0, 10.5), (62.0, 0.4, 172.5, 8.6, 7.4, 12.0), (70.0, 0.2, 172.0, 9.5, 8.0, 14.0),
          (84.0, 0.0, 171.0, 11.0, 9.0, 17.0))
SLEEVE_LIP = (84.0, 0.0, 171.0, 9.3, 7.3, 15.2)
SLEEVE_INNER = (74.0, 0.0, 172.5, 7.5, 6.0, 10.0)

# Where a rune of the stole stands, by height, clear of every seam between faces.
STOLE_RUNES = (166.0, 150.0, 134.0, 101.0, 76.0, 49.0)
STOLE_END = 38.0
STOLE_HALF = 4

RUNES = (
    (".#.", "#.#", ".#.", "#.#", ".#."),
    ("#.#", ".#.", "###", ".#.", ".#."),
    (".#.", "###", "#.#", "###", ".#."),
    ("#..", "##.", "#.#", ".##", "..#"),
    (".#.", ".#.", "###", "#.#", "#.#"),
    ("#.#", "#.#", ".#.", "#.#", "#.#"),
    ("###", "#.#", "#.#", ".#.", ".#."),
)
# Runes that stand on a seam: the half to the right of it, the other half being its mirror.
SEAM_RUNES = (
    ("#.", "##", "#.", "#.", "#."),
    (".#", ".#", "#.", "#.", "#."),
    ("##", ".#", ".#", ".#", ".#"),
    ("#.", "##", "##", "#.", ".#"),
    ("#.", ".#", ".#", "#.", "#."),
    ("##", "#.", "##", "#.", "#."),
)
# The sigil on the back of the mantle, the half to the left of the seam (the seam is its right edge).
SIGIL = (
    "....#",
    "...##",
    "..#.#",
    ".#..#",
    "#..##",
    "#.#.#",
    "#..##",
    ".#..#",
    "..#.#",
    "...##",
    "....#",
    "....#",
)


# --- bones ----------------------------------------------------------------------------------------


def bones():
    """[(name, head, tail, roll axis)] in pixels for the left side and the middle; `.R` bones are mirrored by the build."""
    table = [
        ("Hips", (0, 0, 118), (0, 0, 128), FRONT),
        ("Spine", (0, 0, 128), (0, 0, 142), FRONT),
        ("Chest", (0, 0, 142), (0, 0, 178), FRONT),
        ("Neck", (0, 0, 178), (0, 0, HEAD_Z), FRONT),
        ("Head", (0, 0, HEAD_Z), (0, 0, 218), FRONT),
        # The head that is seen. Same place as Head, under the neck beside it.
        ("HeadVisual", (0, 0, HEAD_Z), (0, 0, 218), FRONT),
        ("Sway.Hood", (0, 21, 207), (0, 27.5, 203.5), Z),
        ("Sway.Hood.001", (0, 27.5, 203.5), tuple(HOOD_TIP), Z),
        ("Shoulder.L", (3, 0, 172), tuple(SHOULDER), Z),
        ("UpperArm.L", tuple(SHOULDER), (ELBOW_X, 0.5, ARM_Z), Z),
        ("LowerArm.L", (ELBOW_X, 0.5, ARM_Z), (WRIST_X, 0, ARM_Z), Z),
        ("Hand.L", (WRIST_X, 0, ARM_Z), (KNUCKLE_X, 0, ARM_Z), Z),
        ("Sway.Sleeve.L", (64, 0, 166), SLEEVE_SWAY_END, Z),
        ("UpperLeg.L", (LEG_X, 0, HIP_Z), (LEG_X, -0.6, KNEE_Z), FRONT),
        ("LowerLeg.L", (LEG_X, -0.6, KNEE_Z), (LEG_X, 1, ANKLE_Z), FRONT),
        ("Foot.L", (LEG_X, 1, ANKLE_Z), (LEG_X, -10, 3), Z),
        ("Toes.L", (LEG_X, -10, 3), (LEG_X, -22, 3), Z),
    ]
    for finger, (y, lengths) in FINGERS.items():
        x = KNUCKLE_X
        for number, length in enumerate(lengths, start=1):
            table.append((f"{finger}{number}.L", (x, y, ARM_Z), (x + length, y, ARM_Z), Z))
            x += length
    point = THUMB_ROOT
    for number, length in enumerate(THUMB_LENGTHS, start=1):
        table.append((f"Thumb{number}.L", tuple(point), tuple(point + THUMB_DIRECTION * length), Z))
        point = point + THUMB_DIRECTION * length
    return table


def index_tip():
    """The end of the left index finger, where a light would sit."""
    y, lengths = FINGERS["Index"]
    return vec(KNUCKLE_X + sum(lengths), y, ARM_Z)


# --- outlines -------------------------------------------------------------------------------------


def half_ring(z, rx, ry, n, cy=0.0, pleat=0.0):
    """Half of an n-sided outline about the vertical axis whose front and back are flat: from the
    middle of the front, round the left side, to the middle of the back. Every other corner stands
    `pleat` further out and the ones between as far in, beginning and ending with one that stands out."""
    corners = []
    for k in range(1, n // 2 + 1):
        theta = -math.pi / 2.0 + (2 * k - 1) * math.pi / n
        f = 1.0 + (pleat if k % 2 == 1 else -pleat) / max(rx, ry)
        corners.append(vec(rx * f * math.cos(theta), cy + ry * f * math.sin(theta), z))
    return [vec(0.0, corners[0][1], z)] + corners + [vec(0.0, corners[-1][1], z)]


def rim_y(z, depth=0.0):
    """Where the plane of the hood's rim is at a height, or a plane `depth` behind it."""
    y0, y1, _w, zb, _zm, zt = HOOD_RIM_OUTER
    return y0 + (y1 - y0) * (z - zb) / (zt - zb) + depth


def arch(section, depth=None):
    """Half of a hood's cross-section, from the middle of its underside up the left to its point.
    A section of four numbers lies in the plane of the rim, `depth` behind it."""
    if depth is None:
        y0, y1, w, zb, zm, zt = section

        def y(z):
            return y0 + (y1 - y0) * (z - zb) / (zt - zb)
    else:
        w, zb, zm, zt = section

        def y(z):
            return rim_y(z, depth)

    points = [(0.0, zb)]
    for a in (40.0, 75.0):
        r = math.radians(a)
        points.append((w * math.sin(r), zm - (zm - zb) * math.cos(r)))
    for a in (15.0, 42.0, 68.0):
        r = math.radians(a)
        points.append((w * math.cos(r) ** 1.3, zm + (zt - zm) * math.sin(r)))
    points.append((0.0, zt))
    return [vec(x, y(z), z) for x, z in points]


def sleeve_ring(section):
    """A sleeve's cross-section, eight corners from the lowest round by the front."""
    x, cy, cz, ry, up, down = section
    k = 0.72
    return [vec(x, cy, cz - down), vec(x, cy - ry * k, cz - down * k), vec(x, cy - ry, cz), vec(x, cy - ry * k, cz + up * k),
            vec(x, cy, cz + up), vec(x, cy + ry * k, cz + up * k), vec(x, cy + ry, cz), vec(x, cy + ry * k, cz - down * k)]


# --- paints ---------------------------------------------------------------------------------------


def weave(c, base, dark, light, phase=0):
    """Cloth: a flat colour with a few threads standing out, the same wherever it is painted."""
    c.fill(base)
    for y in range(c.h):
        for x in range(c.w):
            n = ((x * 73856093) ^ (y * 19349663) ^ ((phase + 1) * 83492791)) % 41
            if n == 0:
                c.px(x, y, light)
            elif n == 1:
                c.px(x, y, dark)


def rune(c, x, y, rows, colour="sig", glow=True):
    for j, row in enumerate(rows):
        for i, ch in enumerate(row):
            if ch == "#":
                c.px(x + i, y + j, colour, glow)


def shade_edges(c, f, tones, ridge):
    """Folds: the cloth darkens towards the edge that lies in a fold and catches light on the one that stands out.
    `ridge` is 'left', 'right', 'both' or None; the other edge is a fold."""
    base, dark, deep, light = tones
    from bot_geo import BAYER4
    for y in range(c.h):
        for x in range(c.w):
            px, py = x + 0.5, y + 0.5
            dl = abs(edge_distance(f.a0, f.b0, px, py))
            dr = abs(edge_distance(f.a1, f.b1, px, py))
            for side, d in (("left", dl), ("right", dr)):
                stands_out = ridge in (side, "both")
                if stands_out:
                    if d < 1.0 or (d < 2.5 and BAYER4[y % 4, x % 4] < 0.3):
                        c.px(x, y, light)
                elif ridge is not None:
                    if d < 1.2:
                        c.px(x, y, deep)
                    elif d < 3.4 and BAYER4[y % 4, x % 4] < 0.55:
                        c.px(x, y, dark)
                    elif d < 5.5 and BAYER4[y % 4, x % 4] < 0.2:
                        c.px(x, y, dark)


ROBE = ("cloth", "cloth-dark", "cloth-deep", "cloth-light")
MANTLE = ("mantle", "mantle-dark", "night-1", "mantle-light")


def stole(c, f, z_top, z_bottom, seam):
    """The band down the front, on the half of it this face carries. `seam` is 'left' or 'right': the side
    of the canvas the middle of the figure is on."""
    h = c.h

    def row(z):
        return (z_top - z) / max(1e-6, z_top - z_bottom) * h

    end = row(STOLE_END)

    def column(i):
        return i if seam == "left" else c.w - 1 - i

    for y in range(c.h):
        # The stole ends in a point above the hem.
        reach = STOLE_HALF if y + 0.5 < end - 4 else max(0.0, end - (y + 0.5))
        for i in range(STOLE_HALF + 1):
            if i < reach - 1:
                c.px(column(i), y, "night-1")
            elif i < reach:
                c.px(column(i), y, "sig-dim")
    for index, z in enumerate(STOLE_RUNES):
        y = row(z)
        if 3.0 <= y <= h - 3.0 and y < end - 8:
            rows = SEAM_RUNES[index % len(SEAM_RUNES)]
            for j, line in enumerate(rows):
                for i, ch in enumerate(line):
                    if ch == "#":
                        c.px(column(i), int(round(y)) - 2 + j, "sig", True)


def robe_wall(ridge, z_top, z_bottom, seam=None, hem=False, glyph=None, phase=0):
    @facepaint
    def paint(c, f):
        weave(c, "cloth", "cloth-dark", "cloth-light", phase)
        shade_edges(c, f, ROBE, ridge)
        # The robe is a little darker where the belt and the mantle shade it.
        if hem:
            h = c.h
            c.hline(h - 1, "night-1")
            c.hline(h - 2, "sig-lo")
            c.rect(0, h - 9, c.w, h - 2, "night-1")
            c.hline(h - 10, "sig-dim")
            middle = (f.a0[0] + f.a1[0]) / 2.0
            if glyph is not None and seam is None:
                rune(c, int(round(middle - 1.5)), h - 8, RUNES[glyph % len(RUNES)])
            elif seam is None:
                c.px(int(round(middle - 0.5)), h - 6, "sig-lo", True)
        if seam is not None:
            stole(c, f, z_top, z_bottom, seam)
    return paint


def torso_wall(z_top, z_bottom, seam=None, phase=0, shadow=False):
    @facepaint
    def paint(c, f):
        weave(c, "cloth", "cloth-dark", "cloth-light", phase)
        if shadow:
            c.fade(0, 0, c.w, min(c.h, 9), "cloth-deep", 0.9, 0.0)
        if seam is not None:
            stole(c, f, z_top, z_bottom, seam)
    return paint


def belt_wall(c):
    c.fill("leather")
    c.hline(0, "leather-dark")
    c.hline(c.h - 1, "leather-dark")
    for x in range(1, c.w, 3):
        c.px(x, c.h // 2, "leather-light")


def buckle_front(c):
    c.fill("brass")
    c.frame(0, 0, c.w, c.h, "wood")
    c.rect(2, 2, c.w - 2, c.h - 2, "night-1")
    c.rect(3, 3, c.w - 3, c.h - 3, "sig", True)
    c.px(3, 3, "sig-hi", True)


def mantle_wall(trim, seam=None, phase=0, dots=True):
    """The mantle's cloth. With `trim`, the band along its lower edge; with `seam` = 'right', the half sigil."""
    @facepaint
    def paint(c, f):
        weave(c, "mantle", "mantle-dark", "mantle-light", phase)
        if trim:
            for y in range(c.h):
                for x in range(c.w):
                    d = abs(edge_distance(f.a0, f.a1, x + 0.5, y + 0.5))
                    along = edge_along(f.a0, f.a1, x + 0.5, y + 0.5)
                    if d < 1.0:
                        c.px(x, y, "night-1")
                    elif d < 2.0:
                        c.px(x, y, "sig-lo")
                    elif d < 5.0:
                        c.px(x, y, "night-1")
                        if dots and 3.0 <= d < 4.0 and (along % 5.0) < 1.0:
                            c.px(x, y, "sig", True)
                    elif d < 6.0:
                        c.px(x, y, "sig-dim")
        if seam == "right":
            # The sigil hangs below the collar, in the middle of the back.
            top = int(round(max(f.b0[1], f.b1[1]))) + 5
            for j, row in enumerate(SIGIL):
                for i, ch in enumerate(row):
                    if ch == "#":
                        c.px(c.w - len(row) + i, top + j, "sig", True)
    return paint


def cowl_wall(phase=0):
    def paint(c):
        weave(c, "mantle", "mantle-dark", "mantle-light", phase)
        c.hline(c.h - 1, "mantle-dark")
        c.dither(0, c.h - 3, c.w, c.h - 1, "mantle-dark", 0.5)
        c.hline(0, "mantle-light")
    return paint


def hood_wall(rim=False, crest=False, phase=0):
    """The hood's cloth. With `rim`, the band behind its opening. With `crest`, the seam along the top
    of the hood, which is the edge of the face's second corners."""
    @facepaint
    def paint(c, f):
        weave(c, "mantle", "mantle-dark", "mantle-light", phase)
        if rim:
            for y in range(c.h):
                for x in range(c.w):
                    d = abs(edge_distance(f.a0, f.a1, x + 0.5, y + 0.5))
                    along = edge_along(f.a0, f.a1, x + 0.5, y + 0.5)
                    if d < 1.0:
                        c.px(x, y, "night-1")
                    elif d < 2.0:
                        c.px(x, y, "sig-dim")
                    elif 3.0 <= d < 4.0 and (along % 4.0) < 1.0:
                        c.px(x, y, "sig-lo")
        if crest:
            for y in range(c.h):
                for x in range(c.w):
                    if abs(edge_distance(f.a1, f.b1, x + 0.5, y + 0.5)) < 1.0:
                        c.px(x, y, "mantle-dark")
    return paint


def sleeve_wall(under, cuff=False, phase=0):
    def paint(c):
        if under:
            weave(c, "cloth-dark", "cloth-deep", "cloth", phase)
        else:
            weave(c, "cloth", "cloth-dark", "cloth-light", phase)
        if cuff:
            c.hline(0, "night-1")
            c.hline(1, "sig-lo")
            c.rect(0, 2, c.w, 6, "night-1")
            for x in range(c.w // 2 % 4, c.w, 4):
                c.px(x, 3, "sig", True)
                c.px(x, 4, "sig", True)
            c.hline(6, "sig-dim")
    return paint


def wrap(under=False, tip=False):
    def paint(c):
        c.fill("wrap-mid" if under else "wrap")
        for y in range(1, c.h, 3):
            c.hline(y, "wrap-dark")
        if tip:
            c.hline(0, "wrap-dark")
    return paint


def hand_back(c):
    c.fill("wrap")
    for y in range(2, c.h, 3):
        c.hline(y, "wrap-dark")
    c.px(c.w // 2, c.h // 2, "sig-lo", True)


def hand_palm(c):
    c.fill("wrap-mid")
    for y in range(1, c.h, 3):
        c.hline(y, "wrap-dark")


def digit(tip, under):
    def paint(c):
        c.fill("wrap-mid" if under else "wrap")
        c.hline(c.h - 1, "wrap-dark")
        if tip and not under:
            c.hline(0, "wrap-mid")
    return paint


def boot_side(c):
    c.fill("leather")
    c.hline(c.h - 1, "leather-dark")
    c.hline(c.h - 2, "soot")
    c.hline(0, "leather-light")


def boot_top(c):
    c.fill("leather")
    c.vline(c.w // 2, "leather-dark")
    for y in range(2, c.h - 1, 3):
        c.px(c.w // 2 - 1, y, "leather-light")
        c.px(c.w // 2 + 1, y, "leather-light")


def toe_cap(c):
    c.fill("leather-dark")
    c.hline(0, "leather-light")
    c.hline(c.h - 1, "soot")


def boot_shaft(c):
    c.fill("leather")
    c.hline(c.h - 1, "leather-dark")
    for y in range(3, c.h - 2, 4):
        c.hline(y, "leather-dark")
    c.hline(0, "leather-light")


def sole(c):
    c.fill("soot")
    for x in range(1, c.w, 3):
        c.vline(x, "leather-dark")


def tome_cover(c):
    c.fill("leather")
    c.frame(0, 0, c.w, c.h, "leather-dark")
    for x, y in ((1, 1), (c.w - 2, 1), (1, c.h - 2), (c.w - 2, c.h - 2)):
        c.px(x, y, "brass")
    rune(c, c.w // 2 - 1, c.h // 2 - 2, RUNES[2])


def tome_pages(c):
    c.fill("cream")
    for y in range(1, c.h, 2):
        c.hline(y, "wrap-mid")
    c.vline(0, "leather-dark")
    c.vline(c.w - 1, "leather-dark")


def tome_spine(c):
    c.fill("leather-dark")
    for y in (2, c.h - 3):
        c.hline(y, "brass")


def pouch_front(c):
    c.fill("leather")
    c.rect(0, 0, c.w, c.h // 2, "leather-light")
    c.hline(c.h // 2, "leather-dark")
    c.px(c.w // 2, c.h // 2 + 1, "brass")
    c.hline(c.h - 1, "leather-dark")


# --- parts ----------------------------------------------------------------------------------------


def box(b, low, high, paint):
    """An upright box. `paint(face)` gives the paint of 'front', 'back', 'left', 'right', 'top' and 'bottom'."""
    x0, y0, z0 = low
    x1, y1, z1 = high
    b.poly([(x0, y0, z0), (x1, y0, z0), (x1, y0, z1), (x0, y0, z1)], Z, paint("front"))
    b.poly([(x1, y1, z0), (x0, y1, z0), (x0, y1, z1), (x1, y1, z1)], Z, paint("back"))
    b.poly([(x1, y0, z0), (x1, y1, z0), (x1, y1, z1), (x1, y0, z1)], Z, paint("left"))
    b.poly([(x0, y1, z0), (x0, y0, z0), (x0, y0, z1), (x0, y1, z1)], Z, paint("right"))
    b.poly([(x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)], Y, paint("top"))
    b.poly([(x0, y1, z0), (x1, y1, z0), (x1, y0, z0), (x0, y0, z0)], Y, paint("bottom"))


def blend(*pairs):
    """{bone: weight} from (bone, weight) pairs, leaving out what weighs nothing."""
    weights = {}
    for bone, weight in pairs:
        if weight > 1e-6:
            weights[bone] = weights.get(bone, 0.0) + weight
    return weights


def clamp(value, low=0.0, high=1.0):
    return max(low, min(high, value))


def skirt_weights(p):
    x, _y, z = (float(c) for c in p)
    left = clamp(0.5 + x / 14.0)
    if z >= 112.0:
        return {"Hips": 1.0}
    if z >= KNEE_Z:
        legs = clamp((112.0 - z) / (112.0 - KNEE_Z) * 1.6)
        upper = legs if z > KNEE_Z + 0.5 else 0.5
        lower = 0.0 if z > KNEE_Z + 0.5 else 0.5
        return blend(("Hips", 1.0 - legs), ("UpperLeg.L", upper * left), ("UpperLeg.R", upper * (1.0 - left)),
                     ("LowerLeg.L", lower * left), ("LowerLeg.R", lower * (1.0 - left)))
    lower = 0.5 + 0.5 * clamp((KNEE_Z - z) / 26.0)
    return blend(("UpperLeg.L", (1.0 - lower) * left), ("UpperLeg.R", (1.0 - lower) * (1.0 - left)),
                 ("LowerLeg.L", lower * left), ("LowerLeg.R", lower * (1.0 - left)))


def build_skirt(b):
    rings = [half_ring(z, rx, ry, SKIRT_SIDES, cy, pleat) for z, rx, ry, cy, pleat in SKIRT]
    last = len(rings[0]) - 2

    @sides
    def wall(k, i):
        z0, z1 = SKIRT[k][0], SKIRT[k + 1][0]
        pleated = SKIRT[k][4] > 0.0 or SKIRT[k + 1][4] > 0.0
        if i == 0:
            return robe_wall("right" if pleated else None, z1, z0, seam="left", hem=k == 0, phase=k)
        if i == last:
            return robe_wall("left" if pleated else None, z1, z0, hem=k == 0, glyph=None, phase=k + i)
        ridge = ("left" if i % 2 == 1 else "right") if pleated else None
        return robe_wall(ridge, z1, z0, hem=k == 0, glyph=(i + 1) // 2 if i % 2 == 1 else None, phase=k + i)

    def anchor(k, i):
        return (0.0, 1.0) if i == 0 else (1.0, 1.0) if i == last else (0.5, 1.0)

    def half():
        b.strip(rings, wall, key="skirt", inside=lambda k, i: (0.0, 0.0, (SKIRT[k][0] + SKIRT[k + 1][0]) / 2.0), anchor=anchor)
        b.fan((0.0, 1.0, 15.0), rings[0], swatch("night-0"), key="skirt/under", inside=(0.0, 0.0, 40.0))
        b.fan((0.0, 0.0, 121.0), rings[-1], swatch("cloth-deep"), key="skirt/top", inside=(0.0, 0.0, 100.0))

    with b.solid("skirt", weights=skirt_weights):
        half()
        with b.mirrored():
            half()


def torso_weights(p):
    z = float(p[2])
    if z <= 118.0:
        return {"Hips": 1.0}
    if z <= 127.0:
        return {"Hips": 0.5, "Spine": 0.5}
    if z <= 143.0:
        return {"Spine": 0.5, "Chest": 0.5}
    return {"Chest": 1.0}


def build_torso(b):
    rings = [half_ring(z, rx, ry, TORSO_SIDES) for z, rx, ry in TORSO]
    last = len(rings[0]) - 2

    @sides
    def wall(k, i):
        z0, z1 = TORSO[k][0], TORSO[k + 1][0]
        return torso_wall(z1, z0, seam="left" if i == 0 else None, phase=k * 3 + i, shadow=k == 3)

    def anchor(k, i):
        return (0.0, 1.0) if i == 0 else (1.0, 1.0) if i == last else (0.5, 1.0)

    def half():
        b.strip(rings, wall, key="torso", inside=lambda k, i: (0.0, 0.0, (TORSO[k][0] + TORSO[k + 1][0]) / 2.0), anchor=anchor)
        b.fan((0.0, 0.0, TORSO[0][0]), rings[0], swatch("cloth-deep"), key="torso/under", inside=(0.0, 0.0, 140.0))
        b.fan((0.0, 0.0, 183.0), rings[-1], swatch("cloth-deep"), key="torso/top", inside=(0.0, 0.0, 140.0))

    with b.solid("torso", weights=torso_weights):
        half()
        with b.mirrored():
            half()


def build_belt(b):
    rings = [half_ring(z, 18.3, 14.8, SKIRT_SIDES) for z in (BELT_Z0, BELT_Z1)]

    def half():
        b.strip(rings, (belt_wall, "wall"), key="belt", inside=(0.0, 0.0, 119.5))
        b.fan((0.0, 0.0, BELT_Z0), rings[0], swatch("leather-dark"), key="belt/under", inside=(0.0, 0.0, 119.5))
        b.fan((0.0, 0.0, BELT_Z1), rings[1], swatch("leather-dark"), key="belt/top", inside=(0.0, 0.0, 119.5))

    with b.solid("belt", bone="Hips"):
        half()
        with b.mirrored():
            half()

    front = rings[0][0][1]
    with b.solid("buckle", bone="Hips"):
        box(b, (-4.0, front - 1.5, BELT_Z0 - 0.5), (4.0, front + 1.0, BELT_Z1 + 0.5),
            lambda face: buckle_front if face == "front" else swatch("brass"))

    # A book at the left hip, hung from the belt by a strap, and a pouch at the right.
    with b.solid("tome", bone="Hips"):
        def tome(face):
            if face == "left":
                return tome_cover
            if face in ("front", "bottom"):
                return tome_pages
            if face == "back":
                return tome_spine
            return swatch("leather-dark") if face == "right" else tome_pages
        box(b, (17.0, -6.0, 98.0), (22.5, 4.0, 111.0), tome)
    with b.solid("tome-strap", bone="Hips"):
        box(b, (18.5, -2.0, 110.5), (20.5, 0.0, BELT_Z0 + 2.0), lambda face: swatch("leather-dark"))
    with b.solid("pouch", bone="Hips"):
        box(b, (-23.0, -5.0, 103.0), (-17.5, 3.0, 114.0), lambda face: pouch_front if face == "right" else swatch("leather" if face != "bottom" else "leather-dark"))


def mantle_weights(p):
    x = abs(float(p[0]))
    if float(p[2]) >= 183.9:
        return {"Chest": 1.0}
    arm = clamp((x - 20.0) / 15.0) * 0.55
    shoulder = clamp((x - 6.0) / 14.0) * (1.0 - arm) * 0.5
    return blend(("UpperArm.L", arm), ("Shoulder.L", shoulder), ("Chest", 1.0 - arm - shoulder))


def build_mantle(b):
    rings = [[vec(*p) for p in row] for row in (MANTLE_EDGE, MANTLE_MID, MANTLE_TOP)]
    last = len(rings[0]) - 2
    inside = (0.0, 0.0, 178.0)

    @sides
    def wall(k, i):
        return mantle_wall(trim=k == 0, seam="right" if (k == 0 and i == last) else None, phase=k * 5 + i)

    def anchor(k, i):
        return (0.0, 1.0) if i == 0 else (1.0, 1.0) if i == last else (0.5, 1.0)

    def half():
        b.strip(rings, wall, key="mantle", inside=inside, anchor=anchor)
        b.fan((0.0, 0.0, 170.0), rings[0], swatch("night-0"), key="mantle/under", inside=inside)
        b.fan((0.0, 0.0, 185.0), rings[-1], swatch("mantle-dark"), key="mantle/top", inside=inside)

    with b.solid("mantle", weights=mantle_weights):
        half()
        with b.mirrored():
            half()

    # The cowl: the roll of cloth the hood sits in.
    cowl = [half_ring(181.0, 13.5, 13.5, 12, 2.0), half_ring(184.5, 17.0, 16.5, 12, 2.5), half_ring(189.0, 17.0, 16.5, 12, 2.5),
            half_ring(191.5, 14.5, 14.0, 12, 2.5), half_ring(190.0, 11.5, 11.0, 12, 2.5)]

    @sides
    def roll(k, i):
        if k == 3:
            return swatch("night-1")
        return cowl_wall(k), f"roll{k}"

    def within(k, i):
        # A point inside the roll, behind the middle of its outer wall.
        middle = (cowl[1][i] + cowl[1][i + 1] + cowl[2][i] + cowl[2][i + 1]) / 4.0
        return (middle[0] * 0.85, 2.5 + (middle[1] - 2.5) * 0.85, middle[2])

    def cowl_half():
        b.strip(cowl, roll, key="cowl", inside=within)
        b.fan((0.0, 2.0, 181.0), cowl[0], swatch("mantle-dark"), key="cowl/under", inside=(0.0, 2.5, 187.0))
        b.fan((0.0, 2.5, 187.5), cowl[-1], swatch("night-0"), key="cowl/dish", inside=(0.0, 2.5, 184.0))

    with b.solid("cowl", weights=lambda p: {"Chest": 0.5, "Neck": 0.5}):
        cowl_half()
        with b.mirrored():
            cowl_half()


def hood_weights(p):
    y = float(p[1])
    if y >= 33.0:
        return {"Sway.Hood.001": 1.0}
    if y >= 26.0:
        return {"HeadVisual": 0.35, "Sway.Hood": 0.65}
    return {"HeadVisual": 1.0}


def build_hood(b):
    outer, inner, void = arch(HOOD_RIM_OUTER), arch(HOOD_RIM_INNER, 0.0), arch(HOOD_VOID, VOID_DEPTH)
    shell = [outer] + [arch(section) for section in HOOD_SHELL]
    top = len(outer) - 2

    @sides
    def wall(k, i):
        return hood_wall(rim=k == 0, crest=i == top, phase=k * 3 + i)

    def anchor(k, i):
        # Seen from outside with the back of the hood up, the top of the hood is to the left.
        return (0.0, 1.0) if i == top else (1.0, 1.0) if i == 0 else (0.5, 1.0)

    # The middle of each section, on the plane the hood is mirrored in: between two of them is inside the hood.
    middles = [np.mean(section, axis=0) * vec(0, 1, 1) for section in shell]

    def half():
        b.strip(shell, wall, key="hood", inside=lambda k, i: tuple((middles[k] + middles[k + 1]) / 2.0), anchor=anchor)
        b.fan(HOOD_TIP, shell[-1], sides(lambda i: (hood_wall(phase=i), "tip")), key="hood/tip",
              inside=tuple(middles[-1] * 0.7 + HOOD_TIP * 0.3))
        # The lip of the opening, the walls of the dark inside, and its back.
        b.strip([outer, inner], swatch("sig-lo"), key="hood/lip", inside=tuple(middles[1]))
        b.strip([inner, void], sides(lambda k, i: swatch("night-0")), key="hood/void", inside=tuple(VOID_CENTRE), inward=True)
        b.wall(void, Z, swatch("black"), key="hood/back", inside=tuple(VOID_CENTRE), inward=True)

    with b.solid("hood", weights=hood_weights):
        half()
        with b.mirrored():
            half()


def sleeve_weights(p):
    x, _y, z = (float(c) for c in p)
    if x <= 16.5:
        return {"Shoulder.L": 1.0}
    if x <= 30.5:
        return {"Shoulder.L": 0.25, "UpperArm.L": 0.75}
    if x <= 46.5:
        return {"UpperArm.L": 1.0}
    if x <= 54.5:
        return {"UpperArm.L": 0.5, "LowerArm.L": 0.5}
    if x <= 62.5:
        return {"LowerArm.L": 1.0}
    # The hanging lobe of the cuff sways.
    centre = 172.0 if x <= 70.5 else 172.5 if x <= 74.5 else 171.0
    hang = clamp((centre - z) / (14.0 if x <= 70.5 else 10.0 if x <= 74.5 else 17.0))
    sway = hang ** 1.5 * (0.45 if x <= 70.5 else 0.8)
    return blend(("LowerArm.L", 1.0 - sway), ("Sway.Sleeve.L", sway))


def build_arm(b):
    rings = [sleeve_ring(section) for section in SLEEVE]
    lip, inner = sleeve_ring(SLEEVE_LIP), sleeve_ring(SLEEVE_INNER)
    centres = [vec(s[0], s[1], s[2]) for s in SLEEVE]

    @sides
    def wall(k, i):
        under = i in (0, 7)
        return sleeve_wall(under, cuff=k == len(rings) - 2, phase=k + min(i, 7 - i)), f"{k}.{min(i, 7 - i)}"

    with b.solid("sleeve", weights=sleeve_weights):
        b.strip(rings, wall, key="sleeve", closed=True, inside=lambda k, i: tuple((centres[k] + centres[k + 1]) / 2.0),
                anchor=(0.5, 0.0))
        b.fan(centres[0], rings[0], swatch("cloth-deep"), key="sleeve/root", closed=True, inside=tuple(centres[1]))
        b.strip([rings[-1], lip], swatch("sig-lo"), key="sleeve/lip", closed=True, inside=tuple(centres[-2]))
        hollow = (79.0, 0.0, 171.5)
        b.strip([lip, inner], sides(lambda k, i: swatch("night-0")), key="sleeve/inside", closed=True, inside=hollow, inward=True)
        b.wall(inner, Z, swatch("black"), key="sleeve/back", inside=hollow, inward=True)

    ea, eb = frame(X, FRONT)  # ea is down, eb is back: sides 1..3 of a tube face the ground
    with b.solid("wrist", bone="LowerArm.L"):
        outline = ngon(6, 3.4)
        b.loft([place(outline, (72.0, 0, ARM_Z), ea, eb), place(outline, (WRIST_X + 1.0, 0, ARM_Z), ea, eb)],
               (wrap(), "wrap"), cap0=swatch("black"), cap1=swatch("wrap-dark"), key="wrist")

    with b.solid("palm", bone="Hand.L"):
        @sides
        def palm(k, i):
            if k == 1 and i == 6:
                return hand_back
            if k == 1 and i == 2:
                return hand_palm
            return swatch("wrap-mid") if i in (1, 2, 3) or k == 0 else swatch("wrap")

        b.loft([place(rrect(1.8, 5.5, 1.0), (WRIST_X + 0.5, 0, ARM_Z), ea, eb), place(rrect(2.5, 6.5, 1.0), (WRIST_X + 2.5, 0, ARM_Z), ea, eb),
                place(rrect(2.5, 6.5, 1.0), (KNUCKLE_X, 0, ARM_Z), ea, eb)], palm, cap0=swatch("wrap-dark"), cap1=swatch("wrap-dark"), key="palm")

    def finger(name, root, direction, lengths, da, db, half_a, half_b, under, lit=False):
        point = np.asarray(root, dtype=np.float64)
        for number, length in enumerate(lengths, start=1):
            tip = number == len(lengths)
            end = point + direction * length
            with b.solid(f"{name}{number}", bone=f"{name}{number}.L"):
                b.loft([place(rrect(half_a, half_b), point, da, db), place(rrect(half_a * (0.8 if tip else 1.0), half_b * (0.85 if tip else 1.0)), end, da, db)],
                       sides(lambda k, i, tip=tip: (digit(tip, i == under), ("tip-" if tip else "") + ("under" if i == under else "over"))),
                       cap0=swatch("wrap-dark"), cap1=swatch("sig", True) if (tip and lit) else swatch("wrap-mid" if tip else "wrap-dark"),
                       key=f"digit{'-tip' if tip else ''}")
            point = end

    # A finger is 3.4 thick and 2.6 wide, so that there is a gap between it and the next.
    for name, (y, lengths) in FINGERS.items():
        finger(name, (KNUCKLE_X, y, ARM_Z), X, lengths, ea, eb, 1.7, 1.3, under=1, lit=name == "Index")
    ta, tb = frame(THUMB_DIRECTION, -Z)
    finger("Thumb", THUMB_ROOT, THUMB_DIRECTION, THUMB_LENGTHS, ta, tb, 1.5, 1.7, under=0)


def build_boot(b):
    ea, eb = frame(Z, FRONT)
    with b.solid("boot-shaft", bone="LowerLeg.L"):
        b.loft([place(ngon(8, 6.3), (LEG_X, 1.5, 6.0), ea, eb), place(ngon(8, 6.8), (LEG_X, 1.5, 24.0), ea, eb)], (boot_shaft, "shaft"),
               cap0=swatch("soot"), cap1=swatch("leather-dark"), key="boot-shaft")

    fa, fb = frame(-Y, -Z)
    with b.solid("boot", bone="Foot.L"):
        @sides
        def wall(k, i):
            if i in (0, 1, 7):
                return (sole, "sole") if (k == 1 and i == 0) else swatch("soot")
            if k == 0:
                return swatch("leather-dark")
            return (boot_side, "side") if i in (2, 6) else (boot_top, "top") if i == 4 else swatch("leather")

        b.loft([place(rrect(5.5, 3.5, 1.5, cx=LEG_X, cy=3.5), (0, 9.5, 0), fa, fb), place(rrect(6.8, 5.0, 1.5, cx=LEG_X, cy=5.0), (0, 7.5, 0), fa, fb),
                place(rrect(6.8, 5.0, 1.5, cx=LEG_X, cy=5.0), (0, -10.0, 0), fa, fb)], wall, cap0=swatch("leather-dark"), cap1=swatch("soot"),
               up=lambda k, i: Z if i in (2, 6) else None, key="boot")
    with b.solid("boot-toes", bone="Toes.L"):
        @sides
        def wall(k, i):
            if i in (0, 1, 7):
                return (sole, "sole") if (k == 0 and i == 0) else swatch("soot")
            if k == 1:
                return swatch("leather-dark")
            return (toe_cap, "top") if i == 4 else (boot_side, "side") if i in (2, 6) else swatch("leather-dark")

        b.loft([place(rrect(6.8, 5.0, 1.5, cx=LEG_X, cy=5.0), (0, -10.0, 0), fa, fb), place(rrect(6.8, 4.4, 1.5, cx=LEG_X, cy=4.4), (0, -21.0, 0), fa, fb),
                place(rrect(5.2, 3.0, 1.5, cx=LEG_X, cy=3.0), (0, -25.5, 0), fa, fb)], wall, cap0=swatch("soot"), cap1=swatch("leather-dark"),
               up=lambda k, i: Z if i in (2, 6) else None, key="boot-toes")


def build(b):
    build_skirt(b)
    build_torso(b)
    build_belt(b)
    build_mantle(b)
    build_hood(b)
    build_arm(b)
    build_boot(b)
    with b.mirrored():
        build_arm(b)
        build_boot(b)
