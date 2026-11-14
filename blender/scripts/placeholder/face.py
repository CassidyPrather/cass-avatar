"""Head and face of the placeholder, plus the bookkeeping the shape keys are generated from.

The head is a row/column grid over an analytic surface. Eyes, brows, blush and
tears are flat decals described in a 2D frame centred on each eye and projected
onto that surface; `pose_decals` places them for any `EyeState`, so the rest
shape and every eye/brow shape key come from the same function. Geometry that
only some keys show (heart and star pupils, blush, tears) rests shrunk just
behind the face skin and is brought forward by its key.
"""

import math
from dataclasses import dataclass, field, replace
from typing import Callable, Optional

from .meshkit import interp, lerp

HEAD = {"Head": 1.0}

# Design-space head rows for a 0.27 m head, crown to chin:
# (height above chin, half-width, centre y, front depth, back depth).
HEAD_ROWS = [
    (0.263, 0.0340, 0.004, 0.0360, 0.038),
    (0.247, 0.0580, 0.004, 0.0620, 0.066),
    (0.224, 0.0760, 0.004, 0.0820, 0.088),
    (0.196, 0.0880, 0.004, 0.0940, 0.100),
    (0.166, 0.0935, 0.004, 0.1000, 0.105),
    (0.140, 0.0940, 0.004, 0.1020, 0.105),
    (0.122, 0.0935, 0.004, 0.1025, 0.103),
    (0.105, 0.0920, 0.004, 0.1025, 0.100),
    (0.088, 0.0890, 0.004, 0.1020, 0.096),
    (0.074, 0.0840, 0.003, 0.1005, 0.090),
    (0.062, 0.0770, 0.002, 0.0980, 0.084),
    (0.051, 0.0690, 0.000, 0.0940, 0.076),
    (0.041, 0.0600, -0.003, 0.0880, 0.066),
    (0.031, 0.0500, -0.007, 0.0810, 0.058),
    (0.019, 0.0380, -0.014, 0.0680, 0.048),
    (0.008, 0.0230, -0.024, 0.0480, 0.036),
]
ROW_NOSE, ROW_ABOVE_LIP, ROW_MOUTH, ROW_BELOW_LIP, ROW_CHIN, ROW_CHIN_TIP = 10, 11, 12, 13, 14, 15
TOP_POLE_Y, BOTTOM_POLE_Y = 0.004, -0.030

# Front-half columns as fractions of the row's half-width (dense round the
# mouth), then back-half columns as angles from the front.
FRONT_U = [0.0, 0.075, 0.15, 0.225, 0.30, 0.40, 0.50, 0.60, 0.70, 0.80, 0.89, 0.96, 1.0]
BACK_DEG = [105.0, 122.0, 140.0, 160.0]
FRONT_POWER = 2.6
LAST_FRONT = len(FRONT_U) - 1
LAST_SIDE = LAST_FRONT + len(BACK_DEG)
BACK = LAST_SIDE + 1
COLUMNS = list(range(0, BACK + 1)) + list(range(-LAST_SIDE, 0))
# The lips span columns -CORNER..CORNER of the mouth row.
CORNER = 4

# Decal layer offsets in front of the analytic face surface (metres).
# The iris layers keep a clear gap to the eye white: an Eye bone rotation tilts them a little.
LAYER_WHITE, LAYER_IRIS, LAYER_PUPIL, LAYER_HILITE, LAYER_LASH = 0.0010, 0.0024, 0.0032, 0.0040, 0.0050
LAYER_BROW, LAYER_BLUSH, LAYER_TEAR = 0.0015, 0.0012, 0.0014
LAYER_SCRIBBLE, LAYER_SCRIBBLE_LINE = 0.0085, 0.0093
LAYER_HIDDEN, HIDDEN_SCALE = -0.004, 0.03

