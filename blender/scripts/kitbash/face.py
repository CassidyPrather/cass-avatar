"""The head: the face of HENGE's Mizunashi Hiyori, refitted and re-keyed.

The source face carries its own expression set (VRChat visemes, the ARKit
shapes and the author's `blend_*` shapes). None of those names are exported.
`RECIPES` rebuilds every name in Spec/blendshapes.json as a weighted sum of
source shapes, optionally limited to one side of the face or to one lip, so
the contract stays the spec's and the face behind it can be swapped later by
writing a new table.
"""

import bmesh
import numpy as np
from mathutils import Matrix, Vector

from . import common

# Source shapes whose geometry is kept from the overlay material; everything else on it
# (manga marks, tear and blush cards that need a transparent material) is deleted.
KEPT_OVERLAYS = {"heart": "blend_exeye_heart", "star": "blend_exeye_twinkle"}

# Regions a recipe can be limited to. L and R are the character's left (+X) and right.
L, R, UP, LO = "L", "R", "UP", "LO"


def _pair(key):
    """A shape that exists per side in the source, for both sides at once."""
    return {f"{key}Left": 1.0, f"{key}Right": 1.0}


RECIPES = {
    # --- visemes ---
    **{f"vrc.v_{v}": {f"vrc.v_{v}": 1.0} for v in
       ("sil", "pp", "ff", "th", "dd", "kk", "ch", "ss", "nn", "rr", "aa", "e", "ih", "oh", "ou")},

    # --- face tracking (Unified Expressions), from the ARKit set ---
    "EyeClosedLeft": {"eyeBlinkLeft": 1.0}, "EyeClosedRight": {"eyeBlinkRight": 1.0},
    "EyeSquintLeft": {"eyeSquintLeft": 1.0}, "EyeSquintRight": {"eyeSquintRight": 1.0},
    "EyeWideLeft": {"eyeWideLeft": 1.0}, "EyeWideRight": {"eyeWideRight": 1.0},
    "EyeConstrictLeft": {"blend_Eye_small_L": 1.0}, "EyeConstrictRight": {"blend_Eye_small_R": 1.0},
    "BrowLowererLeft": {"browDownLeft": 1.0}, "BrowLowererRight": {"browDownRight": 1.0},
    "BrowPinchLeft": {"blend_brow_in_L": 0.5}, "BrowPinchRight": {"blend_brow_in_R": 0.5},
    "BrowInnerUpLeft": ({"browInnerUp": 1.0}, L), "BrowInnerUpRight": ({"browInnerUp": 1.0}, R),
    "BrowOuterUpLeft": {"browOuterUpLeft": 1.0}, "BrowOuterUpRight": {"browOuterUpRight": 1.0},
    # The source has no nose shapes; a sneer is read from the lip and cheek it drags along.
    "NoseSneerLeft": {"mouthUpperUpLeft": 0.35, "cheekSquintLeft": 0.5},
    "NoseSneerRight": {"mouthUpperUpRight": 0.35, "cheekSquintRight": 0.5},
    "CheekSquintLeft": {"cheekSquintLeft": 1.0}, "CheekSquintRight": {"cheekSquintRight": 1.0},
    "CheekPuffLeft": ({"cheekPuff": 1.0}, L), "CheekPuffRight": ({"cheekPuff": 1.0}, R),
    "JawOpen": {"jawOpen": 1.0}, "JawLeft": {"jawLeft": 1.0}, "JawRight": {"jawRight": 1.0},
    "JawForward": {"jawForward": 1.0}, "JawBackward": {"jawForward": -0.6},
    "MouthClosed": {"mouthClose": 1.0},
    "LipSuckUpperLeft": ({"mouthRollUpper": 1.0}, L), "LipSuckUpperRight": ({"mouthRollUpper": 1.0}, R),
    "LipSuckLowerLeft": ({"mouthRollLower": 1.0}, L), "LipSuckLowerRight": ({"mouthRollLower": 1.0}, R),
    "LipFunnelUpperLeft": ({"mouthFunnel": 1.0}, L, UP), "LipFunnelUpperRight": ({"mouthFunnel": 1.0}, R, UP),
    "LipFunnelLowerLeft": ({"mouthFunnel": 1.0}, L, LO), "LipFunnelLowerRight": ({"mouthFunnel": 1.0}, R, LO),
    "LipPuckerUpperLeft": ({"mouthPucker": 1.0}, L, UP), "LipPuckerUpperRight": ({"mouthPucker": 1.0}, R, UP),
    "LipPuckerLowerLeft": ({"mouthPucker": 1.0}, L, LO), "LipPuckerLowerRight": ({"mouthPucker": 1.0}, R, LO),
    "MouthUpperUpLeft": {"mouthUpperUpLeft": 1.0}, "MouthUpperUpRight": {"mouthUpperUpRight": 1.0},
    "MouthLowerDownLeft": {"mouthLowerDownLeft": 1.0}, "MouthLowerDownRight": {"mouthLowerDownRight": 1.0},
    "MouthUpperLeft": ({"mouthLeft": 1.0}, UP), "MouthUpperRight": ({"mouthRight": 1.0}, UP),
    "MouthLowerLeft": ({"mouthLeft": 1.0}, LO), "MouthLowerRight": ({"mouthRight": 1.0}, LO),
    "MouthCornerPullLeft": {"mouthSmileLeft": 1.0}, "MouthCornerPullRight": {"mouthSmileRight": 1.0},
    "MouthCornerSlantLeft": {"mouthSmileLeft": 0.3}, "MouthCornerSlantRight": {"mouthSmileRight": 0.3},
    "MouthFrownLeft": {"mouthFrownLeft": 1.0}, "MouthFrownRight": {"mouthFrownRight": 1.0},
    "MouthStretchLeft": {"mouthStretchLeft": 1.0}, "MouthStretchRight": {"mouthStretchRight": 1.0},
    "MouthDimpleLeft": {"mouthDimpleLeft": 1.0}, "MouthDimpleRight": {"mouthDimpleRight": 1.0},
    "MouthRaiserUpper": {"mouthShrugUpper": 1.0}, "MouthRaiserLower": {"mouthShrugLower": 1.0},
    "MouthPressLeft": {"mouthPressLeft": 1.0}, "MouthPressRight": {"mouthPressRight": 1.0},
    "MouthTightenerLeft": ({"mouthPucker": 0.4}, L), "MouthTightenerRight": ({"mouthPucker": 0.4}, R),
    "TongueOut": {"tongueOut": 1.0},

    # --- MMD: eyes ---
    "まばたき": _pair("eyeBlink"),
    "笑い": {"blend_Eye_niko_L": 1.0, "blend_Eye_niko_R": 1.0},
    "ウィンク": {"blend_Eye_niko_L": 1.0}, "ウィンク右": {"blend_Eye_niko_R": 1.0},
    "ウィンク２": {"eyeBlinkLeft": 1.0}, "ｳｨﾝｸ２右": {"eyeBlinkRight": 1.0},
    "なごみ": {"blend_Eye_suya_L": 1.0, "blend_Eye_suya_R": 1.0},
    "はぅ": {"blend_Eye_daisyo": 1.0},
    "びっくり": {**_pair("eyeWide"), "blend_Eye_small_L": 0.35, "blend_Eye_small_R": 0.35},
    "じと目": {"blend_Eye_zito_L": 1.0, "blend_Eye_zito_R": 1.0},
    "ｷﾘｯ": {**_pair("eyeSquint"), "eyeWideLeft": -0.25, "eyeWideRight": -0.25},
    "はちゅ目": {"blend_Eye_hide": 1.0, "blend_Eye_hidehigh": 1.0},
    "はぁと": {"blend_exeye_heart": 1.0}, "星目": {"blend_exeye_twinkle": 1.0},
    "瞳小": {"blend_Eye_small_L": 1.0, "blend_Eye_small_R": 1.0},
    "ハイライト消": {"blend_Eye_hidehigh": 1.0},
    # --- MMD: mouth ---
    "あ": {"vrc.v_aa": 1.0}, "い": {"vrc.v_ih": 1.0}, "う": {"vrc.v_ou": 1.0}, "え": {"vrc.v_e": 1.0}, "お": {"vrc.v_oh": 1.0},
    "あ２": {"blend_face_mouth_aaaaa": 1.0},
    "ん": {"mouthPressLeft": 0.7, "mouthPressRight": 0.7, "mouthShrugLower": 0.3},
    "▲": {"mouthFunnel": 0.7, "jawOpen": 0.25, "mouthFrownLeft": 0.5, "mouthFrownRight": 0.5},
    "∧": {"blend_face_mouth_mu": 1.0},
    "□": {"blend_mouth_open2": 1.0, "mouthStretchLeft": 0.4, "mouthStretchRight": 0.4},
    "ワ": {"blend_face_mouth_joy": 1.0, "jawOpen": 0.35},
    "ω": {"mouthSmileLeft": 0.6, "mouthSmileRight": 0.6, "mouthShrugUpper": 0.8, "mouthPucker": 0.3},
    "ω□": {"mouthSmileLeft": 0.6, "mouthSmileRight": 0.6, "mouthShrugUpper": 0.8, "mouthPucker": 0.3, "jawOpen": 0.4},
    "にやり": {"mouthSmileLeft": 1.0, "mouthDimpleLeft": 0.5, "mouthPressRight": 0.3},
    "にっこり": {"blend_face_mouth_niko": 1.0},
    "ぺろっ": {"blend_face_mouth_pero": 1.0},
    "てへぺろ": {"blend_face_mouth_pero": 1.0, "mouthLeft": 0.7, "mouthSmileLeft": 0.5},
    "口角上げ": {"mouthSmileLeft": 0.7, "mouthSmileRight": 0.7},
    "口角下げ": _pair("mouthFrown"),
    "口横広げ": _pair("mouthStretch"),
    # --- MMD: brows ---
    "真面目": {"blend_brow_down": 0.6, "blend_brow_in_L": 0.25, "blend_brow_in_R": 0.25},
    "困る": {"browInnerUp": 1.0, "browOuterUpLeft": -0.5, "browOuterUpRight": -0.5},
    "にこり": {"browOuterUpLeft": 0.5, "browOuterUpRight": 0.5, "browInnerUp": 0.3},
    "怒り": {"blend_brow_in_L": 1.0, "blend_brow_in_R": 1.0},
    "上": {"browInnerUp": 1.0, "browOuterUpLeft": 1.0, "browOuterUpRight": 1.0},
    "下": _pair("browDown"),
}

