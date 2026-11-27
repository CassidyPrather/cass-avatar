"""Renders review pictures of the meta figure into dist/meta-review/ (git-ignored).

    blender -b --factory-startup --python-exit-code 1 --python blender/meta/render_meta.py -- [--out DIR] [--only NAME[,NAME...]]

The pictures show the texture unlit, sampled nearest-neighbour as the game will, with a little
shading from the face normals so that the forms read; what glows is not shaded. The poses stand in
for what the game will do to the rig: arms down, pointing, a stride, sitting. `hues` shows the
signature colour turned to three other hues the way Unity is meant to do it, through the tint mask.
The .blend is not saved.
"""

import sys
import pathlib

sys.dont_write_bytecode = True
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import argparse
import math

import bpy
import numpy as np
from mathutils import Matrix, Vector

import meta_spec
import bot_geo
import meta_pose

BACKGROUND = (0.32, 0.36, 0.5)
LIGHT = Vector((-0.45, -0.65, 0.62)).normalized()
HUES = {"cyan": 0.0, "amber": -145.0 / 360.0, "rose": 150.0 / 360.0, "green": -60.0 / 360.0}


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    parser = argparse.ArgumentParser(prog="render_meta.py", description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("--out", default=str(meta_spec.REVIEW_DIR))
    parser.add_argument("--blend", default=str(meta_spec.BLEND_PATH))
    parser.add_argument("--only", default="", help="comma-separated picture groups (rest, idle, head, hands, point, walk, sit, reach, arms, hues); default all")
    parser.add_argument("--tag", default="", help="a suffix for the pictures' names, to keep a sheet from before a change beside the one after")
    return parser.parse_args(argv)


def review_material(body):
    """Rebuilds the material as unlit texture with a touch of shading by the face normal, the glow left
    unshaded, and the hue of the signature texels on a dial. Returns the dial (a Hue/Saturation node)."""
    material = body.material_slots[0].material
    tree = material.node_tree
    for node in list(tree.nodes):
        tree.nodes.remove(node)

    def texture(path):
        # From the file the build wrote, wherever the .blend remembers it to have been.
        node = tree.nodes.new("ShaderNodeTexImage")
        node.image = bpy.data.images.load(str(path), check_existing=False)
        node.interpolation = "Closest"
        return node

    colour, glow, tint = texture(meta_spec.ATLAS_PNG), texture(meta_spec.EMISSION_PNG), texture(meta_spec.TINT_PNG)
    for node in (glow, tint):
        node.image.colorspace_settings.name = "Non-Color"
    output = tree.nodes.new("ShaderNodeOutputMaterial")
    dial = tree.nodes.new("ShaderNodeHueSaturation")
    tree.links.new(colour.outputs["Color"], dial.inputs["Color"])
    tree.links.new(tint.outputs["Color"], dial.inputs["Fac"])
    geometry = tree.nodes.new("ShaderNodeNewGeometry")
    dot = tree.nodes.new("ShaderNodeVectorMath")
    dot.operation = "DOT_PRODUCT"
    dot.inputs[1].default_value = LIGHT
    shade = tree.nodes.new("ShaderNodeMapRange")
    shade.inputs["From Min"].default_value, shade.inputs["From Max"].default_value = -1.0, 1.0
    shade.inputs["To Min"].default_value, shade.inputs["To Max"].default_value = 0.6, 1.0
    # Where it glows the shade is 1.
    lift = tree.nodes.new("ShaderNodeMix")
    lift.data_type = "FLOAT"
    scale = tree.nodes.new("ShaderNodeVectorMath")
    scale.operation = "SCALE"
    emission = tree.nodes.new("ShaderNodeEmission")
    tree.links.new(geometry.outputs["Normal"], dot.inputs[0])
    tree.links.new(dot.outputs["Value"], shade.inputs["Value"])
    tree.links.new(glow.outputs["Color"], lift.inputs["Factor"])
    tree.links.new(shade.outputs["Result"], lift.inputs["A"])
    lift.inputs["B"].default_value = 1.0
    tree.links.new(dial.outputs["Color"], scale.inputs[0])
    tree.links.new(lift.outputs["Result"], scale.inputs["Scale"])
    tree.links.new(scale.outputs["Vector"], emission.inputs["Color"])
    tree.links.new(emission.outputs[0], output.inputs["Surface"])
    material.use_backface_culling = True
    return dial


def setup(scene):
    for engine in ("BLENDER_EEVEE", "BLENDER_EEVEE_NEXT"):
        try:
            scene.render.engine = engine
            break
        except TypeError:
            continue
    scene.view_settings.view_transform = "Standard"
    scene.render.film_transparent = False
    scene.render.filter_size = 0.6
    scene.render.image_settings.file_format = "PNG"
    world = bpy.data.worlds.new("Review")
    world.use_nodes = True
    background = next(node for node in world.node_tree.nodes if node.type == "BACKGROUND")
    background.inputs["Color"].default_value = (*BACKGROUND, 1.0)
    scene.world = world
    camera = bpy.data.objects.new("ReviewCamera", bpy.data.cameras.new("ReviewCamera"))
    scene.collection.objects.link(camera)
    scene.camera = camera
    return camera


def aim(camera, target, direction, width, lens=85.0):
    """Looks at `target` from along `direction`, far enough that `width` metres fill the picture's width."""
    scene = bpy.context.scene
    camera.data.lens = lens
    camera.data.sensor_fit = "HORIZONTAL"
    distance = width * lens / camera.data.sensor_width
    direction = Vector(direction).normalized()
    camera.location = Vector(target) + direction * distance
    camera.rotation_euler = (-direction).to_track_quat("-Z", "Y").to_euler()
    camera.data.clip_start, camera.data.clip_end = 0.01, 100.0
    scene.view_layers[0].update()


def turn(armature, name, axis, degrees):
    """Turns a pose bone about a world axis through its own joint. A pose is written as turns in the
    T-pose's own axes, fingertips first and shoulders last: a bone keeps its own turn when its parent
    is turned afterwards."""
    bpy.context.view_layer.update()
    bone = armature.pose.bones[name]
    pivot = bone.matrix.translation.copy()
    rotation = Matrix.Translation(pivot) @ Matrix.Rotation(math.radians(degrees), 4, Vector(axis)) @ Matrix.Translation(-pivot)
    bone.matrix = rotation @ bone.matrix
    bpy.context.view_layer.update()


def curl(armature, side, fingers, degrees, thumb=None):
    sign = 1.0 if side == "L" else -1.0
    for number in (3, 2, 1):
        for finger in fingers:
            turn(armature, f"{finger}{number}.{side}", (0.0, 1.0, 0.0), sign * degrees)
        if thumb is not None:
            turn(armature, f"Thumb{number}.{side}", (1.0, 0.0, 0.0), thumb)


def pose_rest(armature):
    for bone in armature.pose.bones:
        bone.matrix_basis = Matrix.Identity(4)
    bpy.context.view_layer.update()


def arm_down(armature, side, swing=0.0, forearm=-15.0, down=76.0):
    sign = 1.0 if side == "L" else -1.0
    curl(armature, side, ("Index", "Middle", "Ring", "Little"), 22, thumb=10)
    turn(armature, f"LowerArm.{side}", (0, 0, 1), forearm * sign)
    turn(armature, f"UpperArm.{side}", (0, 1, 0), down * sign)
    if swing:
        turn(armature, f"UpperArm.{side}", (1, 0, 0), swing)


def pose_idle(armature):
    pose_rest(armature)
    arm_down(armature, "L")
    arm_down(armature, "R")


def pose_point(armature):
    """The right arm raised and pointing ahead, the left at the side, the head turned a little."""
    pose_rest(armature)
    arm_down(armature, "L")
    curl(armature, "R", ("Middle", "Ring", "Little"), 82, thumb=30)
    turn(armature, "LowerArm.R", (0, 0, 1), 12)
    turn(armature, "UpperArm.R", (0, 0, 1), 68)
    turn(armature, "UpperArm.R", (1, 0, 0), -12)
    turn(armature, "HeadVisual", (0, 0, 1), -18)
    turn(armature, "Head", (0, 0, 1), -18)


def pose_walk(armature):
    pose_rest(armature)
    arm_down(armature, "L", swing=22)
    arm_down(armature, "R", swing=-22)
    turn(armature, "Toes.L", (1, 0, 0), -10)
    turn(armature, "LowerLeg.L", (1, 0, 0), 12)
    turn(armature, "UpperLeg.L", (1, 0, 0), -30)
    turn(armature, "LowerLeg.R", (1, 0, 0), 30)
    turn(armature, "UpperLeg.R", (1, 0, 0), 20)


def pose_sit(armature):
    pose_rest(armature)
    arm_down(armature, "L", forearm=-65, down=70)
    arm_down(armature, "R", forearm=-65, down=70)
    for side in "LR":
        turn(armature, f"LowerLeg.{side}", (1, 0, 0), 86)
        turn(armature, f"UpperLeg.{side}", (1, 0, 0), -86)


def pose_reach(armature):
    """One arm up, the other out in front, the head turned and bowed: the ends of what a player does."""
    pose_rest(armature)
    curl(armature, "L", ("Index", "Middle", "Ring", "Little"), 10, thumb=5)
    turn(armature, "LowerArm.L", (0, 1, 0), -25)
    turn(armature, "UpperArm.L", (0, 1, 0), -62)
    turn(armature, "LowerArm.R", (0, 0, 1), 35)
    turn(armature, "UpperArm.R", (0, 0, 1), 55)
    turn(armature, "UpperArm.R", (1, 0, 0), 25)
    for bone in ("HeadVisual", "Head"):
        turn(armature, bone, (1, 0, 0), -22)
        turn(armature, bone, (0, 0, 1), 55)


def render(scene, path, size):
    scene.render.resolution_x, scene.render.resolution_y = size
    scene.render.resolution_percentage = 100
    scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)


