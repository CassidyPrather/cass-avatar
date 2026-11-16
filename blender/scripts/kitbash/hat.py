"""The cowboy hat: a creased crown over the top of the head and a wide brim rolled up at the sides.

It is drawn a size too big, as head-wear on this kind of character is. The
ears root outside the crown and pass up through the brim, which has a hole
cut for each one. At the full level the brim has an underside of its own, a
bound edge and a line of stitching, and the band carries a buckle; at lite
the brim is a single sheet. The hat follows the head rigidly.
"""

import math

import numpy as np

from . import common, extras, hair

# Where the brim meets the crown, from the skull's centre, and how far the hat tips back.
SEAT = np.array((0.0, 0.020, 0.112))
TILT = math.radians(11.0)
CROWN = (0.104, 0.124)          # half-width, half-depth at the band
CROWN_HEIGHT = 0.150
CROWN_PINCH = 0.34              # how much narrower the top of the crown is at the front
BAND_HEIGHT = 0.026
BRIM = (0.285, 0.262)           # half-width, half-depth at the edge
BRIM_CURL = 0.085               # how high the sides of the brim roll up
BRIM_DROOP = 0.020              # how far the front and back dip
BRIM_THICKNESS = 0.006
EAR_HOLE = 0.036


def _place(local, centre):
    """Hat-local coordinates (z up from the band) to the model's."""
    x, y, z = local
    c, s = math.cos(-TILT), math.sin(-TILT)
    return centre + SEAT + np.array((x, y * c - z * s, y * s + z * c))


def _unplace(point, centre):
    x, y, z = np.asarray(point, dtype=np.float64) - centre - SEAT
    c, s = math.cos(-TILT), math.sin(-TILT)
    return np.array((x, y * c + z * s, -y * s + z * c))


def _brim_lift(q, angle):
    return BRIM_CURL * q ** 1.7 * math.sin(angle) ** 2 - BRIM_DROOP * q * math.cos(angle) ** 2


def tuck(points, centre):
    """Moves points that would poke through the hat to just inside it.

    Hair is modelled as it grows and then fitted to the hat, the way hair
    is: whatever stands above the brim outside the crown is laid down under
    the brim, and whatever is inside the crown is drawn in clear of its
    wall. With the hat switched off this leaves the hair a little flattened
    where the hat sits.
    """
    w, d = CROWN
    out = np.array(points, dtype=np.float64)
    for index, point in enumerate(out):
        x, y, z = _unplace(point, centre)
        angle = math.atan2(x, -y)
        crown = math.hypot(x / w, y / d)
        if crown < 1.0:
            # Inside the crown's footprint: fine below the band, drawn in above it.
            limit = 0.80 - 0.16 * max(0.0, math.cos(angle)) * min(1.0, max(0.0, z) / (CROWN_HEIGHT * 0.6))
            if z > -0.004 and crown > limit:
                x, y = x * limit / crown, y * limit / crown
            z = min(z, CROWN_HEIGHT * 0.70)
        elif math.hypot(x / BRIM[0], y / BRIM[1]) < 1.03:
            low, high = 0.0, 1.0
            for _ in range(14):
                q = (low + high) / 2.0
                if math.hypot(x / (w + (BRIM[0] - w) * q), y / (d + (BRIM[1] - d) * q)) > 1.0:
                    low = q
                else:
                    high = q
            ceiling = _brim_lift(q, angle) - BRIM_THICKNESS - 0.006
            z = min(z, ceiling)
        else:
            continue
        out[index] = _place((x, y, z), centre)
    return out


