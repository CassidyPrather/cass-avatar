"""Builds the wirenook bot, a low-polygon robot avatar, from code alone.

    blender -b --factory-startup --python-exit-code 1 --python blender/bot/build_bot.py -- [--force] [--draft] [--output PATH]

Writes blender/bot/bot.blend, the two textures in Packages/net.wirenook.bot/Textures/ and the face
contract Packages/net.wirenook.bot/Spec/face.json. Nothing is read but the wirenook palette and
the cass avatar's bone and blendshape names; every vertex and texel is made here.

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

import bot_face
import bot_geo
import bot_model
import bot_spec
import bot_validate
from bot_geo import PX
from kitbash import stamp  # blender/scripts, put on the path by bot_spec


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    parser = argparse.ArgumentParser(prog="build_bot.py", description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("--force", action="store_true", help="overwrite even a hand-edited .blend")
    parser.add_argument("--draft", action="store_true", help="save even when validation fails, to look at work in progress")
    parser.add_argument("--output", help="where to save (default: blender/bot/bot.blend)")
    return parser.parse_args(argv)


def guard_existing(path, force):
    if not path.exists() or force:
        return
    bpy.ops.wm.open_mainfile(filepath=str(path))
    if not stamp.is_untouched():
        raise SystemExit(f"build_bot: {path} is not untouched generator output; refusing to overwrite hand-made work. Pass --force to replace it.")


def make_armature(collection):
    data = bpy.data.armatures.new(bot_spec.ARMATURE)
    armature = bpy.data.objects.new(bot_spec.ARMATURE, data)
    collection.objects.link(armature)
    bpy.context.view_layer.objects.active = armature
    bpy.ops.object.mode_set(mode="EDIT")
    parents = bot_spec.expected_bones()
    table = []
    for name, head, tail, roll in bot_model.bones():
        table.append((name, Vector(head), Vector(tail), Vector(roll)))
        if ".L" in name:
            mirror = Vector((-1.0, 1.0, 1.0))
            table.append((name.replace(".L", ".R"), Vector(head) * mirror, Vector(tail) * mirror, Vector(roll) * mirror))
    made = {name for name, *_rest in table}
    if made != set(parents):
        raise SystemExit(f"build_bot: bones differ from the contract: {sorted(made ^ set(parents))}")
    # In the contract's own order, so that the armature lists the humanoid bones as the spec does.
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


def make_material(name, hologram):
    material = bpy.data.materials.new(name)
    if material.node_tree is None:
        material.use_nodes = True
    tree = material.node_tree
    for node in list(tree.nodes):
        if node.type != "OUTPUT_MATERIAL":
            tree.nodes.remove(node)
    output = next(node for node in tree.nodes if node.type == "OUTPUT_MATERIAL")
    colour = tree.nodes.new("ShaderNodeTexImage")
    colour.image = bpy.data.images.load(str(bot_spec.ATLAS_PNG), check_existing=True)
    colour.interpolation = "Closest"
    colour.location = (-600, 200)
    glow = tree.nodes.new("ShaderNodeTexImage")
    glow.image = bpy.data.images.load(str(bot_spec.EMISSION_PNG), check_existing=True)
    glow.image.colorspace_settings.name = "Non-Color"
    glow.interpolation = "Closest"
    glow.location = (-600, -150)
    if hologram:
        # Light added to what is behind it, which is how Unity will draw it.
        emission = tree.nodes.new("ShaderNodeEmission")
        clear = tree.nodes.new("ShaderNodeBsdfTransparent")
        add = tree.nodes.new("ShaderNodeAddShader")
        tree.links.new(colour.outputs["Color"], emission.inputs["Color"])
        tree.links.new(emission.outputs[0], add.inputs[0])
        tree.links.new(clear.outputs[0], add.inputs[1])
        tree.links.new(add.outputs[0], output.inputs["Surface"])
        material.surface_render_method = "BLENDED"
        material.use_backface_culling = True
    else:
        bsdf = tree.nodes.new("ShaderNodeBsdfPrincipled")
        bsdf.inputs["Roughness"].default_value = 1.0
        tree.links.new(colour.outputs["Color"], bsdf.inputs["Base Color"])
        tree.links.new(colour.outputs["Color"], bsdf.inputs["Emission Color"])
        tree.links.new(glow.outputs["Color"], bsdf.inputs["Emission Strength"])
        tree.links.new(bsdf.outputs[0], output.inputs["Surface"])
    tree.nodes.active = colour
    return material


def make_mesh(name, data, atlas, armature, collection, materials):
    """One skinned mesh object from collected faces, with the slots its name is promised (bot_spec.MESH_MATERIALS)."""
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata([tuple(c * PX for c in v) for v in data["vertices"]], [], data["faces"])
    if mesh.validate():
        raise SystemExit("build_bot: the generated mesh was not valid (degenerate or duplicate faces)")
    mesh.update()
    if len(mesh.polygons) != len(data["faces"]):
        raise SystemExit("build_bot: faces were dropped while making the mesh")

    atlas_layer = mesh.uv_layers.new(name=bot_spec.UV_ATLAS, do_init=False)
    uv = [island.uv(x, y, atlas.size) for corners in data["loops"] for island, x, y in corners]
    atlas_layer.data.foreach_set("uv", np.asarray(uv, dtype=np.float32).ravel())
    # The second layer only says "never discard": the shared material drops faces by the tile of this layer.
    tile_layer = mesh.uv_layers.new(name=bot_spec.UV_TILE, do_init=False)
    tile_layer.data.foreach_set("uv", np.full(len(mesh.loops) * 2, 0.5, dtype=np.float32))
    mesh.uv_layers.active = mesh.uv_layers[bot_spec.UV_ATLAS]
    mesh.uv_layers[bot_spec.UV_ATLAS].active_render = True

    slots = bot_spec.MESH_MATERIALS[name]
    if max(data["materials"]) >= len(slots):
        raise SystemExit(f"build_bot: {name} has faces for a material slot it does not have")
    for slot in slots:
        mesh.materials.append(materials[slot])
    mesh.polygons.foreach_set("material_index", data["materials"])
    mesh.polygons.foreach_set("use_smooth", [False] * len(mesh.polygons))
    if name == bot_spec.MESH:
        attribute = mesh.attributes.new(bot_spec.SPRITE_ATTRIBUTE, "INT", "POINT")
        attribute.data.foreach_set("value", [1 if flag else 0 for flag in data["sprite"]])

    body = bpy.data.objects.new(name, mesh)
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


def make_shape_keys(body, data, keys, depths):
    """One key per name. A key that shows a sprite brings its own quad forward and sends the layer's
    neutral sprite back; a key that shows nothing nudges the hidden anchor so that it is not empty."""
    tags = data["tags"]
    body.shape_key_add(name="Basis", from_mix=False)
    for name, _group, layer, _sprite in keys:
        block = body.shape_key_add(name=name, from_mix=False)
        if layer is None:
            for index in tags["anchor"]:
                block.data[index].co.y += bot_face.EMPTY_NUDGE
            continue
        hidden, shown = depths[name]
        for index in tags[f"key:{name}"]:
            block.data[index].co.y -= hidden + shown
        if layer != "overlay":
            for index in tags[f"neutral:{layer}"]:
                block.data[index].co.y += bot_face.NEUTRAL_TRAVEL
    for block in body.data.shape_keys.key_blocks:
        block.value = 0.0
    body.active_shape_key_index = 0


def to_unity(point):
    """Blender (x, y, z) -> the avatar's frame in Unity: x to its right, y up, z the way it faces."""
    return [round(-point[0], 6) + 0.0, round(point[2], 6) + 0.0, round(-point[1], 6) + 0.0]


