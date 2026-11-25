"""The cyber wardrobe: a techwear jacket, a pleated skirt, a cropped utility vest, platform boots and a headset.

It is the other set of garments the generator can dress the figure in
(`build_cass.py --wardrobe cyber`), in wirenook.net's night colours with
violet and indigo panels and a few lines of light. Unity exchanges it for the
western wardrobe by mesh name, so every garment here keeps the name, the
tile and the bones of the one it stands in for:

    Outfit_Sweater   outfit.default.top      the jacket
    Outfit_Shorts    outfit.default.bottom   dark shorts
    Outfit_Skirt     outfit.skirt.bottom     the pleated skirt, on the gingham skirt's own chains
    Outfit_Vest      outfit.vest.layer       the utility vest
    Outfit_Boots     outfit.default.shoes    the boots
    Outfit_Hat       outfit.default.hat      the headset

One skeleton carries both wardrobes, and a mesh that is exchanged is skinned
to the bones where the avatar has them. So nothing here moves a bone: the
jacket is finished from the sweater's own shell (garments.top_shell), which
the skirt's waistband and chains are placed by, and the short skirt hangs on
the upper two bones of chains that run on to the long skirt's hem. The boots
close their shafts at the height the cowboy boots do, so the skin is tiled
the same under either pair. Body, face, hair, ears and tail are the same
meshes in both wardrobes.

The lite level keeps the lines of light that the look depends on (they are a
few faces each) and leaves out the straps and pockets.
"""

import math
import types

import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

from . import common, garments, hair, rig
from .common import smoothstep
from .detail import Applique, Surface
from .shell import ring_to_radius

# Swatches (Textures/cass-palette.toml).
NIGHT, DEEP, SLATE, INK = "cyber-night", "cyber-deep", "cyber-slate", "cyber-ink"
INDIGO, VIOLET = "cyber-indigo", "cyber-violet"
CYAN, MAGENTA = "cyber-glow-cyan", "cyber-glow-magenta"

COLLAR_HEIGHT = 0.050             # how far the jacket's collar stands above its neckline
LINE = 0.008                      # the width of a line of light

SKIRT_HEM = 0.790                 # height of the pleated skirt's hem above the ground: mid-thigh, below the shell under it
SKIRT_SWEEP = (0.262, 0.232)      # its half-width and half-depth there: about where the long skirt's chains pass
SKIRT_PLEATS = {True: 24, False: 12}
SKIRT_PLEAT = 0.016               # how far a pleat's edge stands out from its fold at the hem
SKIRT_STAND = 0.012               # how far the cloth stands out from the waistband's seam, as the gingham's gathers do
SKIRT_LINE = 0.016                # the height of the bright line along the hem

VEST_CROP = 0.070                 # how far above the waist the vest ends
VEST_GAP = 0.046                  # half the width of its open front
VEST_NECK = 0.090

BOOT_TOP = 0.390                  # the rim of the shaft, level all round
BOOT_FLOOR = 0.029                # closes the shaft at the height the cowboy boots close theirs (see the module docstring)
BOOT_SOLE = 0.022                 # the thickness of the outsole
BOOT_LINE = 0.012                 # the bright edge of the midsole above it

# The headset, in metres from the skull's centre: where a cup's middle is (left side), its radius and depth.
CUP_AT = (0.020, -0.030)          # y, z
CUP_RADIUS = 0.058
CUP_DEPTH = 0.040
BAND_DROP = 0.030                 # how far the band dips on its way round the back of the head
BAND_SIZE = (0.022, 0.008)        # its height and thickness


# --- shorts ------------------------------------------------------------------


def build_shorts(ctx):
    """Dark shorts: the denim shorts' cut exactly, in night cloth with indigo seams and a line of light at each hem.

    Exactly, because the jacket's tube is sized round the shorts and the
    skirt's chains are placed by that tube; a different cut here would move
    bones that both wardrobes share.
    """
    return garments.build_shorts(ctx, swatches={"denim": NIGHT, "denim-shade": DEEP, "denim-stitch": MAGENTA,
                                                "denim-seam": INDIGO, "boot-stitch": CYAN})


# --- jacket ------------------------------------------------------------------


