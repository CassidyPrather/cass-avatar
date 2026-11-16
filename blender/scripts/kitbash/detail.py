"""Detail without textures: stitching, seams, patches and trims laid onto a finished part as geometry.

The avatar's colours are flat swatches, so anything that would be drawn on a
texture is a thin strip or a small patch floating a hair above the surface
instead. A `Surface` finds where on a part a mark goes; an `Applique`
collects the marks and adds them to the part's mesh, weighted like the
surface under them so they move with it.
"""

import math

import bmesh
import numpy as np
from mathutils import Vector

import cass_spec

from . import common

LIFT = 0.0022


class Surface:
    """Finds points on a part's surface by casting rays at it."""

    def __init__(self, obj):
        self.obj = obj
        self.tree = common.bvh_of(obj)
        self.skin = common.SkinSource(obj)

    def hit(self, origin, direction, reach=1.0):
        """(point, unit normal facing back along the ray), or None when the ray misses."""
        direction = np.asarray(direction, dtype=np.float64)
        direction = direction / np.linalg.norm(direction)
        found = self.tree.ray_cast(Vector(origin), Vector(direction), reach)
        if found[0] is None:
            return None
        normal = np.array(found[1])
        if normal @ direction > 0:
            normal = -normal
        return np.array(found[0]), normal

    def around(self, axis_xy, azimuth, z, reach=0.6):
        """The outermost point at a height, seen from a vertical axis: azimuth 0 is the front, 90 the left."""
        a = math.radians(azimuth)
        outward = np.array((math.sin(a), -math.cos(a), 0.0))
        origin = np.array((axis_xy[0], axis_xy[1], z)) + outward * reach
        return self.hit(origin, -outward, reach)

    def below(self, x, y, top=3.0):
        """The topmost point under (x, y)."""
        return self.hit((x, y, top), (0.0, 0.0, -1.0), top + 1.0)


class Applique:
    def __init__(self, surface):
        self.surface = surface
        self.co, self.faces, self.swatches = [], [], []

    def _vert(self, point):
        self.co.append(tuple(float(c) for c in point))
        return len(self.co) - 1

    def ribbon(self, hits, width, swatch, closed=False, lift=LIFT):
        """A strip along surface points. `hits` are (point, normal) pairs; missing ones (None) break the strip."""
        runs, run = [], []
        for hit in hits:
            if hit is None:
                if len(run) > 1:
                    runs.append(run)
                run = []
            else:
                run.append(hit)
        if len(run) > 1:
            runs.append(run)
        for run in runs:
            loop = closed and len(runs) == 1
            points = np.array([p for p, _n in run])
            normals = np.array([n for _p, n in run])
            count = len(points)
            pairs = []
            for i in range(count):
                before = points[(i - 1) % count] if loop or i > 0 else points[i]
                after = points[(i + 1) % count] if loop or i < count - 1 else points[i]
                along = after - before
                across = np.cross(normals[i], along)
                length = np.linalg.norm(across)
                across = across / length if length > 1e-9 else np.zeros(3)
                base = points[i] + normals[i] * lift
                pairs.append((self._vert(base + across * width / 2.0), self._vert(base - across * width / 2.0)))
            for i in range(count if loop else count - 1):
                a, b = pairs[i], pairs[(i + 1) % count]
                self.faces.append((a[0], a[1], b[1], b[0]))
                self.swatches.append(swatch)

    def patch(self, hits, swatch, lift=LIFT):
        """A filled polygon through surface points, fanned from their middle."""
        hits = [hit for hit in hits if hit is not None]
        if len(hits) < 3:
            return
        ring = [self._vert(point + normal * lift) for point, normal in hits]
        centre = self._vert(np.mean([point + normal * lift for point, normal in hits], axis=0))
        for i in range(len(ring)):
            self.faces.append((ring[i], ring[(i + 1) % len(ring)], centre))
            self.swatches.append(swatch)

    def solid(self, points, faces, swatch):
        """Free-standing geometry (a pull strap, a heel) given as points and index tuples."""
        start = len(self.co)
        for point in points:
            self._vert(point)
        for corners in faces:
            self.faces.append(tuple(start + i for i in corners))
            self.swatches.append(swatch)

    def apply(self, palette, tiles, tile):
        """Adds everything collected to the part's mesh."""
        if not self.faces:
            return
        obj = self.surface.obj
        mesh = obj.data
        first_vertex, first_face = len(mesh.vertices), len(mesh.polygons)
        weights = self.surface.skin.sample(np.array(self.co))
        table = common.weights_of(obj)
        bm = bmesh.new()
        bm.from_mesh(mesh)
        new = [bm.verts.new(position) for position in self.co]
        for corners in self.faces:
            face = bm.faces.new([new[i] for i in corners])
            face.smooth = True
        bm.to_mesh(mesh)
        bm.free()
        mesh.update()

        count = len(mesh.vertices)
        merged = {}
        for name in set(table) | set(weights):
            column = np.zeros(count)
            if name in table:
                column[:first_vertex] = table[name]
            if name in weights:
                column[first_vertex:] = weights[name]
            merged[name] = column
        common.set_weights(obj, merged)

        added = list(range(first_face, len(mesh.polygons)))
        common.set_swatches(mesh, palette, self.swatches, added)
        uv = cass_spec.tile_uv(tiles["by_id"][tile])
        common.paint_faces(mesh, cass_spec.UV_TILE, np.tile(uv, (len(added), 1)), added)
        mesh.polygons.foreach_set("material_index", [0] * len(mesh.polygons))
