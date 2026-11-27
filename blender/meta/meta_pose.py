"""Poses of the meta figure's arms, as turns of bones, for the review sheets and the validator.

A pose is a list of (bone, axis, degrees): turns about a world axis through the bone's own joint,
applied in order, written for the left side. `.L` and `.R` in a bone's name are swapped for the
right side and turns about Y and Z change sign there. A parent is turned before its child.

The poses are the ends of what a player's arms do, which is where cloth over the shoulders fails:
the arm coming through the mantle, or the mantle through the hood.
"""

import math

import bpy
from mathutils import Matrix, Vector

X, Y, Z = (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)

# Turns for the left arm. About Y, negative raises it; about Z, negative brings it forward.
ARMS = {
    "up": [("UpperArm.L", Y, -85.0)],
    "high": [("UpperArm.L", Y, -45.0)],
    "head": [("UpperArm.L", Y, -65.0), ("UpperArm.L", Z, -15.0), ("LowerArm.L", Y, -85.0)],
    "t": [],
    "forward": [("UpperArm.L", Z, -85.0)],
    "forward-up": [("UpperArm.L", Z, -85.0), ("UpperArm.L", X, -40.0)],
    "face": [("UpperArm.L", Z, -95.0), ("UpperArm.L", X, -35.0), ("LowerArm.L", Z, -60.0)],
    "shrug": [("Shoulder.L", Y, -20.0), ("UpperArm.L", Y, -70.0)],
    "crossed": [("UpperArm.L", Y, 72.0), ("UpperArm.L", X, -30.0), ("LowerArm.L", Y, 108.0), ("LowerArm.L", Z, 20.0)],
    "down": [("UpperArm.L", Y, 76.0), ("LowerArm.L", Z, -15.0)],
    "back": [("UpperArm.L", Y, 60.0), ("UpperArm.L", X, 40.0)],
}

# What the validator tries, both arms alike.
CHECKED = ("up", "high", "head", "shrug", "t", "forward", "forward-up", "face", "crossed", "down", "back")

# The sheet: (name, the left arm's pose, the right arm's pose).
SHEET = (
    ("up", "up", "up"),
    ("head", "head", "head"),
    ("t", "t", "t"),
    ("forward", "forward", "forward"),
    ("crossed", "crossed", "crossed"),
    ("up-down", "up", "down"),
)


def rest(armature):
    for bone in armature.pose.bones:
        bone.matrix_basis = Matrix.Identity(4)
    bpy.context.view_layer.update()


def turn(armature, name, axis, degrees):
    bpy.context.view_layer.update()
    bone = armature.pose.bones[name]
    pivot = bone.matrix.translation.copy()
    rotation = Matrix.Translation(pivot) @ Matrix.Rotation(math.radians(degrees), 4, Vector(axis)) @ Matrix.Translation(-pivot)
    bone.matrix = rotation @ bone.matrix
    bpy.context.view_layer.update()


def arm(armature, side, pose):
    """Puts one arm in a pose of ARMS."""
    for name, axis, degrees in ARMS[pose]:
        if side == "R":
            name = name.replace(".L", ".R")
            if axis != X:
                degrees = -degrees
        turn(armature, name, axis, degrees)


def arms(armature, left, right):
    rest(armature)
    arm(armature, "L", left)
    arm(armature, "R", right)
