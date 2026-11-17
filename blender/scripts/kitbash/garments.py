"""The outfit: sweater, denim shorts and cowboy boots, and the pieces that can be worn instead of or over them.

The sweater and the shorts are shells cut from the body (see shell.py). The
boots are lofted around the lower leg and foot, measuring the skin as they
go. Stitching, seams and pockets are laid on afterwards (detail.py). The
skirt, an alternative to the shorts, is lofted round the hips and legs and
wears the atlas's painted gingham. The vest and neckerchief are a layer over
the sweater, on a tile of their own.
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

import cass_spec

from . import atlas, common, rig, sweep
from .common import smoothstep
from .detail import Applique, Surface
from .shell import Shell, around_axis, ring_scaled, ring_to_radius

SWEATER_SEGMENTS = ("Chest_01", "Chest_02", "Spine", "Shoulder", "UpperArm", "Elbow", "LowerArm")
SHORTS_SEGMENTS = ("Hips", "UpperLeg_01")

# "scoop" is an open U at the front; "crew" closes round the base of the neck.
NECKLINE = "crew"
# How steeply the neckline climbs from the middle towards the shoulders (metres per metre squared).
NECK_CLIMB = 3.2
SWEATER_HEM = 0.090        # how far below the waist the sweater ends
SWEATER_SQUARE = 2.6       # the tube's cross-section: 2 is an ellipse, more is squarer
SWEATER_HEM_RIB = 0.042    # the height of the ribbed band at the hem
SWEATER_RIB = 0.955        # how far the ribbed band draws in from the tube above it
SWEATER_EASE = 0.009       # room between the hem band and what is worn under it
SWEATER_HEM_FREE = 0.7     # how much of the thighs' pull on the hem is given to the hips instead


def _relaxed(count, detail):
    """Relaxing shrinks a coarse shell far more than a fine one."""
    return max(2, int(round(count * detail * detail)))


def _oval(x, y, half_width, half_depth, square=None):
    """How far (x, y) is from the centre of a squarish oval, as a fraction of the way to its edge."""
    n = SWEATER_SQUARE if square is None else square
    return np.maximum((np.abs(x / half_width) ** n + np.abs(y / half_depth) ** n) ** (1.0 / n), 1e-9)


def _oval_ring(co, centre_y, half_width, half_depth, z, square=None):
    """A ring's vertices set on a horizontal oval at height `z`, each keeping its bearing from the axis."""
    rho = _oval(co[:, 0], co[:, 1] - centre_y, half_width, half_depth, square)
    return np.stack([co[:, 0] / rho, centre_y + (co[:, 1] - centre_y) / rho, np.full(len(co), z)], axis=1)


