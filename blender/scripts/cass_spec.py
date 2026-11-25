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
# The texture the model wears: the painted face plus the palette, baked by build_cass.py.
ATLAS_JSON = PACKAGE / "Textures" / "cass-atlas.json"
ATLAS_PNG = PACKAGE / "Textures" / "cass-atlas.png"
ATLAS_NORMAL_PNG = PACKAGE / "Textures" / "cass-atlas-normal.png"
# White where the atlas glows: the palette's own emission mask, laid out as the atlas is.
PALETTE_EMISSION_PNG = PACKAGE / "Textures" / "cass-palette-emission.png"
ATLAS_EMISSION_PNG = PACKAGE / "Textures" / "cass-atlas-emission.png"
BLEND_PATH = REPO / "blender" / "cass.blend"
SOURCES_DIR = REPO / "blender" / "sources"
FBX_PATH = PACKAGE / "BlenderExports" / "cass.fbx"

# Fidelity levels. Both are built by the same generator from the same sources
# and share one skeleton; `lite` uses the body base's low-polygon mesh and
# coarser modelled parts, for mobile builds and the optimised PC variant.
# `max_triangles` counts the tiles that are shown at rest. `max_hidden_triangles` counts the
# rest (the alternative garments and hairstyles), where they are budgeted apart; without it
# they count towards `max_triangles` with everything else.
LEVELS = {
    # A PC build keeps every tile, so the whole mesh is held to VRChat's 70,000.
    "full": {"blend": BLEND_PATH, "fbx": FBX_PATH, "max_triangles": 70000, "max_hidden_triangles": None},
    "lite": {"blend": REPO / "blender" / "cass-lite.blend", "fbx": PACKAGE / "BlenderExports" / "cass-lite.fbx",
             # Before the build removes the skin under the outfit; VRChat's mobile Medium is 15,000 after it,
             # and `scripts/cass.sh verify <slug> android` is what holds the build to that. The mobile
             # build cuts the tiles hidden at rest out of the mesh, so they are free there; the cap on
             # them only keeps the alternatives coarse.
             "max_triangles": 17000, "max_hidden_triangles": 8000},
}
LEVEL_PROP = "wirenook_level"

# Wardrobes: sets of garments built by the same generator onto the same body, face, hair, ears,
# tail and skeleton, each at both levels. Every wardrobe has the same mesh names, bones,
# blendshapes and UV tiles, so Unity exchanges one for another by mesh name, as it does the
# levels. The value is what a wardrobe adds to the file names: cass-cyber.blend, cass-cyber-lite.fbx.
WARDROBES = {"western": "", "cyber": "-cyber"}
WARDROBE_PROP = "wirenook_wardrobe"


def outputs(level, wardrobe="western"):
    """The .blend and the FBX of a wardrobe at a level; the budgets are the level's own (LEVELS)."""
    if wardrobe == "western":
        return {"blend": LEVELS[level]["blend"], "fbx": LEVELS[level]["fbx"]}
    stem = "cass" + WARDROBES[wardrobe] + ("" if level == "full" else f"-{level}")
    return {"blend": REPO / "blender" / f"{stem}.blend", "fbx": PACKAGE / "BlenderExports" / f"{stem}.fbx"}

EXPORT_COLLECTION = "Export"
MATERIAL_NAME = "cass"
UV_PALETTE = "UVMap"
UV_TILE = "Tile"
# Scene property marking a .blend as generator output that is safe to
# regenerate; the digest detects hand edits made without clearing the flag.
GENERATED_PROP = "wirenook_generated"
GENERATED_DIGEST_PROP = "wirenook_generated_digest"

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

# VRChat ranks an avatar Good on PC, and Medium on mobile, up to 150 bones. The mobile build does
# not carry them all: it cuts out what is hidden at rest, and the bones only that hangs on go with it.
MAX_BONES = 150
MAX_INFLUENCES = 4


def _load(path):
    return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))


def load_palette():
    """Swatch name -> (u, v) of the cell centre."""
    return {name: tuple(entry["uv"]) for name, entry in _load(ATLAS_JSON)["swatches"].items()}


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