# Eye-frame coordinates are authored at this fraction of their final size.
EYE_SCALE = 1.15
EYE_W = 0.0185
EYE_TILT = 0.05
IRIS_CENTRE = (0.0, -0.0015)
IRIS_RX, IRIS_RZ = 0.0118, 0.0150
LID_MARGIN = 0.0003


def basis_top(ex):
    return 0.0190 * (1.0 - min(1.0, abs(ex / EYE_W)) ** 2.6) ** 0.5 + EYE_TILT * ex


def basis_bot(ex):
    return -0.0170 * (1.0 - min(1.0, abs(ex / EYE_W)) ** 2.2) ** 0.62 + EYE_TILT * ex


def no_brow_motion(_s):
    return (0.0, 0.0)


@dataclass(frozen=True)
class EyeState:
    """Everything a key can change about one eye and its brow, in the eye's 2D frame.

    ex is metres toward the outer corner, ez metres up, both from the eye centre.
    """
    top: Callable = basis_top
    bot: Callable = basis_bot
    look: tuple = (0.0, 0.0)
    iris: float = 1.0
    pupil: float = 1.0
    hilite: float = 1.0
    heart: float = 0.0
    star: float = 0.0
    lash: float = 1.0
    # Optional explicit lash strokes: s in [0, 1] -> ((ex, ez) lower edge, (ex, ez) upper edge).
    upper_stroke: Optional[Callable] = None
    lower_stroke: Optional[Callable] = None
    scribble: float = 1.0
    brow: Callable = no_brow_motion
    blush: float = 0.0
    tear: float = 0.0

    def but(self, **changes):
        return replace(self, **changes)


BASIS_EYE = EyeState()


def _upper_lash(state, s):
    if state.upper_stroke:
        return state.upper_stroke(s)
    across = 0.85
    if s <= across:
        q = s / across
        ex = EYE_W * (2.0 * q - 1.0)
        thick = (lerp(0.0018, 0.0038, q) + 0.0018 * math.sin(math.pi * q)) * state.lash
        base = state.top(ex)
        return (ex, base - 0.0012 * state.lash), (ex, base + thick)
    # The flick past the outer corner.
    q = (s - across) / (1.0 - across)
    base = state.top(EYE_W)
    low = (EYE_W + 0.0060 * q, base + (-0.0012 + 0.0057 * q) * state.lash)
    high = (EYE_W + 0.0065 * q, base + lerp(0.0038, 0.0057, q) * state.lash)
    return low, high


def _lower_lash(state, s):
    if state.lower_stroke:
        return state.lower_stroke(s)
    ex = lerp(-0.5 * EYE_W, 0.8 * EYE_W, s)
    half = 0.0002 + 0.0006 * math.sin(math.pi * s)
    base = state.bot(ex)
    return (ex, base - half - 0.0002), (ex, base + half - 0.0002)


def _brow(state, s):
    ex = -0.016 + 0.034 * s
    ez = 0.0335 + 0.0035 * math.sin(math.pi * (0.2 + 0.6 * s)) - 0.0015 * s
    half = lerp(0.0024, 0.0010, s)
    dex, dez = state.brow(s)
    return (ex + dex, ez + dez - half), (ex + dex, ez + dez + half)


def _clamp_to_lids(state, ex, ez, centre_ex):
    """Clips an iris-layer point to the lid opening, which is what the lids would hide.

    Where the lids are shut the point drops onto one level line through the
    iris centre, so a closed eye leaves the iris with exactly zero area.
    """
    ex = max(-EYE_W, min(EYE_W, ex))
    top, bot = state.top(ex) - LID_MARGIN, state.bot(ex) + LID_MARGIN
    if top <= bot:
        centre_ex = max(-EYE_W, min(EYE_W, centre_ex))
        return ex, 0.5 * (state.top(centre_ex) + state.bot(centre_ex))
    return ex, max(bot, min(top, ez))


