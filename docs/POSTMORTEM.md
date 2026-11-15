# Post-mortem: the placeholder pipeline

What was built, what went wrong on the way, what bit more than once, and
what is still open. Written on 2026-11-15, after the pipeline had carried
placeholder builds from Blender to public VRChat avatars and the first
round of feedback from wearing them had been worked through.

The model, textures and animation art are placeholders throughout. This is
about the machinery around them.

## What exists

- **Specs first.** `Packages/net.wirenook.cass/Spec/*.json` (blendshapes,
  skeleton, UV tiles, gestures, variants, proportions) is read by both the
  Blender scripts and the Unity generators.
- **Everything in Unity is generated in place** from those specs and the
  Blender export: materials, the FX controller, menus, the root prefab and
  the variants on top of it. Generated assets keep their GUIDs, so
  references and hand edits survive a rebuild.
- **Five feature packages** as submodules (`wirenook-assets`, `locomotion`,
  `world-sync`, `avatar-stations`, `adventure-tools`), each a drop-in set
  of Modular Avatar prefabs built by code.
- **Build-time work on a copy:** Modular Avatar, the wirenook-assets
  plugin (joins hand tools to the avatar's mesh; makes the mobile build),
  then Avatar Optimizer.
- **Checks and pictures:** `verify` on the built result, contact sheets, a
  probe that re-opens the bundle the SDK built.
- **Upload automation** with soft guardrails: source link in the
  description, `ai` and `agplv3` tags plus feature tags, public
  visibility, a generated thumbnail.
- **Variants:** `cass`, `cass-adv`, and the PC-only `cass-flashlight` and
  `cass-lantern`; PC, Android and iOS builds of the first two.

All four variants are uploaded and public, `cass` and `cass-adv` for all
three platforms. Section "Status" of the top-level README lists the avatar
ids and says which of this has been seen working in the client. The short
version: `cass` and `cass-adv` have been worn on PC; nothing has been
tried on Android or iOS hardware, and the real-light variants have not
been worn.

## Timeline of the things that went wrong

Roughly in the order they happened. Each is here because it cost time or
would have cost the wearer something.

| What happened | Cause | What changed |
| --- | --- | --- |
| Props and avatar arrived in Unity lying down or pointing at the floor | Stale pose-bone matrices after an in-memory axis conversion in the exporters; separately, a leftover `bakeAxisConversion` import flag made the avatar look backwards and was misreported as an export bug | Exporters assert orientation on the raw FBX; both importers set `bakeAxisConversion = false` explicitly |
| Avatar Optimizer merged nothing | It only merges renderers that match in root bone, bounds, probe anchor and animated material properties, and backs off near components it does not know | `UnifyRenderers`, the join pass, `IWirenookEditorOnly` markers stripped before it runs |
| Hand tools never hid | A prop's mesh object and its root bone share a name; a search by name found the mesh | `FeaturePrefab.Bone` looks among the skinned mesh's bones |
| Contact sheets showed no poses or expressions | Three Unity behaviours at once (see gotchas) | One combined clip per picture, plain sampling, skin every render |
| First upload came out private and failed its own policy check | The SDK uploads a first-time avatar with the record VRChat returned when it reserved the id; VRChat rewrites punctuation in descriptions | `upload` re-sends the record after a first upload; the policy check folds lookalike characters back |
| `cass-adv` nearly overwrote `cass` on VRChat | A prefab variant inherits its parent's blueprint id | Rebuild clears inherited ids, `verify` reports sharing, `upload` refuses. Caught by the upload preview before anything was sent |
| An upload failed after the build, with the reason hidden | The SDK's own validation rejected sound clips without Load In Background; the error was printed above a page of logs that `tail` cut off | Import rule for sounds; `verify` runs the SDK's validation; the bridge prints errors last |
| An upload sat for an hour | VRChat's rights confirmation appeared as a native window that blocks the editor, and nobody was at the machine | Documented. The confirmation is the uploader's to give; nothing clicks it for them |
| Every prop showed at once for anyone blocking the avatar's animations | Props rested at full size and relied on the animator to shrink them | Feature prefabs rest at their animator's default pose; `verify` compares the two |
| Re-uploading with only the bundle changed failed | VRChat refuses a file identical to the one it holds, and the SDK sends the thumbnail first | `upload` hashes the thumbnail as the SDK would send it and leaves it out when unchanged |
| A T-posed second avatar stood in the contact sheets | The SDK saves the open scene while the copy it builds from is in it; destroying the copy afterwards only removed it from memory | `upload` saves the scene again without it |
| The portal vanished at the wearer instead of where it stood | The synced anchor let go the moment it was switched off, before the pop-out played | The anchor holds its place for the length of the pop-out |
| A notice could not be dismissed | It was one clip that played to the end | Three states; switching off goes to the fade-out |
| Thumbnails were unreadable | Designed at full size: a card of text, chips and a badge, shown by VRChat a couple of hundred pixels wide | No text; a bust and one row of grouped feature icons |
| The lantern's real light was a downward spotlight | Two tools were made to share one light, and a light's type cannot be animated | Two props, one real light per variant |
| The lantern stopped swinging in the real-light build | A second child under the swinging bone: a PhysBone does not swing a bone with several children unless told how. Avatar Optimizer noticed and removed the component, which is how it was found | The light hangs under the flame bone, the only child |

## Gotchas

Things that are true of the tools and will be true again.

### Unity

- **A humanoid sampled with a clip resets everything the clip does not
  mention.** Sample one combined clip per picture.
- **Skinned meshes skin once per frame.** Several renders in one editor
  frame need `forceMatrixRecalculationPerRender`.
- **Animation preview mode holds every animator-bound property at rest,**
  blendshapes included. Use plain `SampleAnimation`.
- **A light's type is not animatable.** Colour, intensity, range, spot
  angle and enabled are.
- **Unity strips vertex channels it thinks no shader reads** when it packs
  a bundle. The outfit toggles live in the second UV channel; `cass.sh
  bundle` shows what survived.
- **Unity will not save a scene it believes unchanged,** and
  `OpenScene` on a scene that is already open does not reload it.
- **A prefab variant inherits every property of its parent,** including
  the avatar id.
- **Switching build target reimports everything** and reloads scripts. It
  is cached per target after the first time.

### VRChat SDK and service

- **The SDK signs out on every script reload** until its control panel is
  drawn again.
- **A first upload is private** whatever record it was given.
- **Descriptions come back with lookalike punctuation**
  (`github․com⁄…`): readable, not clickable, and not equal to what was
  sent.
- **An unchanged file is refused** ("This file was already uploaded"),
  thumbnail included, and the thumbnail goes first.
- **The rights confirmation can be a blocking native window.** From a
  script it looks like a hang.
- **The SDK saves the open scene during a build** with its working copy in
  it.
- **Expression parameters sync by position.** A platform build with a
  different list scrambles toggles between platforms. Mobile builds here
  keep every parameter even where the feature is gone, and `verify`
  compares the lists.
- **Any light ranks an avatar Poor on PC; a second, Very Poor.** Enabled
  or not.
- **Mobile is far stricter.** One collider or one audio source is Very
  Poor; four material slots is the edge of Poor; only VRChat's own mobile
  shaders are accepted, and none of them can discard UV tiles.
- **A parameter holds at most eight bits,** which is what shapes the
  synced-position encoding.
- **A station that is disabled at upload never works;** disable its
  collider instead.
- **Constraints whose source is outside the scene resolve to the world
  origin.** That is the world frame the synced anchor stands on (VRLabs'
  technique).

### Modular Avatar, NDMF, Avatar Optimizer, lilToon

- **Avatar Optimizer keeps meshes with blendshapes apart** from those
  without. That one extra skinned mesh (the face) is what stands between
  the PC builds and Excellent, and it is the better trade.
- **Avatar Optimizer removes PhysBones that would do nothing,** such as
  one on a bone with two children and multi-child type Ignore. Read its
  before-and-after counts when they change.
- **Its components are not public API.** Trace and Optimize and Remove
  Mesh By UV Tile are added by type name and configured as serialized data;
  an update can move them.
- **lilToon logs `unrecognized identifier 'CBUFFER_START'` on every
  build.** It comes from a pass that never draws. The bundles are fine.
- **lilToon's Clipping Canceller is a project setting,** not a material
  one; the rebuild switches it on.
- **Template clones share GUIDs.** The five packages needed fresh `.meta`
  files.

### Working through the editor bridge

- **"Refreshed" can arrive before compilation starts.** The bridge waits
  two idle seconds; `unity-refresh.sh` also waits for the tree to
  type-check.
- **Never refresh or recompile during an upload.** The reload kills it.
- **A failed patch can take constants with it.** More than one outage here
  was a scripted edit that removed or mangled something next to its target
  (a newline inside a string literal, a block of constants). Compile
  before trusting an edit; the offline check takes seconds.
- **Shell here-documents mangle quoted code** on this machine. Edits are
  written as files and run.
- **Read the end of the log.** The one upload failure that took longest to
  understand had printed its reason where a pipe through `tail` hid it.

## What would be done differently

- **Design the thumbnail at the size it is seen.** It was iterated at
  1200 pixels and judged there.
- **Rest pose is part of the feature.** Anything an animator hides should
  be hidden without the animator. The check for it now exists; it should
  have come with the first toggle.
- **Run the SDK's own validation before the first upload,** not after the
  first rejection.
- **Wear it sooner.** The portal and notice problems were obvious within
  minutes in the client and invisible in the editor. The editor can check
  structure; it cannot check feel.
- **Do not share what cannot be shared.** One light for two tools was
  built before checking that a light's type could be animated. The check
  took one editor call.

## Open issues

### Unverified in the client

- Everything on Android and iOS. The builds are measured, pass the SDK's
  validation and VRChat's shader rule, keep the PC parameter list, and
  uploaded without complaint. That is all that is known.
- Whether glowing geometry draws on mobile. It uses VRChat's additive
  particle shader on meshes without vertex colours. Opened in the PC
  editor, the Android bundle reports that shader as unsupported; that may
  only be a PC editor reading an Android bundle, and it may not.
- The fixes from the first round of feedback: the portal's pop-out, the
  notices' early exit.
- Real lights and placing them (`cass-flashlight`, `cass-lantern`).
- The sending half of synced world positions: contact readings and
  weighted constraints only run in the client. The receiving half decodes
  to within 2.7 cm in the editor.
- Face tracking handing regions over to gestures, MMD worlds, locomotion
  feel, hand poses around tools.

### Known limits

- **Mobile builds give up** the garment toggles, flight, both stations,
  the screen notices, real lights and all sound. `cass-adv` is Poor
  there (four material slots, two skinned meshes); `cass` is Medium.
- **Expressions that show or hide UV tiles** (anything in `gestures.json`
  with `tiles`) do nothing on mobile for the same reason the garment
  toggles do not.
- **PC rank is Good, not Excellent,** because of the separate face mesh.
- **A placed light floats where the hand was.** It does not find the
  ground.
- **The laser's beam is not drawn in the contact sheets.** Its length
  comes from a ray the editor does not cast.
- **Stations are not pooled at run time.** VRChat allows six per avatar;
  the build only counts them.
- **The locomotion bake is generic,** not fitted to this rig
  (`LocomotionBuild.BakeFor` exists and has not been run for it).
- **No texture atlasing.** Flat palettes leave nothing to atlas; painted
  textures will.
- **The project's product name is still the template's**
  (`vpm-package-maker`), which is why built bundles land under that name
  in the temp folder.

### Fragile by construction

- Reflection into the SDK: the builder's `_builder` panel field and
  `OnGUIAvatarCheck` (for validation), `VRC_EditorTools.CropImage` (for
  the thumbnail hash). Each degrades to a note or to the old behaviour if
  the member moves.
- Avatar Optimizer components configured by name.
- lilToon's internal setting API for the Clipping Canceller.

### Housekeeping

- Nothing is released. No package has a version tag, and none is in the
  VPM listing.
- The root repository has never been pushed. Submodule branches
  (`claude/setup`) are pushed only up to the first upload.
- `Generated/flashlight Flashlight.Beam.asset` and `lantern Lantern.Glow.asset`
  in adventure-tools are generated for the real-light builds and not used
  by them.
- Editor-written settings (`ProjectSettings.asset`, `GraphicsSettings.asset`)
  flip between two values depending on what ran last and are reverted
  rather than committed.
