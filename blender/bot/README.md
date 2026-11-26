# The wirenook bot

A low-polygon robot avatar in the wirenook.net style: a toy with a monitor
for a head, ball joints, checkered cuffs, and rabbit ears and a tail that
are projected as holograms. Its face is a screen of chunky pixels. Every
vertex and texel is made by the scripts in this folder; nothing is modelled
by hand and no third-party asset is used. The only inputs are the wirenook
palette and the cass avatar's bone and blendshape names.

| | |
| --- | --- |
| Meshes | `Body`, the face alone, and `Shell`, everything else |
| Triangles | 2,105 (limit 5,000): `Body` 185, `Shell` 1,920 (1,812 on `bot`, 108 on `bot-holo`) |
| Vertices | `Body` 371, `Shell` 1,104 in Blender |
| Bones | 59: the 53 humanoid bones of `Spec/skeleton.json` and 6 for the ears and tail |
| Shape keys | 96, all on `Body`, all sprite moves; `Shell` has none |
| Textures | `bot-atlas.png` and `bot-atlas-emission.png`, 256 x 256, for point filtering |
| Height | 1.5 m to the top of the head, 1.86 m to the tips of the ears |

## Commands

Run from the repository root. Blender 5.0 is not on PATH on this machine.

```bash
BLENDER="/c/Program Files/Blender Foundation/Blender 5.0/blender.exe"
"$BLENDER" -b --factory-startup --python-exit-code 1 --python "$PWD/blender/bot/build_bot.py"     # model, textures, face.json
"$BLENDER" -b --factory-startup --python-exit-code 1 --python "$PWD/blender/bot/export_bot.py"    # validate, export, read back
"$BLENDER" -b --factory-startup --python-exit-code 1 --python "$PWD/blender/bot/render_bot.py"    # pictures in dist/bot-review/
"$BLENDER" -b --factory-startup blender/bot/bot.blend --python "$PWD/blender/bot/bot_validate.py" # validate only
```

Each exits non-zero on any error. `build_bot.py --force` overwrites a
`.blend` that was edited by hand; `--draft` saves one that fails validation.
`render_bot.py -- --only front,faces` renders some of the pictures.

## Files

| Path | Purpose |
| --- | --- |
| `build_bot.py` | Builds everything and saves `bot.blend`. Also writes the two textures and `face.json`. |
| `bot_model.py` | The design: bone positions, the shape of every part and how it is painted. |
| `bot_face.py` | The sprite face: the pictures as rows of characters, the depth order, and which shape key shows which sprite. |
| `bot_geo.py` | The kit: pixel canvas, atlas packer, PNG writer, and the mesh builder with its checks. |
| `bot_spec.py` | Paths, names and loaders. |
| `bot_validate.py` | Checks an open `.blend` against the contract below. The build and the export both gate on it. |
| `export_bot.py` | Exports `Packages/net.wirenook.bot/BlenderExports/bot.fbx` and verifies the file. |
| `render_bot.py` | Review pictures: views, face close-ups, a contact sheet of expressions, hands, two poses. |
| `bot.blend` | Generator output, stamped like `cass.blend`. Do not edit; change the scripts. |

Outside this folder the build writes
`Packages/net.wirenook.bot/Textures/bot-atlas.png`, `bot-atlas-emission.png`
and `Packages/net.wirenook.bot/Spec/face.json`.

Three modules of the cass pipeline are imported from `blender/scripts/`
rather than copied: `cass_spec` (the Spec loaders), `kitbash/stamp.py` (the
generator stamp) and `export.py` (FBX settings, axis baking and the checks
of the written file). A change to how cass is exported therefore changes
the bot's export too.

## How it is built

Everything is authored in pixels: one pixel is 1/128 m, and one texel of the
atlas covers one square pixel of surface. Parts are convex solids (boxes
with cut corners, eight-sided tubes, low-polygon balls) that overlap at the
joints, each following one bone at full weight, like a toy. Only the
hologram ears and tail are weighted to two bones. `Builder.solid` checks
every solid for being closed and facing outward, and the build fails
otherwise.

The solids are then dealt into two meshes. The sprites and the hidden
anchor triangle become `Body`, which carries every shape key; everything
else becomes `Shell`, which carries none. Unity's Avatar Optimizer keeps a
mesh that has blendshapes apart from all others, so with one mesh no
hand-held prop could be merged into the avatar; with the face apart, props
merge into `Shell` and the avatar has two skinned meshes.

A flat face is unwrapped by projection onto its own plane, so texels are
square on the model. Its island is a rectangle of whole texels with one
texel of its own edge colour repeated all round, so a sample that lands a
hair outside an island finds the colour it would have found inside. Faces
of one flat colour share a single texel. The right limbs mirror the left
and use the same texels. The pictures are drawn by the small paint functions
in `bot_model.py`; the palette is read from
`modules/wirenook-assets/.../wirenook-palette.toml` at build time.

