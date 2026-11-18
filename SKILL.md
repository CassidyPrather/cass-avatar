---
name: cass-avatar
description: Cassidy's VRChat avatar as a generated, non-destructive pipeline — Blender export, specs, generated Unity assets, prefab variants, build-time optimisation, policy-checked uploads; standalone feature packages mounted as submodules
---

# cass-avatar

Unity 2022.3 project at the repository root. The avatar is the VPM package
`Packages/net.wirenook.cass`; seven standalone packages it builds on are git
submodules under `modules/` and are referenced in place from
`Packages/manifest.json`. Code is AGPL-3.0-or-later with the VRChat/Unity
linking exception in `LICENSE_ADDENDUM`.

Almost everything in Unity is **generated from code and specs**. Change the
spec or the generator and rebuild; do not hand-edit generated assets.

## Repo Map

- `Packages/net.wirenook.cass/Spec/` — the contracts, read by both Blender and Unity: `blendshapes.json`, `skeleton.json`, `uv-tiles.json`, `gestures.json`, `variants.json`, `proportions.json`.
- `Packages/net.wirenook.cass/BlenderExports/` — the only place Blender exports land: `cass.fbx` and `cass-lite.fbx`, the same avatar at two fidelity levels. Import settings are applied in code (`Editor/CassModelImporter.cs`). `Editor/CassBuildPlugin.cs` exchanges the meshes for the lite ones at build time on mobile and for variants with `"model": "lite"`.
- `Packages/net.wirenook.cass/Editor/` — generators (`CassMaterials`, `CassFx`, `CassMenus`, `CassPrefabs`), entry points (`CassBuild`), post-build checks (`CassChecks`), upload automation (`CassUpload`, `CassThumbnail`).
- `Packages/net.wirenook.cass/Runtime/Core/` — engine-free logic (upload policy, tile rules, gesture rules), unit-tested headless.
- `Packages/net.wirenook.cass/{Generated,Materials,Prefabs}/` — generator output, committed. `Prefabs/cass-root.prefab` is the single root avatar prefab (a variant of the model); `Prefabs/Variants/*.prefab` are the upload variants.
- `blender/` — `sources/` (the trimmed CC0 body base and face), `scripts/build_cass.py` and `scripts/kitbash/` (the generator that assembles them with the modelled hair, ears, tail and outfit), the two outputs `cass.blend` and `cass-lite.blend`, and the headless scripts that validate and export. See `blender/README.md`.
- `modules/<repo>/` — submodules: `wirenook-assets`, `locomotion`, `world-sync`, `avatar-stations`, `adventure-tools`, `party-tricks`, `shape-collector`. Each is its own repository with its own README, SKILL.md, CI and version.- `Assets/Validation/` and `Assets/Scenes/Validation.unity` — cameras, lighting conditions, poses and the contact-sheet renderer, plus tools for looking at one feature: `FxProbe` (what a build left in a variant's animators, `Menu` for its menu and parameters, and `Try` to build a variant with one more feature prefab on it), `ShownPreview` (a feature prefab with its hidden props brought out), `GaitPreview` (clips of a locomotion controller on the built avatar), and `BeaconPreview`, `CensorPreview`, `NapPreview`. Harness only; not shipped.
- `Assets/DevTools/UnityBridge/` — the file bridge that lets scripts drive the open editor.
- `tools/thumbnail/`, `tools/contact_sheet.py`, `art/banner/` — Python and SVG tooling outside Unity.
- `ref/` — private reference art. Never publish, embed or trace it.
- `Packages/com.vrchat.core.bootstrap/`, `Packages/vpm-manifest.json`, `Packages/.gitignore` — inherited from the template: the bootstrapper is vendored byte-for-byte, VPM dependencies are edited with a VPM client (`vrc-get`/ALCOM), and the allowlist keeps resolver-installed packages out of git.

## Commands

```bash
scripts/cass.sh build|export|rebuild|verify|report|sheets|preview|upload [slug]   # see the script header
scripts/cass.sh gaits [styles|<style>]      # bake the walk on the avatar's own skeleton; all styles for cass-gaits; or choose one
scripts/compile-check.py <package dir>...   # type-check C# without touching the editor
scripts/unity-refresh.sh                    # recompile the open editor, once everything type-checks
scripts/unity-bridge.py invoke Namespace.Type.Method [string args...]
scripts/check-meta.sh && scripts/check-manifests.py && scripts/format.sh --check && scripts/test.sh
python tools/thumbnail/test_thumbnail.py
```

## Working in the editor

- The editor stays open. Drive it with `scripts/unity-bridge.py`; it works while Unity is in the background. A batch-mode run is not possible while the project is open.
- Recompile with `scripts/unity-refresh.sh`, which waits for `scripts/compile-check.py` to pass first. A compile error in the live editor blocks every other tool.
- `Wirenook.DevTools.Reflect.Describe <Type>` and `Reflect.Serialized <Type>` (via `invoke`) list a type's members and serialized property names. The VRChat SDK is compiled and thinly documented; ask the editor instead of guessing.
- Rendering several pictures in one editor frame needs `CassPreview.SkinEveryRender`, and a pose plus toggle states has to go through one sampled clip (`CassPreview.Sample`); Unity skins once per frame and resets whatever a sampled clip does not mention.
- Shell here-documents fail on this machine whenever their text contains an apostrophe. Write the script to a file and run that.
- Entry points take strings and return a short text result. Keep invocations short, never enter play mode, never leave objects in the open scene.
- Unity writes `.meta` files on refresh. Commit them; never hand-write them.

## Rules that are easy to break

- **Prefabs are edited in place, never recreated.** Variants store overrides against ids inside their parent; recreating a parent orphans them.
- **FX layers 1 and 2 are the hand gesture layers** and the only ones that touch MMD-named blendshapes. MMD worlds silence exactly those two. Nothing may be inserted before them.
- **The face mesh is named `Body` and sits directly under the avatar root.** MMD worlds animate it by that path.
- **Tile switches animate every renderer that wears the material**, even ones with no faces in that tile. Renderers with identical animation are the ones the optimiser may merge.
- **Props are toggled by scaling a bone, not by switching a renderer**, for the same reason.
- **Write Defaults is ON everywhere** (`ControllerBuilder.WriteDefaults`).
- **`Runtime/Core/` and `Tests/` compile with plain dotnet in CI**: no `UnityEngine` there, classic NUnit asserts only.
- **A tile's switch is a rule** (`uv-tiles.json`): the value of its parameter that shows it, what it `needs` and what it gives way to (`unless`). Alternatives share one parameter with opposite `when`. The 4x4 grid is full; a new garment has to share a tile or replace one.
- **A bone that a second layer scales must also be scaled by the layer that toggles its prop.** Avatar Optimizer dropped the curves of a bone that only a later layer scaled (the hammer's hit burst). Check with `FxProbe.Clips`.
- **Nothing with a constraint goes under a bone that is scaled to zero.** A world position has no answer under a parent of no size. Scale the constrained parts themselves (the stepladder's steps).
- **A feature that must stay off Android and iOS for rank is marked `WirenookPcOnly` on the object, not the prefab**, so the rest of the feature is kept (the nap's Zs, the seats' screen).
- Blendshape, bone and tile names live in `Spec/`. Add a name there first; Blender's validation and Unity's generators both read it.
- **A physics chain that carries one garment names that garment's `tile` in `skeleton.json`** (the skirt). Its PhysBone is then switched with the tile and removed from mobile builds, which cut hidden tiles out; without it a hidden garment's physics still counts on mobile and takes the rank to Very Poor.
- **Skirt bones have Y down the cloth and Z pointing out from the body.** A PhysBone hinge turns a bone about its X axis; `CassPrefabs` throws on a chain rolled otherwise.
- **The walk is baked for this skeleton** into `Generated/Locomotion/` by `scripts/cass.sh gaits` (the locomotion submodule does the work); bake again when the legs or feet change. `Generated/Gaits/` is the style sampler of `cass-gaits`: its controllers are git-ignored (90 MB) and `verify` fails the variant until `scripts/cass.sh gaits styles` has written them.
- **Two features must not both replace the Base playable layer.** `cass-gaits` builds on the root prefab, not on `cass`, for that reason.
- **A build can fail inside NDMF with `AssetSaver.SaveAsset: sameAssetFile`.** Seen once, straight after a script reload, cause unknown; the same build passed when run again. A failed build removes its half-built copy (`CassBuild.Measure`); `ValidationScene.RemoveStrays` clears anything else left standing in the validation scene, where it would be in every later picture.
- **PhysBones cannot be simulated here** (it needs play mode). `blender/scripts/preview.py --pose sit,run,kick` lays the skirt over the legs geometrically; feel is only seen in a client.
- **Both fidelity levels must export the same mesh names, bones, blendshapes and UV tiles.** The lite meshes are swapped in by name.
- **`blender/cass.blend` and `cass-lite.blend` are generator output.** Change the generator and run `scripts/cass.sh build`; a hand-edited file is detected by its stamp and not overwritten without `--force`.
- **`Textures/cass-atlas.png` and `.json` are written by the model build**, not by hand. Colours are added in `cass-palette.toml`.
- **Poses in `gestures.json` may only turn extra bones**, never humanoid ones, and should leave `Ear1` nearly still: the ears stand in holes in the hat's brim.
- Performance is checked on the **built** avatar (`scripts/cass.sh verify`), not the prefab. Every component counts for rank even when disabled.

## House Rules

- Every third-party asset gets a `CREDITS.md` line at intake — source, author, licence, URL. Model assets are also credited in the avatar description (`Spec/variants.json`) as "name by author". Nothing proprietary and nothing licence-incompatible enters the repository; draw, model or synthesise it instead.
- Unity editor stays on 2022.3.22f1, the version VRChat supports.
- Version lives in `package.json`; a release publishes every package whose version matches the tag.
- The linking exception in `LICENSE_ADDENDUM` is load-bearing legal text. Don't reword it casually.
- Never weaken the `Packages/.gitignore` allowlist.
- Uploading asks the person uploading to confirm they hold the rights to the content. That confirmation is theirs; do not automate it.