def build_hat(ctx):
    armature, detail = ctx["armature"], ctx["detail"]
    centre = hair.skull_centre(armature)
    around = max(12, int(round(28 * detail * detail / 4)) * 4) if detail < 1.0 else 40
    part = common.Part("Outfit_Hat", "outfit.default.hat")

    def ring(half_width, half_depth, height, pinch=0.0):
        points = []
        for k in range(around):
            angle = 2.0 * math.pi * k / around
            narrow = 1.0 - pinch * max(0.0, math.cos(angle)) ** 0.5
            points.append(_place((half_width * narrow * math.sin(angle), -half_depth * math.cos(angle),
                                  height(angle) if callable(height) else height), centre))
        return part.verts(points)

    # Crown: band, sides drawing in, a rounded shoulder, and a top creased front to back.
    w, d = CROWN
    crown = [
        (ring(w, d, 0.0), None),
        (ring(w * 1.01, d * 1.01, BAND_HEIGHT), "hat-band"),
        (ring(w * 0.97, d * 0.98, BAND_HEIGHT + 0.004), "hat"),
        (ring(w * 0.95, d * 0.97, CROWN_HEIGHT * 0.60, CROWN_PINCH * 0.5), "hat"),
        (ring(w * 0.89, d * 0.94, CROWN_HEIGHT * 0.90, CROWN_PINCH), "hat"),
        (ring(w * 0.78, d * 0.88, CROWN_HEIGHT, CROWN_PINCH), "hat"),
        (ring(w * 0.52, d * 0.76, CROWN_HEIGHT * 0.93, CROWN_PINCH), "hat"),
        (ring(w * 0.20, d * 0.66, CROWN_HEIGHT * 0.80, CROWN_PINCH), "hat-shade"),
    ]
    for (lower, _), (upper, swatch) in zip(crown, crown[1:]):
        part.loft([lower, upper], swatch)
    part.fan(crown[-1][0], _place((0.0, 0.0, CROWN_HEIGHT * 0.77), centre), "hat-shade")

    # Brim: out from the band, rolled up at the sides and dipped front and back. It has a top
    # and an underside, joined round the edge by a binding, so it is solid from every angle.
    steps = max(3, int(round(7 * detail)))

    def lift(q):
        return lambda angle: _brim_lift(q, angle)

    first_face = len(part.faces)
    top = [crown[0][0]]
    for step in range(1, steps + 1):
        q = step / steps
        top.append(ring(w + (BRIM[0] - w) * q, d + (BRIM[1] - d) * q, lift(q)))
    for index in range(steps):
        q = (index + 1) / steps
        # A line of stitching near the edge, where the brim is wide enough to show one.
        part.loft([top[index], top[index + 1]], "hat-shade" if detail >= 1.0 and index == steps - 2 else "hat")
    if detail >= 1.0:
        under = []
        for step in range(0, steps + 1):
            q = step / steps
            under.append(ring(w * 0.98 + (BRIM[0] - w * 0.98) * q, d * 0.98 + (BRIM[1] - d * 0.98) * q,
                              lambda angle, q=q: lift(q)(angle) - BRIM_THICKNESS))
        part.loft(under, "hat-shade", flip=True)
        part.loft([top[-1], under[-1]], "hat-band")
    last_face = len(part.faces)

    # Holes for the ears: drop the brim faces an ear passes through, then round the opening.
    co = np.array(part.co)
    doomed = set()
    for point, direction in extras.ear_axes(armature):
        def off_axis(positions):
            relative = positions - point
            return np.linalg.norm(relative - np.outer(relative @ direction, direction), axis=1)
        rim = set()
        for index in range(first_face, last_face):
            corners = list(part.faces[index])
            centre_of_face = co[corners].mean(axis=0)
            # Only where the ear actually is: the axis is a line, and it has an other end.
            if abs((centre_of_face - point) @ direction) > 0.12:
                continue
            if off_axis(centre_of_face[None, :])[0] < EAR_HOLE:
                doomed.add(index)
                rim.update(corners)
        for vertex in rim:
            relative = co[vertex] - point
            radial = relative - (relative @ direction) * direction
            distance = np.linalg.norm(radial)
            if 1e-6 < distance < EAR_HOLE:
                co[vertex] = co[vertex] + radial / distance * (EAR_HOLE - distance)
    part.co = [tuple(position) for position in co]
    for attribute in ("faces", "swatches", "tiles"):
        setattr(part, attribute, [value for index, value in enumerate(getattr(part, attribute)) if index not in doomed])

    if detail >= 1.0:
        # A buckle on the band, front left: a brass frame with the band showing through it.
        for scale, swatch, proud in ((1.0, "boot-stitch", 0.004), (0.55, "hat-band", 0.006)):
            corners = []
            for dx, dz in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
                angle = math.radians(38.0) + dx * scale * 0.16
                corners.append(_place(((w + proud) * math.sin(angle), -(d + proud) * math.cos(angle),
                                       BAND_HEIGHT / 2 + dz * scale * BAND_HEIGHT * 0.62), centre))
            part.face(part.verts(corners), swatch)

    obj = part.to_object(ctx["collection"], armature, ctx["material"], ctx["palette"], ctx["tiles"], sharp_angle=55.0)
    common.rigid_weights(obj, "Head")
    return obj
