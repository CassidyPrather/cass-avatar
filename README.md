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
        Prefabs/Variants/cass-lite.prefab   the one for tight performance (on the root, not on cass)
        Prefabs/Variants/cass.prefab        everyday upload
                    ▼
        Prefabs/Variants/cass-adv.prefab    adds flight, stations, hand tools and what a group needs
        Prefabs/Variants/cass-flashlight.prefab, cass-lantern.prefab   one real light each (extend cass)
        Prefabs/Variants/cass-contacts.prefab   the contact toys and the shape collector (extends cass)
                    ▼  at build time, on a copy
        lite model where asked ▶ Modular Avatar ▶ wirenook-assets ▶ Avatar Optimizer ▶ measured, checked, uploaded
```

| Path | What it is |
| --- | --- |
| `blender/` | The source assets, the generator that builds `cass.blend` and `cass-lite.blend` from them, and the headless scripts that validate and export those. |
| `Packages/net.wirenook.cass/` | The avatar, as a VPM package. `Spec/` holds the contracts, `BlenderExports/` the one place exports land, `Editor/` the generators, `Generated/`, `Materials/` and `Prefabs/` their output. |
| `modules/` | Eight standalone packages the avatar builds on, as git submodules, each with its own repository, version and README; and beside them the world, a Unity project of its own. |
| `Assets/` | The validation scene and development tools. Not shipped. |
| `tools/`, `art/` | The thumbnail composer, contact-sheet composer and banner. |

### The standalone packages

| Submodule | Package | What it provides |
| --- | --- | --- |
| [`wirenook-assets`](https://github.com/CassidyPrather/wirenook-assets) | `net.wirenook.assets` | The shared palette, materials, menu icons, sounds and the editor helpers the others build with. |
| [`locomotion`](https://github.com/CassidyPrather/locomotion) | `net.wirenook.locomotion` | Procedural locomotion generated from a gait model, collider flight, a stepladder for a lifted play space, and a standing nap while away. |
| [`world-sync`](https://github.com/CassidyPrather/world-sync) | `net.wirenook.world-sync` | Leaving props in the world, with their position synced for late joiners: one at a time, or many on a shared bus. |
| [`avatar-stations`](https://github.com/CassidyPrather/avatar-stations) | `net.wirenook.avatar-stations` | A carry seat, a catch-up portal, and seats for a group in a ring or facing a screen. |
| [`adventure-tools`](https://github.com/CassidyPrather/adventure-tools) | `net.wirenook.adventure-tools` | Laser pointer (with a ping), megaphone, flashlight, lantern, screen notices, a beacon. |
| [`party-tricks`](https://github.com/CassidyPrather/party-tricks) | `net.wirenook.party-tricks` | A bonk hammer, a vanishing act, a mosaic censor, a busy sign. |
| [`shape-collector`](https://github.com/CassidyPrather/shape-collector) | `net.wirenook.shape-collector` | A collect-the-shapes course to lay out in any world; the pilot for world-sync's bus. |
| [`contacts`](https://github.com/CassidyPrather/contacts) | `net.wirenook.contacts` | VRChat's standard contact tags put to use: reactions to each, a tester that emits each and launches things, a shield that burns, targets to set down. |

`contacts` was made in the session described under [Status](#status), and
its repository exists only on the machine it was made on until it is
pushed; the address above is where it is meant to go.

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
scripts/cass.sh build             # sources + modelled parts -> blender/cass.blend, cass-lite.blend, and each other wardrobe's
scripts/cass.sh export            # Blender -> BlenderExports/cass.fbx, cass-lite.fbx, and each other wardrobe's, validated
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
scripts/cass.sh retire cass-party # delete a deprecated variant's avatar from VRChat, for good
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
  hair, skirt) names its PhysBone settings. A chain that carries one
  garment also names that garment's UV tile, and `colliders` lists the
  capsules along the legs that keep the skirt's chains off them. A bone
  with `follow` is turned part of the way with a limb by a constraint (the
  skirt's two lifts, with the thighs), and a chain marked `pcOnly` has
  physics that Android and iOS builds leave out.
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
  clothing and a hidden zone costs nothing to draw. A tile's switch is a
  rule: the value of its parameter that shows it, what else it needs and
  what it gives way to. The shorts give way to the skirt, the vest is only
  shown over the sweater it is fitted to, and the short and the long hair
  are one switch. A switch can name the value it `rests` at where its
  tile's resting state does not say (the shorts rest hidden under the
  skirt with their switch on), and a tile marked `"mobile": false` rests
  shown on PC and is cut from Android and iOS builds, which have no room
  for it. The grid is four by four, the most the shader has, and
  every tile is now in use. It is one float per
  group on the material rather than a renderer per toggle, which is what
  lets the whole avatar be one mesh and one material slot.
- **`proportions.json`**: the figure is scaled to its `height` and stands
  `bootHeelHeight` off the ground. The other measurements described the
  placeholder; the body base's own proportions now stand in for them.

The model exists at two fidelity levels with the same objects, bones,
blendshapes and UV tiles: `cass.fbx` (about 58,700 triangles) and
`cass-lite.fbx` (about 18,900, of which 16,300 are shown at rest), which
uses the body base's low-polygon mesh and coarser modelled parts. The prefabs hold the full one; a build takes the
lite meshes instead for Android and iOS, and for any variant that asks.

How the model is built, what was changed about the source assets and the
contracts a hand-made replacement has to keep are in
[`blender/README.md`](blender/README.md).

### Textures

There is one texture, `Textures/cass-atlas.png`, baked by the model build.
It holds the face's painted texture (recoloured: blue eyes, brown lashes
and brows) and, beside it, the flat colours of
`Textures/cass-palette.toml` as solid cells. Everything but the head and
the skirt is flat-coloured: every face maps to the centre of one cell, so nothing is
mirrored and mip-mapping cannot bleed. The body's skin cell is sampled from
the face texture, so the two match. The body keeps its own UVs in a
skin-coloured corner of the atlas. The skirt's gingham is a painted patch
that repeats every two centimetres, and each of the skirt's faces is laid on
it at one scale.

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
so it keeps working in MMD worlds and with a face tracker. The ears bend
from the base: the first bone takes most of each turn. They pass through
holes in the hat's brim just above their roots, though, so `posesWhile`
gives a second set for while the hat is worn, which bends them higher up
and barely moves the base; the layer follows the hat's switch. Their
PhysBones swing around whatever pose is held, and may swing furthest at
the base too.

**A hand that is busy makes no face.** A feature that uses a hand's
gesture as a button says so with a `WirenookHandClaim`
(`net.wirenook.assets`): the laser pointer that pings on a fist, and
anything that is aimed before it is set down (below). While such a
feature's parameter is on, and afterwards until that hand has relaxed or
1.2 s have passed, the expressions, the blink, the tracking hand-over and
the ear poses all read that hand as making no gesture, so a trigger pull
that places a portal is not also a grin. The other hand's expressions go
on working. The generator finds the claims on every feature a variant
lists and gives the avatar one small layer per claimed hand, after the two
gesture layers.

**Away.** While the wearer is away, the avatar crashes. That is VRChat's
own AFK or the menu's "AFK" switch (`WN/Away`); the feature is
`Wirenook Away` in `net.wirenook.party-tricks`, whose README has the
whole of it. The body locks in a standing pose and stops following the
headset, the mesh tears and throws out spikes, an error window reading
AFK stands at the edge of the avatar on each viewer's own side, a
device-unplugged cue plays and a low buzz sets in. The avatar adds two
things of its own, in layers that already owned those shapes and bones
(the blink and the poses) and are outside the two that MMD worlds
silence: the eyes stop blinking and each becomes a small blue error
screen with a sad face, and the ears hang. The screen is the toon
shader's (`net.wirenook.assets`), drawn on the faces of the eyes' UV
tile; where on an eye its picture goes is written into the model's third
UV set as it is imported (`CassModelImporter`).

The switch cannot mute the microphone, because VRChat gives an avatar no
way to. `modules/party-tricks/tools/away_mic.py`, run beside VRChat with
OSC enabled, does it from outside, and unmutes on return only if the mute
was its own and nothing has touched the microphone since.

The nap that used to stand here (`Wirenook Nap`, `net.wirenook.locomotion`)
is still in its package; no variant carries it now.

## Variants and uploads

`Spec/variants.json` lists the upload variants. Each is a prefab variant of
the root prefab, or of another variant, with feature prefabs added as
children.

| Variant | Rank on PC | What it is |
| --- | --- | --- |
| `cass-lite` | Good | The one for where performance is tight: the low-polygon model on PC too, locomotion, the Face Tracking switch, the Outfit menu, and the crash while away in its lite form (no window, no sound). Nothing else, and nothing is to be added. |
| `cass` | Good | Everyday, and what the rest start from: the full model, locomotion baked for this avatar's own skeleton, the crash while away with its AFK window and sounds, the party tricks (a bonk hammer, a vanishing act that leaves a log behind, a mosaic censor for the head or the whole body, a busy sign) and the outfit shuffle. |
| `cass-adv` | Medium | For going out and for leading a group: everything `cass` has, and flight, a stepladder for a lifted play space, a carry seat, a catch-up portal, four seats to put down in a ring or facing a screen, a laser pointer that can ping the spot it points at, a megaphone, a flashlight and a lantern, screen notices, and a beacon that shows where the wearer is through walls. |
| `cass-flashlight`, `cass-lantern` | Poor | `cass` with the adventure kit and one real light: a spotlight in the flashlight, or a point light in the lantern, which can be placed in the world. They carry that one tool and not the other. A light ranks an avatar Poor and a second Very Poor, hence one each. On mobile the tool is there without its light. |
| `cass-contacts` | Medium | For playing with contacts: everything `cass` has, everything in `net.wirenook.contacts` (it reacts to VRChat's standard contact traits, and carries the tester, the shield that burns and the targets), and the shape collector. One avatar to clone for both halves of a test. PC only. |
| `cass-gaits` | Good | A sampler for choosing how the avatar walks: every walk style of the locomotion package, with a Walk style menu to switch between them in game. PC only, and not a variant of `cass`. See below. |
| `cass-cyber` | Good | `cass` in the cyber wardrobe: a techwear jacket with lit seams, a utility vest, a pleated skirt with a lit hem, chunky boots and a headset in place of the hat. See [Wardrobes](#wardrobes). |
| `cass-quickhack` | Very Poor | The cyber build carrying Quick Hack by DiNe Shop, a bought prop that is not in this repository. PC only, uploaded private, and only made where the prop has been imported. See [Assets that are not in the repository](#assets-that-are-not-in-the-repository). |

### How much a variant carries

There were twelve variants, most of them `cass` with one more thing, and
which one to wear was a question with too many answers. The rule now:

- **What a variant carries goes by the rank it is held to and what it is
  for.** `cass-lite` carries nothing it can do without. A variant held to
  Good carries every reusable feature that fits at Good. A variant that is
  Medium anyway (the placed props of `cass-adv` are meshes of their own,
  which nothing can help) carries everything that is of use to it, and
  does not try to stay at Good.
- **A feature that costs a platform its rank is left out there, not
  everywhere.** A feature in `variants.json` can be marked `pcOnly` for
  one variant: `cass` leaves the tricks and the shuffle out of its Android
  and iOS builds, where they would take it from Medium to Very Poor, and
  keeps their parameters so that the list is the same on every platform.
  On mobile, `cass` is therefore `cass-lite`.
- **Features share what they can.** The build keeps one audio source for
  every feature whose sounds are short cues from the avatar itself
  (`WirenookSharedSound`), where each used to bring its own; signs (the
  AFK window, the contact reactions) are geometry in the avatar's own
  mesh and material and take turns in it; hand-held props join the
  avatar's mesh as before. What cannot be shared is a thing left standing
  in the world, which has to be a mesh of its own with its own slots.

| Was | Is now | Why |
| --- | --- | --- |
| `cass-party` | `cass` | The tricks fit beside the everyday build at Good. |
| `cass-event` | `cass-adv` | It was `cass-adv` with more; `cass-adv` now has all of it and is Medium, as this was. |
| `cass-shuffle` | `cass` | The shuffle is a switch in the Outfit menu now. |
| `cass-shapes` | `cass-contacts` | The shape collector is a contact game, and lives with the others. |

Those four are listed under `deprecated` in `Spec/variants.json`, with
the avatar ids they were uploaded under. Their prefabs are gone from the
repository. `scripts/cass.sh retire <slug>` takes a deprecated variant's
avatar down from VRChat; it refuses anything that is not on that list.

**The Outfit menu** has five switches, each with an icon of its own: the
boots, the hat, a tiered gingham skirt, an open vest with a neckerchief
worn over the sweater, and long hair in place of the short. The skirt and
the vest rest on and the hat rests off, so the avatar as it loads is the
design in the reference art but for the hair.

A garment with nothing under it has no switch. The body base is a doll
body with no underwear layer, so `uv-tiles.json` marks the torso and the
hips as zones that have to stay covered (`cover`), and the menu offers a
switch only where no combination of the offered switches could bare one
(`TileLayout.Offered`). The sweater is all there is over the torso, so it
stays on. Two garments cover the hips; the shorts give way to the skirt,
so they are the layer that stays, and the skirt's switch chooses between
the two. Boots come off, because bare feet are just bare feet. The rule is
worked out from the tiles, so a wardrobe that gains something to wear
underneath (a swimsuit over the same zones) gets its sweater and shorts
switches back without anything else changing. A switch that is not offered
is not synced either.

**Shuffle**, the menu's last entry on `cass` and what builds on it, makes
the avatar change its outfit whenever a viewer looks away from it and
back. Each viewer's client rolls for itself; nothing but the switch is
synced, and no two people need see the same outfit. It lays its outfit
over the wearer's own choices through a layer whose weight the switch
sets, so switched off it changes nothing. PC only: the outfits are UV
tiles.

**The skirt** is cloth on physics, carried by the legs. It hangs on ten
chains of three bones, jointed at the seams between its tiers. The four
chains in front of the thighs hang from two lifts, one at each hip joint,
that a rotation constraint turns half of the way with its thigh; the six
round the sides and back hang from a root that stays with the hips. A knee
that comes up therefore takes its cloth with it at once, however fast it
comes: left to physics alone, a quick knee went straight through. Three
PhysBones do the rest, each chain on a hinge that lets it swing straight
out from the body or back in, with capsules along the upper and lower legs
to push them: sitting lays the cloth over the thighs, and a heel kicked
back lifts the hem behind. A stride swings the front of the skirt with it,
by half the thigh's angle. The PhysBones are switched with the skirt and
are not simulated while the shorts are worn.

### Wardrobes

The outfit above is the `western` wardrobe. The generator can dress the
same figure in another: `cyber` so far, in the Wirenook palette pushed
towards cyberpunk. Blender exports each wardrobe as a model of its own
(`cass-cyber.fbx`, `cass-cyber-lite.fbx`) on the same skeleton, with the
same mesh names, blendshapes and UV tiles, and a variant that names a
`wardrobe` in `variants.json` has its meshes exchanged by name at build
time, the way the low-polygon model is exchanged for the full one. So a
wardrobe is not a toggle and costs nothing in the menu, the material or
the rank: it is a different avatar to upload, with every switch, physics
chain, expression and feature of the first. The Outfit menu's labels stay
"Sweater", "Hat" and so on, which in the cyber wardrobe are the jacket and
the headset.

The cyber wardrobe's cyan and magenta lines are the palette's two glowing
swatches, and they do glow: the build bakes an emission mask for the atlas
(`cass-atlas-emission.png`, the palette's own mask in the atlas's layout)
and the material uses it. Nothing in the western wardrobe is on a glowing
swatch. Mobile shaders have no emission, so there the lines are only
bright.

**The walk** comes from `net.wirenook.locomotion`, baked on this avatar's
own skeleton: `scripts/cass.sh gaits` measures the legs, hips and feet of
`cass.fbx` and writes the clips, the two controllers and the prefab that
installs them to `Generated/Locomotion/`, which every variant of `cass`
carries. Run it again when the model's legs or feet change. Standing,
walking and running, crouching, jumping, falling and landing are all the
package's own; only lying prone is still VRChat's.

How it walks is a style, kept in `Generated/Locomotion/Gait Profile.asset`.
The package names six (Weighty, Light, Sway, Bouncy, Swagger, Dainty), and
`cass-gaits` is for telling them apart on the avatar itself:

```bash
scripts/cass.sh gaits styles          # bake all six for the sampler (minutes; about 90 MB, not committed)
scripts/cass.sh upload cass-gaits     # then try them in game: Walk style in the menu
scripts/cass.sh gaits Sway            # make the one you chose the avatar's own, and bake it
scripts/cass.sh verify cass           # the variants pick the new bake up as they are
```

After that the profile can be tuned by hand and baked again with
`scripts/cass.sh gaits`; the package's README says what each number does.

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
upload profile from an avatar switches the check off. A variant that
carries someone else's asset is held to the opposite on one point: it must
be private (next section).

### Assets that are not in the repository

A variant can carry a prefab that this repository does not contain: a
bought asset whose terms forbid passing it on. `Spec/variants.json` lists
such a thing under `local`, by the GUID its author shipped it with, and
with the name, author and address it is credited by. That GUID is all the
repository holds of it. Whoever holds a licence imports the author's own
package into their checkout, where it lands in a folder that `.gitignore`
names, and the generator finds the prefab by GUID and stands it in the
variant.

- Where the asset is absent, every command skips the variant and says
  why: `rebuild` leaves its prefab exactly as committed, `verify` reports
  "not checked" and passes, and `upload` refuses.
- The description credits it ("Carries, not from that source or under its
  licence: name by author (address)") after the usual link to this source.
- It uploads **private** and without the `agplv3` tag, and the policy
  refuses to send it public: such terms as a rule forbid an upload others
  can clone, and the avatar as a whole is no longer under this
  repository's licence.

```bash
scripts/unity-bridge.py invoke Wirenook.Validation.Editor.LocalAssets.Import <path to the author's .unitypackage>
scripts/unity-bridge.py invoke Wirenook.Validation.Editor.LocalAssets.List     # what is needed, and whether it is here
scripts/cass.sh rebuild && scripts/cass.sh verify cass-quickhack
```

`cass-quickhack` carries [Quick Hack by DiNe Shop](https://dineshop.booth.pm/items/9153292).
Its terms license it to the purchaser alone, allow use on that person's own
avatars, and forbid redistribution, public or cloneable uploads, and use as
training data for machine learning; read them before adding it anywhere.
The prop draws effects over the view of whoever it is aimed at, for those
who have the avatar's shaders shown.

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
| Garment toggles (the Outfit menu), and with them the shorts and the long hair; expressions that swap UV tiles | They work by discarding UV tiles |
| The vest | It rests on, but with it the avatar is about 16,300 triangles and Medium ends at 15,000 (`"mobile": false` in `uv-tiles.json`) |
| The skirt's physics | Thirty bones against four colliders are several times the PhysBone limits. The skirt is worn, and its lifts still carry the front of it with the thighs (by four fifths there, with no collider to do the rest), but the cloth does not swing or drape |
| The outfit shuffle | The same |
| The party tricks, on `cass` and what builds on it | They would take `cass` from Medium to Very Poor there; `cass-adv` is Very Poor anyway and does without them too, being built on `cass` |
| The AFK window, and the glitch and eye screens of the crash while away | Drawn by the avatar's PC shader; the body still locks |
| Everything in `net.wirenook.contacts`; `cass-contacts` is not built for mobile at all | More contacts than mobile allows, and its reactions are the PC shader's |
| The beacon, the censor, the picture on the seats' screen | Drawn by custom shaders |
| The nap's Zs | A third material slot is past Medium there; the nap itself is kept |
| Flight | It is a collider to stand on, and avatar colliders are disabled |
| Screen notices | Drawn by a custom shader |
| The light in `cass-flashlight` and `cass-lantern` | Avatar lights are disabled; the tool is still there and can still be placed, unlit |
| All sound | Audio sources are disabled |

| Variant | Mobile rank | Triangles | Skinned + static meshes | Material slots |
| --- | --- | --- | --- | --- |
| `cass`, `cass-lite` | Medium | 14,428 | 2 + 0 | 2 |
| `cass-cyber` | Medium | 14,390 | 2 + 0 | 2 |
| `cass-adv` | Very Poor | 18,856 | 2 + 6 | 10 |
| `cass-flashlight` | Very Poor | 17,284 | 2 + 4 | 8 |
| `cass-lantern` | Very Poor | 17,430 | 2 + 5 | 9 |

`cass` is under 600 triangles short of Medium's limit of 15,000 (the hat rests off now, and is cut there with the rest of what rests hidden), so anything added to
what the lite level shows at rest has to be paid for there; that is what
keeps the vest off mobile. What rests hidden (the shorts, the long hair) or
is marked as too much for mobile (the vest) is cut out of the mobile build
and costs it nothing. The face is 8,500 of them, because
it is the same mesh at both levels; the stitched details are left out of
the lite level altogether, as are the folded edges of the waistband,
hems and collar.

The adventure variants keep the carry seat and the catch-up portal
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

Some things no sheet shows, because at rest they are nothing, and each has
a preview of its own (run with `scripts/unity-bridge.py invoke
Wirenook.Validation.Editor.<Name>.Render <slug>`, pictures in
`dist/validation/`):

- `AwayPreview`: the crash while away, with the shader's properties set by
  hand: the eye screens, the AFK window from every camera, the glitch at a
  simmer and at its worst.
- `SignPreview`: every sign the built avatar carries, unfolded one at a
  time, read back from the built mesh.
- `GripPreview`: each held prop in its hand with the finger pose the
  build gave it, from five sides.

`UvProbe.Built <slug>` lists what each built mesh has in each UV set, and
`ShaderProbe.Check "<shader names>"` says whether a shader compiled.

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
- **`net.wirenook.assets`** also closes each hand round what it holds
  (finger poses in the Gesture layer, made from the grips on the avatar),
  spreads a feature's whole-avatar material animation to every renderer,
  and keeps one audio source for all the features that can share one.

| Variant | Rank | Triangles | Skinned + static meshes | Material slots | Bones | Synced bits |
| --- | --- | --- | --- | --- | --- | --- |
| `cass-lite` | Good | 19,505 | 2 + 0 | 2 | 109 | 7 of 256 |
| `cass` | Good | 61,944 | 2 + 3 | 7 | 113 | 85 of 256 |
| `cass-adv` | Medium | 66,712 | 2 + 12 | 16 | 133 | 243 of 256 |
| `cass-flashlight` | Poor (one light) | 65,134 | 2 + 8 | 12 | 128 | 240 of 256 |
| `cass-lantern` | Poor (one light) | 65,280 | 2 + 9 | 13 | 128 | 240 of 256 |
| `cass-contacts` | Medium | 69,403 | 3 + 11 | 16 | 162 | 244 of 256 |
| `cass-gaits` | Good | 60,608 | 2 + 0 | 2 | 109 | 15 of 256 |
| `cass-cyber` | Good | 56,972 | 2 + 3 | 7 | 103 | 85 of 256 |
| `cass-quickhack` | Very Poor (the prop's 38 meshes and 56 material slots) | 59,820 | 3 + 41 | 63 | 105 | 97 of 256 |

Three of these are close to an edge. `cass-adv` and `cass-contacts` are at
Medium's sixteen material slots exactly: one more thing left standing in
the world takes either to Poor. `cass-contacts` is 600 triangles under
the 70,000 past which an avatar is Very Poor. And the three fullest are
within sixteen bits of the 256 an avatar may sync, most of it the 66 bits
each synced position costs; things that are never out at once could share
one such position, which nothing does yet.

Thirty of each variant's bones are the skirt's chains. Good allows 150.

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

**Twelve variants are uploaded**, eleven public and `cass-quickhack`
private, each for every platform it is built for, as this page describes
them; the uploads were last made on 2026-11-20.

The build before this one was worn at an event on 2026-11-19, briefly.
What was noticed there is what this one changes: the vest's armholes, the
teeth in the speaking shapes, ears that bent in the middle, a knee coming
through the skirt, the thin neck, the open boots, the shape collector's
shapes and gate, how loud the sounds are, the carry seat in a turn, and a
censor that blurred the room as well. **None of those changes has itself
been worn.** Neither have the things added alongside them: the skirt and
vest as the resting outfit, the hand lock, the aimed portal, the cyber
wardrobe and `cass-quickhack`. The walk styles of `cass-gaits` are still
unchosen.

| Variant | Avatar id | Platforms uploaded |
| --- | --- | --- |
| `cass` | `avtr_83eafc89-950e-4553-bb36-c37238333069` | PC, Android, iOS |
| `cass-lite` | `avtr_df376716-743f-4bde-a5cc-98ddec85a313` | PC, Android, iOS |
| `cass-adv` | `avtr_5b291f6b-6058-4b39-83b2-382596f7b6d9` | PC, Android, iOS |
| `cass-event` | `avtr_eb395cf9-c1b5-45f1-af1c-ea60c6710fba` | PC, Android, iOS |
| `cass-party` | `avtr_703d3044-1d5c-419f-8136-72743d3290dc` | PC, Android, iOS |
| `cass-shuffle` | `avtr_3c5130fb-ca48-4958-81ae-1c1087e9eff0` | PC |
| `cass-shapes` | `avtr_01467232-af45-4db8-b1ef-288077548fbe` | PC, Android, iOS |
| `cass-flashlight` | `avtr_a22b0123-710f-49f9-a2a5-01870c26a4e9` | PC, Android, iOS |
| `cass-lantern` | `avtr_411ef326-6e48-4d16-ba22-48299840102c` | PC, Android, iOS |
| `cass-gaits` | `avtr_05927e20-4f35-4d3f-a94a-bacbef962f89` | PC |
| `cass-cyber` | `avtr_6e4d8fa5-248c-49c2-ab94-f95251452992` | PC, Android, iOS |
| `cass-quickhack` (private) | `avtr_03ae9d5a-620a-4000-a0a0-8ad4dae77823` | PC |

The first pass of the model, as `cass` and `cass-adv`, was worn in the
client on PC. That is where the portal's pop-out, the notices' early exit
and the thumbnails were found wanting, and the fixes for those have still
not been tried there. Everything since was checked in Blender, in the
Unity editor, against VRChat's API, or headless. `docs/POSTMORTEM.md` has
the history, the gotchas and the open issues, in three parts: the
pipeline, the session of 2026-11-16 and 17 that added most of what is
listed below as unchecked, and the session of 2026-11-19 and 20 that
answered the notes from wearing it.

That session ran unattended. The uploads were made with the owner's
written certification that they hold the rights to the content, given
beforehand for the purpose; it was recorded for each avatar id through the
SDK's own agreement call, not by anyone answering the SDK's dialog. The
uploads of 2026-11-18 and of 2026-11-20 ran overnight the same way, each
on a certification the owner gave that evening.

Checked:

- Both Blender exports validate against the specs with no errors, and each
  exported file is read back and compared (names, bones, shape keys, UVs,
  orientation).
- All twelve variants build through Modular Avatar and Avatar Optimizer for
  the platforms they are built for, and pass `scripts/cass.sh verify`: the
  rank each is held to, the MMD mesh name and layer order intact after the
  build, every viseme, required tracking key and MMD shape still present,
  budgets respected, no brightness floor.
- The contact sheets for `cass` were rendered with the new model, and the
  cameras and the outfit sheet looked at: each switch flipped in turn,
  everything on (the original design) and everything off, with whole skin
  underneath. The model's own review renders, in more poses, are from
  Blender.
- Each new feature was built onto a variant and read back with `FxProbe`:
  its layers are there and every curve of its clips arrives at an object
  that exists. Where there was something to see it was rendered in the
  editor: the beacon's pin and arrow from nine camera positions, the censor
  over the avatar under each of its modes, the nap's pose at four moments,
  the seats in both arrangements, the party tricks in the feature sheet.
- world-sync's anchor bus was run in the editor by a check that stands in
  for VRChat's parameter drivers, contacts and network; a viewer who
  arrives after six things are placed has all six, to within 2.9 cm, after
  one turn of the broadcast.
- All uploads went through `scripts/cass.sh upload`, and VRChat's records
  read back matching the upload policy (source link, required tags,
  public).
- Headless tests: 36 for the avatar's core logic, 11 for the thumbnail
  composer, and each submodule's own suite (56 in locomotion).

Not checked, because only the client can:

- **Face tracking hand-over.** The design follows VRChat's documentation
  for SDK 3.10.6, but that documentation does not say what happens when an
  animation and a tracker drive the same blendshape, which is why gestures
  only animate shapes the tracker is not mapped to while one is live.
- **MMD worlds**, beyond the mesh name and layer order.
- **Every gadget in use.** The older ones: collider flight, the carry
  seat, the portal's station, the laser's raycast, the screen notice in a
  headset. And every new one: the ping, the beacon, the hammer, the
  vanishing act, the censor, the stepladder, the nap, the seats and their
  screen, the outfit shuffle, the shape collector. Each submodule's README
  says what its own unknowns are.
- **Synced world positions.** The receiving half, and now the bus's whole
  protocol, are checked in the editor; the half that measures a position
  on the wearer's client only runs in game, and the stepladder now rests on
  the same kind of reading.
- **How the locomotion feels**, and how it sits with real tracking. That
  goes for all six styles, for the crouch, and for the jump, fall and
  landing poses, which were looked at on the avatar in the editor and
  nowhere else. `cass-gaits` exists so that the styles can be judged in
  the client.
- **Hand poses.** Props sit in the hand pointing where the fingers point,
  and the fingers now close round them: each grip says when its prop is
  held and how far the fingers, the index finger and the thumb close, and
  the build gives each hand a pose layer for it (`HandPoses` in
  `net.wirenook.assets`). `GripPreview.Render <slug>` shows every held
  prop in its hand from four sides, read back from the built avatar. The
  fingers were fitted from those pictures; the thumb still stands off the
  megaphone and the laser pointer more than it should. Whether the hand
  keeps its pose against finger tracking, as the tracking control it sets
  should make it, only a client shows.
- **The model in motion.** The ear and tail poses, the arm twist
  constraints, the hair, ear and tail physics and the eye-look limits are
  generated and build cleanly, but nothing has seen them move. The long
  hair hangs on six more bones under the same PhysBone, with settings that
  were chosen for the short hair. The ears were stiffened after a note
  from wearing them (more pull, less spring), and after a second note
  bend from the base, in their poses and in their swing (30° at the base,
  a third of that at the tip); neither has been seen since.
- **The skirt.** Worn once on physics alone, where a quick knee came
  straight through it. The lifts that now carry its front with the thighs,
  and the mobile build's skirt that has only those, are checked in Blender,
  where `preview.py` turns the lifts, lays the chains over posed legs and
  the cloth covers them sitting, running, kicking and with a knee raised
  high. That is geometry, not a simulation: how much a stride swings the
  skirt, and how the PhysBones' pull, spring, gravity and hinge feel, only
  a client shows. The numbers are in `skeleton.json` (`follow`,
  `colliders`) and `CassPrefabs` (`"skirt"`).
- **Hands, aiming and the wardrobe.** The hand lock's layer, the portal's
  aiming layers and the cyber wardrobe's meshes are in the built avatars
  (read back with `FxProbe`, rendered in the editor, ranked by `verify`).
  Whether a fist reads as a click, whether the preview keeps up with the
  hand, and how the outfit sits in motion, nobody has seen.

Known gaps:

- The model is a fourth pass, modelled by script and judged from renders
  and one round of notes from wearing the first. The face is a stand-in
  from another avatar, and its expressions are mild; a search for
  licence-compatible alternatives found candidates and tried none (see the
  post-mortem). There are no socks. Garment openings are hollow and rely on
  the double-sided material.
- With the sweater off and neither the shorts nor the skirt on, the body
  is bare: the base is a smooth doll body with no underwear layer. The
  skirt needs none: it hides the hips and is closed off inside by a dark
  lining, so from below there is only dark.
- The skirt collides with the wearer's legs and nothing else: it hangs
  straight through a chair, the floor and other people. A high kick opens
  it onto its dark lining, since a chain cannot fold round a leg. Its
  waistband goes round the untucked sweater, so the waist is wide, and with
  the sweater off the lining shows in the gap.
- The vest is fitted to the sweater and is only shown over it. With the
  skirt on, its fringe is inside the skirt's waistband. The sweater still
  comes a few millimetres through the tops of its shoulder straps when
  the arms are raised high. Mobile builds do not have the vest at all.
- The tail passes through the back of the skirt, which rests on now.
- The open vowels show the upper row of teeth as one pale band.
- Long hair turns rigidly with the head until physics moves it, and has no
  collider to keep it out of the shoulders.
- The sweater's collar stands a little, and a twist wrinkles its front.
- The ears clip the hat's brim when a pose or physics bends them far;
  they have holes to stand in, not room to move.
- Under the chin, the face texture's painted shadow is stretched where the
  head's neck meets the body's, which was made a third thicker than the
  body base's own.
- The hair is fitted under the hat, so with the hat switched off it is a
  little flattened where the hat sits, and the top edge of its lengths
  shows as a faint line round the head.
- Nothing fades or dithers out as a viewer comes close; lilToon's Clipping
  Canceller pushes near geometry back instead.
- The nap is baked on a generic rig and retargeted, not fitted to this
  avatar as the gaits now are.
- Lying prone still plays VRChat's own crawl; the gait model has nothing
  to say about it.
- VRChat's ten tags do not hold every feature of `cass-event`; the
  least important two are left out.
- The seven submodule packages are released as 0.1.0 on GitHub, each
  with its `.zip` and `.unitypackage`. This repository's own v0.1.0 has
  no files (see [Releasing](#releasing)). None is on the VPM listing yet.

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

Step 2 does not work in this repository as it stands. Its releases are
immutable, which GitHub only lets take files while they are still drafts,
and CI attaches them after publication. v0.1.0 was published that way on
2026-11-18 and has no files, and its tag cannot be used again. The
submodules do not have the setting and released normally.

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

The outfit shuffle notices when it is not being drawn by the method of VRLabs'
[IsRendering Detection](https://github.com/VRLabs/IsRendering-Detection) (MIT), and the world frame of
`net.wirenook.world-sync` is the technique of VRLabs' World Constraint. Both are built here from their
descriptions; no file of either is in this repository.

Descended from https://github.com/vrchat-community/template-package
([VRCHAT DISTRO LICENSE FILE](https://github.com/vrchat-community/template-package/blob/d9cf13fe9f56867cbf7315a4dbbf1901bc1537ec/Packages/com.vrchat.core.bootstrap/License.md))

Third-party material is inventoried in [CREDITS.md](CREDITS.md).