def read_png(path):
    image = bpy.data.images.load(str(path), check_existing=False)
    w, h = image.size
    pixels = np.array(image.pixels[:], dtype=np.float32).reshape(h, w, 4)[::-1, :, :3]
    bpy.data.images.remove(image)
    return (np.clip(pixels, 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8)


def sheet(paths, columns, target):
    tiles = [read_png(path) for path in paths]
    h, w = tiles[0].shape[:2]
    rows = (len(tiles) + columns - 1) // columns
    canvas = np.zeros((rows * h, columns * w, 3), dtype=np.uint8)
    for index, tile in enumerate(tiles):
        r, c = divmod(index, columns)
        canvas[r * h:(r + 1) * h, c * w:(c + 1) * w] = tile
    bot_geo.write_png(target, canvas)


FULL = (0, 0, 0.88)
SHOTS = {
    "front": (FULL, (0, -1, 0.03), 2.0), "back": (FULL, (0, 1, 0.03), 2.0), "side": (FULL, (1, 0, 0.03), 2.0),
    "three-quarter": (FULL, (-0.62, -1, 0.22), 2.0), "three-quarter-back": (FULL, (0.7, 1, 0.3), 2.0),
    "low": ((0, 0, 0.7), (-0.4, -1, -0.45), 2.0), "high": ((0, 0, 0.95), (0.35, -1, 0.9), 2.0),
}


def main():
    args = parse_args()
    out = pathlib.Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    only = {name for name in args.only.split(",") if name}
    bpy.ops.wm.open_mainfile(filepath=str(pathlib.Path(args.blend).resolve()))
    scene = bpy.context.scene
    armature, body = bpy.data.objects[meta_spec.ARMATURE], bpy.data.objects[meta_spec.MESH]
    dial = review_material(body)
    camera = setup(scene)
    size = (700, 700)

    def wanted(name):
        return not only or name in only

    def shots(prefix, names, columns):
        paths = []
        for name in names:
            target, direction, width = SHOTS[name]
            aim(camera, target, direction, width)
            path = out / "tiles" / f"{prefix}-{name}.png"
            render(scene, path, size)
            paths.append(path)
        sheet(paths, columns, out / f"{prefix}.png")

    def close(prefix, views, columns, tile=(700, 700)):
        paths = []
        for name, (target, direction, width) in views.items():
            aim(camera, target, direction, width)
            path = out / "tiles" / f"{prefix}-{name}.png"
            render(scene, path, tile)
            paths.append(path)
        sheet(paths, columns, out / f"{prefix}.png")

    if wanted("rest"):
        pose_rest(armature)
        shots("rest", ["front", "three-quarter", "side", "back", "three-quarter-back", "low"], 3)
    if wanted("idle"):
        pose_idle(armature)
        shots("idle", ["front", "three-quarter", "side", "back", "three-quarter-back", "high"], 3)
    if wanted("head"):
        pose_idle(armature)
        close("head", {"front": ((0, 0, 1.56), (0, -1, 0.0), 0.75), "three-quarter": ((0, 0, 1.56), (-0.6, -1, 0.15), 0.75),
                       "side": ((0, 0, 1.56), (1, -0.05, 0.05), 0.75), "back": ((0, 0, 1.5), (0.5, 1, 0.3), 0.85),
                       "under": ((0, 0, 1.56), (-0.3, -1, -0.5), 0.75), "above": ((0, 0, 1.56), (0.3, -1, 0.8), 0.75)}, 3)
    if wanted("hands"):
        pose_rest(armature)
        close("hands", {"back": ((0.72, 0, 1.345), (0.5, -1, 1.1), 0.42), "palm": ((0.72, 0, 1.33), (0.4, -1, -0.9), 0.42),
                        "cuff": ((0.66, 0, 1.33), (1, -0.35, 0.1), 0.42)}, 3)
    if wanted("point"):
        pose_point(armature)
        close("point", {"outside": (FULL, (-1, -0.75, 0.25), 2.0), "side": (FULL, (-1, -0.1, 0.03), 2.0),
                        "front": (FULL, (0.25, -1, 0.03), 2.0), "back": (FULL, (-0.6, 1, 0.3), 2.0),
                        "shoulder": ((-0.2, -0.05, 1.38), (-0.8, -1, 0.5), 0.8), "hand": ((-0.2, -0.62, 1.44), (-1, -0.9, 0.35), 0.5)}, 3)
    if wanted("walk"):
        pose_walk(armature)
        close("walk", {"side": (FULL, (1, -0.05, 0.03), 2.0), "three-quarter": (FULL, (-0.62, -1, 0.22), 2.0),
                       "front": (FULL, (0, -1, 0.03), 2.0), "back": (FULL, (0.5, 1, 0.2), 2.0)}, 4)
    if wanted("sit"):
        pose_sit(armature)
        close("sit", {"side": ((0, -0.2, 0.88), (1, -0.05, 0.03), 2.0), "three-quarter": ((0, -0.2, 0.88), (-0.62, -1, 0.22), 2.0),
                      "front": ((0, -0.2, 0.88), (0, -1, 0.1), 2.0), "back": ((0, -0.2, 0.88), (0.6, 1, 0.3), 2.0)}, 4)
    if wanted("reach"):
        pose_reach(armature)
        close("reach", {"front": (FULL, (0, -1, 0.03), 2.2), "three-quarter": (FULL, (-0.62, -1, 0.22), 2.2),
                        "back": (FULL, (0.5, 1, 0.2), 2.2), "head": ((0, 0, 1.52), (0.4, -1, 0.1), 0.9)}, 4)
    if wanted("arms"):
        # The ends of what arms do, a row to a pose: where cloth over the shoulders gives way.
        views = {"front": ((0, 0, 1.42), (0, -1, 0.05), 1.5), "front-high": ((0, 0, 1.42), (-0.6, -1, 0.7), 1.5),
                 "back": ((0, 0, 1.42), (0, 1, 0.05), 1.5), "back-high": ((0, 0, 1.42), (0.6, 1, 0.7), 1.5)}
        paths = []
        for name, left, right in meta_pose.SHEET:
            meta_pose.arms(armature, left, right)
            for view, (target, direction, width) in views.items():
                aim(camera, target, direction, width)
                path = out / "tiles" / f"arms{args.tag}-{name}-{view}.png"
                render(scene, path, (560, 560))
                paths.append(path)
        sheet(paths, len(views), out / f"arms{args.tag}.png")
    if wanted("hues"):
        pose_idle(armature)
        paths = []
        for name, shift in HUES.items():
            dial.inputs["Hue"].default_value = 0.5 + shift
            for view in ("three-quarter", "three-quarter-back"):
                target, direction, width = SHOTS[view]
                aim(camera, target, direction, width)
                path = out / "tiles" / f"hue-{name}-{view}.png"
                render(scene, path, size)
                paths.append(path)
        dial.inputs["Hue"].default_value = 0.5
        sheet(paths, 4, out / "hues.png")
    print(f"render_meta: wrote pictures to {out}")


main()