def build_sweater(ctx):
    """An oversized crew-neck sweater: a plain tube below the arms, bloused into ribbed bands at hem, cuffs and neck."""
    armature, detail = ctx["armature"], ctx["detail"]
    shoulder = np.array(rig.head_of(armature, "UpperArm.L"))
    wrist = np.array(rig.head_of(armature, "Hand.L"))
    chest = np.array(rig.head_of(armature, "Chest"))
    neck = np.array(rig.head_of(armature, "Neck"))
    armpit = shoulder[2] - 0.065

    shell = Shell(ctx["skin"], SWEATER_SEGMENTS, "sweater")
    shell.inflate(0.010)

    # Rims: each is cut straight, just inside the saw-toothed edge of the body segment.
    hem = shell.cut_rim(shell.loop_where(lambda c: abs(c[0]) < 0.1 and c[2] < chest[2] - 0.05), (0, 0, -1))
    cuffs = {sign: shell.cut_rim(shell.loop_where(lambda c, sign=sign: c[0] * sign > 0.4), (sign, 0, 0)) for sign in (1.0, -1.0)}
    waist = float(np.mean([v.co.z for v in hem]))
    low = waist - SWEATER_HEM

    # Below the arms the sweater is a tube that owes nothing to the waist under it: an ellipse
    # at every height, a little wider than the ribcage at the top and, at the hem, as big as it
    # has to be for the ribbed band to pass round what is worn underneath. Every vertex there is
    # put on it, in or out, so the body's shape cannot show and the hem has no ledge. A tube much
    # wider than this swamps the arms and the head.
    top = np.array((0.146, chest[1] + 0.004, 0.098))                      # half-width, centre y, half-depth
    bottom = np.array((0.152, chest[1] + 0.004, 0.100))
    if ctx.get("shorts") is not None:
        under = common.coords(ctx["shorts"].data)
        under = under[(under[:, 2] > low - 0.01) & (under[:, 2] < waist + 0.01)]
        if len(under):
            front, back = under[:, 1].min(), under[:, 1].max()
            fit = np.array((np.abs(under[:, 0]).max(), (front + back) / 2.0, (back - front) / 2.0))
            rho = _oval(under[:, 0], under[:, 1] - fit[1], fit[0], fit[2]).max()
            fit[0], fit[2] = fit[0] * rho + SWEATER_EASE, fit[2] * rho + SWEATER_EASE
            # The band is drawn in from the tube by SWEATER_RIB; the tube is that much bigger than the fit.
            bottom = np.array((max(bottom[0], fit[0] / SWEATER_RIB), fit[1], max(bottom[2], fit[2] / SWEATER_RIB)))
    print(f"sweater: waist {waist:.3f}, hem {low:.3f}, tube at the hem {np.round(bottom, 3)}")

    def tube(z):
        # 1 at the armpit, 0 at the waist.
        blend = smoothstep(waist - 0.02, armpit - 0.02, z)[:, None]
        return bottom + (top - bottom) * blend

    def drape(co):
        out = co.copy()
        half_width, centre_y, half_depth = tube(co[:, 2]).T
        rho = _oval(co[:, 0], co[:, 1] - centre_y, half_width, half_depth)
        # Near the armpit only what is inside the tube is pushed out to it; lower down, where
        # there is no arm to drag in, everything is put on it.
        push = 1.0 - smoothstep(armpit - 0.03, armpit + 0.05, co[:, 2])
        pull = 1.0 - smoothstep(armpit - 0.11, armpit - 0.03, co[:, 2])
        grow = 1.0 + (1.0 / rho - 1.0) * np.where(rho < 1.0, push, pull)
        out[:, 0] = co[:, 0] * grow
        out[:, 1] = centre_y + (co[:, 1] - centre_y) * grow

        # Sleeves: loose from the dropped shoulder, a little fuller towards the cuff.
        for sign in (1.0, -1.0):
            a, b = shoulder * (sign, 1, 1), wrist * (sign, 1, 1)
            t, _foot, radial = around_axis(out, a, b)
            distance = np.maximum(np.linalg.norm(radial, axis=1), 1e-6)
            loose = 0.049 + 0.011 * smoothstep(0.0, 0.85, t)
            arm = smoothstep(0.02, 0.22, t) * (out[:, 0] * sign > 0)
            push = np.maximum(loose - distance, 0.0) * arm
            out += radial / distance[:, None] * push[:, None]
        return out

    shell.reshape(drape)

    # The neckline is a plane through the nape and a point on the chest, so it is an oval, lower in front.
    crew = NECKLINE == "crew"
    nape = np.array((0.0, neck[1] + 0.060, neck[2] + (0.054 if crew else 0.056)))
    front = np.array((0.0, neck[1] - (0.094 if crew else 0.108), neck[2] + (-0.012 if crew else -0.050)))
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
    shell.smooth_loop(collar, 6)
    shell.relax(_relaxed(16, detail))
    # Relaxing draws the sleeves and the tube in again, most of all on a coarse shell; put the room back.
    shell.reshape(drape)
    shell.clear_skin(0.008)
    # Lifting the rim clear of the skin vertex by vertex leaves it wavy, and a ribbed band grown
    # from a wavy rim is a frill. The neckline is redrawn as one even oval.
    neck_axis = shell.fair_loop(collar, clearance=0.008)
    shell.relax_near(collar, 0.035, 4)
    shell.clear_skin(0.008)
    shell.fair_loop(collar, clearance=0.008)
    # What is worn over the sweater is shaped by the same drape and laid round the same neckline.
    ctx["sweater_drape"] = drape
    ctx["sweater_collar"] = shell.faired
    rim = np.array([v.co[:] for v in collar])
    print(f"sweater: collar x {rim[:, 0].min():.3f}..{rim[:, 0].max():.3f}, y {rim[:, 1].min():.3f}..{rim[:, 1].max():.3f}, z {rim[:, 2].min():.3f}..{rim[:, 2].max():.3f}")

    for sign, cuff in cuffs.items():
        a, b = shoulder * (sign, 1, 1), wrist * (sign, 1, 1)
        # The sleeve blouses over the cuff, which is a ribbed band close round the wrist.
        steps = [
            (lambda co, a=a, b=b: ring_to_radius(co, a, b, 0.057, 0.016), "sweater"),
            (lambda co, a=a, b=b: ring_to_radius(co, a, b, 0.041, 0.012), "sweater"),
            (lambda co, a=a, b=b: ring_to_radius(co, a, b, 0.039, 0.034), "sweater-shade"),
        ]
        if detail >= 1.0:
            steps.append((lambda co, a=a, b=b: ring_to_radius(co, a, b, 0.033, -0.003), "sweater-shade"))
        made = []
        shell.band(cuff, steps, made)
        if detail >= 1.0:
            shell.ribs(made[1], made[2], "sweater", spacing=0.010)

    def hem_ring(scale, drop):
        half_width, centre_y, half_depth = bottom
        return lambda co: _oval_ring(co, centre_y, half_width * scale, half_depth * scale, waist - drop)

    rib_top = SWEATER_HEM - SWEATER_HEM_RIB
    steps = [
        (hem_ring(1.012, rib_top * 0.50), "sweater"),
        (hem_ring(1.000, rib_top - 0.008), "sweater"),
        (hem_ring(SWEATER_RIB + 0.008, rib_top), "sweater"),
        (hem_ring(SWEATER_RIB, SWEATER_HEM), "sweater-shade"),
    ]
    if detail >= 1.0:
        steps.append((hem_ring(SWEATER_RIB - 0.045, SWEATER_HEM - 0.003), "sweater-shade"))
    made = []
    shell.band(hem, steps, made)
    if detail >= 1.0:
        shell.ribs(made[2], made[3], "sweater", spacing=0.011)

    def rib(co, rise, draw):
        out = co + opening * rise
        out[:, :2] = middle[:2] + (out[:, :2] - middle[:2]) * draw
        return out

    def lean(co, rise, inward):
        """A ring moved up out of the neckline and in towards the neck by so many metres."""
        out = co + opening * rise
        radial = out[:, :2] - neck_axis
        distance = np.maximum(np.linalg.norm(radial, axis=1, keepdims=True), 1e-9)
        out[:, :2] = neck_axis + radial * (1.0 - inward / distance)
        return out

    if crew:
        # A ribbed band that stands a little proud of the cloth and leans in towards the neck,
        # with an edge that turns under.
        ribbing = [
            (lambda co: lean(co, 0.005, -0.003), "sweater-shade"),
            (lambda co: lean(co, 0.013, 0.010), "sweater-shade"),
        ]
        if detail >= 1.0:
            ribbing.append((lambda co: lean(co, -0.005, 0.006), "sweater-shade"))
    else:
        ribbing = [
            (lambda co: rib(co, 0.008, 0.99), "sweater-shade"),
            (lambda co: rib(co, 0.008, 0.98), "sweater-shade"),
        ]
        if detail >= 1.0:
            # Rolled over: the rib turns in and down, so the neckline has an edge with some depth to it.
            ribbing += [
                (lambda co: rib(co, 0.000, 0.955), "sweater-shade"),
                (lambda co: rib(co, -0.012, 0.975), "sweater-shade"),
            ]
    made = []
    shell.band(collar, ribbing, made)
    if detail >= 1.0 and crew:
        shell.ribs(made[0], made[1], "sweater", spacing=0.008, width=0.002, inset=0.2)
    obj = shell.to_object("Outfit_Sweater", "outfit.default.top", ctx["collection"], armature, ctx["material"],
                          ctx["palette"], ctx["tiles"])

    # The hem hangs from the waist. Skin weights sampled from the hips under it would have each
    # thigh drag its side of the band along; most of that is given back to the hips.
    table = common.weights_of(obj)
    co = common.coords(obj.data)
    hanging = smoothstep(waist + 0.02, waist - 0.03, co[:, 2])
    table.setdefault("Hips", np.zeros(len(co)))
    for side in "LR":
        name = f"UpperLeg.{side}"
        if name in table:
            given = table[name] * hanging * SWEATER_HEM_FREE
            table[name] = table[name] - given
            table["Hips"] = table["Hips"] + given
    common.set_weights(obj, table)
    ctx["sweater"] = obj
    ctx["sweater_tube"] = {"waist": waist, "low": low, "bottom": bottom, "rib": SWEATER_RIB}
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
        hem = [
            (lambda co, centre=centre: ring_scaled(co, centre, 1.035, -0.012), "denim"),
            (lambda co, centre=centre: ring_scaled(co, centre, 1.0, -0.004), "denim-stitch"),
            (lambda co, centre=centre: ring_scaled(co, centre, 1.02, -0.022), "denim-shade"),
        ]
        if detail >= 1.0:
            # The turn-up has an underside.
            hem += [
                (lambda co, centre=centre: ring_scaled(co, centre, 0.955, -0.002), "denim-shade"),
                (lambda co, centre=centre: ring_scaled(co, centre, 0.99, 0.020), "denim-shade"),
            ]
        shell.band(loop, hem)

    centre = np.mean([v.co[:] for v in waist], axis=0)[:2]
    top = shell.band(waist, [
        (lambda co: ring_scaled(co, centre, 1.0, 0.004), "denim-stitch"),
        (lambda co: ring_scaled(co, centre, 1.0, 0.034), "denim-shade"),
    ])
    band_top = float(np.mean([v.co.z for v in top]))
    # The waistband is a folded strip: it turns over at the top and comes back down inside.
    # The lite level makes do with the turn.
    fold = [(lambda co: ring_scaled(co, centre, 0.955, -0.003), "denim-shade")]
    if detail >= 1.0:
        fold = [(lambda co: ring_scaled(co, centre, 0.985, 0.004), "denim-shade")] + fold + [
            (lambda co: ring_scaled(co, centre, 0.985, -0.026), "denim-shade")]
    shell.band(top, fold)
    obj = shell.to_object("Outfit_Shorts", "outfit.default.bottom", ctx["collection"], armature, ctx["material"],
                          ctx["palette"], ctx["tiles"])
    # What is worn over the shorts keeps clear of the cloth itself, not of the stitching on it.
    ctx["shorts_tree"] = common.bvh_of(obj)
    ctx["shorts"] = obj

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


