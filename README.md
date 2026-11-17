![cass, a VRChat avatar from wirenook.net](art/banner/banner.png)

# cass

Cassidy's VRChat avatar, built as a pipeline rather than a scene: the model
comes out of Blender, everything Unity needs is generated from it and from a
handful of spec files, the optimising happens at build time on a throwaway
copy, and uploads fill in their own metadata.

The model is a kitbash, and is itself generated: a CC0 body base
(SiroinoSotai) and a CC0 face (HENGE's Mizunashi Hiyori), with the hair,
rabbit ears, tail and outfit modelled in code around them. See
[Credits](#credits).

## How it fits together

```
blender/sources/ (body base, face) ─┐
blender/scripts/kitbash/ (hair,     ├─build─▶ blender/cass.blend, cass-lite.blend
  ears, tail, outfit, texture)     ─┘                 │ export, verified
                                                      ▼
                         Packages/net.wirenook.cass/BlenderExports/cass.fbx, cass-lite.fbx
                                        │  import rules applied in code
Spec/*.json ───────────────────────────▶│
                                        ▼
                         generated materials, FX animator, menus
                                        ▼
        Prefabs/cass-root.prefab        the one root avatar prefab (a variant of the model)
                    ▼
        Prefabs/Variants/cass.prefab        everyday upload
                    ▼
        Prefabs/Variants/cass-adv.prefab    adds flight, stations and hand tools
        Prefabs/Variants/cass-flashlight.prefab, cass-lantern.prefab   one real light each (extend cass)
                    ▼  at build time, on a copy
        lite model where asked ▶ Modular Avatar ▶ wirenook-assets ▶ Avatar Optimizer ▶ measured, checked, uploaded
```

| Path | What it is |
| --- | --- |
| `blender/` | The source assets, the generator that builds `cass.blend` and `cass-lite.blend` from them, and the headless scripts that validate and export those. |
| `Packages/net.wirenook.cass/` | The avatar, as a VPM package. `Spec/` holds the contracts, `BlenderExports/` the one place exports land, `Editor/` the generators, `Generated/`, `Materials/` and `Prefabs/` their output. |
| `modules/` | Six standalone packages the avatar builds on, as git submodules. Each has its own repository, version and README. |
| `Assets/` | The validation scene and development tools. Not shipped. |
| `tools/`, `art/` | The thumbnail composer, contact-sheet composer and banner. |

### The standalone packages

| Submodule | Package | What it provides |
| --- | --- | --- |
| [`wirenook-assets`](https://github.com/CassidyPrather/wirenook-assets) | `net.wirenook.assets` | The shared palette, materials, menu icons, sounds and the editor helpers the others build with. |
| [`locomotion`](https://github.com/CassidyPrather/locomotion) | `net.wirenook.locomotion` | Procedural locomotion generated from a gait model, and collider flight. |
| [`world-sync`](https://github.com/CassidyPrather/world-sync) | `net.wirenook.world-sync` | Leaving props in the world, with their position synced for late joiners. |
| [`avatar-stations`](https://github.com/CassidyPrather/avatar-stations) | `net.wirenook.avatar-stations` | A carry seat and a catch-up portal. |
| [`adventure-tools`](https://github.com/CassidyPrather/adventure-tools) | `net.wirenook.adventure-tools` | Laser pointer, megaphone, flashlight, lantern, screen notices. |

They are mounted as submodules and referenced in place
(`Packages/manifest.json` points at `modules/<repo>/Packages/<id>`), so one
checkout edits everything in one Unity project. Someone installing the
avatar from a VPM listing gets them as ordinary dependencies instead.

## Getting started

```bash
git clone --recurse-submodules https://github.com/CassidyPrather/cass-avatar
```

Requires Unity 2022.3.22f1 through a VPM client (prefer
[ALCOM](https://vrc-get.anatawa12.com/en/alcom/)), Blender 5.0, Python
3.11+ with Pillow and numpy, and the [.NET SDK](https://dotnet.microsoft.com/download)
11 for the headless checks.

Add these listings to your VPM client once, then add this folder as a
project and open it in Unity:

| Listing | For |
| --- | --- |
| `https://vpm.nadena.dev/vpm.json` | Modular Avatar, NDMF |
| `https://lilxyzw.github.io/vpm-repos/vpm.json` | lilToon |
| `https://vpm.anatawa12.com/vpm.json` | Avatar Optimizer |

## Everyday commands

These talk to the Unity editor you already have open; nothing needs to be
closed or restarted.

```bash
scripts/cass.sh build             # sources + modelled parts -> blender/cass.blend, cass-lite.blend
scripts/cass.sh export            # Blender -> BlenderExports/cass.fbx, cass-lite.fbx, validated
scripts/cass.sh rebuild           # regenerate materials, animators, menus, prefabs
scripts/cass.sh verify cass       # build the variant as an upload would, and check it
scripts/cass.sh verify cass android   # the same for another platform's build
scripts/cass.sh sheets cass       # contact sheets in dist/validation/cass/
scripts/cass.sh preview cass      # what an upload would send to VRChat
scripts/cass.sh platform android  # switch the editor to pc, android or ios
scripts/cass.sh upload cass       # build and upload for the editor's platform
scripts/cass.sh upload '.*' all   # every variant (a regex over slugs) for every platform
scripts/cass.sh live cass         # what VRChat holds for the uploaded variant
scripts/cass.sh publish cass      # send name, description, tags, visibility only
scripts/cass.sh bundle            # inspect the bundle the SDK built last
scripts/cass.sh all               # export, rebuild, verify every variant on every platform
```

The same things are in Unity's menu under `Tools > Wirenook`.

## The model contract

Blender validates these on export and Unity builds from them, so each name
is written down once, in `Packages/net.wirenook.cass/Spec/`.

- **`skeleton.json`**: one armature shared by every outfit, variant and
  fidelity level, mapped to Unity's humanoid bones by name. Its extra
  bones say what they are for: the body base's arm twist helpers name the
  bone they follow, and the first bone of each physics chain (ears, tail,
  hair) names its PhysBone settings.
- **`blendshapes.json`**: the shapes the `Body` mesh (the head) carries.
  - the 15 VRChat visemes (`vrc.v_*`);
  - VRChat's native face-tracking keys (Unified Expressions names, 102 in
    SDK 3.10.6), each tagged with a face region and whether it is required;
  - 44 MMD shapes under their Japanese names. MMD worlds find them on a
    mesh that must itself be called `Body`, directly under the avatar root.
- **`uv-tiles.json`**: toggles as UV tile discard. Every face carries a
  second UV set that only says which toggle group it belongs to, and the
  shader drops whole groups. A garment lists the body zones it covers, and
  a zone is drawn only while nothing covers it, so skin cannot clip through
  clothing and a hidden zone costs nothing to draw. It is one float per
  group on the material rather than a renderer per toggle, which is what
  lets the whole avatar be one mesh and one material slot.
- **`proportions.json`**: the figure is scaled to its `height` and stands
  `bootHeelHeight` off the ground. The other measurements described the
  placeholder; the body base's own proportions now stand in for them.

The model exists at two fidelity levels with the same objects, bones,
blendshapes and UV tiles: `cass.fbx` (about 49,000 triangles) and
`cass-lite.fbx` (about 16,600), which uses the body base's low-polygon mesh
and coarser modelled parts. The prefabs hold the full one; a build takes the
lite meshes instead for Android and iOS, and for any variant that asks.

How the model is built, what was changed about the source assets and the
contracts a hand-made replacement has to keep are in
[`blender/README.md`](blender/README.md).

### Textures

There is one texture, `Textures/cass-atlas.png`, baked by the model build.
It holds the face's painted texture (recoloured: blue eyes, brown lashes
and brows) and, beside it, the flat colours of
`Textures/cass-palette.toml` as solid cells. Everything but the head is
flat-coloured: every face maps to the centre of one cell, so nothing is
mirrored and mip-mapping cannot bleed. The body's skin cell is sampled from
the face texture, so the two match. The body keeps its own UVs in a
skin-coloured corner of the atlas, and about a third of the atlas is free
for painted detail later.

A second texture with the same layout, `Textures/cass-atlas-normal.png`,
carries the face's and the body base's own normal maps and is flat
elsewhere. Both sources are meant to be shaded through them: without the
face's, toon shadow creases around the mouth.

Detail that a texture would carry is geometry instead: stitching, seams,
pockets, belt loops, lacing and trims are thin strips and patches laid a
couple of millimetres above the surface (`kitbash/detail.py`), at the full
level only.

Materials are lilToon with no minimum brightness (in a dark world the
avatar is dark), and lilToon's Clipping Canceller is switched on for the
project so a face seen from very close is pushed back rather than cut open.
The avatar's material adds, in `CassMaterials.Look`: an outline coloured
from the texture under it (darker and a little more saturated, never plain
black), a faint rim light with a matching rim shade, and a softer, shorter
shadow than the props use.

## Gestures and face tracking

`Spec/gestures.json` is Cassidy's learned layout, one expression per
gesture per hand:

| Gesture | Left hand | Right hand |
| --- | --- | --- |
| Fist | Sleepy Content | Happy |
| Open | Sleepy Sad | Sleepy Happy |
| Thumbs up | Flummoxed | Excited |
| Finger gun | Afraid | Sad |
| Point | Angry | Smug |
| Peace | Hungry | Wink 1 |
| Rock | Heart Eyes | Wink 2 |

One expression shows at a time: while the right hand holds one, the left
hand's layer rests, so two recipes are never laid over each other.
Expressions are recipes over the shapes above, not extra blendshapes.

**With a face tracker.** The tracking keys are split into three blendshape
sets, eyes, brows and mouth, and each expression says which of those it
*owns*. While a tracker is live, holding a gesture fades out only the sets
it owns and animates only those regions; the tracker keeps the rest. Sleepy
Content closes your eyes while your tracked mouth goes on talking. Heart
Eyes and the scribbled Afraid eyes work the same way.

**Without one**, or with the menu's Face Tracking switch off, the sets stay
at zero, gestures animate the whole face, and an animated blink runs. It
pauses while a gesture owns the eyes, so a wink is never blinked through.

The gesture layers are FX layers 1 and 2, the two MMD worlds silence, and
they are the only layers that touch the MMD-named shapes.

**Ears and tail.** An expression can also name a `pose` from the same file:
perked, spread, relaxed, drooping, pinned back, or one ear cocked for a
wink. A pose turns the ear and tail bones, given per bone as degrees
forward, outward and of twist about the avatar's own axes. A layer of its
own reads both hands (the right hand wins when its expression has a pose),
so it keeps working in MMD worlds and with a face tracker. The ears pass
through holes in the hat's brim just above their roots, so poses bend them
higher up; their PhysBones swing around whatever pose is held.

## Variants and uploads

`Spec/variants.json` lists the upload variants. Each is a prefab variant of
the root prefab, or of another variant, with feature prefabs added as
children.

| Variant | Adds |
| --- | --- |
| `cass` | Default outfit with per-garment toggles, procedural locomotion, the Face Tracking switch. |
| `cass-lite` | The same, built from the low-polygon model on PC too. |
| `cass-adv` | Flight, a carry seat, a catch-up portal, laser pointer, megaphone, a flashlight and lantern, screen notices. |
| `cass-event` | The adventure build for leading a group: its laser pointer can ping the spot it points at, and a beacon shows where the wearer is through walls, with an arrow in everyone else's view when they are out of it. The ping's marker and the beacon are meshes of their own, which takes it to Medium; that is why it is not `cass-adv`. |
| `cass-party` | The everyday build with the party tricks: a bonk hammer, a vanishing act that leaves a log behind, a mosaic censor for the head or the whole body, and a busy sign. |
| `cass-flashlight`, `cass-lantern` | The adventure build with one real light: a spotlight in the flashlight, or a point light in the lantern, which can be placed in the world. They carry that one tool and not the other. A light ranks an avatar Poor and a second Very Poor, hence one each. On mobile the tool is there without its light. |

`scripts/cass.sh upload <slug>` builds the variant and sends it with:

- the **name** and **description** from the variant's upload profile; the
  description credits the body base and the face by name and author;
- the tags **`ai`** and **`agplv3`**, plus a tag for each feature the
  variant actually contains, highest priority first, within VRChat's limit
  of ten (VRChat lower-cases tags and stores them as `author_tag_*`);
- visibility **public**;
- a **thumbnail** with no text: a cut-out render of the built avatar's
  head and shoulders, and one icon per kind of feature (`tools/thumbnail/`).
  It repeats nothing VRChat already shows beside it.

It refuses to upload if the description does not mention
`github.com/CassidyPrather/cass-avatar`, if a required tag is missing, or if
the avatar would not be public. A hook applies the same check to uploads
made by hand from the SDK panel. These are guardrails against forgetting,
not locks: the policy is `Runtime/Core/UploadGuard.cs`, and removing the
upload profile from an avatar switches the check off.

VRChat asks whoever uploads to confirm they hold the rights to the
content. That dialog is left to you. It can come up as a window of its
own ("Copyright ownership agreement") that blocks the whole editor, and
`upload` waits behind it without saying so; if an upload seems stuck,
look at Unity.

Each variant uploads to its own avatar id, kept on its prefab once the
first upload has reserved one. A variant that extends another would
inherit its parent's id like any other property and replace the parent's
avatar on upload, so the rebuild clears inherited ids, `verify` reports
any two variants that share one, and `upload` refuses.

Four things about VRChat's side that the scripts allow for:

- **A first upload comes out private.** The SDK reserves an id, then
  uploads with the record VRChat returned for the reservation rather than
  the one it was given. `upload` reads the record back afterwards and sends
  it again if it does not pass the policy; `publish` does only that step.
- **Descriptions are stored with lookalike punctuation**
  (`github․com⁄CassidyPrather⁄…`), so the link is there to read but not to
  click, and the policy check folds those characters back before it looks
  for the link.
- **The SDK signs itself out on every script reload** and back in only
  once its control panel is drawn. The commands open the panel and wait.
- **An unchanged thumbnail stops an update.** VRChat refuses a file
  identical to the one it holds, and the SDK sends the picture before the
  bundle, so the avatar itself never goes out. `upload` compares the
  picture it would send against VRChat's and leaves it out when they match.

`scripts/cass.sh bundle` opens the file the SDK built last and reports
which vertex data each mesh kept, which shaders it carries, and a picture
(`dist/validation/bundle.png`). Unity strips vertex channels it believes
no shader reads when it packs a bundle, and the outfit toggles live in the
second UV channel, so this is worth a look after anything changes in the
materials. The picture is taken without the avatar's animator running, so
it shows the avatar as it rests, which is also what someone whose safety
settings block its animations sees. The build logs a shader error from lilToon
(`unrecognized identifier 'CBUFFER_START'`); it comes from a pass that
never draws, and the uploaded bundle renders correctly.

## Platforms

A variant is built for PC, Android and iOS from the same prefab; the
differences are made at build time, on the copy. `Spec/variants.json`
gives each variant a mobile rank target beside its PC one, and can narrow
its `platforms`.

`verify`, `report` and `sheets` take a platform and build as that
platform's would without touching the editor's build target, so the mobile
result can be measured and looked at in seconds. An upload is different:
the SDK builds for the editor's active target, so switch first with
`scripts/cass.sh platform android` (Unity reimports the project the first
time), upload, and switch back. All platforms of a variant upload to the
same avatar id.

A mobile build first takes its meshes from the lite model
(`CassBuildPlugin`). Then, in `net.wirenook.assets`' build plugin, it:

- **leaves out everything marked PC-only** (`WirenookPcOnly`), but keeps
  the expression parameters those things declare. VRChat syncs parameters
  by position in the list, so the list must be identical on every
  platform; `verify` compares it against the PC build's.
- **cuts hidden UV tiles out of the mesh.** No mobile shader can discard
  them, so what the PC build hides at rest (skin under clothing) is
  removed for good, through Avatar Optimizer.
- **swaps every material for a VRChat mobile shader:** Toon Lit, or the
  additive particle shader for glows. `verify` fails on any other shader.
- **removes what VRChat disables there:** audio sources, lights and
  colliders. They would do nothing and each ranks a mobile avatar Very
  Poor. A station keeps working without its collider, because VRChat gives
  a station that has none a trigger of its own.

What that costs on Android and iOS:

| Left out | Why |
| --- | --- |
| Garment toggles (the Outfit menu), expressions that swap UV tiles | They work by discarding UV tiles |
| Flight | It is a collider to stand on, and avatar colliders are disabled |
| Screen notices | Drawn by a custom shader |
| The light in `cass-flashlight` and `cass-lantern` | Avatar lights are disabled; the tool is still there and can still be placed, unlit |
| All sound | Audio sources are disabled |

| Variant | Mobile rank | Triangles | Skinned + static meshes | Material slots |
| --- | --- | --- | --- | --- |
| `cass`, `cass-lite` | Medium | 14,936 | 2 + 0 | 2 |
| `cass-adv` | Very Poor | 17,968 | 2 + 3 | 7 |
| `cass-flashlight` | Very Poor | 17,380 | 2 + 4 | 8 |
| `cass-lantern` | Very Poor | 17,526 | 2 + 5 | 9 |

`cass` is 64 triangles under Medium's limit of 15,000, so anything added to
the lite level has to be paid for there. The face is 8,500 of them, because
it is the same mesh at both levels; the stitched details are left out of
the lite level altogether, as are the folded edges of the waistband,
hems and collar.

The three adventure variants keep the carry seat and the catch-up portal
on mobile, which is what they are worn for, and pay for it in rank: the
props that are left in the world are separate meshes with their own
material slots, and mobile allows two of each before Very Poor. Mobile
users see a Very Poor avatar only when they choose to show it. The mobile
build of `cass-flashlight` or `cass-lantern` is the same avatar with the
tool dark.

VRChat also has hard limits on mobile (8 PhysBone components, 16
contacts, 150 constraints, among others) past which it strips every such
component whatever the viewer chose. `verify` checks those; the fullest
variant uses 12 of the 16 contacts.

## Checking the work

`scripts/cass.sh verify <slug>` runs the real build on a copy and checks
what came out: the performance rank against the variant's target, that
`Body` and the gesture layers are still where MMD worlds expect them, that
the optimiser kept every viseme, tracking and MMD shape, the synced
parameter and station budgets, that no material has a brightness floor,
and that everything the FX layers scale or switch rests the way they start
it (a prop that relies on the animator to hide it shows permanently for
anyone who has the avatar's animations blocked).
With the SDK control panel open it also runs the SDK's own upload
validation on the result. Anything that fails stops an upload after the
build, so it is cheaper to hear about it here (it is how sound effects
that did not load in the background were found).

`scripts/cass.sh sheets <slug>` photographs the built avatar in
`Assets/Scenes/Validation.unity` and writes eight labelled contact sheets to
`dist/validation/<slug>/`:

1. **Cameras**: sixteen fixed views, from full body to nose-to-nose (for
   near-plane clipping), including from above and below.
2. **Lighting**: seven conditions, including no light at all (the avatar
   should go black), far too bright (it should not blow out) and saturated
   coloured lights.
3. **Animations**: VRChat's own walk, run, crouch, crawl, sit, fall, AFK
   and emotes.
4. **Range of motion**: each joint group pushed to both ends of its
   humanoid range, plus a squat, a high kick and a hug. This is where
   clothing and skin intersect.
5. **Expressions**: every gesture expression.
6. **Visemes**.
7. **Outfit**: each garment taken off in turn, then all of them, to check
   the skin underneath comes back whole.
8. **Features**: each optional feature switched on by itself.

The sheets show the avatar after the build, so what you review is what
would be uploaded. Open the scene to look around by hand; the cameras and
lighting conditions are ordinary objects in it.

## Build-time optimisation

Nothing is merged or baked in the project. The prefabs stay modular (nine
meshes, a feature prefab per gadget) and the build does the work on a
copy:

- **Avatar Optimizer** merges the meshes, merges identical material slots,
  drops blendshapes and bones nothing uses, and trims the animator.
- **`net.wirenook.assets`** adds two steps before it. Optimisers only merge
  renderers that are alike in every way they can see, so the build makes
  hand-held props agree with the body (same root bone, bounds, probe
  anchor, and the same animated material properties) and removes the
  editor-only marker components that would otherwise make an optimiser
  give up.
- Props that can be left in the world (the seat, the portal) are built as
  plain rigid meshes instead. Merged into the avatar they would be culled
  with it, and vanish whenever the avatar itself was out of view.
- Every toggle is something a merged mesh can still do: UV tile discard
  for the outfit, scaling a bone to nothing for props.

| Variant | Rank | Triangles | Skinned + static meshes | Material slots | Bones | Synced bits |
| --- | --- | --- | --- | --- | --- | --- |
| `cass` | Good | 48,812 | 2 + 0 (from 9) | 2 (from 9) | 69 | 5 of 256 |
| `cass-lite` | Good | 16,618 | 2 + 0 (from 9) | 2 (from 9) | 69 | 5 of 256 |
| `cass-adv` | Good | 52,178 | 2 + 4 | 8 | 80 | 91 of 256 |
| `cass-flashlight` | Poor (one light) | 51,590 | 2 + 5 | 9 | 75 | 157 of 256 |
| `cass-lantern` | Poor (one light) | 51,736 | 2 + 6 | 10 | 75 | 157 of 256 |

The second skinned mesh is what stands between this and Excellent. It is
the head: Avatar Optimizer keeps meshes with blendshapes apart, because
every vertex added to such a mesh makes each expression cost more. That
is the better trade for real performance, so it is left alone. Only the
head (named `Body`, for MMD worlds) carries blendshapes; the body's skin
merges with the clothes.

On PC the skin under a garment is still in the mesh, discarded by the
shader, so that garments can be taken off. On mobile it is cut out.

No atlasing happens at build time: the model is built with its one atlas.

## Status

**Five variants are uploaded and public**, for PC, Android and iOS, with
the second pass of the model described here. The first pass was worn on
PC; this one has not been worn yet.

| Variant | Avatar id | Platforms uploaded |
| --- | --- | --- |
| `cass` | `avtr_83eafc89-950e-4553-bb36-c37238333069` | PC, Android, iOS |
| `cass-lite` | `avtr_df376716-743f-4bde-a5cc-98ddec85a313` | PC, Android, iOS |
| `cass-adv` | `avtr_5b291f6b-6058-4b39-83b2-382596f7b6d9` | PC, Android, iOS |
| `cass-flashlight` | `avtr_a22b0123-710f-49f9-a2a5-01870c26a4e9` | PC, Android, iOS |
| `cass-lantern` | `avtr_411ef326-6e48-4d16-ba22-48299840102c` | PC, Android, iOS |

**`cass` and `cass-adv` have been worn in the VRChat client on PC, which
is where the portal's pop-out, the notices' early exit and the thumbnails
were found wanting; the fixes for those have not been tried in the client
yet. The Android and iOS builds and the two real-light variants have not
been worn at all.** Everything below was checked in Blender, in the Unity
editor, against VRChat's API, or headless. `docs/POSTMORTEM.md` has the
history, the gotchas and the open issues.

Checked:

- Both Blender exports validate against the specs with no errors, and each
  exported file is read back and compared (names, bones, shape keys, UVs,
  orientation).
- All five variants build through Modular Avatar and Avatar Optimizer for
  PC, Android and iOS, and pass `scripts/cass.sh verify`: the rank each is
  held to, the MMD mesh name and layer order intact after the build, every
  viseme, required tracking key and MMD shape still present, budgets
  respected, no brightness floor.
- The contact sheets for `cass` render and were looked at: all fourteen
  expressions (heart eyes and the scribbled Afraid eyes among them), each
  garment taken off with whole skin underneath, the cameras and the poses,
  and the face under harsh, dim and coloured light.
- All five uploaded through `scripts/cass.sh upload` for all three
  platforms, with the editor switched to each, and VRChat's records read
  back matching the upload policy (source link, required tags, public).
  The uploaded bundles of this model have not been re-opened with
  `scripts/cass.sh bundle`; the placeholder's were.
- Headless tests: 22 for the avatar's core logic, 11 for the thumbnail
  composer, and each submodule's own suite.

Not checked, because only the client can:

- **Face tracking hand-over.** The design follows VRChat's documentation
  for SDK 3.10.6, but that documentation does not say what happens when an
  animation and a tracker drive the same blendshape, which is why gestures
  only animate shapes the tracker is not mapped to while one is live.
- **MMD worlds**, beyond the mesh name and layer order.
- **Every gadget in use**: collider flight, the carry seat, the portal's
  station, the laser's raycast, the screen notice in a headset. Each
  submodule's README says what its own unknowns are.
- **Synced world positions.** The receiving half is checked in the editor
  (a dropped prop reconstructs within 3 cm across a ±512 m world); the half
  that measures the position on the wearer's client only runs in game.
- **How the locomotion feels**, and how it sits with real tracking.
- **Hand poses**: props sit in the hand pointing where the fingers point,
  and the fingers do not close around them.
- **The new model in motion.** The ear and tail poses, the arm twist
  constraints, the hair, ear and tail physics and the eye-look limits are
  generated and build cleanly, but nothing has seen them move. The ear
  poses are not in the contact sheets, which sample the expression clips
  and not the pose layer.

Known gaps:

- The model is a second pass, modelled by script and judged from renders
  and one round of notes from wearing the first. The face is a stand-in
  from another avatar, and its expressions are mild. The outfit is
  plainer than the design's skirt was. There are no socks. Garment
  openings are hollow and rely on the double-sided material.
- With the sweater and the shorts both switched off the body is bare: the
  base is a smooth doll body with no underwear layer. Parked, by choice.
- The ears clip the hat's brim when a pose or physics bends them far;
  they have holes to stand in, not room to move.
- Under the chin, the face texture's painted shadow is stretched where the
  head's neck was narrowed to meet the body's.
- The human ears of the face mesh are still there, under the side hair.
- The hair is fitted under the hat, so with the hat switched off it is a
  little flattened where the hat sits. Where the fringe's strands meet at
  the parting they still run into each other.
- Nothing fades or dithers out as a viewer comes close; lilToon's Clipping
  Canceller pushes near geometry back instead.
- Held tools have no hand poses of their own.
- The locomotion clips are baked on a generic rig and retargeted, not
  fitted to this avatar; `LocomotionBuild.BakeFor` exists for that.
- Nothing is published: no releases, and the repositories are not on the
  VPM listing.

## Development

```bash
scripts/check-meta.sh          # every visible file has a committed .meta
scripts/check-manifests.py     # package.json sanity across Packages/
scripts/format.sh --check      # dotnet-format over the CI-visible C#
scripts/test.sh                # headless NUnit run of Runtime/Core + Tests
python tools/thumbnail/test_thumbnail.py
scripts/compile-check.py Packages/net.wirenook.cass   # type-check without the editor
scripts/unity-refresh.sh       # recompile the open editor once everything type-checks
```

Pre-commit hook: `git config core.hooksPath .githooks`

[`SKILL.md`](SKILL.md) has the rules that are easy to break and how to
drive the open editor from scripts.

### Releasing

The avatar is versioned in `Packages/net.wirenook.cass/package.json`.

1. Bump `version`, commit and push.
2. Create a GitHub release tagged with that version. CI attaches the `.zip`
   and `.unitypackage`.
3. Each submodule releases the same way from its own repository.
4. Add the repositories to the listing's `githubRepos`
   ([CassidyPrather/vpm](https://github.com/CassidyPrather/vpm)) once.

## Legal

Copyright 2026 Cassidy Prather <cassidy@wirenook.net>

Everything in this repository henceforth is licensed under
[AGPLv3](https://www.gnu.org/licenses/agpl-3.0.html) (See `LICENSE`) unless
otherwise specified.

As a special exception, the copyright holders give permission to link this
Program with the VRChat SDK and with Unity Technologies' proprietary engine
components, and to convey the resulting work under terms of your choice,
provided that you also convey the Corresponding Source of this Program under
the terms of the GNU Affero General Public License version 3 in all other
respects. (This exception also in `LICENSE_ADDENDUM`.)

## Credits

The body is [SiroinoSotai](https://siroinoworks.booth.pm/items/8268676) by
しろいの (Siroino Works), and the face is from
[水無ひより / Mizunashi Hiyori](https://booth.pm/en/items/6120660) by
ひみこ / HENGE. Both are CC0. Neither author was involved in or endorses
this avatar.

Descended from https://github.com/vrchat-community/template-package
([VRCHAT DISTRO LICENSE FILE](https://github.com/vrchat-community/template-package/blob/d9cf13fe9f56867cbf7315a4dbbf1901bc1537ec/Packages/com.vrchat.core.bootstrap/License.md))

Third-party material is inventoried in [CREDITS.md](CREDITS.md).
