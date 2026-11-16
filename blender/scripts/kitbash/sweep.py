"""Sweeps a flat cross-section along a guide path: the building block of hair, ears and tail.

A guide is a short list of control points with a width at each. The path
through them is a Catmull-Rom spline; the cross-section is carried along it
facing away from a reference point (the head's centre for hair), so strands
lie flat against what they grow from without any hand-set tilt.
"""

import numpy as np

# Cross-sections as (across, outward) pairs on a unit half-width and unit thickness,
# counter-clockwise seen from the root. The outer side is a round dome, the inner a shallower one.
PROFILES = {
    "full": [(-1.0, 0.0), (-0.72, 0.68), (0.0, 1.0), (0.72, 0.68), (1.0, 0.0), (0.62, -0.34), (0.0, -0.46), (-0.62, -0.34)],
    "lite": [(-1.0, 0.0), (0.0, 1.0), (1.0, 0.0), (0.0, -0.36)],
}
# Which sides of each profile face outward (the rest are the underside).
OUTER_SIDES = {"full": (0, 1, 2, 3), "lite": (0, 1)}


def spline(points, count):
    """`count` + 1 points along a Catmull-Rom spline through `points`, evenly spaced by arc length."""
    points = np.asarray(points, dtype=np.float64)
    padded = np.vstack([2 * points[0] - points[1], points, 2 * points[-1] - points[-2]])
    dense = []
    for i in range(len(points) - 1):
        p0, p1, p2, p3 = padded[i], padded[i + 1], padded[i + 2], padded[i + 3]
        for t in np.linspace(0.0, 1.0, 16, endpoint=False):
            dense.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t
                                + (-p0 + 3 * p1 - 3 * p2 + p3) * t ** 3))
    dense.append(points[-1])
    dense = np.array(dense)
    lengths = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(dense, axis=0), axis=1))])
    targets = np.linspace(0.0, lengths[-1], count + 1)
    return np.stack([np.interp(targets, lengths, dense[:, k]) for k in range(3)], axis=1)


def resample(values, count):
    """Values given per control point, linearly resampled to `count` + 1 stations."""
    values = np.asarray(values, dtype=np.float64)
    return np.interp(np.linspace(0.0, 1.0, count + 1), np.linspace(0.0, 1.0, len(values)), values)


def frames(path, away_from=None, facing=None):
    """Tangent, across and outward unit vectors at each path point.

    `away_from` makes outward point away from a position; `facing` fixes it to
    one direction instead (used by ears, which face where the head faces).
    """
    tangent = np.gradient(path, axis=0)
    tangent /= np.linalg.norm(tangent, axis=1, keepdims=True)
    if facing is not None:
        outward = np.tile(np.asarray(facing, dtype=np.float64), (len(path), 1))
    else:
        outward = path - np.asarray(away_from, dtype=np.float64)
    outward = outward - (outward * tangent).sum(axis=1, keepdims=True) * tangent
    outward /= np.maximum(np.linalg.norm(outward, axis=1, keepdims=True), 1e-9)
    across = np.cross(tangent, outward)
    return tangent, across, outward


def strand(part, guide, widths, thickness, segments, level, outer, under, away_from=None, facing=None, tip=True,
           root_cap=False):
    """Adds one swept strand to `part`. Returns the vertex index rings, root first.

    `widths` are half-widths at the guide's control points; a strand with
    `tip` ends in a point. `thickness` is the dome height as a fraction of
    the half-width, or an absolute list per control point.
    """
    path = spline(guide, segments)
    half = resample(widths, segments)
    thick = resample(thickness, segments) if np.ndim(thickness) else half * thickness
    _tangent, across, outward = frames(path, away_from, facing)
    profile = PROFILES[level]
    last = segments - 1 if tip else segments
    rings = []
    for i in range(last + 1):
        rings.append(part.verts([path[i] + across[i] * (a * half[i]) + outward[i] * (o * thick[i]) for a, o in profile]))
    outer_sides = OUTER_SIDES[level]
    part.loft(rings, lambda r, side: outer if side in outer_sides else under)
    if tip:
        n = len(profile)
        apex = part.vert(path[-1])
        for side in range(n):
            part.face((rings[-1][side], rings[-1][(side + 1) % n], apex), outer if side in outer_sides else under)
    if root_cap:
        part.face(rings[0][::-1], under)
    return rings, path
