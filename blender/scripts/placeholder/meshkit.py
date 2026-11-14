"""A small polygon builder for the placeholder meshes.

Every face carries a palette swatch and a discard tile from the moment it is
created, and every vertex carries its bone weights, so the UV and skinning
contracts hold by construction rather than by a later painting pass.
"""

import math

import bpy

import cass_spec


def smoothstep(t):
    t = min(1.0, max(0.0, t))
    return t * t * (3.0 - 2.0 * t)


def lerp(a, b, t):
    return a + (b - a) * t


def interp(table, x):
    """Piecewise-linear lookup in rows of (x, v0, v1, ...) sorted by x either way; clamps at the ends."""
    rows = table if table[0][0] <= table[-1][0] else table[::-1]
    if x <= rows[0][0]:
        return rows[0][1:]
    for lo, hi in zip(rows, rows[1:]):
        if x <= hi[0]:
            t = (x - lo[0]) / (hi[0] - lo[0])
            return tuple(lerp(a, b, t) for a, b in zip(lo[1:], hi[1:]))
    return rows[-1][1:]


def sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def add(a, b):
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def scale(a, s):
    return (a[0] * s, a[1] * s, a[2] * s)


def dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def normalized(a):
    length = math.sqrt(dot(a, a))
    return scale(a, 1.0 / length)


def limit_weights(weights, limit=cass_spec.MAX_INFLUENCES):
    """Keeps the strongest `limit` influences and renormalises (VRChat skins with at most four)."""
    kept = sorted(((w, bone) for bone, w in weights.items() if w > 0.004), reverse=True)[:limit]
    total = sum(w for w, _ in kept)
    return {bone: w / total for w, bone in kept}


