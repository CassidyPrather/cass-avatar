"""Validates a .blend and exports its `Export` collection as the FBX Unity imports.

    blender -b --factory-startup --python blender/scripts/export.py -- [--blend PATH] [--output PATH]

Defaults: blender/cass.blend -> Packages/net.wirenook.cass/BlenderExports/cass.fbx.
The export is refused when validate.py reports an error. Afterwards the FBX is
checked twice against the source scene: once as stored (node transforms, bind
matrices and vertices parsed straight from the file, which is how Unity reads
it) and once through Blender's importer. Any difference is an error. The
.blend is never saved.
"""

import sys
import pathlib

sys.dont_write_bytecode = True
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import argparse
import math

import bpy
import numpy as np
from mathutils import Euler, Matrix

import cass_spec
import validate

# Unity 2022.3 / VRChat settings. Each line is here for a reason:
FBX_SETTINGS = dict(
    object_types={"ARMATURE", "MESH"},
    # Blender is Z-up/-Y-forward, Unity Y-up/Z-forward. The exporter's own
    # "apply transform" option skips armatures, so `bake_axis_conversion` below
    # does the baking and this only declares the target axes.
    axis_forward="-Z",
    axis_up="Y",
    bake_space_transform=False,
    # Metres are declared in the file's unit scale instead of scaling every
    # object by 100, so Unity's imported transforms keep scale 1.
    global_scale=1.0,
    apply_unit_scale=True,
    apply_scale_options="FBX_SCALE_ALL",
    # Applying modifiers would bake the mesh and drop its shape keys; the only
    # modifier allowed on export meshes is Armature, which FBX carries as skin.
    use_mesh_modifiers=False,
    # Flat shading is exported as split normals; no smoothing groups needed.
    mesh_smooth_type="OFF",
    use_tspace=False,
    # Only real, weighted bones: no `_end` leaf bones, no helper bones. Extra
    # bones would count against VRChat's limits and confuse humanoid mapping.
    add_leaf_bones=False,
    use_armature_deform_only=True,
    primary_bone_axis="Y",
    secondary_bone_axis="X",
    armature_nodetype="NULL",
    # The rest pose is the T-pose Unity needs; no animation is shipped.
    bake_anim=False,
    # Unity assigns its own material; the palette lives beside the FBX in the package.
    path_mode="AUTO",
    embed_textures=False,
    use_custom_props=False,
)