def metres(*point):
    return [round(c * PX, 6) for c in point]


def write_face_json(atlas, keys, depths):
    m = bot_model
    sw, z0, z1 = m.SCREEN_HALF_WIDTH, m.SCREEN_Z0, m.SCREEN_Z1

    def texels(layer, sprite):
        rows = bot_face.sprite_picture(layer, sprite)
        island = atlas.islands[f"sprite/{layer}.{sprite}:{len(rows[0])}x{len(rows)}"]
        size = atlas.size
        return {"rect": [island.x, island.y, island.w, island.h],
                "uv": [island.x / size, 1.0 - (island.y + island.h) / size, (island.x + island.w) / size, 1.0 - island.y / size]}

    def entry(layer, sprite, screen_rect):
        result = {"name": sprite}
        if layer != "overlay" and sprite == bot_face.NEUTRAL[layer]:
            result["neutral"] = True
        result["screenRect"] = screen_rect
        result.update(texels(layer, sprite))
        result["shownDepth"] = round(bot_face.shown_depth(layer, sprite), 6)
        return result

    (c0, c1), (r0, r1) = bot_face.BLUSH_COLUMNS, bot_face.BLUSH_ROWS
    half = bot_face.SCREEN_W // 2
    overlay_rects = {"lid-left": [half, 0, half, bot_face.EYES_H], "lid-right": [0, 0, half, bot_face.EYES_H],
                     "blush": [c0, r0, c1 - c0, r1 - r0], bot_face.BLUESCREEN: [0, 0, bot_face.SCREEN_W, bot_face.SCREEN_H]}
    sprites = {
        "eyes": [entry("eyes", s, [0, 0, bot_face.SCREEN_W, bot_face.EYES_H]) for s in [bot_face.NEUTRAL["eyes"]] + bot_face.ORDER["eyes"]],
        "mouth": [entry("mouth", s, [0, bot_face.EYES_H, bot_face.SCREEN_W, bot_face.MOUTH_H])
                  for s in [bot_face.NEUTRAL["mouth"]] + bot_face.ORDER["mouth"]],
        "overlay": [entry("overlay", s, overlay_rects[s]) for s in bot_face.OVERLAYS],
    }
    sprites["overlay"][bot_face.OVERLAYS.index("blush")]["mirroredAt"] = [bot_face.SCREEN_W - c1, r0, c1 - c0, r1 - r0]

    shape_keys = []
    for name, group, layer, sprite in keys:
        item = {"name": name, "group": group, "layer": layer, "shows": sprite,
                "hides": bot_face.NEUTRAL[layer] if layer in ("eyes", "mouth") else None}
        if layer is not None:
            item["restDepth"] = round(-depths[name][0], 6)
        shape_keys.append(item)

    eye_z = z1 - 7.5
    plate = (0.0, m.PLATE_Y, (z0 + z1) / 2.0)
    document = {
        "$comment": "The sprite face of the wirenook bot, written by blender/bot/build_bot.py; do not edit. The mesh `Body` is the "
                    "face alone (the sprites and every shape key, on the material `bot`); the rest of the bot, the backing plate "
                    "included, is the mesh `Shell`, which has no shape keys. The head has a screen: "
                    "a backing plate behind an opening in the front of the head. Textured quads (sprites) rest either just in front "
                    "of the plate (shown) or just behind it (hidden), and shape keys on the mesh only ever slide them along the "
                    "screen's depth. Two layers are independent, `eyes` (the upper rows of the screen) and `mouth` (the lower rows); "
                    "each has one neutral sprite that rests shown. A key of a layer brings its own copy of a sprite forward to "
                    "`shownDepth` and sends that layer's neutral sprite back; both cross the plate at weight `depth.crossover`. "
                    "Where two keys of a layer are on, the sprite with the larger `shownDepth` covers the other (sprites are listed "
                    "from back to front), so a blink covers an expression and speech covers a smile. `overlay` sprites lie over the "
                    "layers and hide nothing: the two eyelids (half the eyes layer each), the blush marks and the full-screen "
                    "bluescreen. A key whose `layer` is null shows nothing; it moves a hidden triangle by `depth.emptyNudge` so that "
                    "no tool drops it. Left and right are the avatar's own. Lengths are metres. `unity` positions are in the "
                    "avatar's frame as Unity imports it (x to its right, y up, z forward); `blender` ones are x to its left, "
                    "y back, z up. `rect` is [x, y, width, height] in texels from the atlas's top left; `uv` is "
                    "[u0, v0, u1, v1] from its bottom left; `screenRect` is [column, row, width, height] in screen pixels "
                    "from the screen's top left, as someone facing the avatar sees it.",
        "mesh": bot_spec.MESH,
        "material": bot_spec.MATERIALS[0],
        "atlas": {"texture": "Textures/" + bot_spec.ATLAS_PNG.name, "emission": "Textures/" + bot_spec.EMISSION_PNG.name,
                  "size": atlas.size, "filter": "point", "metresPerTexel": PX},
        "screen": {
            "pixels": [bot_face.SCREEN_W, bot_face.SCREEN_H],
            "eyesRows": bot_face.EYES_H,
            "size": metres(2.0 * sw, z1 - z0),
            "pixelSize": PX,
            "centreUnity": to_unity(metres(*plate)),
            "centreBlender": metres(*plate),
            "plateBlender": metres(*plate),
            "openingDepth": round(m.RECESS * PX, 6),
            "eyesCentreUnity": to_unity(metres(0.0, m.PLATE_Y, (m.EYES_Z0 + z1) / 2.0)),
            "mouthCentreUnity": to_unity(metres(0.0, m.PLATE_Y, (z0 + m.EYES_Z0) / 2.0)),
            "leftEyeUnity": to_unity(metres(sw - bot_face.EYE_CENTRES[0], m.PLATE_Y, eye_z)),
            "rightEyeUnity": to_unity(metres(-(sw - bot_face.EYE_CENTRES[0]), m.PLATE_Y, eye_z)),
        },
        "viewPosition": {"unity": to_unity(metres(0.0, m.PLATE_Y, eye_z)),
                         "note": "Between the eyes of the neutral face, on the backing plate of the screen."},
        "depth": {"neutralShown": bot_face.NEUTRAL_SHOWN, "neutralTravel": round(bot_face.NEUTRAL_TRAVEL, 6),
                  "crossover": bot_face.CROSSOVER, "copyStep": bot_face.COPY_STEP, "emptyNudge": bot_face.EMPTY_NUDGE},
        "neutral": dict(bot_face.NEUTRAL),
        "sprites": sprites,
        "shapeKeys": shape_keys,
    }
    bot_spec.FACE_JSON.parent.mkdir(parents=True, exist_ok=True)
    bot_spec.FACE_JSON.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build_scene():
    scene = bpy.context.scene
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 1.0
    collection = bpy.data.collections.new(bot_spec.EXPORT_COLLECTION)
    scene.collection.children.link(collection)

    palette = bot_spec.load_palette()
    atlas = bot_geo.Atlas(bot_spec.ATLAS_SIZE, palette)
    builder = bot_geo.Builder(atlas)
    visemes, mmd = bot_spec.spec_shape_names()
    keys = bot_face.shape_keys(visemes, mmd)
    depths = bot_model.build(builder, keys)

    rows = atlas.pack()
    colour, glow = atlas.render()
    bot_spec.TEXTURES.mkdir(parents=True, exist_ok=True)
    bot_geo.write_png(bot_spec.ATLAS_PNG, colour)
    bot_geo.write_png(bot_spec.EMISSION_PNG, np.repeat(glow[:, :, None], 3, axis=2))
    print(f"build_bot: atlas {atlas.size} x {atlas.size}, {len(atlas.islands)} islands, {rows} rows used")

    # The face apart from the rest: `Body` is every sprite solid, `Shell` every other.
    data = builder.collect(lambda solid: solid.sprite)
    shell_data = builder.collect(lambda solid: not solid.sprite)
    armature = make_armature(collection)
    materials = {name: make_material(name, hologram=name != bot_spec.MATERIALS[0]) for name in bot_spec.MATERIALS}
    body = make_mesh(bot_spec.MESH, data, atlas, armature, collection, materials)
    make_mesh(bot_spec.SHELL, shell_data, atlas, armature, collection, materials)
    make_shape_keys(body, data, keys, depths)
    write_face_json(atlas, keys, depths)
    print(f"build_bot: {builder.triangle_count()} triangles ({bot_spec.MESH} {sum(len(f) - 2 for f in data['faces'])}, "
          f"{bot_spec.SHELL} {sum(len(f) - 2 for f in shell_data['faces'])}), {len(data['vertices'])} + {len(shell_data['vertices'])} vertices, "
          f"{len(keys)} shape keys, {len(armature.data.bones)} bones")
    return scene


def main():
    args = parse_args()
    output = pathlib.Path(args.output).resolve() if args.output else bot_spec.BLEND_PATH
    guard_existing(output, args.force)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = build_scene()

    report = bot_validate.validate()
    report.print()
    if report.errors and not args.draft:
        raise SystemExit("build_bot: the model fails validation; nothing was saved")

    stamp.stamp(scene)
    print(f"build_bot: content digest {scene[bot_spec.cass_spec.GENERATED_DIGEST_PROP]}")
    output.parent.mkdir(parents=True, exist_ok=True)
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.wm.save_as_mainfile(filepath=str(output), compress=True)
    # The textures are referenced relative to the .blend, which only means something once it has a location.
    bpy.ops.file.make_paths_relative()
    bpy.ops.wm.save_mainfile(compress=True)
    print(f"build_bot: wrote {output}")


main()