class MeshBuilder:
    def __init__(self, name, tile):
        self.name = name
        self.tile = tile
        self.co = []
        self.weights = []
        self.faces = []
        self.face_swatch = []
        self.face_tile = []
        self.mirrored = False

    # -- sides -----------------------------------------------------------
    # Limbs are authored once for the character's left (+X) and replayed
    # mirrored; winding is fixed up by the orientation helpers below.
    def set_side(self, side):
        self.mirrored = side < 0

    @property
    def suffix(self):
        return ".R" if self.mirrored else ".L"

    def bone(self, stem):
        return stem + self.suffix

    # -- vertices ----------------------------------------------------------
    def vert(self, p, weights=None):
        x, y, z = p
        self.co.append((-x if self.mirrored else x, y, z))
        self.weights.append(weights)
        return len(self.co) - 1

    def ring(self, points, weights=None):
        return [self.vert(p, weights) for p in points]

    def centroid(self, indices):
        n = len(indices)
        return tuple(sum(self.co[i][k] for i in indices) / n for k in range(3))

    # -- faces -------------------------------------------------------------
    def face(self, indices, swatch, tile=None):
        self.faces.append(tuple(indices))
        self.face_swatch.append(swatch)
        self.face_tile.append(tile or self.tile)
        return len(self.faces) - 1

    def face_normal(self, f):
        pts = [self.co[i] for i in self.faces[f]]
        n = [0.0, 0.0, 0.0]
        for a, b in zip(pts, pts[1:] + pts[:1]):
            n[0] += (a[1] - b[1]) * (a[2] + b[2])
            n[1] += (a[2] - b[2]) * (a[0] + b[0])
            n[2] += (a[0] - b[0]) * (a[1] + b[1])
        return tuple(n)

    def orient(self, face_ids, outward):
        """Flips the faces as a group so they face `outward(face_centre)` on balance."""
        score = 0.0
        for f in face_ids:
            score += dot(self.face_normal(f), outward(self.centroid(self.faces[f])))
        if score < 0.0:
            for f in face_ids:
                self.faces[f] = self.faces[f][::-1]

    def orient_toward(self, face_ids, direction):
        self.orient(face_ids, lambda _centre: direction)

    def loft(self, rings, swatch, tile=None, closed=True, inward=False):
        """Bridges consecutive vertex rings with quads. `swatch` may be fn(span, segment) -> name.

        Faces point away from the ring centroids (or toward them with `inward`).
        """
        created = []
        for span, (lower, upper) in enumerate(zip(rings, rings[1:])):
            n = len(lower)
            axis = scale(add(self.centroid(lower), self.centroid(upper)), 0.5)
            ids = []
            for k in range(n if closed else n - 1):
                j = (k + 1) % n
                name = swatch(span, k) if callable(swatch) else swatch
                quad = [lower[k], lower[j], upper[j], upper[k]]
                # A ring may reuse a vertex (lip corners); drop the repeat so the face stays valid.
                quad = [v for i, v in enumerate(quad) if v not in quad[:i]]
                if len(quad) >= 3:
                    ids.append(self.face(quad, name, tile))
            sign = -1.0 if inward else 1.0
            self.orient(ids, lambda centre, axis=axis, sign=sign: scale(sub(centre, axis), sign))
            created.extend(ids)
        return created

    def fan(self, centre, ring, swatch, tile=None, closed=True):
        n = len(ring)
        return [
            self.face((centre, ring[k], ring[(k + 1) % n]), swatch, tile)
            for k in range(n if closed else n - 1)
        ]

    def cap(self, ring, tip, swatch, tile=None, weights=None, inward=False):
        """Closes a ring with a fan to a new vertex at `tip` (given in unmirrored space)."""
        base = self.centroid(ring)
        centre = self.vert(tip, weights)
        ids = self.fan(centre, ring, swatch, tile)
        away = sub(self.co[centre], base)
        if dot(away, away) < 1e-12:
            raise ValueError(f"{self.name}: cap tip coincides with its ring centroid")
        self.orient_toward(ids, scale(away, -1.0 if inward else 1.0))
        return centre

    # -- output ------------------------------------------------------------
    def fill_weights(self, field):
        """Weights every vertex that was created without explicit weights from a position field."""
        for i, w in enumerate(self.weights):
            if w is None:
                self.weights[i] = field(self.co[i])

    def triangle_count(self):
        return sum(len(f) - 2 for f in self.faces)

    def to_object(self, collection, armature, material, palette, tiles):
        mesh = bpy.data.meshes.new(self.name)
        mesh.from_pydata(self.co, [], self.faces)
        mesh.validate()
        if len(mesh.polygons) != len(self.faces):
            raise RuntimeError(f"{self.name}: Blender rejected {len(self.faces) - len(mesh.polygons)} faces")
        mesh.materials.append(material)

        swatch_uv = mesh.uv_layers.new(name=cass_spec.UV_PALETTE)
        tile_uv = mesh.uv_layers.new(name=cass_spec.UV_TILE)
        for poly in mesh.polygons:
            colour = palette[self.face_swatch[poly.index]]
            tile = cass_spec.tile_uv(tiles["by_id"][self.face_tile[poly.index]])
            for loop in poly.loop_indices:
                swatch_uv.data[loop].uv = colour
                tile_uv.data[loop].uv = tile
        mesh.uv_layers.active = swatch_uv
        swatch_uv.active_render = True

        obj = bpy.data.objects.new(self.name, mesh)
        collection.objects.link(obj)

        used = {bone for w in self.weights for bone in w}
        groups = {bone.name: obj.vertex_groups.new(name=bone.name) for bone in armature.data.bones if bone.name in used}
        missing = used - set(groups)
        if missing:
            raise RuntimeError(f"{self.name}: weights reference unknown bones {sorted(missing)}")
        for i, w in enumerate(self.weights):
            for bone, value in limit_weights(w).items():
                groups[bone].add([i], value, "REPLACE")

        obj.parent = armature
        modifier = obj.modifiers.new("Armature", "ARMATURE")
        modifier.object = armature
        return obj


def superellipse(cos_t, sin_t, power):
    """Unit superellipse point for angle components; power 2 is a circle, higher is boxier."""
    e = 2.0 / power
    return (math.copysign(abs(cos_t) ** e, cos_t), math.copysign(abs(sin_t) ** e, sin_t))


def polyline_length(points, closed=True):
    pairs = zip(points, points[1:] + points[:1]) if closed else zip(points, points[1:])
    return sum(math.dist(a, b) for a, b in pairs)
