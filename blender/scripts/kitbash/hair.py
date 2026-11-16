"""Shoulder-length wavy hair: a scalp cap with swept strands over it.

The guides below are the hairstyle. Each is a handful of control points in
metres from the centre of the skull (x to the character's left, y to the
back, z up), with a half-width at each point. Points that would sink into
the head are lifted onto its surface, so a guide only has to say roughly
where a strand goes. Back and side strands are generated around the head
from a few numbers instead of being listed one by one.

The same guides are stored in the .blend as curves in the `Guides`
collection (not exported), to look at or to model over.

Physics: the hanging parts of the back and side strands are weighted to four
two-bone chains under `HairRoot`; the fringe and the cap follow the head.
"""

import math

import bmesh
import bpy
import numpy as np
from mathutils import Vector

from . import common, face, rig, sweep
from .common import smoothstep

CAP_OFFSET = 0.011
STRAND_OFFSET = 0.016
# Hairline height (z from the skull centre) by how far back a point is (y from the skull centre).
HAIRLINE = ((-0.20, 0.074), (-0.08, 0.068), (-0.04, 0.036), (0.0, 0.024), (0.060, 0.024), (0.090, -0.060), (0.16, -0.100))

# Fringe, from a parting just right of centre. (control points, half-widths). The first point of
# each is its root, which is set down on the scalp; later strands lie over earlier ones.
FRINGE = [
    # Short pieces under everything else, so no forehead shows between the longer ones.
    ([(-0.020, -0.090, 0.130), (0.020, -0.150, 0.090), (0.040, -0.156, 0.058), (0.050, -0.156, 0.036)],
     [0.020, 0.030, 0.024, 0.003]),
    ([(-0.045, -0.085, 0.128), (-0.082, -0.128, 0.088), (-0.100, -0.126, 0.056), (-0.106, -0.124, 0.030)],
     [0.018, 0.028, 0.022, 0.003]),
    ([(0.030, -0.080, 0.132), (0.090, -0.118, 0.092), (0.118, -0.108, 0.058), (0.130, -0.100, 0.030)],
     [0.018, 0.028, 0.022, 0.003]),
    # The long sweep across the forehead to the character's left, flicking out at the temple.
    ([(-0.020, -0.075, 0.138), (0.030, -0.140, 0.100), (0.085, -0.135, 0.050), (0.128, -0.100, 0.008), (0.168, -0.070, -0.012)],
     [0.020, 0.036, 0.034, 0.026, 0.004]),
    ([(-0.025, -0.080, 0.136), (0.005, -0.150, 0.090), (0.045, -0.150, 0.045), (0.082, -0.135, 0.012), (0.105, -0.128, -0.014)],
     [0.018, 0.030, 0.028, 0.020, 0.003]),
    # To the right of the parting: shorter pieces that fall towards the right temple.
    ([(-0.030, -0.078, 0.137), (-0.060, -0.135, 0.095), (-0.100, -0.115, 0.050), (-0.128, -0.085, 0.000), (-0.142, -0.080, -0.045)],
     [0.018, 0.032, 0.030, 0.022, 0.003]),
    ([(-0.028, -0.082, 0.135), (-0.040, -0.150, 0.088), (-0.062, -0.150, 0.048), (-0.070, -0.146, 0.018)],
     [0.014, 0.024, 0.020, 0.003]),
    # Locks in front of each ear, down to the jaw.
    ([(0.060, -0.060, 0.128), (0.118, -0.075, 0.070), (0.140, -0.062, 0.000), (0.136, -0.066, -0.075), (0.150, -0.075, -0.125)],
     [0.016, 0.026, 0.026, 0.020, 0.003]),
    ([(-0.065, -0.060, 0.126), (-0.120, -0.070, 0.070), (-0.141, -0.058, 0.000), (-0.138, -0.064, -0.070), (-0.128, -0.078, -0.118)],
     [0.016, 0.026, 0.026, 0.020, 0.003]),
]

FRINGE_UNDERLAYER = 3     # how many of the first FRINGE entries are the short pieces underneath

# Back and side strands: azimuths in degrees from straight ahead, per level (mirrored, plus one at 180).
AZIMUTHS = {"full": (64, 82, 100, 118, 136, 153, 168), "lite": (70, 105, 142)}
INNER_AZIMUTHS = {"full": (118, 150), "lite": (125,)}
WHORL = (0.0, 0.030, 0.146)
LENGTH = 0.235            # how far below the skull centre the tips hang

BONES = {"Side": 82.0, "Back": 150.0}
BONE_HEIGHTS = (-0.060, -0.150, -0.235)


def _direction(azimuth):
    a = math.radians(azimuth)
    return np.array((math.sin(a), -math.cos(a), 0.0))


