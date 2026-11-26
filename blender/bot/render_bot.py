"""Renders review pictures of the bot into dist/bot-review/ (git-ignored).

    blender -b --factory-startup --python-exit-code 1 --python blender/bot/render_bot.py -- [--out DIR] [--only NAME[,NAME...]]

The pictures show the texture unlit, sampled nearest-neighbour as the game will, with a little
shading from the face normals so that the forms read. The hologram is added to what is behind it.
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

import bot_geo
import bot_spec

BACKGROUND = (0.105, 0.125, 0.235)
LIGHT = Vector((-0.45, -0.65, 0.62)).normalized()

FACES = {
    "neutral": {},
    "happy": {"eyes.happy": 1.0, "mouth.big-smile": 1.0},
    "sad": {"eyes.sad": 1.0, "mouth.frown": 1.0},
    "angry": {"eyes.angry": 1.0, "mouth.wavy": 1.0},
    "wide": {"eyes.wide": 1.0, "mouth.small-o": 1.0},
    "wink-left": {"eyes.wink-left": 1.0, "mouth.smile": 1.0},
    "wink-right": {"eyes.wink-right": 1.0, "mouth.tongue": 1.0},
    "hearts": {"eyes.hearts": 1.0, "mouth.cat": 1.0, "face.blush": 1.0},
    "sleepy": {"eyes.sleepy": 1.0, "mouth.pressed": 1.0},
    "smug": {"eyes.smug": 1.0, "mouth.smirk": 1.0},
    "crossed": {"eyes.crossed": 1.0, "mouth.wavy": 1.0},
    "dizzy": {"eyes.dizzy": 1.0, "mouth.medium-o": 1.0},
    "squeeze": {"eyes.squeeze": 1.0, "mouth.triangle": 1.0},
    "stars": {"eyes.stars": 1.0, "mouth.big-smile": 1.0},
    "dot": {"eyes.dot": 1.0, "mouth.narrow": 1.0},
    "cry": {"eyes.cry": 1.0, "mouth.frown": 1.0},
    "closed": {"eyes.closed": 1.0},
    "blink-keys": {"EyeClosedLeft": 1.0, "EyeClosedRight": 1.0},
    "lid-left": {"EyeClosedLeft": 1.0},
    "viseme-aa": {"vrc.v_aa": 1.0},
    "viseme-ih": {"vrc.v_ih": 1.0},
    "viseme-oh": {"vrc.v_oh": 1.0},
    "viseme-ou": {"vrc.v_ou": 1.0},
    "viseme-pp": {"vrc.v_pp": 1.0},
    "viseme-kk": {"vrc.v_kk": 1.0},
    "viseme-ff": {"vrc.v_ff": 1.0},
    "smile+aa": {"mouth.smile": 1.0, "eyes.happy": 1.0, "vrc.v_aa": 1.0},
    "half-aa-oh": {"vrc.v_aa": 0.5, "vrc.v_oh": 0.5},
    "mmd-a": {"あ": 1.0, "まばたき": 1.0},
    "mmd-wink": {"ウィンク": 1.0, "にっこり": 1.0},
    "blush": {"照れ": 1.0, "笑い": 1.0, "ω": 1.0},
    "bluescreen": {"face.bluescreen": 1.0},
}


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    parser = argparse.ArgumentParser(prog="render_bot.py", description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("--out", default=str(bot_spec.REVIEW_DIR))
    parser.add_argument("--blend", default=str(bot_spec.BLEND_PATH))
    parser.add_argument("--only", default="", help="comma-separated picture names; default all")
    return parser.parse_args(argv)


def review_materials(shell):
    """Rebuilds both materials as unlit texture with a touch of shading by the face normal."""
    for slot in shell.material_slots:
        hologram = slot.material.name != bot_spec.MATERIALS[0]
        tree = slot.material.node_tree
        image = next(node.image for node in tree.nodes if node.type == "TEX_IMAGE" and node.image.colorspace_settings.name != "Non-Color")
        for node in list(tree.nodes):
            tree.nodes.remove(node)
        output = tree.nodes.new("ShaderNodeOutputMaterial")
        texture = tree.nodes.new("ShaderNodeTexImage")
        texture.image, texture.interpolation = image, "Closest"
        emission = tree.nodes.new("ShaderNodeEmission")
        if hologram:
            clear = tree.nodes.new("ShaderNodeBsdfTransparent")
            add = tree.nodes.new("ShaderNodeAddShader")
            emission.inputs["Strength"].default_value = 0.85
            tree.links.new(texture.outputs["Color"], emission.inputs["Color"])
            tree.links.new(emission.outputs[0], add.inputs[0])
            tree.links.new(clear.outputs[0], add.inputs[1])
            tree.links.new(add.outputs[0], output.inputs["Surface"])
            slot.material.surface_render_method = "BLENDED"
            slot.material.use_backface_culling = True
            continue
        geometry = tree.nodes.new("ShaderNodeNewGeometry")
        dot = tree.nodes.new("ShaderNodeVectorMath")
        dot.operation = "DOT_PRODUCT"
        dot.inputs[1].default_value = LIGHT
        shade = tree.nodes.new("ShaderNodeMapRange")
        shade.inputs["From Min"].default_value, shade.inputs["From Max"].default_value = -1.0, 1.0
        shade.inputs["To Min"].default_value, shade.inputs["To Max"].default_value = 0.66, 1.0
        mix = tree.nodes.new("ShaderNodeVectorMath")
        mix.operation = "SCALE"
        tree.links.new(geometry.outputs["Normal"], dot.inputs[0])
        tree.links.new(dot.outputs["Value"], shade.inputs["Value"])
        tree.links.new(texture.outputs["Color"], mix.inputs[0])
        tree.links.new(shade.outputs["Result"], mix.inputs["Scale"])
        tree.links.new(mix.outputs["Vector"], emission.inputs["Color"])
        tree.links.new(emission.outputs[0], output.inputs["Surface"])
        slot.material.use_backface_culling = True


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
    """Turns a pose bone about a world axis through its own joint.

    A pose is written as turns in the T-pose's own axes, fingertips first and shoulders last: a
    bone keeps its own turn when its parent is turned afterwards, so each axis can be read off
    the T-pose (Y bends a finger or raises an arm, Z swings a forearm forward)."""
    bpy.context.view_layer.update()
    bone = armature.pose.bones[name]
    pivot = bone.matrix.translation.copy()
    rotation = Matrix.Translation(pivot) @ Matrix.Rotation(math.radians(degrees), 4, Vector(axis)) @ Matrix.Translation(-pivot)
    bone.matrix = rotation @ bone.matrix
    bpy.context.view_layer.update()


def curl(armature, side, fingers, degrees, thumb=None):
    """Bends every joint of the named fingers towards the palm, and the thumb across it."""
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


def pose_demo(armature):
    """The avatar's right arm down with a fist, its left hand raised open in a wave, a step, and a tilt of the head."""
    pose_rest(armature)
    curl(armature, "R", ("Index", "Middle", "Ring", "Little"), 80, thumb=28)
    turn(armature, "LowerArm.R", (0, 0, 1), 30)
    turn(armature, "UpperArm.R", (0, 1, 0), -74)
    for finger, spread in (("Index", -10), ("Ring", 8), ("Little", 18)):
        turn(armature, f"{finger}1.L", (0, 0, 1), spread)
    turn(armature, "Thumb1.L", (0, 0, 1), -20)
    turn(armature, "Hand.L", (1, 0, 0), -80)
    turn(armature, "LowerArm.L", (0, 1, 0), -58)
    turn(armature, "UpperArm.L", (0, 1, 0), -30)
    turn(armature, "Ear.L.001", (0, 1, 0), 22)
    turn(armature, "Ear.R", (0, 1, 0), -10)
    turn(armature, "Head", (0, 1, 0), 9)
    turn(armature, "Head", (0, 0, 1), 14)
    turn(armature, "Chest", (0, 0, 1), -6)
    turn(armature, "Toes.L", (1, 0, 0), -20)
    turn(armature, "LowerLeg.L", (1, 0, 0), 45)
    turn(armature, "UpperLeg.L", (1, 0, 0), -30)
    turn(armature, "UpperLeg.R", (1, 0, 0), 10)
    turn(armature, "Tail", (1, 0, 0), -20)