# --- skirt -------------------------------------------------------------------

SKIRT_RISE = 0.010                # how far above the sweater's waist the waistband stands
SKIRT_BAND = 0.044                # the waistband's height
SKIRT_HEM = 0.470                 # height of the hem above the ground: mid-calf, clear of the boots
SKIRT_WAIST = (0.176, 0.122)      # half-width and half-depth of the waistband, when no sweater says otherwise
SKIRT_SWEEP = (0.350, 0.330)      # the same at the hem
SKIRT_TIERS = (0.31, 0.65, 1.0)   # where each tier ends, as a fraction of the way from waistband to hem
SKIRT_GATHER = 0.010              # how far each tier stands out from the seam it is gathered into
SKIRT_FOLDS = (12, 18, 24)        # folds round each tier (full level)
SKIRT_LINING = 0.014              # how far inside the cloth its dark lining hangs


def _skirt_weights(co, axis_y, hip, knee):
    """Skirt weights by place: the hips at the waist, and below them each leg's share of what hangs beside it.

    Cloth in front of a leg goes most of the way with it, so a knee carries
    the skirt up; cloth behind goes with it less, so a stride does not fold
    the back of the skirt into the body.
    """
    theta = np.arctan2(co[:, 0], -(co[:, 1] - axis_y))
    # Cloth straight in front of a leg is that leg's; only a narrow strip down the middle is shared.
    left = smoothstep(-0.3, 0.3, np.sin(theta))
    front = 0.5 + 0.5 * np.cos(theta)
    leg = smoothstep(hip + 0.03, hip - 0.22, co[:, 2]) * (0.50 + 0.45 * front)
    shin = smoothstep(knee + 0.05, knee - 0.10, co[:, 2]) * 0.75
    spine = smoothstep(hip + 0.14, hip + 0.21, co[:, 2]) * 0.5
    return {
        "Hips": (1.0 - leg) * (1.0 - spine), "Spine": (1.0 - leg) * spine,
        "UpperLeg.L": leg * left * (1.0 - shin), "LowerLeg.L": leg * left * shin,
        "UpperLeg.R": leg * (1.0 - left) * (1.0 - shin), "LowerLeg.R": leg * (1.0 - left) * shin,
    }


