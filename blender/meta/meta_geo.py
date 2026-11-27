"""What the meta generator adds to the robot's kit (blender/bot/bot_geo.py): cloth.

The robot is rigid solids, one bone each, and its faces are painted without knowing their shape.
A robe bends, is symmetric, and wears its trim along edges that slope. So this builder

- builds one half of a solid and mirrors it into the same solid, welded along the middle, with
  weights that may name bones of both sides (`mirrored`, and `_side`, which swaps .L and .R);
- lays strips and fans between rings that need not close on themselves (`strip`, `fan`), turning
  each face outward by an interior point instead of by the order of its corners;
- gives a paint the face it is painting (`facepaint`): where each corner lies on the canvas, so
  that a hem can follow a slanted edge and a stripe can sit exactly on the seam.

One pixel is still PX metres and one texel still one square pixel of surface.
"""

import math

import numpy as np

import bot_geo
from bot_geo import PX, unit, vec, swatch  # noqa: F401  (re-exported for the model)


def facepaint(function):
    """Marks a paint as taking (canvas, face) rather than the canvas alone."""
    function.wants_face = True
    return function


class Face:
    """The face a paint is working on: where points of the model fall on its canvas."""

    def __init__(self, origin, u, v, ox, oy, w, h, corners, names):
        self._origin, self._u, self._v, self._ox, self._oy = origin, u, v, ox, oy
        self.w, self.h = w, h
        self.corners = [self.at(p) for p in corners]
        for name, point in names.items():
            setattr(self, name, self.at(point))

    def at(self, point):
        """Canvas coordinates (x right, y down) of a point of the model on this face's plane."""
        d = np.asarray(point, dtype=np.float64) - self._origin
        return (float(d @ self._u) - self._ox, self._oy - float(d @ self._v))


def edge_distance(a, b, x, y):
    """How far the canvas point (x, y) is from the line through a and b, positive to the left of a -> b
    as the canvas is drawn (y down)."""
    ax, ay = a
    bx, by = b
    length = math.hypot(bx - ax, by - ay)
    if length < 1e-9:
        return math.hypot(x - ax, y - ay)
    return ((bx - ax) * (y - ay) - (by - ay) * (x - ax)) / length


def edge_along(a, b, x, y):
    """How far along a -> b the canvas point (x, y) lies, in pixels from a."""
    ax, ay = a
    bx, by = b
    length = math.hypot(bx - ax, by - ay)
    if length < 1e-9:
        return 0.0
    return ((x - ax) * (bx - ax) + (y - ay) * (by - ay)) / length


