"""Mesh, weight and UV helpers shared by the kitbash modules.

Everything here works on plain bpy data with numpy; nothing needs a viewport
or an operator that depends on the UI, so the build runs with `blender -b`.
"""

import math

import bmesh
import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

import cass_spec


def smoothstep(edge0, edge1, x):
    t = np.clip((np.asarray(x, dtype=np.float64) - edge0) / (edge1 - edge0), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def coords(mesh):
    data = np.empty(len(mesh.vertices) * 3, dtype=np.float32)
    mesh.vertices.foreach_get("co", data)
    return data.reshape(-1, 3).astype(np.float64)


def set_coords(mesh, co):
    mesh.vertices.foreach_set("co", np.asarray(co, dtype=np.float32).ravel())
    mesh.update()


def key_coords(block):
    data = np.empty(len(block.data) * 3, dtype=np.float32)
    block.data.foreach_get("co", data)
    return data.reshape(-1, 3).astype(np.float64)


def set_key_coords(block, co):
    block.data.foreach_set("co", np.asarray(co, dtype=np.float32).ravel())


def append_objects(path, names):
    """Appends named objects from another .blend and links them to the scene."""
    with bpy.data.libraries.load(str(path), link=False) as (source, target):
        missing = [name for name in names if name not in source.objects]
        if missing:
            raise RuntimeError(f"{path} has no object(s) {missing}; re-run blender/scripts/intake.py")
        target.objects = list(names)
    for obj in target.objects:
        bpy.context.scene.collection.objects.link(obj)
    return {obj.name: obj for obj in target.objects}


def move_to_collection(obj, collection):
    for other in list(obj.users_collection):
        other.objects.unlink(obj)
    collection.objects.link(obj)


def activate(obj):
    for other in bpy.context.view_layer.objects:
        other.select_set(False)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj


# --- weights -----------------------------------------------------------------


def weights_of(obj):
    """Vertex weights as {group name: array over vertices}."""
    names = [group.name for group in obj.vertex_groups]
    table = {name: np.zeros(len(obj.data.vertices)) for name in names}
    for vertex in obj.data.vertices:
        for element in vertex.groups:
            table[names[element.group]][vertex.index] = element.weight
    return table


def set_weights(obj, table, limit=cass_spec.MAX_INFLUENCES):
    """Replaces all vertex groups with `table`, keeping the strongest `limit` per vertex, normalised."""
    names = [name for name, values in table.items() if np.any(values > 1e-6)]
    matrix = np.stack([table[name] for name in names], axis=1) if names else np.zeros((len(obj.data.vertices), 0))
    if matrix.shape[1] > limit:
        cutoff = -np.sort(-matrix, axis=1)[:, limit - 1:limit]
        matrix = np.where(matrix >= cutoff, matrix, 0.0)
        # Ties at the cutoff could keep more than `limit`; drop the surplus from the right.
        surplus = (matrix > 0).cumsum(axis=1) > limit
        matrix[surplus] = 0.0
    totals = matrix.sum(axis=1, keepdims=True)
    if np.any(totals <= 1e-9):
        raise RuntimeError(f"{obj.name}: {int((totals <= 1e-9).sum())} vertex(es) would have no bone weight")
    matrix = matrix / totals
    obj.vertex_groups.clear()
    for column, name in enumerate(names):
        group = obj.vertex_groups.new(name=name)
        values = matrix[:, column]
        # One call per distinct weight keeps this fast enough for a few thousand vertices.
        for index in np.flatnonzero(values > 1e-6):
            group.add([int(index)], float(values[index]), "REPLACE")


def rigid_weights(obj, bone):
    set_weights(obj, {bone: np.ones(len(obj.data.vertices))})


class SkinSource:
    """Samples another mesh's skin weights at arbitrary points (nearest surface, barycentric)."""

    def __init__(self, obj):
        mesh = obj.data
        mesh.calc_loop_triangles()
        self.co = coords(mesh)
        self.triangles = np.array([tri.vertices[:] for tri in mesh.loop_triangles], dtype=np.int64)
        self.tree = BVHTree.FromPolygons([tuple(v) for v in self.co], [tuple(t) for t in self.triangles])
        self.weights = weights_of(obj)
        self.names = list(self.weights)
        self.matrix = np.stack([self.weights[name] for name in self.names], axis=1)

    def nearest(self, point):
        location, normal, index, distance = self.tree.find_nearest(Vector(point))
        return location, normal, index, distance

    def sample(self, points):
        out = np.zeros((len(points), len(self.names)))
        for row, point in enumerate(points):
            location, _normal, index, _distance = self.tree.find_nearest(Vector(point))
            a, b, c = self.triangles[index]
            bary = _barycentric(np.array(location), self.co[a], self.co[b], self.co[c])
            out[row] = bary[0] * self.matrix[a] + bary[1] * self.matrix[b] + bary[2] * self.matrix[c]
        return {name: out[:, column] for column, name in enumerate(self.names)}


def _barycentric(p, a, b, c):
    v0, v1, v2 = b - a, c - a, p - a
    d00, d01, d11 = v0 @ v0, v0 @ v1, v1 @ v1
    d20, d21 = v2 @ v0, v2 @ v1
    denominator = d00 * d11 - d01 * d01
    if abs(denominator) < 1e-18:
        return np.array([1.0, 0.0, 0.0])
    v = (d11 * d20 - d01 * d21) / denominator
    w = (d00 * d21 - d01 * d20) / denominator
    return np.clip(np.array([1.0 - v - w, v, w]), 0.0, 1.0)


# --- UVs ---------------------------------------------------------------------


def ensure_uv_layers(mesh):
    """Leaves exactly the two contract layers, in order, creating what is missing."""
    # Removing a layer invalidates the others' handles, so look each one up afresh.
    for name in [l.name for l in mesh.uv_layers if l.name not in (cass_spec.UV_PALETTE, cass_spec.UV_TILE)]:
        mesh.uv_layers.remove(mesh.uv_layers[name])
    for name in (cass_spec.UV_PALETTE, cass_spec.UV_TILE):
        if name not in mesh.uv_layers:
            mesh.uv_layers.new(name=name, do_init=False)
    if [l.name for l in mesh.uv_layers] != [cass_spec.UV_PALETTE, cass_spec.UV_TILE]:
        raise RuntimeError(f"{mesh.name}: could not order the UV layers")
    mesh.uv_layers.active = mesh.uv_layers[cass_spec.UV_PALETTE]
    mesh.uv_layers[cass_spec.UV_PALETTE].active_render = True


def loop_polygons(mesh):
    totals = np.empty(len(mesh.polygons), dtype=np.int32)
    mesh.polygons.foreach_get("loop_total", totals)
    return np.repeat(np.arange(len(mesh.polygons)), totals)


def get_uv(mesh, layer):
    data = np.empty(len(mesh.loops) * 2, dtype=np.float32)
    mesh.uv_layers[layer].data.foreach_get("uv", data)
    return data.reshape(-1, 2).astype(np.float64)


def set_uv(mesh, layer, uv):
    mesh.uv_layers[layer].data.foreach_set("uv", np.asarray(uv, dtype=np.float32).ravel())


def paint_faces(mesh, layer, face_uv, faces=None):
    """Puts every loop of each face on that face's UV. `face_uv` is (n, 2) for `faces` (default all)."""
    uv = get_uv(mesh, layer)
    polygon_of_loop = loop_polygons(mesh)
    if faces is None:
        uv[:] = np.asarray(face_uv)[polygon_of_loop]
    else:
        lookup = np.full(len(mesh.polygons), -1)
        lookup[np.asarray(faces)] = np.arange(len(faces))
        chosen = lookup[polygon_of_loop]
        mask = chosen >= 0
        uv[mask] = np.asarray(face_uv)[chosen[mask]]
    set_uv(mesh, layer, uv)


def set_tiles(mesh, tiles, tile_ids):
    """`tile_ids`: one tile id per polygon."""
    lookup = {tile["id"]: cass_spec.tile_uv(tile) for tile in tiles["tiles"]}
    paint_faces(mesh, cass_spec.UV_TILE, np.array([lookup[t] for t in tile_ids]))


def set_swatches(mesh, palette, swatches, faces=None):
    """`swatches`: one swatch name per polygon (or per entry of `faces`)."""
    paint_faces(mesh, cass_spec.UV_PALETTE, np.array([palette[s] for s in swatches]), faces)


# --- building meshes ---------------------------------------------------------


class Part:
    """Accumulates vertices and faces for one generated mesh.

    Faces carry a swatch name and, optionally, a tile id that overrides the
    part's own; `to_object` turns that into the two contract UV layers.
    """

    def __init__(self, name, tile):
        self.name = name
        self.tile = tile
        self.co = []
        self.faces = []
        self.swatches = []
        self.tiles = []
        self.sharp = set()

    def vert(self, point):
        self.co.append(tuple(float(c) for c in point))
        return len(self.co) - 1

    def verts(self, points):
        return [self.vert(p) for p in points]

    def face(self, indices, swatch, tile=None):
        self.faces.append(tuple(int(i) for i in indices))
        self.swatches.append(swatch)
        self.tiles.append(tile or self.tile)

    def loft(self, rings, swatch, closed=True, flip=False, tile=None):
        """Quads between consecutive rings of equal length. `rings` are lists of vertex indices.

        `swatch` may be one name or a function of (ring index, segment index).
        """
        for r in range(len(rings) - 1):
            a, b = rings[r], rings[r + 1]
            n = len(a)
            for i in range(n if closed else n - 1):
                j = (i + 1) % n
                quad = (a[i], a[j], b[j], b[i])
                name = swatch(r, i) if callable(swatch) else swatch
                self.face(quad[::-1] if flip else quad, name, tile)

    def fan(self, ring, centre, swatch, flip=False, tile=None):
        c = self.vert(centre)
        n = len(ring)
        for i in range(n):
            tri = (ring[i], ring[(i + 1) % n], c)
            self.face(tri[::-1] if flip else tri, swatch, tile)
        return c

    def to_object(self, collection, armature, material, palette, tiles, smooth=True, sharp_angle=None, recalc=True):
        mesh = bpy.data.meshes.new(self.name)
        mesh.from_pydata(self.co, [], self.faces)
        mesh.validate()
        mesh.update()
        if recalc:
            # Lofts are written without minding which way each quad winds.
            bm = bmesh.new()
            bm.from_mesh(mesh)
            bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
            bm.to_mesh(mesh)
            bm.free()
        if len(mesh.polygons) != len(self.faces):
            raise RuntimeError(f"{self.name}: {len(self.faces) - len(mesh.polygons)} degenerate face(s) were dropped")
        return finish_object(mesh, self.name, collection, armature, material, palette, tiles, self.swatches, self.tiles,
                             smooth=smooth, sharp_angle=sharp_angle)


def finish_object(mesh, name, collection, armature, material, palette, tiles, swatches, tile_ids, smooth=True,
                  sharp_angle=None):
    """Wraps a mesh as a contract-conforming object: UV layers, material, parent, Armature modifier."""
    ensure_uv_layers(mesh)
    if swatches is not None:
        set_swatches(mesh, palette, swatches)
    set_tiles(mesh, tiles, tile_ids)
    mesh.polygons.foreach_set("use_smooth", [smooth] * len(mesh.polygons))
    if smooth and sharp_angle is not None:
        mesh.set_sharp_from_angle(angle=math.radians(sharp_angle))
    mesh.materials.clear()
    mesh.materials.append(material)
    mesh.polygons.foreach_set("material_index", [0] * len(mesh.polygons))
    obj = bpy.data.objects.new(name, mesh)
    collection.objects.link(obj)
    attach(obj, armature)
    return obj


def finish_mesh(obj, collection, armature, material, tiles, tile_ids, smooth=None):
    """The same wrap-up for a mesh that already is an object (the sourced body and head)."""
    mesh = obj.data
    ensure_uv_layers(mesh)
    set_tiles(mesh, tiles, tile_ids)
    if smooth is not None:
        mesh.polygons.foreach_set("use_smooth", [smooth] * len(mesh.polygons))
    mesh.materials.clear()
    mesh.materials.append(material)
    mesh.polygons.foreach_set("material_index", [0] * len(mesh.polygons))
    move_to_collection(obj, collection)
    obj.matrix_world.identity()
    attach(obj, armature)


def attach(obj, armature):
    obj.parent = armature
    obj.parent_type = "OBJECT"
    for modifier in list(obj.modifiers):
        obj.modifiers.remove(modifier)
    modifier = obj.modifiers.new("Armature", "ARMATURE")
    modifier.object = armature


def join(target, source):
    """Joins `source`'s mesh into `target`'s. Vertex groups and UV layers are matched by name."""
    data = source.data
    with bpy.context.temp_override(active_object=target, object=target, selected_objects=[target, source],
                                   selected_editable_objects=[target, source]):
        bpy.ops.object.join()
    if data.users == 0:
        bpy.data.meshes.remove(data)


def bvh_of(obj):
    mesh = obj.data
    mesh.calc_loop_triangles()
    co = coords(mesh)
    return BVHTree.FromPolygons([tuple(v) for v in co], [tuple(t.vertices) for t in mesh.loop_triangles])


def smooth_vertices(mesh, indices, factor=0.5, repeat=1):
    """Laplacian-relaxes the given vertices in place; everything else stays put."""
    bm = bmesh.new()
    bm.from_mesh(mesh)
    bm.verts.ensure_lookup_table()
    chosen = [bm.verts[i] for i in indices]
    for _ in range(repeat):
        bmesh.ops.smooth_vert(bm, verts=chosen, factor=factor, use_axis_x=True, use_axis_y=True, use_axis_z=True)
    bm.to_mesh(mesh)
    bm.free()
    mesh.update()


def triangle_count(mesh):
    return sum(polygon.loop_total - 2 for polygon in mesh.polygons)
