"""The default outfit: sweater, denim shorts and cowboy boots.

The sweater and the shorts are shells cut from the body (see shell.py). The
boots are lofted around the lower leg and foot, measuring the skin as they
go. All lengths are in metres on the finished, scaled figure; anything that
depends on where the body is reads the skeleton.

`detail` is 1.0 for the full level and lower for lite. Shells get their
resolution from the body level they are cut from; `detail` only sets how
finely lofted parts and bands are divided.
"""

import math

import numpy as np
from mathutils import Vector

from . import common, rig
from .common import smoothstep
from .shell import Shell, around_axis, ring_scaled, ring_to_radius

SWEATER_SEGMENTS = ("Chest_01", "Chest_02", "Spine", "Shoulder", "UpperArm", "Elbow", "LowerArm")
SHORTS_SEGMENTS = ("Hips",)


def _mirror(point):
    return (-point[0], point[1], point[2])


def build_sweater(ctx):
    """Oversized crew-neck sweater with ribbed, striped bands."""
    armature = ctx["armature"]
    shoulder = np.array(rig.head_of(armature, "UpperArm.L"))
    wrist = np.array(rig.head_of(armature, "Hand.L"))
    chest = np.array(rig.head_of(armature, "Chest"))
    neck = np.array(rig.head_of(armature, "Neck"))
    armpit = shoulder[2] - 0.065

    shell = Shell(ctx["skin"], SWEATER_SEGMENTS, "sweater")
    shell.inflate(0.010)

    # The body of the sweater hangs as a tube rather than following the waist:
    # wherever the skin is inside this ellipse, the cloth is pushed out to it.
    centre_y = chest[1] + 0.004
    half_depth = 0.120

    def half_width(z):
        return 0.162 + 0.020 * (1.0 - smoothstep(chest[2] - 0.13, armpit, z))

    def drape(co):
        out = co.copy()
        hang = 1.0 - smoothstep(armpit - 0.02, armpit + 0.05, co[:, 2])
        x, y = co[:, 0] / half_width(co[:, 2]), (co[:, 1] - centre_y) / half_depth
        rho = np.maximum(np.sqrt(x * x + y * y), 1e-6)
        grow = np.where(rho < 1.0, 1.0 + (1.0 / rho - 1.0) * hang, 1.0)
        out[:, 0] = co[:, 0] * grow
        out[:, 1] = centre_y + (co[:, 1] - centre_y) * grow

        # Sleeves: loose from the dropped shoulder, widest just before the cuff.
        for sign in (1.0, -1.0):
            a, b = shoulder * (sign, 1, 1), wrist * (sign, 1, 1)
            t, foot, radial = around_axis(out, a, b)
            distance = np.maximum(np.linalg.norm(radial, axis=1), 1e-6)
            loose = 0.052 + 0.024 * smoothstep(0.0, 0.85, t)
            arm = smoothstep(0.02, 0.22, t) * (out[:, 0] * sign > 0)
            push = np.maximum(loose - distance, 0.0) * arm
            out += radial / distance[:, None] * push[:, None]
        return out

    shell.reshape(drape)
    hem = shell.loop_where(lambda c: abs(c[0]) < 0.1 and c[2] < chest[2] - 0.05)
    collar = shell.loop_where(lambda c: abs(c[0]) < 0.05 and c[2] > neck[2])
    cuffs = {sign: shell.loop_where(lambda c, sign=sign: c[0] * sign > 0.4) for sign in (1.0, -1.0)}
    shell.level(hem, (0, 0, 1))
    shell.level(collar)
    shell.even_out(collar, (0.0, neck[1]))
    shell.even_out(hem, (0.0, centre_y))
    for sign, cuff in cuffs.items():
        shell.level(cuff, (sign, 0, 0))
    shell.relax(14)

    for sign, cuff in cuffs.items():
        a, b = shoulder * (sign, 1, 1), wrist * (sign, 1, 1)
        shell.band(cuff, [
            (lambda co, a=a, b=b: ring_to_radius(co, a, b, 0.043, 0.008), "sweater-shade"),
            (lambda co, a=a, b=b: ring_to_radius(co, a, b, 0.042, 0.014), "sweater-stripe"),
            (lambda co, a=a, b=b: ring_to_radius(co, a, b, 0.041, 0.016), "sweater-shade"),
        ])

    axis = (0.0, centre_y)
    shell.band(hem, [
        (lambda co: ring_scaled(co, axis, 1.0, -0.040), "sweater"),
        (lambda co: ring_scaled(co, axis, 0.95, -0.012), "sweater-shade"),
        (lambda co: ring_scaled(co, axis, 1.0, -0.016), "sweater-stripe"),
        (lambda co: ring_scaled(co, axis, 1.0, -0.020), "sweater-shade"),
    ])

    neck_axis = (0.0, neck[1])
    shell.band(collar, [
        # Tall enough to cover the saw-toothed edge where the neck's skin begins.
        (lambda co: ring_scaled(co, neck_axis, 1.0, 0.014), "sweater-shade"),
        (lambda co: ring_scaled(co, neck_axis, 0.96, 0.014), "sweater-shade"),
        (lambda co: ring_scaled(co, neck_axis, 0.95, 0.010), "sweater-shade"),
    ])
    return shell.to_object("Outfit_Sweater", "outfit.default.top", ctx["collection"], armature, ctx["material"],
                           ctx["palette"], ctx["tiles"])


