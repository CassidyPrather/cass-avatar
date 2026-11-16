"""Rabbit ears and tail.

The ears are long, upright and cupped: a thick rounded back in the hair's
colour, a rolled rim, and a hollow pink inside that ends in a rounded point
short of the tip. A ring of fur tufts hides where each one roots. They sit
on three-bone chains that physics and the gesture expressions both move,
wide enough apart to pass the hat's crown and come up through its brim
(hat.py cuts the holes from `ear_axes`).

The tail is a scut: short, tapered and turned up, darker on top and pale
underneath, with tufts breaking its outline. Not a pom-pom.
"""

import math

import numpy as np
from mathutils import Vector

from . import common, hair, rig, sweep
from .common import smoothstep

# Left ear, in metres from the skull's centre: where it roots, and the path to its tip.
EAR_ROOT = np.array((0.128, 0.012, 0.086))
EAR_GUIDE = np.array(((-0.012, -0.002, -0.030), (0.0, 0.0, 0.0), (0.014, 0.006, 0.115), (0.040, 0.020, 0.245), (0.070, 0.040, 0.360)))
EAR_HALF_WIDTH = 0.052
EAR_DEPTH = 0.50            # how thick the ear is front to back, as a fraction of its half-width
# The ear's open side faces this way (left ear); the right ear mirrors it.
EAR_FRONT = np.array((0.30, -0.95, 0.0))
EAR_JOINTS = (0.085, 0.36, 0.66, 1.0)     # fractions of the path where Ear1, Ear2, Ear3 start, and the tip

# Cross-sections as (across, towards the back) on a unit half-width. The back is a dome,
# the front has a rolled rim at each edge and is hollow between them.
EAR_PROFILES = {
    # The rim rolls forward past the edge, then steps down a wall into the hollow: that step is
    # the crease that keeps the front from reading as a flat card.
    "full": [(-1.0, 0.10), (-0.80, 0.62), (-0.36, 0.94), (0.36, 0.94), (0.80, 0.62), (1.0, 0.10),
             (0.93, -0.20), (0.70, -0.16), (0.56, 0.26), (0.0, 0.58), (-0.56, 0.26), (-0.70, -0.16), (-0.93, -0.20)],
    "lite": [(-1.0, 0.10), (-0.55, 0.85), (0.55, 0.85), (1.0, 0.10), (0.80, -0.14), (0.0, 0.50), (-0.80, -0.14)],
}
# Sides of each profile (by the index of their first point): the hollow inside, and the walls down into it.
EAR_INSIDE = {"full": (8, 9), "lite": (4, 5)}
EAR_WALLS = {"full": (7, 10), "lite": ()}

# The tail's centre line from where it roots on the back (x left, y back, z up), and its radius along it.
TAIL_GUIDE = np.array(((0.0, -0.024, -0.010), (0.0, 0.040, 0.000), (0.0, 0.088, 0.026), (0.0, 0.122, 0.066), (0.0, 0.138, 0.110)))
TAIL_RADII = (0.020, 0.037, 0.042, 0.030, 0.008)
TAIL_FLATTEN = (1.25, 0.66)     # wider than it is thick
# Tufts that break up the outline: (fraction along the tail, sideways lean, half-width).
TAIL_TUFTS = ((0.46, 1.0, 0.021), (0.46, -1.0, 0.021), (0.72, 0.8, 0.019), (0.72, -0.8, 0.019), (0.60, 0.0, 0.020))


def _mirror(points, sign):
    return np.asarray(points, dtype=np.float64) * (sign, 1.0, 1.0)


def ear_guide(armature, sign):
    return hair.skull_centre(armature) + _mirror(EAR_ROOT, sign) + _mirror(EAR_GUIDE, sign)


def ear_axes(armature):
    """(point, unit direction) of each ear near its root, for whatever has to make room for it."""
    axes = []
    for sign in (1.0, -1.0):
        guide = ear_guide(armature, sign)
        axes.append((guide[1], (guide[2] - guide[1]) / np.linalg.norm(guide[2] - guide[1])))
    return axes


