"""Trims the third-party source assets into the small files the build reads.

    blender -b --factory-startup --python blender/scripts/intake.py -- [--siroino ZIP] [--henge ZIP]

The two archives are CC0 downloads kept out of the repository (ref/*.zip).
This script unpacks them into a temporary folder and writes only what the
avatar is built from into blender/sources/, which is committed:

    siroino-body.blend   both fidelity levels of the SiroinoSotai body on one armature
    siroino-normal-full.png, siroino-normal-lite.png   the body's normal map for each level
    henge-face.blend     the face mesh of Mizunashi Hiyori with its armature
    henge-face.png       its colour texture
    henge-face-normal.png  its normal map, which its author's material shades the face through

Nothing is modelled here; the meshes, weights and shape keys are stored as
they arrive. Re-run it only when a source archive changes. CREDITS.md lists
where the archives come from.
"""

import sys
import pathlib

sys.dont_write_bytecode = True
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import argparse
import shutil
import tempfile
import zipfile

import bpy

import cass_spec

SIROINO_ZIP = cass_spec.REPO / "ref" / "SiroinoSotai_1.0.zip"
HENGE_ZIP = cass_spec.REPO / "ref" / "Henge_MizunashiHiyori_20240922.zip"

SIROINO_TEXTURES = {
    "SiroinoSotai_1.0/TEX/PC/SiroinoSotaiNormal_PC_1k.png": "siroino-normal-full.png",
    "SiroinoSotai_1.0/TEX/Mobail/SiroinoSotaiNormal_Mobile_1k.png": "siroino-normal-lite.png",
}
SIROINO_MEMBERS = {
    "full": "SiroinoSotai_1.0/SiroinoSotai_PC.fbx",
    "lite": "SiroinoSotai_1.0/SiroinoSotai_Mobile.fbx",
}
HENGE_FBX = "Henge_MizunashiHiyori_20240922/CC0_FBX/mizunashi2024.fbx"
HENGE_TEXTURES = {
    "Henge_MizunashiHiyori_20240922/CC0_Textures/mizunashi_20240621_subs_Face_2048_AlbedoTransparency.png": "henge-face.png",
    "Henge_MizunashiHiyori_20240922/CC0_Textures/mizunashi_20240621_subs_Face_2048_Normal.png": "henge-face-normal.png",
}
HENGE_FACE = "a_Face_Hiyori"


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    parser = argparse.ArgumentParser(prog="intake.py", description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("--siroino", default=str(SIROINO_ZIP))
    parser.add_argument("--henge", default=str(HENGE_ZIP))
    return parser.parse_args(argv)


def extract(archive, member, folder):
    """Extracts one member by its exact name; never trusts paths stored in the archive."""
    target = pathlib.Path(folder) / pathlib.PurePosixPath(member).name
    with zipfile.ZipFile(archive) as source, source.open(member) as data, open(target, "wb") as out:
        shutil.copyfileobj(data, out)
    return target


def save(path):
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.wm.save_as_mainfile(filepath=str(path), compress=True)
    print(f"intake: wrote {path} ({path.stat().st_size} bytes)")


def drop_materials():
    """The sources' materials point at textures on the author's disk; the build assigns its own."""
    for obj in bpy.data.objects:
        if obj.type == "MESH":
            # Slots stay (the face tells its overlays apart by slot); only the links go.
            for slot in obj.material_slots:
                slot.material = None
    for block in (bpy.data.materials, bpy.data.images):
        for item in list(block):
            block.remove(item)


def intake_siroino(archive, folder):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    armature = None
    for level, member in SIROINO_MEMBERS.items():
        before = set(bpy.data.objects)
        bpy.ops.import_scene.fbx(filepath=str(extract(archive, member, folder)))
        new = set(bpy.data.objects) - before
        mesh = next(o for o in new if o.type == "MESH")
        rig = next(o for o in new if o.type == "ARMATURE")
        mesh.name = mesh.data.name = f"siroino-{level}"
        if armature is None:
            armature = rig
            armature.name = armature.data.name = "siroino-armature"
        else:
            # Both levels are skinned to the same skeleton; keep one copy of it.
            mesh.parent = armature
            mesh.modifiers[0].object = armature
            bpy.data.objects.remove(rig)
    drop_materials()
    save(cass_spec.SOURCES_DIR / "siroino-body.blend")
    for member, name in SIROINO_TEXTURES.items():
        shutil.copyfile(extract(archive, member, folder), cass_spec.SOURCES_DIR / name)
        print(f"intake: wrote {cass_spec.SOURCES_DIR / name}")


def intake_henge(archive, folder):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.fbx(filepath=str(extract(archive, HENGE_FBX, folder)))
    for obj in list(bpy.data.objects):
        if obj.type == "MESH" and obj.name != HENGE_FACE:
            bpy.data.objects.remove(obj)
    face = bpy.data.objects[HENGE_FACE]
    face.name = face.data.name = "henge-face"
    face.parent.name = face.parent.data.name = "henge-armature"
    drop_materials()
    for block in (bpy.data.meshes, bpy.data.armatures):
        for item in [i for i in block if i.users == 0]:
            block.remove(item)
    save(cass_spec.SOURCES_DIR / "henge-face.blend")
    for member, name in HENGE_TEXTURES.items():
        shutil.copyfile(extract(archive, member, folder), cass_spec.SOURCES_DIR / name)
        print(f"intake: wrote {cass_spec.SOURCES_DIR / name}")


def main():
    args = parse_args()
    cass_spec.SOURCES_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as folder:
        intake_siroino(args.siroino, folder)
        intake_henge(args.henge, folder)


main()