# Vertex classes, stored per face so the decals and the tile layout can find the eyes again.
SKIN, IRIS, HIGHLIGHT, OVERLAY = 0, 1, 2, 3
CLASS_ATTRIBUTE = "face_part"


def _islands(mesh):
    """Connected component id per vertex."""
    parent = np.arange(len(mesh.vertices))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for edge in mesh.edges:
        a, b = find(edge.vertices[0]), find(edge.vertices[1])
        if a != b:
            parent[b] = a
    return np.array([find(i) for i in range(len(parent))])


def _moved(mesh, name):
    blocks = mesh.shape_keys.key_blocks
    return np.linalg.norm(common.key_coords(blocks[name]) - common.key_coords(blocks["Basis"]), axis=1) > 1e-6


def _classify(mesh):
    """Per vertex: the class, and whether the vertex's island should be deleted."""
    island = _islands(mesh)
    overlay_material = np.zeros(len(mesh.vertices), dtype=bool)
    for polygon in mesh.polygons:
        if polygon.material_index == 1:
            overlay_material[list(polygon.vertices)] = True
    hide, hide_highlight = _moved(mesh, "blend_Eye_hide"), _moved(mesh, "blend_Eye_hidehigh")
    kept = np.zeros(len(mesh.vertices), dtype=bool)
    for key in KEPT_OVERLAYS.values():
        kept |= _moved(mesh, key)

    classes = np.zeros(len(mesh.vertices), dtype=np.int32)
    doomed = np.zeros(len(mesh.vertices), dtype=bool)
    for identifier in np.unique(island):
        members = island == identifier
        if len(np.flatnonzero(members)) > 2000:
            continue  # the head itself
        if overlay_material[members].all():
            if kept[members].mean() > 0.5:
                classes[members] = OVERLAY
            else:
                doomed[members] = True
        elif hide[members].mean() > 0.5:
            classes[members] = IRIS
        elif hide_highlight[members].mean() > 0.5:
            classes[members] = HIGHLIGHT
    return classes, doomed


