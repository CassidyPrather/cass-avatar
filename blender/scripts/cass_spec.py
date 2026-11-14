"""Paths, names and loaders for the machine-readable avatar contracts.

Everything the generator, the validator and the exporter agree on lives in the
JSON files under Packages/net.wirenook.cass/Spec (shared with Unity), so the
three scripts read them through this one module rather than repeating names.
It has no bpy dependency and can be imported by plain Python too.
"""

import json
import pathlib

REPO = pathlib.Path(__file__).resolve().parents[2]
PACKAGE = REPO / "Packages" / "net.wirenook.cass"
SPEC_DIR = PACKAGE / "Spec"
PALETTE_JSON = PACKAGE / "Textures" / "cass-palette.json"
PALETTE_PNG = PACKAGE / "Textures" / "cass-palette.png"
BLEND_PATH = REPO / "blender" / "cass.blend"
FBX_PATH = PACKAGE / "BlenderExports" / "cass.fbx"

EXPORT_COLLECTION = "Export"
MATERIAL_NAME = "cass"
UV_PALETTE = "UVMap"
UV_TILE = "Tile"
# Scene property marking a .blend as generator output that is safe to
# regenerate; the digest detects hand edits made without clearing the flag.
PLACEHOLDER_PROP = "wirenook_placeholder"
PLACEHOLDER_DIGEST_PROP = "wirenook_placeholder_digest"

# Unity lets these humanoid bones be absent; a child then hangs off the
# nearest mapped ancestor. Order is child -> canonical parent.
HUMANOID_PARENT = {
    "Spine": "Hips", "Chest": "Spine", "UpperChest": "Chest", "Neck": "UpperChest", "Head": "Neck",
    "LeftEye": "Head", "RightEye": "Head", "Jaw": "Head",
    "LeftShoulder": "UpperChest", "LeftUpperArm": "LeftShoulder", "LeftLowerArm": "LeftUpperArm",
    "LeftHand": "LeftLowerArm",
    "RightShoulder": "UpperChest", "RightUpperArm": "RightShoulder", "RightLowerArm": "RightUpperArm",
    "RightHand": "RightLowerArm",
    "LeftUpperLeg": "Hips", "LeftLowerLeg": "LeftUpperLeg", "LeftFoot": "LeftLowerLeg", "LeftToes": "LeftFoot",
    "RightUpperLeg": "Hips", "RightLowerLeg": "RightUpperLeg", "RightFoot": "RightLowerLeg",
    "RightToes": "RightFoot",
}
for _side in ("Left", "Right"):
    for _finger in ("Thumb", "Index", "Middle", "Ring", "Little"):
        HUMANOID_PARENT[f"{_side}{_finger}Proximal"] = f"{_side}Hand"
        HUMANOID_PARENT[f"{_side}{_finger}Intermediate"] = f"{_side}{_finger}Proximal"
        HUMANOID_PARENT[f"{_side}{_finger}Distal"] = f"{_side}{_finger}Intermediate"

# The bones Unity refuses to build a humanoid avatar without.
HUMANOID_REQUIRED = (
    "Hips", "Spine", "Head",
    "LeftUpperArm", "LeftLowerArm", "LeftHand", "RightUpperArm", "RightLowerArm", "RightHand",
    "LeftUpperLeg", "LeftLowerLeg", "LeftFoot", "RightUpperLeg", "RightLowerLeg", "RightFoot",
)

MAX_BONES = 75
MAX_TRIANGLES = 32000
MAX_INFLUENCES = 4


def _load(path):
    return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))


def load_palette():
    """Swatch name -> (u, v) of the cell centre."""
    return {name: tuple(entry["uv"]) for name, entry in _load(PALETTE_JSON)["swatches"].items()}


def load_tiles():
    """The uv-tiles spec with an added `by_id` lookup of tile id -> entry."""
    spec = _load(SPEC_DIR / "uv-tiles.json")
    spec["by_id"] = {tile["id"]: tile for tile in spec["tiles"]}
    return spec


def tile_uv(tile):
    return (tile["column"] + 0.5, tile["row"] + 0.5)


def load_blendshapes():
    """Returns the spec plus flat name lists: `required`, `optional`, `all` (in file order)."""
    spec = _load(SPEC_DIR / "blendshapes.json")
    tracking = spec["faceTracking"]
    mmd = [entry["name"] for entry in spec["mmd"]]
    spec["required"] = (
        list(spec["visemes"]) + [e["key"] for e in tracking if e["tier"] == "core"] + mmd
    )
    spec["optional"] = [e["key"] for e in tracking if e["tier"] != "core"]
    spec["all"] = list(spec["visemes"]) + [e["key"] for e in tracking] + mmd
    return spec


def load_proportions():
    return _load(SPEC_DIR / "proportions.json")


def load_skeleton():
    return _load(SPEC_DIR / "skeleton.json")


def humanoid_parent_bone(skeleton, humanoid_name):
    """Armature bone that must parent `humanoid_name`'s bone, skipping unmapped optional bones."""
    mapping = skeleton["humanoid"]
    parent = HUMANOID_PARENT.get(humanoid_name)
    while parent is not None and parent not in mapping:
        parent = HUMANOID_PARENT.get(parent)
    return mapping[parent] if parent is not None else None
