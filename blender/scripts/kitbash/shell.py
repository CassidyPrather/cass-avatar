"""Garments cut from the body itself.

A `Shell` starts as a copy of the skin faces of some body segments, so it
has the body's topology and, vertex for vertex, the body's skin weights: it
bends exactly where the body bends and cannot be poked through. It is then
pushed off the skin, reshaped, relaxed until the anatomy underneath no longer
shows, and finished with bands (cuffs, hems, collars) extruded from its open
edges. The same code gives a coarser garment from the coarser body level.
"""

import bmesh
import bpy
import numpy as np

from . import body, common

SWATCH_LAYER = "swatch"


class Shell:
    def __init__(self, skin, segments, swatch):
        self.skin = skin
        self.swatches = [swatch]
        self.bm = bmesh.new()
        self.bm.from_mesh(skin.data)
        layer = self.bm.faces.layers.int[body.SEGMENT_ATTRIBUTE]
        wanted = {body.SEGMENTS.index(name) for name in segments}
        bmesh.ops.delete(self.bm, geom=[f for f in self.bm.faces if f[layer] not in wanted], context="FACES")
        self.swatch_layer = self.bm.faces.layers.int.new(SWATCH_LAYER)
        self.deform = self.bm.verts.layers.deform.verify()
        self.grown = []
        self.bm.normal_update()

    # --- coordinates ---

    def co(self):
        return np.array([v.co[:] for v in self.bm.verts], dtype=np.float64)

    def set_co(self, co):
        for vertex, position in zip(self.bm.verts, co):
            vertex.co = position
        self.bm.normal_update()

    def normals(self):
        return np.array([v.normal[:] for v in self.bm.verts], dtype=np.float64)

    def inflate(self, distance):
        """Moves every vertex along its normal. `distance` is a number or an array per vertex."""
        self.set_co(self.co() + self.normals() * np.reshape(distance, (-1, 1)))

    def reshape(self, function):
        """Applies `function(co) -> co` to all vertex positions."""
        self.set_co(function(self.co()))

    def relax(self, repeat, factor=0.5):
        """Smooths the interior; open edges stay where they are so bands still meet the body's loops."""
        interior = [v for v in self.bm.verts if not v.is_boundary]
        for _ in range(repeat):
            bmesh.ops.smooth_vert(self.bm, verts=interior, factor=factor, use_axis_x=True, use_axis_y=True, use_axis_z=True)
        self.bm.normal_update()

    # --- bands ---

    def swatch_id(self, name):
        if name not in self.swatches:
            self.swatches.append(name)
        return self.swatches.index(name)

    def open_loops(self):
        """The open edges as lists of BMVerts, one list per connected loop."""
        boundary = [e for e in self.bm.edges if e.is_boundary]
        neighbours = {}
        for edge in boundary:
            a, b = edge.verts
            neighbours.setdefault(a, []).append(b)
            neighbours.setdefault(b, []).append(a)
        seen, loops = set(), []
        for start in neighbours:
            if start in seen:
                continue
            stack, members = [start], []
            seen.add(start)
            while stack:
                vertex = stack.pop()
                members.append(vertex)
                for other in neighbours[vertex]:
                    if other not in seen:
                        seen.add(other)
                        stack.append(other)
            loops.append(members)
        return loops

    def loop_where(self, test):
        """The one open loop whose centroid passes `test(centroid)`."""
        found = [loop for loop in self.open_loops() if test(np.mean([v.co[:] for v in loop], axis=0))]
        if len(found) != 1:
            raise RuntimeError(f"expected one open loop, found {len(found)}")
        return found[0]

    def level(self, loop, direction=None):
        """Puts an open loop in one plane by sliding its vertices along `direction`.

        Without a direction the loop settles onto its own best-fit plane,
        which suits a rim that is not square to any axis, such as a collar.

        Segments of a triangulated body meet on saw-toothed edges; a garment
        wants a clean rim before a band is grown from it.
        """
        points = np.array([v.co[:] for v in loop], dtype=np.float64)
        centre = points.mean(axis=0)
        normal = np.linalg.svd(points - centre)[2][-1]
        if direction is None:
            direction = normal
        direction = np.asarray(direction, dtype=np.float64)
        direction = direction / np.linalg.norm(direction)
        # A loop far from square to the sliding direction is levelled across it instead.
        if abs(normal @ direction) < 0.5:
            normal = direction
        slide = ((centre - points) @ normal) / (direction @ normal)
        for vertex, position in zip(loop, points + slide[:, None] * direction):
            vertex.co = position
        self.bm.normal_update()

    def even_out(self, loop, centre_xy, window=7):
        """Smooths how far a roughly horizontal loop stands from a vertical axis, going round it.

        Levelling straightens a saw-toothed rim along the axis; this takes
        the teeth out of its outline as well.
        """
        centre = np.asarray(centre_xy, dtype=np.float64)
        offsets = np.array([v.co[:2] for v in loop], dtype=np.float64) - centre
        order = np.argsort(np.arctan2(offsets[:, 1], offsets[:, 0]))
        radii = np.linalg.norm(offsets[order], axis=1)
        half = window // 2
        padded = np.concatenate([radii[-half:], radii, radii[:half]])
        smooth = np.convolve(padded, np.ones(window) / window, mode="valid")
        for index, radius, target in zip(order, radii, smooth):
            loop[index].co.x = centre[0] + offsets[index][0] / radius * target
            loop[index].co.y = centre[1] + offsets[index][1] / radius * target
        self.bm.normal_update()

    def band(self, loop, steps):
        """Extrudes an open loop through `steps`, a list of (function(co) -> co, swatch).

        Each step makes one ring of quads; its function maps the previous
        ring's positions to the new ring's. Band vertices are weighted like
        the skin nearest to where they end up (see `to_object`), not like the
        seam they grew from: a seam between two body segments is weighted to
        both, and a hem that kept those weights would tear as the joint bends.
        Returns the last ring.
        """
        ring = list(loop)
        members = set(ring)
        for function, swatch in steps:
            edges = [e for e in self.bm.edges if e.is_boundary and e.verts[0] in members and e.verts[1] in members]
            positions = function(np.array([v.co[:] for v in ring], dtype=np.float64))
            grown = {}
            for vertex, position in zip(ring, positions):
                new = self.bm.verts.new(position)
                new[self.deform] = vertex[self.deform]
                grown[vertex] = new
                self.grown.append(new)
            identifier = self.swatch_id(swatch)
            for edge in edges:
                # Wind against the face the edge already has, so the new quad faces the same way.
                loop_ = edge.link_loops[0]
                a, b = loop_.vert, loop_.link_loop_next.vert
                face = self.bm.faces.new((b, a, grown[a], grown[b]))
                face[self.swatch_layer] = identifier
                face.smooth = True
            ring = [grown[v] for v in ring]
            members = set(ring)
        self.bm.normal_update()
        return ring

    def paint(self, test, swatch):
        """Recolours the faces whose centre passes `test(centre)`."""
        identifier = self.swatch_id(swatch)
        for face in self.bm.faces:
            if test(np.array(face.calc_center_median()[:])):
                face[self.swatch_layer] = identifier

    # --- output ---

    def to_object(self, name, tile, collection, armature, material, palette, tiles):
        mesh = bpy.data.meshes.new(name)
        self.bm.faces.ensure_lookup_table()
        swatches = [self.swatches[f[self.swatch_layer]] for f in self.bm.faces]
        self.bm.verts.index_update()
        bands = [v.index for v in self.grown]
        self.bm.to_mesh(mesh)
        self.bm.free()
        for attribute in (body.SEGMENT_ATTRIBUTE, SWATCH_LAYER):
            if attribute in mesh.attributes:
                mesh.attributes.remove(mesh.attributes[attribute])
        obj = common.finish_object(mesh, name, collection, armature, material, palette, tiles, swatches,
                                   [tile] * len(mesh.polygons))
        # The deform layer indexes vertex groups by position, so the groups must be the skin's, in order.
        for group in self.skin.vertex_groups:
            obj.vertex_groups.new(name=group.name)
        table = common.weights_of(obj)
        if bands:
            sampled = common.SkinSource(self.skin).sample(common.coords(mesh)[bands])
            for name in set(table) | set(sampled):
                column = table.setdefault(name, np.zeros(len(mesh.vertices)))
                column[bands] = sampled.get(name, np.zeros(len(bands)))
        common.set_weights(obj, table)
        return obj


def around_axis(co, start, end):
    """Splits positions into (parameter along the axis, foot point on it, radial offset)."""
    start, end = np.asarray(start, dtype=np.float64), np.asarray(end, dtype=np.float64)
    axis = end - start
    length = np.linalg.norm(axis)
    axis = axis / length
    along = (co - start) @ axis
    foot = start + along[:, None] * axis
    return along / length, foot, co - foot


def ring_to_radius(co, start, end, radius, shift=0.0):
    """Moves a ring onto a circle of `radius` about an axis, `shift` metres further along it."""
    _t, foot, radial = around_axis(co, start, end)
    distance = np.linalg.norm(radial, axis=1, keepdims=True)
    direction = (np.asarray(end, dtype=np.float64) - np.asarray(start, dtype=np.float64))
    direction = direction / np.linalg.norm(direction)
    return foot + direction * shift + radial / np.maximum(distance, 1e-9) * radius


def ring_scaled(co, centre_xy, factor, dz):
    """Scales a roughly horizontal ring about a vertical axis and moves it by `dz`."""
    out = co.copy()
    out[:, :2] = np.asarray(centre_xy) + (co[:, :2] - np.asarray(centre_xy)) * factor
    out[:, 2] += dz
    return out
