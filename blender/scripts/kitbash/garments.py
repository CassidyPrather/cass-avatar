"""The default outfit: sweater, denim shorts and cowboy boots.

The sweater and the shorts are shells cut from the body (see shell.py). The
boots are lofted around the lower leg and foot, measuring the skin as they
go. Stitching, seams, pockets and lacing are laid on afterwards (detail.py).
All lengths are in metres on the finished, scaled figure; anything that
depends on where the body is reads the skeleton.

`detail` is 1.0 for the full level and lower for lite. Shells get their
resolution from the body level they are cut from; `detail` sets how finely
lofted parts are divided, how much a coarse shell may be relaxed, and
whether the laid-on details are made at all.
"""

import math

import numpy as np
from mathutils import Vector

from . import common, rig
from .common import smoothstep
from .detail import Applique, Surface
from .shell import Shell, around_axis, ring_scaled, ring_to_radius

SWEATER_SEGMENTS = ("Chest_01", "Chest_02", "Spine", "Shoulder", "UpperArm", "Elbow", "LowerArm")
SHORTS_SEGMENTS = ("Hips", "UpperLeg_01")

# "scoop" is an open U at the front; "crew" closes round the base of the neck.
NECKLINE = "scoop"
# How steeply the neckline climbs from the middle towards the shoulders (metres per metre squared).
NECK_CLIMB = 3.2


def _relaxed(count, detail):
    """Relaxing shrinks a coarse shell far more than a fine one."""
    return max(2, int(round(count * detail * detail)))