def _ear_width(fraction):
    """Half-width along the ear, as a fraction of its widest: narrow at the root, a rounded tip."""
    rise = 0.52 + 0.48 * smoothstep(0.0, 0.40, fraction)
    fall = np.sqrt(np.clip(1.0 - (np.clip(fraction - 0.45, 0.0, None) / 0.55) ** 2.2, 0.0, 1.0))
    return rise * fall


def _ear_bones(armature):
    rows = []
    for side, sign in (("L", 1.0), ("R", -1.0)):
        path = sweep.spline(ear_guide(armature, sign), 40)
        joints = [path[int(round(f * 40))] for f in EAR_JOINTS]
        front = _mirror(EAR_FRONT, sign)
        for i in range(3):
            rows.append((f"Ear{i + 1}.{side}", joints[i], joints[i + 1], "Head" if i == 0 else f"Ear{i}.{side}", tuple(front)))
    return rows


def build_ears(ctx):
    armature, level, detail = ctx["armature"], ctx["level"], ctx["detail"]
    rig.add_bones(armature, _ear_bones(armature))
    segments = max(8, int(round(18 * detail)))
    part = common.Part("Ears", "always")
    profile = EAR_PROFILES[level]
    inside = EAR_INSIDE[level]
    n = len(profile)
    fractions = []
    for side, sign in (("L", 1.0), ("R", -1.0)):
        path = sweep.spline(ear_guide(armature, sign), segments)
        # Stations bunch towards the tip, where the outline curves fastest.
        stations = [1.0 - (1.0 - i / segments) ** 1.5 for i in range(segments)]
        back = -_mirror(EAR_FRONT, sign)
        _tangent, across, outward = sweep.frames(path, facing=back)
        rings = []
        for t in stations:
            at = t * segments
            i, f = min(int(at), segments - 1), at - min(int(at), segments - 1)
            centre = path[i] * (1 - f) + path[i + 1] * f
            a = across[i] * (1 - f) + across[i + 1] * f
            o = outward[i] * (1 - f) + outward[i + 1] * f
            half = EAR_HALF_WIDTH * float(_ear_width(t))
            rings.append(part.verts([centre + a * (x * half * sign) + o * (y * half * EAR_DEPTH) for x, y in profile]))
            fractions.append([(side, t)] * n)

        def swatch(r, s):
            t = stations[r]
            # The pink starts above the root and stops short of the tip; the ear narrows there, so it ends in a point.
            if 0.12 < t < 0.88:
                if s in inside:
                    return "ear-inner"
                if s in EAR_WALLS[level]:
                    return "hair-shade"
            return "hair"

        part.loft(rings, swatch, flip=sign < 0)
        tip = part.vert(path[-1])
        fractions.append([(side, 1.0)])
        for s in range(n):
            triangle = (rings[-1][s], rings[-1][(s + 1) % n], tip)
            part.face(triangle[::-1] if sign < 0 else triangle, "hair")

        # Fur at the root: a ring of short tufts leaning out from the base of the ear.
        root, lean = path[0], path[2] - path[0]
        lean = lean / np.linalg.norm(lean)
        tufts = 7 if level == "full" else 3
        for k in range(tufts):
            angle = 2.0 * math.pi * (k + 0.5) / tufts
            out = across[0] * math.cos(angle) + outward[0] * math.sin(angle)
            # Kept short and leaning out, so the tufts stay under the hat's brim.
            start = root + lean * 0.004 + out * 0.016
            end = start + lean * (0.018 + 0.006 * math.sin(k * 2.4)) + out * 0.026
            before = len(part.co)
            sweep.strand(part, [start, (start + end) / 2 + out * 0.006, end], [0.011, 0.010, 0.002], 0.7,
                         3 if level == "full" else 2, level, "hair", "hair-shade", facing=out)
            fractions.append([(side, 0.0)] * (len(part.co) - before))
    obj = part.to_object(ctx["collection"], armature, ctx["material"], ctx["palette"], ctx["tiles"], sharp_angle=42.0)

    flat = [entry for group in fractions for entry in group]
    count = len(obj.data.vertices)
    if len(flat) != count:
        raise RuntimeError(f"ears: {count} vertices but {len(flat)} weights")
    table = {"Head": np.zeros(count)}
    for side in "LR":
        for i in range(3):
            table[f"Ear{i + 1}.{side}"] = np.zeros(count)
    for index, (side, fraction) in enumerate(flat):
        # Each bone takes over from the one below it across a short blend around its joint.
        take = [float(smoothstep(joint - 0.07, joint + 0.07, fraction)) for joint in EAR_JOINTS[:3]]
        table["Head"][index] = 1.0 - take[0]
        table[f"Ear1.{side}"][index] = take[0] * (1.0 - take[1])
        table[f"Ear2.{side}"][index] = take[1] * (1.0 - take[2])
        table[f"Ear3.{side}"][index] = take[2]
    common.set_weights(obj, table)
    return obj