def prepare(obj, source_armature, head_position, head_scale):
    """Moves the face onto the body's head joint, deletes unused overlays and tags the eye parts.

    Returns the positions of the source's eye pivots after the move.
    """
    mesh = obj.data
    pivot = source_armature.matrix_world @ source_armature.data.bones["Head"].head_local
    place = Matrix.Translation(Vector(head_position)) @ Matrix.Scale(head_scale, 4) @ Matrix.Translation(-pivot)
    mesh.transform(place @ obj.matrix_world, shape_keys=True)
    obj.matrix_world = Matrix.Identity(4)
    eyes = {side: place @ (source_armature.matrix_world @ source_armature.data.bones[f"Eye_{side}F"].head_local) for side in "LR"}

    _classes, doomed = _classify(mesh)
    bm = bmesh.new()
    bm.from_mesh(mesh)
    bm.verts.ensure_lookup_table()
    bmesh.ops.delete(bm, geom=[bm.verts[i] for i in np.flatnonzero(doomed)], context="VERTS")
    bm.to_mesh(mesh)
    bm.free()
    mesh.update()

    classes, _ = _classify(mesh)
    face_class = np.array([classes[polygon.vertices[0]] for polygon in mesh.polygons], dtype=np.int32)
    attribute = mesh.attributes.new(CLASS_ATTRIBUTE, "INT", "FACE")
    attribute.data.foreach_set("value", face_class)

    # The source splits the head between a Head and a Face bone (it rescales the face with
    # avatar height) and has a second pair of eye bones under Face. One of each is enough.
    table = common.weights_of(obj)
    merged = {"Neck": table["Neck"], "Head": table["Head"] + table["Face"], "Eye.L": table["Eye_LF"], "Eye.R": table["Eye_RF"]}
    common.set_weights(obj, merged)
    return eyes


