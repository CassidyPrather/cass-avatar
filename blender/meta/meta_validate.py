"""Checks the open .blend against the meta contract (blender/meta/README.md).

    blender -b --factory-startup blender/meta/meta.blend --python blender/meta/meta_validate.py

Exits non-zero on any error. Importable: `validate()` returns a Report for the open file, which
build_meta.py and export_meta.py both gate on.
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

import meta_spec

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


def png_size(path):
    with open(path, "rb") as handle:
        header = handle.read(24)
    if header[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    return struct.unpack(">II", header[16:24])


def check_scene(report):
    collection = bpy.data.collections.get(meta_spec.EXPORT_COLLECTION)
    if collection is None:
        report.error(f"no collection named '{meta_spec.EXPORT_COLLECTION}'")
        return None, None
    objects = sorted(collection.all_objects, key=lambda o: o.name)
    names = [(o.name, o.type) for o in objects]
    if names != [(meta_spec.ARMATURE, "ARMATURE"), (meta_spec.MESH, "MESH")]:
        report.error(f"'{meta_spec.EXPORT_COLLECTION}' must hold exactly the armature '{meta_spec.ARMATURE}' and the mesh "
                     f"'{meta_spec.MESH}', holds {names}")
        return None, None
    armature, body = objects
    if bpy.context.scene.unit_settings.scale_length != 1.0:
        report.error("scene unit scale must be 1 (metres)")
    for obj in (armature, body):
        if not _is_identity(obj.matrix_world) or not _is_identity(obj.matrix_basis):
            report.error(f"{obj.name}: transform is not applied (object must be at identity)")
    if body.parent != armature or body.parent_type != "OBJECT":
        report.error(f"{body.name}: must be parented to '{armature.name}' (object parenting)")
    kinds = [m.type for m in body.modifiers]
    if kinds != ["ARMATURE"] or body.modifiers[0].object != armature:
        report.error(f"{body.name}: needs exactly one Armature modifier, on '{armature.name}', has {kinds or 'none'}")
    return armature, body


def check_skeleton(report, armature):
    bones = armature.data.bones
    expected = meta_spec.expected_bones()
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
    if len(bones) > meta_spec.MAX_BONES:
        report.error(f"{len(bones)} bones exceed the limit of {meta_spec.MAX_BONES}")

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
        report.error("the figure must face -Y (toes are not in front of the ankles)")
    # The seen head is the twin of the humanoid one: same place, same parent.
    head, visual = bones.get("Head"), bones.get(meta_spec.HEAD_VISUAL)
    if head is not None and visual is not None:
        if (head.head_local - visual.head_local).length > 1e-6 or (head.tail_local - visual.tail_local).length > 1e-6:
            report.error(f"{meta_spec.HEAD_VISUAL} must rest exactly where Head does")
        if head.children:
            report.error(f"Head must have no children ({_few(c.name for c in head.children)}): it is moved away on purpose")
    extra = len(meta_spec.EXTRA_BONES)
    report.note(f"Bones: {len(bones)} ({len(meta_spec.HUMANOID)} humanoid, {extra} extra; limit {meta_spec.MAX_BONES})")


def check_mesh(report, body, armature):
    mesh = body.data
    slots = [slot.material.name if slot.material else None for slot in body.material_slots]
    if slots != [meta_spec.MATERIAL]:
        report.error(f"{body.name}: must have the one material slot '{meta_spec.MATERIAL}', has {slots}")
    if mesh.shape_keys is not None:
        report.error(f"{body.name}: must have no shape keys")

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
    report.note(f"{body.name}: {triangles} triangles (limit {meta_spec.MAX_TRIANGLES}), {len(mesh.vertices)} vertices")
    if triangles > meta_spec.MAX_TRIANGLES:
        report.error(f"{triangles} triangles exceed the limit of {meta_spec.MAX_TRIANGLES}")

    names = [layer.name for layer in mesh.uv_layers]
    if names != [meta_spec.UV_ATLAS, meta_spec.UV_TILE]:
        report.error(f"{body.name}: UV layers must be ['{meta_spec.UV_ATLAS}', '{meta_spec.UV_TILE}'] in that order, are {names}")
    else:
        def layer(name):
            data = np.empty(len(mesh.loops) * 2, dtype=np.float32)
            mesh.uv_layers[name].data.foreach_get("uv", data)
            return data.reshape(-1, 2).astype(np.float64)

        atlas = layer(meta_spec.UV_ATLAS)
        if ((atlas < -UV_TOLERANCE) | (atlas > 1.0 + UV_TOLERANCE)).any():
            report.error(f"{body.name}: '{meta_spec.UV_ATLAS}' leaves the 0..1 square")
        tile = layer(meta_spec.UV_TILE)
        if ((tile < 0.05) | (tile > 0.95)).any():
            report.error(f"{body.name}: '{meta_spec.UV_TILE}' must keep every corner inside the (0, 0) tile, clear of its borders")

    deform = {bone.name for bone in armature.data.bones if bone.use_deform}
    is_bone = [group.name in deform for group in body.vertex_groups]
    unweighted, crowded, unnormalised = [], [], []
    for vertex in mesh.vertices:
        weights = [e.weight for e in vertex.groups if is_bone[e.group] and e.weight > 0.0]
        if not weights:
            unweighted.append(vertex.index)
        elif len(weights) > meta_spec.MAX_INFLUENCES:
            crowded.append(vertex.index)
        elif abs(sum(weights) - 1.0) > WEIGHT_TOLERANCE:
            unnormalised.append(vertex.index)
    for label, found in (("with no bone weight", unweighted), (f"with more than {meta_spec.MAX_INFLUENCES} influences", crowded),
                         ("whose weights do not sum to 1", unnormalised)):
        if found:
            report.error(f"{body.name}: {len(found)} vertex(es) {label} (vertices {_few(found)})")
    loose = [group.name for group, bone in zip(body.vertex_groups, is_bone) if not bone]
    if loose:
        report.error(f"{body.name}: vertex groups that match no bone: {_few(loose)}")

    weighted = {body.vertex_groups[e.group].name for v in mesh.vertices for e in v.groups if e.weight > 0.0}
    if "Head" in weighted:
        report.error(f"{body.name}: something is weighted to Head; everything of the head belongs on {meta_spec.HEAD_VISUAL}")
    if meta_spec.HEAD_VISUAL not in weighted:
        report.error(f"{body.name}: nothing is weighted to {meta_spec.HEAD_VISUAL}")
    fingers = [f"{finger}{n}.{side}" for side in "LR" for finger in ("Thumb", "Index", "Middle", "Ring", "Little") for n in (1, 2, 3)]
    bare = [name for name in fingers if name not in weighted]
    if bare:
        report.error(f"{body.name}: finger bones that nothing follows: {_few(bare)}")
    idle = [name for name, _parent, role in meta_spec.EXTRA_BONES if "visual" not in role and name not in weighted]
    if idle:
        report.error(f"{body.name}: sway bones that nothing follows: {_few(idle)}")

    low, high = co[:, 2].min(), co[:, 2].max()
    report.note(f"Height: soles at {low:.4f} m, top of the hood at {high:.4f} m")
    if abs(low) > 1e-3:
        report.error(f"the lowest vertex is at Z={low:.4f}; the figure must stand on Z=0")
    if abs(high - meta_spec.HEIGHT) > 0.03:
        report.error(f"the top of the hood is at {high:.3f} m, not about {meta_spec.HEIGHT} m")
    lopsided = abs(co[:, 0].max() + co[:, 0].min())
    if lopsided > 0.08:
        report.error(f"the figure is not centred on X=0 (off by {lopsided:.3f} m)")


def check_textures(report):
    for path in (meta_spec.ATLAS_PNG, meta_spec.EMISSION_PNG, meta_spec.TINT_PNG):
        size = png_size(path) if path.exists() else None
        if size != (meta_spec.ATLAS_SIZE, meta_spec.ATLAS_SIZE):
            report.error(f"{path.name}: must be a {meta_spec.ATLAS_SIZE} x {meta_spec.ATLAS_SIZE} PNG, is {size or 'missing'}")
    report.note(f"Textures: {meta_spec.ATLAS_PNG.name}, {meta_spec.EMISSION_PNG.name}, {meta_spec.TINT_PNG.name}, "
                f"{meta_spec.ATLAS_SIZE} x {meta_spec.ATLAS_SIZE}")


def validate():
    report = Report(bpy.data.filepath or "(unsaved scene)")
    armature, body = check_scene(report)
    if armature is not None:
        check_skeleton(report, armature)
        check_mesh(report, body, armature)
    check_textures(report)
    return report


if __name__ == "__main__":
    result = validate()
    result.print()
    sys.exit(1 if result.errors else 0)
