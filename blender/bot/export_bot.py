"""Validates the bot's .blend and exports it as the FBX Unity imports.

    blender -b --factory-startup --python-exit-code 1 --python blender/bot/export_bot.py -- [--blend PATH] [--output PATH]

Defaults: blender/bot/bot.blend -> Packages/net.wirenook.bot/BlenderExports/bot.fbx.

The export itself is the cass avatar's, imported from blender/scripts/export.py rather than
copied: the same FBX settings, the same baking of the Z-up to Y-up turn into the mesh and bone
data (so every node in the file is at identity and Unity gets the avatar upright, facing +Z, at
scale 1), and the same two checks of the file that was written, once as stored and once through
Blender's importer. On top of those this script checks what only the bot promises: the two
two meshes (`Body`, the face with every shape key, and `Shell`, the rest with none), the material
slots of each and what each slot carries, every shape key by name and by how far it moves (the
empty ones included), and both UV layers of both meshes. Any difference is an error and the exit code is non-zero.
The .blend is never saved.
"""

import sys
import pathlib

sys.dont_write_bytecode = True
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import argparse

import bpy
import numpy as np

import bot_spec
import bot_validate
import export as cass_export  # blender/scripts, put on the path by bot_spec

KEY_TOLERANCE = 1e-5
UV_TOLERANCE = 1e-5


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    parser = argparse.ArgumentParser(prog="export_bot.py", description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("--blend", help="the .blend to export (default: the open file, else blender/bot/bot.blend)")
    parser.add_argument("--output", default=str(bot_spec.FBX_PATH), help="where to write the FBX")
    return parser.parse_args(argv)


def describe(body):
    """What the bot promises beyond the cass checks, read from a mesh object."""
    mesh = body.data
    slots = [slot.material.name if slot.material else None for slot in body.material_slots]
    triangles = [sum(p.loop_total - 2 for p in mesh.polygons if p.material_index == index) for index in range(len(slots))]
    keys = {}
    if mesh.shape_keys:
        basis = bot_validate.key_coordinates(mesh.shape_keys.reference_key)
        for block in mesh.shape_keys.key_blocks[1:]:
            delta = bot_validate.key_coordinates(block) - basis
            moved = np.abs(delta).max(axis=1) > 1e-7
            keys[block.name] = (float(np.abs(delta).max()), int(moved.sum()))
    layers = {}
    for layer in mesh.uv_layers:
        data = np.empty(len(mesh.loops) * 2, dtype=np.float32)
        layer.data.foreach_get("uv", data)
        uv = data.reshape(-1, 2).astype(np.float64)
        layers[layer.name] = np.concatenate([uv.min(axis=0), uv.max(axis=0), uv.mean(axis=0)])
    return {"slots": slots, "triangles": triangles, "keys": keys, "uv": layers, "vertices": len(mesh.vertices), "loops": len(mesh.loops)}


def verify_mesh(name, expected):
    """Compares one mesh of the scene Blender rebuilt from the FBX with what was exported."""
    problems = []
    body = bpy.data.objects.get(name)
    if body is None or body.type != "MESH":
        return [f"the FBX has no mesh object named {name}"]
    got = describe(body)
    print(f"  {name}: material slots {got['slots']}, triangles per slot {got['triangles']}, {got['vertices']} vertices")
    if got["slots"] != expected["slots"] or got["slots"] != list(bot_spec.MESH_MATERIALS[name]):
        problems.append(f"{name}: material slots {got['slots']} != {list(bot_spec.MESH_MATERIALS[name])}")
    elif got["triangles"] != expected["triangles"]:
        problems.append(f"{name}: triangles per material slot {got['triangles']} != {expected['triangles']}")
    if got["vertices"] != expected["vertices"]:
        problems.append(f"{name}: {got['vertices']} vertices != {expected['vertices']}")
    if list(got["keys"]) != list(expected["keys"]):
        lost = [key for key in expected["keys"] if key not in got["keys"]]
        problems.append(f"{name}: shape keys changed; missing {lost[:8]}, got {len(got['keys'])} of {len(expected['keys'])}")
    elif not expected["keys"]:
        print(f"  {name}: no shape keys, as promised")
    else:
        off = [name for name, (size, _count) in expected["keys"].items() if abs(got["keys"][name][0] - size) > KEY_TOLERANCE]
        still = [name for name, (size, _count) in got["keys"].items() if size <= 1e-7]
        if off:
            problems.append(f"shape keys that move a different distance after the round trip: {off[:8]}")
        if still:
            problems.append(f"shape keys that came back empty: {still[:8]}")
        smallest = min(size for size, _count in got["keys"].values())
        print(f"  {name}: {len(got['keys'])} shape keys, all present and none empty; the smallest moves {smallest * 1000.0:.3f} mm")
    if list(got["uv"]) != list(expected["uv"]) or list(got["uv"]) != [bot_spec.UV_ATLAS, bot_spec.UV_TILE]:
        problems.append(f"{name}: UV layers {list(got['uv'])} != {[bot_spec.UV_ATLAS, bot_spec.UV_TILE]}")
    else:
        for layer, stats in expected["uv"].items():
            if np.abs(got["uv"][layer] - stats).max() > UV_TOLERANCE:
                problems.append(f"{name}: UV layer {layer} changed in the round trip")
        print(f"  {name}: UV layers {list(got['uv'])} unchanged")
    return problems


def verify_bot(promised):
    """Both meshes, that the shell came back without shape keys, and every bone of the contract."""
    problems = []
    meshes = sorted(o.name for o in bpy.data.objects if o.type == "MESH")
    if meshes != sorted(bot_spec.MESH_MATERIALS):
        problems.append(f"mesh objects in the FBX are {meshes}, not {sorted(bot_spec.MESH_MATERIALS)}")
    for name, expected in promised.items():
        problems += verify_mesh(name, expected)
    shell = bpy.data.objects.get(bot_spec.SHELL)
    if shell is not None and shell.type == "MESH" and shell.data.shape_keys is not None:
        problems.append(f"{bot_spec.SHELL} came back with shape keys")
    armature = bpy.data.objects.get(bot_spec.ARMATURE)
    bones = set(armature.data.bones.keys()) if armature else set()
    lost = [name for name in bot_spec.expected_bones() if name not in bones]
    if lost:
        problems.append(f"bones missing from the FBX: {lost[:8]}")
    return problems


def main():
    args = parse_args()
    blend = pathlib.Path(args.blend).resolve() if args.blend else None
    if blend is None and not bpy.data.filepath:
        blend = bot_spec.BLEND_PATH
    if blend is not None:
        bpy.ops.wm.open_mainfile(filepath=str(blend))

    report = bot_validate.validate()
    report.print()
    if report.errors:
        raise SystemExit("export_bot: validation failed; nothing was exported")

    collection = bpy.data.collections[bot_spec.EXPORT_COLLECTION]
    objects = list(collection.all_objects)
    expected = cass_export.summarise(objects)
    promised = {name: describe(bpy.data.objects[name]) for name in bot_spec.MESH_MATERIALS}
    cass_export.bake_axis_conversion(objects)
    output = pathlib.Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.export_scene.fbx(filepath=str(output), check_existing=False, collection=collection.name, **cass_export.FBX_SETTINGS)
    print(f"export_bot: wrote {output} ({output.stat().st_size} bytes)")

    print("== FBX as stored (what Unity reads) ==")
    problems = cass_export.verify_file(output, expected)
    print("== re-import into Blender ==")
    problems += cass_export.verify_import(output, expected)
    print("== the bot's own promises ==")
    problems += verify_bot(promised)
    for problem in problems:
        print(f"  ERROR: {problem}")
    print(f"== {'FAILED' if problems else 'OK'}: {len(problems)} difference(s) ==")
    if problems:
        raise SystemExit("export_bot: the FBX does not match the source scene")
    for name, mesh in promised.items():
        print(f"export_bot: {name}: {sum(mesh['triangles'])} triangles, {mesh['vertices']} vertices, "
              f"{len(mesh['keys'])} shape keys, material slots {mesh['slots']}")


if __name__ == "__main__":
    main()
