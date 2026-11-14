"""Generates the placeholder character into blender/cass.blend from nothing.

    blender -b --factory-startup --python blender/scripts/build_placeholder.py -- [--force] [--output PATH]

The output is deterministic: the model is computed from the Spec JSON files
and constants in the placeholder package, with no randomness. The scene is
stamped `wirenook_placeholder = True` together with a digest of its content.
An existing file is only overwritten when it carries that stamp and still
matches its digest, i.e. when nobody has modelled in it; anything else needs
--force.
"""

import sys
import pathlib

sys.dont_write_bytecode = True
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import argparse

import bpy
import numpy as np

import cass_spec
import validate
from placeholder import body, face, hair, outfit, rig, shapekeys, stamp
from placeholder.layout import Layout
from placeholder.meshkit import MeshBuilder


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    parser = argparse.ArgumentParser(prog="build_placeholder.py", description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("--force", action="store_true", help="overwrite even a hand-modelled .blend")
    parser.add_argument("--output", default=str(cass_spec.BLEND_PATH))
    return parser.parse_args(argv)


def guard_existing(path, force):
    if not path.exists() or force:
        return
    bpy.ops.wm.open_mainfile(filepath=str(path))
    if not stamp.is_untouched_placeholder():
        raise SystemExit(
            f"build_placeholder: {path} is not an untouched placeholder (missing or stale "
            f"'{cass_spec.PLACEHOLDER_PROP}' stamp); refusing to overwrite hand-made work. Pass --force to replace it."
        )


def make_material():
    material = bpy.data.materials.new(cass_spec.MATERIAL_NAME)
    tree = material.node_tree
    bsdf = next(node for node in tree.nodes if node.type == "BSDF_PRINCIPLED")
    texture = tree.nodes.new("ShaderNodeTexImage")
    texture.image = bpy.data.images.load(str(cass_spec.PALETTE_PNG))
    # Faces sample one swatch centre each; filtering would only blur neighbours in.
    texture.interpolation = "Closest"
    texture.location = (-320, 300)
    tree.links.new(texture.outputs["Color"], bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 1.0
    # Solid-mode texture colouring shows the active image node.
    tree.nodes.active = texture
    return material


def add_shape_keys(obj, basis, keys):
    obj.shape_key_add(name="Basis", from_mix=False)
    rest = np.array(basis, dtype=np.float64)
    for name, delta in keys.items():
        block = obj.shape_key_add(name=name, from_mix=False)
        block.data.foreach_set("co", (rest + delta).astype(np.float32).ravel())
        # Blender 5 creates keys switched on; the rest shape must be the Basis.
        block.value = 0.0
        if block.name != name:
            raise RuntimeError(f"Blender renamed shape key {name!r} to {block.name!r}")


def build_scene():
    scene = bpy.context.scene
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 1.0
    L = Layout(cass_spec.load_proportions())
    skeleton = cass_spec.load_skeleton()
    palette, tiles, blendshapes = cass_spec.load_palette(), cass_spec.load_tiles(), cass_spec.load_blendshapes()

    collection = bpy.data.collections.new(cass_spec.EXPORT_COLLECTION)
    scene.collection.children.link(collection)
    armature = rig.create_armature(skeleton["armature"], collection, L)
    material = make_material()
    field = rig.make_body_field(L)

    body_mesh = MeshBuilder(blendshapes["mesh"], "always")
    neck = body.build_body(body_mesh, L)
    face_rig = face.build_face(body_mesh, L, neck)
    garments = [
        ("Hair", "always", hair.build_hair),
        ("Outfit_Sweater", "outfit.default.top", outfit.build_sweater),
        ("Outfit_Shorts", "outfit.default.bottom", outfit.build_shorts),
        ("Outfit_Boots", "outfit.default.shoes", outfit.build_boots),
        ("Outfit_Hat", "outfit.default.hat", outfit.build_hat),
    ]
    builders = [body_mesh]
    for name, tile, build in garments:
        builder = MeshBuilder(name, tile)
        build(builder, L)
        builders.append(builder)

    for builder in builders:
        builder.fill_weights(field)
        obj = builder.to_object(collection, armature, material, palette, tiles)
        if builder is body_mesh:
            add_shape_keys(obj, builder.co, shapekeys.build_shape_keys(face_rig, builder.co, blendshapes["all"]))
    return scene


def main():
    args = parse_args()
    output = pathlib.Path(args.output).resolve()
    guard_existing(output, args.force)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = build_scene()

    report = validate.validate()
    report.print()
    if report.errors:
        raise SystemExit("build_placeholder: the generated model fails validation; nothing was saved")

    stamp.stamp(scene)
    output.parent.mkdir(parents=True, exist_ok=True)
    # No .blend1 backups: the file is reproducible from this script.
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.wm.save_as_mainfile(filepath=str(output))
    # The palette is referenced relative to the .blend so the repo can live
    # anywhere. A relative path only means something once the file has a
    # location, hence the second save.
    bpy.ops.file.make_paths_relative()
    bpy.ops.wm.save_mainfile()
    print(f"build_placeholder: wrote {output}")


main()
