"""Checks the open .blend against the bot contract (blender/bot/README.md).

    blender -b --factory-startup blender/bot/bot.blend --python blender/bot/bot_validate.py

Exits non-zero on any error. Importable: `validate()` returns a Report for the open file, which
build_bot.py and export_bot.py both gate on. It checks what the contract says, not how the
generator happens to build the model.
"""

import sys
import pathlib

sys.dont_write_bytecode = True
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import math
import struct

import bpy
import numpy as np
from mathutils import Vector

import bot_face
import bot_spec

MOVE_EPSILON = 1e-6
LENGTH_TOLERANCE = 2e-5
WEIGHT_TOLERANCE = 1e-3
UV_TOLERANCE = 1e-5
POSE_TOLERANCE_DEG = 10.0
PLANAR_TOLERANCE = 1e-5


class Report:
    def __init__(self, title):
        self.title, self.errors, self.warnings, self.summary = title, [], [], []

    def error(self, message):
        self.errors.append(message)

    def warn(self, message):
        self.warnings.append(message)

    def note(self, message):
        self.summary.append(message)

    def print(self):
        print(f"== validate: {self.title} ==")
        for line in self.summary:
            print(f"  {line}")
        for label, items in (("ERROR", self.errors), ("WARNING", self.warnings)):
            for item in items:
                print(f"  {label}: {item}")
        print(f"== {'FAILED' if self.errors else 'OK'}: {len(self.errors)} error(s), {len(self.warnings)} warning(s) ==")


def _few(items, limit=6):
    items = list(items)
    return ", ".join(str(i) for i in items[:limit]) + (f", ... ({len(items)} in all)" if len(items) > limit else "")


def _is_identity(matrix, tolerance=1e-5):
    return all(abs(matrix[i][j] - (1.0 if i == j else 0.0)) <= tolerance for i in range(4) for j in range(4))


def triangle_count(mesh):
    return sum(polygon.loop_total - 2 for polygon in mesh.polygons)


def key_coordinates(block):
    data = np.empty(len(block.data) * 3, dtype=np.float32)
    block.data.foreach_get("co", data)
    return data.reshape(-1, 3).astype(np.float64)


