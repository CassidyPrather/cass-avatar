"""Paths, names and loaders the meta scripts share. Plain Python, no bpy."""

import colorsys
import json
import os
import pathlib
import sys
import tomllib

REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "blender" / "scripts"))
sys.path.insert(0, str(REPO / "blender" / "bot"))

import cass_spec  # noqa: E402  (the humanoid bone names are the cass avatar's, so the same Unity code maps them)

# Where the model's outputs land: the avatar's package. Not "net.wirenook.meta": Unity takes a
# folder whose name ends in .meta for the meta file of a folder that is not there.
PACKAGE = REPO / "Packages" / "net.wirenook.meta-avatar"
# Work in progress goes somewhere Unity is not watching: META_PACKAGE=dist/staging sends the textures,
# the Spec files and the FBX there instead. A .blend built that way refers to those textures.
if os.environ.get("META_PACKAGE"):
    PACKAGE = (REPO / os.environ["META_PACKAGE"]).resolve()
TEXTURES = PACKAGE / "Textures"
ATLAS_PNG = TEXTURES / "meta-atlas.png"
EMISSION_PNG = TEXTURES / "meta-atlas-emission.png"
TINT_PNG = TEXTURES / "meta-atlas-tint.png"
SKELETON_JSON = PACKAGE / "Spec" / "skeleton.json"
MODEL_JSON = PACKAGE / "Spec" / "model.json"
FBX_PATH = PACKAGE / "BlenderExports" / "meta.fbx"
BLEND_PATH = REPO / "blender" / "meta" / "meta.blend"
PALETTE_TOML = REPO / "modules" / "wirenook-assets" / "Packages" / "net.wirenook.assets" / "Textures" / "wirenook-palette.toml"
REVIEW_DIR = REPO / "dist" / "meta-review"

EXPORT_COLLECTION = cass_spec.EXPORT_COLLECTION
ARMATURE = "Armature"
MESH = "Body"
MATERIAL = "meta"
UV_ATLAS = cass_spec.UV_PALETTE
UV_TILE = cass_spec.UV_TILE
# In the .blend only: an integer on each face saying which part of the figure it is, and the parts' names.
PART_ATTRIBUTE = "part"
PART_NAMES = "parts"

# Metres to a pixel of the model, as on the robot (bot_geo.PX), and where the mantle's underside
# meets in the middle of the body, in pixels: the validator leaves the faces that meet there out.
PX = 1.0 / 128.0
MANTLE_UNDER = (0.0, 0.0, 170.0)

ATLAS_SIZE = 256
MAX_TRIANGLES = 5000
MAX_BONES = 60
MAX_INFLUENCES = 4
HEIGHT = 1.75

# The humanoid map: UnityEngine.HumanBodyBones name -> bone. The cass names, without the eyes
# (there is no face) and so without anything that hangs on the head bone.
HUMANOID = {name: bone for name, bone in cass_spec.load_skeleton()["humanoid"].items() if name not in ("LeftEye", "RightEye")}

# The head the player's voice and nameplate follow carries nothing. What is seen of the head is on
# HeadVisual, its twin under the neck, which Unity makes follow Head with a constraint.
HEAD_VISUAL = "HeadVisual"

# Bones beyond the humanoid ones: (name, parent, what it is for).
#   visual  follows the humanoid bone named, by constraint
#   sway    an optional physics chain; a build without physics leaves the bones rigid
EXTRA_BONES = (
    (HEAD_VISUAL, "Neck", {"visual": "Head"}),
    ("Sway.Hood", HEAD_VISUAL, {"sway": "hood"}),
    ("Sway.Hood.001", "Sway.Hood", {}),
    ("Sway.Sleeve.L", "LowerArm.L", {"sway": "sleeve"}),
    ("Sway.Sleeve.R", "LowerArm.R", {"sway": "sleeve"}),
)

# The signature colour as the atlas has it: one hue at four strengths. Everything in the tint mask
# is one of these, so turning the hue of the masked texels gives any other signature colour.
SIGNATURE_HUE = 185.0 / 360.0
SIGNATURE = {  # name -> (saturation, value)
    "sig-hi": (0.16, 1.00),
    "sig": (0.55, 1.00),
    "sig-lo": (0.72, 0.66),
    "sig-dim": (0.66, 0.40),
}


def signature_rgb(name, hue=SIGNATURE_HUE):
    s, v = SIGNATURE[name]
    return tuple(int(round(c * 255.0)) for c in colorsys.hsv_to_rgb(hue, s, v))


def load_palette():
    """The wirenook palette: swatch name -> (r, g, b) in 0..255, plus black and the signature colours."""
    data = tomllib.loads(PALETTE_TOML.read_text(encoding="utf-8"))
    palette = {}
    for row in data["row"]:
        for name, colour in row["swatches"]:
            value = colour.lstrip("#")
            palette.setdefault(name, tuple(int(value[i:i + 2], 16) for i in (0, 2, 4)))
    palette["black"] = (0, 0, 0)
    # Cloth of the robe: the palette's own darks, and two mixes between them for folds.
    palette["cloth"] = _mix(palette["grey-dark"], palette["night-3"], 0.2)
    palette["cloth-dark"] = _mix(palette["grey-dark"], palette["night-4"], 0.35)
    palette["cloth-deep"] = _mix(palette["grey-dark"], palette["night-4"], 0.85)
    palette["cloth-light"] = _mix(palette["grey-dark"], palette["night-3"], 0.6)
    # The mantle and the hood are a darker, bluer cloth than the robe under them.
    palette["mantle"] = _mix(palette["night-4"], palette["grey-dark"], 0.12)
    palette["mantle-dark"] = _mix(palette["night-4"], palette["night-1"], 0.55)
    palette["mantle-light"] = _mix(palette["night-4"], palette["night-3"], 0.3)
    palette["leather"] = palette["wood-dark"]
    palette["leather-dark"] = _mix(palette["wood-dark"], palette["soot"], 0.55)
    palette["leather-light"] = _mix(palette["wood-dark"], palette["wood"], 0.5)
    palette["wrap"] = palette["cream"]
    palette["wrap-dark"] = _mix(palette["cream"], palette["night-3"], 0.45)
    palette["wrap-mid"] = _mix(palette["cream"], palette["night-3"], 0.2)
    for name in SIGNATURE:
        palette[name] = signature_rgb(name)
    return palette


def _mix(a, b, t):
    return tuple(int(round(x + (y - x) * t)) for x, y in zip(a, b))


def humanoid_bones():
    """Bone name -> parent bone name for every humanoid bone, in the map's order."""
    skeleton = {"humanoid": HUMANOID}
    return {bone: cass_spec.humanoid_parent_bone(skeleton, name) for name, bone in HUMANOID.items()}


def expected_bones():
    bones = humanoid_bones()
    for name, parent, _role in EXTRA_BONES:
        bones[name] = parent
    return bones


def load_model():
    return json.loads(MODEL_JSON.read_text(encoding="utf-8"))
