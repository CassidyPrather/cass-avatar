"""The shared armature: the SiroinoSotai skeleton under the names of Spec/skeleton.json.

The body base's bones are kept where its author put them (including the arm
twist bones, which Unity drives with rotation constraints). Its breast bones
are folded into the chest. Everything the head and the modelled parts need is
added on top by `add_bones`.
"""

import bpy
from mathutils import Vector

FINGERS = ("Thumb", "Index", "Middle", "Ring", "Little")
SEGMENTS = {"Proximal": "1", "Intermediate": "2", "Distal": "3"}

# Bones of the body base that the avatar does not keep, and the bone that takes their weights.
FOLDED = {"Breast_Root": "Chest", "Breast_L": "Chest", "Breast_R": "Chest", "Breast_L_end": "Chest", "Breast_R_end": "Chest"}


def spec_name(source):
    """SiroinoSotai bone name -> skeleton.json bone name."""
    if "_" not in source:
        return source
    stem, side = source.rsplit("_", 1)
    if side not in ("L", "R"):
        return source
    for finger in FINGERS:
        for segment, number in SEGMENTS.items():
            if stem == finger + segment:
                return f"{finger}{number}.{side}"
    stem = {"Toe": "Toes", "UpperArm_Twist": "UpperArmTwist", "LowerArm_Twist": "LowerArmTwist"}.get(stem, stem)
    return f"{stem}.{side}"


def adopt(armature, name, collection):
    """Renames the body base's armature and its bones in place and drops the folded bones."""
    armature.name = armature.data.name = name
    for other in list(armature.users_collection):
        other.objects.unlink(armature)
    collection.objects.link(armature)
    bpy.context.view_layer.objects.active = armature
    bpy.ops.object.mode_set(mode="EDIT")
    bones = armature.data.edit_bones
    for source in FOLDED:
        if source in bones:
            bones.remove(bones[source])
    for bone in list(bones):
        bone.name = spec_name(bone.name)
        bone.use_deform = True
        bone.use_connect = False
    bpy.ops.object.mode_set(mode="OBJECT")
    return armature


def rename_groups(obj):
    """Gives a mesh skinned to the body base the same names, folding dropped bones into their target."""
    for group in list(obj.vertex_groups):
        if group.name in FOLDED:
            target = obj.vertex_groups.get(FOLDED[group.name]) or obj.vertex_groups.new(name=FOLDED[group.name])
            for vertex in obj.data.vertices:
                for element in vertex.groups:
                    if element.group == group.index and element.weight > 0.0:
                        target.add([vertex.index], element.weight, "ADD")
            obj.vertex_groups.remove(group)
    for group in obj.vertex_groups:
        group.name = spec_name(group.name)


def add_bones(armature, bones):
    """Adds deform bones. `bones` is a list of (name, head, tail, parent, roll axis)."""
    bpy.context.view_layer.objects.active = armature
    bpy.ops.object.mode_set(mode="EDIT")
    edit = armature.data.edit_bones
    for name, head, tail, parent, roll in bones:
        bone = edit.new(name)
        bone.head, bone.tail = Vector(head), Vector(tail)
        bone.align_roll(Vector(roll))
        bone.use_deform = True
        bone.parent = edit[parent]
        bone.use_connect = False
    bpy.ops.object.mode_set(mode="OBJECT")


def move_tail(armature, name, tail):
    bpy.context.view_layer.objects.active = armature
    bpy.ops.object.mode_set(mode="EDIT")
    armature.data.edit_bones[name].tail = Vector(tail)
    bpy.ops.object.mode_set(mode="OBJECT")


def head_of(armature, name):
    return armature.data.bones[name].head_local.copy()


def tail_of(armature, name):
    return armature.data.bones[name].tail_local.copy()
