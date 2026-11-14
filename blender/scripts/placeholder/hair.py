"""Placeholder hair: a short bob with bangs, blonde outside and blue underneath.

An outer shell follows the skull down to its widest row and then hangs to jaw
length with a ragged hem; an inner shell lines the hanging part so the
underside shows the inner colour from below and behind the neck.
"""

import math

from .face import HEAD, HEAD_ROWS
from .meshkit import interp, lerp, smoothstep, superellipse

COLUMNS = 30
WIDEST = 0.166
CROWN = 0.270
UPPER_ROWS = [0.262, 0.245, 0.222, 0.195, WIDEST]
HANG_FRACTIONS = [0.3, 0.6, 0.85, 1.0]
INNER_GAP = 0.007
# Height above the chin (design metres) where each column's hair ends, by
# degrees from the front. Bangs stop above the brows; the sides and back reach the jaw.
BANG_ENDS = {-48: 0.139, -36: 0.150, -24: 0.160, -12: 0.153, 0: 0.163, 12: 0.150, 24: 0.156, 36: 0.146, 48: 0.139}
HANG_ENDS = {60: 0.040, 72: 0.052, 84: 0.034, 96: 0.046, 108: 0.026, 120: 0.038, 132: 0.022, 144: 0.034, 156: 0.020, 168: 0.032, 180: 0.022}


def _column_degrees(k):
    degrees = k * 360 // COLUMNS
    return degrees if degrees <= 180 else degrees - 360


def _end_height(degrees):
    return BANG_ENDS[degrees] if degrees in BANG_ENDS else HANG_ENDS[abs(degrees)]


def build_hair(mb, L):
    s = L.head_h / 0.27

    def shell(h, degrees, inset):
        """Point on the hair surface at design height h; `inset` moves it toward the scalp."""
        a, cy, bf, bb = interp(HEAD_ROWS, max(h, WIDEST))
        up = smoothstep((h - WIDEST) / (CROWN - WIDEST))
        thick = lerp(0.020, 0.014, up) - inset
        # Below the widest row the hair hangs straight and curls in a little at the ends.
        curl = 1.0 - 0.10 * (max(0.0, WIDEST - h) / 0.146) ** 2
        theta = math.radians(degrees)
        c, sn = superellipse(math.cos(theta), math.sin(theta), 2.3)
        depth = (bf + 0.8 * thick) if c > 0 else (bb + thick)
        return (s * curl * (a + thick) * sn, s * (cy - curl * depth * c), L.chin_z + s * (h + thick * up))

    def column_heights(degrees):
        end = _end_height(degrees)
        return UPPER_ROWS + [lerp(WIDEST, end, f) for f in HANG_FRACTIONS]

    degrees = [_column_degrees(k) for k in range(COLUMNS)]
    rows = len(UPPER_ROWS) + len(HANG_FRACTIONS)
    outer = [[mb.vert(shell(column_heights(d)[r], d, 0.0), HEAD) for d in degrees] for r in range(rows)]
    first_hang = len(UPPER_ROWS) - 1

    def strand(span, k):
        # Every third column's hanging part takes the shade swatch so the bob reads as locks.
        return "hair-shade" if span >= first_hang and k % 3 == 2 else "hair"

    mb.loft(outer, strand)
    mb.cap(outer[0], (0.0, 0.004 * s, L.chin_z + s * (CROWN + 0.014)), "hair", weights=HEAD)

    inner = [[mb.vert(shell(column_heights(d)[r], d, INNER_GAP), HEAD) for d in degrees] for r in range(first_hang, rows)]

    def lining(span, k):
        # The blue shows where the underside is seen from behind and below; the fringe stays blonde.
        return "hair-inner" if abs(degrees[k]) >= 84 and abs(degrees[(k + 1) % COLUMNS]) >= 84 else "hair-shade"

    mb.loft(inner, lining, inward=True)
    hem = mb.loft([outer[-1], inner[-1]], lining)
    mb.orient_toward(hem, (0.0, 0.0, -1.0))