def overlay_pairs(obj):
    """(shape, UV rect of the overlay, UV rect of the iris it sits on) for each kept eye overlay."""
    mesh = obj.data
    classes, _ = _classify(mesh)
    uv = common.get_uv(mesh, mesh.uv_layers[0].name)
    uv[:, 0] %= 1.0
    loop_vertex = np.empty(len(mesh.loops), dtype=np.int32)
    mesh.loops.foreach_get("vertex_index", loop_vertex)
    x = common.coords(mesh)[:, 0]

    def rect(vertices):
        chosen = uv[vertices[loop_vertex]]
        if not len(chosen):
            raise RuntimeError("an eye part of the face was not found; the source mesh has changed")
        return (chosen[:, 0].min(), chosen[:, 1].min(), chosen[:, 0].max(), chosen[:, 1].max())

    pairs = []
    for side in (x > 0, x < 0):
        iris = rect((classes == IRIS) & side)
        for shape, key in KEPT_OVERLAYS.items():
            pairs.append((shape, rect((classes == OVERLAY) & side & _moved(mesh, key)), iris))
    return pairs


def face_classes(mesh):
    values = np.empty(len(mesh.polygons), dtype=np.int32)
    mesh.attributes[CLASS_ATTRIBUTE].data.foreach_get("value", values)
    return values


def neck_opening(obj, below):
    """Vertex indices, centre and mean radius of the open loop at the bottom of the neck."""
    mesh = obj.data
    bm = bmesh.new()
    bm.from_mesh(mesh)
    loop = sorted({v.index for e in bm.edges if e.is_boundary for v in e.verts if v.co.z < below})
    bm.free()
    co = common.coords(mesh)[loop]
    centre = co.mean(axis=0)
    radius = np.linalg.norm(co[:, :2] - centre[:2], axis=1).mean()
    return loop, centre, radius


def narrow_neck(obj, loop, centre, radius, target, reach):
    """Draws the head's neck stub in to `target` radius.

    The source's neck is much thicker than the body's. The open loop moves
    all the way and stays round. Above it, a vertex follows by its weight to
    the neck bone, which already fades smoothly into the jaw, or by how close
    it is to the loop, whichever is more; the underside of the jaw stretches
    inwards instead of creasing.
    """
    mesh = obj.data
    blocks = mesh.shape_keys.key_blocks
    basis = common.key_coords(blocks["Basis"])
    by_weight = common.smoothstep(0.0, 0.7, common.weights_of(obj)["Neck"])
    to_loop = np.linalg.norm(basis[:, None, :] - basis[loop][None, :, :], axis=2).min(axis=1)
    amount = np.maximum(by_weight, 1.0 - common.smoothstep(0.0, reach, to_loop))
    offset = basis[:, :2] - np.array(centre[:2])
    delta = np.zeros_like(basis)
    delta[:, :2] = offset * ((target / radius) - 1.0) * amount[:, None]
    # The same offset goes on every key, so no expression sees the neck move.
    for block in blocks:
        common.set_key_coords(block, common.key_coords(block) + delta)
    common.set_coords(mesh, basis + delta)


