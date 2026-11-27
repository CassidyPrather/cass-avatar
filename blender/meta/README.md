# The meta figure

A low-polygon game master in a hooded robe, in the wirenook.net style of the
robot (`blender/bot/`): flat faces, pixels painted on instead of detail
modelled. The hood is deep and there is nothing in it: no face, no visemes,
no shape keys. Over the shoulders a short mantle with a sigil on the back;
under it a long robe with a stole of runes down the front, a belt with a
book and a pouch, wide sleeves, wrapped hands and boots. Every vertex and
texel is made by the scripts in this folder; nothing is modelled by hand and
no third-party asset is used. The only inputs are the wirenook palette and
the cass avatar's humanoid bone names.

| | |
| --- | --- |
| Mesh | `Body`, one skinned mesh with one material, `meta` |
| Triangles | 1,854 (limit 5,000) |
| Vertices | 1,031 in Blender |
| Bones | 56 (limit 60): 51 humanoid, `HeadVisual`, and 4 that only sway |
| Shape keys | none |
| Textures | `meta-atlas.png`, `meta-atlas-emission.png`, `meta-atlas-tint.png`, 256 x 256, for point filtering; 148 rows are used |
| Height | 1.75 m to the top of the hood; the view position is at 1.59 m |

## Commands

Run from the repository root. Blender 5.0 is not on PATH on this machine.

```bash
BLENDER="/c/Program Files/Blender Foundation/Blender 5.0/blender.exe"
"$BLENDER" -b --factory-startup --python-exit-code 1 --python "$PWD/blender/meta/build_meta.py"     # model, textures, Spec
"$BLENDER" -b --factory-startup --python-exit-code 1 --python "$PWD/blender/meta/export_meta.py"    # validate, export, read back
"$BLENDER" -b --factory-startup --python-exit-code 1 --python "$PWD/blender/meta/render_meta.py"    # pictures in dist/meta-review/
"$BLENDER" -b --factory-startup blender/meta/meta.blend --python "$PWD/blender/meta/meta_validate.py" # validate only
```

Each exits non-zero on any error. `build_meta.py --force` overwrites a
`.blend` that was edited by hand; `--draft` saves one that fails validation.
`render_meta.py -- --only idle,hues` renders some of the sheets (`rest`,
`idle`, `head`, `hands`, `point`, `walk`, `sit`, `reach`, `hues`).

## Files

| Path | Purpose |
| --- | --- |
| `build_meta.py` | Builds everything and saves `meta.blend`. Also writes the three textures and the two Spec files. |
| `meta_model.py` | The design: bone positions, the shape of every part, how each bends and how it is painted. |
| `meta_geo.py` | What cloth needs on top of the robot's kit: mirrored halves welded into one solid, strips and fans turned outward by an interior point, and paints that know the face they are painting. |
| `meta_spec.py` | Paths, names, the humanoid map, the extra bones and the signature colour. |
| `meta_validate.py` | Checks an open `.blend` against the contract below. The build and the export both gate on it. |
| `export_meta.py` | Exports the FBX and verifies the file. |
| `render_meta.py` | Review sheets: views, close-ups, poses, and the signature colour turned to other hues. |
| `meta.blend` | Generator output, stamped like `cass.blend`. Do not edit; change the scripts. |

Everything else the build writes goes under `meta_spec.PACKAGE`, which is
the avatar's package, `Packages/net.wirenook.meta-avatar`: `Textures/`,
`Spec/skeleton.json`, `Spec/model.json`, `BlenderExports/meta.fbx`. After
exporting, `scripts/cass.sh rebuild` makes the Unity side again
(`Editor/MetaBuild.cs` there), which is also what saves the new rest poses
with the model's import settings.

The robot's kit (`blender/bot/bot_geo.py`: the pixel canvas, the atlas
packer, the PNG writer, the mesh builder) and three modules of the cass
pipeline (`cass_spec`, `kitbash/stamp.py`, `export.py`) are imported, not
copied. A change to how cass is exported, or to the robot's kit, changes
this model too.

## How it is built

One pixel is 1/128 m and one texel of the atlas covers one square pixel of
surface, as on the robot. Faces are flat-shaded and unwrapped by projection
onto their own plane.

Unlike the robot, most of this figure bends. The robe, the torso, the
mantle, the cowl and the hood are each built as their left half, from the
middle of the front round to the middle of the back, and mirrored into the
same solid, so they are welded along the middle and the right side shares
the left's texels. A solid's weights are a function of where a point is;
under the mirror, `.L` and `.R` are swapped in whatever it returns.

- **The robe below the belt** follows the legs: at the hips it is the
  hips', below them it goes over to the thighs and at the knee to the
  shins, and across the figure it goes from the left leg to the right over
  14 pixels, so the middle of the front and the back hang between the legs.
  It is pleated: every other corner of its outline stands out and the ones
  between stand in, more towards the hem. There are no legs inside it. Its
  underside is closed, dark, and the boots come out through it.
- **The mantle** hangs from the chest; towards the shoulders it follows the
  shoulder and then, up to 55 %, the upper arm, so that it drapes when the
  arms come down from the T-pose.