def build_jacket(ctx):
    """A techwear jacket: the sweater's loose shell with a high stand collar, banded cuffs and hem, and lines of light.

    A line of light runs round each cuff and above the hem band, one down
    the front where the zip is, and one along the top of each sleeve.
    """
    full = ctx["detail"] >= 1.0
    tube = garments.top_shell(ctx, NIGHT)
    shell = tube.shell

    for sign, cuff in tube.cuffs.items():
        a, b = tube.shoulder * (sign, 1, 1), tube.wrist * (sign, 1, 1)
        # The sleeve blouses over a deep cuff; the line of light is the step between them.
        # At lite the step is one ring, and is itself the line.
        steps = [(lambda co, a=a, b=b: ring_to_radius(co, a, b, 0.057, 0.016), NIGHT)]
        if full:
            steps += [
                (lambda co, a=a, b=b: ring_to_radius(co, a, b, 0.044, 0.010), NIGHT),
                (lambda co, a=a, b=b: ring_to_radius(co, a, b, 0.044, LINE), CYAN),
                (lambda co, a=a, b=b: ring_to_radius(co, a, b, 0.041, 0.029), SLATE),
                (lambda co, a=a, b=b: ring_to_radius(co, a, b, 0.034, -0.003), DEEP),
            ]
        else:
            steps += [
                (lambda co, a=a, b=b: ring_to_radius(co, a, b, 0.044, 0.014), CYAN),
                (lambda co, a=a, b=b: ring_to_radius(co, a, b, 0.041, 0.033), SLATE),
            ]
        shell.band(cuff, steps)

    # The hem: the same tube and the same draw-in as the sweater's, which the skirt's waistband is fitted round.
    rib_top = garments.SWEATER_HEM - garments.SWEATER_HEM_RIB
    steps = [(garments.hem_ring(tube, 1.012, rib_top * 0.50), NIGHT)] if full else []
    steps += [
        (garments.hem_ring(tube, 1.000, rib_top - LINE), NIGHT),
        (garments.hem_ring(tube, garments.SWEATER_RIB + 0.008, rib_top), CYAN),
        (garments.hem_ring(tube, garments.SWEATER_RIB, garments.SWEATER_HEM), SLATE),
    ]
    if full:
        steps.append((garments.hem_ring(tube, garments.SWEATER_RIB - 0.045, garments.SWEATER_HEM - 0.003), DEEP))
    shell.band(tube.hem, steps)

    def lean(rise, inward):
        return lambda co: garments.lean_ring(co, tube.opening, tube.neck_axis, rise, inward)

    # The collar stands up round the neck, a little proud of the cloth, with a bright edge that turns in.
    if full:
        collar = [
            (lean(0.004, -0.005), SLATE),
            (lean(COLLAR_HEIGHT * 0.5, 0.001), SLATE),
            (lean(COLLAR_HEIGHT * 0.5 - 0.006, -0.002), SLATE),
            (lean(0.006, 0.001), MAGENTA),
            (lean(-0.004, 0.007), DEEP),
            (lean(-0.020, 0.001), DEEP),
        ]
    else:
        collar = [(lean(COLLAR_HEIGHT - 0.002, -0.006), SLATE), (lean(0.006, 0.001), MAGENTA), (lean(-0.004, 0.007), DEEP)]
    shell.band(tube.collar, collar)
    obj = garments.finish_top(ctx, tube)

    surface = Surface(obj)
    applique = Applique(surface)
    axis = (0.0, tube.bottom[1])
    co = common.coords(obj.data)
    # The zip: down the front from the base of the collar to the hem band.
    front = co[(np.abs(co[:, 0]) < 0.03) & (co[:, 1] < axis[1])]
    neckline = front[:, 2].max() - COLLAR_HEIGHT - 0.012
    # It ends behind the skirt's waistband; lower, it would show through the pleats when they are lifted.
    zip_low = tube.waist - 0.030
    applique.ribbon([surface.around(axis, 0.0, z) for z in np.linspace(neckline, zip_low, 12 if full else 6)], LINE, CYAN, lift=0.003)
    # A line along the top of each sleeve, from the shoulder to the cuff: the outside of the arm once it hangs.
    for sign in (1.0, -1.0):
        xs = np.linspace(tube.shoulder[0] + 0.035, tube.wrist[0] - 0.075, 10 if full else 5)
        applique.ribbon([surface.below(sign * x, tube.shoulder[1], top=tube.shoulder[2] + 0.2) for x in xs], LINE + 0.002, CYAN,
                        lift=0.003 if full else 0.005)
    if full:
        # A violet band round each upper arm, with a short bar of light on it.
        for sign in (1.0, -1.0):
            x = sign * (tube.shoulder[0] + 0.105)
            hits = []
            for turn in np.linspace(0.0, 2.0 * math.pi, 20, endpoint=False):
                out = np.array((0.0, math.cos(turn), math.sin(turn)))
                hits.append(surface.hit(np.array((x, tube.shoulder[1], tube.shoulder[2])) + out * 0.2, -out, 0.2))
            applique.ribbon(hits, 0.034, VIOLET, closed=True, lift=0.0035)
            bar = [surface.hit(np.array((x, tube.shoulder[1] - 0.2, tube.shoulder[2] + dz)), (0.0, 1.0, 0.0), 0.2) for dz in (-0.014, 0.0, 0.014)]
            applique.ribbon(bar, 0.012, MAGENTA, lift=0.0055)
    applique.apply(ctx["palette"], ctx["tiles"], "outfit.default.top")
    return obj