The build is deterministic: no randomness, no iteration over sets, and a PNG
writer without metadata. Two runs give identical textures, `face.json` and
content digest.

## Contract

`bot_validate.py` checks all of this.

### Scene and skeleton

- Metres. The bot stands on Z = 0 facing -Y, its left side at +X, in a
  T-pose with palms down. Collection `Export` holds the armature `Armature`
  and the meshes `Body` and `Shell`, all at identity; each mesh is parented
  to `Armature` and has one Armature modifier. In the FBX all three hang
  directly off the root.
- Bones: every value of `humanoid` in
  `Packages/net.wirenook.cass/Spec/skeleton.json` with the same parents, and
  `Ear.L`, `Ear.L.001`, `Ear.R`, `Ear.R.001` (under `Head`) and `Tail`,
  `Tail.001` (under `Hips`). The cass twist, hair and skirt bones are not
  here.
- `Eye.L` and `Eye.R` exist because the humanoid map lists them. They sit
  behind the eyes of the neutral face and carry no weights: the eyes are
  pictures.
- Knees are 0.6 pixels in front of the line from hip to ankle and elbows
  0.5 behind the line from shoulder to wrist, so that IK bends them the
  right way.

### Meshes

- `Body` is the face and nothing else: every sprite quad and the hidden
  anchor triangle, all following `Head`, with all 96 shape keys and one
  material slot, `bot`. MMD worlds animate it by that name.
- `Shell` is the rest: the head with its opening and backing plate, torso,
  limbs, hands, emitters, and the hologram ears and tail. It has no shape
  keys, and two material slots in this order: `bot` (opaque, everything
  solid) and `bot-holo` (the ears and tail, meant to be drawn additively;
  black in the atlas adds nothing).
- Triangles and flat convex quads only. At most 5,000 triangles between
  the two.
- Both meshes have the UV layers `UVMap` and `Tile`, in that order.
  `UVMap` is the atlas. `Tile` has every corner at (0.5, 0.5), inside the
  tile the shared material never discards.
- Each finger has three boxes, one per bone. They abut at rest and hinge
  apart when the finger bends, showing their dark end caps like the joints
  of a toy.
- The point attribute `bot_sprite` on `Body` marks the vertices shape keys
  may move. It is 1 on all of them; a vertex without it does not belong on
  `Body`.

### The sprite face

`Packages/net.wirenook.bot/Spec/face.json` is the machine-readable form of
this section; `bot_face.py` is its source.

The front of the head has an opening 40 x 28 pixels (0.3125 x 0.21875 m)
with a backing plate 17.6 mm behind it. The opening and the plate are part
of `Shell`; the sprites that stand before and behind the plate are `Body`. The upper 16 rows are the `eyes`
layer and the lower 12 the `mouth` layer. A sprite is an opaque quad the
size of its layer, with the screen's background colour painted in, so
nothing needs alpha.

- Each layer has a neutral sprite (`eyes.open`, `mouth.flat`) that rests
  2 mm in front of the plate.
- Every other sprite rests behind the plate, inside the closed head, where
  nothing can see it. Hiding `Shell` on its own would bare them.
- A shape key at 1 brings its sprite forward to its own `shownDepth`
  (3.5 mm to 12.5 mm, 0.6 mm apart) and sends the layer's neutral sprite
  back to 3.7 mm behind the plate. Both cross the plate at weight 0.35.
- Where several keys of a layer are on, the sprite standing furthest
  forward covers the others. The order runs from expressions to the blink
  for the eyes, and from expressions to speech for the mouth, so a blink
  covers a happy face and a viseme covers a smile. At silence the smile
  shows again.
- **Every key has a quad of its own**, even where several keys show the
  same picture (`mouth.open-big`, `vrc.v_aa`, `あ`, `あ２`, `□`). A shared
  quad would be pushed out through the front of the head by two such keys
  at once; with a quad each, no combination of weights between 0 and 1 can
  move a sprite past its shown depth. Copies rest 0.1 mm apart so no two
  faces coincide.
- Three overlays lie over the layers and hide nothing: `EyeClosedLeft` and
  `EyeClosedRight` each bring a closed eye over their half of the eyes
  layer, `face.blush` (and `照れ`) two blush marks, and `face.bluescreen`
  the full-screen blue picture for an away state. Drive the bluescreen to 1;
  below that it shows as soon as it stands in front of whatever is shown.
- A key with nothing to show (`vrc.v_sil`, `ハイライト消`, `真面目`, `にこり`,
  `上`, `下`, and the two neutral names `eyes.open` and `mouth.flat`) moves a
  hidden triangle in the middle of the head by 0.1 mm. Blender's exporter
  keeps a key that moves nothing, but what Unity's importer and the
  optimisers downstream do with one was not verified, so none is left
  empty.
- Left and right are the avatar's own: `eyes.wink-left` closes its left
  eye, which is on the right of the screen for someone facing it.

