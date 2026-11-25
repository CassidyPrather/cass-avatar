"""Measures how far one garment pokes out through the one worn over it, pose by pose.

    blender -b --factory-startup blender/cass.blend --python blender/scripts/poke.py -- [options]

    --pairs INNER:OUTER[,INNER:OUTER]   mesh names, default Outfit_Sweater:Outfit_Vest
    --pose NAME[,NAME]                  poses from preview.py (default: rest,down,forward,raised,twist,reach)
    --over MM                           what counts as poking out (default 0.5 mm)
    --cover M                           how deep under the outer mesh a vertex still counts as covered by it
                                        (default 0.03; legs under a full skirt need about 0.5)
    --stiff                             pose the skirt as a build without its PhysBones holds it

For every vertex of the inner mesh that the outer one covers at rest, the
distance it stands outside the outer surface in that pose. A vertex is covered
when it lies just under a face of the outer mesh, not beside its rim, so a
sleeve that leaves through an armhole is not counted, and neither is an arm
that comes to lie against the outside of a vest. The worst places are listed
with the bone that moves them most, which says whose weights to look at.
"""

import sys
import pathlib

sys.dont_write_bytecode = True
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import argparse

import bmesh
import bpy
from mathutils.bvhtree import BVHTree

import preview

REACH = 0.04      # how far from the outer surface an inner vertex is still looked at
COVER = 0.03      # how deep under the outer surface a vertex still counts as covered by it
ON_FACE = 0.8     # how squarely the nearest point has to face the vertex to be on a face and not the rim


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    parser = argparse.ArgumentParser(prog="poke.py", description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("--pairs", default="Outfit_Sweater:Outfit_Vest")
    parser.add_argument("--pose", default="rest,down,forward,raised,twist,reach")
    parser.add_argument("--over", type=float, default=0.5)
    parser.add_argument("--cover", type=float, default=COVER)
    parser.add_argument("--stiff", action="store_true")
    return parser.parse_args(argv)


def posed(obj):
    """The object's mesh as the armature leaves it, in world space."""
    depsgraph = bpy.context.evaluated_depsgraph_get()
    bm = bmesh.new()
    bm.from_object(obj, depsgraph)
    bm.transform(obj.matrix_world)
    bm.normal_update()
    return bm


def heaviest(obj, index):
    groups = obj.data.vertices[index].groups
    if not groups:
        return "-"
    return obj.vertex_groups[max(groups, key=lambda g: g.weight).group].name


def signed(inner, outer, reach):
    """Per inner vertex: how far outside the outer surface it is, or None where it faces no face of it."""
    inner_bm, outer_bm = posed(inner), posed(outer)
    tree = BVHTree.FromBMesh(outer_bm)
    result = []
    for vertex in inner_bm.verts:
        point, normal, _, distance = tree.find_nearest(vertex.co, reach)
        if point is None or distance < 1e-6 or abs((vertex.co - point).dot(normal)) / distance < ON_FACE:
            result.append((None, vertex.co.copy()))
        else:
            result.append(((vertex.co - point).dot(normal), vertex.co.copy()))
    inner_bm.free()
    outer_bm.free()
    return result


def measure(inner, outer, covered, over, reach):
    worst = [(outside, index, at) for index, (outside, at) in enumerate(signed(inner, outer, reach))
             if index in covered and outside is not None and outside * 1000.0 > over]
    return sorted(worst, reverse=True)


def main():
    args = parse_args()
    preview.SKIRT_PHYSICS = not args.stiff
    reach = max(REACH, args.cover)
    for pair in args.pairs.split(","):
        inner_name, outer_name = pair.split(":")
        inner, outer = bpy.data.objects[inner_name], bpy.data.objects[outer_name]
        preview.apply_pose("rest")
        covered = {index for index, (outside, _) in enumerate(signed(inner, outer, reach))
                   if outside is not None and -args.cover < outside < 0.0005}
        print(f"POKE {inner_name} under {outer_name}: {len(covered)} vertices covered at rest")
        for pose in args.pose.split(","):
            preview.apply_pose(pose)
            worst = measure(inner, outer, covered, args.over, reach)
            line = f"POKE {inner_name} through {outer_name} in {pose}: {len(worst)} vertices"
            if worst:
                line += f", worst {worst[0][0] * 1000:.1f} mm"
            print(line)
            for outside, index, at in worst[:6]:
                print(f"POKE   {outside * 1000:5.1f} mm at ({at.x:+.3f}, {at.y:+.3f}, {at.z:+.3f}) moved by {heaviest(inner, index)}")
    preview.apply_pose("rest")


main()