def build_sweater(ctx):
    """A loose sweater: scoop neck, striped ribbed bands, and laced vents at the sides of the hem."""
    armature, detail = ctx["armature"], ctx["detail"]
    shoulder = np.array(rig.head_of(armature, "UpperArm.L"))
    wrist = np.array(rig.head_of(armature, "Hand.L"))
    chest = np.array(rig.head_of(armature, "Chest"))
    neck = np.array(rig.head_of(armature, "Neck"))
    armpit = shoulder[2] - 0.065

    shell = Shell(ctx["skin"], SWEATER_SEGMENTS, "sweater")
    shell.inflate(0.010)

    # The body of the sweater hangs as a tube rather than following the waist:
    # wherever the skin is inside this ellipse, the cloth is pushed out to it.
    # It is only a little wider than the ribcage; a wide one swamps the arms and the head.
    centre_y = chest[1] + 0.002
    half_depth = 0.100

    def half_width(z):
        return 0.138 + 0.014 * (1.0 - smoothstep(chest[2] - 0.13, armpit, z))

    def drape(co):
        out = co.copy()
        hang = 1.0 - smoothstep(armpit - 0.03, armpit + 0.05, co[:, 2])
        x, y = co[:, 0] / half_width(co[:, 2]), (co[:, 1] - centre_y) / half_depth
        rho = np.maximum(np.sqrt(x * x + y * y), 1e-6)
        grow = np.where(rho < 1.0, 1.0 + (1.0 / rho - 1.0) * hang, 1.0)
        out[:, 0] = co[:, 0] * grow
        out[:, 1] = centre_y + (co[:, 1] - centre_y) * grow

        # Sleeves: loose from the dropped shoulder, widest just before the cuff.
        for sign in (1.0, -1.0):
            a, b = shoulder * (sign, 1, 1), wrist * (sign, 1, 1)
            t, _foot, radial = around_axis(out, a, b)
            distance = np.maximum(np.linalg.norm(radial, axis=1), 1e-6)
            loose = 0.050 + 0.022 * smoothstep(0.0, 0.85, t)
            arm = smoothstep(0.02, 0.22, t) * (out[:, 0] * sign > 0)
            push = np.maximum(loose - distance, 0.0) * arm
            out += radial / distance[:, None] * push[:, None]
        return out

    shell.reshape(drape)

    # Rims: each is cut straight, just inside the saw-toothed edge of the body segment.
    hem = shell.cut_rim(shell.loop_where(lambda c: abs(c[0]) < 0.1 and c[2] < chest[2] - 0.05), (0, 0, -1))
    cuffs = {sign: shell.cut_rim(shell.loop_where(lambda c, sign=sign: c[0] * sign > 0.4), (sign, 0, 0)) for sign in (1.0, -1.0)}
    # The neckline is a plane through the nape and a point on the chest, so it is an oval, lower in front.
    crew = NECKLINE == "crew"
    nape = np.array((0.0, neck[1] + 0.060, neck[2] + (0.070 if crew else 0.056)))
    front = np.array((0.0, neck[1] - (0.070 if crew else 0.108), neck[2] + (0.040 if crew else -0.050)))
    slope = front - nape
    opening = np.array((0.0, slope[2], -slope[1]))
    opening = opening / np.linalg.norm(opening) * (1.0 if opening[2] > 0 else -1.0)
    middle = (nape + front) / 2.0
    # A plane low enough for the front would also slice the tops of the shoulders, so the cut is
    # made with the shell bent: sunk towards the sides beforehand and raised again after, which
    # turns the plane into a U that climbs to the shoulders.
    def bend(co, amount):
        out = co.copy()
        out[:, 2] -= amount * NECK_CLIMB * np.minimum(np.abs(co[:, 0]), 0.2) ** 2
        return out

    shell.reshape(lambda co: bend(co, 1.0))
    collar = shell.cut_within(shell.loop_where(lambda c: abs(c[0]) < 0.05 and c[2] > neck[2] - 0.05), nape, opening)
    shell.reshape(lambda co: bend(co, -1.0))
    shell.relax(_relaxed(16, detail))
    # Relaxing draws the sleeves and the tube in again, most of all on a coarse shell; put the room back.
    shell.reshape(drape)
    shell.clear_skin(0.008)

    for sign, cuff in cuffs.items():
        a, b = shoulder * (sign, 1, 1), wrist * (sign, 1, 1)
        shell.band(cuff, [
            (lambda co, a=a, b=b: ring_to_radius(co, a, b, 0.058, 0.022), "sweater"),
            (lambda co, a=a, b=b: ring_to_radius(co, a, b, 0.043, 0.010), "sweater-shade"),
            (lambda co, a=a, b=b: ring_to_radius(co, a, b, 0.042, 0.014), "sweater-stripe"),
            (lambda co, a=a, b=b: ring_to_radius(co, a, b, 0.041, 0.016), "sweater-shade"),
        ])

    axis = (0.0, centre_y)
    shell.band(hem, [
        (lambda co: ring_scaled(co, axis, 1.0, -0.030), "sweater"),
        (lambda co: ring_scaled(co, axis, 1.0, -0.030), "sweater"),
        (lambda co: ring_scaled(co, axis, 0.965, -0.012), "sweater-shade"),
        (lambda co: ring_scaled(co, axis, 1.0, -0.016), "sweater-stripe"),
        (lambda co: ring_scaled(co, axis, 1.0, -0.020), "sweater-shade"),
    ])

    def rib(co, rise, draw):
        out = co + opening * rise
        out[:, :2] = middle[:2] + (out[:, :2] - middle[:2]) * draw
        return out

    shell.band(collar, [
        (lambda co: rib(co, 0.009, 0.985), "sweater-shade"),
        (lambda co: rib(co, 0.009, 0.975), "sweater-shade"),
    ])
    obj = shell.to_object("Outfit_Sweater", "outfit.default.top", ctx["collection"], armature, ctx["material"],
                          ctx["palette"], ctx["tiles"])

    if detail >= 1.0:
        surface = Surface(obj)
        applique = Applique(surface)
        low = min(v.co.z for v in obj.data.vertices)
        for sign in (1.0, -1.0):
            # A vent at each side of the hem: a darker gusset, laced shut with pale cord.
            side = 90.0 * sign
            bottom, top, spread = low + 0.006, low + 0.100, 15.0
            gusset = [surface.around(axis, side - spread, bottom), surface.around(axis, side, bottom),
                      surface.around(axis, side + spread, bottom), surface.around(axis, side + spread * 0.5, (bottom + top) / 2),
                      surface.around(axis, side, top), surface.around(axis, side - spread * 0.5, (bottom + top) / 2)]
            applique.patch(gusset, "sweater-shade", lift=0.0015)
            rows = 4
            for row in range(rows):
                z0 = bottom + (top - bottom) * (row + 0.15) / (rows + 0.6)
                z1 = bottom + (top - bottom) * (row + 1.05) / (rows + 0.6)
                reach = spread * (1.0 - (row + 0.3) / (rows + 0.8))
                for lean in (1.0, -1.0):
                    cord = [surface.around(axis, side - reach * lean * (1 - 2 * t), z0 + (z1 - z0) * t) for t in np.linspace(0, 1, 5)]
                    applique.ribbon(cord, 0.0042, "ear-fur", lift=0.0035)
            for edge in (-1.0, 1.0):
                seam = [surface.around(axis, side + edge * spread * (1.0 - t) * 1.05, bottom + (top - bottom) * t) for t in np.linspace(0, 1, 6)]
                applique.ribbon(seam, 0.004, "sweater-stripe", lift=0.0028)
        applique.apply(ctx["palette"], ctx["tiles"], "outfit.default.top")
    return obj