Sprites, back to front:

| Layer | Sprites |
| --- | --- |
| `eyes` | `open` (neutral), `dot`, `sleepy`, `smug`, `sad`, `angry`, `wide`, `happy`, `hearts`, `stars`, `dizzy`, `crossed`, `cry`, `squeeze`, `wink-left`, `wink-right`, `closed` |
| `mouth` | `flat` (neutral), `smile`, `smirk`, `frown`, `wavy`, `cat`, `triangle`, `tongue`, `big-smile`, `pressed`, `narrow`, `wide`, `open-mid`, `small-o`, `medium-o`, `open-big` |
| `overlay` | `lid-left`, `lid-right`, `blush`, `bluescreen` |

Shape keys, in export order after `Basis`:

| Group | Keys | Shows |
| --- | --- | --- |
| Visemes (15) | `vrc.v_sil` | nothing |
| | `vrc.v_pp` | `pressed` |
| | `vrc.v_ff`, `vrc.v_th`, `vrc.v_dd`, `vrc.v_nn` | `narrow` |
| | `vrc.v_kk`, `vrc.v_e` | `open-mid` |
| | `vrc.v_ch`, `vrc.v_ss`, `vrc.v_ih` | `wide` |
| | `vrc.v_rr`, `vrc.v_ou` | `small-o` |
| | `vrc.v_aa` | `open-big` |
| | `vrc.v_oh` | `medium-o` |
| Blink (2) | `EyeClosedLeft`, `EyeClosedRight` | `lid-left`, `lid-right` |
| MMD eyes | `まばたき`, `なごみ` | `closed` |
| | `笑い` | `happy` |
| | `ウィンク`, `ウィンク２` / `ウィンク右`, `ｳｨﾝｸ２右` | `wink-left` / `wink-right` |
| | `はぅ`, `びっくり`, `はちゅ目`, `じと目`, `ｷﾘｯ` | `squeeze`, `wide`, `wide`, `sleepy`, `angry` |
| | `はぁと`, `星目`, `瞳小`, `涙` | `hearts`, `stars`, `dot`, `cry` |
| | `困る`, `怒り` (brows) | `sad`, `angry` |
| | `ハイライト消`, `真面目`, `にこり`, `上`, `下` | nothing |
| MMD mouth | `あ`, `あ２`, `□` | `open-big` |
| | `い`, `口横広げ` | `wide` |
| | `う`, `え`, `お`, `ん` | `small-o`, `open-mid`, `medium-o`, `pressed` |
| | `▲`, `∧`, `口角下げ` | `triangle`, `frown`, `frown` |
| | `ワ`, `ω`, `ω□`, `にやり` | `big-smile`, `cat`, `cat`, `smirk` |
| | `にっこり`, `口角上げ`, `ぺろっ`, `てへぺろ` | `smile`, `smile`, `tongue`, `tongue` |
| MMD other | `照れ` | `blush` |
| By sprite (35) | `eyes.<sprite>` for all 17, `mouth.<sprite>` for all 16, `face.blush`, `face.bluescreen` | that sprite |

The MMD names are all 44 of `Spec/blendshapes.json`. The face-tracking
names of that file, other than the two blink keys, are not on this model.

To add a sprite: draw it in `bot_face.py`, put it in `ORDER` where it
should stand, and name the keys that show it. The opening is deep enough
for the present 16 eye sprites, the overlays and 2 mm to spare; `RECESS` in
`bot_model.py` is the depth.

## Export

`export_bot.py` refuses a file that fails validation, exports with the cass
settings (binary FBX, Y up, Z forward, unit scale declared in the file,
deform bones only, no leaf bones, shape keys, no animation), and bakes the
axis change into the data so that every node is at identity. It then checks
the file three ways and fails on any difference:

- as stored: axes, node transforms, bone nodes against the scene and
  against the skin's bind pose, and the orientation stated on its own terms
  (head above hips, toes ahead of ankles, left arm at FBX +X);
- re-imported: object names, bones and parents, bone positions, triangle
  count, UV layer names, shape key names and sizes, weighted groups, bounds;
- the bot's own promises: exactly the meshes `Body` and `Shell`, the
  material slots of each in order with the triangles each slot carries,
  every shape key of `Body` present and none empty with the distance it
  moves to 0.01 mm, no shape key on `Shell`, and both UV layers of both
  meshes unchanged.

## Not checked here

- Nothing was imported into Unity. That the humanoid importer accepts the
  T-pose, that Unity keeps all 96 blendshapes, and how the hologram looks
  drawn additively are for the Unity side to confirm.
- The atlas has one texel of padding round each island and is meant for
  point filtering without mip maps. With mip maps, neighbouring islands
  blend from the second level on.
- Two sprites of one layer both at exactly half weight stand 0.14 mm
  apart. That is enough at conversation distance and may flicker for the
  frames of a blend when seen from many metres.