- **The hood** is cross-sections from its rim back to its point, with a lip
  round the opening and a dark hollow 13 pixels deep behind it, closed by a
  black back.
- **The sleeves** widen to a cuff that hangs lower than it rises, hollow
  like the hood, with the wrapped wrist coming out of the dark.
- The hands, the boots, the belt's buckle, the book and the pouch are
  rigid solids, one bone each, as on the robot.

A paint is given the face it paints: where each corner lies on its canvas.
That is how the mantle's trim follows an edge that slopes, how a fold
darkens towards the corner that stands in, and how the stole and the sigil
sit exactly on the seam, half on each side. Faces that carry a seam are
placed on their island so that the seam is a texel boundary.

The build is deterministic: no randomness, no iteration over sets, and a PNG
writer without metadata.

## Contract

`meta_validate.py` checks all of this.

### Scene and skeleton

- Metres. The figure stands on Z = 0 facing -Y, its left side at +X, in a
  T-pose with palms down. Collection `Export` holds the armature `Armature`
  and the mesh `Body`, both at identity; the mesh is parented to the
  armature and has one Armature modifier. In the FBX both hang directly off
  the root.
- Bones: the humanoid map of `Spec/skeleton.json` (the cass names, without
  the eyes), and five more.
- **`Head` carries nothing.** A player's voice and nameplate follow the
  humanoid head bone, and this avatar moves it away on purpose, per viewer,
  to go unheard. So nothing is weighted to `Head` and it has no children.
  Everything of the head (the hood) is on `HeadVisual`, which rests exactly
  where `Head` does, under `Neck` beside it. Unity must make `HeadVisual`
  follow `Head` (a rotation constraint is enough; they share a parent and a
  position) and hide it from its wearer (`VRCHeadChop`, scale 0), because
  VRChat only shrinks `Head` itself in first person.
- `Sway.Hood`, `Sway.Hood.001` (under `HeadVisual`): the hood's point.
  `Sway.Sleeve.L`, `Sway.Sleeve.R` (under the lower arms): the lobe of each
  cuff, which should hang whichever way the arm turns. They are for physics
  and optional: left rigid, the figure still looks right. A build for
  mobile can leave the physics out; the bones cost nothing but their count.
- Knees are 0.6 pixels in front of the line from hip to ankle and elbows
  0.5 behind the line from shoulder to wrist, so that IK bends them the
  right way.

### Mesh

- One mesh, `Body`, one material slot, `meta`, no shape keys.
- Triangles and flat convex quads only; at most 5,000 triangles.
- UV layers `UVMap` and `Tile`, in that order. `UVMap` is the atlas. `Tile`
  has every corner at (0.5, 0.5), inside the tile the shared wirenook
  material never discards.
- At most four bones to a vertex, weights summing to 1. Every finger bone
  and every sway bone is followed by something.

### The signature colour

The trim, the runes, the gems and the lit ends of the index fingers are one
colour, which the wearer changes in game.

- In the atlas they are painted in **one hue, 185 degrees (0.5139)**, at
  four strengths: `sig-hi`, `sig`, `sig-lo`, `sig-dim` (`Spec/model.json`
  has their values). Nothing else in the atlas uses those colours.
- `meta-atlas-tint.png` is white on exactly those texels. Turning the hue
  of the texels under it by (wanted hue - 0.5139) gives any other signature
  colour with its light and dark kept; `render_meta.py -- --only hues`
  does that with a Hue/Saturation node and is the picture to compare with.
- `meta-atlas-emission.png` is white on the subset that glows: the runes
  of the stole and the hem, the dots of the trim, the sigil, the gems, the
  fingertips. The build fails if anything glows that is not in the tint
  mask, so emission taken from the turned colour always follows the wearer.
- The cloth is dark and near neutral (the palette's `grey-dark` and
  `night-4` families) so that any hue sits on it.

`Spec/model.json` also gives the view position, the middle of the hood's
opening, and the ends of the index fingers in the T-pose, in Unity's frame.

## Export

`export_meta.py` refuses a file that fails validation, exports with the cass
settings (binary FBX, Y up, Z forward, unit scale declared in the file,
deform bones only, no leaf bones, no animation), and bakes the axis change
into the data so that every node is at identity. It then checks the file as
stored and re-imported, as the cass and robot exports do, and this model's
own promises: the one mesh and slot, no shape keys, both UV layers
unchanged, every bone with its parent, and nothing weighted to `Head`.

## Not checked here

- Nothing was imported into Unity. That the humanoid importer accepts the
  T-pose and a head bone without weights is for the Unity side to confirm.
- The poses in the review sheets are turns of bones, not VRChat's IK.
- The robe has no legs inside and follows the legs it hides. Walking and
  sitting look right in the sheets; a deep crouch or a high kick will
  stretch it, and the stole widens between the legs in a long stride.
- An arm raised above the shoulder comes through the mantle, which only
  follows it part of the way.
- With the cuffs' sway bones rigid, the lobe of a cuff points at the hip
  when the arm hangs, and its tip rests against the robe, the book and the
  pouch, a pixel or two into them.
- The atlas has one texel of padding round each island and is meant for
  point filtering without mip maps.
