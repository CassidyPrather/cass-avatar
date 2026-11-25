"""Checks the open .blend against the avatar contracts in Packages/net.wirenook.cass/Spec.

    blender -b --factory-startup blender/cass.blend --python blender/scripts/validate.py

Exits non-zero when any error is found. Also importable: `validate()` returns
a Report for the currently open file (export.py and build_cass.py both gate
on it). The checks only assume the contracts in blender/README.md, never how
the generator happens to build the model, so they hold for hand-made content
too.
"""

import sys
import pathlib

sys.dont_write_bytecode = True
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import math

import bpy
import numpy as np
from mathutils import Vector

import cass_spec

UV_TOLERANCE = 1e-4
# Tile UVs must sit clear of the cell edges so no filtering or precision loss can change the tile.
TILE_MARGIN = 0.05
WEIGHT_TOLERANCE = 1e-3
MOVE_EPSILON = 1e-6
POSE_TOLERANCE_DEG = 10.0


class Report:
    def __init__(self, title):
        self.title = title
        self.errors = []
        self.warnings = []
        self.summary = []

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
        verdict = "FAILED" if self.errors else "OK"
        print(f"== {verdict}: {len(self.errors)} error(s), {len(self.warnings)} warning(s) ==")


def _few(items, limit=6):
    items = list(items)
    shown = ", ".join(str(i) for i in items[:limit])
    return shown + (f", ... ({len(items)} in all)" if len(items) > limit else "")


def _is_identity(matrix, tolerance=1e-5):
    return all(abs(matrix[i][j] - (1.0 if i == j else 0.0)) <= tolerance for i in range(4) for j in range(4))


def triangle_count(mesh):
    return sum(polygon.loop_total - 2 for polygon in mesh.polygons)


def check_collection(report, skeleton, body_name):
    """Returns (armature, meshes) or (None, []) when the collection is unusable."""
    collection = bpy.data.collections.get(cass_spec.EXPORT_COLLECTION)
    if collection is None:
        report.error(f"no collection named '{cass_spec.EXPORT_COLLECTION}'")
        return None, []
    objects = list(collection.all_objects)
    armatures = [o for o in objects if o.type == "ARMATURE"]
    meshes = sorted((o for o in objects if o.type == "MESH"), key=lambda o: o.name)
    strays = [o.name for o in objects if o.type not in ("ARMATURE", "MESH")]
    if strays:
        report.error(f"'{cass_spec.EXPORT_COLLECTION}' holds objects that are neither armature nor mesh: {_few(strays)}")
    if len(armatures) != 1 or armatures[0].name != skeleton["armature"]:
        report.error(f"'{cass_spec.EXPORT_COLLECTION}' must hold exactly one armature named '{skeleton['armature']}', "
                     f"found: {_few(o.name for o in armatures) or 'none'}")
        return None, meshes
    armature = armatures[0]
    if body_name not in [m.name for m in meshes]:
        report.error(f"no mesh object named '{body_name}' (MMD worlds and the shape key contract need that exact name)")
    if bpy.context.scene.unit_settings.scale_length != 1.0:
        report.error(f"scene unit scale is {bpy.context.scene.unit_settings.scale_length}, must be 1 (metres)")

    for obj in [armature] + meshes:
        if not _is_identity(obj.matrix_world) or not _is_identity(obj.matrix_basis):
            report.error(f"{obj.name}: transform is not applied (object must be at identity)")
    for obj in meshes:
        if obj.parent != armature or obj.parent_type != "OBJECT":
            report.error(f"{obj.name}: must be parented to '{armature.name}' (object parenting)")
        kinds = [m.type for m in obj.modifiers]
        if kinds != ["ARMATURE"]:
            report.error(f"{obj.name}: needs exactly one Armature modifier and no others, has {kinds or 'none'}")
        elif obj.modifiers[0].object != armature:
            report.error(f"{obj.name}: Armature modifier does not target '{armature.name}'")
    return armature, meshes