def pose_arms_down(armature):
    pose_rest(armature)
    for side, sign in (("L", 1.0), ("R", -1.0)):
        curl(armature, side, ("Index", "Middle", "Ring", "Little"), 20, thumb=10)
        turn(armature, f"LowerArm.{side}", (0, 0, 1), -15 * sign)
        turn(armature, f"UpperArm.{side}", (0, 1, 0), 76 * sign)


def set_face(body, values):
    for block in body.data.shape_keys.key_blocks[1:]:
        block.value = values.get(block.name, 0.0)


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


def main():
    args = parse_args()
    out = pathlib.Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    only = {name for name in args.only.split(",") if name}
    bpy.ops.wm.open_mainfile(filepath=str(pathlib.Path(args.blend).resolve()))
    scene = bpy.context.scene
    armature, body = bpy.data.objects[bot_spec.ARMATURE], bpy.data.objects[bot_spec.MESH]
    review_materials(bpy.data.objects[bot_spec.SHELL])
    camera = setup(scene)
    face = bot_spec.load_face()
    cx, cy, cz = face["screen"]["centreBlender"]

    def wanted(name):
        return not only or name in only

    body_shots = {
        "front": ((0, 0, 0.93), (0, -1, 0.03), 2.1), "back": ((0, 0, 0.93), (0, 1, 0.03), 2.1),
        "side": ((0, 0, 0.93), (1, 0, 0.03), 2.1), "three-quarter": ((0, 0, 0.93), (-0.62, -1, 0.22), 2.1),
        "three-quarter-back": ((0, 0, 0.93), (0.7, 1, 0.3), 2.1), "top": ((0, 0, 1.3), (0.2, -0.6, 1), 1.6),
        "below": ((0, 0, 0.7), (-0.4, -1, -0.75), 2.0),
    }
    pose_rest(armature)
    set_face(body, {})
    for name, (target, direction, width) in body_shots.items():
        if wanted(name):
            aim(camera, target, direction, width)
            render(scene, out / f"{name}.png", (900, 900))
    if wanted("head"):
        aim(camera, (0, 0, 1.42), (-0.5, -1, 0.15), 0.85)
        render(scene, out / "head.png", (900, 900))
    if wanted("head-back"):
        aim(camera, (0, 0, 1.42), (0.6, 1, 0.25), 0.85)
        render(scene, out / "head-back.png", (900, 900))
    if wanted("head-side"):
        aim(camera, (0, 0, 1.42), (1, -0.08, 0.05), 0.85)
        render(scene, out / "head-side.png", (900, 900))
    if wanted("hand"):
        aim(camera, (0.63, 0, 1.03), (0.5, -1, 1.1), 0.36)
        render(scene, out / "hand.png", (900, 700))
        aim(camera, (0.63, 0, 1.02), (0.4, -1, -0.9), 0.36)
        render(scene, out / "hand-palm.png", (900, 700))

    if wanted("faces"):
        paths = []
        for name, values in FACES.items():
            set_face(body, values)
            aim(camera, (cx, cy, cz + 0.02), (0, -1, 0), 0.44)
            path = out / "faces" / f"{name}.png"
            render(scene, path, (360, 300))
            paths.append(path)
        sheet(paths, 6, out / "faces.png")
        set_face(body, {"eyes.happy": 1.0, "mouth.big-smile": 1.0})
        aim(camera, (0, 0, 1.36), (-0.75, -1, 0.3), 0.6)
        render(scene, out / "face-happy.png", (900, 900))
        set_face(body, {"eyes.hearts": 1.0, "mouth.cat": 1.0, "face.blush": 1.0})
        aim(camera, (0, 0, 1.36), (0.4, -1, -0.1), 0.6)
        render(scene, out / "face-hearts.png", (900, 900))
        set_face(body, {"face.bluescreen": 1.0})
        aim(camera, (0, 0, 1.36), (0.2, -1, 0.1), 0.6)
        render(scene, out / "face-bluescreen.png", (900, 900))
        set_face(body, {})

    if wanted("posed"):
        pose_demo(armature)
        set_face(body, {"eyes.wink-left": 1.0, "mouth.big-smile": 1.0})
        aim(camera, (0, 0, 0.95), (-0.5, -1, 0.2), 2.1)
        render(scene, out / "posed.png", (900, 900))
        aim(camera, (0, 0, 0.95), (0.8, 1, 0.3), 2.1)
        render(scene, out / "posed-back.png", (900, 900))
        aim(camera, (-0.2, -0.1, 0.56), (-1, -0.75, 0.2), 0.4)
        render(scene, out / "posed-fist.png", (900, 700))
        aim(camera, (0.4, -0.02, 1.36), (0.25, -1, 0.15), 0.5)
        render(scene, out / "posed-open-hand.png", (900, 700))
    if wanted("arms-down"):
        pose_arms_down(armature)
        set_face(body, {"mouth.smile": 1.0})
        aim(camera, (0, 0, 0.93), (-0.35, -1, 0.12), 2.1)
        render(scene, out / "arms-down.png", (900, 900))
        aim(camera, (0, 0, 0.93), (1, -0.1, 0.05), 2.1)
        render(scene, out / "arms-down-side.png", (900, 900))
    print(f"render_bot: wrote pictures to {out}")


main()
