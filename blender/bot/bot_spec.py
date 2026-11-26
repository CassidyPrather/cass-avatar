"""Paths, names and loaders the bot scripts share. Plain Python, no bpy."""

import json
import pathlib
import sys
import tomllib

REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "blender" / "scripts"))

import cass_spec  # noqa: E402  (the humanoid bone names and the blendshape names are the cass avatar's)

PACKAGE = REPO / "Packages" / "net.wirenook.bot"
TEXTURES = PACKAGE / "Textures"
ATLAS_PNG = TEXTURES / "bot-atlas.png"
EMISSION_PNG = TEXTURES / "bot-atlas-emission.png"
FACE_JSON = PACKAGE / "Spec" / "face.json"
FBX_PATH = PACKAGE / "BlenderExports" / "bot.fbx"
BLEND_PATH = REPO / "blender" / "bot" / "bot.blend"
PALETTE_TOML = REPO / "modules" / "wirenook-assets" / "Packages" / "net.wirenook.assets" / "Textures" / "wirenook-palette.toml"
REVIEW_DIR = REPO / "dist" / "bot-review"

EXPORT_COLLECTION = cass_spec.EXPORT_COLLECTION
ARMATURE = "Armature"
# Two skinned meshes. `Body` is the face alone: the sprites, the hidden anchor and every shape
# key. `Shell` is everything else and has no shape keys, so that Unity's optimiser, which keeps a
# mesh with blendshapes apart, can merge props into it.
MESH = "Body"
SHELL = "Shell"
MATERIALS = ("bot", "bot-holo")
MESH_MATERIALS = {MESH: ("bot",), SHELL: MATERIALS}
UV_ATLAS = cass_spec.UV_PALETTE
UV_TILE = cass_spec.UV_TILE
# The attribute on `Body` that marks the vertices shape keys may move: the sprites and the anchor.
SPRITE_ATTRIBUTE = "bot_sprite"

ATLAS_SIZE = 256
MAX_TRIANGLES = 5000
MAX_INFLUENCES = 4
HEIGHT = 1.5

# Bones beyond the humanoid ones, with their parents: the hologram ears and tail, for physics.
EXTRA_BONES = (("Ear.L", "Head"), ("Ear.L.001", "Ear.L"), ("Ear.R", "Head"), ("Ear.R.001", "Ear.R"),
               ("Tail", "Hips"), ("Tail.001", "Tail"))


def load_palette():
    """The wirenook palette: swatch name -> (r, g, b) in 0..255, plus black for what a hologram leaves dark."""
    data = tomllib.loads(PALETTE_TOML.read_text(encoding="utf-8"))
    palette = {}
    for row in data["row"]:
        for name, colour in row["swatches"]:
            value = colour.lstrip("#")
            palette.setdefault(name, tuple(int(value[i:i + 2], 16) for i in (0, 2, 4)))
    palette["black"] = (0, 0, 0)
    return palette


def humanoid_bones():
    """Bone name -> parent bone name for every humanoid bone of Spec/skeleton.json, in its order."""
    skeleton = cass_spec.load_skeleton()
    return {bone: cass_spec.humanoid_parent_bone(skeleton, name) for name, bone in skeleton["humanoid"].items()}


def expected_bones():
    bones = humanoid_bones()
    bones.update(dict(EXTRA_BONES))
    return bones


def spec_shape_names():
    """(visemes, mmd names) from the cass blendshape contract, in file order."""
    spec = cass_spec.load_blendshapes()
    return list(spec["visemes"]), [entry["name"] for entry in spec["mmd"]]


def load_face():
    return json.loads(FACE_JSON.read_text(encoding="utf-8"))