class MetaBuilder(bot_geo.Builder):
    def _side(self, name):
        if not self._mirror:
            return name
        if ".L" in name:
            return name.replace(".L", ".R")
        if ".R" in name:
            return name.replace(".R", ".L")
        return name

    # -- one face -----------------------------------------------------------------------------

    def wall(self, points, up, paint, key=None, anchor=(0.5, 1.0), inside=None, inward=False, names=None):
        """A flat (or nearly flat) polygon with a picture of its own.

        `inside` is a point the face must look away from (or towards, with `inward`); without it
        the corners are taken to go counter-clockwise seen from outside. `anchor` says where the
        face sits on its island of whole texels when it does not fill it: (0, ...) puts its left
        edge on the island's, (..., 1) its lowest point on the island's bottom row. `names` are
        points of the model the paint wants located (see Face)."""
        points = [np.asarray(p, dtype=np.float64) for p in points]
        unique = []
        for p in points:
            if not any(self._key(p) == self._key(q) for q in unique):
                unique.append(p)
        points = unique
        if len(points) < 3:
            return None
        normal = bot_geo._newell(points)
        if float(np.linalg.norm(normal)) < 1e-9:
            return None
        normal = unit(normal)
        if inside is not None:
            centre = np.mean(points, axis=0)
            outward = float(normal @ (centre - np.asarray(inside, dtype=np.float64))) > 0.0
            if outward == inward:
                points = points[::-1]
                normal = -normal
        if getattr(paint, "swatch", None):
            return self.planar([points], up, paint, key)

        key = self._auto_key(key)
        up = np.asarray(up, dtype=np.float64)
        v = unit(up - normal * float(up @ normal))
        u = np.cross(v, normal)
        origin = points[0]
        flat = [(float((p - origin) @ u), float((p - origin) @ v)) for p in points]
        us, vs = [c[0] for c in flat], [c[1] for c in flat]
        w = max(1, math.ceil(max(us) - min(us) - 1e-6))
        h = max(1, math.ceil(max(vs) - min(vs) - 1e-6))
        ox = min(us) - (w - (max(us) - min(us))) * anchor[0]
        oy = max(vs) + (h - (max(vs) - min(vs))) * (1.0 - anchor[1])
        face = Face(origin, u, v, ox, oy, w, h, points, names or {})
        if getattr(paint, "wants_face", False):
            island = self.atlas.island(key, w, h, lambda canvas, paint=paint, face=face: paint(canvas, face))
        else:
            island = self.atlas.island(key, w, h, paint)
        uvs = face.corners
        if len(points) <= 4:
            self.face_uv(points, uvs, island)
        else:
            for part in self._convex_parts(points, normal):
                self._emit([points[i] for i in part], island, [uvs[i] for i in part])
        return island

    # -- many faces ---------------------------------------------------------------------------

    def strip(self, rings, wall, key=None, closed=False, inside=None, inward=False, up=None, anchor=(0.5, 1.0)):
        """Faces between consecutive rings of equal length. A ring is a row of points; with `closed`
        the last point joins the first. `wall(band, side)` returns a paint, (paint, key) to share
        texels with another face of the same size, or None for no face. `inside(band, side)` or a
        single point turns the faces; `up(band, side)` is the picture's up, the rise of the strip
        if left out. The paint's face has the corners as `a0`, `a1` (this ring) and `b0`, `b1` (the next)."""
        rings = [[np.asarray(p, dtype=np.float64) for p in ring] for ring in rings]
        n = len(rings[0])
        base = self._auto_key(key)
        for k in range(len(rings) - 1):
            a, b = rings[k], rings[k + 1]
            for i in range(n if closed else n - 1):
                j = (i + 1) % n
                chosen = wall(k, i) if callable(wall) and getattr(wall, "per_side", False) else wall
                if chosen is None:
                    continue
                paint, suffix = chosen if isinstance(chosen, tuple) else (chosen, f"w{k}.{i}")
                rise = (b[i] + b[j]) / 2.0 - (a[i] + a[j]) / 2.0
                chosen_up = up(k, i) if up is not None else None
                if chosen_up is None:
                    chosen_up = rise if float(np.linalg.norm(rise)) > 1e-6 else vec(0, 0, 1)
                point = inside(k, i) if callable(inside) else inside
                placed = anchor(k, i) if callable(anchor) else anchor
                self.wall([a[i], a[j], b[j], b[i]], chosen_up, paint, f"{base}/{suffix}", placed, point, inward,
                          names={"a0": a[i], "a1": a[j], "b0": b[i], "b1": b[j]})

    def fan(self, apex, ring, paint, key=None, closed=False, inside=None, inward=False, up=None, anchor=(0.5, 1.0)):
        """Triangles from a point to each side of a ring. `paint` may be `per_side`, taking the side."""
        apex = np.asarray(apex, dtype=np.float64)
        ring = [np.asarray(p, dtype=np.float64) for p in ring]
        n = len(ring)
        base = self._auto_key(key)
        for i in range(n if closed else n - 1):
            j = (i + 1) % n
            chosen = paint(i) if getattr(paint, "per_side", False) else paint
            if chosen is None:
                continue
            chosen, suffix = chosen if isinstance(chosen, tuple) else (chosen, f"f{i}")
            rise = (ring[i] + ring[j]) / 2.0 - apex
            self.wall([apex, ring[i], ring[j]], rise if up is None else up, chosen, f"{base}/{suffix}", anchor, inside, inward,
                      names={"apex": apex, "a0": ring[i], "a1": ring[j]})


def sides(function):
    function.per_side = True
    return function


def flat_colour(canvas, colour, glow=None):
    canvas.fill(colour, glow)