def decal_position(desc, state):
    """(ex, ez, layer) of one decal vertex under `state`."""
    kind = desc[0]
    if kind == "white":
        _, ex, edge = desc
        top, bot = state.top(ex), state.bot(ex)
        top = max(top, bot)
        return ex, {"top": top, "bot": bot, "corner": 0.5 * (top + bot)}[edge], LAYER_WHITE
    centre = (IRIS_CENTRE[0] + state.look[0], IRIS_CENTRE[1] + state.look[1])
    if kind in ("iris", "pupil"):
        _, lx, lz = desc
        k = state.iris * (state.pupil if kind == "pupil" else 1.0)
        ex, ez = _clamp_to_lids(state, centre[0] + lx * k, centre[1] + lz * k, centre[0])
        return ex, ez, LAYER_IRIS if kind == "iris" else LAYER_PUPIL
    if kind == "hilite":
        _, lx, lz, ox, oz = desc
        k = state.hilite
        ex, ez = _clamp_to_lids(state, centre[0] + ox * state.iris + lx * k, centre[1] + oz * state.iris + lz * k, centre[0])
        return ex, ez, LAYER_HILITE
    if kind in ("heart", "star"):
        _, lx, lz = desc
        shown = getattr(state, kind)
        k = lerp(HIDDEN_SCALE, 1.0, shown)
        return centre[0] + lx * k, centre[1] + lz * k, lerp(LAYER_HIDDEN, LAYER_HILITE, shown)
    if kind in ("ulash", "llash", "brow"):
        _, s, edge = desc
        low, high = {"ulash": _upper_lash, "llash": _lower_lash, "brow": _brow}[kind](state, s)
        ex, ez = high if edge else low
        return ex, ez, LAYER_BROW if kind == "brow" else LAYER_LASH
    if kind in ("blush", "tear"):
        _, lx, lz, ox, oz = desc
        shown = getattr(state, kind)
        k = lerp(HIDDEN_SCALE, 1.0, shown)
        front = LAYER_BLUSH if kind == "blush" else LAYER_TEAR
        return ox + lx * k, oz + lz * k, lerp(LAYER_HIDDEN, front, shown)
    if kind == "scribble":
        _, lx, lz, layer = desc
        return lx * state.scribble, lz * state.scribble, layer
    raise ValueError(kind)


@dataclass
class FaceRig:
    """Where the face's movable parts ended up in the Body mesh."""
    scale: float
    chin_z: float
    eye_x: float
    eye_z: float
    rows: list                                   # world-space head rows: (z, a, cy, bf, bb)
    grid: dict = field(default_factory=dict)      # (row, column) -> vertex; the mouth row holds only columns beyond the lips
    bottom_pole: int = -1
    lip_upper: dict = field(default_factory=dict)  # column -CORNER..CORNER -> vertex (corners shared with lip_lower)
    lip_lower: dict = field(default_factory=dict)
    sock: list = field(default_factory=list)       # (vertex, 'upper'|'lower'|'corner', column, depth 1|2|3)
    teeth_upper: list = field(default_factory=list)
    teeth_lower: list = field(default_factory=list)
    tongue: list = field(default_factory=list)     # (vertex, fraction root->tip, local x, local z)
    decals: list = field(default_factory=list)     # (vertex, side, descriptor)
    neck: list = field(default_factory=list)       # neck rings above the collar loop, bottom to top
    mouth_z: float = 0.0

    def surface_y(self, x, z):
        return surface_y(self.rows, x, z)

    def project(self, side, ex, ez, layer):
        x = side * (self.eye_x + ex * EYE_SCALE)
        z = self.eye_z + ez * EYE_SCALE
        return (x, self.surface_y(x, z) - layer, z)

    def pose_decals(self, states):
        """Vertex -> position for every decal, given {+1: EyeState, -1: EyeState}."""
        return {v: self.project(side, *decal_position(desc, states[side])) for v, side, desc in self.decals}


