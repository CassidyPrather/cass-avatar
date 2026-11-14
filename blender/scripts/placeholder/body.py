"""Skin of the placeholder body below the head: trunk, neck, arms, hands, legs, feet, ears.

The trunk/limb topology helpers are shared with the garments (outfit.py),
which are the same tubes inflated. Skin zones change tile only on whole rings,
so each uv-tiles.json zone ends on a closed edge loop.
"""

import math

from .layout import ARM_COLUMNS, LEG_COLUMNS, TORSO_COLUMNS, section_ring
from .meshkit import add, cross, normalized, scale, smoothstep
from .rig import FINGERS, FRONT, UP, finger_points

# Trunk columns bounding each armhole: (front, middle, back).
ARMHOLE_COLUMNS = {1: (3, 4, 5), -1: (13, 12, 11)}
LEG_START_ANGLE = math.radians(310.0)


def build_trunk(mb, rows, armhole_rows, swatch, tile_of_span=None):
    """Lofts 16-column rings top to bottom, leaving a 2-column armhole on each side.

    `armhole_rows` is the (top, bottom) row index pair of the holes, or None.
    Returns the vertex grid [row][column]; vertices inside a hole are None.
    """
    grid = []
    for r, points in enumerate(rows):
        inside = armhole_rows is not None and armhole_rows[0] < r < armhole_rows[1]
        grid.append([None if inside and k in (4, 12) else mb.vert(p) for k, p in enumerate(points)])
    for r in range(len(rows) - 1):
        holed = armhole_rows is not None and armhole_rows[0] <= r < armhole_rows[1]
        ids = []
        for k in range(TORSO_COLUMNS):
            if holed and k in (3, 4, 11, 12):
                continue
            j = (k + 1) % TORSO_COLUMNS
            name = swatch(r, k) if callable(swatch) else swatch
            tile = tile_of_span(r) if tile_of_span else None
            ids.append(mb.face([grid[r][k], grid[r][j], grid[r + 1][j], grid[r + 1][k]], name, tile))
        axis = mb.centroid([v for v in grid[r] + grid[r + 1] if v is not None])
        mb.orient(ids, lambda centre, axis=axis: (centre[0] - axis[0], centre[1] - axis[1], 0.0))
    return grid


def armhole_loop(grid, armhole_rows, side):
    """The hole's boundary in arm-ring order: top first, then round by the front."""
    front, mid, back = ARMHOLE_COLUMNS[side]
    top, bottom = armhole_rows
    loop = [grid[top][mid], grid[top][front]]
    loop += [grid[r][front] for r in range(top + 1, bottom)]
    loop += [grid[bottom][front], grid[bottom][mid], grid[bottom][back]]
    loop += [grid[r][back] for r in range(bottom - 1, top, -1)]
    loop.append(grid[top][back])
    assert len(loop) == ARM_COLUMNS
    return loop


def build_branch(mb, L, last_row, swatch, tile=None, inflate=0.0, drop=0.0):
    """Adds the saddle loop under the trunk and the crotch line; returns (ring, crotch)."""
    ring_points, crotch_points = L.branch_ring(inflate, drop)
    ring = mb.ring(ring_points)
    crotch = mb.ring(crotch_points)
    mb.loft([last_row, ring], swatch, tile)
    return ring, crotch


def leg_top_loop(ring, crotch, side):
    """One leg's opening: its half of the branch ring closed through the crotch line."""
    if side > 0:
        outer = ring[0:9]
    else:
        outer = [ring[0]] + [ring[TORSO_COLUMNS - k] for k in range(1, 9)]
    loop = outer + crotch
    assert len(loop) == LEG_COLUMNS
    return loop


def leg_angles(mb, L, loop, z, side, blend):
    """Ring angles easing from the opening's real vertex angles (blend 0) to an even spacing (1)."""
    cx, cy = L.leg_centre(z)
    angles = []
    for j, v in enumerate(loop):
        x, y, _ = mb.co[v]
        actual = math.atan2(side * x - cx, -(y - cy))
        even = LEG_START_ANGLE + 2.0 * math.pi * j / LEG_COLUMNS
        offset = (actual - even + math.pi) % (2.0 * math.pi) - math.pi
        angles.append(even + offset * (1.0 - blend))
    return angles


def build_leg(mb, L, top_loop, zs, side, swatch, tile_of_z=None, inflate=0.0):
    """Lofts a leg from its opening down through heights `zs`; returns all rings (opening first)."""
    rings = [top_loop]
    for i, z in enumerate(zs):
        angles = leg_angles(mb, L, top_loop, z, side, blend=0.5 if i == 0 else 1.0)
        rings.append(mb.ring(L.leg_ring(z, angles, inflate if not callable(inflate) else inflate(z))))
    for i in range(len(rings) - 1):
        name = (lambda span, k, i=i: swatch(i, k)) if callable(swatch) else swatch
        mb.loft(rings[i:i + 2], name, tile_of_z(zs[i]) if tile_of_z else None)
    return rings


def even_leg_angles():
    return [LEG_START_ANGLE + 2.0 * math.pi * j / LEG_COLUMNS for j in range(LEG_COLUMNS)]


