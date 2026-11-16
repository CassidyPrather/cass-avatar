"""The cowboy hat: a small crown perched on top of the hair, with a wide brim curled up at the sides.

The ears root outside the crown and pass up through the brim, which has a
hole cut for each one. The hat follows the head rigidly.
"""

import math

import numpy as np

from . import common, extras, hair

# Where the brim meets the crown, from the skull's centre, and how far the hat tips back.
SEAT = np.array((0.0, 0.016, 0.138))
TILT = math.radians(12.0)
CROWN = (0.088, 0.104)          # half-width, half-depth at the band
CROWN_HEIGHT = 0.130
CROWN_PINCH = 0.30             # how much narrower the top of the crown is at the front
BAND_HEIGHT = 0.022
BRIM = (0.222, 0.205)           # half-width, half-depth at the edge
BRIM_CURL = 0.062               # how high the sides of the brim roll up
BRIM_DROOP = 0.014              # how far the front and back dip
EAR_HOLE = 0.030


def _place(local, centre):
    """Hat-local coordinates (z up from the band) to the model's."""
    x, y, z = local
    c, s = math.cos(-TILT), math.sin(-TILT)
    return centre + SEAT + np.array((x, y * c - z * s, y * s + z * c))


def build_hat(ctx):
    armature, detail = ctx["armature"], ctx["detail"]
    centre = hair.skull_centre(armature)
    around = max(16, int(round(36 * detail / 4)) * 4)
    part = common.Part("Outfit_Hat", "outfit.default.hat")

    def ring(half_width, half_depth, height, pinch=0.0):
        points = []
        for k in range(around):
            angle = 2.0 * math.pi * k / around
            narrow = 1.0 - pinch * max(0.0, math.cos(angle)) ** 0.5
            points.append(_place((half_width * narrow * math.sin(angle), -half_depth * math.cos(angle),
                                  height(angle) if callable(height) else height), centre))
        return part.verts(points)

    # Crown: band, straight sides drawing in slightly, a rounded shoulder and a dented top.
    w, d = CROWN
    crown = [
        (ring(w, d, 0.0), None),
        (ring(w, d, BAND_HEIGHT), "hat-band"),
        (ring(w * 0.96, d * 0.97, CROWN_HEIGHT * 0.60, CROWN_PINCH * 0.5), "hat"),
        (ring(w * 0.90, d * 0.94, CROWN_HEIGHT * 0.93, CROWN_PINCH), "hat"),
        (ring(w * 0.76, d * 0.86, CROWN_HEIGHT, CROWN_PINCH), "hat"),
        (ring(w * 0.36, d * 0.66, CROWN_HEIGHT * 0.84, CROWN_PINCH), "hat-shade"),
    ]
    for (lower, _), (upper, swatch) in zip(crown, crown[1:]):
        part.loft([lower, upper], swatch)
    part.fan(crown[-1][0], _place((0.0, 0.0, CROWN_HEIGHT * 0.80), centre), "hat-shade")

    # Brim: out from the band, rolled up at the sides and dipped front and back.
    steps = max(3, int(round(6 * detail)))
    first_face = len(part.faces)
    brim = [crown[0][0]]
    for step in range(1, steps + 1):
        q = step / steps
        lift = lambda angle, q=q: BRIM_CURL * q ** 1.7 * math.sin(angle) ** 2 - BRIM_DROOP * q * math.cos(angle) ** 2
        brim.append(ring(w + (BRIM[0] - w) * q, d + (BRIM[1] - d) * q, lift))
    part.loft(brim, "hat")

    # Holes for the ears: drop the brim faces an ear passes through, then round the opening.
    co = np.array(part.co)
    brim_faces = range(first_face, len(part.faces))
    doomed = set()
    for point, direction in extras.ear_axes(armature):
        def off_axis(positions):
            relative = positions - point
            return np.linalg.norm(relative - np.outer(relative @ direction, direction), axis=1)
        rim = set()
        for index in brim_faces:
            corners = list(part.faces[index])
            if off_axis(co[corners].mean(axis=0)[None, :])[0] < EAR_HOLE:
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

    obj = part.to_object(ctx["collection"], armature, ctx["material"], ctx["palette"], ctx["tiles"], sharp_angle=55.0)
    common.rigid_weights(obj, "Head")
    return obj