def build_shorts(ctx):
    """Denim short-shorts: waistband, and short legs that end in a pale stitch line and a turned-up hem."""
    armature = ctx["armature"]
    hip = np.array(rig.head_of(armature, "UpperLeg.L"))
    shell = Shell(ctx["skin"], SHORTS_SEGMENTS, "denim")
    shell.inflate(0.008)
    waist = shell.loop_where(lambda c: abs(c[0]) < 0.05 and c[2] > hip[2] + 0.05)
    legs = {sign: shell.loop_where(lambda c, sign=sign: c[0] * sign > 0.03 and c[2] < hip[2] + 0.04) for sign in (1.0, -1.0)}
    shell.level(waist, (0, 0, 1))
    for loop in legs.values():
        shell.level(loop, (0, 0, 1))
    shell.relax(4)

    # The body segment ends at the crease of the leg; the legs of the shorts are grown from there.
    for sign, loop in legs.items():
        centre = np.mean([v.co[:] for v in loop], axis=0)[:2]
        shell.band(loop, [
            (lambda co, centre=centre: ring_scaled(co, centre, 1.05, -0.022), "denim"),
            (lambda co, centre=centre: ring_scaled(co, centre, 1.03, -0.022), "denim"),
            (lambda co, centre=centre: ring_scaled(co, centre, 1.0, -0.004), "denim-stitch"),
            (lambda co, centre=centre: ring_scaled(co, centre, 1.02, -0.020), "denim-shade"),
        ])

    centre = np.mean([v.co[:] for v in waist], axis=0)[:2]
    shell.band(waist, [
        (lambda co: ring_scaled(co, centre, 1.0, 0.004), "denim-stitch"),
        (lambda co: ring_scaled(co, centre, 1.0, 0.032), "denim-shade"),
    ])
    return shell.to_object("Outfit_Shorts", "outfit.default.bottom", ctx["collection"], armature, ctx["material"],
                           ctx["palette"], ctx["tiles"])


# --- boots -------------------------------------------------------------------

BOOT_TOP = 0.425          # height of the shaft's rim at the sides
BOOT_SCALLOP = 0.018      # how far the rim dips at the front and back
BOOT_OFFSET = 0.013       # leather thickness over the skin
BOOT_TOE = 0.040          # how far the pointed toe reaches past the toes


def _boot_path(armature, count):
    """Centre line from the shaft's rim down the shin, round the ankle and out along the foot."""
    knee = np.array(rig.head_of(armature, "LowerLeg.L"))
    ankle = np.array(rig.head_of(armature, "Foot.L"))
    ball = np.array(rig.head_of(armature, "Toes.L"))
    tip = np.array(rig.tail_of(armature, "Toes.L"))

    def shin(z):
        return knee + (ankle - knee) * ((knee[2] - z) / (knee[2] - ankle[2]))

    knots = np.array([
        shin(BOOT_TOP), shin(BOOT_TOP - 0.08), shin(ankle[2] + 0.13), shin(ankle[2] + 0.055),
        ankle + (0.0, -0.012, -0.018),
        ankle + (ball - ankle) * 0.42 + (0.0, 0.0, 0.004),
        ball + (0.0, 0.0, 0.012),
        ball + (tip - ball) * 0.45 + (0.0, 0.0, 0.008),
        ball + (tip - ball) * 0.86 + (0.0, 0.0, 0.004),
    ])
    # Arc-length resample of a Catmull-Rom spline through the knots.
    dense = []
    padded = np.vstack([knots[0], knots, knots[-1]])
    for i in range(len(knots) - 1):
        p0, p1, p2, p3 = padded[i], padded[i + 1], padded[i + 2], padded[i + 3]
        for t in np.linspace(0.0, 1.0, 12, endpoint=False):
            dense.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t
                                + (-p0 + 3 * p1 - 3 * p2 + p3) * t ** 3))
    dense.append(knots[-1])
    dense = np.array(dense)
    lengths = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(dense, axis=0), axis=1))])
    # A little denser round the ankle, where the tube bends.
    stations = np.linspace(0.0, 1.0, count)
    targets = stations * lengths[-1]
    points = np.stack([np.interp(targets, lengths, dense[:, k]) for k in range(3)], axis=1)
    tangents = np.gradient(points, axis=0)
    tangents /= np.linalg.norm(tangents, axis=1, keepdims=True)
    return points, tangents, tip