def _finger(mb, L, stem, radius, swatch):
    points = finger_points(L, stem)
    base, tip = points[0], points[3]
    length = math.dist(base, tip)
    axis = normalized((tip[0] - base[0], tip[1] - base[1], tip[2] - base[2]))
    u = normalized(cross(axis, UP))
    v = cross(u, axis)
    j1, j2 = L.finger_joints
    blend = 0.09

    def weights(f):
        w2 = smoothstep((f - (j1 - blend)) / (2 * blend))
        w3 = smoothstep((f - (j2 - blend)) / (2 * blend))
        return {mb.bone(f"{stem}1"): 1 - w2, mb.bone(f"{stem}2"): w2 * (1 - w3), mb.bone(f"{stem}3"): w2 * w3}

    rings = []
    for f in (0.0, 0.22, j1, 0.60, j2, 0.88, 0.97):
        r = radius * (1.0 - 0.22 * f) * (0.72 if f > 0.9 else 1.0)
        centre = add(base, scale(axis, length * f))
        ring = []
        for k in range(6):
            a = 2.0 * math.pi * k / 6
            ring.append(add(centre, add(scale(v, 0.85 * r * math.cos(a)), scale(u, r * math.sin(a)))))
        rings.append(mb.ring(ring, weights(f)))
    mb.loft(rings, swatch)
    mb.cap(rings[-1], tip, swatch, weights=weights(1.0))


def _arm_and_hand(mb, L, hole, side):
    mb.set_side(side)
    rings = [hole] + [mb.ring(L.arm_ring(x)) for x in L.arm_rows]
    mb.loft(rings, "skin", "body.arms")
    wrist = rings[-1]
    hand = [wrist] + [mb.ring(L.arm_ring(x, table=L.hand_table, power=3.0)) for x, _, _ in L.hand_table]
    mb.loft(hand, "skin", "always")
    mb.cap(hand[-1], (L.wrist_x + L.hand_len, L.arm_y, L.arm_z), "skin", "always")
    for stem in FINGERS:
        radius = L.thumb[1] if stem == "Thumb" else next(f[2] for f in L.fingers if f[0] == stem)
        _finger(mb, L, stem, radius, "skin")
    mb.set_side(1)


def _leg_and_foot(mb, L, ring, crotch, side):
    def zone(z):
        if z >= L.mid_thigh_z:
            return "body.hips"
        return "body.legs" if z >= L.mid_calf_z else "body.feet"

    mb.set_side(side)
    rings = build_leg(mb, L, leg_top_loop(ring, crotch, side), L.leg_rows, side, "skin", zone)
    foot, tip = L.foot_rings(even_leg_angles())
    foot = [rings[-1]] + [mb.ring(points) for points in foot]
    mb.loft(foot, "skin", "body.feet")
    mb.cap(foot[-1], tip, "skin", "body.feet")
    mb.set_side(1)


def _ear(mb, L, side):
    mb.set_side(side)
    axis = normalized(L.ear_dir)
    u = normalized(cross(axis, FRONT))
    front = cross(u, axis)
    start = 0.035 / L.ear_len
    third = (1.0 - start) / 3.0

    def weights(s):
        a = smoothstep((s - (start - 0.06)) / 0.12)
        b = smoothstep((s - (start + third - 0.07)) / 0.14)
        c = smoothstep((s - (start + 2 * third - 0.07)) / 0.14)
        return {"Head": 1 - a, mb.bone("Ear1"): a * (1 - b), mb.bone("Ear2"): a * b * (1 - c), mb.bone("Ear3"): a * b * c}

    # (fraction along the ear, half-width, half-thickness)
    profile = [
        (0.00, 0.014, 0.010), (0.12, 0.020, 0.010), (0.30, 0.027, 0.009), (0.50, 0.030, 0.008),
        (0.70, 0.026, 0.007), (0.86, 0.017, 0.005), (0.96, 0.008, 0.003),
    ]
    rings = []
    for s, half_width, half_thick in profile:
        centre = add(L.ear_root, scale(axis, L.ear_len * s))
        ring = []
        for k in range(8):
            a = 2.0 * math.pi * k / 8
            # The front-centre column is pulled back so the ear cups its pink inner face.
            depth = half_thick * (0.15 if k == 0 else math.cos(a))
            ring.append(add(centre, add(scale(u, half_width * math.sin(a)), scale(front, depth))))
        rings.append(mb.ring(ring, weights(s)))
    last = len(profile) - 2
    mb.loft(rings, lambda span, k: "ear-inner" if k in (0, 7) and 0 < span <= last else "ear-fur", "always")
    mb.cap(rings[-1], add(L.ear_root, scale(axis, L.ear_len)), "ear-fur", "always", weights=weights(1.0))
    mb.set_side(1)


def build_body(mb, L):
    """Adds everything below the head to `mb`; returns the neck rings (bottom to top) for the face keys."""
    rows = [L.torso_ring(z) for z in L.torso_rows]
    waist_row = L.torso_rows.index(L.waist_z)
    holes = (L.torso_rows.index(L.armhole_rows[0]), L.torso_rows.index(L.armhole_rows[-1]))
    grid = build_trunk(mb, rows, holes, "skin", lambda r: "body.torso" if r < waist_row else "body.hips")
    ring, crotch = build_branch(mb, L, grid[-1], "skin", "body.hips")

    neck_rows = [(L.neck_base_z + 0.020, 0.012), (L.neck_base_z + 0.045, 0.011), (L.chin_z + 0.012, 0.011),
                 (L.chin_z + 0.035, 0.010), (L.chin_z + 0.060, 0.010)]
    r = L.neck_radius
    neck = [grid[0]] + [mb.ring(section_ring(z, r, r, r, cy, power=2.0)) for z, cy in neck_rows]
    # The neck sits in the chin's shadow: one flat shade from the collar up.
    mb.loft(neck, lambda span, k: "skin-shade" if span >= 1 else "skin", "always")

    for side in (1, -1):
        _arm_and_hand(mb, L, armhole_loop(grid, holes, side), side)
        _leg_and_foot(mb, L, ring, crotch, side)
        _ear(mb, L, side)
    return neck