# --- skirt -------------------------------------------------------------------


def _pleats(frame):
    """The outside of the skirt: a waistband, and knife pleats that open towards a bright hem.

    Every pleat is two faces: a panel that runs from its edge in to its
    fold, in the cloth's colour, and the short return from the fold out to
    the next edge, which is the inside of the pleat and lighter.
    """
    part, oval = frame.part, frame.oval
    pleats = SKIRT_PLEATS[frame.full]
    count = pleats * 2

    def ring(z, shape, depth=0.0):
        half_width, half_depth, centre_y, square, scale, extra = shape
        points = []
        for k in range(pleats):
            for offset, out in ((0.0, depth), (0.80, 0.0)):
                theta = 2.0 * math.pi * (k + offset) / pleats
                x, y = math.sin(theta), -math.cos(theta)
                radius = scale / float(garments._oval(x, y, half_width, half_depth, square)) + extra + out
                points.append((x * radius, centre_y + y * radius, z))
        return part.verts(points)

    def strip(upper, lower, swatch):
        for j in range(count):
            k = (j + 1) % count
            part.face((upper[j], lower[j], lower[k], upper[k]), swatch(j) if callable(swatch) else swatch)

    rim = ring(frame.top, oval(0.0))
    lip = ring(frame.top - 0.003, oval(0.0, scale=0.955))
    part.loft([rim, lip], SLATE, flip=False)
    seam = ring(frame.band_low, oval(0.0))
    strip(rim, seam, SLATE)

    line = SKIRT_LINE / frame.drop
    # The cloth stands out from the seam at once, as the gingham's gathers do: when a thigh lifts
    # the front, the top of the cloth is carried back towards the jacket, and this is the room for it.
    rows = (0.005 / frame.drop,) + ((0.30, 0.65, 1.0 - line, 1.0) if frame.full else (0.5, 1.0 - line, 1.0))
    previous = seam
    for f in rows:
        # The pleats open quickly below the waistband and then keep their depth.
        depth = SKIRT_PLEAT * float(smoothstep(0.02, 0.45, f))
        current = ring(frame.band_low - frame.drop * f, oval(f, extra=SKIRT_STAND), depth)
        if f >= 1.0:
            strip(previous, current, CYAN)
        else:
            strip(previous, current, lambda j: NIGHT if j % 2 == 0 else INDIGO)
        previous = current


def build_skirt(ctx):
    """A short pleated skirt with a bright hem, on the gingham skirt's waistband, lining and chains."""
    return garments.build_skirt(ctx, types.SimpleNamespace(hem=SKIRT_HEM, sweep=SKIRT_SWEEP, cloth=_pleats))


# --- vest --------------------------------------------------------------------


