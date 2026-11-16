# Blender side of the cass avatar

The model is a kitbash, assembled by script: a CC0 body base, a CC0 face,
and hair, ears, tail and outfit modelled in code around them. Headless
Blender 5.0 scripts build it into `cass.blend`, validate it against the JSON
contracts in `Packages/net.wirenook.cass/Spec/`, and export it to
`Packages/net.wirenook.cass/BlenderExports/`, which Unity imports. There is
no interactive step; everything runs with `blender -b`.

It is built at two fidelity levels from the same generator, on one skeleton:

| Level | File | Export | Body mesh | Triangles |
| --- | --- | --- | --- | --- |
| `full` | `cass.blend` | `cass.fbx` | SiroinoSotai PC (16.7k) | about 38,000 |
| `lite` | `cass-lite.blend` | `cass-lite.fbx` | SiroinoSotai Mobile (3.5k) | about 15,600 |

Both have the same objects, bones, shape keys and UV tiles, which is what
lets Unity exchange one for the other at build time. The garments cut from
the body follow its level; hair, ears, tail, boots and hat are divided more
coarsely in `lite`. The face is the same mesh in both.

## Files

| Path | Purpose |
| --- | --- |
| `cass.blend`, `cass-lite.blend` | The model at each level. One collection, `Export`, holds what is exported; `Guides` holds the hair's guide curves for reference. |
| `sources/` | The trimmed third-party assets the build starts from (see below). |
| `scripts/intake.py` | Trims the downloaded source archives into `sources/`. |
| `scripts/build_cass.py` | Builds a level from `sources/` and the modules in `scripts/kitbash/`. |
| `scripts/kitbash/` | The generator's modules; each has a docstring that says what it decides. |
| `scripts/cass_spec.py` | Paths, names and loaders for the Spec JSON files. Shared by the other scripts. |
| `scripts/validate.py` | Checks the open `.blend` against the contracts. Runnable, and importable as `validate.validate()`. |
| `scripts/export.py` | Validates, exports the FBX, reads it back and compares it with the scene. |
| `scripts/preview.py` | Renders flat-lit PNG previews for checking a headless session by eye. |

| Module | What it makes |
| --- | --- |
| `kitbash/body.py` | The skin below the neck, with the size preset baked in and each face tagged with its body segment. |
| `kitbash/face.py` | The head: fitted to the body's neck, re-keyed to the spec's shape key names. |
| `kitbash/decals.py` | Blush strokes, tears and the scribbled eyes, as geometry on the face. |
| `kitbash/atlas.py` | The one texture, `Textures/cass-atlas.png`: the painted face beside the palette. |
| `kitbash/rig.py` | The armature: the body base's skeleton under the spec's names, plus added bones. |
| `kitbash/shell.py`, `garments.py` | Sweater and shorts cut from the body's own mesh; boots lofted around the leg. |
| `kitbash/sweep.py`, `hair.py`, `extras.py`, `hat.py` | Swept strands; the hair; ears and tail; the hat. |
| `kitbash/stamp.py` | Marks a `.blend` as generator output and detects hand edits. |

## Commands

Run from the repository root. `BLENDER` overrides the `blender` found on PATH.

