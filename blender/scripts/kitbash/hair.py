"""Wavy hair in two lengths: a scalp cap, a swept fringe, and curtains of hair hanging round the head.

The cap is a dome over the scalp. The fringe is a few broad locks swept
along guides: each guide is a handful of control points in metres from the
centre of the skull (x to the character's left, y to the back, z up), with
a half-width at each point. Points that would sink into the head are lifted
onto its surface, so a guide only has to say roughly where a lock goes.

The lengths are not separate locks, which cut through one another wherever
they overlap, but curtains: one sheet each, running round the head from in
front of one ear to in front of the other, corrugated into locks and cut
into points along its hem, with the blue inner layer as its inside face.
There are two sets, one to the shoulders and one to the middle of the back.
The long set is three curtains, because long hair has to pass the
shoulders: one falls down the back and one forward over each side of the
chest.

The cap, the fringe and the locks in front of the ears are on the `always`
tile. The short lengths are on `hair.short` and the long ones on
`hair.long`, so the two can be exchanged; only one is meant to be shown at
a time.

The fringe's guides are stored in the .blend as curves in the `Guides`
collection (not exported), to look at or to model over.

Physics: the hanging parts of the curtains are weighted to four chains
under `HairRoot` (`HairSide`, three bones, and `HairBack`, four, on each
side); the fringe and the cap follow the head. The short lengths end on the
second bone of each chain.
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

# The parting runs back from the hairline to the whorl, a little to the character's right.
PART_X = -0.030
WHORL = (PART_X * 0.5, 0.034, 0.146)

# Fringe: (control points, half-widths, height). The first point of each is its root, set down
# on the scalp beside the parting, on the side the lock falls to, so that no two roots share a
# place. The height is how far above the head the rest of the lock rides; locks that cross are
# a lock's thickness apart in height, so one lies over the other instead of cutting through it.
# The forehead shows between the two sides, as an upturned V under the parting.
FRINGE = [
    # The long sweep across the forehead to the character's left, flicking out past the temple.
    ([(-0.016, -0.074, 0.138), (0.034, -0.142, 0.100), (0.086, -0.136, 0.052), (0.132, -0.100, 0.006), (0.176, -0.066, -0.018)],
     [0.018, 0.036, 0.037, 0.026, 0.004], 0.030),
    # Under it, a shorter piece that stops over the left brow.
    ([(-0.018, -0.086, 0.133), (0.022, -0.152, 0.088), (0.060, -0.150, 0.050), (0.088, -0.138, 0.022)],
     [0.016, 0.028, 0.025, 0.003], 0.016),
    # To the right of the parting: a sweep down to the right temple, turning out at its end.
    ([(-0.044, -0.074, 0.136), (-0.078, -0.134, 0.094), (-0.112, -0.114, 0.048), (-0.138, -0.084, 0.000), (-0.166, -0.062, -0.034)],
     [0.018, 0.032, 0.032, 0.023, 0.004], 0.028),
    # Under that, a short piece over the right brow.
    ([(-0.042, -0.086, 0.132), (-0.052, -0.150, 0.088), (-0.076, -0.148, 0.054), (-0.090, -0.138, 0.028)],
     [0.014, 0.024, 0.021, 0.003], 0.016),
    # Locks in front of each ear, down to the jaw, waved.
    ([(0.050, -0.052, 0.130), (0.116, -0.076, 0.072), (0.142, -0.060, 0.000), (0.132, -0.070, -0.070), (0.150, -0.076, -0.128)],
     [0.016, 0.027, 0.027, 0.021, 0.003], 0.018),
    ([(-0.072, -0.052, 0.126), (-0.122, -0.070, 0.070), (-0.143, -0.056, 0.000), (-0.134, -0.068, -0.066), (-0.148, -0.078, -0.120)],
     [0.016, 0.027, 0.027, 0.021, 0.003], 0.018),
]

# The curtains start this far round from straight ahead, just in front of the ears, on each side.
CURTAIN_FRONT = 62.0
# Each length: how far below the skull centre the tips hang, how many waves the hair makes on
# the way down and how far they swing it (degrees round the head), how far the tips flick out,
# how deeply the hem is cut into points, and its curtains: (from, to) in degrees round the
# head, clockwise seen from above from straight ahead, the number of points along the hem,
# and where the curtain goes.
LENGTHS = {
    "short": {"tile": "hair.short", "length": 0.235, "waves": 0.8, "swing": 5.0, "flick": 0.028, "notch": 0.24,
              "rows": {"full": 7, "lite": 3},
              "curtains": ((CURTAIN_FRONT, 360.0 - CURTAIN_FRONT, 9, "round"),)},
    "long": {"tile": "hair.long", "length": 0.495, "waves": 1.9, "swing": 7.0, "flick": 0.030, "notch": 0.16,
             "rows": {"full": 13, "lite": 5},
             "curtains": ((CURTAIN_FRONT, 114.0, 3, "chest"), (114.0, 246.0, 6, "back"),
                          (246.0, 360.0 - CURTAIN_FRONT, 3, "chest"))},
}
CURTAIN_THICKNESS = 0.013
CORRUGATION = 0.007       # how far the middle of each lock stands out from the grooves between them
BODY_CLEARANCE = 0.016

# The chains: the bearing of each joint and its height from the skull centre.
BONES = {
    "Side": ((82.0, -0.060), (82.0, -0.150), (72.0, -0.235), (60.0, -0.345)),
    "Back": ((150.0, -0.060), (150.0, -0.150), (150.0, -0.235), (152.0, -0.350), (155.0, -0.480)),
}
BONE_REACH = 0.135


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


def _clear_body(point, centre, body, clearance):
    """Moves a point (relative to `centre`) out of the body and its clothes, to `clearance` off them."""
    world = np.array(point, dtype=np.float64) + centre
    for tree in body:
        location, normal, _index, _distance = tree.find_nearest(Vector(world), 0.25)
        if location is None:
            continue
        height = (Vector(world) - location).dot(normal)
        if height < clearance:
            # Sideways only, so the hair keeps its length.
            push = np.array(normal) * (clearance - height)
            push[2] = 0.0
            world = world + push * 1.2
    return world - centre


def _curtain(part, skull, level, spec, start, end, teeth, course, body):
    """One sheet of hanging hair between two bearings. Returns the bearing of each vertex it adds."""
    full = level == "full"
    per_tooth = 6 if full else 2
    columns = teeth * per_tooth + 1
    polars = (46.0, 60.0, 74.0) if full else (56.0,)
    rows = spec["rows"][level]
    long = course != "round"
    bearings = np.linspace(start, end, columns)

    # The head's outline at ear height, evened out round the head: the face mesh has ears.
    # It has to pass outside them, so the widest point between the temple and the jaw counts,
    # and what its neighbours measure counts for each bearing too.
    measured = np.array([max(np.linalg.norm(skull.on_surface(_direction(b) + np.array((0.0, 0.0, tilt)), STRAND_OFFSET)[:2])
                             for tilt in (0.05, -0.12, -0.28, -0.45)) for b in bearings])
    spread = 2 if full else 1
    reach = np.array([measured[max(0, i - spread):i + spread + 1].max() for i in range(columns)])
    for _ in range(2 if full else 1):
        reach[1:-1] = (reach[:-2] + 2.0 * reach[1:-1] + reach[2:]) / 4.0
    # A coarse curtain is flat between its few columns, and passes inside what a round one clears.
    reach = np.maximum(reach, measured) + (0.0 if full else 0.007)

    outer = []          # rows of points, top to hem
    for index, polar in enumerate(polars):
        p = math.radians(polar)
        # It starts flush with the cap and stands off it more and more on its way down the head.
        clearance = CAP_OFFSET + 0.0015 + (STRAND_OFFSET - CAP_OFFSET) * (index + 1) / (len(polars) + 1)
        outer.append([skull.on_surface(_direction(b) * math.sin(p) + np.array((0.0, 0.0, math.cos(p))), clearance) for b in bearings])
    outer.append([np.array((*(_direction(b)[:2] * r), 0.008)) for b, r in zip(bearings, reach)])
    hanging = len(outer) - 1

    for row in range(1, rows + 1):
        f = row / rows
        ring = []
        for column, (bearing, radius) in enumerate(zip(bearings, reach)):
            tooth = column // per_tooth
            # 0 in the middle of a lock, 1 in the groove between two.
            groove = abs(2.0 * ((column % per_tooth) / per_tooth) - 1.0)
            length = spec["length"] * (1.0 + 0.05 * math.sin(tooth * 2.4 + start)) * (1.0 - spec["notch"] * groove ** 0.7)
            if course == "chest":
                length *= 0.86
            z = -length * f
            # Waves: the whole curtain swings a little one way and then the other on its way down.
            swing = spec["swing"] * math.sin(2.0 * math.pi * spec["waves"] * f + math.radians(bearing) * 1.3) * min(1.0, f * 2.5)
            turned = bearing
            if course == "chest":
                # Round to the front of the shoulder, to fall on the chest.
                side = 1.0 if bearing < 180.0 else -1.0
                home = bearing if side > 0 else 360.0 - bearing
                goal = home * 0.45 + 26.0
                # The curtains part below the ear and are apart by the shoulder.
                turned = home + (goal - home) * float(smoothstep(0.17, 0.46, f))
                turned = turned if side > 0 else 360.0 - turned
                radius = radius * (1.0 - 0.06 * float(smoothstep(0.1, 0.5, f)))
            elif course == "back":
                # Behind the shoulders, spreading as it falls.
                goal = 180.0 + (bearing - 180.0) * 0.80
                goal = min(max(goal, 126.0), 234.0)
                turned = bearing + (goal - bearing) * float(smoothstep(0.17, 0.46, f))
                radius = radius * (1.0 + 0.30 * f)
            tip = float(smoothstep(0.72, 1.0, f))
            radius += CORRUGATION * (1.0 - 2.0 * groove) * min(1.0, f * 2.0 + 0.25)
            radius += spec["flick"] * tip ** 1.6 * (1.0 - 0.6 * groove)
            direction = _direction(turned + swing)
            point = np.array((direction[0] * radius, direction[1] * radius, z + 0.012 * tip ** 2))
            if body is not None:
                point = _clear_body(point, skull.centre, body, BODY_CLEARANCE)
            ring.append(point)
        outer.append(ring)

    # The inside face, in the inner colour: the same sheet a thickness nearer the head, thinning to nothing at the hem.
    inner = []
    for row in range(hanging, len(outer) - 1):
        f = (row - hanging) / rows
        thickness = CURTAIN_THICKNESS * (1.0 - 0.75 * f)
        ring = []
        for point in outer[row]:
            flat = np.array((point[0], point[1], 0.0))
            inward = point - flat / max(np.linalg.norm(flat), 1e-9) * thickness
            if body is not None and row > hanging:
                inward = _clear_body(inward, skull.centre, body, 0.004)
            ring.append(inward)
        inner.append(ring)

    first = len(part.co)
    centre = skull.centre
    outer_ids = [part.verts([centre + q for q in ring]) for ring in outer]
    inner_ids = [part.verts([centre + q for q in ring]) for ring in inner] + [outer_ids[-1]]
    tile = spec["tile"]
    part.loft(outer_ids, "hair", closed=False, tile=tile)
    part.loft(inner_ids, "hair-inner", closed=False, flip=True, tile=tile)
    # Its two edges, where it has a thickness.
    for column, flip in ((0, True), (columns - 1, False)):
        for row in range(len(inner_ids) - 1):
            quad = (outer_ids[hanging + row][column], outer_ids[hanging + row + 1][column],
                    inner_ids[row + 1][column], inner_ids[row][column])
            if len(set(quad)) == 4:
                part.face(quad[::-1] if flip else quad, "hair-shade", tile)
            else:
                part.face(tuple(dict.fromkeys(quad[::-1] if flip else quad)), "hair-shade", tile)
    per_vertex = [float(b) for _ring in outer for b in bearings] + [float(b) for _ring in inner for b in bearings]
    if len(per_vertex) != len(part.co) - first:
        raise RuntimeError("hair: a curtain's vertices and bearings are out of step")
    return per_vertex


def bone_table(armature):
    """The hair bones as rig.add_bones rows: HairRoot under Head, then the chains."""
    centre = skull_centre(armature)
    rows = [("HairRoot", centre, centre + (0.0, 0.0, 0.05), "Head", (0.0, -1.0, 0.0))]
    for stem, joints in BONES.items():
        for side, sign in (("L", 1.0), ("R", -1.0)):
            places = [centre + _direction(azimuth) * (sign, 1.0, 1.0) * BONE_REACH + (0.0, 0.0, z) for azimuth, z in joints]
            roll = tuple(-_direction(joints[0][0]) * (sign, 1.0, 1.0))
            for number in range(1, len(joints)):
                parent = "HairRoot" if number == 1 else f"Hair{stem}{number - 1}.{side}"
                rows.append((f"Hair{stem}{number}.{side}", places[number - 1], places[number], parent, roll))
    return rows


def _weights(co, centre, owners):
    """Hair weights: the head above the ears, and below them the chains nearest the vertex's place round the head.

    `owners` holds, per vertex, its bearing round the head as the hair grows
    (not where a long curtain has since swung it to), or None for the cap
    and the fringe.
    """
    relative = co - centre
    table = {"Head": np.ones(len(co))}
    for stem, joints in BONES.items():
        for side in "LR":
            for number in range(1, len(joints)):
                table[f"Hair{stem}{number}.{side}"] = np.zeros(len(co))
    for index, bearing in enumerate(owners):
        if bearing is None:
            continue
        z = relative[index, 2]
        # Left and right meet down the middle of the back across a blend, so the curtain does not tear there.
        left = float(smoothstep(200.0, 160.0, bearing))
        from_front = bearing if bearing <= 180.0 else 360.0 - bearing
        back = float(smoothstep(108.0, 124.0, from_front))
        hanging = 1.0 - float(smoothstep(BONES["Side"][0][1] - 0.035, BONES["Side"][0][1] + 0.025, z))
        table["Head"][index] = 1.0 - hanging
        for stem, share in (("Side", 1.0 - back), ("Back", back)):
            if share <= 0.0:
                continue
            joints = BONES[stem]
            count = len(joints) - 1
            # Each bone takes over from the one above it across a short blend round its joint.
            take = [1.0 - float(smoothstep(joints[k][1] - 0.03, joints[k][1] + 0.03, z)) for k in range(1, count)]
            carried = hanging * share
            for number in range(1, count + 1):
                passed = take[number - 1] if number <= len(take) else 0.0
                for side, part in (("L", left), ("R", 1.0 - left)):
                    table[f"Hair{stem}{number}.{side}"][index] += carried * (1.0 - passed) * part
                carried *= passed
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
    # What long hair has to hang clear of: the body, and the sweater over it.
    body = [common.bvh_of(ctx["skin"])] + ([common.bvh_of(ctx["sweater"])] if ctx.get("sweater") is not None else [])

    part = common.Part("Hair", "always")
    _cap(part, skull, detail)
    segments = max(6, int(round(16 * detail * detail + 2)))
    owners = [None] * len(part.co)
    guides = []

    for points, widths, clearance in FRINGE:
        lifted = [skull.settle(points[0], 0.003)] + [skull.lift(p, clearance) for p in points[1:]]
        sweep.strand(part, [centre + p for p in lifted], widths, 0.20, max(5, segments - 4), level, "hair", "hair-shade",
                     away_from=centre)
        guides.append((lifted, widths))
    owners.extend([None] * (len(part.co) - len(owners)))

    for name, spec in LENGTHS.items():
        for start, end, teeth, course in spec["curtains"]:
            owners.extend(_curtain(part, skull, level, spec, start, end, teeth, course, body if name == "long" else None))
    _store_guides(guides, centre)

    # Fit the hair to the hat: nothing may stand through the crown or the brim.
    from . import hat
    part.co = [tuple(position) for position in hat.tuck(part.co, centre)]

    removed = trim_scalp(ctx["head"], centre)
    print(f"hair: {len(guides)} fringe locks and {sum(len(spec['curtains']) for spec in LENGTHS.values())} curtains; removed {removed} hidden scalp faces from the head")
    obj = part.to_object(ctx["collection"], armature, ctx["material"], ctx["palette"], ctx["tiles"], sharp_angle=40.0)
    if len(owners) != len(obj.data.vertices):
        raise RuntimeError(f"hair: {len(obj.data.vertices)} vertices but {len(owners)} weights")
    common.set_weights(obj, _weights(common.coords(obj.data), centre, owners))
    return obj
