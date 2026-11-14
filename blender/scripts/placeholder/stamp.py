"""Marks a .blend as generator output and detects whether it has been edited since.

The generator may only overwrite its own untouched output. A flag alone is
not enough: someone who starts hand-modelling in the generated file would
still carry the flag. So the stamp also stores a digest of everything in the
Export collection, and a file whose content no longer matches is treated as
hand-made.
"""

import hashlib

import bpy
import numpy as np

import cass_spec


def _floats(collection, attribute, width):
    data = np.empty(len(collection) * width, dtype=np.float32)
    collection.foreach_get(attribute, data)
    return data.tobytes()


def content_digest():
    digest = hashlib.sha256()
    collection = bpy.data.collections.get(cass_spec.EXPORT_COLLECTION)
    objects = sorted(collection.all_objects, key=lambda o: o.name) if collection else []
    for obj in objects:
        digest.update(f"{obj.type}:{obj.name}".encode())
        if obj.type == "MESH":
            mesh = obj.data
            digest.update(_floats(mesh.vertices, "co", 3))
            loops = np.empty(len(mesh.loops), dtype=np.int32)
            mesh.loops.foreach_get("vertex_index", loops)
            digest.update(loops.tobytes())
            for layer in mesh.uv_layers:
                digest.update(layer.name.encode())
                digest.update(_floats(layer.data, "uv", 2))
            for block in mesh.shape_keys.key_blocks if mesh.shape_keys else []:
                digest.update(block.name.encode())
                digest.update(_floats(block.data, "co", 3))
            names = [group.name for group in obj.vertex_groups]
            for vertex in mesh.vertices:
                for element in vertex.groups:
                    digest.update(f"{names[element.group]}={element.weight:.6f};".encode())
        elif obj.type == "ARMATURE":
            for bone in obj.data.bones:
                parent = bone.parent.name if bone.parent else ""
                digest.update(f"{bone.name}<{parent}:{tuple(bone.head_local)}:{tuple(bone.tail_local)}".encode())
    return digest.hexdigest()


def stamp(scene):
    scene[cass_spec.PLACEHOLDER_PROP] = True
    scene[cass_spec.PLACEHOLDER_DIGEST_PROP] = content_digest()


def is_untouched_placeholder():
    """True when the open file is generator output nobody has modelled in."""
    for scene in bpy.data.scenes:
        if scene.get(cass_spec.PLACEHOLDER_PROP) and scene.get(cass_spec.PLACEHOLDER_DIGEST_PROP) == content_digest():
            return True
    return False