def head_rows(L):
    """HEAD_ROWS in world space: (z, half-width, centre y, front depth, back depth)."""
    s = L.head_h / 0.27
    return [(L.chin_z + h * s, a * s, cy * s, bf * s, bb * s) for h, a, cy, bf, bb in HEAD_ROWS]


def surface_y(rows, x, z):
    """The analytic front surface the head grid samples; decals are projected onto it."""
    a, cy, bf, _ = interp(rows, z)
    u = min(1.0, abs(x) / a)
    return cy - bf * (1.0 - u ** FRONT_POWER) ** (1.0 / FRONT_POWER)


def eye_pivot(L):
    """Where the left Eye bone must sit so that rotating it slides the iris along the face.

    The irises are flat decals, not eyeballs: a pivot behind the eye centre
    would swing them into the skull. The pivot is the centre of the face's
    horizontal curvature at the eye instead, so a yaw follows the surface.
    """
    rows, x0, z, h = head_rows(L), L.eye_x, L.eye_z, 0.004
    y0, y1, y2 = (surface_y(rows, x, z) for x in (x0 - h, x0, x0 + h))
    slope, bend = (y2 - y0) / (2.0 * h), (y2 - 2.0 * y1 + y0) / (h * h)
    norm = math.sqrt(1.0 + slope * slope)
    radius = norm ** 3 / bend
    return (x0 - radius * slope / norm, y1 + radius / norm, z)


def _column_point(row, c):
    z, a, cy, bf, bb = row
    sign = -1.0 if c < 0 else 1.0
    k = abs(c)
    if k <= LAST_FRONT:
        u = FRONT_U[k]
        return (sign * a * u, cy - bf * (1.0 - u ** FRONT_POWER) ** (1.0 / FRONT_POWER), z)
    if k <= LAST_SIDE:
        theta = math.radians(BACK_DEG[k - LAST_FRONT - 1])
        return (sign * a * math.sin(theta), cy - bb * math.cos(theta), z)
    return (0.0, cy + bb, z)


def _lip_rest(face, c):
    """Rest positions of the upper and lower lip at lip column c: a thin, slightly smiling slit."""
    x = _column_point(face.rows[ROW_MOUTH], c)[0]
    t = c / CORNER
    upper_z = face.mouth_z - 0.0010 * (1.0 - t * t)
    lower_z = upper_z - 0.0024 * (1.0 - t * t) ** 0.7
    return (x, face.surface_y(x, upper_z), upper_z), (x, face.surface_y(x, lower_z), lower_z)


def _build_skull(mb, face):
    for r, row in enumerate(face.rows):
        for c in COLUMNS:
            if r == ROW_MOUTH and abs(c) < CORNER:
                continue
            x, y, z = _column_point(row, c)
            # A small anime nose: one raised vertex with slightly lifted neighbours.
            if r == ROW_NOSE and c == 0:
                y, z = y - 0.0055, z - 0.002
            elif r == ROW_NOSE and abs(c) == 1:
                y -= 0.0012
            face.grid[(r, c)] = mb.vert((x, y, z), HEAD)
    for c in range(-CORNER, CORNER + 1):
        if abs(c) == CORNER:
            face.lip_upper[c] = face.lip_lower[c] = face.grid[(ROW_MOUTH, c)]
            continue
        upper, lower = _lip_rest(face, c)
        face.lip_upper[c] = mb.vert(upper, HEAD)
        face.lip_lower[c] = mb.vert(lower, HEAD)

    def ring(r, lips=None):
        return [lips[c] if lips and r == ROW_MOUTH and abs(c) < CORNER else face.grid[(r, c)] for c in COLUMNS]

    for r in range(len(face.rows) - 1):
        mb.loft([ring(r, face.lip_lower), ring(r + 1, face.lip_upper)], "skin", "always")
    s = face.scale
    mb.cap(ring(0), (0.0, TOP_POLE_Y * s, face.chin_z + 0.270 * s), "skin", "always", weights=HEAD)
    face.bottom_pole = mb.cap(ring(len(face.rows) - 1), (0.0, BOTTOM_POLE_Y * s, face.chin_z), "skin-shade", "always", weights=HEAD)


