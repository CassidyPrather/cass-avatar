"""Renders flat-lit preview PNGs of the open .blend so a headless session can be checked by eye.

    blender -b --factory-startup blender/cass.blend --python blender/scripts/preview.py -- --out DIR [options]

    --views front,side,back,quarter,face   which cameras to render (default: all five)
    --keys NAME=1,NAME=0.5                 shape key values on Body (bare NAME means 1)
    --each-key NAME,NAME | all             also render the face once per listed key, alone at 1 (key_NNN.png)
    --pose test                            rotate arm, leg, finger and ear bones to exercise the skinning
    --bare                                 leave the garments out and show the skin zones they hide
    --tiles ID=0,ID=1                      override the default shown state of discard tiles
    --tag TEXT                             appended to the output file names
    --size N                               image height in pixels (default 1000)

Blender has no UDIM discard, so the script mimics Unity's default state on a
throwaway copy of the scene: faces on tiles with `shown: false` are deleted,
and so are the skin zones hidden by garments that are present. Nothing is saved.
"""

import sys
import pathlib

sys.dont_write_bytecode = True
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import argparse
import math

import bmesh
import bpy
from mathutils import Euler, Matrix, Vector

import cass_spec

# name -> (direction the camera looks from, frame centre z as a fraction of height, frame height fraction)
BODY_VIEWS = {
    "front": Vector((0.0, -1.0, 0.0)),
    "side": Vector((1.0, 0.0, 0.0)),
    "back": Vector((0.0, 1.0, 0.0)),
    "quarter": Vector((0.7, -1.0, 0.25)),
}

