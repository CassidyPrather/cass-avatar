"""The shared armature and the skin-weight field that every body-hugging mesh samples.

Bone names come from Spec/skeleton.json; this module only decides where the
joints sit. Weights are a function of rest position, so the body and the
garments over it get the same weights at the same place and deform together
instead of poking through each other.
"""

import bpy

from .face import eye_pivot
from .meshkit import add, lerp, limit_weights, normalized, scale, smoothstep

FINGERS = ("Thumb", "Index", "Middle", "Ring", "Little")
FRONT = (0.0, -1.0, 0.0)
UP = (0.0, 0.0, 1.0)


def finger_points(L, name):
    """Head positions of a left finger's three bones and its tip."""
    if name == "Thumb":
        _, _, length = L.thumb
        base, direction = L.thumb_base, normalized(L.thumb_dir)
    else:
        _, y, _, length = next(f for f in L.fingers if f[0] == name)
        base, direction = (L.knuckle_x - 0.004, L.arm_y + y, L.arm_z), (1.0, 0.0, 0.0)
    j1, j2 = L.finger_joints
    return [add(base, scale(direction, length * f)) for f in (0.0, j1, j2, 1.0)]


def ear_points(L):
    """Head positions of the left ear's three bones and the ear tip."""
    direction = normalized(L.ear_dir)
    start = 0.035
    step = (L.ear_len - start) / 3.0
    return [add(L.ear_root, scale(direction, start + step * i)) for i in range(4)]


def bone_table(L):
    """name -> (head, tail, parent, roll reference axis), both sides."""
    head_pivot = (0.0, 0.010, L.chin_z + 0.020)
    spine = (0.0, 0.008, L.hip_z + 0.12)
    chest = (0.0, 0.006, L.hip_z + 0.30)
    neck = (0.0, 0.012, L.neck_base_z)
    bones = {
        "Hips": ((0.0, 0.010, L.hip_z + 0.03), spine, None, FRONT),
        "Spine": (spine, chest, "Hips", FRONT),
        "Chest": (chest, neck, "Spine", FRONT),
        "Neck": (neck, head_pivot, "Chest", FRONT),
        "Head": (head_pivot, (0.0, 0.010, L.crown_z), "Neck", FRONT),
    }
    # Knees sit a hair forward and elbows a hair back of the straight line so
    # IK solvers know which way the joints fold.
    shoulder = (L.shoulder_x, L.arm_y, L.arm_z)
    elbow = (L.elbow_x, L.arm_y + 0.004, L.arm_z)
    wrist = (L.wrist_x, L.arm_y, L.arm_z)
    hip = (L.hip_x, 0.0, L.hip_z)
    knee = (L.hip_x, -0.004, L.knee_z)
    ankle = (L.hip_x, 0.004, L.ankle_z)
    toes = (L.hip_x, L.toe_joint_y, L.lift + 0.004)
    eye = eye_pivot(L)
    left = {
        "Eye": (eye, (eye[0], eye[1] - 0.030, eye[2]), "Head", UP),
        "Shoulder": ((0.025, 0.012, L.arm_z + 0.030), shoulder, "Chest", UP),
        "UpperArm": (shoulder, elbow, "Shoulder", UP),
        "LowerArm": (elbow, wrist, "UpperArm", UP),
        "Hand": (wrist, (L.wrist_x + 0.07, L.arm_y, L.arm_z), "LowerArm", UP),
        "UpperLeg": (hip, knee, "Hips", FRONT),
        "LowerLeg": (knee, ankle, "UpperLeg", FRONT),
        "Foot": (ankle, toes, "LowerLeg", UP),
        "Toes": (toes, (L.hip_x, L.toe_y, L.lift + 0.004), "Foot", UP),
    }
    for finger in FINGERS:
        points = finger_points(L, finger)
        for i in range(3):
            parent = "Hand" if i == 0 else f"{finger}{i}"
            left[f"{finger}{i + 1}"] = (points[i], points[i + 1], parent, UP)
    ear = ear_points(L)
    for i in range(3):
        left[f"Ear{i + 1}"] = (ear[i], ear[i + 1], "Head" if i == 0 else f"Ear{i}", FRONT)

    central = set(bones)
    for suffix, sign in ((".L", 1.0), (".R", -1.0)):
        for stem, (head, tail, parent, roll) in left.items():
            parent_name = parent if parent in central else parent + suffix
            bones[stem + suffix] = (
                (head[0] * sign, head[1], head[2]),
                (tail[0] * sign, tail[1], tail[2]),
                parent_name,
                roll,
            )
    return bones