def build_shorts(ctx):
    """Denim short-shorts: waistband with belt loops, pockets, fly and seams stitched on, turned-up hems."""
    armature, detail = ctx["armature"], ctx["detail"]
    hip = np.array(rig.head_of(armature, "UpperLeg.L"))
    hips = np.array(rig.head_of(armature, "Hips"))
    shell = Shell(ctx["skin"], SHORTS_SEGMENTS, "denim")
    shell.inflate(0.009)

    waist = shell.cut_rim(shell.loop_where(lambda c: abs(c[0]) < 0.05 and c[2] > hip[2] + 0.05), (0, 0, 1))
    # The legs are cut level a hand's width below the hip joint, well inside the thigh segment,
    # so the cloth runs smoothly over the crease of the leg instead of starting at it.
    hem_height = hip[2] - 0.135
    rim = shell.cut((0.0, hip[1], hem_height), (0, 0, -1))
    legs = {sign: [v for v in rim if v.co.x * sign > 0] for sign in (1.0, -1.0)}
    shell.relax(_relaxed(10, detail))
    shell.clear_skin(0.008)

    for sign, loop in legs.items():
        centre = np.mean([v.co[:] for v in loop], axis=0)[:2]
        shell.band(loop, [
            (lambda co, centre=centre: ring_scaled(co, centre, 1.035, -0.012), "denim"),
            (lambda co, centre=centre: ring_scaled(co, centre, 1.0, -0.004), "denim-stitch"),
            (lambda co, centre=centre: ring_scaled(co, centre, 1.02, -0.022), "denim-shade"),
        ])

    centre = np.mean([v.co[:] for v in waist], axis=0)[:2]
    top = shell.band(waist, [
        (lambda co: ring_scaled(co, centre, 1.0, 0.004), "denim-stitch"),
        (lambda co: ring_scaled(co, centre, 1.0, 0.034), "denim-shade"),
    ])
    band_top = float(np.mean([v.co.z for v in top]))
    obj = shell.to_object("Outfit_Shorts", "outfit.default.bottom", ctx["collection"], armature, ctx["material"],
                          ctx["palette"], ctx["tiles"])

    if detail >= 1.0:
        surface = Surface(obj)
        applique = Applique(surface)
        axis = (0.0, hips[1] + 0.02)
        stitch = 0.0034
        band_low = band_top - 0.036
        seat = band_low - 0.012

        def line(points, swatch="denim-stitch", width=stitch):
            applique.ribbon([surface.around(axis, a, z) for a, z in points], width, swatch)

        for sign in (1.0, -1.0):
            # Back pocket: a stitched shield, and a second line across its top.
            at = 180.0 - 30.0 * sign
            w, h = 13.0, 0.085
            outline = [(at - w, seat), (at + w, seat), (at + w, seat - h * 0.62), (at, seat - h), (at - w, seat - h * 0.62), (at - w, seat)]
            dense = []
            for (a0, z0), (a1, z1) in zip(outline, outline[1:]):
                dense += [(a0 + (a1 - a0) * t, z0 + (z1 - z0) * t) for t in np.linspace(0, 1, 4, endpoint=False)]
            line(dense + [outline[-1]])
            line([(at - w + 1.5, seat - 0.012), (at, seat - 0.012), (at + w - 1.5, seat - 0.012)])
            # Front pocket: a curve from the waistband out to the side seam.
            line([(sign * (26.0 + 46.0 * t), band_low - 0.004 - 0.052 * t ** 1.8) for t in np.linspace(0, 1, 8)])
            # Side seam, waistband to hem.
            line([(sign * 90.0, z) for z in np.linspace(band_low - 0.004, hem_height - 0.008, 10)], width=0.003)
            # Yoke across the back, dipping to the centre.
            line([(180.0 - sign * a, seat + 0.006 - 0.016 * (1.0 - a / 78.0)) for a in np.linspace(2.0, 78.0, 8)], width=0.003)
        # Fly: a J of stitching left of centre, and a brass button on the waistband.
        line([(7.0, band_low - 0.004), (7.5, band_low - 0.045), (6.5, band_low - 0.075), (3.0, band_low - 0.092), (0.5, band_low - 0.098)])
        line([(0.0, z) for z in np.linspace(band_low - 0.004, band_low - 0.100, 6)], width=0.003)
        button = [surface.around(axis, 3.0 * math.cos(k * math.pi / 3), band_low + 0.018 + 0.008 * math.sin(k * math.pi / 3)) for k in range(6)]
        applique.patch(button, "boot-stitch", lift=0.004)
        # Belt loops stand over the waistband.
        for at in (-152.0, -90.0, -28.0, 28.0, 90.0, 152.0, 180.0):
            loop = [surface.around(axis, at + da, z) for da, z in ((-2.6, band_low - 0.004), (2.6, band_low - 0.004), (2.6, band_top + 0.002), (-2.6, band_top + 0.002))]
            applique.patch(loop, "denim", lift=0.0045)
        applique.apply(ctx["palette"], ctx["tiles"], "outfit.default.bottom")
    return obj