def build_skirt(ctx):
    """A tiered gingham skirt to mid-calf, as an alternative to the shorts: waistband, three gathered tiers, a ruffled hem.

    The cloth is painted, not flat: every face is laid on the atlas's patch
    of gingham at one scale (atlas.gingham_uv), each tier as a straight strip
    of cloth would be, so the checks are true along a tier's hem and crowd
    together where it is gathered into the seam above.

    Nothing is worn under it and the hips are hidden while it is on, so it
    carries its own darkness: a lining a little inside the cloth, a loose
    dark shell over the hidden hips that moves with the legs, a membrane
    joining the two and a floor under the sweater's hem, all in the `void`
    swatch. Looking up the skirt shows
    legs coming out of the dark, not a hollow body.
    """
    armature, detail, level = ctx["armature"], ctx["detail"], ctx["level"]
    full = detail >= 1.0
    hip = np.array(rig.head_of(armature, "UpperLeg.L"))
    knee = np.array(rig.head_of(armature, "LowerLeg.L"))
    tube = ctx.get("sweater_tube")
    if tube is not None:
        # Outside the sweater, which hangs to below the waistband.
        waist_size = (tube["bottom"][0] * 1.03 + 0.005, tube["bottom"][2] * 1.03 + 0.005)
        waist_y, top = tube["bottom"][1], tube["waist"] + SKIRT_RISE
    else:
        waist_size, waist_y, top = SKIRT_WAIST, hip[1] - 0.02, hip[2] + 0.215
    hem_y = hip[1] - 0.008
    band_low = top - SKIRT_BAND
    columns = 72 if full else 16
    per_tier = 5 if full else 2
    thetas = np.arange(columns + 1) * (2.0 * math.pi / columns)
    period = atlas.GINGHAM_PERIOD / atlas.GINGHAM_SCALE

    def oval(f, scale=1.0, extra=0.0):
        """Half-width, half-depth, centre and squareness of the skirt, `f` of the way from waistband to hem."""
        spread = f ** 0.85
        return (waist_size[0] + (SKIRT_SWEEP[0] - waist_size[0]) * spread, waist_size[1] + (SKIRT_SWEEP[1] - waist_size[1]) * spread,
                waist_y + (hem_y - waist_y) * spread, SWEATER_SQUARE + (2.0 - SWEATER_SQUARE) * min(1.0, f * 2.5), scale, extra)

    def ring(z, shape, wave=None):
        half_width, half_depth, centre_y, square, scale, extra = shape
        points = []
        for theta in thetas[:-1]:
            x, y = math.sin(theta), -math.cos(theta)
            rho = float(_oval(x, y, half_width, half_depth, square))
            radius = scale / rho + extra + (wave[0] * math.cos(wave[1] * theta + wave[2]) if wave else 0.0)
            lift = wave[3] * math.cos(wave[1] * theta + wave[2] + 1.2) if wave else 0.0
            points.append((x * radius, centre_y + y * radius, z + lift))
        return points

    def girth(shape):
        points = np.array(ring(0.0, shape))
        return float(np.linalg.norm(points - np.roll(points, 1, axis=0), axis=1).sum())

    part = common.Part("Outfit_Skirt", "outfit.skirt.bottom")
    painted = {}        # face index -> {vertex index: (s, t) in metres of cloth}

    def strip(rows, repeats):
        """Lofts rings of (vertex ids, t) into gingham; `repeats` is how many checks go round."""
        for (upper, t0), (lower, t1) in zip(rows, rows[1:]):
            for j in range(columns):
                k = (j + 1) % columns
                s0, s1 = j / columns * repeats * period, (j + 1) / columns * repeats * period
                part.face((upper[j], lower[j], lower[k], upper[k]), "sweater-stripe")
                painted[len(part.faces) - 1] = {upper[j]: (s0, t0), lower[j]: (s0, t1), lower[k]: (s1, t1), upper[k]: (s1, t0)}

    # The waistband, with an edge turned in at the top to meet the sweater.
    band = oval(0.0)
    repeats = max(1, int(round(girth(band) / period)))
    rim = part.verts(ring(top, band))
    lip = part.verts(ring(top - 0.003, oval(0.0, scale=0.955)))
    part.loft([rim, lip], "sweater-stripe", flip=False)
    seam = part.verts(ring(band_low, band))
    strip([(rim, 0.0), (seam, SKIRT_BAND)], repeats)

    # The tiers: each a strip of cloth gathered into the seam above it and fuller than the last.
    previous, start = seam, 0.0
    drop = band_low - SKIRT_HEM
    for tier, end in enumerate(SKIRT_TIERS):
        last = tier == len(SKIRT_TIERS) - 1
        repeats = max(1, int(round(girth(oval(end)) / period)))
        folds, phase = SKIRT_FOLDS[tier], tier * 1.3
        rows, t, before = [(previous, -0.004)], 0.0, None
        for row in range(per_tier + 1):
            g = row / per_tier
            f = start + (end - start) * g
            z = band_low - drop * f - (0.005 if row == 0 else 0.0)
            # Out from the seam at once, a belly below it, and back in to where the next seam will be.
            puff = SKIRT_GATHER * (1.0 - g) + 0.007 * 4.0 * g * (1.0 - g)
            if last:
                puff += 0.010 * g
            wave = None
            if full:
                depth = (0.004 + 0.018 * g) if last else (0.003 + 0.011 * g)
                wave = (depth, folds, phase, 0.007 * g if last and row == per_tier else 0.0)
            shape = oval(f, extra=puff)
            mean = 0.5 * (shape[0] + shape[1])
            if before is not None:
                t += math.hypot(before[0] - z, before[1] - mean)
            before = (z, mean)
            rows.append((part.verts(ring(z, shape, wave)), t))
        strip(rows, repeats)
        previous, start = rows[-1][0], end

    # The lining: the inside of the skirt, dark, a little way in from the cloth and not gathered.
    lining = []
    inner_columns = slice(None, None, 2) if full else slice(None)
    for f in (-SKIRT_BAND / drop * 0.8, 0.0, 0.33, 0.66, 1.0) if full else (-SKIRT_BAND / drop * 0.8, 0.5, 1.0):
        shape = oval(max(f, 0.0))
        z = band_low - drop * f + (0.012 if f >= 1.0 else 0.0)
        shrink = 1.0 - SKIRT_LINING / (0.5 * (shape[0] + shape[1]))
        lining.append(part.verts(ring(z, oval(max(f, 0.0), scale=shrink))[inner_columns]))
    part.loft(lining, "void", flip=False)
    # A lid under the waistband, seen from above when nothing is tucked into the skirt: from the
    # lining in to an oval that lies inside the waist itself.
    lid = part.verts(ring(band_low + SKIRT_BAND * 0.8, (0.085, 0.052, waist_y - 0.012, 2.0, 1.0, 0.0))[inner_columns])
    part.loft([lining[0], lid], "void", flip=False)
    # A floor across the skirt under the sweater's hem, seen from below: from the lining in to an
    # oval that lies inside the hips. Without it the hem of what is tucked in shows up the skirt.
    if tube is not None:
        z = tube["low"] - 0.014
        shape = oval((band_low - z) / drop)
        shrink = 1.0 - SKIRT_LINING / (0.5 * (shape[0] + shape[1]))
        outer = part.verts(ring(z, oval((band_low - z) / drop, scale=shrink))[inner_columns])
        inner = part.verts(ring(z, (0.105, 0.065, hip[1] - 0.010, 2.0, 1.0, 0.0))[inner_columns])
        part.loft([outer, inner], "void", flip=True)

    obj = part.to_object(ctx["collection"], armature, ctx["material"], ctx["palette"], ctx["tiles"], sharp_angle=55.0, recalc=False)
    mesh = obj.data
    uv = common.get_uv(mesh, cass_spec.UV_PALETTE)
    for index, corners in painted.items():
        polygon = mesh.polygons[index]
        loops = list(polygon.loop_indices)
        cloth = np.array([corners[mesh.loops[loop].vertex_index] for loop in loops])
        uv[loops] = atlas.gingham_uv(cloth)
    common.set_uv(mesh, cass_spec.UV_PALETTE, uv)
    common.set_weights(obj, _skirt_weights(common.coords(mesh), hem_y, hip[2], knee[2]))

    # The dark shell over the hips, cut from the body like the shorts but loose and shapeless,
    # and a membrane from its waist out to the lining. It moves with the legs.
    shell = Shell(ctx["skin"], SHORTS_SEGMENTS, "void")
    shell.inflate(0.014)
    waist = shell.cut_rim(shell.loop_where(lambda c: abs(c[0]) < 0.05 and c[2] > hip[2] + 0.05), (0, 0, 1))
    shell.cut((0.0, hip[1], hip[2] - 0.135), (0, 0, -1))
    shell.relax(_relaxed(14, detail))
    shell.clear_skin(0.008)
    level_z = float(np.mean([v.co.z for v in waist]))
    f = (band_low - level_z) / drop
    shape = oval(max(f, 0.0))
    shrink = 1.0 - (SKIRT_LINING - 0.003) / (0.5 * (shape[0] + shape[1]))
    shell.band(waist, [(lambda co: _oval_ring(co, shape[2], shape[0] * shrink, shape[1] * shrink, level_z, shape[3]), "void")])
    void = shell.to_object("Outfit_SkirtVoid", "outfit.skirt.bottom", ctx["collection"], armature, ctx["material"],
                           ctx["palette"], ctx["tiles"])
    common.join(obj, void)
    print(f"skirt: waistband {np.round(waist_size, 3)} at {top:.3f}, hem at {SKIRT_HEM:.3f}")
    return obj


# --- the layer worn over the sweater: a suede vest and a neckerchief -------------

VEST_SEGMENTS = ("Chest_01", "Chest_02", "Spine", "Shoulder")
VEST_EASE = 0.007                 # room between the vest and the sweater under it
VEST_GAP = 0.034                  # half the width of the open front
VEST_NECK = 0.078                 # half the width of the front opening where it reaches the shoulders
VEST_DROP = 0.034                 # how far below the waist the vest's hem hangs
VEST_FRINGE = 0.046               # the length of the fringe on the hem
BANDANA_ROLL = 0.012              # the radius of the neckerchief where it is rolled round the neck
BANDANA_POINT = 0.125             # how far below the neckline its point hangs on the chest


def _star(surface, axis, azimuth, z, size):
    """A five-pointed star on a part's surface, as hits for Applique.patch."""
    hits = []
    for k in range(10):
        radius = size * (1.0 if k % 2 == 0 else 0.42)
        angle = math.radians(90.0 + 36.0 * k)
        hits.append(surface.around(axis, azimuth + math.degrees(radius * math.cos(angle) / 0.14), z + radius * math.sin(angle)))
    return hits