def create_armature(name, collection, L):
    data = bpy.data.armatures.new(name)
    obj = bpy.data.objects.new(name, data)
    collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.mode_set(mode="EDIT")
    for bone_name, (head, tail, parent, roll) in bone_table(L).items():
        bone = data.edit_bones.new(bone_name)
        bone.head, bone.tail = head, tail
        bone.align_roll(roll)
        bone.use_deform = True
        if parent is not None:
            bone.parent = data.edit_bones[parent]
            bone.use_connect = False
    bpy.ops.object.mode_set(mode="OBJECT")
    return obj


def make_body_field(L):
    """Returns fn(position) -> {bone: weight} for the trunk, arms (to the wrist) and legs."""

    def leg_chain(suffix, y, z):
        knee = smoothstep((L.knee_z + 0.045 - z) / 0.09)
        ankle = smoothstep((L.ankle_z + 0.035 - z) / 0.06)
        toes = smoothstep((L.toe_joint_y + 0.02 - y) / 0.04) * smoothstep((L.ankle_z - 0.02 - z) / 0.03)
        return {
            "UpperLeg" + suffix: 1.0 - knee,
            "LowerLeg" + suffix: knee * (1.0 - ankle),
            "Foot" + suffix: knee * ankle * (1.0 - toes),
            "Toes" + suffix: knee * ankle * toes,
        }

    def trunk(x, y, z):
        ax = abs(x)
        spine = smoothstep((z - (L.hip_z + 0.07)) / 0.10)
        chest = smoothstep((z - (L.hip_z + 0.24)) / 0.12)
        # The blend to the neck starts above the collar loop so collars stay with the chest.
        neck = smoothstep((z - (L.neck_base_z + 0.005)) / 0.05)
        head = smoothstep((z - L.chin_z) / 0.04)
        w = {
            "Hips": 1.0 - spine,
            "Spine": spine * (1.0 - chest),
            "Chest": chest * (1.0 - neck),
            "Neck": neck * (1.0 - head),
            "Head": neck * head,
        }
        suffix = ".L" if x >= 0 else ".R"
        shoulder = 0.75 * smoothstep((ax - 0.05) / 0.11) * smoothstep((z - (L.arm_z - 0.105)) / 0.08) * (1.0 - neck)
        if shoulder > 0.0:
            w = {bone: value * (1.0 - shoulder) for bone, value in w.items()}
            w["Shoulder" + suffix] = shoulder

        # Hip crease: the pelvis hands over to the thighs gradually, later near
        # the centre line so the crotch stays with the hips.
        top, bottom = L.hip_z + 0.07, L.hip_z - 0.14
        below = smoothstep((L.crotch_z - z) / 0.06)
        leg = smoothstep((top - z) / (top - bottom)) * lerp(0.35 + 0.65 * smoothstep(ax / 0.09), 1.0, below)
        if leg > 0.0:
            width = lerp(0.03, 0.0005, below)
            left = smoothstep((x + width) / (2.0 * width))
            w = {bone: value * (1.0 - leg) for bone, value in w.items()}
            for suffix, share in ((".L", left), (".R", 1.0 - left)):
                for bone, value in leg_chain(suffix, y, z).items():
                    w[bone] = w.get(bone, 0.0) + leg * share * value
        return w

    def field(p):
        x, y, z = p
        ax = abs(x)
        suffix = ".L" if x >= 0 else ".R"
        # Where the arm takes over from the trunk: at the armhole when level
        # with the arm, progressively further out below it (loose garment sides).
        start = 0.15 + 1.2 * max(0.0, (L.arm_z - 0.045) - z)
        arm = smoothstep((ax - start) / 0.07)
        w = {}
        if arm < 1.0:
            for bone, value in trunk(x, y, z).items():
                w[bone] = value * (1.0 - arm)
        if arm > 0.0:
            elbow = smoothstep((ax - (L.elbow_x - 0.04)) / 0.08)
            wrist = smoothstep((ax - (L.wrist_x - 0.022)) / 0.044)
            w["UpperArm" + suffix] = arm * (1.0 - elbow)
            w["LowerArm" + suffix] = arm * elbow * (1.0 - wrist)
            w["Hand" + suffix] = arm * elbow * wrist
        return limit_weights(w)

    return field
