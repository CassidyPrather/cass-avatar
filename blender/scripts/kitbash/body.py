"""The skin below the neck: the SiroinoSotai body base, at either fidelity level.

The base ships with shape keys instead of textures: body-size presets, and
one `<Part>_OFF` key per body segment that shrinks that segment away under
clothing. The presets are baked into the rest shape here. The `_OFF` keys are
not exported, but they are read first, because the vertices each one moves
are exactly a segment bounded by closed edge loops, which is what the skin
zones of Spec/uv-tiles.json need.
"""

import bmesh
import numpy as np

from . import common

# The base's size preset, and how much of its flat-chest key is mixed in (the design is flat-chested).
SIZE_KEY = "All_M"
FLATTEN_KEY = "Breasts_flat"
FLATTEN = 1.0

# Body segment (the stem of its _OFF key) -> skin zone. Garments are cut from the same segments.
SEGMENT_ZONE = {
    "Neck": "always", "Hand": "always", "Wrist": "always",
    # The collarbones and the tops of the shoulders show in an open neckline, so they are never hidden.
    "Chest_01": "always", "Shoulder": "always",
    "Chest_02": "body.torso", "Spine": "body.torso",
    "UpperArm": "body.arms", "Elbow": "body.arms", "LowerArm": "body.arms",
    "Hips": "body.hips",
    "UpperLeg_01": "body.legs", "UpperLeg_02": "body.legs", "Knee": "body.legs", "LowerLeg_01": "body.legs",
    "LowerLeg_02": "body.feet", "Foot": "body.feet", "Toe": "body.feet",
}
SEGMENTS = list(SEGMENT_ZONE)
SEGMENT_ATTRIBUTE = "segment"


def prepare(obj):
    """Bakes the presets, drops the shape keys and records each face's body segment. Returns the body's own UVs per loop."""
    mesh = obj.data
    # The first UV layer is the one the base's normal map is drawn for; the rest are for its nail textures.
    own_uv = common.get_uv(mesh, mesh.uv_layers[0].name)
    blocks = mesh.shape_keys.key_blocks
    basis = common.key_coords(blocks["Basis"])
    moved = np.stack([np.linalg.norm(common.key_coords(blocks[f"{name}_OFF"]) - basis, axis=1) for name in SEGMENTS], axis=1)
    vertex_segment = moved.argmax(axis=1)
    # A vertex that no key really moves (one sits on the sternum) belongs to no segment;
    # faces decide by their other corners.
    vertex_segment[moved.max(axis=1) < 1e-5] = -1

    rest = basis + (common.key_coords(blocks[SIZE_KEY]) - basis) + FLATTEN * (common.key_coords(blocks[FLATTEN_KEY]) - basis)
    obj.shape_key_clear()
    common.set_coords(mesh, rest)

    for attribute in list(mesh.color_attributes):
        mesh.color_attributes.remove(attribute)

    # A face belongs to the segment most of its corners are in; ties go to the lower index,
    # which keeps the result symmetric.
    face_segment = np.empty(len(mesh.polygons), dtype=np.int32)
    for polygon in mesh.polygons:
        corners = vertex_segment[list(polygon.vertices)]
        face_segment[polygon.index] = np.bincount(corners[corners >= 0]).argmax()
    attribute = mesh.attributes.new(SEGMENT_ATTRIBUTE, "INT", "FACE")
    attribute.data.foreach_set("value", face_segment)
    return own_uv


def face_segments(mesh):
    values = np.empty(len(mesh.polygons), dtype=np.int32)
    mesh.attributes[SEGMENT_ATTRIBUTE].data.foreach_get("value", values)
    return values


def zones(mesh):
    return [SEGMENT_ZONE[SEGMENTS[index]] for index in face_segments(mesh)]


def fit_neck(obj, seam_centre, seam_radius, overlap):
    """Flares the top of the neck to the head's neck opening and trims what would sit inside the head.

    The neck keeps its own shape at its base and reaches `seam_radius` at the
    height of `seam_centre`, a hair inside the head's opening so the two
    surfaces never share a depth.
    """
    mesh = obj.data
    co = common.coords(mesh)
    segment = face_segments(mesh)
    neck_faces = np.flatnonzero(segment == SEGMENTS.index("Neck"))
    neck = np.zeros(len(co), dtype=bool)
    for index in neck_faces:
        neck[list(mesh.polygons[index].vertices)] = True
    base = co[neck][:, 2].min()
    top = seam_centre[2]

    ring = neck & (np.abs(co[:, 2] - top) < 0.02)
    offsets = co[ring][:, :2] - np.array(seam_centre[:2])
    current = np.linalg.norm(offsets, axis=1).mean()
    gain = seam_radius / current

    blend = common.smoothstep(base, top, co[:, 2])
    factor = 1.0 + (gain - 1.0) * blend
    centre = np.array(seam_centre[:2])
    moved = co.copy()
    moved[neck, :2] = centre + (co[neck, :2] - centre) * factor[neck, None]
    common.set_coords(mesh, moved)

    # Above the seam the neck is a straight tube of the seam's radius, hidden inside the head.
    above = neck & (moved[:, 2] > top)
    offsets = moved[above, :2] - centre
    moved[above, :2] = centre + offsets / np.maximum(np.linalg.norm(offsets, axis=1, keepdims=True), 1e-9) * seam_radius
    common.set_coords(mesh, moved)

    bm = bmesh.new()
    bm.from_mesh(mesh)
    doomed = [v for v in bm.verts if v.co.z > top + overlap]
    bmesh.ops.delete(bm, geom=doomed, context="VERTS")
    bm.to_mesh(mesh)
    bm.free()
    mesh.update()