def _vest_details(ctx, obj, where):
    """What makes the layer a utility vest: a strap and buckle across the open front, pockets, a back plate, a bright hem."""
    full = ctx["detail"] >= 1.0
    surface = Surface(obj)
    applique = Applique(surface)
    axis = where.axis

    def around(azimuths, z):
        return [surface.around(axis, a, z) for a in azimuths]

    # A line of light just above the hem. The open front breaks it by itself: there is nothing there to lay it on.
    turn = np.linspace(0.0, 360.0, 49 if full else 25)
    applique.ribbon(around(turn, where.hem + 0.014), LINE, CYAN, lift=0.003 if full else 0.005)

    # The chest strap: from one front edge to the other, standing clear of the jacket between them.
    z = where.armpit - 0.012
    edges = [surface.around(axis, sign * a, z) for sign in (1.0, -1.0) for a in (26.0, 34.0)]
    if all(edges):
        left, right = edges[0][0] + edges[0][1] * 0.006, edges[2][0] + edges[2][1] * 0.006
        middle = (left + right) / 2.0 + np.array((0.0, -0.010, 0.0))
        half = np.array((0.0, 0.0, 0.013))
        outer_left, outer_right = edges[1][0] + edges[1][1] * 0.006, edges[3][0] + edges[3][1] * 0.006
        points = [outer_left - half, outer_left + half, left - half, left + half, middle - half, middle + half,
                  right - half, right + half, outer_right - half, outer_right + half]
        quads = [(2 * i, 2 * i + 1, 2 * i + 3, 2 * i + 2) for i in range(4)]
        applique.solid(points, quads, DEEP)
        # The buckle, in the middle of it.
        proud = np.array((0.0, -0.004, 0.0))
        wide, tall = np.array((0.017, 0.0, 0.0)), np.array((0.0, 0.0, 0.018))
        buckle = [middle + proud - wide - tall, middle + proud - wide + tall, middle + proud + wide + tall, middle + proud + wide - tall]
        applique.solid(buckle, [(3, 2, 1, 0)], MAGENTA)

    if full:
        for sign in (1.0, -1.0):
            # A pocket low on each front, with a flap over it.
            azimuths = [sign * a for a in np.linspace(36.0, 72.0, 7)]
            applique.ribbon(around(azimuths, where.hem + 0.058), 0.052, INK, lift=0.004)
            applique.ribbon(around(azimuths, where.hem + 0.081), 0.020, INDIGO, lift=0.0065)
        # The back plate: a panel across the shoulder blades, and a bar of light under it.
        across = np.linspace(180.0 - 46.0, 180.0 + 46.0, 11)
        applique.ribbon(around(across, where.armpit + 0.012), 0.070, INDIGO, lift=0.004)
        applique.ribbon(around(across[2:-2], where.armpit - 0.036), LINE, MAGENTA, lift=0.004)
    applique.apply(ctx["palette"], ctx["tiles"], "outfit.vest.layer")


def build_vest(ctx):
    """A cropped utility vest over the jacket: the suede vest's construction, ending above the waist, without fringe or neckerchief."""
    return garments.build_vest(ctx, garments.vest_cut(swatch=VIOLET, shade=INK, gap=VEST_GAP, neck=VEST_NECK, drop=0.022, fringe=0.0,
                                                      crop=VEST_CROP, details=_vest_details, bandana=False))


# --- boots -------------------------------------------------------------------


def _boot_details(ctx, obj, cut):
    """Two straps round each shaft, each with a buckle on the outside. Full level only."""
    if ctx["detail"] < 1.0:
        return
    armature = ctx["armature"]
    surface = Surface(obj)
    applique = Applique(surface)
    turn = np.linspace(0.0, 360.0, 25)[:-1]
    for sign in (1.0, -1.0):
        for z in (cut.top - 0.085, cut.top - 0.175):
            applique.ribbon([garments.boot_wall(surface, armature, sign, a, z) for a in turn], 0.026, DEEP, closed=True, lift=0.004)
            buckle = [garments.boot_wall(surface, armature, sign, sign * 90.0 + da, z) for da in (-14.0, 0.0, 14.0)]
            applique.ribbon(buckle, 0.018, MAGENTA, lift=0.0065)
    applique.apply(ctx["palette"], ctx["tiles"], "outfit.default.shoes")


def build_boots(ctx):
    """Chunky boots: a straight shaft with a violet cuff, a blunt capped toe, and a thick sole with a bright edge."""
    armature = ctx["armature"]
    ball = np.array(rig.head_of(armature, "Toes.L"))
    knee, ankle = np.array(rig.head_of(armature, "LowerLeg.L")), np.array(rig.head_of(armature, "Foot.L"))
    shin = (knee - ankle) / np.linalg.norm(knee - ankle)
    rim = knee + (ankle - knee) * ((knee[2] - BOOT_TOP) / (knee[2] - ankle[2]))

    def paint(corners):
        middle = np.mean(corners, axis=0)
        # The cuff is measured along the shin, as the shaft's rings are, so it ends on a ring.
        if (middle - rim) @ shin > -0.050:
            return VIOLET
        if middle[1] < ball[1] - 0.030 and middle[2] < 0.12:
            return VIOLET
        return None

    cut = garments.boot_cut(top=BOOT_TOP, dip=0.0, floor=BOOT_FLOOR, offset=0.017, toe=0.020, heel=0.0, foot=(0.057, 0.076),
                            toe_height=0.050, heel_cup=(0.047, 0.012), spring=0.0, welt=BOOT_LINE, point=(0.80, 3.0),
                            sole=BOOT_SOLE, body=SLATE, shade=DEEP, under=DEEP, edge=CYAN, paint=paint, details=_boot_details)
    return garments.build_boots(ctx, cut)


