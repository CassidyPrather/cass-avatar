"""Rabbit ears and tail.

The ears are long, upright and open to the front, on three-bone chains that
physics and the gesture expressions both move. They root on the upper sides
of the skull, wide enough apart to pass the hat's crown and come up through
its brim (hat.py cuts the holes from `ear_axes`).

The tail is a scut: short, tapered and turned up, pale underneath, ending in
a few tufts. Not a pom-pom.
"""

import math

import numpy as np
from mathutils import Vector

from . import common, hair, rig, sweep
from .common import smoothstep

# Left ear, in metres from the skull's centre: where it roots, and the path to its tip.
EAR_ROOT = np.array((0.110, 0.014, 0.098))
EAR_GUIDE = np.array(((-0.004, -0.001, -0.022), (0.0, 0.0, 0.0), (0.012, 0.005, 0.095), (0.034, 0.016, 0.200), (0.058, 0.032, 0.300)))
EAR_WIDTHS = (0.021, 0.025, 0.042, 0.040, 0.013)
EAR_THICKNESS = 0.34
# The ear's open side faces this way (left ear); the right ear mirrors it.
EAR_FRONT = np.array((0.30, -0.95, 0.0))
EAR_JOINTS = (0.085, 0.36, 0.66, 1.0)     # fractions of the path where Ear1, Ear2, Ear3 start, and the tip

# The tail's centre line from where it roots on the back (x left, y back, z up), and its radius along it.
TAIL_GUIDE = np.array(((0.0, -0.022, -0.012), (0.0, 0.034, 0.004), (0.0, 0.066, 0.050), (0.0, 0.078, 0.108), (0.0, 0.070, 0.160)))
TAIL_RADII = (0.020, 0.036, 0.040, 0.028, 0.008)
TAIL_FLATTEN = (1.30, 0.62)     # wider than it is thick
# Tufts that break up the outline: (fraction along the tail, sideways lean, half-width).
TAIL_TUFTS = ((0.50, 1.0, 0.020), (0.50, -1.0, 0.020), (0.76, 0.75, 0.018), (0.76, -0.75, 0.018))


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
    segments = max(6, int(round(11 * detail)))
    part = common.Part("Ears", "always")
    profile = sweep.PROFILES[level]
    fractions = []
    for side, sign in (("L", 1.0), ("R", -1.0)):
        path = sweep.spline(ear_guide(armature, sign), segments)
        half = sweep.resample(EAR_WIDTHS, segments)
        back = -_mirror(EAR_FRONT, sign)
        _tangent, across, outward = sweep.frames(path, facing=back)
        rings = [part.verts([path[i] + across[i] * (a * half[i]) + outward[i] * (o * half[i] * EAR_THICKNESS) for a, o in profile])
                 for i in range(segments + 1)]
        n = len(profile)
        # The domed back is fur. On the open front, only the middle is the pink inner ear,
        # and only above the root, where the ear has opened up.
        def swatch(r, s):
            inner = s == (4 if level == "full" else None) or (level == "lite" and s in (2, 3))
            return "ear-inner" if inner and 0 < r < segments - 1 else "ear-fur"
        part.loft(rings, swatch, flip=sign < 0)
        tip = part.vert(path[-1] + (path[-1] - path[-2]) * 0.45)
        for s in range(n):
            triangle = (rings[-1][s], rings[-1][(s + 1) % n], tip)
            part.face(triangle[::-1] if sign < 0 else triangle, "ear-fur")
        fractions.extend([(side, i / segments)] * n for i in range(segments + 1))
        fractions.append([(side, 1.0)])
    obj = part.to_object(ctx["collection"], armature, ctx["material"], ctx["palette"], ctx["tiles"], sharp_angle=45.0)

    flat = [entry for group in fractions for entry in group]
    count = len(obj.data.vertices)
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
    segments = max(4, int(round(7 * detail)))
    around = max(6, int(round(10 * detail / 2)) * 2)
    path = sweep.spline(guide, segments)
    radii = sweep.resample(TAIL_RADII, segments)
    _tangent, across, outward = sweep.frames(path, facing=(0.0, -1.0, 0.25))

    part = common.Part("Tail", "always")
    rings = []
    for i in range(segments + 1):
        ring = []
        for k in range(around):
            angle = 2.0 * math.pi * k / around
            ring.append(path[i] + across[i] * (math.cos(angle) * radii[i] * TAIL_FLATTEN[0])
                        + outward[i] * (math.sin(angle) * radii[i] * TAIL_FLATTEN[1]))
        rings.append(part.verts(ring))
    # The side towards the body is fur-coloured and the side shown to whoever follows is white, as on a rabbit.
    part.loft(rings, lambda r, k: "ear-fur" if k < around // 2 else "highlight")
    tip = path[-1] + (path[-1] - path[-2]) * 0.6
    part.fan(rings[-1], tip, "ear-fur")
    tangent = _tangent
    for fraction, lean, width in TAIL_TUFTS:
        i = min(segments - 1, int(round(fraction * segments)))
        start = path[i] + across[i] * (lean * radii[i] * 0.7)
        reach = across[i] * (lean * 0.020) + tangent[i] * 0.034
        sweep.strand(part, [start, start + reach * 0.55 + tangent[i] * 0.006, start + reach], [width, width * 0.75, 0.002], 0.7,
                     2, level, "ear-fur", "highlight", facing=outward[i])
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