def check_skeleton(report, skeleton, armature):
    bones = armature.data.bones
    humanoid = skeleton["humanoid"]
    expected_parent = {bone: cass_spec.humanoid_parent_bone(skeleton, name) for name, bone in humanoid.items()}
    expected_parent.update({entry["name"]: entry["parent"] for entry in skeleton["extra"]})

    for name in cass_spec.HUMANOID_REQUIRED:
        if name not in humanoid:
            report.error(f"skeleton.json maps no bone for required humanoid bone {name}")
    missing = [name for name in expected_parent if name not in bones]
    if missing:
        report.error(f"armature lacks bones from skeleton.json: {_few(missing)}")
    unknown = [bone.name for bone in bones if bone.name not in expected_parent]
    if unknown:
        report.error(f"armature has bones that skeleton.json does not list: {_few(unknown)}")
    for name, parent in expected_parent.items():
        if name not in bones:
            continue
        actual = bones[name].parent.name if bones[name].parent else None
        if actual != parent:
            report.error(f"bone {name}: parent is {actual}, skeleton.json requires {parent}")
        # Only deform bones are exported, so a non-deform contract bone would vanish from the FBX.
        if not bones[name].use_deform:
            report.error(f"bone {name}: Deform is off, it would be dropped from the export")
    if len(bones) > cass_spec.MAX_BONES:
        report.error(f"{len(bones)} bones exceed the limit of {cass_spec.MAX_BONES}")

    # Unity takes the exported pose as the T-pose reference, and the FBX carries the current pose.
    if armature.data.pose_position != "REST":
        posed = [pb.name for pb in armature.pose.bones if not _is_identity(pb.matrix_basis)]
        if posed:
            report.error(f"armature is posed ({_few(posed)}); clear the pose so the export is the rest T-pose")

    def direction(humanoid_name):
        bone = bones.get(humanoid.get(humanoid_name, ""))
        return (bone.tail_local - bone.head_local).normalized() if bone else None

    def head(humanoid_name):
        bone = bones.get(humanoid.get(humanoid_name, ""))
        return bone.head_local if bone else None

    limit = math.cos(math.radians(POSE_TOLERANCE_DEG))
    for prefix, sign in (("Left", 1.0), ("Right", -1.0)):
        for part, axis in (("UpperArm", Vector((sign, 0, 0))), ("LowerArm", Vector((sign, 0, 0))),
                           ("UpperLeg", Vector((0, 0, -1))), ("LowerLeg", Vector((0, 0, -1)))):
            d = direction(prefix + part)
            if d is not None and d.dot(axis) < limit:
                report.error(f"bone {humanoid[prefix + part]}: rest pose is not a T-pose (points {tuple(round(c, 2) for c in d)})")
    left, toes, foot = head("LeftUpperArm"), head("LeftToes"), head("LeftFoot")
    if left is not None and left.x <= 0.0:
        report.error("the character's left side must be +X (LeftUpperArm is on -X)")
    if toes is not None and foot is not None and toes.y >= foot.y:
        report.error("the character must face -Y (toes are not in front of the ankles)")
    report.note(f"Bones: {len(bones)} (limit {cass_spec.MAX_BONES})")


def _key_coordinates(block):
    data = np.empty(len(block.data) * 3, dtype=np.float32)
    block.data.foreach_get("co", data)
    return data.reshape(-1, 3)


def check_shape_keys(report, blendshapes, body, tile_ids):
    keys = body.data.shape_keys
    blocks = list(keys.key_blocks) if keys else []
    names = [block.name for block in blocks]
    report.note(f"Shape keys on {body.name}: {max(0, len(names) - 1)} (+ basis)")
    if not blocks:
        report.error(f"{body.name} has no shape keys")
        return
    if blocks[0] != keys.reference_key or names[0] != "Basis":
        report.error(f"{body.name}: the first shape key must be the reference key and be named 'Basis' (is '{names[0]}')")
    present = set(names[1:])
    missing = [name for name in blendshapes["required"] if name not in present]
    if missing:
        report.error(f"{body.name} lacks required shape keys: {_few(missing)}")
    optional = [name for name in blendshapes["optional"] if name not in present]
    if optional:
        report.warn(f"{body.name} lacks extended face-tracking keys: {_few(optional)}")
    known = set(blendshapes["all"])
    extra = [name for name in names[1:] if name not in known]
    if extra:
        report.warn(f"{body.name} has shape keys that blendshapes.json does not list: {_few(extra)}")

    # Vertices of the clothed skin zones; face keys have no business moving them.
    zone_vertices = np.zeros(len(body.data.vertices), dtype=bool)
    if tile_ids is not None:
        for polygon, tile in zip(body.data.polygons, tile_ids):
            if tile is not None and tile.startswith("body."):
                zone_vertices[list(polygon.vertices)] = True

    basis = _key_coordinates(keys.reference_key)
    empty, stray, relative, active = [], [], [], []
    for block in blocks[1:]:
        moved = np.abs(_key_coordinates(block) - basis).max(axis=1) > MOVE_EPSILON
        if not moved.any():
            empty.append(block.name)
        elif (moved & zone_vertices).any():
            stray.append(block.name)
        if block.relative_key != keys.reference_key:
            relative.append(block.name)
        if block.value != 0.0:
            active.append(block.name)
    if empty:
        report.error(f"shape keys that move nothing: {_few(empty)}")
    if stray:
        report.warn(f"shape keys that move vertices of body.* skin zones: {_few(stray)}")
    if relative:
        report.warn(f"shape keys not relative to Basis: {_few(relative)}")
    if active:
        report.warn(f"shape keys left at a non-zero value (the FBX would carry it): {_few(active)}")