# --- boots -------------------------------------------------------------------

BOOT_TOP = 0.425          # height of the shaft's rim
BOOT_OFFSET = 0.012       # leather thickness over the skin
BOOT_TOE = 0.034          # how far the toe reaches past the toes
HEEL_HEIGHT = 0.034       # the stacked heel
FOOT = (0.050, 0.034)     # half-width and half-height of the boot round the ball of the foot


def _shin(armature, z):
    """The point on the shin bone's line at a height."""
    knee = np.array(rig.head_of(armature, "LowerLeg.L"))
    ankle = np.array(rig.head_of(armature, "Foot.L"))
    return knee + (ankle - knee) * ((knee[2] - z) / (knee[2] - ankle[2]))


def _boot_path(armature, count):
    """Centre line from the shaft's rim down the shin, round the ankle in a wide bend, and out along the foot."""
    ankle = np.array(rig.head_of(armature, "Foot.L"))
    ball = np.array(rig.head_of(armature, "Toes.L"))
    tip = np.array(rig.tail_of(armature, "Toes.L"))
    knots = np.array([
        _shin(armature, BOOT_TOP), _shin(armature, BOOT_TOP - 0.09), _shin(armature, ankle[2] + 0.15),
        _shin(armature, ankle[2] + 0.085),
        _shin(armature, ankle[2] + 0.035) + (0.0, -0.006, 0.0),
        ankle + (0.0, -0.030, -0.012),
        ankle + (ball - ankle) * 0.55 + (0.0, 0.0, 0.006),
        ball + (0.0, 0.0, 0.010),
        ball + (tip - ball) * 0.5 + (0.0, 0.0, 0.008),
        tip + (0.0, -BOOT_TOE * 0.45, 0.006),
    ])
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
    targets = np.linspace(0.0, 1.0, count) * lengths[-1]
    points = np.stack([np.interp(targets, lengths, dense[:, k]) for k in range(3)], axis=1)
    tangents = np.gradient(points, axis=0)
    tangents /= np.linalg.norm(tangents, axis=1, keepdims=True)
    return points, tangents, ankle, ball, tip