class Skull:
    """Distances from the skull's centre to the head's surface."""

    def __init__(self, head, centre):
        self.centre = np.asarray(centre, dtype=np.float64)
        self.tree = common.bvh_of(head)

    def radius(self, direction):
        direction = np.asarray(direction, dtype=np.float64)
        direction = direction / np.linalg.norm(direction)
        hit = self.tree.ray_cast(Vector(self.centre + direction * 0.4), Vector(-direction), 0.4)
        return 0.4 - hit[3] if hit[0] is not None else 0.0

    def settle(self, point, clearance):
        """`point` (relative to the centre) set down at `clearance` above the surface, wherever it was."""
        return self.on_surface(point, clearance)

    def lift(self, point, clearance):
        """`point` (relative to the centre) pushed out to at least `clearance` above the surface."""
        point = np.asarray(point, dtype=np.float64)
        distance = np.linalg.norm(point)
        surface = self.radius(point)
        return point / distance * max(distance, surface + clearance) if distance > 1e-9 else point

    def on_surface(self, direction, clearance):
        direction = np.asarray(direction, dtype=np.float64)
        direction = direction / np.linalg.norm(direction)
        return direction * (self.radius(direction) + clearance)


def skull_centre(armature):
    joint = np.array(rig.head_of(armature, "Head"))
    crown = rig.tail_of(armature, "Head").z
    return np.array((0.0, joint[1] - 0.016, joint[2] + (crown - joint[2]) * 0.51))


def _hairline(y):
    ys, zs = zip(*HAIRLINE)
    return np.interp(y, ys, zs)


def _cap(part, skull, detail):
    """A dome over the scalp, from the whorl down to the hairline."""
    segments = max(12, int(round(24 * detail / 2)) * 2)
    rings = max(4, int(round(7 * detail)))
    top = skull.on_surface((0.0, 0.0, 1.0), CAP_OFFSET)
    grid = []
    for r in range(1, rings + 1):
        ring = []
        for s in range(segments):
            azimuth = 360.0 * s / segments
            flat = _direction(azimuth)
            # Walk down this meridian to the hairline (a little below it, so strands cover the rim).
            rim_z = None
            for polar in np.linspace(5.0, 150.0, 60):
                p = math.radians(polar)
                point = skull.on_surface(flat * math.sin(p) + np.array((0.0, 0.0, math.cos(p))), CAP_OFFSET)
                if point[2] < _hairline(point[1]) - 0.004:
                    rim_z = polar
                    break
            rim = math.radians(rim_z if rim_z is not None else 150.0)
            p = rim * (r / rings) ** 0.85
            ring.append(part.vert(skull.centre + skull.on_surface(flat * math.sin(p) + np.array((0.0, 0.0, math.cos(p))), CAP_OFFSET)))
        grid.append(ring)
    part.fan(grid[0], skull.centre + top, "hair")
    part.loft(grid, "hair")


def _hanging_guide(skull, azimuth, index, inner=False):
    """A strand from the whorl over the head and down to the shoulders."""
    flat = _direction(azimuth)
    vary = math.sin(index * 2.399)          # deterministic variation between strands
    clearance = (0.006 if inner else STRAND_OFFSET) + 0.004 * (index % 2)
    points, widths = [], []
    if not inner:
        points.append(np.array(WHORL) + flat * 0.012)
        widths.append(0.012)
        for polar, width in ((32.0, 0.034), (62.0, 0.044)):
            p = math.radians(polar)
            points.append(skull.on_surface(flat * math.sin(p) + np.array((0.0, 0.0, math.cos(p))), clearance))
            widths.append(width)
    equator = skull.on_surface(flat + np.array((0.0, 0.0, 0.05)), clearance)
    reach = np.linalg.norm(equator[:2])
    points.append(equator)
    widths.append(0.050 if inner else 0.042)
    length = LENGTH * (0.94 if inner else 1.0 + 0.10 * vary)
    turn = 1.0 if index % 2 else -1.0
    # Hang with a soft wave, then curl outwards and up at the tip, each strand turning its own way.
    for fraction, bulge, width, curl in ((0.36, 0.985, 0.042, 0.0), (0.66, 1.02 + 0.03 * vary, 0.038, 0.0), (0.86, 1.08, 0.030, 0.1),
                                         (0.96, 1.17, 0.019, 0.5), (1.0, 1.22 + 0.04 * vary, 0.003, 1.0)):
        if inner:
            bulge, curl = 0.90 + 0.06 * fraction, 0.0
            width *= 1.3
        swirl = _direction(azimuth + turn * (4.0 * fraction + 9.0 * curl))
        points.append(np.array((swirl[0] * reach * bulge, swirl[1] * reach * bulge, -length * fraction + 0.016 * curl)))
        widths.append(width)
    return points, widths


def bone_table(armature):
    """The hair bones as rig.add_bones rows: HairRoot under Head, then four two-bone chains."""
    centre = skull_centre(armature)
    rows = [("HairRoot", centre, centre + (0.0, 0.0, 0.05), "Head", (0.0, -1.0, 0.0))]
    for stem, azimuth in BONES.items():
        for side, sign in (("L", 1.0), ("R", -1.0)):
            flat = _direction(azimuth) * (sign, 1.0, 1.0)
            joints = [centre + flat * 0.135 + (0.0, 0.0, z) for z in BONE_HEIGHTS]
            rows.append((f"Hair{stem}1.{side}", joints[0], joints[1], "HairRoot", tuple(-flat)))
            rows.append((f"Hair{stem}2.{side}", joints[1], joints[2], f"Hair{stem}1.{side}", tuple(-flat)))
    return rows