def check_uvs(report, obj, tiles):
    """Checks both UV layers; returns the tile id of each polygon (None where invalid), or None."""
    mesh = obj.data
    names = [layer.name for layer in mesh.uv_layers]
    if names != [cass_spec.UV_PALETTE, cass_spec.UV_TILE]:
        report.error(f"{obj.name}: UV layers must be exactly ['{cass_spec.UV_PALETTE}', '{cass_spec.UV_TILE}'] in that order, are {names}")
        return None
    if not mesh.polygons:
        report.error(f"{obj.name}: mesh has no faces")
        return None

    starts = np.empty(len(mesh.polygons), dtype=np.int32)
    totals = np.empty(len(mesh.polygons), dtype=np.int32)
    mesh.polygons.foreach_get("loop_start", starts)
    mesh.polygons.foreach_get("loop_total", totals)
    polygon_of_loop = np.repeat(np.arange(len(mesh.polygons)), totals)

    def layer_uv(name):
        data = np.empty(len(mesh.loops) * 2, dtype=np.float32)
        mesh.uv_layers[name].data.foreach_get("uv", data)
        return data.reshape(-1, 2).astype(np.float64)

    # Colour comes from the atlas: flat faces sit on a swatch, painted ones span their artwork.
    # Either way the texture is not tiled, so nothing may leave the unit square.
    colour_uv = layer_uv(cass_spec.UV_PALETTE)
    outside = ((colour_uv < -UV_TOLERANCE) | (colour_uv > 1.0 + UV_TOLERANCE)).any(axis=1)
    bad = np.unique(polygon_of_loop[outside])
    if bad.size:
        report.error(f"{obj.name}: {bad.size} face(s) whose '{cass_spec.UV_PALETTE}' loops leave the 0..1 square (faces {_few(bad)})")

    tile_uv = layer_uv(cass_spec.UV_TILE)
    cell = np.floor(tile_uv)
    inside = tile_uv - cell
    loop_ok = ((inside > TILE_MARGIN) & (inside < 1.0 - TILE_MARGIN)).all(axis=1)
    loop_ok &= (cell == cell[starts][polygon_of_loop]).all(axis=1)
    polygon_ok = np.ones(len(mesh.polygons), dtype=bool)
    np.logical_and.at(polygon_ok, polygon_of_loop, loop_ok)
    by_cell = {(tile["column"], tile["row"]): tile["id"] for tile in tiles["tiles"]}
    ids = []
    for index, (column, row) in enumerate(cell[starts].astype(int)):
        tile = by_cell.get((column, row)) if polygon_ok[index] else None
        polygon_ok[index] = tile is not None
        ids.append(tile)
    bad = np.flatnonzero(~polygon_ok)
    if bad.size:
        report.error(f"{obj.name}: {bad.size} face(s) whose '{cass_spec.UV_TILE}' loops are not inside one valid tile, clear of its "
                     f"borders (faces {_few(bad)})")
    return ids


def check_weights(report, obj, armature):
    bones = {bone.name for bone in armature.data.bones if bone.use_deform}
    is_bone = [group.name in bones for group in obj.vertex_groups]
    unweighted, crowded, unnormalised = [], [], []
    for vertex in obj.data.vertices:
        weights = [element.weight for element in vertex.groups if is_bone[element.group] and element.weight > 0.0]
        if not weights:
            unweighted.append(vertex.index)
        elif len(weights) > cass_spec.MAX_INFLUENCES:
            crowded.append(vertex.index)
        elif abs(sum(weights) - 1.0) > WEIGHT_TOLERANCE:
            unnormalised.append(vertex.index)
    if unweighted:
        report.error(f"{obj.name}: {len(unweighted)} vertex(es) with no bone weight (vertices {_few(unweighted)})")
    if crowded:
        report.error(f"{obj.name}: {len(crowded)} vertex(es) with more than {cass_spec.MAX_INFLUENCES} bone influences "
                     f"(vertices {_few(crowded)})")
    if unnormalised:
        report.error(f"{obj.name}: {len(unnormalised)} vertex(es) whose weights do not sum to 1 (vertices {_few(unnormalised)})")
    loose = [group.name for group, bone in zip(obj.vertex_groups, is_bone) if not bone]
    if loose:
        report.warn(f"{obj.name}: vertex groups that match no deform bone are ignored by the export: {_few(loose)}")