def build_boots(ctx):
    """Mid-calf cowboy boots: stitched shafts with pull straps, a tapering toe, and a stacked heel."""
    armature, skin, detail = ctx["armature"], ctx["skin"], ctx["detail"]
    rings = max(11, int(round(22 * detail)))
    around = max(8, int(round(20 * detail / 2)) * 2)
    tree = common.bvh_of(skin)
    points, tangents, ankle, ball, tip = _boot_path(armature, rings)

    side = np.array((1.0, 0.0, 0.0))
    angles = np.arange(around) * (2.0 * math.pi / around)
    oval = np.array([math.hypot(FOOT[0] * math.cos(a), FOOT[1] * math.sin(a)) for a in angles])
    radii = np.empty((rings, around))
    for index, (centre, tangent) in enumerate(zip(points, tangents)):
        front = np.cross(tangent, side)
        row = np.empty(around)
        for k, angle in enumerate(angles):
            direction = math.cos(angle) * side + math.sin(angle) * front
            found = tree.ray_cast(Vector(centre), Vector(direction), 0.14)
            row[k] = found[3] if found[0] is not None else np.nan
        fallback = np.nanmedian(row) if np.isfinite(row).any() else 0.04
        row = np.clip(np.where(np.isfinite(row), row, fallback), 0.015, 0.075) + BOOT_OFFSET
        # Along the foot the boot is its own shape, not the foot's: at least an oval this big,
        # so rays that slip between toes or miss the arch leave no dent.
        on_foot = smoothstep(ankle[2] + 0.02, ankle[2] - 0.03, centre[2])
        row = np.maximum(row, oval * on_foot)
        # From the ball of the foot on, it is only that oval, drawn in smoothly to a blunt point.
        toe = smoothstep(ball[1] + 0.02, tip[1] - BOOT_TOE * 0.45, centre[1])
        radii[index] = row * (1.0 - toe) + oval * (1.0 - 0.72 * toe ** 1.6) * toe
    # Even the shape out along the boot and round it, so no ring stands out as a crease or a band.
    for _ in range(2):
        radii[1:-1] = (radii[:-2] + 2.0 * radii[1:-1] + radii[2:]) / 4.0
        radii = (np.roll(radii, 1, axis=1) + 2.0 * radii + np.roll(radii, -1, axis=1)) / 4.0

    shape = np.empty((rings, around, 3))
    for index, (centre, tangent) in enumerate(zip(points, tangents)):
        front = np.cross(tangent, side)
        flare = 0.010 * (1.0 - smoothstep(0.0, 0.18, index / (rings - 1)))
        for k, angle in enumerate(angles):
            direction = math.cos(angle) * side + math.sin(angle) * front
            shape[index, k] = centre + direction * (radii[index, k] + flare)

    # The sole: flat on the ground under the ball and toe, rising to the heel's height at the back.
    heel_front = ankle[1] - 0.030

    def sole(y):
        return HEEL_HEIGHT * smoothstep(ball[1] + 0.035, heel_front, y)

    z = shape[..., 2]
    z -= z.min() * (1.0 - smoothstep(0.04, 0.13, z))
    rise = sole(shape[..., 1])
    shape[..., 2] = np.where(z < 0.020, rise, np.maximum(z, rise))

    toe_point = np.array((tip[0], tip[1] - BOOT_TOE, 0.016))
    part = common.Part("Outfit_Boots", "outfit.default.shoes")
    toe_rings = max(2, rings // 5)
    for sign in (1.0, -1.0):
        ring_ids = [part.verts(ring * (sign, 1.0, 1.0)) for ring in shape]

        def swatch(r, i):
            corners = (shape[r][i], shape[r][(i + 1) % around], shape[r + 1][i], shape[r + 1][(i + 1) % around])
            if all(c[2] <= sole(c[1]) + 0.004 for c in corners):
                return "boot-sole"
            if r == 0:
                return "boot-shade"
            return "boot-shade" if r >= rings - 1 - toe_rings else "boot"

        part.loft(ring_ids, swatch, flip=sign < 0)
        part.fan(ring_ids[-1], toe_point * (sign, 1.0, 1.0), "boot-shade", flip=sign < 0)

        # The stacked heel: a block under the heel, a little narrower at the ground than at the boot.
        back = ankle[1] + 0.058
        cx = ankle[0] * sign
        top = [(cx - 0.036, heel_front, HEEL_HEIGHT), (cx + 0.036, heel_front, HEEL_HEIGHT),
               (cx + 0.038, back - 0.012, HEEL_HEIGHT), (cx + 0.022, back, HEEL_HEIGHT),
               (cx - 0.022, back, HEEL_HEIGHT), (cx - 0.038, back - 0.012, HEEL_HEIGHT)]
        ground = [(cx + (x - cx) * 0.86, heel_front + 0.010 + (y - heel_front - 0.010) * 0.90, 0.0) for x, y, _z in top]
        upper, lower = part.verts(top), part.verts(ground)
        part.loft([upper, lower], "boot-sole")
        part.face(lower, "boot-sole")
    obj = part.to_object(ctx["collection"], armature, ctx["material"], ctx["palette"], ctx["tiles"], sharp_angle=50.0)
    common.set_weights(obj, common.SkinSource(skin).sample(common.coords(obj.data)))

    if detail >= 1.0:
        surface = Surface(obj)
        applique = Applique(surface)
        rim = BOOT_TOP - 0.012
        for sign in (1.0, -1.0):
            def shaft(z):
                at = _shin(armature, z)
                return (at[0] * sign, at[1])

            def line(points, width=0.0036, closed=False):
                # A short reach: a ray started further out would begin beyond the other boot.
                applique.ribbon([surface.around(shaft(z), a, z, reach=0.075) for a, z in points], width, "boot-stitch", closed=closed)

            # Piping round the rim, and a second row of stitching under it.
            line([(a, rim) for a in np.linspace(0.0, 360.0, 21)[:-1]], width=0.006, closed=True)
            line([(a, rim - 0.020) for a in np.linspace(0.0, 360.0, 21)[:-1]], width=0.003, closed=True)
            # The shaft's stitched flames: one on each side, one smaller inside it.
            flame = [(0.0, 0.150), (16.0, 0.115), (25.0, 0.070), (17.0, 0.030), (0.0, 0.0), (-17.0, 0.030), (-25.0, 0.070), (-16.0, 0.115)]
            dense = []
            for (a0, z0), (a1, z1) in zip(flame, flame[1:] + flame[:1]):
                dense += [(a0 + (a1 - a0) * t, z0 + (z1 - z0) * t) for t in np.linspace(0, 1, 3, endpoint=False)]
            for at in (90.0, -90.0):
                for scale in (1.0, 0.55):
                    line([(at + a * scale, 0.215 + 0.075 * (1 - scale) + zz * scale) for a, zz in dense], closed=True)
            # A seam down the front and the back.
            for at in (0.0, 180.0):
                line([(at, z) for z in np.linspace(rim - 0.024, ankle[2] + 0.075, 7)], width=0.003)
            # Pull straps: a flat loop standing over the rim at each side.
            for at in (90.0, -90.0):
                a = math.radians(at)
                out = np.array((math.sin(a), -math.cos(a), 0.0))
                along = np.array((-out[1], out[0], 0.0))
                found = surface.around(shaft(rim), at, rim, reach=0.075)
                if found is None:
                    continue
                base = found[0] + out * 0.004
                strap = [base - along * 0.011 + (0, 0, -0.030), base + along * 0.011 + (0, 0, -0.030),
                         base + along * 0.011 + (0, 0, 0.038), base - along * 0.011 + (0, 0, 0.038)]
                applique.solid(strap, [(0, 1, 2, 3)], "boot-shade")
            # The toe: a stitched wingtip across the top of the foot.
            cx = ankle[0] * sign
            wing = [surface.below(cx + t * (FOOT[0] - 0.004), ball[1] - 0.018 - 0.050 * (1.0 - t * t), top=0.3)
                    for t in np.linspace(-1.0, 1.0, 11)]
            applique.ribbon(wing, 0.0036, "boot-stitch")
        applique.apply(ctx["palette"], ctx["tiles"], "outfit.default.shoes")
    return obj