def png_size(path):
    with open(path, "rb") as handle:
        header = handle.read(24)
    if header[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    return struct.unpack(">II", header[16:24])


def check_scene(report):
    collection = bpy.data.collections.get(bot_spec.EXPORT_COLLECTION)
    if collection is None:
        report.error(f"no collection named '{bot_spec.EXPORT_COLLECTION}'")
        return None, None
    objects = sorted(collection.all_objects, key=lambda o: o.name)
    names = [(o.name, o.type) for o in objects]
    if names != [(bot_spec.ARMATURE, "ARMATURE"), (bot_spec.MESH, "MESH"), (bot_spec.SHELL, "MESH")]:
        report.error(f"'{bot_spec.EXPORT_COLLECTION}' must hold exactly the armature '{bot_spec.ARMATURE}' and the meshes "
                     f"'{bot_spec.MESH}' and '{bot_spec.SHELL}', holds {names}")
        return None, None, None
    armature, body, shell = objects
    if bpy.context.scene.unit_settings.scale_length != 1.0:
        report.error("scene unit scale must be 1 (metres)")
    for obj in (armature, body, shell):
        if not _is_identity(obj.matrix_world) or not _is_identity(obj.matrix_basis):
            report.error(f"{obj.name}: transform is not applied (object must be at identity)")
    for mesh in (body, shell):
        if mesh.parent != armature or mesh.parent_type != "OBJECT":
            report.error(f"{mesh.name}: must be parented to '{armature.name}' (object parenting)")
        kinds = [m.type for m in mesh.modifiers]
        if kinds != ["ARMATURE"] or mesh.modifiers[0].object != armature:
            report.error(f"{mesh.name}: needs exactly one Armature modifier, on '{armature.name}', has {kinds or 'none'}")
    return armature, body, shell


def check_skeleton(report, armature):
    bones = armature.data.bones
    expected = bot_spec.expected_bones()
    missing = [name for name in expected if name not in bones]
    unknown = [bone.name for bone in bones if bone.name not in expected]
    if missing:
        report.error(f"armature lacks bones: {_few(missing)}")
    if unknown:
        report.error(f"armature has bones the contract does not list: {_few(unknown)}")
    for name, parent in expected.items():
        if name not in bones:
            continue
        actual = bones[name].parent.name if bones[name].parent else None
        if actual != parent:
            report.error(f"bone {name}: parent is {actual}, the contract requires {parent}")
        if not bones[name].use_deform:
            report.error(f"bone {name}: Deform is off, it would be dropped from the export")
    posed = [pb.name for pb in armature.pose.bones if not _is_identity(pb.matrix_basis)]
    if posed and armature.data.pose_position != "REST":
        report.error(f"armature is posed ({_few(posed)}); the export must be the rest T-pose")

    def direction(name):
        bone = bones.get(name)
        return (bone.tail_local - bone.head_local).normalized() if bone else None

    limit = math.cos(math.radians(POSE_TOLERANCE_DEG))
    for side, sign in ((".L", 1.0), (".R", -1.0)):
        for part, axis in (("UpperArm", Vector((sign, 0, 0))), ("LowerArm", Vector((sign, 0, 0))), ("Hand", Vector((sign, 0, 0))),
                           ("UpperLeg", Vector((0, 0, -1))), ("LowerLeg", Vector((0, 0, -1)))):
            d = direction(part + side)
            if d is not None and d.dot(axis) < limit:
                report.error(f"bone {part + side}: rest pose is not a T-pose (points {tuple(round(c, 2) for c in d)})")
    if "UpperArm.L" in bones and bones["UpperArm.L"].head_local.x <= 0.0:
        report.error("the left side must be +X (UpperArm.L is on -X)")
    if "Toes.L" in bones and "Foot.L" in bones and bones["Toes.L"].head_local.y >= bones["Foot.L"].head_local.y:
        report.error("the bot must face -Y (toes are not in front of the ankles)")
    report.note(f"Bones: {len(bones)} ({len(bot_spec.humanoid_bones())} humanoid, {len(bot_spec.EXTRA_BONES)} extra)")


def check_mesh(report, body, armature):
    """What both meshes owe: their material slots, faces, UV layers and weights. Returns the triangle count."""
    mesh = body.data
    wanted = list(bot_spec.MESH_MATERIALS[body.name])
    slots = [slot.material.name if slot.material else None for slot in body.material_slots]
    if slots != wanted:
        report.error(f"{body.name}: material slots must be {wanted} in that order, are {slots}")
    used = sorted({polygon.material_index for polygon in mesh.polygons})
    if used != list(range(len(wanted))):
        report.error(f"{body.name}: every material slot must have faces; used slots are {used}")

    # Faces: triangles, or flat convex quads.
    co = np.array([v.co[:] for v in mesh.vertices], dtype=np.float64)
    bad = []
    for polygon in mesh.polygons:
        if polygon.loop_total == 3:
            continue
        if polygon.loop_total != 4:
            bad.append(polygon.index)
            continue
        p = co[list(polygon.vertices)]
        normal = np.cross(p[1] - p[0], p[2] - p[0])
        length = np.linalg.norm(normal)
        if length < 1e-12:
            bad.append(polygon.index)
            continue
        normal /= length
        flat = abs(float((p[3] - p[0]) @ normal)) < PLANAR_TOLERANCE
        convex = all(float(np.cross(p[(i + 1) % 4] - p[i], p[(i + 2) % 4] - p[(i + 1) % 4]) @ normal) > 0.0 for i in range(4))
        if not (flat and convex):
            bad.append(polygon.index)
    if bad:
        report.error(f"{body.name}: {len(bad)} face(s) are neither triangles nor flat convex quads (faces {_few(bad)})")
    triangles = triangle_count(mesh)
    per_slot = [sum(p.loop_total - 2 for p in mesh.polygons if p.material_index == index) for index in range(len(body.material_slots))]
    report.note(f"{body.name}: {triangles} triangles, per slot {dict(zip(slots, per_slot))}; {len(mesh.vertices)} vertices")

    # UV layers.
    names = [layer.name for layer in mesh.uv_layers]
    if names != [bot_spec.UV_ATLAS, bot_spec.UV_TILE]:
        report.error(f"{body.name}: UV layers must be ['{bot_spec.UV_ATLAS}', '{bot_spec.UV_TILE}'] in that order, are {names}")
    else:
        def layer(name):
            data = np.empty(len(mesh.loops) * 2, dtype=np.float32)
            mesh.uv_layers[name].data.foreach_get("uv", data)
            return data.reshape(-1, 2).astype(np.float64)

        atlas = layer(bot_spec.UV_ATLAS)
        if ((atlas < -UV_TOLERANCE) | (atlas > 1.0 + UV_TOLERANCE)).any():
            report.error(f"{body.name}: '{bot_spec.UV_ATLAS}' leaves the 0..1 square")
        tile = layer(bot_spec.UV_TILE)
        if ((tile < 0.05) | (tile > 0.95)).any():
            report.error(f"{body.name}: '{bot_spec.UV_TILE}' must keep every corner inside the (0, 0) tile, clear of its borders")

    # Weights.
    deform = {bone.name for bone in armature.data.bones if bone.use_deform}
    is_bone = [group.name in deform for group in body.vertex_groups]
    unweighted, crowded, unnormalised = [], [], []
    for vertex in mesh.vertices:
        weights = [e.weight for e in vertex.groups if is_bone[e.group] and e.weight > 0.0]
        if not weights:
            unweighted.append(vertex.index)
        elif len(weights) > bot_spec.MAX_INFLUENCES:
            crowded.append(vertex.index)
        elif abs(sum(weights) - 1.0) > WEIGHT_TOLERANCE:
            unnormalised.append(vertex.index)
    for label, found in (("with no bone weight", unweighted), (f"with more than {bot_spec.MAX_INFLUENCES} influences", crowded),
                         ("whose weights do not sum to 1", unnormalised)):
        if found:
            report.error(f"{body.name}: {len(found)} vertex(es) {label} (vertices {_few(found)})")
    loose = [group.name for group, bone in zip(body.vertex_groups, is_bone) if not bone]
    if loose:
        report.error(f"{body.name}: vertex groups that match no bone: {_few(loose)}")
    return triangles


def check_shell(report, shell):
    """What only the shell owes: no shape keys, every finger bone followed, and the size of the bot."""
    mesh = shell.data
    if mesh.shape_keys is not None:
        report.error(f"{shell.name}: must have no shape keys (they belong on {bot_spec.MESH}); a mesh with any cannot take merged props")
    co = np.array([v.co[:] for v in mesh.vertices], dtype=np.float64)
    fingers = [f"{finger}{n}.{side}" for side in "LR" for finger in ("Thumb", "Index", "Middle", "Ring", "Little") for n in (1, 2, 3)]
    weighted = {shell.vertex_groups[e.group].name for v in mesh.vertices for e in v.groups if e.weight > 0.0}
    bare = [name for name in fingers if name not in weighted]
    if bare:
        report.error(f"{shell.name}: finger bones that nothing follows: {_few(bare)}")

    low, high = co[:, 2].min(), co[:, 2].max()
    solid = sorted({v for p in mesh.polygons if p.material_index == 0 for v in p.vertices})
    top = co[solid, 2].max() if solid else 0.0
    report.note(f"Height: feet at {low:.4f} m, top of the head at {top:.4f} m, tips of the ears at {high:.4f} m")
    if abs(low) > 1e-3:
        report.error(f"the lowest vertex is at Z={low:.4f}; the bot must stand on Z=0")
    if abs(top - bot_spec.HEIGHT) > 0.02:
        report.error(f"the top of the head is at {top:.3f} m, not about {bot_spec.HEIGHT} m")


def check_face(report, body):
    """Shape keys: the names of the contract, each moving only sprites, straight along the screen's depth."""
    mesh = body.data
    visemes, mmd = bot_spec.spec_shape_names()
    expected = bot_face.shape_keys(visemes, mmd)
    keys = mesh.shape_keys
    blocks = list(keys.key_blocks) if keys else []
    names = [block.name for block in blocks]
    report.note(f"Shape keys on {body.name}: {max(0, len(names) - 1)} (+ Basis)")
    if not blocks or blocks[0] != keys.reference_key or names[0] != "Basis":
        report.error(f"{body.name}: the first shape key must be the reference key, named 'Basis'")
        return
    wanted = [entry[0] for entry in expected]
    if names[1:] != wanted:
        missing = [name for name in wanted if name not in names]
        extra = [name for name in names[1:] if name not in wanted]
        report.error(f"{body.name}: shape keys differ from the contract; missing {_few(missing) or 'none'}, unexpected {_few(extra) or 'none'}"
                     + ("" if missing or extra else ", order differs"))
        return

    attribute = mesh.attributes.get(bot_spec.SPRITE_ATTRIBUTE)
    if attribute is None:
        report.error(f"{body.name}: no '{bot_spec.SPRITE_ATTRIBUTE}' attribute marking the sprite vertices")
        return
    sprite = np.array([item.value for item in attribute.data], dtype=bool)
    if not sprite.all():
        report.error(f"{body.name}: holds {int((~sprite).sum())} vertex(es) that are not sprites; everything else belongs on {bot_spec.SHELL}")
    followed = {body.vertex_groups[e.group].name for v in mesh.vertices for e in v.groups if e.weight > 0.0}
    if followed != {"Head"}:
        report.error(f"{body.name}: the face must follow the bone Head alone, follows {sorted(followed)}")
    try:
        face = bot_spec.load_face()
    except (OSError, ValueError) as error:
        report.error(f"cannot read {bot_spec.FACE_JSON}: {error}")
        return
    listed = {entry["name"]: entry for entry in face["shapeKeys"]}
    if list(listed) != wanted:
        report.error("face.json lists different shape keys than the contract tables in bot_face.py; rebuild")
        return
    plate = face["screen"]["plateBlender"][1]
    shown = {(layer, entry["name"]): entry["shownDepth"] for layer, entries in face["sprites"].items() for entry in entries}
    basis = key_coordinates(keys.reference_key)
    for block, (name, _group, layer, target) in zip(blocks[1:], expected):
        delta = key_coordinates(block) - basis
        moved = np.abs(delta).max(axis=1) > MOVE_EPSILON
        if not moved.any():
            report.error(f"shape key {name}: moves nothing")
            continue
        if (moved & ~sprite).any():
            report.error(f"shape key {name}: moves {int((moved & ~sprite).sum())} vertex(es) that are not sprites")
        if np.abs(delta[:, [0, 2]]).max() > MOVE_EPSILON:
            report.error(f"shape key {name}: moves vertices sideways; a sprite may only move along the screen's depth")
        if block.relative_key != keys.reference_key or block.value != 0.0:
            report.error(f"shape key {name}: must be relative to Basis and rest at 0")
        forward = moved & (delta[:, 1] < 0.0)
        if layer is None:
            if forward.any():
                report.error(f"shape key {name}: shows something, but the contract says it shows nothing")
            continue
        # The sprite the key brings forward must end exactly at its shown depth in front of the plate.
        if not forward.any():
            report.error(f"shape key {name}: brings nothing forward")
            continue
        depth = plate - (basis[forward, 1] + delta[forward, 1])
        want = shown[(layer, target)]
        if np.abs(depth - want).max() > LENGTH_TOLERANCE:
            report.error(f"shape key {name}: its sprite ends {depth.max():.5f} m in front of the plate, not {want:.5f}")
        if (plate - basis[forward, 1]).max() >= 0.0:
            report.error(f"shape key {name}: its sprite does not rest behind the backing plate")
        back = moved & (delta[:, 1] > 0.0)
        if layer != "overlay" and not back.any():
            report.error(f"shape key {name}: does not send the neutral {layer} sprite back")
        if back.any() and (plate - (basis[back, 1] + delta[back, 1])).max() >= 0.0:
            report.error(f"shape key {name}: the neutral sprite does not end behind the backing plate")


def check_textures(report):
    for path in (bot_spec.ATLAS_PNG, bot_spec.EMISSION_PNG):
        size = png_size(path) if path.exists() else None
        if size != (bot_spec.ATLAS_SIZE, bot_spec.ATLAS_SIZE):
            report.error(f"{path.name}: must be a {bot_spec.ATLAS_SIZE} x {bot_spec.ATLAS_SIZE} PNG, is {size or 'missing'}")
    report.note(f"Textures: {bot_spec.ATLAS_PNG.name}, {bot_spec.EMISSION_PNG.name}, {bot_spec.ATLAS_SIZE} x {bot_spec.ATLAS_SIZE}")


def validate():
    report = Report(bpy.data.filepath or "(unsaved scene)")
    armature, body, shell = check_scene(report)
    if armature is not None:
        check_skeleton(report, armature)
        triangles = check_mesh(report, body, armature) + check_mesh(report, shell, armature)
        report.note(f"Triangles: {triangles} in all (limit {bot_spec.MAX_TRIANGLES})")
        if triangles > bot_spec.MAX_TRIANGLES:
            report.error(f"{triangles} triangles exceed the limit of {bot_spec.MAX_TRIANGLES}")
        check_shell(report, shell)
        check_face(report, body)
    check_textures(report)
    return report


if __name__ == "__main__":
    result = validate()
    result.print()
    sys.exit(1 if result.errors else 0)