def _weights(co, centre):
    """Hair weights by position: the head above the ears, the nearest chain below."""
    relative = co - centre
    azimuth = np.degrees(np.arctan2(np.abs(relative[:, 0]), -relative[:, 1]))
    left = relative[:, 0] >= 0.0
    hanging = 1.0 - smoothstep(BONE_HEIGHTS[0] - 0.035, BONE_HEIGHTS[0] + 0.025, relative[:, 2])
    lower = 1.0 - smoothstep(BONE_HEIGHTS[1] - 0.03, BONE_HEIGHTS[1] + 0.03, relative[:, 2])
    back = smoothstep(108.0, 124.0, azimuth)
    table = {"Head": 1.0 - hanging}
    for stem, share in (("Side", 1.0 - back), ("Back", back)):
        for side, mask in (("L", left), ("R", ~left)):
            table[f"Hair{stem}1.{side}"] = hanging * (1.0 - lower) * share * mask
            table[f"Hair{stem}2.{side}"] = hanging * lower * share * mask
    return table


def _store_guides(guides, centre):
    """Keeps the guides in the file as poly curves, for reference and for modelling over."""
    collection = bpy.data.collections.get("Guides") or bpy.data.collections.new("Guides")
    if collection.name not in bpy.context.scene.collection.children:
        bpy.context.scene.collection.children.link(collection)
    curve = bpy.data.curves.new("HairGuides", "CURVE")
    curve.dimensions = "3D"
    for points, widths in guides:
        path = sweep.spline(points, 12) + centre
        radii = sweep.resample(widths, 12)
        polyline = curve.splines.new("POLY")
        polyline.points.add(len(path) - 1)
        for point, position, radius in zip(polyline.points, path, radii):
            point.co = (*position, 1.0)
            point.radius = radius
    collection.objects.link(bpy.data.objects.new("HairGuides", curve))
    collection.hide_render = True


def trim_scalp(head, centre):
    """Removes the head's skin under the hair. It is never seen, and the face mesh pays for every vertex in each shape key."""
    mesh = head.data
    classes = face.face_classes(mesh)
    co = common.coords(mesh) - centre
    covered = co[:, 2] > _hairline(co[:, 1]) + 0.022
    bm = bmesh.new()
    bm.from_mesh(mesh)
    bm.faces.ensure_lookup_table()
    doomed = [f for f in bm.faces if classes[f.index] == face.SKIN and all(covered[v.index] for v in f.verts)]
    bmesh.ops.delete(bm, geom=doomed, context="FACES")
    bm.to_mesh(mesh)
    bm.free()
    mesh.update()
    return len(doomed)


def build_hair(ctx):
    armature, level, detail = ctx["armature"], ctx["level"], ctx["detail"]
    centre = skull_centre(armature)
    skull = Skull(ctx["head"], centre)
    rig.add_bones(armature, bone_table(armature))

    part = common.Part("Hair", "always")
    _cap(part, skull, detail)
    segments = max(6, int(round(16 * detail * detail + 2)))

    guides = []
    # The lite level leaves out the short underlayer of the fringe.
    fringe = FRINGE if level == "full" else FRINGE[FRINGE_UNDERLAYER:]
    for layer, (points, widths) in enumerate(fringe):
        # Each strand rides a little higher than the one before, so they overlap instead of cutting through each other.
        clearance = 0.010 + 0.0055 * layer
        lifted = [skull.settle(points[0], 0.002)] + [skull.lift(p, clearance) for p in points[1:]]
        guides.append((lifted, widths))
    fringe_count = len(guides)
    azimuths = [180.0] + [sign * a for a in AZIMUTHS[level] for sign in (1.0, -1.0)]
    for index, azimuth in enumerate(azimuths):
        guides.append(_hanging_guide(skull, azimuth, index))
    outer_count = len(guides)
    inner = [180.0] + [sign * a for a in INNER_AZIMUTHS[level] for sign in (1.0, -1.0)]
    for index, azimuth in enumerate(inner):
        guides.append(_hanging_guide(skull, azimuth, index + 3, inner=True))

    for index, (points, widths) in enumerate(guides):
        world = [centre + p for p in points]
        is_inner = index >= outer_count
        sweep.strand(part, world, widths, 0.46 if index < fringe_count else 0.42,
                     segments if index >= fringe_count else max(5, segments - 4), level,
                     "hair-inner" if is_inner else "hair", "hair-inner" if is_inner else "hair-shade",
                     away_from=centre, root_cap=is_inner)
    _store_guides(guides, centre)

    removed = trim_scalp(ctx["head"], centre)
    print(f"hair: {len(guides)} strands; removed {removed} hidden scalp faces from the head")
    obj = part.to_object(ctx["collection"], armature, ctx["material"], ctx["palette"], ctx["tiles"], sharp_angle=40.0)
    common.set_weights(obj, _weights(common.coords(obj.data), centre))
    return obj