SCALE_TOLERANCE = 1e-4
LENGTH_TOLERANCE = 1e-3


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    parser = argparse.ArgumentParser(prog="export.py", description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("--blend", help="the .blend to export (default: the open file, else blender/cass.blend)")
    parser.add_argument("--output", default=str(cass_spec.FBX_PATH))
    return parser.parse_args(argv)


def _bounds(points):
    points = np.asarray(points, dtype=np.float64)
    return points.min(axis=0), points.max(axis=0)


def _bounds_differ(got, want):
    return max(np.abs(got[0] - want[0]).max(), np.abs(got[1] - want[1]).max()) > LENGTH_TOLERANCE


def summarise(objects):
    """What must survive the export, read from Blender objects in world space."""
    summary = {"armatures": {}, "meshes": {}}
    for obj in objects:
        if obj.type == "ARMATURE":
            summary["armatures"][obj.name] = {
                "parents": {bone.name: (bone.parent.name if bone.parent else None) for bone in obj.data.bones},
                # Posed heads, not rest heads: the FBX carries the pose, and Unity reads the pose.
                "heads": {pb.name: np.array(obj.matrix_world @ pb.head) for pb in obj.pose.bones},
            }
        elif obj.type == "MESH":
            mesh = obj.data
            keys = {}
            if mesh.shape_keys:
                basis = np.empty(len(mesh.vertices) * 3, dtype=np.float32)
                mesh.shape_keys.reference_key.data.foreach_get("co", basis)
                scale = obj.matrix_world.to_scale().x
                for block in mesh.shape_keys.key_blocks[1:]:
                    co = np.empty(len(mesh.vertices) * 3, dtype=np.float32)
                    block.data.foreach_get("co", co)
                    keys[block.name] = float(np.abs(co - basis).max()) * scale
            summary["meshes"][obj.name] = {
                "triangles": validate.triangle_count(mesh),
                "uv_layers": [layer.name for layer in mesh.uv_layers],
                "shape_keys": keys,
                # Only groups that weight something: FBX has no notion of an empty group.
                "groups": sorted({obj.vertex_groups[e.group].name for v in mesh.vertices for e in v.groups if e.weight > 0.0}),
                "scale": tuple(obj.matrix_world.to_scale()),
                "bounds": _bounds([obj.matrix_world @ v.co for v in mesh.vertices]),
            }
    return summary


def bake_axis_conversion(objects):
    """Moves the Z-up to Y-up conversion out of the object transforms and into the data.

    Blender's exporter converts axes by rotating each root object -90 degrees
    about X, which Unity shows as a rotated `Armature` under the model root.
    Rotating the data by that amount and the armature object the opposite way
    leaves the scene unchanged but makes the exported node transforms identity.
    Works on the open scene in memory; the caller must not save the file.
    """
    to_y_up = Matrix.Rotation(-math.pi / 2.0, 4, "X")
    for data in {obj.data for obj in objects}:
        if isinstance(data, bpy.types.Mesh):
            data.transform(to_y_up, shape_keys=True)
        else:
            data.transform(to_y_up)
    armatures = [obj for obj in objects if obj.type == "ARMATURE"]
    for obj in armatures:
        # Meshes are children of the armature at identity, so they follow it.
        obj.matrix_world = to_y_up.inverted()
        # The exporter writes each bone node from its POSE matrix. Rotating the
        # rest bones does not refresh the pose by itself; without this the mesh
        # and bind pose are exported Y-up while the bone nodes stay Z-up, and
        # Unity (which reads the nodes) gets the character lying on its back.
        obj.data.update_tag()
        obj.update_tag(refresh={"OBJECT", "DATA"})
    bpy.context.view_layer.update()
    for obj in armatures:
        stale = [pb.name for pb in obj.pose.bones
                 if max(abs(a - b) for row_a, row_b in zip(pb.matrix, pb.bone.matrix_local) for a, b in zip(row_a, row_b)) > 1e-5]
        if stale:
            raise RuntimeError(f"export: the pose of {obj.name} did not follow the axis conversion ({stale[:4]} ...)")


def read_fbx(path):
    """The FBX as Unity reads it: node hierarchy with local transforms, mesh vertices, skin bind matrices.

    Returns (settings, models). `models` maps node id to a dict with name,
    kind, parent id (0 for the root), props, world matrix, and where present
    the mesh vertices and the skin's bind matrix, all in the file's own axes
    and units.
    """
    from io_scene_fbx import parse_fbx

    root, _version = parse_fbx.parse(str(path))

    def child(element, name):
        return next((e for e in element.elems if e.id == name), None)

    def properties(element):
        block = child(element, b"Properties70")
        return {p.props[0].decode(): tuple(p.props[4:]) for p in block.elems} if block else {}

    settings = properties(child(root, b"GlobalSettings"))
    models, geometry, clusters = {}, {}, {}
    for element in child(root, b"Objects").elems:
        uid = element.props[0]
        if element.id == b"Model":
            models[uid] = {"name": element.props[1].split(b"\x00")[0].decode(), "kind": element.props[2].decode(),
                           "props": properties(element), "parent": 0}
        elif element.id == b"Geometry" and element.props[2] == b"Mesh":
            geometry[uid] = np.array(child(element, b"Vertices").props[0], dtype=np.float64).reshape(-1, 3)
        elif element.id == b"Deformer" and element.props[2] == b"Cluster":
            # FBX stores matrices column-major.
            clusters[uid] = np.array(child(element, b"TransformLink").props[0], dtype=np.float64).reshape(4, 4).T
    for connection in child(root, b"Connections").elems:
        if connection.props[0] != b"OO":
            continue
        source, target = connection.props[1], connection.props[2]
        if source in models and target in models:
            models[source]["parent"] = target
        elif source in geometry and target in models:
            models[target]["vertices"] = geometry[source]
        elif source in models and target in clusters:
            models[source]["bind"] = clusters[target]

    def local(props):
        def rotation(key):
            return Euler([math.radians(angle) for angle in props.get(key, (0.0, 0.0, 0.0))], "XYZ").to_matrix().to_4x4()

        scaling = Matrix.Diagonal((*props.get("Lcl Scaling", (1.0, 1.0, 1.0)), 1.0))
        return Matrix.Translation(props.get("Lcl Translation", (0.0, 0.0, 0.0))) @ rotation("PreRotation") @ rotation("Lcl Rotation") @ scaling

    def world(uid):
        model = models[uid]
        if "world" not in model:
            parent = world(model["parent"]) if model["parent"] else Matrix.Identity(4)
            model["world"] = np.array(parent @ local(model["props"]))
        return Matrix(model["world"].tolist())

    for uid in models:
        world(uid)
    return settings, models


def verify_file(path, expected):
    """Checks the stored FBX data the way Unity will read it, without Blender's importer.

    Unity places bones from the node hierarchy's local transforms and expects
    Y-up data when the header says Y-up. Blender's importer would hide a
    mistake here (it rebuilds bones from the skin's bind matrices), so the
    node transforms, the bind matrices and the vertices are each compared with
    the source scene after mapping FBX (x, y, z) to Blender (x, -z, y).
    """
    problems = []
    settings, models = read_fbx(path)
    axes = {name: settings[name][0] for name in ("UpAxis", "UpAxisSign", "FrontAxis", "FrontAxisSign", "CoordAxis", "CoordAxisSign")}
    metres = settings["UnitScaleFactor"][0] / 100.0
    print(f"  axes {axes}, UnitScaleFactor {settings['UnitScaleFactor'][0]}")
    if axes != {"UpAxis": 1, "UpAxisSign": 1, "FrontAxis": 2, "FrontAxisSign": 1, "CoordAxis": 0, "CoordAxisSign": 1}:
        problems.append(f"FBX axis system is not Y-up/Z-front: {axes}")

    def to_blender(points):
        points = np.atleast_2d(points)
        return np.stack([points[:, 0], -points[:, 2], points[:, 1]], axis=1) * metres

    def triple(props, key, default=0.0):
        return props.get(key, (default,) * 3)

    heads = {name: head for armature in expected["armatures"].values() for name, head in armature["heads"].items()}
    hips = cass_spec.load_skeleton()["humanoid"]["Hips"]
    worst_head = worst_bind = 0.0
    bones = 0
    for model in sorted(models.values(), key=lambda m: m["name"]):
        props, name, matrix = model["props"], model["name"], model["world"]
        if model["kind"] == "LimbNode":
            bones += 1
            if name in heads:
                worst_head = max(worst_head, float(np.abs(to_blender(matrix[:3, 3])[0] - heads[name]).max()))
            if "bind" in model:
                difference = np.abs(model["bind"] - matrix)
                worst_bind = max(worst_bind, float(difference[:3, :3].max()), float(difference[:3, 3].max()) * metres)
            if name == hips:
                print(f"  bone {name}: Lcl Translation {tuple(round(v, 4) for v in triple(props, 'Lcl Translation'))}, "
                      f"Lcl Rotation {tuple(round(v, 2) for v in triple(props, 'Lcl Rotation'))}, "
                      f"world position {tuple(round(float(v), 4) for v in matrix[:3, 3])} (FBX X, Y, Z; Y is up)")
            continue
        offsets = triple(props, "Lcl Rotation") + triple(props, "Lcl Translation") + triple(props, "PreRotation")
        clean = all(abs(v) < SCALE_TOLERANCE for v in offsets) and all(abs(v - 1.0) < SCALE_TOLERANCE for v in triple(props, "Lcl Scaling", 1.0))
        line = (f"  node {name} ({model['kind']}): rotation {tuple(round(v, 4) for v in triple(props, 'Lcl Rotation'))}, "
                f"scaling {triple(props, 'Lcl Scaling', 1.0)}")
        if not clean:
            line += "  <-- not identity"
            problems.append(f"FBX node {name} is not at identity; Unity would import it with an extra transform")
        if model["parent"]:
            line += "  <-- not a child of the root"
            problems.append(f"FBX node {name} is parented to {models[model['parent']]['name']}; it must hang directly off the root")
        if "vertices" in model:
            vertices = model["vertices"] @ matrix[:3, :3].T + matrix[:3, 3]
            low, high = _bounds(vertices)
            line += f", X {low[0]:.3f}..{high[0]:.3f}, Y {low[1]:.3f}..{high[1]:.3f}, Z {low[2]:.3f}..{high[2]:.3f}"
            want = expected["meshes"].get(name)
            if want is not None and _bounds_differ(_bounds(to_blender(vertices)), want["bounds"]):
                line += "  <-- wrong orientation or size"
                problems.append(f"FBX mesh {name} is not where the scene has it once read as Y-up")
        print(line)
    print(f"  bones: {bones} nodes; worst node position vs scene {worst_head:.5f} m; worst node vs skin bind pose {worst_bind:.5f}")

    # Orientation stated on its own terms, independent of the scene comparison.
    # Unity negates X when it reads the right-handed file, so its avatar convention
    # (facing +Z, left side at -X) means, in FBX axes: up +Y, facing +Z, left side at +X.
    humanoid = cass_spec.load_skeleton()["humanoid"]
    at = {m["name"]: m["world"][:3, 3] for m in models.values() if m["kind"] == "LimbNode"}

    def offset(upper, lower, axis):
        return float(at[humanoid[upper]][axis] - at[humanoid[lower]][axis]) if humanoid.get(upper) in at and humanoid.get(lower) in at else None

    facing = {"up +Y (head above hips)": offset("Head", "Hips", 1), "facing +Z (toes ahead of ankle)": offset("LeftToes", "LeftFoot", 2),
              "left at +X (left arm vs right arm)": offset("LeftUpperArm", "RightUpperArm", 0)}
    print("  orientation: " + ", ".join(f"{label} {value:+.3f}" for label, value in facing.items() if value is not None))
    for label, value in facing.items():
        if value is not None and value <= 0.0:
            problems.append(f"FBX orientation is wrong: expected {label}, measured {value:+.3f}")
    if worst_head > LENGTH_TOLERANCE:
        problems.append(f"FBX bone nodes are up to {worst_head:.3f} m from the scene's bones once read as Y-up (bone data not converted)")
    if worst_bind > LENGTH_TOLERANCE:
        problems.append(f"FBX bone nodes disagree with the skin bind pose by up to {worst_bind:.3f}; Unity would import a deformed rest pose")
    return problems


def verify_import(path, expected):
    """Imports the FBX into an empty scene and compares what Blender rebuilds with the source."""
    problems = []
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.fbx(filepath=str(path), axis_forward="-Z", axis_up="Y", automatic_bone_orientation=False)
    actual = summarise(bpy.data.objects)

    if actual["armatures"].keys() != expected["armatures"].keys():
        problems.append(f"armature objects: {sorted(actual['armatures'])} != {sorted(expected['armatures'])}")
    for name, want in expected["armatures"].items():
        got = actual["armatures"].get(name)
        if got is None:
            continue
        if got["parents"] != want["parents"]:
            diff = sorted(set(got["parents"].items()) ^ set(want["parents"].items()), key=str)
            problems.append(f"bones of {name} changed (name, parent): {diff[:8]}")
            continue
        worst = max(float(np.abs(got["heads"][bone] - head).max()) for bone, head in want["heads"].items())
        print(f"  armature {name}: {len(got['parents'])} bones, worst world-space head offset {worst:.5f} m")
        if worst > LENGTH_TOLERANCE:
            problems.append(f"bones of {name} moved by up to {worst:.3f} m in the round trip")
    if actual["meshes"].keys() != expected["meshes"].keys():
        problems.append(f"mesh objects: {sorted(actual['meshes'])} != {sorted(expected['meshes'])}")
    for name, want in expected["meshes"].items():
        got = actual["meshes"].get(name)
        if got is None:
            continue
        print(f"  mesh {name}: {got['triangles']} triangles, UV layers {got['uv_layers']}, {len(got['shape_keys'])} shape keys")
        for field in ("triangles", "uv_layers", "groups"):
            if got[field] != want[field]:
                problems.append(f"{name}: {field} {got[field]} != {want[field]}")
        if list(got["shape_keys"]) != list(want["shape_keys"]):
            lost = [k for k in want["shape_keys"] if k not in got["shape_keys"]]
            problems.append(f"{name}: shape key names changed; missing {lost[:8]}, got {len(got['shape_keys'])} of {len(want['shape_keys'])}")
        else:
            off = [k for k in want["shape_keys"] if abs(got["shape_keys"][k] - want["shape_keys"][k]) > LENGTH_TOLERANCE]
            if off:
                problems.append(f"{name}: shape keys changed size: {off[:8]}")
        if any(abs(s - 1.0) > SCALE_TOLERANCE for s in got["scale"]):
            problems.append(f"{name}: imported with scale {got['scale']}")
        if _bounds_differ(got["bounds"], want["bounds"]):
            problems.append(f"{name}: bounds changed in the round trip: {np.round(got['bounds'][0], 3)} .. {np.round(got['bounds'][1], 3)}")
    if actual["meshes"]:
        low = min(m["bounds"][0][2] for m in actual["meshes"].values())
        high = max(m["bounds"][1][2] for m in actual["meshes"].values())
        print(f"  height (Blender Z): {low:.4f} .. {high:.4f} m")
    return problems


def main():
    args = parse_args()
    blend = pathlib.Path(args.blend).resolve() if args.blend else None
    if blend is None and not bpy.data.filepath:
        blend = cass_spec.BLEND_PATH
    if blend is not None:
        bpy.ops.wm.open_mainfile(filepath=str(blend))

    report = validate.validate()
    report.print()
    if report.errors:
        raise SystemExit("export: validation failed; nothing was exported")

    collection = bpy.data.collections[cass_spec.EXPORT_COLLECTION]
    expected = summarise(collection.all_objects)
    bake_axis_conversion(list(collection.all_objects))
    output = pathlib.Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.export_scene.fbx(filepath=str(output), check_existing=False, collection=collection.name, **FBX_SETTINGS)
    print(f"export: wrote {output} ({output.stat().st_size} bytes)")

    print("== FBX as stored (what Unity reads) ==")
    problems = verify_file(output, expected)
    print("== re-import into Blender ==")
    problems += verify_import(output, expected)
    for problem in problems:
        print(f"  ERROR: {problem}")
    print(f"== {'FAILED' if problems else 'OK'}: {len(problems)} difference(s) ==")
    if problems:
        raise SystemExit("export: the FBX does not match the source scene")


if __name__ == "__main__":
    main()
