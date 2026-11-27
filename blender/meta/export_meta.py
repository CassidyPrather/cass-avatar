"""Validates the meta figure's .blend and exports it as the FBX Unity imports.

    blender -b --factory-startup --python-exit-code 1 --python blender/meta/export_meta.py -- [--blend PATH] [--output PATH]

Defaults: blender/meta/meta.blend -> <meta_spec.PACKAGE>/BlenderExports/meta.fbx.

The export itself is the cass avatar's, imported from blender/scripts/export.py rather than
copied: the same FBX settings, the same baking of the Z-up to Y-up turn into the mesh and bone
data (so every node in the file is at identity and Unity gets the avatar upright, facing +Z, at
scale 1), and the same two checks of the file that was written, once as stored and once through
Blender's importer. On top of those this script checks what only this model promises: one mesh,
`Body`, with one material slot and no shape keys; both UV layers unchanged; every bone of the
contract; nothing weighted to Head. Any difference is an error and the exit code is non-zero.
The .blend is never saved.
"""

import sys
import pathlib

sys.dont_write_bytecode = True
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import argparse

import bpy
import numpy as np

import meta_spec
import meta_validate
import export as cass_export  # blender/scripts, put on the path by meta_spec

UV_TOLERANCE = 1e-5


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    parser = argparse.ArgumentParser(prog="export_meta.py", description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("--blend", help="the .blend to export (default: the open file, else blender/meta/meta.blend)")
    parser.add_argument("--output", default=str(meta_spec.FBX_PATH), help="where to write the FBX")
    return parser.parse_args(argv)


def describe(body):
    mesh = body.data
    slots = [slot.material.name if slot.material else None for slot in body.material_slots]
    layers = {}
    for layer in mesh.uv_layers:
        data = np.empty(len(mesh.loops) * 2, dtype=np.float32)
        layer.data.foreach_get("uv", data)
        uv = data.reshape(-1, 2).astype(np.float64)
        layers[layer.name] = np.concatenate([uv.min(axis=0), uv.max(axis=0), uv.mean(axis=0)])
    weighted = sorted({body.vertex_groups[e.group].name for v in mesh.vertices for e in v.groups if e.weight > 0.0})
    return {"slots": slots, "triangles": meta_validate.triangle_count(mesh), "uv": layers, "vertices": len(mesh.vertices),
            "keys": mesh.shape_keys is not None, "weighted": weighted}


def verify_model(promised):
    problems = []
    meshes = sorted(o.name for o in bpy.data.objects if o.type == "MESH")
    if meshes != [meta_spec.MESH]:
        return [f"mesh objects in the FBX are {meshes}, not ['{meta_spec.MESH}']"]
    got = describe(bpy.data.objects[meta_spec.MESH])
    print(f"  {meta_spec.MESH}: material slots {got['slots']}, {got['triangles']} triangles, {got['vertices']} vertices")
    if got["slots"] != [meta_spec.MATERIAL]:
        problems.append(f"material slots {got['slots']} != ['{meta_spec.MATERIAL}']")
    if got["triangles"] != promised["triangles"]:
        problems.append(f"{got['triangles']} triangles != {promised['triangles']}")
    if got["vertices"] != promised["vertices"]:
        problems.append(f"{got['vertices']} vertices != {promised['vertices']}")
    if got["keys"]:
        problems.append("the mesh came back with shape keys")
    if list(got["uv"]) != [meta_spec.UV_ATLAS, meta_spec.UV_TILE]:
        problems.append(f"UV layers {list(got['uv'])} != {[meta_spec.UV_ATLAS, meta_spec.UV_TILE]}")
    else:
        for layer, stats in promised["uv"].items():
            if np.abs(got["uv"][layer] - stats).max() > UV_TOLERANCE:
                problems.append(f"UV layer {layer} changed in the round trip")
        print(f"  UV layers {list(got['uv'])} unchanged")
    if got["weighted"] != promised["weighted"]:
        problems.append(f"weighted bones changed: {sorted(set(got['weighted']) ^ set(promised['weighted']))}")
    if "Head" in got["weighted"]:
        problems.append("something is weighted to Head")
    armature = bpy.data.objects.get(meta_spec.ARMATURE)
    bones = {bone.name: (bone.parent.name if bone.parent else None) for bone in armature.data.bones} if armature else {}
    expected = meta_spec.expected_bones()
    lost = [name for name in expected if name not in bones]
    if lost:
        problems.append(f"bones missing from the FBX: {lost[:8]}")
    moved = [name for name, parent in expected.items() if name in bones and bones[name] != parent]
    if moved:
        problems.append(f"bones whose parent changed: {moved[:8]}")
    extra = [name for name in bones if name not in expected]
    if extra:
        problems.append(f"bones the contract does not list: {extra[:8]}")
    print(f"  {len(bones)} bones, {len(got['weighted'])} of them weighted; Head carries nothing and {meta_spec.HEAD_VISUAL} is beside it under "
          f"{bones.get(meta_spec.HEAD_VISUAL)}")
    return problems


def main():
    args = parse_args()
    blend = pathlib.Path(args.blend).resolve() if args.blend else None
    if blend is None and not bpy.data.filepath:
        blend = meta_spec.BLEND_PATH
    if blend is not None:
        bpy.ops.wm.open_mainfile(filepath=str(blend))

    report = meta_validate.validate()
    report.print()
    if report.errors:
        raise SystemExit("export_meta: validation failed; nothing was exported")

    collection = bpy.data.collections[meta_spec.EXPORT_COLLECTION]
    objects = list(collection.all_objects)
    expected = cass_export.summarise(objects)
    promised = describe(bpy.data.objects[meta_spec.MESH])
    cass_export.bake_axis_conversion(objects)
    output = pathlib.Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.export_scene.fbx(filepath=str(output), check_existing=False, collection=collection.name, **cass_export.FBX_SETTINGS)
    print(f"export_meta: wrote {output} ({output.stat().st_size} bytes)")

    print("== FBX as stored (what Unity reads) ==")
    problems = cass_export.verify_file(output, expected)
    print("== re-import into Blender ==")
    problems += cass_export.verify_import(output, expected)
    print("== this model's own promises ==")
    problems += verify_model(promised)
    for problem in problems:
        print(f"  ERROR: {problem}")
    print(f"== {'FAILED' if problems else 'OK'}: {len(problems)} difference(s) ==")
    if problems:
        raise SystemExit("export_meta: the FBX does not match the source scene")
    print(f"export_meta: {meta_spec.MESH}: {promised['triangles']} triangles, {promised['vertices']} vertices, material slots {promised['slots']}")


if __name__ == "__main__":
    main()
