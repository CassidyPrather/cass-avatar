"""Builds the meta figure, a low-polygon game master in a hooded robe, from code alone.

    blender -b --factory-startup --python-exit-code 1 --python blender/meta/build_meta.py -- [--force] [--draft] [--output PATH]

Writes blender/meta/meta.blend and, under meta_spec.PACKAGE, the three textures and the two Spec
files (skeleton.json, model.json). Nothing is read but the wirenook palette and the cass avatar's
humanoid bone names; every vertex and texel is made here.

The output is deterministic. The scene is stamped as generator output with a digest of its
content, as the cass build does; an existing .blend that no longer matches its stamp has been
edited by hand and is only overwritten with --force.
"""

import sys
import pathlib

sys.dont_write_bytecode = True
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import argparse
import json

import bpy
import numpy as np
from mathutils import Vector

import meta_spec  # first: it puts the robot's kit and the cass scripts on the path
import bot_geo
import meta_geo
import meta_model
import meta_validate
from bot_geo import PX
from kitbash import stamp


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    parser = argparse.ArgumentParser(prog="build_meta.py", description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("--force", action="store_true", help="overwrite even a hand-edited .blend")
    parser.add_argument("--draft", action="store_true", help="save even when validation fails, to look at work in progress")
    parser.add_argument("--output", help="where to save (default: blender/meta/meta.blend)")
    return parser.parse_args(argv)


def guard_existing(path, force):
    if not path.exists() or force:
        return
    bpy.ops.wm.open_mainfile(filepath=str(path))
    if not stamp.is_untouched():
        raise SystemExit(f"build_meta: {path} is not untouched generator output; refusing to overwrite hand-made work. Pass --force to replace it.")


def make_armature(collection):
    data = bpy.data.armatures.new(meta_spec.ARMATURE)
    armature = bpy.data.objects.new(meta_spec.ARMATURE, data)
    collection.objects.link(armature)
    bpy.context.view_layer.objects.active = armature
    bpy.ops.object.mode_set(mode="EDIT")
    parents = meta_spec.expected_bones()
    table = []
    for name, head, tail, roll in meta_model.bones():
        table.append((name, Vector(head), Vector(tail), Vector(roll)))
        if ".L" in name:
            mirror = Vector((-1.0, 1.0, 1.0))
            table.append((name.replace(".L", ".R"), Vector(head) * mirror, Vector(tail) * mirror, Vector(roll) * mirror))
    made = {name for name, *_rest in table}
    if made != set(parents):
        raise SystemExit(f"build_meta: bones differ from the contract: {sorted(made ^ set(parents))}")
    by_name = {name: rest for name, *rest in table}
    for name in parents:
        head, tail, roll = by_name[name]
        bone = data.edit_bones.new(name)
        bone.head, bone.tail = head * PX, tail * PX
        bone.align_roll(roll)
        bone.use_deform = True
    for name, parent in parents.items():
        if parent is not None:
            data.edit_bones[name].parent = data.edit_bones[parent]
            data.edit_bones[name].use_connect = False
    bpy.ops.object.mode_set(mode="OBJECT")
    return armature


def make_material():
    material = bpy.data.materials.new(meta_spec.MATERIAL)
    if material.node_tree is None:
        material.use_nodes = True
    tree = material.node_tree
    for node in list(tree.nodes):
        if node.type != "OUTPUT_MATERIAL":
            tree.nodes.remove(node)
    output = next(node for node in tree.nodes if node.type == "OUTPUT_MATERIAL")
    colour = tree.nodes.new("ShaderNodeTexImage")
    colour.image = bpy.data.images.load(str(meta_spec.ATLAS_PNG), check_existing=True)
    colour.interpolation = "Closest"
    colour.location = (-600, 200)
    glow = tree.nodes.new("ShaderNodeTexImage")
    glow.image = bpy.data.images.load(str(meta_spec.EMISSION_PNG), check_existing=True)
    glow.image.colorspace_settings.name = "Non-Color"
    glow.interpolation = "Closest"
    glow.location = (-600, -150)
    tint = tree.nodes.new("ShaderNodeTexImage")
    tint.image = bpy.data.images.load(str(meta_spec.TINT_PNG), check_existing=True)
    tint.image.colorspace_settings.name = "Non-Color"
    tint.interpolation = "Closest"
    tint.location = (-600, -500)
    tint.label = "Signature (tint mask)"
    bsdf = tree.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.inputs["Roughness"].default_value = 1.0
    tree.links.new(colour.outputs["Color"], bsdf.inputs["Base Color"])
    tree.links.new(colour.outputs["Color"], bsdf.inputs["Emission Color"])
    tree.links.new(glow.outputs["Color"], bsdf.inputs["Emission Strength"])
    tree.links.new(bsdf.outputs[0], output.inputs["Surface"])
    tree.nodes.active = colour
    return material


def make_mesh(data, atlas, armature, collection, material):
    mesh = bpy.data.meshes.new(meta_spec.MESH)
    mesh.from_pydata([tuple(c * PX for c in v) for v in data["vertices"]], [], data["faces"])
    if mesh.validate():
        raise SystemExit("build_meta: the generated mesh was not valid (degenerate or duplicate faces)")
    mesh.update()
    if len(mesh.polygons) != len(data["faces"]):
        raise SystemExit("build_meta: faces were dropped while making the mesh")

    atlas_layer = mesh.uv_layers.new(name=meta_spec.UV_ATLAS, do_init=False)
    uv = [island.uv(x, y, atlas.size) for corners in data["loops"] for island, x, y in corners]
    atlas_layer.data.foreach_set("uv", np.asarray(uv, dtype=np.float32).ravel())
    # The second layer only says "never discard": the shared material drops faces by the tile of this layer.
    tile_layer = mesh.uv_layers.new(name=meta_spec.UV_TILE, do_init=False)
    tile_layer.data.foreach_set("uv", np.full(len(mesh.loops) * 2, 0.5, dtype=np.float32))
    mesh.uv_layers.active = mesh.uv_layers[meta_spec.UV_ATLAS]
    mesh.uv_layers[meta_spec.UV_ATLAS].active_render = True

    mesh.materials.append(material)
    mesh.polygons.foreach_set("use_smooth", [False] * len(mesh.polygons))
    # Which part each face belongs to, for the validator: it poses the figure and looks for one part
    # coming through another. The attribute is not exported.
    names = sorted(set(data["solids"]))
    part = mesh.attributes.new(meta_spec.PART_ATTRIBUTE, "INT", "FACE")
    part.data.foreach_set("value", [names.index(name) for name in data["solids"]])
    mesh[meta_spec.PART_NAMES] = json.dumps(names)

    body = bpy.data.objects.new(meta_spec.MESH, mesh)
    collection.objects.link(body)
    body.parent = armature
    body.parent_type = "OBJECT"
    modifier = body.modifiers.new("Armature", "ARMATURE")
    modifier.object = armature
    groups = {}
    for bone in armature.data.bones:
        if any(bone.name in weights for weights in data["weights"]):
            groups[bone.name] = body.vertex_groups.new(name=bone.name)
    for index, weights in enumerate(data["weights"]):
        total = sum(weights.values())
        for bone, weight in weights.items():
            groups[bone].add([index], weight / total, "REPLACE")
    return body


def to_unity(point):
    """Pixels in Blender's axes -> metres in the avatar's frame in Unity: x to its right, y up, z the way it faces."""
    return [round(-point[0] * PX, 6) + 0.0, round(point[2] * PX, 6) + 0.0, round(-point[1] * PX, 6) + 0.0]


def write_spec(atlas, triangles, vertices, bones):
    m = meta_model
    skeleton = {
        "$comment": "Bone contract of the meta figure, written by blender/meta/build_meta.py; do not edit. `humanoid` maps "
                    "UnityEngine.HumanBodyBones names to the bones of the FBX, whose rest pose is the T-pose. `extra` lists the "
                    "others with their parents. One with `visual` is the seen twin of the humanoid bone it names: it rests in the "
                    "same place under the same parent, carries everything that bone would, and must be made to follow it (the "
                    "humanoid Head itself carries nothing, so that it can be moved away without anything being seen to move). One "
                    "with `sway` is the root of an optional physics chain of that kind; a build without physics leaves its bones "
                    "rigid and the figure still looks right.",
        "armature": meta_spec.ARMATURE,
        "humanoid": dict(meta_spec.HUMANOID),
        "extra": [{"name": name, "parent": parent, **role} for name, parent, role in meta_spec.EXTRA_BONES],
    }
    tip = m.index_tip()
    eye = (0.0, m.rim_y(204.0, 6.0), 204.0)
    opening = (0.0, m.rim_y(204.0), 204.0)
    model = {
        "$comment": "Facts about the meta figure that Unity needs, written by blender/meta/build_meta.py; do not edit. Lengths are "
                    "metres. `unity` positions are in the avatar's frame as Unity imports it (x to its right, y up, z forward). "
                    "The signature colour: every texel that is white in `atlas.tint` is painted in the hue `signature.hue` "
                    "(0..1), at one of the strengths listed, and nothing else in the atlas is; turning the hue of those texels "
                    "by (wanted - signature.hue) gives the wearer's colour. `atlas.emission` is white on the subset of them "
                    "that glows. Each `sway` chain ends at `endUnity`, the far end of its last bone, which is what a physics "
                    "chain of one bone needs to know to have anything to swing.",
        "mesh": meta_spec.MESH,
        "material": meta_spec.MATERIAL,
        "atlas": {"texture": "Textures/" + meta_spec.ATLAS_PNG.name, "emission": "Textures/" + meta_spec.EMISSION_PNG.name,
                  "tint": "Textures/" + meta_spec.TINT_PNG.name, "size": atlas.size, "filter": "point", "metresPerTexel": PX},
        "signature": {"hue": round(meta_spec.SIGNATURE_HUE, 6),
                      "colours": {name: "#%02x%02x%02x" % meta_spec.signature_rgb(name) for name in meta_spec.SIGNATURE}},
        "height": round(m.HOOD_TOP * PX, 6),
        "viewPosition": {"unity": to_unity(eye), "note": "Inside the hood, where eyes would be."},
        "hood": {"openingCentreUnity": to_unity(opening), "bone": meta_spec.HEAD_VISUAL},
        "fingerLight": {"leftBone": "Index3.L", "rightBone": "Index3.R", "leftTipUnity": to_unity(tip),
                        "rightTipUnity": to_unity((-tip[0], tip[1], tip[2])),
                        "note": "The ends of the index fingers in the T-pose; the fingers point along the arm."},
        "sway": [{"kind": "hood", "bones": ["Sway.Hood", "Sway.Hood.001"], "endUnity": to_unity(tuple(m.HOOD_TIP))},
                 {"kind": "sleeve", "bones": ["Sway.Sleeve.L"], "endUnity": to_unity(m.SLEEVE_SWAY_END)},
                 {"kind": "sleeve", "bones": ["Sway.Sleeve.R"],
                  "endUnity": to_unity((-m.SLEEVE_SWAY_END[0], m.SLEEVE_SWAY_END[1], m.SLEEVE_SWAY_END[2]))}],
        "counts": {"triangles": triangles, "vertices": vertices, "bones": bones},
    }
    meta_spec.SKELETON_JSON.parent.mkdir(parents=True, exist_ok=True)
    meta_spec.SKELETON_JSON.write_text(json.dumps(skeleton, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    meta_spec.MODEL_JSON.write_text(json.dumps(model, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build_scene():
    scene = bpy.context.scene
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 1.0
    collection = bpy.data.collections.new(meta_spec.EXPORT_COLLECTION)
    scene.collection.children.link(collection)

    palette = meta_spec.load_palette()
    atlas = bot_geo.Atlas(meta_spec.ATLAS_SIZE, palette, background="night-0")
    builder = meta_geo.MetaBuilder(atlas)
    meta_model.build(builder)

    rows = atlas.pack()
    colour, glow = atlas.render()
    # The tint mask: every texel in a signature colour, and no other.
    tint = np.zeros(colour.shape[:2], dtype=bool)
    for name in meta_spec.SIGNATURE:
        tint |= (colour == np.array(palette[name], dtype=np.uint8)).all(axis=2)
    if (glow.astype(bool) & ~tint).any():
        raise SystemExit("build_meta: something glows that is not in a signature colour; the emission would not follow the wearer's hue")
    meta_spec.TEXTURES.mkdir(parents=True, exist_ok=True)
    bot_geo.write_png(meta_spec.ATLAS_PNG, colour)
    bot_geo.write_png(meta_spec.EMISSION_PNG, np.repeat(glow[:, :, None], 3, axis=2))
    bot_geo.write_png(meta_spec.TINT_PNG, np.repeat((tint * 255).astype(np.uint8)[:, :, None], 3, axis=2))
    print(f"build_meta: atlas {atlas.size} x {atlas.size}, {len(atlas.islands)} islands, {rows} rows used, "
          f"{int(tint.sum())} signature texels of which {int(glow.astype(bool).sum())} glow")

    data = builder.collect()
    armature = make_armature(collection)
    make_mesh(data, atlas, armature, collection, make_material())
    triangles = builder.triangle_count()
    write_spec(atlas, triangles, len(data["vertices"]), len(armature.data.bones))
    print(f"build_meta: {triangles} triangles, {len(data['vertices'])} vertices, {len(armature.data.bones)} bones")
    return scene


def main():
    args = parse_args()
    output = pathlib.Path(args.output).resolve() if args.output else meta_spec.BLEND_PATH
    guard_existing(output, args.force)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = build_scene()

    report = meta_validate.validate()
    report.print()
    if report.errors and not args.draft:
        raise SystemExit("build_meta: the model fails validation; nothing was saved")

    stamp.stamp(scene)
    print(f"build_meta: content digest {scene[meta_spec.cass_spec.GENERATED_DIGEST_PROP]}")
    output.parent.mkdir(parents=True, exist_ok=True)
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.wm.save_as_mainfile(filepath=str(output), compress=True)
    # The textures are referenced relative to the .blend, which only means something once it has a location.
    bpy.ops.file.make_paths_relative()
    bpy.ops.wm.save_mainfile(compress=True)
    print(f"build_meta: wrote {output}")


main()
