---
name: cass-avatar
description: Cassidy's VRChat avatar as a generated, non-destructive pipeline — Blender export, specs, generated Unity assets, prefab variants, build-time optimisation, policy-checked uploads; standalone feature packages mounted as submodules
---

# cass-avatar

Unity 2022.3 project at the repository root. The avatar is the VPM package
`Packages/net.wirenook.cass`; five standalone packages it builds on are git
submodules under `modules/` and are referenced in place from
`Packages/manifest.json`. Code is AGPL-3.0-or-later with the VRChat/Unity
linking exception in `LICENSE_ADDENDUM`.

Almost everything in Unity is **generated from code and specs**. Change the
spec or the generator and rebuild; do not hand-edit generated assets.

## Repo Map

- `Packages/net.wirenook.cass/Spec/` — the contracts, read by both Blender and Unity: `blendshapes.json`, `skeleton.json`, `uv-tiles.json`, `gestures.json`, `variants.json`, `proportions.json`.
- `Packages/net.wirenook.cass/BlenderExports/` — the only place Blender exports land. Import settings are applied in code (`Editor/CassModelImporter.cs`).
- `Packages/net.wirenook.cass/Editor/` — generators (`CassMaterials`, `CassFx`, `CassMenus`, `CassPrefabs`), entry points (`CassBuild`), post-build checks (`CassChecks`), upload automation (`CassUpload`, `CassThumbnail`).
- `Packages/net.wirenook.cass/Runtime/Core/` — engine-free logic (upload policy, tile rules, gesture rules), unit-tested headless.
- `Packages/net.wirenook.cass/{Generated,Materials,Prefabs}/` — generator output, committed. `Prefabs/cass-root.prefab` is the single root avatar prefab (a variant of the model); `Prefabs/Variants/*.prefab` are the upload variants.
- `blender/` — `cass.blend` and the headless scripts that build the placeholder, validate and export. See `blender/README.md`.
- `modules/<repo>/` — submodules: `wirenook-assets`, `locomotion`, `world-sync`, `avatar-stations`, `adventure-tools`. Each is its own repository with its own README, SKILL.md, CI and version.
- `Assets/Validation/` and `Assets/Scenes/Validation.unity` — cameras, lighting conditions, poses and the contact-sheet renderer. Harness only; not shipped.
- `Assets/DevTools/UnityBridge/` — the file bridge that lets scripts drive the open editor.
- `tools/thumbnail/`, `tools/contact_sheet.py`, `art/banner/` — Python and SVG tooling outside Unity.
- `ref/` — private reference art. Never publish, embed or trace it.
- `Packages/com.vrchat.core.bootstrap/`, `Packages/vpm-manifest.json`, `Packages/.gitignore` — inherited from the template: the bootstrapper is vendored byte-for-byte, VPM dependencies are edited with a VPM client (`vrc-get`/ALCOM), and the allowlist keeps resolver-installed packages out of git.

## Commands

```bash
scripts/cass.sh export|rebuild|verify|report|sheets|preview|upload [slug]   # see the script header
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
- Blendshape, bone and tile names live in `Spec/`. Add a name there first; Blender's validation and Unity's generators both read it.
- Performance is checked on the **built** avatar (`scripts/cass.sh verify`), not the prefab. Every component counts for rank even when disabled.

## House Rules

- Every third-party asset gets a `CREDITS.md` line at intake — source, author, licence, URL. Nothing proprietary and nothing licence-incompatible enters the repository; draw, model or synthesise it instead.
- Unity editor stays on 2022.3.22f1, the version VRChat supports.
- Version lives in `package.json`; a release publishes every package whose version matches the tag.
- The linking exception in `LICENSE_ADDENDUM` is load-bearing legal text. Don't reword it casually.
- Never weaken the `Packages/.gitignore` allowlist.
- Uploading asks the person uploading to confirm they hold the rights to the content. That confirmation is theirs; do not automate it.
