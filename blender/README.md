# Blender side of the cass avatar

`cass.blend` holds the character model. Headless Blender 5.0 scripts validate
it against the JSON contracts in `Packages/net.wirenook.cass/Spec/` and export
it to `Packages/net.wirenook.cass/BlenderExports/cass.fbx`, which Unity
imports. There is no interactive step; everything runs with `blender -b`.

The model in `cass.blend` is currently a generated placeholder. It is meant to
be replaced by hand-modelling in the same file. Validation and export do not
depend on the generator, only on the contracts listed below.

## Files

| Path | Purpose |
| --- | --- |
| `cass.blend` | The model. One collection, `Export`, holds what is exported. |
| `scripts/cass_spec.py` | Paths, names and loaders for the Spec JSON files. Shared by the other scripts. |
| `scripts/validate.py` | Checks the open `.blend` against the contracts. Runnable, and importable as `validate.validate()`. |
| `scripts/export.py` | Validates, exports the FBX, reads it back and compares it with the scene. |
| `scripts/build_placeholder.py` | Generates the placeholder model from the Spec files. |
| `scripts/placeholder/` | The generator's modules: layout, rig and weights, body, face, shape keys, hair, outfit. |
| `scripts/preview.py` | Renders flat-lit PNG previews for checking a headless session by eye. |

## Commands

Run from the repository root. `BLENDER` overrides the `blender` found on PATH.

```bash
scripts/blender-build-placeholder.sh             # regenerate blender/cass.blend
scripts/blender-export.sh                        # validate, export, verify the FBX
blender -b --factory-startup blender/cass.blend --python blender/scripts/validate.py    # validate only
blender -b --factory-startup blender/cass.blend --python blender/scripts/preview.py -- --out some/dir
```

`--factory-startup` keeps user add-ons and preferences out of the run.
`validate.py` and `export.py` exit non-zero on any error. `export.py` refuses
to export a file that fails validation, and then checks the FBX it wrote in
two ways:

- As stored, parsed straight from the file, which is how Unity reads it.
  Every non-bone node must be at identity and hang directly off the root, the
  bone nodes and the mesh vertices must be where the scene has them once the
  file is read as Y-up, and the bone nodes must agree with the skin's bind
  pose.
- Re-imported into Blender. Object names, bones and their world positions,
  shape key names and sizes, UV layers, triangle counts, vertex groups and
  bounds must match the scene.

The first check exists because the second cannot see an orientation error in
the bone nodes: Blender's importer rebuilds bones from the bind pose. Run `preview.py` with `-- --help` for its options (views, shape key
values, a test pose, tile overrides).

## Replacing the placeholder

`build_placeholder.py` stamps the scene with the custom property
`wirenook_placeholder = True` and a digest of the `Export` collection's
content. It overwrites an existing `cass.blend` only if the stamp is present
and the content still matches the digest. Once the file has been edited by
hand it no longer matches, and the generator refuses unless `--force` is
passed. Deleting the `wirenook_placeholder` scene property makes the same
thing explicit.

The generator is deterministic: it uses no randomness, so the same Spec files
give the same model.

## Modelling contracts

`validate.py` checks these, except where noted. A hand-made model has to keep
them.

### Scene

- Metres, unit scale 1. The character stands on Z = 0, centred on the origin,
  facing -Y. Its left side is +X.
- The rest pose is a T-pose: arms along X with palms down, legs straight.
  Unity takes the exported pose as its T-pose reference, so the armature must
  not be left posed.
- The collection `Export` contains one armature object named `Armature` and
  the mesh objects, nothing else.
- Every object is at identity (transforms applied). Every mesh is parented to
  `Armature` and has an Armature modifier pointing at it, and no other
  modifier. Export does not apply modifiers, because that would drop shape
  keys.

### Skeleton

- `Spec/skeleton.json` is the source of truth. Its `humanoid` map gives the
  bone name for each Unity `HumanBodyBones` entry, and `extra` lists the ear
  bones with their parents. The armature must contain exactly those bones,
  with those parents, all with Deform enabled.
- At most 75 bones. No leaf or helper bones.
- To add or rename a bone, change `skeleton.json` first. Unity configures the
  humanoid rig from the same file.
- Not checked: the `Eye.L` / `Eye.R` bones of the placeholder sit at the
  centre of the face's curvature, not behind the eyes, because the irises are
  flat decals that have to slide along the face when the bone turns. About
  3.5 degrees of yaw and 3 degrees of pitch keep the iris inside the eye
  white. Eyes modelled as real eyeballs want the bones at the eyeball centres.

