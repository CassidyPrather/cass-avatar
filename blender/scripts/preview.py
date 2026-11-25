"""Renders flat-lit preview PNGs of the open .blend so a headless session can be checked by eye.

    blender -b --factory-startup blender/cass.blend --python blender/scripts/preview.py -- --out DIR [options]

    --views front,side,back,quarter,face   which cameras to render (default: all five)
    --keys NAME=1,NAME=0.5                 shape key values on Body (bare NAME means 1)
    --each-key NAME,NAME | all             also render the face once per listed key, alone at 1 (key_NNN.png)
    --pose NAME[,NAME]                     render in a pose instead of the rest pose; several give one set of
                                           pictures each (rest, test, down, forward, raised, twist, reach, sit, walk, run, kick, knee);
                                           the skirt is then laid over the legs as its physics would lay it
    --shaded                               studio light instead of flat, to see how the surface shades
    --bare                                 leave the garments out and show the skin zones they hide
    --stiff                                pose the skirt as a build without its PhysBones holds it (Android, iOS)
    --tiles ID=0,ID=1                      override the default shown state of discard tiles
    --shot NAME:CX,CY,CZ:DX,DY,DZ:H        an extra view: centre, direction the camera looks from, frame height (repeatable)
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
    "quarterback": Vector((-0.7, 1.0, 0.25)),
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


def _arms(down=0.0, forward=0.0, elbow=0.0):
    """Both arms turned the same way: degrees down from the T-pose, forward, and bent at the elbow."""
    pose = {}
    for side, sign in (("L", 1.0), ("R", -1.0)):
        pose[f"UpperArm.{side}"] = (0, sign * down, -sign * forward)
        if elbow:
            pose[f"LowerArm.{side}"] = (0, 0, -sign * elbow)
    return pose


# Poses for looking at how the clothes and hair move: the same kind of table as TEST_POSE.
POSES = {
    "rest": {},
    "test": TEST_POSE,
    # How the avatar actually stands in VRChat: arms at the sides.
    "down": {**_arms(down=72.0), "Shoulder.L": (0, 6, 0), "Shoulder.R": (0, -6, 0)},
    "forward": _arms(down=10.0, forward=80.0),
    "raised": {**_arms(down=-65.0), "Shoulder.L": (0, -12, 0), "Shoulder.R": (0, 12, 0)},
    "twist": {**_arms(down=65.0, elbow=25.0), "Spine": (18, 0, 22), "Chest": (10, 8, 18), "Head": (0, 0, -20)},
    "sit": {**_arms(down=60.0, forward=20.0, elbow=40.0), "UpperLeg.L": (-88, 0, 0), "UpperLeg.R": (-88, 0, 0),
            "LowerLeg.L": (88, 0, 0), "LowerLeg.R": (88, 0, 0)},
    "walk": {**_arms(down=72.0), "UpperLeg.L": (-32, 0, 0), "LowerLeg.L": (18, 0, 0), "UpperLeg.R": (24, 0, 0),
             "LowerLeg.R": (30, 0, 0), "UpperArm.L": (0, 72, 25), "UpperArm.R": (0, -72, 25)},
    "run": {**_arms(down=60.0, elbow=80.0), "UpperLeg.L": (-58, 0, 0), "LowerLeg.L": (75, 0, 0), "UpperLeg.R": (22, 0, 0),
            "LowerLeg.R": (95, 0, 0)},
    "kick": {**_arms(down=40.0), "UpperLeg.L": (-105, 0, 0), "LowerLeg.L": (12, 0, 0), "UpperLeg.R": (8, 0, 0)},
    # Hands held out in front at chest height, elbows bent: where a headset wearer's arms spend their time.
    "reach": _arms(down=48.0, forward=42.0, elbow=75.0),
    # A knee brought up fast, as high as it goes.
    "knee": {**_arms(down=72.0), "UpperLeg.L": (-110, 0, 0), "LowerLeg.L": (115, 0, 0)},
}

# The skirt's PhysBone, as Unity sets it up (CassPrefabs, "skirt"): how thick a chain is, and how far its hinge lets a bone turn.
SKIRT_RADIUS = 0.03
SKIRT_LIMIT = 80.0
# Whether the skirt's chains are laid over the legs as their PhysBones would lay them. Off, the
# picture is of a build that leaves those out (Android and iOS; --stiff).
SKIRT_PHYSICS = True


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    parser = argparse.ArgumentParser(prog="preview.py", description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("--out", required=True)
    parser.add_argument("--views", default="front,side,back,quarter,face")
    parser.add_argument("--keys", default="")
    parser.add_argument("--each-key", default="")
    parser.add_argument("--pose", default="")
    parser.add_argument("--shaded", action="store_true")
    parser.add_argument("--bare", action="store_true")
    parser.add_argument("--stiff", action="store_true")
    parser.add_argument("--tiles", default="")
    parser.add_argument("--shot", action="append", default=[])
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


def apply_pose(pose):
    armature = next(o for o in export_objects() if o.type == "ARMATURE")
    for pose_bone in armature.pose.bones:
        pose_bone.matrix_basis = Matrix.Identity(4)
    for name, degrees in POSES[pose].items():
        pose_bone = armature.pose.bones[name]
        rest = pose_bone.bone.matrix_local
        pivot = Matrix.Translation(rest.translation)
        rotation = Euler([math.radians(d) for d in degrees], "XYZ").to_matrix().to_4x4()
        # The rotation is specified in armature space about the bone's head;
        # express it in the bone's rest frame, which is what matrix_basis expects.
        target = pivot @ rotation @ pivot.inverted() @ rest
        pose_bone.matrix_basis = rest.inverted() @ target
    bpy.context.view_layer.update()
    settle_skirt(armature)
    bpy.context.view_layer.update()


def _clear(point, capsules):
    """Whether a point of a chain is outside every collider, by the chain's own thickness."""
    for start, end, radius in capsules:
        along = end - start
        t = max(0.0, min(1.0, (point - start).dot(along) / along.length_squared))
        if (point - (start + along * t)).length < radius + SKIRT_RADIUS:
            return False
    return True