def _build_mouth_interior(mb, face):
    zm = face.mouth_z
    lip_y = mb.co[face.lip_upper[0]][1]
    order = [("corner", -CORNER)] + [("upper", c) for c in range(-CORNER + 1, CORNER)]
    order += [("corner", CORNER)] + [("lower", c) for c in range(CORNER - 1, -CORNER, -1)]
    rings = [[(face.lip_upper if part != "lower" else face.lip_lower)[c] for part, c in order]]
    # The sock widens behind the lips and runs back into the head; its lower half follows the jaw.
    for depth, (back, grow) in enumerate(((0.007, 1.0), (0.022, 1.0), (0.037, 0.85)), start=1):
        ring = []
        for part, c in order:
            x, y, _ = mb.co[face.lip_upper[c]]
            arch = math.sqrt(max(0.0, 1.0 - (c / CORNER) ** 2))
            dz = {"upper": 0.002 + 0.008 * arch, "lower": -0.002 - 0.011 * arch, "corner": 0.0}[part]
            v = mb.vert((x * 1.25 * grow, y + back, zm + dz * grow), HEAD)
            face.sock.append((v, part, c, depth))
            ring.append(v)
        rings.append(ring)
    mb.loft(rings, "mouth-inner", "always", inward=True)
    mb.cap(rings[-1], (0.0, lip_y + 0.040, zm - 0.002), "mouth-inner", "always", weights=HEAD, inward=True)

    def teeth(z_low, z_high, back, store):
        low, high = [], []
        for i in range(7):
            x = 0.0155 * (i / 3.0 - 1.0)
            y = lip_y + back + 0.004 * (x / 0.0155) ** 2
            low.append(mb.vert((x, y, z_low), HEAD))
            high.append(mb.vert((x, y, z_high), HEAD))
        ids = mb.loft([low, high], "teeth", "always", closed=False)
        mb.orient_toward(ids, (0.0, -1.0, 0.0))
        store.extend(low + high)

    teeth(zm + 0.0012, zm + 0.0085, 0.0035, face.teeth_upper)
    teeth(zm - 0.0115, zm - 0.0046, 0.0045, face.teeth_lower)

    centre_z = zm - 0.0078
    rings = []
    for k, (half_width, half_thick) in enumerate([(0.0105, 0.0028), (0.0100, 0.0028), (0.0092, 0.0027), (0.0078, 0.0025), (0.0055, 0.0020)]):
        f = k / 4.0
        y = lip_y + lerp(0.030, 0.009, f)
        ring = []
        for j in range(8):
            a = 2.0 * math.pi * j / 8
            lx, lz = half_width * math.sin(a), half_thick * math.cos(a)
            v = mb.vert((lx, y, centre_z + lz), HEAD)
            face.tongue.append((v, f, lx, lz))
            ring.append(v)
        rings.append(ring)
    mb.loft(rings, "tongue", "always")
    tip = mb.cap(rings[-1], (0.0, lip_y + 0.0065, centre_z), "tongue", "always", weights=HEAD)
    face.tongue.append((tip, 1.1, 0.0, 0.0))


def _decal_fan(mb, face, side, bone, swatch, tile, centre_desc, outline_descs):
    """A fan of triangles in the eye frame; returns nothing, records the decal vertices."""
    def add(desc):
        v = mb.vert(face.project(side, *decal_position(desc, BASIS_EYE)), bone)
        face.decals.append((v, side, desc))
        return v

    centre = add(centre_desc)
    ring = [add(d) for d in outline_descs]
    ids = mb.fan(centre, ring, swatch, tile)
    mb.orient_toward(ids, (0.0, -1.0, 0.0))


