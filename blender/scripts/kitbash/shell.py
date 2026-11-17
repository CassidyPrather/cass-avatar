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

    def relax_near(self, loop, reach, repeat, factor=0.5):
        """Smooths the interior within `reach` of an open loop, to settle the cloth after its rim has been moved."""
        rim = np.array([v.co[:] for v in loop], dtype=np.float64)
        near = [v for v in self.bm.verts if not v.is_boundary
                and np.linalg.norm(rim - np.array(v.co[:]), axis=1).min() < reach]
        for _ in range(repeat):
            bmesh.ops.smooth_vert(self.bm, verts=near, factor=factor, use_axis_x=True, use_axis_y=True, use_axis_z=True)
        self.bm.normal_update()

    def clear_skin(self, clearance):
        """Lifts every vertex that has sunk to within `clearance` of the skin back out to that distance.

        Relaxing a tube draws it in, and a shell that started a centimetre
        off the body can end up under it in places. This runs after the
        shaping is done, so the cloth is smooth where it is loose and still
        never lets the skin through.
        """
        if not hasattr(self, "_skin_tree"):
            self._skin_tree = common.bvh_of(self.skin)
        for vertex in self.bm.verts:
            location, normal, _index, _distance = self._skin_tree.find_nearest(vertex.co)
            height = (vertex.co - location).dot(normal)
            if height < clearance:
                vertex.co = vertex.co + normal * (clearance - height)
        self.bm.normal_update()

    def clear_of(self, tree, clearance):
        """The same for another part worn underneath, given as its BVH: the shorts under the sweater's hem."""
        for vertex in self.bm.verts:
            location, normal, _index, distance = tree.find_nearest(vertex.co)
            if distance > clearance * 4.0:
                continue
            height = (vertex.co - location).dot(normal)
            if height < clearance:
                vertex.co = vertex.co + normal * (clearance - height)
        self.bm.normal_update()

    def smooth_loop(self, loop, repeat=3):
        """Eases the kinks out of an open loop by moving each vertex towards its two neighbours on the loop."""
        members = set(loop)
        neighbours = {v: [e.other_vert(v) for e in v.link_edges if e.is_boundary and e.other_vert(v) in members] for v in loop}
        for _ in range(repeat):
            moved = {v: (v.co + sum((n.co for n in near), v.co * 0.0) / len(near)) / 2.0 for v, near in neighbours.items() if len(near) == 2}
            for vertex, position in moved.items():
                vertex.co = position
        self.bm.normal_update()

    def fair_loop(self, loop, clearance=None, order=3):
        """Redraws a roughly level open loop as an even, symmetric oval about a vertical axis.

        Radius and height are each fitted as a few cosine harmonics of the
        bearing from the axis (cosines only, so left and right match). With
        `clearance`, the oval is then grown until no vertex on it is nearer
        the skin than that. Returns the axis as (x, y).
        """
        co = np.array([v.co[:] for v in loop], dtype=np.float64)
        axis = np.array((0.0, (co[:, 1].min() + co[:, 1].max()) / 2.0))
        bearing = np.arctan2(co[:, 0], -(co[:, 1] - axis[1]))
        basis = np.stack([np.cos(k * bearing) for k in range(order + 1)], axis=1)
        radius = basis @ np.linalg.lstsq(basis, np.linalg.norm(co[:, :2] - axis, axis=1), rcond=None)[0]
        height = basis @ np.linalg.lstsq(basis, co[:, 2], rcond=None)[0]
        grow = 0.0
        if clearance is not None:
            if not hasattr(self, "_skin_tree"):
                self._skin_tree = common.bvh_of(self.skin)
            for _ in range(4):
                short = 0.0
                for r, z, b in zip(radius + grow, height, bearing):
                    point = (r * np.sin(b), axis[1] - r * np.cos(b), z)
                    location, normal, _index, _distance = self._skin_tree.find_nearest(point)
                    short = max(short, clearance - (np.array(point) - np.array(location)) @ np.array(normal))
                if short <= 1e-5:
                    break
                grow += short
        for vertex, r, z, b in zip(loop, radius + grow, height, bearing):
            vertex.co = (r * np.sin(b), axis[1] - r * np.cos(b), z)
        self.bm.normal_update()
        radius_fit = np.linalg.lstsq(basis, radius + grow, rcond=None)[0]
        height_fit = np.linalg.lstsq(basis, height, rcond=None)[0]
        # The oval, for whatever is to be laid round it: (axis, radius by bearing, height by bearing), bearings in radians.
        self.faired = (axis, lambda b: float(sum(c * np.cos(k * b) for k, c in enumerate(radius_fit))),
                       lambda b: float(sum(c * np.cos(k * b) for k, c in enumerate(height_fit))))
        return axis

    def cut_out(self, planes, where, inside):
        """Cuts an opening with straight edges: the shell is split along each plane, then the faces `inside` go.

        `planes` are (point, normal) pairs; `where` and `inside` are tests of
        a face's centre. Only faces passing `where` are split or removed, so
        an opening in the front leaves the back alone.
        """
        for point, normal in planes:
            faces = [f for f in self.bm.faces if where(np.array(f.calc_center_median()[:]))]
            geometry = list({v for f in faces for v in f.verts}) + list({e for f in faces for e in f.edges}) + faces
            bmesh.ops.bisect_plane(self.bm, geom=geometry, dist=1e-6, plane_co=point, plane_no=normal,
                                   clear_outer=False, clear_inner=False)
        doomed = []
        for face in self.bm.faces:
            centre = np.array(face.calc_center_median()[:])
            if where(centre) and inside(centre):
                doomed.append(face)
        bmesh.ops.delete(self.bm, geom=doomed, context="FACES")
        self.bm.normal_update()

    def fringe(self, ring, swatch, length, spacing, width, lift=0.0015):
        """Hangs a row of pointed strips from a band's last ring, `spacing` apart: a fringed hem."""
        self.bm.normal_update()
        identifier = self.swatch_id(swatch)
        order = _chain(ring)
        lengths = [(b.co - a.co).length for a, b in zip(order, order[1:])]
        total = sum(lengths)
        number = max(1, int(round(total / spacing)))
        segment, start = 0, 0.0
        for k in range(number):
            target = total * (k + 0.5) / number
            while start + lengths[segment] < target and segment < len(lengths) - 1:
                start += lengths[segment]
                segment += 1
            a, b = order[segment], order[segment + 1]
            t = (target - start) / max(lengths[segment], 1e-9)
            point = a.co.lerp(b.co, t)
            normal = a.normal.lerp(b.normal, t)
            normal.z = 0.0
            if normal.length < 1e-9:
                continue
            normal.normalize()
            along = (b.co - a.co).normalized() * (width / 2.0)
            source = a if t < 0.5 else b
            corners = []
            for position in (point - along + normal * lift, point + along + normal * lift,
                             point + normal * (lift + 0.004) - type(point)((0.0, 0.0, length * (0.85 + 0.15 * ((k * 7) % 5) / 4.0)))):
                new = self.bm.verts.new(position)
                new[self.deform] = source[self.deform]
                self.grown.append(new)
                corners.append(new)
            face = self.bm.faces.new(corners)
            face.normal_update()
            if face.normal.dot(normal) < 0.0:
                face.normal_flip()
            face[self.swatch_layer] = identifier
            face.smooth = True
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

    def cut(self, point, normal, centre=None, reach=None):
        """Cuts the shell with a plane and discards what lies on the side `normal` points to.

        Segments of a triangulated body meet on saw-toothed edges. A garment
        gets its rims by being cut straight a little inside those edges, so
        every rim is a clean line with new vertices on it. With `centre` and
        `reach`, only geometry within that distance of the centre is cut,
        which keeps a collar's plane from also slicing the shoulders.
        Returns the new rim as a list of vertices.
        """
        normal = np.asarray(normal, dtype=np.float64)
        normal = normal / np.linalg.norm(normal)
        point = np.asarray(point, dtype=np.float64)
        if centre is None:
            geometry = self.bm.verts[:] + self.bm.edges[:] + self.bm.faces[:]
        else:
            centre = np.asarray(centre, dtype=np.float64)
            near = {v for v in self.bm.verts if np.linalg.norm(np.array(v.co[:]) - centre) < reach}
            # Any face that reaches into the region is cut whole, or its far part would be left standing.
            faces = [f for f in self.bm.faces if any(v in near for v in f.verts)]
            edges = {e for f in faces for e in f.edges}
            geometry = list({v for f in faces for v in f.verts}) + list(edges) + faces
        result = bmesh.ops.bisect_plane(self.bm, geom=geometry, dist=1e-6, plane_co=point, plane_no=normal, clear_outer=True)
        self.bm.normal_update()
        made = {g for g in result["geom_cut"] if isinstance(g, bmesh.types.BMVert) and g.is_valid and g.is_boundary}
        if len(made) < 3:
            raise RuntimeError("a cut produced no rim; its plane misses the garment")
        # The whole of each open loop the cut made, so a band grown from it has no gaps.
        rim = [v for loop in self.open_loops() if any(v in made for v in loop) for v in loop]
        stray = [v for v in rim if abs((np.array(v.co[:]) - point) @ normal) > 1e-4]
        if stray:
            worst = max(abs((np.array(v.co[:]) - point) @ normal) for v in stray)
            raise RuntimeError(f"a cut left {len(stray)} vertex(es) of the old edge on its rim, up to {worst:.4f} m off the plane; cut deeper")
        return rim

    def cut_rim(self, loop, direction, margin=0.004):
        """Cuts off a saw-toothed open loop: a plane square to `direction`, just inside the loop's deepest tooth."""
        direction = np.asarray(direction, dtype=np.float64)
        direction = direction / np.linalg.norm(direction)
        points = np.array([v.co[:] for v in loop], dtype=np.float64)
        centre = points.mean(axis=0)
        depth = ((points - centre) @ direction).min() - margin
        reach = np.linalg.norm(points - centre, axis=1).max() * 1.5
        return self.cut(centre + direction * depth, direction, centre, reach)

    def cut_fitted(self, loop, towards, margin=0.004):
        """Cuts off a saw-toothed open loop that lies square to no axis (an armhole): with the plane that fits it best.

        `towards` says which side of that plane is discarded, roughly.
        """
        points = np.array([v.co[:] for v in loop], dtype=np.float64)
        centre = points.mean(axis=0)
        normal = np.linalg.svd(points - centre)[2][-1]
        if normal @ np.asarray(towards, dtype=np.float64) < 0.0:
            normal = -normal
        return self.cut_within(loop, centre, normal, margin)

    def cut_within(self, loop, point, normal, margin=0.004):
        """Cuts with a given plane, moved in as far as it must be to clear every tooth of an open loop."""
        normal = np.asarray(normal, dtype=np.float64)
        normal = normal / np.linalg.norm(normal)
        points = np.array([v.co[:] for v in loop], dtype=np.float64)
        centre = points.mean(axis=0)
        needed = ((points - np.asarray(point)) @ normal).min() - margin
        reach = np.linalg.norm(points - centre, axis=1).max() * 2.2
        return self.cut(np.asarray(point) + normal * min(0.0, needed), normal, centre, reach)

    def band(self, loop, steps, rings=None):
        """Extrudes an open loop through `steps`, a list of (function(co) -> co, swatch).

        Each step makes one ring of quads; its function maps the previous
        ring's positions to the new ring's. Band vertices are weighted like
        the skin nearest to where they end up (see `to_object`), not like the
        seam they grew from: a seam between two body segments is weighted to
        both, and a hem that kept those weights would tear as the joint bends.
        Returns the last ring; `rings`, if given, is a list that receives every ring made.
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
            if rings is not None:
                rings.append(ring)
        self.bm.normal_update()
        return ring

    def ribs(self, ring_a, ring_b, swatch, spacing=0.010, width=0.0024, lift=0.0012, inset=0.12):
        """Lays thin strips from one band ring towards the next, evenly `spacing` apart: the lines of a ribbed knit.

        The rings are two results of `band` grown from the same loop, so vertex i of one is
        above vertex i of the other. Each strip stops `inset` of the way short of both rings.
        """
        self.bm.normal_update()
        identifier = self.swatch_id(swatch)
        order = _walk(ring_a, set(ring_a))
        partner = dict(zip(ring_a, ring_b))
        count = len(order)
        lengths = [(order[(i + 1) % count].co - order[i].co).length for i in range(count)]
        total = sum(lengths)
        number = max(3, int(round(total / spacing)))
        segment, start = 0, 0.0
        for k in range(number):
            target = total * (k + 0.5) / number
            while start + lengths[segment] < target and segment < count - 1:
                start += lengths[segment]
                segment += 1
            t = (target - start) / max(lengths[segment], 1e-9)
            a, b = order[segment], order[(segment + 1) % count]
            low = a.co.lerp(b.co, t)
            high = partner[a].co.lerp(partner[b].co, t)
            normal = (a.normal.lerp(b.normal, t) + partner[a].normal.lerp(partner[b].normal, t)).normalized()
            along = high - low
            across = normal.cross(along)
            if across.length < 1e-9:
                continue
            across = across.normalized() * (width / 2.0)
            source = a if t < 0.5 else b
            corners = []
            for fraction, side in ((inset, -1.0), (inset, 1.0), (1.0 - inset, 1.0), (1.0 - inset, -1.0)):
                new = self.bm.verts.new(low + along * fraction + normal * lift + across * side)
                new[self.deform] = source[self.deform]
                self.grown.append(new)
                corners.append(new)
            face = self.bm.faces.new(corners)
            face.normal_update()
            if face.normal.dot(normal) < 0.0:
                face.normal_flip()
            face[self.swatch_layer] = identifier
            face.smooth = True
        self.bm.normal_update()

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


def _chain(ring):
    """The vertices of a ring or an open run of vertices, in order along it."""
    members = set(ring)
    near = {v: [e.other_vert(v) for e in v.link_edges if e.other_vert(v) in members] for v in ring}
    ends = [v for v in ring if len(near[v]) == 1]
    order, previous, current = [], None, ends[0] if ends else ring[0]
    while current is not None and len(order) < len(ring):
        order.append(current)
        following = [v for v in near[current] if v is not previous and v not in order[:1]]
        previous, current = current, (following[0] if following else None)
    return order


def _walk(ring, members):
    """The vertices of a closed ring in order round it."""
    def neighbours(vertex):
        return [e.other_vert(vertex) for e in vertex.link_edges if e.other_vert(vertex) in members]

    order, previous, current = [ring[0]], None, ring[0]
    while True:
        following = [v for v in neighbours(current) if v is not previous and v is not order[0]]
        if not following or len(order) >= len(ring):
            return order
        previous, current = current, following[0]
        order.append(current)


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