def _carried(armature, bone, follow, share):
    """Where a bone with `follow` (skeleton.json) stands in the pose: turned part of the way with its source."""
    parent = bone.parent
    source = armature.pose.bones[follow["source"]]
    resting = parent.bone.matrix_local.inverted() @ source.bone.matrix_local
    posed = parent.matrix.inverted() @ source.matrix
    turned = (posed @ resting.inverted()).to_quaternion()
    part = Matrix.Identity(4).to_quaternion().slerp(turned, share).to_matrix().to_4x4()
    own = parent.bone.matrix_local.inverted() @ bone.bone.matrix_local
    pivot = Matrix.Translation(own.translation)
    return parent.matrix @ pivot @ part @ pivot.inverted() @ own


def settle_skirt(armature):
    """Lays the skirt's chains over the posed legs, standing in for what Unity does to them.

    It is not a simulation. First the bones the front chains hang from are
    turned part of the way with the thighs, as their constraints turn them
    (skeleton.json, `follow`). Then each bone of a chain, from the waist
    down, hangs as near to how it hangs at rest as its hinge lets it, unless
    that puts it inside one of the skeleton spec's colliders; then it is
    turned outward on its hinge, a degree at a time, until it is clear or at
    its limit. That is where a hinged chain under gravity comes to rest on a
    leg, which is enough to see whether the cloth then covers the leg.

    With SKIRT_PHYSICS off the chains stay as they rest on what carries
    them, which is all a build without the skirt's PhysBones does.
    """
    skeleton = cass_spec.load_skeleton()
    roots = [entry for entry in skeleton["extra"] if entry.get("physics") == "skirt" and entry["name"] in armature.pose.bones]
    if not roots:
        return
    capsules = [(armature.pose.bones[entry["bone"]].head.copy(), armature.pose.bones[entry["to"]].head.copy(), entry["radius"])
                for entry in skeleton.get("colliders", []) if "skirt" in entry["physics"]]
    hips = armature.pose.bones["Hips"]
    for entry in roots:
        root = armature.pose.bones[entry["name"]]
        root.matrix_basis = Matrix.Identity(4)
        bpy.context.view_layer.update()
        root_matrix = root.matrix.copy()
        if "follow" in entry:
            follow = entry["follow"]
            root_matrix = _carried(armature, root, follow, follow["weight"] if SKIRT_PHYSICS else follow.get("weightAlone", follow["weight"]))
            root.matrix = root_matrix
            bpy.context.view_layer.update()
        for first in root.children:
            parent, parent_matrix = root, root_matrix
            bone = first
            while bone is not None:
                base = parent_matrix @ parent.bone.matrix_local.inverted() @ bone.bone.matrix_local
                if not SKIRT_PHYSICS:
                    bone.matrix_basis = Matrix.Identity(4)
                    parent, parent_matrix = bone, base
                    bone = bone.children[0] if bone.children else None
                    continue
                # The way the bone points at rest, carried with the hips, seen from where it now hangs.
                rest = (hips.matrix @ hips.bone.matrix_local.inverted() @ bone.bone.matrix_local).to_3x3() @ Vector((0.0, 1.0, 0.0))
                seen = base.to_3x3().inverted() @ rest
                hanging = max(-SKIRT_LIMIT, min(SKIRT_LIMIT, math.degrees(math.atan2(seen.z, seen.y))))
                angle = hanging
                while True:
                    matrix = base @ Matrix.Rotation(math.radians(angle), 4, "X")
                    if angle >= SKIRT_LIMIT or all(_clear(matrix @ Vector((0.0, bone.bone.length * t, 0.0)), capsules)
                                                   for t in (0.25, 0.5, 0.75, 1.0)):
                        break
                    angle = min(SKIRT_LIMIT, angle + 1.0)
                bone.matrix_basis = Matrix.Rotation(math.radians(angle), 4, "X")
                parent, parent_matrix = bone, matrix
                bone = bone.children[0] if bone.children else None


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