def _decal_strip(mb, face, side, bone, swatch, tile, lows, highs):
    """A strip of quads between two rows of decal descriptors; `swatch` may be fn(span)."""
    def add(desc):
        v = mb.vert(face.project(side, *decal_position(desc, BASIS_EYE)), bone)
        face.decals.append((v, side, desc))
        return v

    low, high = [add(d) for d in lows], [add(d) for d in highs]
    name = (lambda span, k: swatch(k)) if callable(swatch) else swatch
    ids = mb.loft([low, high], name, tile, closed=False)
    mb.orient_toward(ids, (0.0, -1.0, 0.0))


def _ellipse_rows(rx, rz, levels):
    """Left/right outline points of an ellipse at sinusoidally spaced heights, bottom to top."""
    rows = []
    for k in range(levels + 1):
        ez = -rz * math.cos(math.pi * k / levels)
        half = rx * math.sqrt(max(0.0, 1.0 - (ez / rz) ** 2))
        rows.append((ez, half))
    return rows


def _build_eye(mb, face, side):
    eye_bone = {("Eye.L" if side > 0 else "Eye.R"): 1.0}

    stations = [EYE_W * (2.0 * i / 8.0 - 1.0) for i in range(9)]
    lows = [("white", ex, "corner" if i in (0, 8) else "bot") for i, ex in enumerate(stations)]
    highs = [("white", ex, "corner" if i in (0, 8) else "top") for i, ex in enumerate(stations)]
    _decal_strip(mb, face, side, HEAD, "eye-white", "always", lows, highs)

    # Iris and pupil are stacks of horizontal bands so the lids can clip them
    # by clamping vertices; the iris's upper bands take the darker swatch.
    iris = _ellipse_rows(IRIS_RX, IRIS_RZ, 8)
    _decal_strip(mb, face, side, eye_bone, lambda k: "iris-dark" if iris[k][0] > 0.002 else "iris", "face.eyes",
                 [("iris", -half, ez) for ez, half in iris], [("iris", half, ez) for ez, half in iris])
    pupil = _ellipse_rows(0.0058, 0.0080, 6)
    _decal_strip(mb, face, side, eye_bone, "pupil", "face.eyes",
                 [("pupil", -half, ez - 0.0005) for ez, half in pupil], [("pupil", half, ez - 0.0005) for ez, half in pupil])

    # Highlights sit on the same world side of both irises, as if lit from one direction.
    for (ox, oz), radius in (((-0.0042 * side, 0.0068), 0.0034), ((0.0040 * side, -0.0068), 0.0017)):
        outline = [("hilite", radius * math.sin(a), radius * math.cos(a), ox, oz) for a in (2.0 * math.pi * j / 6 for j in range(6))]
        _decal_fan(mb, face, side, eye_bone, "highlight", "face.eyes", ("hilite", 0.0, 0.0, ox, oz), outline)

    heart = []
    for j in range(14):
        t = 2.0 * math.pi * j / 14
        hx = 16.0 * math.sin(t) ** 3
        hz = 13.0 * math.cos(t) - 5.0 * math.cos(2 * t) - 2.0 * math.cos(3 * t) - math.cos(4 * t)
        heart.append(("heart", hx * 0.00042, (hz + 2.5) * 0.00042))
    _decal_fan(mb, face, side, eye_bone, "heart", "face.eyes", ("heart", 0.0, 0.0), heart)
    star = []
    for j in range(10):
        radius = 0.0072 if j % 2 == 0 else 0.0030
        a = 2.0 * math.pi * j / 10
        star.append(("star", radius * math.sin(a), radius * math.cos(a)))
    _decal_fan(mb, face, side, eye_bone, "star", "face.eyes", ("star", 0.0, 0.0), star)

    upper = [0.85 * i / 8.0 for i in range(9)] + [0.925, 1.0]
    _decal_strip(mb, face, side, HEAD, "lash", "always", [("ulash", s, 0) for s in upper], [("ulash", s, 1) for s in upper])
    lower = [i / 5.0 for i in range(6)]
    _decal_strip(mb, face, side, HEAD, "lash", "always", [("llash", s, 0) for s in lower], [("llash", s, 1) for s in lower])
    brow = [i / 5.0 for i in range(6)]
    _decal_strip(mb, face, side, HEAD, "brow", "always", [("brow", s, 0) for s in brow], [("brow", s, 1) for s in brow])

    for i in range(3):
        ox, oz = 0.0005 + 0.0065 * i, -0.0285
        corners = [(-0.0026, -0.0040), (-0.0006, -0.0040), (0.0026, 0.0040), (0.0006, 0.0040)]
        _decal_fan(mb, face, side, HEAD, "blush", "always", ("blush", 0.0, 0.0, ox, oz), [("blush", lx, lz, ox, oz) for lx, lz in corners])
    ox, oz = 0.0105, -0.0270
    drop = [(0.0, 0.0085)] + [(0.0044 * math.sin(a), -0.0022 + 0.0044 * math.cos(a)) for a in (math.radians(d) for d in range(55, 306, 25))]
    _decal_fan(mb, face, side, HEAD, "tear", "always", ("tear", 0.0, 0.0, ox, oz), [("tear", lx, lz, ox, oz) for lx, lz in drop])

    # Scribble eyes: an uneven white blob with a scratchy outline, drawn over the ordinary eye.
    wobble = [1.00, 0.93, 1.05, 0.97, 1.08, 0.94, 1.02, 0.90, 1.06, 0.98, 1.07, 0.95]

    def rim(k, stretch):
        a = 2.0 * math.pi * k / 24
        r = stretch * lerp(wobble[(k // 2) % 12], wobble[(k // 2 + 1) % 12], (k % 2) * 0.5)
        return (0.0245 * r * math.sin(a) + 0.0010, 0.0255 * r * math.cos(a) + 0.0010)

    # Two rings, so the flat triangles stay in front of the curved face and the eye beneath.
    def blob(stretch):
        return [("scribble", *rim(k, stretch), LAYER_SCRIBBLE) for k in list(range(0, 24, 2)) + [0]]

    _decal_fan(mb, face, side, HEAD, "eye-white", "face.eyes_scribble", ("scribble", 0.0010, 0.0010, LAYER_SCRIBBLE), blob(0.5)[:-1])
    _decal_strip(mb, face, side, HEAD, "eye-white", "face.eyes_scribble", blob(0.5), blob(1.0))
    zigzag = [rim(k, 1.09 if k % 2 == 0 else 0.93) for k in range(24)]
    for k in range(24):
        (ax, az), (bx, bz) = zigzag[k], zigzag[(k + 1) % 24]
        length = math.hypot(bx - ax, bz - az)
        nx, nz = -(bz - az) / length * 0.0008, (bx - ax) / length * 0.0008
        lows = [("scribble", ax - nx, az - nz, LAYER_SCRIBBLE_LINE), ("scribble", bx - nx, bz - nz, LAYER_SCRIBBLE_LINE)]
        highs = [("scribble", ax + nx, az + nz, LAYER_SCRIBBLE_LINE), ("scribble", bx + nx, bz + nz, LAYER_SCRIBBLE_LINE)]
        _decal_strip(mb, face, side, HEAD, "scribble", "face.eyes_scribble", lows, highs)


def build_face(mb, L, neck):
    """Adds the head and every face feature to `mb`; returns the FaceRig for the shape keys."""
    s = L.head_h / 0.27
    rows = head_rows(L)
    face = FaceRig(scale=s, chin_z=L.chin_z, eye_x=L.eye_x, eye_z=L.eye_z, rows=rows, neck=neck[1:])
    face.mouth_z = rows[ROW_MOUTH][0]
    _build_skull(mb, face)
    _build_mouth_interior(mb, face)
    for side in (1, -1):
        _build_eye(mb, face, side)
    return face