def build_boots(ctx):
    """Mid-calf cowboy boots: scalloped rim, stitched collar, pointed toe, stacked heel."""
    armature, skin = ctx["armature"], ctx["skin"]
    detail = ctx["detail"]
    rings = max(9, int(round(17 * detail)))
    around = max(8, int(round(16 * detail / 2)) * 2)
    tree = common.bvh_of(skin)
    points, tangents, tip = _boot_path(armature, rings)

    side = np.array((1.0, 0.0, 0.0))
    ball = np.array(rig.head_of(armature, "Toes.L"))
    angles = np.arange(around) * (2.0 * math.pi / around)
    shape = []
    for index, (centre, tangent) in enumerate(zip(points, tangents)):
        front = np.cross(tangent, side)
        radii = np.empty(around)
        for k, angle in enumerate(angles):
            direction = math.cos(angle) * side + math.sin(angle) * front
            hit = tree.ray_cast(Vector(centre), Vector(direction), 0.14)
            radii[k] = hit[3] if hit[0] is not None else np.nan
        fallback = np.nanmedian(radii) if np.isfinite(radii).any() else 0.04
        radii = np.clip(np.where(np.isfinite(radii), radii, fallback), 0.015, 0.075)
        # Rays slip between toes and miss the hollow of the arch; even the ring out.
        for _ in range(2):
            radii = np.maximum(radii, (np.roll(radii, 1) + radii + np.roll(radii, -1)) / 3.0)
        along = index / (rings - 1)
        # Past the ball of the foot the boot stops following the toes and tapers to its point.
        toe_box = smoothstep(ball[1] - 0.01, tip[1], centre[1])
        taper = np.array([math.hypot(0.050 * math.cos(a), 0.030 * math.sin(a)) for a in angles]) * (1.0 - 0.45 * toe_box) - BOOT_OFFSET
        radii = radii * (1.0 - toe_box) + taper * toe_box
        flare = 0.012 * (1.0 - smoothstep(0.0, 0.22, along))
        ring = []
        for k, angle in enumerate(angles):
            direction = math.cos(angle) * side + math.sin(angle) * front
            position = centre + direction * (radii[k] + BOOT_OFFSET + flare)
            if index == 0:
                position[2] += BOOT_SCALLOP * math.cos(2.0 * angle) - BOOT_SCALLOP
            ring.append(position)
        shape.append(np.array(ring))
    shape = np.array(shape)

    # Stand the boot on the ground: the foot floats one sole's height above it.
    lowest = shape[..., 2].min()
    z = shape[..., 2]
    z -= lowest * (1.0 - smoothstep(0.035, 0.12, z))
    ankle = np.array(rig.head_of(armature, "Foot.L"))
    ball = np.array(rig.head_of(armature, "Toes.L"))
    # A stacked heel: the sole under the arch is lifted off the ground.
    arch = smoothstep(ankle[1] - 0.035, ankle[1] - 0.055, shape[..., 1]) * (1.0 - smoothstep(ball[1] + 0.03, ball[1] + 0.005, shape[..., 1]))
    low = z < 0.016
    shape[..., 2] = np.where(low, 0.014 * arch, z)

    toe = np.array((tip[0], tip[1] - BOOT_TOE, 0.022))
    palette, tiles = ctx["palette"], ctx["tiles"]
    source = common.SkinSource(skin)
    objects = []
    part = common.Part("Outfit_Boots", "outfit.default.shoes")
    for sign in (1.0, -1.0):
        ring_ids = [part.verts(ring * (sign, 1.0, 1.0)) for ring in shape]
        toe_ring = max(2, rings // 6)

        def swatch(r, i):
            a, b = shape[r], shape[r + 1]
            if max(a[i][2], a[(i + 1) % around][2], b[i][2], b[(i + 1) % around][2]) < 0.019:
                return "boot-sole"
            if r == 0:
                return "boot-shade"
            return "boot-shade" if r >= rings - 1 - toe_ring else "boot"

        part.loft(ring_ids, swatch, flip=sign < 0)
        part.fan(ring_ids[-1], toe * (sign, 1.0, 1.0), "boot-shade", flip=sign < 0)
    obj = part.to_object(ctx["collection"], armature, ctx["material"], palette, tiles, sharp_angle=50.0)
    common.set_weights(obj, source.sample(common.coords(obj.data)))
    return obj