def _build_bandana(ctx, under):
    """A neckerchief: rolled round the neck over the sweater's collar, its point hanging on the chest, tied behind."""
    full = ctx["detail"] >= 1.0
    axis, radius, height = ctx["sweater_collar"]
    part = common.Part("Outfit_VestBandana", "outfit.vest.layer")

    def collar(bearing, out=0.0, up=0.0):
        """A point on the sweater's neckline (bearing in degrees, 0 at the front), moved out and up."""
        b = math.radians(bearing)
        r = radius(b) + out
        return np.array((r * math.sin(b), axis[1] - r * math.cos(b), height(b) + up))

    # The roll: a ring round the neck, fatter at the front where the cloth is bunched.
    turns = 20 if full else 10
    sides = 6 if full else 4
    rings = []
    for k in range(turns):
        bearing = 360.0 * k / turns
        middle = collar(bearing, 0.004, 0.008)
        outward = np.array((math.sin(math.radians(bearing)), -math.cos(math.radians(bearing)), 0.0))
        fat = BANDANA_ROLL * (0.85 + 0.25 * (0.5 + 0.5 * math.cos(math.radians(bearing))))
        rings.append(part.verts([middle + outward * (fat * math.cos(a)) + np.array((0.0, 0.0, fat * 0.8 * math.sin(a)))
                                 for a in np.arange(sides) * (2.0 * math.pi / sides)]))
    part.loft(rings + [rings[0]], lambda r, s: "bandana-shade" if s >= sides // 2 else "bandana", flip=True)

    # The point: a triangle of cloth from the roll down the chest, lying on the sweater.
    spread = 74.0
    columns = 9 if full else 5
    rows = 5 if full else 2
    tip = collar(0.0, 0.0, -BANDANA_POINT)
    laid = []           # per row, per column: (the point's height, its bearing from the axis, its distance from it)
    for row in range(rows + 1):
        t = row / rows
        line = []
        for column in range(columns):
            bearing = -spread + 2.0 * spread * column / (columns - 1)
            start = collar(bearing, 0.012, 0.002)
            corner = collar(math.copysign(spread, bearing) if bearing else 0.0, 0.012, 0.002)
            end = tip + (corner - tip) * (abs(bearing) / spread)
            point = start + (end - start) * t
            # Laid on what is under it, the sweater or the vest over that: found from in front,
            # along the line out from the neck's axis.
            outward = np.array((point[0], point[1] - axis[1], 0.0))
            outward = outward / max(np.linalg.norm(outward), 1e-9)
            hits = [tree.ray_cast(Vector(point + outward * 0.25), Vector(-outward), 0.5) for tree in under]
            hits = [found for found in hits if found[0] is not None]
            if hits:
                point = np.array(min(hits, key=lambda found: found[3])[0])
            line.append((point[2], outward, float(np.hypot(point[0], point[1] - axis[1]))))
        laid.append(line)
    # The cloth cannot follow a step in what it lies on (the vest's edge over the sweater), so
    # each point stands as far out as the furthest of its neighbours, and a little more.
    grid = []
    for row in range(rows + 1):
        line = []
        for column in range(columns):
            near = [laid[r][c][2] for r in range(max(0, row - 1), min(rows, row + 1) + 1)
                    for c in range(max(0, column - 1), min(columns - 1, column + 1) + 1)]
            z, outward, _distance = laid[row][column]
            reach = max(near) + 0.008
            line.append(part.vert((outward[0] * reach, axis[1] + outward[1] * reach, z)))
        grid.append(line)
    for row in range(rows):
        for column in range(columns - 1):
            quad = (grid[row][column], grid[row + 1][column], grid[row + 1][column + 1], grid[row][column + 1])
            part.face(quad, "bandana-shade" if row == rows - 1 and full else "bandana")

    # The knot behind: two short ends hanging from the roll.
    for sign in (1.0, -1.0):
        root = collar(180.0, 0.010, 0.006)
        guide = [root, root + (sign * 0.018, 0.016, -0.022), root + (sign * 0.030, 0.020, -0.062)]
        sweep.strand(part, guide, [0.012, 0.014, 0.003], 0.30, 3 if full else 2, ctx["level"], "bandana", "bandana-shade",
                     facing=(0.0, 1.0, 0.2))
    obj = part.to_object(ctx["collection"], ctx["armature"], ctx["material"], ctx["palette"], ctx["tiles"], sharp_angle=50.0,
                         recalc=False)
    common.set_weights(obj, common.SkinSource(ctx["skin"]).sample(common.coords(obj.data)))
    return obj


def build_vest(ctx):
    """A layer over the sweater, on one tile: an open suede vest with a fringed hem, and a red neckerchief.

    The vest is cut from the body like the sweater, shaped by the sweater's
    own drape and then stood off the sweater's surface, so it moves with it
    vertex for vertex. Its front is cut open down the middle and into a V up
    to the shoulders.
    """
    armature, detail = ctx["armature"], ctx["detail"]
    full = detail >= 1.0
    shoulder = np.array(rig.head_of(armature, "UpperArm.L"))
    chest = np.array(rig.head_of(armature, "Chest"))
    neck = np.array(rig.head_of(armature, "Neck"))
    armpit = shoulder[2] - 0.065
    sweater_tree = common.bvh_of(ctx["sweater"])
    tube = ctx["sweater_tube"]

    shell = Shell(ctx["skin"], VEST_SEGMENTS, "vest")
    shell.inflate(0.010)
    shell.reshape(ctx["sweater_drape"])
    hem = shell.cut_rim(shell.loop_where(lambda c: abs(c[0]) < 0.1 and c[2] < chest[2] - 0.05), (0, 0, -1))
    # The armholes are cut clean where the body is fine enough to be cut there. On the coarse
    # body the shoulder is a few faces wide, and a plane clear of its saw teeth would take the
    # shoulder with them; there the armhole keeps the edge of the body's segment.
    for sign in (1.0, -1.0) if full else ():
        shell.cut_fitted(shell.loop_where(lambda c, sign=sign: c[0] * sign > 0.08 and c[2] > armpit - 0.02), (sign, 0, 0), margin=0.008)
    # The neck: a plane through the nape, lower than the sweater's own, so its collar shows.
    nape = np.array((0.0, neck[1] + 0.066, neck[2] + 0.044))
    front = np.array((0.0, neck[1] - 0.100, neck[2] - 0.030))
    slope = front - nape
    opening = np.array((0.0, slope[2], -slope[1]))
    opening = opening / np.linalg.norm(opening) * (1.0 if opening[2] > 0 else -1.0)

    def bend(co, amount):
        out = co.copy()
        out[:, 2] -= amount * NECK_CLIMB * np.minimum(np.abs(co[:, 0]), 0.2) ** 2
        return out

    shell.reshape(lambda co: bend(co, 1.0))
    collar = shell.cut_within(shell.loop_where(lambda c: abs(c[0]) < 0.05 and c[2] > neck[2] - 0.05), nape, opening)
    shell.reshape(lambda co: bend(co, -1.0))
    shell.smooth_loop(collar, 6)
    shell.relax(_relaxed(16, detail))
    shell.reshape(ctx["sweater_drape"])
    shell.clear_skin(0.008)
    # Now it is the sweater's shape; stand it off the sweater.
    shell.inflate(VEST_EASE * 0.6)
    for _ in range(2):
        shell.clear_of(sweater_tree, VEST_EASE)

    # The front: open down the middle, and widening from the chest up to the shoulders.
    waist = tube["waist"]
    for vertex in hem:
        vertex.co.z = waist
    low, high = armpit - 0.030, neck[2] + 0.030
    lean = (VEST_NECK - VEST_GAP) / (high - low)
    centre_y = tube["bottom"][1]

    def gap(z):
        return VEST_GAP + max(0.0, z - low) * lean

    planes = []
    for sign in (1.0, -1.0):
        planes.append(((sign * VEST_GAP, 0.0, low), (sign, 0.0, 0.0)))
        planes.append(((sign * VEST_GAP, 0.0, low), (sign, 0.0, -lean)))
    shell.cut_out(planes, where=lambda c: c[1] < centre_y, inside=lambda c: abs(c[0]) < gap(c[2]))

    # The hem hangs a little below the waist, following the sweater's tube, and ends in fringe.
    edge = [v for v in shell.bm.verts if v.is_boundary and abs(v.co.z - waist) < 1e-4]
    half_width, tube_y, half_depth = tube["bottom"]
    # Wide enough to hang outside the skirt's waistband as well, when that is worn.
    scale = 1.012 + (VEST_EASE + 0.007) / half_width
    made = []
    shell.band(edge, [
        (lambda co: _oval_ring(co, tube_y, half_width * scale, half_depth * scale, waist - VEST_DROP * 0.5), "vest"),
        (lambda co: _oval_ring(co, tube_y, half_width * (scale - 0.004), half_depth * (scale - 0.004), waist - VEST_DROP), "vest-shade"),
    ], made)
    shell.fringe(made[-1], "vest", VEST_FRINGE, 0.011 if full else 0.030, 0.008 if full else 0.020)
    obj = shell.to_object("Outfit_Vest", "outfit.vest.layer", ctx["collection"], armature, ctx["material"],
                          ctx["palette"], ctx["tiles"])

    if full:
        surface = Surface(obj)
        applique = Applique(surface)
        axis = (0.0, centre_y)
        # Yokes: a stitched line across the back that dips to the middle, and one down each front.
        back = [surface.around(axis, 180.0 + a, armpit + 0.060 - 0.050 * (1.0 - abs(a) / 78.0) ** 1.5) for a in np.linspace(-78.0, 78.0, 15)]
        applique.ribbon(back, 0.004, "boot-stitch")
        for sign in (1.0, -1.0):
            line = [surface.around(axis, sign * (26.0 + 46.0 * t), armpit - 0.020 + 0.085 * t ** 1.3) for t in np.linspace(0.0, 1.0, 8)]
            applique.ribbon(line, 0.004, "boot-stitch")
        # A brass star on the left front.
        applique.patch(_star(surface, axis, 33.0, armpit - 0.045, 0.024), "boot-stitch", lift=0.003)
        applique.apply(ctx["palette"], ctx["tiles"], "outfit.vest.layer")

    common.join(obj, _build_bandana(ctx, [sweater_tree, common.bvh_of(obj)]))
    return obj


# --- boots -------------------------------------------------------------------

BOOT_TOP = 0.425          # height of the shaft's rim at the sides, where the pull straps are
BOOT_DIP = 0.040          # how far the rim dips at the front and the back
BOOT_OFFSET = 0.012       # leather thickness over the skin
BOOT_TOE = 0.034          # how far the toe reaches past the toes
HEEL_HEIGHT = 0.040       # the stacked heel
HEEL_UNDERCUT = 0.016     # how far the heel's back slopes forward on its way to the ground
FOOT = (0.050, 0.066)     # half-width of the boot at the ball of the foot, and the height of the vamp there
TOE_HEIGHT = 0.030        # the height of the toe box near its tip
HEEL_CUP = (0.041, 0.009)  # half-width of the boot round the heel, and how far its back stands behind the skin's
TOE_SPRING = 0.007        # how far the tip of the sole lifts off the ground
WELT = 0.011              # the thickness of the sole's edge


def _shin(armature, z):
    """The point on the shin bone's line at a height."""
    knee = np.array(rig.head_of(armature, "LowerLeg.L"))
    ankle = np.array(rig.head_of(armature, "Foot.L"))
    return knee + (ankle - knee) * ((knee[2] - z) / (knee[2] - ankle[2]))


def _boot_path(armature, toe, count):
    """Centre line from the shaft's rim down the shin, round the ankle in a wide bend, and out along the foot.

    `toe` is the y of the boot's tip. Stations are spread along it by length, but only thinly
    down the straight of the shaft, which needs few.
    """
    ankle = np.array(rig.head_of(armature, "Foot.L"))
    ball = np.array(rig.head_of(armature, "Toes.L"))
    knots = np.array([
        _shin(armature, BOOT_TOP), _shin(armature, BOOT_TOP - 0.09), _shin(armature, ankle[2] + 0.15),
        _shin(armature, ankle[2] + 0.085),
        _shin(armature, ankle[2] + 0.035) + (0.0, -0.006, 0.0),
        ankle + (0.0, -0.030, -0.012),
        (ankle[0], ankle[1] + (ball[1] - ankle[1]) * 0.52, 0.068),
        (ankle[0], ball[1], 0.036),
        (ankle[0], (ball[1] + toe) / 2.0, 0.028),
        (ankle[0], toe + 0.006, 0.022),
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
    steps = np.linalg.norm(np.diff(dense, axis=0), axis=1)
    middle = (dense[:-1, 2] + dense[1:, 2]) / 2.0
    # The first few centimetres keep their full share, for the scalloped rim.
    straight = (middle > ankle[2] + 0.11) & (middle < BOOT_TOP - 0.05)
    lengths = np.concatenate([[0.0], np.cumsum(steps * np.where(straight, 0.38, 1.0))])
    targets = np.linspace(0.0, 1.0, count) * lengths[-1]
    points = np.stack([np.interp(targets, lengths, dense[:, k]) for k in range(3)], axis=1)
    tangents = np.stack([np.interp(targets, lengths, np.gradient(dense[:, k])) for k in range(3)], axis=1)
    tangents /= np.linalg.norm(tangents, axis=1, keepdims=True)
    return points, tangents, ankle, ball


def _hull(points):
    """Convex hull of 2D points, counter-clockwise."""
    points = sorted(map(tuple, np.round(points, 5)))
    def half(sequence):
        chain = []
        for p in sequence:
            while len(chain) >= 2 and (chain[-1][0] - chain[-2][0]) * (p[1] - chain[-2][1]) - (chain[-1][1] - chain[-2][1]) * (p[0] - chain[-2][0]) <= 0:
                chain.pop()
            chain.append(p)
        return chain[:-1]
    return np.array(half(points) + half(reversed(points)))


def _outline(hull, count):
    """`count` points round a convex outline, evenly spaced by bearing from its middle."""
    middle = (hull.min(axis=0) + hull.max(axis=0)) / 2.0
    out = []
    for k in range(count):
        angle = 2.0 * math.pi * (k + 0.5) / count
        direction = np.array((math.cos(angle), math.sin(angle)))
        reach = 0.0
        for a, b in zip(hull, np.roll(hull, -1, axis=0)):
            edge = b - a
            denominator = direction[0] * edge[1] - direction[1] * edge[0]
            if abs(denominator) < 1e-12:
                continue
            offset = a - middle
            along = (offset[0] * edge[1] - offset[1] * edge[0]) / denominator
            across = (offset[0] * direction[1] - offset[1] * direction[0]) / denominator
            if along > 0.0 and -1e-9 <= across <= 1.0 + 1e-9:
                reach = max(reach, along)
        out.append(middle + direction * reach)
    return np.array(out)


def _rim(azimuth):
    """Height of the shaft's rim by bearing (degrees, 0 at the front): high at the sides, a dip front and back."""
    return BOOT_TOP - BOOT_DIP * abs(math.cos(math.radians(azimuth))) ** 2.4


# The stitched pattern on each side of the shaft, as (bearing, height) on a unit square, one
# half; the other half mirrors it. A flame with a waved edge, and a leaf inside it.
BOOT_FLAME = ((0.0, 1.0), (0.16, 0.84), (0.46, 0.74), (0.40, 0.60), (0.80, 0.44), (0.62, 0.28), (0.30, 0.13), (0.0, 0.0))
BOOT_LEAF = ((0.0, 0.80), (0.20, 0.60), (0.24, 0.44), (0.14, 0.30), (0.0, 0.20))


def build_boots(ctx):
    """Mid-calf cowboy boots: a scalloped shaft with pull straps and stitched flames, a pointed toe, an underslung stacked heel."""
    armature, skin, detail = ctx["armature"], ctx["skin"], ctx["detail"]
    full = detail >= 1.0
    rings = 24 if full else 11
    around = 20 if full else 10
    tree = common.bvh_of(skin)
    feet = common.coords(skin.data)
    toe = feet[feet[:, 2] < 0.08][:, 1].min() - BOOT_TOE
    points, tangents, ankle, ball = _boot_path(armature, toe, rings)
    centre_x = ankle[0]
    heel_front = ankle[1] - 0.024

    def floor(y):
        """The underside: on the ground under the ball, lifting a little to the tip, and rising over the arch to the heel."""
        spring = TOE_SPRING * np.clip((ball[1] - y) / (ball[1] - toe), 0.0, 1.0) ** 2
        return spring + HEEL_HEIGHT * smoothstep(ball[1] + 0.030, heel_front, y)

    def last(y, angle):
        """A point of the boot's own cross-section along the foot: a flat sole with a welt, a domed vamp."""
        u = float(np.clip((ball[1] - y) / (ball[1] - toe), 0.0, 1.0))
        # Drawn in from the ball to a blunt point.
        half = FOOT[0] * math.sqrt(max(1.0 - (u * 0.985) ** 2.6, 0.0))
        low = float(floor(y))
        top = FOOT[1] + (TOE_HEIGHT - FOOT[1]) * float(smoothstep(0.0, 0.9, u))
        # The toe box comes down as it narrows, so the tip is not a blunt end.
        top = low + WELT + (top - WELT) * (0.60 + 0.40 * half / FOOT[0])
        middle = low + (top - low) * 0.42
        c, s = math.cos(angle), math.sin(angle)
        side = half * math.copysign(abs(c) ** 0.8, c)
        if s >= 0.0:
            return side, middle + (top - middle) * s ** 0.9
        if s <= -0.55:
            return half * 1.03 * float(np.clip(c / 0.835, -1.0, 1.0)), low
        # Between the side of the upper and the sole: the welt, standing out a little.
        down = min(1.0, -s / 0.30)
        return side + (math.copysign(half * 1.03, c) - side) * down, middle + (low + WELT - middle) * down

    side = np.array((1.0, 0.0, 0.0))
    angles = np.arange(around) * (2.0 * math.pi / around)
    radii = np.empty((rings, around))
    for index, (centre, tangent) in enumerate(zip(points, tangents)):
        front = np.cross(tangent, side)
        row = np.empty(around)
        for k, angle in enumerate(angles):
            direction = math.cos(angle) * side + math.sin(angle) * front
            found = tree.ray_cast(Vector(centre), Vector(direction), 0.14)
            row[k] = found[3] if found[0] is not None else np.nan
        fallback = np.nanmedian(row) if np.isfinite(row).any() else 0.04
        radii[index] = np.clip(np.where(np.isfinite(row), row, fallback), 0.015, 0.075) + BOOT_OFFSET
    # Even the shape out along the boot and round it, so no ring stands out as a crease or a band.
    def even(radii):
        radii[1:-1] = (radii[:-2] + 2.0 * radii[1:-1] + radii[2:]) / 4.0
        return (np.roll(radii, 1, axis=1) + 2.0 * radii + np.roll(radii, -1, axis=1)) / 4.0

    radii = even(even(radii))
    # The heel is a cup of the boot's own, not the shape of the skin's heel (which the rays, cast
    # from in front of it, mostly miss): behind the ankle the rings reach out to a box, flat at the
    # back and underneath, and the evening-out afterwards rounds its corners.
    back = feet[feet[:, 2] < 0.10][:, 1].max() + HEEL_CUP[1]
    for index, (centre, tangent) in enumerate(zip(points, tangents)):
        near = 1.0 - float(smoothstep(ankle[2] + 0.015, ankle[2] + 0.085, centre[2]))
        if near <= 0.0:
            continue
        front = np.cross(tangent, side)
        for k, angle in enumerate(angles):
            direction = math.cos(angle) * side + math.sin(angle) * front
            if direction[1] <= 0.05:
                continue
            reach = (back - centre[1]) / direction[1]
            if direction[2] < -1e-6:
                # Aimed a little under the heel's height: what is left below it after the rounding is cut off flat.
                reach = min(reach, (HEEL_HEIGHT - 0.008 - centre[2]) / direction[2])
            if abs(direction[0]) > 1e-6:
                reach = min(reach, HEEL_CUP[0] / abs(direction[0]))
            share = near * float(smoothstep(0.05, 0.35, direction[1]))
            radii[index, k] += max(reach - radii[index, k], 0.0) * share
    radii = even(radii)

    shape = np.empty((rings, around, 3))
    for index, (centre, tangent) in enumerate(zip(points, tangents)):
        front = np.cross(tangent, side)
        # A coarse shaft is a prism, whose flat sides pass inside the round calf; it stands off further.
        flare = (0.008 if full else 0.017) * (1.0 - smoothstep(0.0, 0.14, BOOT_TOP - centre[2])) + (0.0 if full else 0.004)
        # Down the leg the boot is the leg's shape; from the instep on it turns into its own.
        own = float(smoothstep(ankle[1] - 0.040, ball[1] + 0.030, centre[1])) if centre[2] < ankle[2] + 0.02 else 0.0
        # The rim is scalloped, and the rings under it are drawn down with it, less and less, so
        # the leather does not fold. Where it dips it also stands off the leg a little more: the
        # radii were measured higher up, and the calf is fuller below.
        scallop = 1.0 - float(smoothstep(0.0, 0.10, BOOT_TOP - centre[2]))
        for k, angle in enumerate(angles):
            direction = math.cos(angle) * side + math.sin(angle) * front
            dip = (BOOT_TOP - _rim(math.degrees(math.atan2(math.cos(angle), math.sin(angle))))) * scallop
            measured = centre + direction * (radii[index, k] + flare + 0.35 * dip) - (0.0, 0.0, dip)
            if own > 0.0:
                x, z = last(centre[1], angle)
                measured = measured * (1.0 - own) + np.array((centre[0] + x, centre[1], z)) * own
            shape[index, k] = measured
    shape[..., 2] = np.maximum(shape[..., 2], floor(shape[..., 1]))

    tip = np.array((centre_x, toe, float(floor(toe)) + TOE_HEIGHT * 0.42))
    part = common.Part("Outfit_Boots", "outfit.default.shoes")
    for sign in (1.0, -1.0):
        mirror = np.array((sign, 1.0, 1.0))
        ring_ids = [part.verts(ring * mirror) for ring in shape]
        if full:
            # The rim has an edge: the leather turns over and a little way down inside.
            inner = shape[0].copy()
            inner[:, :2] = points[0][:2] + (inner[:, :2] - points[0][:2]) * 0.90
            inner[:, 2] -= 0.007
            ring_ids = [part.verts(inner * mirror)] + ring_ids
        first = len(ring_ids) - rings

        def swatch(r, i):
            if r < first:
                return "boot-shade"
            r -= first
            corners = (shape[r][i], shape[r][(i + 1) % around], shape[r + 1][i], shape[r + 1][(i + 1) % around])
            if all(c[2] <= floor(c[1]) + WELT + 0.0015 for c in corners):
                return "boot-sole"
            return "boot"

        part.loft(ring_ids, swatch, flip=sign < 0)
        cap = part.fan(ring_ids[-1], tip * mirror, "boot", flip=sign < 0)
        # The fan's lower faces are the tip of the sole.
        for index in range(len(part.faces) - around, len(part.faces)):
            k = index - (len(part.faces) - around)
            if all(c[2] <= floor(c[1]) + WELT + 0.0015 for c in (shape[-1][k], shape[-1][(k + 1) % around])):
                part.swatches[index] = "boot-sole"

        # The stacked heel. Its top is the outline of the boot's own heel, so the two meet edge to
        # edge; it tapers to the ground, its back sloping forward under the boot, in layers of
        # leather that show as bands. It is cut square at the front.
        seat = shape[(shape[..., 1] > heel_front) & (shape[..., 2] <= floor(shape[..., 1]) + 0.003)]
        hull = _hull(seat[:, :2] * (sign, 1.0)) if len(seat) >= 3 else np.zeros((0, 2))
        if len(hull) < 5:
            # A coarse boot has too few points under the heel to give an outline; use a plain one.
            cx, back = centre_x * sign, ankle[1] + 0.060
            hull = np.array([(cx - 0.034, heel_front), (cx + 0.034, heel_front), (cx + 0.037, back - 0.016),
                             (cx + 0.020, back), (cx - 0.020, back), (cx - 0.037, back - 0.016)])
        outline = _outline(hull, 14 if full else 6)
        middle = (outline.min(axis=0) + outline.max(axis=0)) / 2.0
        layers = []
        bands = (1.0, 0.70, 0.66, 0.36, 0.32, 0.0) if full else (1.0, 0.0)
        for fraction in bands:
            taper = 1.0 - fraction
            ring = middle + (outline - middle) * (1.03 - 0.20 * taper) + (0.0, -HEEL_UNDERCUT * taper)
            ring[:, 1] = np.maximum(ring[:, 1], heel_front + 0.004 - HEEL_UNDERCUT * 0.35 * taper)
            layers.append(part.verts([(x, y, HEEL_HEIGHT * fraction + (0.003 if fraction == 1.0 else 0.0)) for x, y in ring]))
        part.loft(layers, lambda r, i: "boot-shade" if r in (1, 3) else "boot-sole")
        part.face(layers[-1], "boot-sole")
    obj = part.to_object(ctx["collection"], armature, ctx["material"], ctx["palette"], ctx["tiles"], sharp_angle=50.0)
    common.set_weights(obj, common.SkinSource(skin).sample(common.coords(obj.data)))

    if full:
        surface = Surface(obj)
        applique = Applique(surface)
        for sign in (1.0, -1.0):
            def shaft(z):
                at = _shin(armature, z)
                return (at[0] * sign, at[1])

            def wall(azimuth, z):
                """The shaft's surface at a bearing and height, found from inside: a ray from outside could start beyond the other boot."""
                a = math.radians(azimuth)
                outward = np.array((math.sin(a), -math.cos(a), 0.0))
                axis = shaft(z)
                origin = Vector((axis[0], axis[1], z)) + Vector(outward) * 0.012
                for _ in range(3):
                    location, normal, _index, _distance = surface.tree.ray_cast(origin, Vector(outward), 0.14)
                    if location is None:
                        return None
                    # The turned-over edge of the rim faces the axis; the wall behind it is the one wanted.
                    if normal.dot(Vector(outward)) > 0.0:
                        return np.array(location), np.array(normal)
                    origin = location + Vector(outward) * 0.0005
                return None

            def line(points, width=0.0034, closed=False):
                applique.ribbon([wall(a, z) for a, z in points], width, "boot-stitch", closed=closed)

            # Piping under the scalloped rim, and a second row of stitching under that.
            turn = np.linspace(0.0, 360.0, 37)[:-1]
            line([(a, _rim(a) - 0.014) for a in turn], width=0.0055, closed=True)
            line([(a, _rim(a) - 0.029) for a in turn], width=0.0026, closed=True)
            # The shaft's stitched flames, one on each side.
            for at in (90.0, -90.0):
                for motif, width in ((BOOT_FLAME, 0.0034), (BOOT_LEAF, 0.0028)):
                    half = [(u * 27.0, 0.205 + v * 0.175) for u, v in motif]
                    whole = half + [(-a, z) for a, z in half[-2:0:-1]]
                    dense = []
                    for (a0, z0), (a1, z1) in zip(whole, whole[1:] + whole[:1]):
                        dense += [(at + a0 + (a1 - a0) * t, z0 + (z1 - z0) * t) for t in np.linspace(0, 1, 3, endpoint=False)]
                    line(dense, width=width, closed=True)
            # A seam down the front, and one down the back that runs on to the heel.
            line([(0.0, z) for z in np.linspace(_rim(0.0) - 0.033, ankle[2] + 0.085, 7)], width=0.0028)
            line([(180.0, z) for z in np.linspace(_rim(180.0) - 0.033, HEEL_HEIGHT + 0.020, 12)], width=0.0028)
            # The heel counter: a stitched cup round the back of the heel, from one side of the ankle to the other.
            line([(180.0 + a, HEEL_HEIGHT + 0.026 + 0.066 * (abs(a) / 100.0) ** 1.6) for a in np.linspace(-100.0, 100.0, 15)])
            line([(180.0 + a, HEEL_HEIGHT + 0.038 + 0.066 * (abs(a) / 100.0) ** 1.6) for a in np.linspace(-92.0, 92.0, 15)], width=0.0026)
            # Pull straps: a loop of leather standing over the rim at each side.
            for at in (90.0, -90.0):
                a = math.radians(at)
                out = np.array((math.sin(a), -math.cos(a), 0.0))
                along = np.array((-out[1], out[0], 0.0))
                found = wall(at, BOOT_TOP - 0.02)
                if found is None:
                    continue
                base = found[0]
                profile = ((0.003, -0.030), (0.005, 0.016), (0.002, 0.038), (-0.006, 0.038), (-0.011, 0.014), (-0.010, -0.004))
                strap = []
                for proud, rise in profile:
                    for edge in (-1.0, 1.0):
                        strap.append(base + out * proud + along * (0.014 * edge) + (0.0, 0.0, rise))
                quads = [(2 * i, 2 * i + 1, 2 * i + 3, 2 * i + 2) for i in range(len(profile) - 1)]
                # Both faces: a strap is seen from either side.
                applique.solid(strap, quads, "boot-shade")
                applique.solid(strap, [q[::-1] for q in quads], "boot-shade")
            # The vamp: a stitched wing across the top of the foot, and a smaller one on the toe.
            cx = centre_x * sign
            for start, depth, reach, width in ((ball[1] + 0.012, 0.058, 0.90, 0.0034), (ball[1] - 0.030, 0.040, 0.62, 0.0028)):
                wing = [surface.below(cx + t * FOOT[0] * reach, start - depth * (1.0 - abs(t) ** 1.6), top=0.3)
                        for t in np.linspace(-1.0, 1.0, 13)]
                applique.ribbon(wing, width, "boot-stitch")
        applique.apply(ctx["palette"], ctx["tiles"], "outfit.default.shoes")
    return obj