def build_tail(ctx):
    armature, level, detail = ctx["armature"], ctx["level"], ctx["detail"]
    hips = np.array(rig.head_of(armature, "Hips"))
    # Root on the small of the back, where the shorts' seat is.
    tree = common.bvh_of(ctx["skin"])
    height = hips[2] - 0.020
    hit = tree.ray_cast(Vector((0.0, 0.5, height)), Vector((0.0, -1.0, 0.0)), 1.0)
    if hit[0] is None:
        raise RuntimeError("tail: could not find the back of the hips")
    root = np.array(hit[0])
    guide = root + TAIL_GUIDE
    segments = max(5, int(round(9 * detail)))
    around = max(6, int(round(12 * detail / 2)) * 2)
    path = sweep.spline(guide, segments)
    radii = sweep.resample(TAIL_RADII, segments)
    # "Outward" is the tail's upper side.
    tangent, across, outward = sweep.frames(path, facing=(0.0, -0.45, 1.0))

    part = common.Part("Tail", "always")
    rings = []
    for i in range(segments + 1):
        ring = []
        for k in range(around):
            angle = 2.0 * math.pi * k / around
            ring.append(path[i] + across[i] * (math.cos(angle) * radii[i] * TAIL_FLATTEN[0])
                        + outward[i] * (math.sin(angle) * radii[i] * TAIL_FLATTEN[1]))
        rings.append(part.verts(ring))
    # Darker on top, in the hair's shade; pale underneath, as on a rabbit.
    part.loft(rings, lambda r, k: "hair-shade" if k < around // 2 else "ear-fur")
    tip = path[-1] + (path[-1] - path[-2]) * 0.6
    part.fan(rings[-1], tip, "ear-fur")
    for fraction, lean, width in TAIL_TUFTS:
        i = min(segments - 1, int(round(fraction * segments)))
        sideways = across[i] * lean if lean else outward[i]
        start = path[i] + sideways * (radii[i] * 0.7)
        reach = sideways * 0.022 + tangent[i] * 0.036
        sweep.strand(part, [start, start + reach * 0.55 + tangent[i] * 0.006, start + reach], [width, width * 0.75, 0.002], 0.7,
                     2, level, "hair-shade" if not lean else "hair", "ear-fur", facing=outward[i])
    obj = part.to_object(ctx["collection"], armature, ctx["material"], ctx["palette"], ctx["tiles"], sharp_angle=50.0)

    middle = path[len(path) // 2]
    rig.add_bones(armature, [
        ("Tail1", path[0] + (path[1] - path[0]) * 0.3, middle, "Hips", (0.0, 0.0, 1.0)),
        ("Tail2", middle, tip, "Tail1", (0.0, 0.0, 1.0)),
    ])
    co = common.coords(obj.data)
    along = (co - path[0]) @ ((tip - path[0]) / np.linalg.norm(tip - path[0])) / np.linalg.norm(tip - path[0])
    first = smoothstep(0.0, 0.22, along)
    second = smoothstep(0.42, 0.62, along)
    common.set_weights(obj, {"Hips": 1.0 - first, "Tail1": first * (1.0 - second), "Tail2": first * second})
    return obj