# Armature-space rotations (degrees about X, Y, Z) for the skinning test pose.
TEST_POSE = {
    "UpperArm.L": (0, 55, 0), "LowerArm.L": (0, 0, -80), "Hand.L": (0, 30, 0),
    "UpperArm.R": (0, -20, 35), "LowerArm.R": (0, 0, 100),
    "Index1.R": (0, -50, 0), "Index2.R": (0, -60, 0), "Index3.R": (0, -40, 0),
    "Middle1.R": (0, -70, 0), "Middle2.R": (0, -80, 0), "Ring1.R": (0, -70, 0), "Little1.R": (0, -70, 0),
    "Thumb1.R": (0, 0, 30),
    "UpperLeg.L": (-70, 0, 0), "LowerLeg.L": (80, 0, 0), "Foot.L": (-20, 0, 0),
    "UpperLeg.R": (15, -12, 0),
    "Spine": (0, 0, 12), "Chest": (8, 0, 0), "Head": (0, 12, -25), "Neck": (0, 0, -10),
    "Ear1.L": (25, 15, 0), "Ear2.L": (25, 15, 0), "Ear3.L": (25, 0, 0), "Ear1.R": (-20, -30, 0), "Ear2.R": (-20, -20, 0),
}


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    parser = argparse.ArgumentParser(prog="preview.py", description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("--out", required=True)
    parser.add_argument("--views", default="front,side,back,quarter,face")
    parser.add_argument("--keys", default="")
    parser.add_argument("--each-key", default="")
    parser.add_argument("--pose", choices=["test"])
    parser.add_argument("--bare", action="store_true")
    parser.add_argument("--tiles", default="")
    parser.add_argument("--tag", default="")
    parser.add_argument("--size", type=int, default=1000)
    return parser.parse_args(argv)


def export_objects():
    return list(bpy.data.collections[cass_spec.EXPORT_COLLECTION].all_objects)


def face_tiles(mesh, tiles):
    """Tile id per polygon, read from the first loop of the Tile UV layer."""
    by_cell = {(t["column"], t["row"]): t["id"] for t in tiles["tiles"]}
    layer = mesh.uv_layers[cass_spec.UV_TILE].data
    return [by_cell.get(tuple(int(math.floor(c)) for c in layer[p.loop_start].uv)) for p in mesh.polygons]


def apply_discards(bare, overrides):
    tiles = cass_spec.load_tiles()
    for item in filter(None, overrides.split(",")):
        tile, _, shown = item.partition("=")
        tiles["by_id"][tile]["shown"] = shown != "0"
    meshes = [o for o in export_objects() if o.type == "MESH"]
    if bare:
        for obj in [o for o in meshes if o.name.startswith("Outfit_")]:
            bpy.data.objects.remove(obj)
        meshes = [o for o in export_objects() if o.type == "MESH"]
    per_object = {obj.name: face_tiles(obj.data, tiles) for obj in meshes}
    present = {tile for ids in per_object.values() for tile in ids}
    hidden = {t["id"] for t in tiles["tiles"] if not t["shown"]}
    for tile in tiles["tiles"]:
        if tile["id"] in present and tile["shown"]:
            hidden.update(tile.get("hides", []))
    for obj in meshes:
        doomed = [i for i, tile in enumerate(per_object[obj.name]) if tile in hidden]
        if not doomed:
            continue
        bm = bmesh.new()
        bm.from_mesh(obj.data)
        bm.faces.ensure_lookup_table()
        bmesh.ops.delete(bm, geom=[bm.faces[i] for i in doomed], context="FACES")
        bm.to_mesh(obj.data)
        bm.free()


def key_blocks():
    return bpy.data.objects[cass_spec.load_blendshapes()["mesh"]].data.shape_keys.key_blocks


def set_keys(spec):
    for item in filter(None, spec.split(",")):
        name, _, value = item.partition("=")
        key_blocks()[name].value = float(value) if value else 1.0


def apply_test_pose():
    armature = next(o for o in export_objects() if o.type == "ARMATURE")
    for name, degrees in TEST_POSE.items():
        pose_bone = armature.pose.bones[name]
        rest = pose_bone.bone.matrix_local
        pivot = Matrix.Translation(rest.translation)
        rotation = Euler([math.radians(d) for d in degrees], "XYZ").to_matrix().to_4x4()
        # The rotation is specified in armature space about the bone's head;
        # express it in the bone's rest frame, which is what matrix_basis expects.
        target = pivot @ rotation @ pivot.inverted() @ rest
        pose_bone.matrix_basis = rest.inverted() @ target
    bpy.context.view_layer.update()


def bounds():
    depsgraph = bpy.context.evaluated_depsgraph_get()
    lo, hi = Vector((1e9,) * 3), Vector((-1e9,) * 3)
    for obj in export_objects():
        if obj.type != "MESH":
            continue
        evaluated = obj.evaluated_get(depsgraph)
        for v in evaluated.data.vertices:
            co = evaluated.matrix_world @ v.co
            lo = Vector(map(min, lo, co))
            hi = Vector(map(max, hi, co))
    return lo, hi


def setup_render(size):
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_WORKBENCH"
    shading = scene.display.shading
    # Flat light keeps the palette colours true; cavity shading and outlines carry the form.
    shading.light = "FLAT"
    shading.color_type = "TEXTURE"
    shading.show_shadows = False
    shading.show_cavity = True
    shading.cavity_type = "BOTH"
    shading.cavity_ridge_factor = 0.0
    shading.cavity_valley_factor = 1.5
    shading.curvature_ridge_factor = 0.0
    shading.curvature_valley_factor = 1.0
    shading.show_object_outline = True
    shading.object_outline_color = (0.15, 0.1, 0.08)
    shading.show_backface_culling = True
    shading.show_specular_highlight = False
    scene.display.render_aa = "8"
    scene.view_settings.view_transform = "Standard"
    scene.render.film_transparent = False
    scene.world = bpy.data.worlds.new("PreviewWorld")
    scene.world.color = (0.62, 0.66, 0.72)
    scene.render.image_settings.file_format = "PNG"
    camera = bpy.data.objects.new("PreviewCamera", bpy.data.cameras.new("PreviewCamera"))
    scene.collection.objects.link(camera)
    camera.data.type = "ORTHO"
    scene.camera = camera
    return camera


def aim(camera, direction, centre, height, aspect, size):
    scene = bpy.context.scene
    scene.render.resolution_y = size
    scene.render.resolution_x = int(size * aspect)
    camera.data.ortho_scale = height * max(1.0, aspect)
    camera.location = centre + direction.normalized() * 5.0
    camera.rotation_euler = (-direction).to_track_quat("-Z", "Y").to_euler()


def aim_at_face(camera, size):
    # The face is centred roughly a hand's width above the head bone's pivot at the jaw.
    head = bpy.data.objects[cass_spec.load_skeleton()["armature"]].data.bones[cass_spec.load_skeleton()["humanoid"]["Head"]]
    aim(camera, Vector((0.0, -1.0, 0.0)), Vector((0.0, 0.0, head.head_local.z + 0.095)), 0.30, 1.0, size)


def render(path):
    bpy.context.scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)
    print(f"preview: wrote {path}")


def main():
    args = parse_args()
    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    apply_discards(args.bare, args.tiles)
    set_keys(args.keys)
    if args.pose:
        apply_test_pose()
    camera = setup_render(args.size)
    lo, hi = bounds()
    tag = f"_{args.tag}" if args.tag else ""
    for view in filter(None, args.views.split(",")):
        if view == "face":
            aim_at_face(camera, args.size)
        else:
            centre = Vector((0.0, 0.0, 0.5 * (lo.z + hi.z)))
            height = (hi.z - lo.z) * 1.06
            # The T-pose is about as wide as it is tall; only the profile is narrow.
            aspect = (0.8 if args.pose else 0.5) if view == "side" else 1.0
            aim(camera, BODY_VIEWS[view], centre, height, aspect, args.size)
        render(out / f"{view}{tag}.png")

    names = [b.name for b in key_blocks()[1:]] if args.each_key == "all" else list(filter(None, args.each_key.split(",")))
    if names:
        aim_at_face(camera, args.size)
    for index, name in enumerate(names):
        for block in key_blocks():
            block.value = 0.0
        key_blocks()[name].value = 1.0
        # Indexed file names: the MMD key names are not safe in every shell.
        render(out / f"key_{index:03d}{tag}.png")


main()