# --- headset -----------------------------------------------------------------


def _mouth(head):
    """Roughly where the mouth is, from what the open-mouth shape moves."""
    keys = head.data.shape_keys.key_blocks
    block = next((keys[name] for name in ("vrc.v_aa", "あ", "JawOpen") if name in keys), None)
    if block is None:
        return None
    moved = np.linalg.norm(common.key_coords(block) - common.key_coords(keys[0]), axis=1)
    if moved.max() < 1e-4:
        return None
    return common.key_coords(keys[0])[moved > moved.max() * 0.5].mean(axis=0)


def build_headset(ctx):
    """A headset in the hat's place: a cup over each side of the head, a band round the back, a microphone on a boom.

    Nothing of it is above the cups, so the ears, which root higher on the
    head, are clear of it however they move. The band goes round the back
    of the head outside the hair, and dips as it goes. The whole of it
    follows the head rigidly.
    """
    armature, full = ctx["armature"], ctx["detail"] >= 1.0
    centre = hair.skull_centre(armature)
    part = common.Part("Outfit_Hat", "outfit.default.hat")
    hair_co = common.coords(bpy.data.objects["Hair"].data) - centre
    head_co = common.coords(ctx["head"].data) - centre
    both = np.vstack([hair_co, head_co])
    cy, cz = CUP_AT

    # A cup sits against the widest thing under it, hair or head, and a little into it.
    under = both[(np.abs(both[:, 1] - cy) < CUP_RADIUS * 0.8) & (np.abs(both[:, 2] - cz) < CUP_RADIUS * 0.8)]
    inner = float(np.abs(under[:, 0]).max()) - 0.014
    sides = 12 if full else 8
    profile = [(0.0, 0.92, SLATE), (0.55, 1.0, SLATE), (0.82, 0.86, VIOLET), (1.0, 0.80, VIOLET)]
    if not full:
        profile = [(0.0, 0.96, SLATE), (0.70, 1.0, SLATE), (1.0, 0.80, VIOLET)]

    def disc(sign, x, radius):
        points = []
        for k in range(sides):
            angle = 2.0 * math.pi * (k + 0.5) / sides
            points.append(centre + (sign * x, cy + radius * math.cos(angle), cz + radius * math.sin(angle)))
        return part.verts(points)

    for sign in (1.0, -1.0):
        rings = [disc(sign, inner + CUP_DEPTH * along, CUP_RADIUS * scale) for along, scale, _swatch in profile]
        part.loft(rings, lambda r, i: profile[r + 1][2])
        # The face of the cup: a dark plate, a ring of light, a dark hub.
        face = inner + CUP_DEPTH
        plate = disc(sign, face, CUP_RADIUS * 0.56)
        glow = disc(sign, face + 0.002, CUP_RADIUS * 0.40)
        part.loft([rings[-1], plate], DEEP)
        part.loft([plate, glow], CYAN)
        part.fan(glow, centre + (sign * (face + 0.004), cy, cz), DEEP)
        if full:
            # Closed towards the head as well: hair can swing clear of it.
            part.fan(rings[0], centre + (sign * inner, cy, cz), DEEP)

    # The band: an arc from cup to cup round the back of the head, wide enough to pass outside the hair there.
    reach = inner + CUP_DEPTH * 0.45
    # Beside the cups the hair is as wide as the cups are, and the band starts inside them; what
    # sets how far back it goes is the hair between them.
    behind = hair_co[(np.abs(hair_co[:, 2] - (cz - BAND_DROP * 0.5)) < BAND_DROP * 0.5 + BAND_SIZE[0])
                     & (hair_co[:, 1] > cy) & (np.abs(hair_co[:, 0]) < reach * 0.8)]
    depth = 0.12
    if len(behind):
        depth = float(((behind[:, 1] - cy) / (1.0 - np.abs(behind[:, 0] / reach) ** 2.4) ** (1.0 / 2.4)).max()) + 0.008
    steps = 20 if full else 8
    rings = []
    for step in range(steps + 1):
        turn = math.pi * step / steps
        c, s = math.cos(turn), math.sin(turn)
        rho = (abs(c) ** 2.4 + abs(s) ** 2.4) ** (1.0 / 2.4)
        middle = np.array((reach * c / rho, cy + depth * s / rho, cz - BAND_DROP * s))
        # The outward direction of the arc there, level.
        normal = np.array((c / reach, s / depth, 0.0))
        normal /= np.linalg.norm(normal)
        up = np.array((0.0, 0.0, BAND_SIZE[0] / 2.0))
        thick = normal * BAND_SIZE[1]
        rings.append(part.verts([centre + middle - up, centre + middle - up + thick, centre + middle + up + thick, centre + middle + up]))
    part.loft(rings, lambda r, i: SLATE if i == 1 else DEEP)

    # The microphone: a boom from the left cup round the cheek to beside the mouth, clear of the face and the hair.
    mouth = _mouth(ctx["head"])
    if mouth is not None:
        mouth = mouth - centre
        tree = BVHTree.FromPolygons([tuple(p) for p in both], _triangles(bpy.data.objects["Hair"], 0) + _triangles(ctx["head"], len(hair_co)))
        start = np.array((inner + CUP_DEPTH * 0.6, cy - CUP_RADIUS * 0.75, cz - CUP_RADIUS * 0.45))
        end_azimuth = 26.0
        path = [start]
        for t in np.linspace(0.25, 1.0, 5 if full else 3):
            azimuth = math.radians(75.0 + (end_azimuth - 75.0) * t)
            z = start[2] + (mouth[2] - 0.004 - start[2]) * t
            outward = np.array((math.sin(azimuth), -math.cos(azimuth), 0.0))
            origin = np.array((0.0, mouth[1] * 0.25, z))
            hit = tree.ray_cast(Vector(centre + origin + outward * 0.4), Vector(-outward), 0.4)
            distance = 0.4 - hit[3] if hit[0] is not None else 0.12
            path.append(origin + outward * (distance + 0.024))
        path = np.array(path)
        size = 0.0045
        rings = []
        for index, point in enumerate(path):
            along = path[min(index + 1, len(path) - 1)] - path[max(index - 1, 0)]
            along /= np.linalg.norm(along)
            side = np.cross(along, (0.0, 0.0, 1.0))
            side /= np.linalg.norm(side)
            up = np.cross(side, along)
            rings.append(part.verts([centre + point + side * (size * a) + up * (size * b) for a, b in ((-1, -1), (1, -1), (1, 1), (-1, 1))]))
        part.loft(rings, SLATE)
        part.face(rings[0], SLATE)
        # The capsule at its end, lit.
        along = path[-1] - path[-2]
        along /= np.linalg.norm(along)
        side = np.cross(along, (0.0, 0.0, 1.0))
        side /= np.linalg.norm(side)
        up = np.cross(side, along)
        tip = []
        for forward, grow in ((-0.004, 2.2), (0.016, 2.2)):
            tip.append(part.verts([centre + path[-1] + along * forward + side * (size * grow * a) + up * (size * grow * b)
                                   for a, b in ((-1, -1), (1, -1), (1, 1), (-1, 1))]))
        part.loft(tip, MAGENTA)
        part.face(tip[0], MAGENTA)
        part.face(tip[1], MAGENTA)
        print(f"headset: mouth at {np.round(mouth, 3)} from the skull's centre, microphone at {np.round(path[-1], 3)}")

    obj = part.to_object(ctx["collection"], armature, ctx["material"], ctx["palette"], ctx["tiles"], sharp_angle=40.0)
    common.rigid_weights(obj, "Head")
    ears = common.coords(bpy.data.objects["Ears"].data) if "Ears" in bpy.data.objects else None
    print(f"headset: cups at x {inner:.3f}..{inner + CUP_DEPTH:.3f}, band {depth:.3f} behind; top of the headset "
          f"{common.coords(obj.data)[:, 2].max() - centre[2]:+.3f} from the skull's centre"
          + ("" if ears is None else f", lowest point of the ears {ears[:, 2].min() - centre[2]:+.3f}"))
    return obj


def _triangles(obj, offset):
    mesh = obj.data
    mesh.calc_loop_triangles()
    return [tuple(int(v) + offset for v in triangle.vertices) for triangle in mesh.loop_triangles]
