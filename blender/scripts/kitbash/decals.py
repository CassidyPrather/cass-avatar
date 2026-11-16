"""Small marks modelled onto the face: blush strokes, tears and the scribbled eyes.

The source face draws these on transparent cards. The avatar's one material
is opaque (and so are VRChat's mobile shaders), so they are geometry here,
laid on the face's surface where a ray from the front lands.

Blush and tears belong to shape keys (MMD's 照れ and 涙): at rest each mark
is collapsed to a point inside the head, and its key unfolds it. The
scribbles are always unfolded and sit on their own discard tile, which the
Afraid expression swaps with the irises' tile.
"""

import bmesh
import numpy as np
from mathutils import Vector

from . import common, face

LIFT = 0.0018            # how far a mark floats above the skin
SCRIBBLE_LIFT = 0.0045   # the scribble has to clear the iris and its highlight

# Per mark: (centre x, centre z) from the eye's own centre on the character's left; mirrored for the right.
BLUSH_STROKES = [(-0.010 + 0.017 * i, -0.062, 0.0045, 0.011) for i in range(3)]        # x, z, half-width, half-height
TEAR = (0.030, -0.040, 0.0085, 0.021)
SCRIBBLE = [(-0.027, 0.014), (-0.014, -0.016), (-0.001, 0.016), (0.012, -0.016), (0.025, 0.013)]
SCRIBBLE_WIDTH = 0.0028


def _eye_centres(mesh):
    """Centre of each iris, as (x, z) seen from the front: left eye, right eye."""
    classes = face.face_classes(mesh)
    co = common.coords(mesh)
    centres = []
    for sign in (1.0, -1.0):
        vertices = sorted({v for p in mesh.polygons if classes[p.index] == face.IRIS and p.center.x * sign > 0 for v in p.vertices})
        points = co[vertices]
        centres.append(((points[:, 0].min() + points[:, 0].max()) / 2.0, (points[:, 2].min() + points[:, 2].max()) / 2.0))
    return centres


def build(head, palette, tiles):
    mesh = head.data
    tree = common.bvh_of(head)
    eyes = _eye_centres(mesh)

    def land(x, z, lift):
        hit = tree.ray_cast(Vector((x, -1.0, z)), Vector((0.0, 1.0, 0.0)), 2.0)
        if hit[0] is None:
            raise RuntimeError(f"decals: nothing under ({x:.3f}, {z:.3f}) on the face")
        return np.array(hit[0]) + np.array(hit[1]) * lift

    marks = []   # (list of shown positions, list of faces as index tuples, swatch, tile, key or None)
    for (eye_x, eye_z), sign in zip(eyes, (1.0, -1.0)):
        for dx, dz, half_width, half_height in BLUSH_STROKES:
            x, z = eye_x + dx * sign, eye_z + dz
            lean = half_height * 0.45 * sign
            corners = [(x - half_width - lean, z - half_height), (x + half_width - lean, z - half_height),
                       (x + half_width + lean, z + half_height), (x - half_width + lean, z + half_height)]
            marks.append(([land(cx, cz, LIFT) for cx, cz in corners], [(0, 1, 2, 3)], "blush", "always", "照れ"))

        dx, dz, radius, height = TEAR
        x, z = eye_x + dx * sign, eye_z + dz
        outline = [(x, z + height * 0.55)]
        for k in range(1, 8):
            angle = np.pi * (0.5 + k / 4.0)
            swell = 1.0 if 2 <= k <= 6 else 0.72
            outline.append((x + np.cos(angle) * radius * swell, z - height * 0.45 + np.sin(angle) * radius * 0.9 + radius * 0.2))
        points = [land(x, z - height * 0.2, LIFT)] + [land(cx, cz, LIFT) for cx, cz in outline]
        fan = [(0, 1 + k, 1 + (k + 1) % len(outline)) for k in range(len(outline))]
        marks.append((points, fan, "tear", "always", "涙"))

        points, quads = [], []
        zigzag = [(eye_x + dx * sign, eye_z + dz) for dx, dz in SCRIBBLE]
        for k, (cx, cz) in enumerate(zigzag):
            before, after = zigzag[max(k - 1, 0)], zigzag[min(k + 1, len(zigzag) - 1)]
            along = np.array((after[0] - before[0], after[1] - before[1]))
            across = np.array((-along[1], along[0])) / np.linalg.norm(along) * SCRIBBLE_WIDTH
            points.append(land(cx + across[0], cz + across[1], SCRIBBLE_LIFT))
            points.append(land(cx - across[0], cz - across[1], SCRIBBLE_LIFT))
            if k:
                quads.append((2 * k - 2, 2 * k - 1, 2 * k + 1, 2 * k))
        marks.append((points, quads, "scribble", "face.eyes_scribble", None))

    first_vertex, first_face = len(mesh.vertices), len(mesh.polygons)
    bm = bmesh.new()
    bm.from_mesh(mesh)
    deform = bm.verts.layers.deform.verify()
    head_group = head.vertex_groups["Head"].index
    part_layer = bm.faces.layers.int[face.CLASS_ATTRIBUTE]
    rest, swatches, tile_ids, moves = [], [], [], {}
    for points, faces, swatch, tile, key in marks:
        shown = np.array(points)
        # Folded away: a point a little way inside the head, behind the mark.
        hidden = np.tile(shown.mean(axis=0) + np.array((0.0, 0.014, 0.0)), (len(shown), 1)) if key else shown
        vertices = []
        for position in hidden:
            vertex = bm.verts.new(position)
            vertex[deform][head_group] = 1.0
            vertices.append(vertex)
        for corners in faces:
            new = bm.faces.new([vertices[i] for i in corners])
            new[part_layer] = face.SKIN
            new.smooth = True
            swatches.append(swatch)
            tile_ids.append(tile)
        if key:
            start = first_vertex + len(rest)
            moves.setdefault(key, []).append((start, shown - hidden))
        rest.extend(hidden)
    bm.to_mesh(mesh)
    bm.free()
    mesh.update()

    # New vertices exist in every shape key; put them at rest in each, then unfold them in their own.
    rest = np.array(rest)
    blocks = mesh.shape_keys.key_blocks
    for block in blocks:
        co = common.key_coords(block)
        co[first_vertex:] = rest
        common.set_key_coords(block, co)
    basis = common.key_coords(blocks["Basis"])
    for key, pieces in moves.items():
        delta = np.zeros_like(basis)
        for start, offsets in pieces:
            delta[start:start + len(offsets)] = offsets
        face.add_key(head, key, delta)

    new_faces = list(range(first_face, len(mesh.polygons)))
    common.set_swatches(mesh, palette, swatches, new_faces)
    lookup = {tile["id"]: common.cass_spec.tile_uv(tile) for tile in tiles["tiles"]}
    common.paint_faces(mesh, common.cass_spec.UV_TILE, np.array([lookup[t] for t in tile_ids]), new_faces)
    mesh.polygons.foreach_set("material_index", [0] * len(mesh.polygons))