def seal_neck(obj, loop, skin):
    """Sets the head's open neck loop down onto the body's neck, so nothing shows between them.

    The loop is slanted and not quite round, and the body's neck is neither
    straight nor centred under it, so matching radii alone leaves gaps to
    look through from below. Each loop vertex goes to the nearest point of
    the body's neck, a hair proud of it; the ring above follows half way.
    """
    mesh = obj.data
    source = common.SkinSource(skin)
    blocks = mesh.shape_keys.key_blocks
    basis = common.key_coords(blocks["Basis"])
    delta = np.zeros_like(basis)
    for index in loop:
        location, normal, _face, _distance = source.nearest(basis[index])
        outward = basis[index] - np.array(location)
        outward[2] = 0.0
        length = np.linalg.norm(outward)
        outward = outward / length if length > 1e-9 else np.array(normal)
        delta[index] = np.array(location) + outward * 0.0008 - basis[index]
    neighbours = {}
    members = set(loop)
    for edge in mesh.edges:
        a, b = edge.vertices
        for inner, outer in ((a, b), (b, a)):
            if inner in members and outer not in members:
                neighbours.setdefault(outer, []).append(inner)
    for vertex, ring in neighbours.items():
        delta[vertex] = 0.5 * np.mean([delta[i] for i in ring], axis=0)
    for block in blocks:
        common.set_key_coords(block, common.key_coords(block) + delta)
    common.set_coords(mesh, basis + delta)


def _lip_line(basis, deltas):
    """Height of the line between the lips: the top of what the jaw carries, near the front."""
    jaw = np.linalg.norm(deltas["jawOpen"], axis=1)
    carried = jaw > 0.6 * jaw.max()
    press = np.linalg.norm(deltas["vrc.v_pp"], axis=1)
    lips = press > 0.3 * press.max()
    both = carried & lips
    return basis[both if both.any() else carried][:, 2].max()


def rebuild_shape_keys(obj, wanted, blend_width):
    """Replaces the source's shape keys with the spec's names. Returns the names that have no recipe."""
    mesh = obj.data
    blocks = mesh.shape_keys.key_blocks
    basis = common.key_coords(blocks["Basis"])
    deltas = {block.name: common.key_coords(block) - basis for block in blocks[1:]}

    left = common.smoothstep(-blend_width, blend_width, basis[:, 0])
    lip = _lip_line(basis, deltas)
    upper = common.smoothstep(lip - blend_width * 0.5, lip + blend_width * 0.5, basis[:, 2])
    masks = {L: left, R: 1.0 - left, UP: upper, LO: 1.0 - upper}

    built, missing = {}, []
    for name in wanted:
        recipe = RECIPES.get(name)
        if recipe is None:
            missing.append(name)
            continue
        parts, regions = (recipe[0], recipe[1:]) if isinstance(recipe, tuple) else (recipe, ())
        delta = np.zeros_like(basis)
        for source, weight in parts.items():
            if source not in deltas:
                raise RuntimeError(f"recipe for {name!r} names a source shape the face does not have: {source!r}")
            delta += deltas[source] * weight
        for region in regions:
            delta *= masks[region][:, None]
        built[name] = delta

    obj.shape_key_clear()
    obj.shape_key_add(name="Basis", from_mix=False)
    for name, delta in built.items():
        block = obj.shape_key_add(name=name, from_mix=False)
        common.set_key_coords(block, basis + delta)
        block.value = 0.0
        if block.name != name:
            raise RuntimeError(f"Blender renamed shape key {name!r} to {block.name!r}")
    return missing


def add_key(obj, name, delta):
    """Adds or replaces one shape key given as offsets from the basis."""
    blocks = obj.data.shape_keys.key_blocks
    basis = common.key_coords(blocks["Basis"])
    block = blocks.get(name) or obj.shape_key_add(name=name, from_mix=False)
    common.set_key_coords(block, basis + delta)
    block.value = 0.0