def setup_render(size, shaded=False):
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_WORKBENCH"
    shading = scene.display.shading
    # Flat light keeps the palette colours true; cavity shading and outlines carry the form.
    shading.light = "STUDIO" if shaded else "FLAT"
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
    global SKIRT_PHYSICS
    args = parse_args()
    SKIRT_PHYSICS = not args.stiff
    out = pathlib.Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    apply_discards(args.bare, args.tiles)
    set_keys(args.keys)
    camera = setup_render(args.size, args.shaded)
    poses = list(filter(None, args.pose.split(","))) or [None]
    for pose in poses:
        if pose:
            apply_pose(pose)
        posed = pose not in (None, "rest")
        lo, hi = bounds()
        tag = (f"_{pose}" if pose and len(poses) > 1 else "") + (f"_{args.tag}" if args.tag else "")
        for view in filter(None, args.views.split(",")):
            if view == "face":
                aim_at_face(camera, args.size)
            else:
                centre = Vector((0.0, 0.5 * (lo.y + hi.y) if posed else 0.0, 0.5 * (lo.z + hi.z)))
                height = (hi.z - lo.z) * 1.06
                # The T-pose is about as wide as it is tall; only the profile is narrow.
                aspect = (0.8 if posed else 0.5) if view == "side" else (0.7 if pose in ("down", "twist", "walk", "run") else 1.0)
                aim(camera, BODY_VIEWS[view], centre, height, aspect, args.size)
            render(out / f"{view}{tag}.png")

        for shot in args.shot:
            name, centre, direction, height = shot.split(":")
            aim(camera, Vector([float(c) for c in direction.split(",")]), Vector([float(c) for c in centre.split(",")]),
                float(height), 1.0, args.size)
            render(out / f"{name}{tag}.png")
    if poses != [None]:
        apply_pose("rest")

    names = [b.name for b in key_blocks()[1:]] if args.each_key == "all" else list(filter(None, args.each_key.split(",")))
    if names:
        aim_at_face(camera, args.size)
    for index, name in enumerate(names):
        for block in key_blocks():
            block.value = 0.0
        key_blocks()[name].value = 1.0
        # Indexed file names: the MMD key names are not safe in every shell.
        render(out / f"key_{index:03d}{tag}.png")


if __name__ == "__main__":
    main()