```bash
scripts/cass.sh build                            # both levels -> blender/cass.blend, cass-lite.blend
scripts/cass.sh export                           # validate, export and verify both FBX files, refresh Unity
scripts/blender-build.sh --level lite            # one level; --force overwrites a hand-edited file
scripts/blender-export.sh --level lite
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
the bone nodes: Blender's importer rebuilds bones from the bind pose. Run
`preview.py` with `-- --help` for its options (views, extra shots, shape key
values, a test pose, tile overrides). Its cavity shading draws faint marks
around the mouth after it has deleted hidden faces; they are not in the model.

## Source assets

Both are CC0 and credited in `CREDITS.md`. The downloads are kept out of
the repository (`ref/*.zip` is ignored); `intake.py` extracts only what the
build needs into `sources/`, which is committed, so a clone builds without
them.

| File | From | Used for |
| --- | --- | --- |
| `sources/siroino-body.blend` | SiroinoSotai 1.0, both FBX files | The body at both levels, its weights and its skeleton. |
| `sources/henge-face.blend` | Mizunashi Hiyori, `CC0_FBX/mizunashi2024.fbx`, face mesh only | The head, its weights and its 122 shape keys. |
| `sources/henge-face.png` | Mizunashi Hiyori, `CC0_Textures/` face albedo | The painted part of the atlas. |

To take a new version of either, replace the archive in `ref/` and run
`blender -b --factory-startup --python blender/scripts/intake.py`.

What the build changes about them:

- **Body.** The `All_M` size preset and three quarters of `Breasts_flat`
  are baked into the rest shape and every other shape key is dropped. The
  base's `<Part>_OFF` keys are read first: the vertices each one moves are a
  body segment bounded by edge loops, and those segments become the skin
  zones and the pieces garments are cut from. Its breast bones are folded
  into the chest. Its normal maps are not used.
- **Head.** Scaled by 1.15 and seated on the body's head joint. Its neck is
  far thicker than the body's, so the stub is drawn in and the top of the
  body's neck flared until they meet; the body's neck ends a little way
  inside the head's. The expression overlays that need a transparent
  material (manga marks, tear and blush cards) are deleted, and the scalp
  under the hair is removed. The source's pink eyes are recoloured blue and
  its lashes and brows brown in the atlas; heart and star pupils are drawn
  there rather than taken from the source.
- **Figure.** Body and head together are scaled so the top of the skull is
  at `height` in `Spec/proportions.json`, standing `bootHeelHeight` above
  the ground for the boot soles.

The other body-size and nail shape keys of the base are not carried over.
A garment made here fits the baked shape only.

## Editing by hand

`build_cass.py` stamps the scene with the custom property
`wirenook_generated = True` and a digest of the `Export` collection's
content. It overwrites an existing `.blend` only if the stamp is present and
the content still matches the digest. Once a file has been edited by hand it
no longer matches, and the generator refuses unless `--force` is passed.
Validation and export do not depend on the generator, only on the contracts
below, so a hand-edited or hand-made file exports the same way.

The generator is deterministic: it uses no randomness, so the same sources
and Spec files give the same model.

To change how something looks, the numbers are at the top of its module:
the hairstyle is the `FRINGE` guides and the azimuth lists in `hair.py`, the
ears and tail are the guides in `extras.py`, the hat's dimensions are in
`hat.py`, and each garment's cut is its function in `garments.py`. A new
outfit is a new set of functions there, on its own discard tiles.

## Modelling contracts

`validate.py` checks these, except where noted.

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
  bone name for each Unity `HumanBodyBones` entry, and `extra` lists every
  other bone with its parent. The armature must contain exactly those bones,
  with those parents, all with Deform enabled.
- At most 90 bones (VRChat's Good on mobile). The model has 74. No leaf or
  helper bones.
- To add or rename a bone, change `skeleton.json` first. Unity configures the
  humanoid rig from the same file.
- The extra bones:
  - `UpperArmTwist`, `LowerArmTwist` (both sides): the body base's twist
    helpers. They carry weights; Unity gives each a rotation constraint
    from the `twist` entry beside it in the spec.
  - `Ear1` to `Ear3` (both sides), `Tail1`, `Tail2`: physics chains that
    the gesture poses also turn.
  - `HairRoot` and four two-bone chains under it (`HairSide`, `HairBack`,
    both sides): one PhysBone on the root swings all four.
- The `Eye.L` / `Eye.R` bones sit deep inside the head, not behind the eyes:
  the irises are shells that slide across the eye whites when the bone
  turns. They point up with Z forward, so in Unity a turn about X is the
  gaze going up or down and about Y sideways. The irises stay inside the
  eye opening out to about 11 degrees sideways; Unity uses 10 sideways,
  8 up and 10 down.

### Meshes

- The mesh carrying the face must be named `Body`. MMD worlds look it up by
  that name, and all shape keys live on it. Here it is the head only.
- Other meshes are free to name. The model has `Skin` (the body), `Hair`,
  `Ears`, `Tail`, `Outfit_Sweater`, `Outfit_Shorts`, `Outfit_Boots` and
  `Outfit_Hat`; `preview.py --bare` treats the `Outfit_` prefix as "garment".
  Both levels must have the same mesh names.
- One material slot per mesh, the same material everywhere, named `cass`. Its
  base colour is `Textures/cass-atlas.png`.
- At most 70,000 triangles at the full level and 16,000 at lite, before the
  build removes anything.
- Each vertex has one to four bone weights that sum to 1.

### UV layers

Every mesh has exactly two UV layers, in this order.

1. `UVMap` selects the colour from the atlas and must stay inside the unit
   square. A flat-coloured face has all its loops on the centre of one
   swatch (`common.set_swatches`); the head keeps the face texture's own
   UVs. Swatch UVs are in `Textures/cass-atlas.json`. To add a colour,
   append a swatch to `cass-palette.toml`, re-bake with
   `python modules/wirenook-assets/tools/palette.py Packages/net.wirenook.cass/Textures/cass-palette.toml`
   and rebuild; the build bakes the palette into the atlas and reassigns
   every swatch UV. The `skin` swatch is not the palette's: it is the
   median skin tone of the face texture, so head and body match.
2. `Tile` selects the toggle group. All loops of a face sit inside one tile of
   `Spec/uv-tiles.json`, at (column + 0.5, row + 0.5), clear of the tile
   borders.

Tile assignment (the tile must be valid; which tile a face should use is not
checked):

| Faces | Tile |
| --- | --- |
| Head, neck, wrists, hands, hair, ears, tail, blush and tear marks | `always` |
| Skin of the chest and waist (segments `Chest_01`, `Chest_02`, `Spine`) | `body.torso` |
| Skin from the shoulders to the forearms (`Shoulder` to `LowerArm`) | `body.arms` |
| Skin of the pelvis (`Hips`) | `body.hips` |
| Skin from the top of the thigh to mid-calf (`UpperLeg_01` to `LowerLeg_01`) | `body.legs` |
| Skin from mid-calf down (`LowerLeg_02`, `Foot`, `Toe`) | `body.feet` |
| Irises, highlights, heart and star pupils | `face.eyes` |
| Scribbled eyes | `face.eyes_scribble` |
| Sweater, shorts, boots, hat | `outfit.default.top`, `.bottom`, `.shoes`, `.hat` |

Unity discards the zones listed under a garment's `hides` while the garment
is worn, so the garment has to reach past the border of those zones. The
body is triangulated, so those borders are saw-toothed by a centimetre or
two; the sweater's collar and cuffs, the waistband and legs of the shorts
and the boot shafts are each long enough to cover theirs.

Blender shows all tiles at once, so the scribbled eyes cover the normal eyes
in the viewport. `preview.py` deletes the faces Unity would discard before it
renders.

### Shape keys

- `Body` carries a `Basis` key first, then every name in
  `Spec/blendshapes.json`: the visemes, the face-tracking keys and the MMD
  names, spelled exactly (the MMD names include half-width katakana).
- A missing viseme, `core` face-tracking key or MMD name is an error. A
  missing `extended` key, or a key the spec does not list, is a warning. The
  model has all the core keys and five of the extended ones; it has no
  gaze, tongue-direction or throat keys.
- A key that moves no vertex is an error. Keys are relative to `Basis` and
  left at value 0.
- `Left` and `Right` in a key name are the character's left (+X) and right.
- None of the source face's key names are exported. `RECIPES` in
  `kitbash/face.py` rebuilds each spec name as a weighted sum of source
  keys, optionally limited to one side of the face or to one lip. Most
  tracking keys are the source's ARKit shape of the same meaning; the
  split ones (`LipFunnelUpperLeft` and the like) are one source shape
  masked four ways, and the nose sneers are approximated from the upper lip
  and cheek, because the source has no nose shapes. To swap the face,
  write a new table.
- `MouthClosed` follows the ARKit convention: it is the difference between
  "jaw open" and "jaw open with sealed lips", so on its own it pushes the
  lower lip through the upper one.
- `照れ` and `涙` unfold blush strokes and tears that rest collapsed to a
  point inside the head.

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