def check_materials(report, meshes):
    materials = set()
    for obj in meshes:
        slots = obj.material_slots
        if len(slots) != 1 or slots[0].material is None:
            report.error(f"{obj.name}: needs exactly one material slot with a material, has {len(slots)}")
            continue
        materials.add(slots[0].material)
    if len(materials) > 1:
        report.error(f"meshes use different materials: {_few(sorted(m.name for m in materials))}")
    elif materials and next(iter(materials)).name != cass_spec.MATERIAL_NAME:
        report.error(f"the shared material must be named '{cass_spec.MATERIAL_NAME}', is '{next(iter(materials)).name}'")


def check_budget(report, meshes, tiles, tile_ids):
    level = bpy.context.scene.get(cass_spec.LEVEL_PROP, "full")
    limit = cass_spec.LEVELS[level]["max_triangles"]
    hidden_limit = cass_spec.LEVELS[level].get("max_hidden_triangles")
    counts = {obj.name: triangle_count(obj.data) for obj in meshes}
    total = sum(counts.values())
    # Triangles on tiles that are hidden at rest: the alternatives to what is worn by default.
    # Where those are budgeted apart it is for the mobile build, which also leaves out the
    # tiles marked as too much for it.
    hidden_tiles = {tile["id"] for tile in tiles["tiles"]
                    if not tile["shown"] or (hidden_limit is not None and not tile.get("mobile", True))}
    hidden = {}
    for obj in meshes:
        ids = tile_ids.get(obj.name)
        if ids is None:
            continue
        hidden[obj.name] = sum(polygon.loop_total - 2 for polygon, tile in zip(obj.data.polygons, ids) if tile in hidden_tiles)
    resting = sum(hidden.values())
    shown = total - resting
    if hidden_limit is None:
        report.note(f"Triangles: {total} (limit {limit} for the {level} level), {resting} of them on tiles hidden at rest")
    else:
        report.note(f"Triangles: {shown} shown at rest (limit {limit} for the {level} level), "
                    f"{resting} on tiles hidden at rest (limit {hidden_limit}), {total} in all")
    for name, count in counts.items():
        report.note(f"  {name}: {count}" + (f" ({hidden[name]} hidden at rest)" if hidden.get(name) else ""))
    if hidden_limit is None:
        if total > limit:
            report.error(f"{total} triangles exceed the limit of {limit}")
    else:
        if shown > limit:
            report.error(f"{shown} triangles shown at rest exceed the limit of {limit}")
        if resting > hidden_limit:
            report.error(f"{resting} triangles on tiles hidden at rest exceed the limit of {hidden_limit}")
    lowest = min((v.co.z for obj in meshes for v in obj.data.vertices), default=0.0)
    if abs(lowest) > 0.01:
        report.warn(f"the lowest vertex is at Z={lowest:.3f}; the character should stand on Z=0")


def validate():
    """Validates the open file and returns a Report."""
    report = Report(bpy.data.filepath or "(unsaved scene)")
    skeleton = cass_spec.load_skeleton()
    blendshapes = cass_spec.load_blendshapes()
    tiles = cass_spec.load_tiles()

    armature, meshes = check_collection(report, skeleton, blendshapes["mesh"])
    report.note("Objects: " + ", ".join([armature.name] if armature else []) + "".join(f", {m.name}" for m in meshes))
    if armature is not None:
        check_skeleton(report, skeleton, armature)
    tile_ids = {}
    for obj in meshes:
        tile_ids[obj.name] = check_uvs(report, obj, tiles)
        if armature is not None:
            check_weights(report, obj, armature)
    body = next((m for m in meshes if m.name == blendshapes["mesh"]), None)
    if body is not None:
        check_shape_keys(report, blendshapes, body, tile_ids[body.name])
    check_materials(report, meshes)
    if meshes:
        check_budget(report, meshes, tiles, tile_ids)
    return report


if __name__ == "__main__":
    result = validate()
    result.print()
    sys.exit(1 if result.errors else 0)
