![cass, a VRChat avatar from wirenook.net](art/banner/banner.png)

# cass

Cassidy's VRChat avatar, built as a pipeline rather than a scene: the model
comes out of Blender, everything Unity needs is generated from it and from a
handful of spec files, the optimising happens at build time on a throwaway
copy, and uploads fill in their own metadata.

The model is currently a **placeholder**. The pipeline around it is real.

## How it fits together

```
blender/cass.blend ──export──▶ Packages/net.wirenook.cass/BlenderExports/cass.fbx
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
        Modular Avatar ▶ wirenook-assets ▶ Avatar Optimizer ▶ measured, checked, uploaded
```

| Path | What it is |
| --- | --- |
| `blender/` | `cass.blend` and the headless scripts that validate and export it. |
| `Packages/net.wirenook.cass/` | The avatar, as a VPM package. `Spec/` holds the contracts, `BlenderExports/` the one place exports land, `Editor/` the generators, `Generated/`, `Materials/` and `Prefabs/` their output. |
| `modules/` | Five standalone packages the avatar builds on, as git submodules. Each has its own repository, version and README. |
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
scripts/cass.sh export            # Blender -> BlenderExports/cass.fbx, validated
scripts/cass.sh rebuild           # regenerate materials, animators, menus, prefabs
scripts/cass.sh verify cass       # build the variant as an upload would, and check it
scripts/cass.sh verify cass android   # the same for another platform's build
scripts/cass.sh sheets cass       # contact sheets in dist/validation/cass/
scripts/cass.sh preview cass      # what an upload would send to VRChat
scripts/cass.sh platform android  # switch the editor to pc, android or ios
scripts/cass.sh upload cass       # build and upload for the editor's platform
scripts/cass.sh live cass         # what VRChat holds for the uploaded variant
scripts/cass.sh publish cass      # send name, description, tags, visibility only
scripts/cass.sh bundle            # inspect the bundle the SDK built last
scripts/cass.sh all               # export, rebuild, verify every variant on every platform
```

The same things are in Unity's menu under `Tools > Wirenook`.

## The model contract

Blender validates these on export and Unity builds from them, so each name
is written down once, in `Packages/net.wirenook.cass/Spec/`.

- **`skeleton.json`**: one armature shared by every outfit and variant,
  mapped to Unity's humanoid bones by name.
- **`blendshapes.json`**: the shapes the `Body` mesh carries.
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
- **`proportions.json`**: the body proportions the model is built to,
  used wherever the character design leaves one open.

Modelling notes for a human replacing the placeholder are in
[`blender/README.md`](blender/README.md).

### Textures

Flat colour comes from a small swatch texture
(`Textures/cass-palette.toml`): every face maps to the centre of one solid
cell. Nothing is mirrored and nothing is wasted, and because cells are
solid, mip-mapping and atlasing cannot bleed. Painted detail will need real
textures later; the flat fills can stay.

Materials are lilToon with no minimum brightness (in a dark world the
avatar is dark), and lilToon's Clipping Canceller is switched on for the
project so a face seen from very close is pushed back rather than cut open.

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

The right hand's layer sits above the left's, so where both touch the same
blendshape the right hand wins. Expressions are recipes over the shapes
above, not extra blendshapes.

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

## Variants and uploads

`Spec/variants.json` lists the upload variants. Each is a prefab variant of
the root prefab, or of another variant, with feature prefabs added as
children.

| Variant | Adds |
| --- | --- |
| `cass` | Default outfit with per-garment toggles, procedural locomotion, the Face Tracking switch. |
| `cass-adv` | Flight, a carry seat, a catch-up portal, laser pointer, megaphone, a flashlight and lantern, screen notices. |
| `cass-flashlight`, `cass-lantern` | The adventure build with one real light: a spotlight in the flashlight, or a point light in the lantern, which can be placed in the world. They carry that one tool and not the other. A light ranks an avatar Poor and a second Very Poor, hence one each. PC only. |

`scripts/cass.sh upload <slug>` builds the variant and sends it with:

- the **name** and **description** from the variant's upload profile;
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
differences are made at build time, on the copy. `Spec/variants.json` can
narrow a variant's `platforms` (the real-light variants are PC only) and
gives each a mobile rank target beside its PC one.

`verify`, `report` and `sheets` take a platform and build as that
platform's would without touching the editor's build target, so the mobile
result can be measured and looked at in seconds. An upload is different:
the SDK builds for the editor's active target, so switch first with
`scripts/cass.sh platform android` (Unity reimports the project the first
time), upload, and switch back. All platforms of a variant upload to the
same avatar id.

What a mobile build does, in `net.wirenook.assets`' build plugin:

- **Leaves out everything marked PC-only** (`WirenookPcOnly`), but keeps
  the expression parameters those things declare. VRChat syncs parameters
  by position in the list, so the list must be identical on every
  platform; `verify` compares it against the PC build's.
- **Cuts hidden UV tiles out of the mesh.** No mobile shader can discard
  them, so what the PC build hides at rest (skin under clothing) is
  removed for good, through Avatar Optimizer.
- **Swaps every material for a VRChat mobile shader:** Toon Lit, or the
  additive particle shader for glows. `verify` fails on any other shader.
- **Removes audio sources,** which VRChat mutes on mobile and still ranks
  Very Poor.

What that costs on Android and iOS:

| Left out | Why |
| --- | --- |
| Garment toggles (the Outfit menu), expressions that swap UV tiles | They work by discarding UV tiles |
| Flight, carry seat, catch-up portal | Each needs a collider; one collider ranks a mobile avatar Very Poor |
| Screen notices | Drawn by a custom shader |
| Real lights | VRChat switches avatar lights off there; those variants are PC only |
| All sound | Audio sources are muted and rank Very Poor |

| Variant | Mobile rank | Triangles | Skinned meshes | Material slots |
| --- | --- | --- | --- | --- |
| `cass` | Medium | 6,618 | 2 | 2 |
| `cass-adv` | Poor | 8,356 | 2 | 4 |

`cass-adv` keeps the laser pointer, megaphone, flashlight and lantern on
mobile. Its four material slots (the avatar's palette twice, the props'
palette, the glow) are the edge of Poor; a fifth would hide it from
everyone on mobile.

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

Nothing is merged or baked in the project. The prefabs stay modular (six
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
| `cass` | Good | 8,202 | 2 + 0 (from 6) | 2 (from 6) | 59 | 5 of 256 |
| `cass-adv` | Good | 11,568 | 2 + 4 (from 11 + 1) | 8 (from 19) | 70 | 91 of 256 |
| `cass-flashlight` | Poor (one light) | 10,980 | 2 + 5 | 9 | 65 | 157 of 256 |
| `cass-lantern` | Poor (one light) | 11,126 | 2 + 6 | 10 | 65 | 157 of 256 |

The second skinned mesh is what stands between this and Excellent. It is
the face: Avatar Optimizer keeps meshes with blendshapes apart, because
every vertex added to such a mesh makes each expression cost more. That
is the better trade for real performance, so it is left alone. A final
model could put only the face (named `Body`, for MMD worlds) on that mesh
and let the rest of the skin merge.

Texture atlasing is not used: the flat palettes leave nothing to atlas.
When painted textures arrive, [TexTransTool](https://ttt.rs64.net/) is the
tool for it.

## Status

**Four placeholder variants are uploaded and public:**

| Variant | Avatar id | Platforms uploaded |
| --- | --- | --- |
| `cass` | `avtr_83eafc89-950e-4553-bb36-c37238333069` | PC, Android, iOS |
| `cass-adv` | `avtr_5b291f6b-6058-4b39-83b2-382596f7b6d9` | PC, Android, iOS |
| `cass-flashlight` | `avtr_a22b0123-710f-49f9-a2a5-01870c26a4e9` | PC |
| `cass-lantern` | `avtr_411ef326-6e48-4d16-ba22-48299840102c` | PC |

**`cass` and `cass-adv` have been worn in the VRChat client on PC, which
is where the portal's pop-out, the notices' early exit and the thumbnails
were found wanting; the fixes for those have not been tried in the client
yet. The Android and iOS builds and the two real-light variants have not
been worn at all.** Everything below was checked in Blender, in the Unity
editor, against VRChat's API, or headless. `docs/POSTMORTEM.md` has the
history, the gotchas and the open issues.

Checked:

- The Blender export validates against the specs with no errors, and the
  exported file is read back and compared (names, bones, shape keys, UVs,
  orientation).
- All four variants build through Modular Avatar and Avatar Optimizer for
  every platform they list, and pass `scripts/cass.sh verify`: the rank each is held to, the MMD mesh name and layer order
  intact after the build, every viseme, required tracking key and MMD
  shape still present, budgets respected, no brightness floor.
- The contact sheets render and were looked at: all fourteen expressions,
  the outfit zones, the lighting extremes, and each feature in place.
- All four uploaded through `scripts/cass.sh upload`, `cass` and `cass-adv`
  for all three platforms with the editor switched to each. VRChat's
  records read back with the source link, the required tags (and
  `cass-adv`'s eight feature tags) and public visibility, and each
  uploaded bundle, opened again in the editor, renders correctly with both
  UV channels intact.
- Headless tests: 19 for the avatar's core logic, 11 for the thumbnail
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

Known gaps:

- The model is a placeholder: no eyelids (closing the eyes squashes the
  decals), ears pass through the hat brim without a hole, garment openings
  are hollow and rely on the double-sided material. `blender/README.md`
  lists the rest.
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

Descended from https://github.com/vrchat-community/template-package
([VRCHAT DISTRO LICENSE FILE](https://github.com/vrchat-community/template-package/blob/d9cf13fe9f56867cbf7315a4dbbf1901bc1537ec/Packages/com.vrchat.core.bootstrap/License.md))

Third-party material is inventoried in [CREDITS.md](CREDITS.md).