### Meshes

- The mesh carrying the face must be named `Body`. MMD worlds look it up by
  that name, and all shape keys live on it.
- Other meshes are free to name. The placeholder uses `Hair`,
  `Outfit_Sweater`, `Outfit_Shorts`, `Outfit_Boots` and `Outfit_Hat`, and
  `preview.py --bare` treats the `Outfit_` prefix as "garment".
- One material slot per mesh, the same material everywhere, named `cass`. Its
  base colour is `Textures/cass-palette.png`.
- At most 32,000 triangles in total. The placeholder has about 8,200.
- Each vertex has one to four bone weights that sum to 1.

### UV layers

Every mesh has exactly two UV layers, in this order.

1. `UVMap` selects the colour. All loops of a face sit on the centre of one
   swatch of `cass-palette.json` (tolerance 1e-4). To add a colour, append a
   swatch to `cass-palette.toml` and re-bake with
   `python modules/wirenook-assets/tools/palette.py Packages/net.wirenook.cass/Textures/cass-palette.toml`.
   Appending a row changes the image height and therefore the V coordinate of
   every swatch, so the model's `UVMap` has to be reassigned afterwards (the
   generator does this by itself).
2. `Tile` selects the toggle group. All loops of a face sit inside one tile of
   `Spec/uv-tiles.json`, at (column + 0.5, row + 0.5), clear of the tile
   borders.

Tile assignment (the tile must be valid; which tile a face should use is not
checked):

| Faces | Tile |
| --- | --- |
| Head, neck, hands, ears, eye whites, lashes, brows, mouth, hair | `always` |
| Skin from the collar loop to the waist loop | `body.torso` |
| Skin from the shoulder seams to the wrist loops | `body.arms` |
| Skin from the waist loop to the mid-thigh loops | `body.hips` |
| Skin from the mid-thigh loops to the mid-calf loops | `body.legs` |
| Skin from the mid-calf loops down | `body.feet` |
| Irises, pupils, highlights (and the heart and star pupils) | `face.eyes` |
| Scribble eyes | `face.eyes_scribble` |
| Sweater, shorts, boots, hat | `outfit.default.top`, `.bottom`, `.shoes`, `.hat` |

Skin zones must meet on closed edge loops. Unity discards the zones listed
under a garment's `hides` while the garment is worn, so the garment has to
reach past the border loops of those zones: the sweater past the collar loop
and the wrist loops, the shorts past the waist loop and the mid-thigh loops,
the boots above the mid-calf loops.

Blender shows all tiles at once, so the scribble eyes cover the normal eyes
in the viewport. `preview.py` deletes the faces Unity would discard before it
renders.

### Shape keys

- `Body` carries a `Basis` key first, then every name in
  `Spec/blendshapes.json`: the visemes, the face-tracking keys and the MMD
  names, spelled exactly (the MMD names include half-width katakana).
- A missing viseme, `core` face-tracking key or MMD name is an error. A
  missing `extended` key, or a key the spec does not list, is a warning.
- A key that moves no vertex is an error. Keys are relative to `Basis` and
  left at value 0.
- Keys move only head and neck vertices. Moving a vertex of a `body.*` zone
  is a warning.
- `Left` and `Right` in a key name are the character's left (+X) and right.
- `MouthClosed` follows the ARKit convention: it is the difference between
  "jaw open" and "jaw open with sealed lips", so on its own it pushes the
  lower lip through the upper one.

The placeholder hides geometry that only some keys show (heart and star
pupils, blush marks, tears) by shrinking it to 3% and resting it 4 mm behind
the face skin. The key scales it up and brings it forward.

## FBX settings

`export.py` exports only the `Export` collection, as binary FBX with Y up and
Z forward, unit scale declared in the file (`FBX_SCALE_ALL`), deform bones
only, no leaf bones, primary bone axis Y and secondary X, no animation, shape
keys included, modifiers not applied, textures not embedded.

Blender's exporter normally expresses the axis change as a -90 degree X
rotation on the armature object. `export.py` rotates the mesh and bone data
into Y-up instead, in memory, so every node in the FBX is at identity and
Unity imports `Armature` with no rotation and scale 1. The exporter writes
bone nodes from the pose, so the pose is refreshed after the rest bones are
rotated; skipping that exports a character lying on its back. The `.blend`
itself is not modified.
