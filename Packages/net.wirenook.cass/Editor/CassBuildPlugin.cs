using System;
using System.Collections.Generic;
using System.Linq;
using nadena.dev.ndmf;
using UnityEditor;
using UnityEngine;
using Wirenook.Assets.Editor;
using Wirenook.Cass.Editor;

[assembly: ExportsPlugin(typeof(CassBuildPlugin))]

namespace Wirenook.Cass.Editor
{
    /// <summary>
    /// The avatar's own step in the non-destructive build: choosing between
    /// its two fidelity levels.
    ///
    /// Blender exports the avatar twice, from the same generator and on the
    /// same skeleton: <c>cass.fbx</c>, and <c>cass-lite.fbx</c> with the body
    /// base's low-polygon mesh and coarser modelled parts. The prefabs hold
    /// the full model. For an Android or iOS build, or a variant marked
    /// <see cref="CassLiteModel"/>, each mesh is exchanged for the one of the
    /// same name in the lite export, on the copy the build works on.
    /// Everything else (materials, animators, physics, toggles) is shared,
    /// because both levels have the same objects, bones, blendshapes and UV
    /// tiles.
    /// </summary>
    public sealed class CassBuildPlugin : Plugin<CassBuildPlugin>
    {
        public override string QualifiedName => "net.wirenook.cass";
        public override string DisplayName => "Cass";

        private const string ModularAvatar = "nadena.dev.modular-avatar";

        protected override void Configure()
        {
            // First of all: every later step should only ever see the meshes that ship.
            InPhase(BuildPhase.Resolving).BeforePlugin(ModularAvatar).Run("Use the low-polygon model", context =>
            {
                var root = context.AvatarRootObject;
                if (WirenookPlatform.IsMobile || root.GetComponent<CassLiteModel>() != null) UseLiteModel(root);
            });
        }

        /// <summary>Exchanges every mesh that comes from the full export for its namesake in the lite one.</summary>
        public static void UseLiteModel(GameObject avatar)
        {
            var full = new HashSet<Mesh>(AssetDatabase.LoadAllAssetsAtPath(CassSpec.ModelPath).OfType<Mesh>());
            var lite = AssetDatabase.LoadAssetAtPath<GameObject>(CassSpec.LiteModelPath);
            if (lite == null)
                throw new InvalidOperationException("The lite model is missing; export it from Blender (scripts/cass.sh export): " + CassSpec.LiteModelPath);
            var sources = lite.GetComponentsInChildren<SkinnedMeshRenderer>(true).ToDictionary(renderer => renderer.name);

            // The two exports list a mesh's bones in their own order, so bones are matched by name.
            var bones = new Dictionary<string, Transform>();
            foreach (var transform in avatar.GetComponentsInChildren<Transform>(true))
            {
                if (!bones.ContainsKey(transform.name)) bones[transform.name] = transform;
            }

            foreach (var renderer in avatar.GetComponentsInChildren<SkinnedMeshRenderer>(true))
            {
                if (renderer.sharedMesh == null || !full.Contains(renderer.sharedMesh)) continue;
                if (!sources.TryGetValue(renderer.name, out var source))
                    throw new InvalidOperationException("The lite model has no mesh named \"" + renderer.name + "\"; both levels must export the same objects.");
                if (source.sharedMesh.blendShapeCount != renderer.sharedMesh.blendShapeCount)
                    throw new InvalidOperationException("\"" + renderer.name + "\" has " + source.sharedMesh.blendShapeCount +
                                                        " blendshapes in the lite model and " + renderer.sharedMesh.blendShapeCount + " in the full one.");

                var missing = source.bones.Where(bone => !bones.ContainsKey(bone.name)).Select(bone => bone.name).ToList();
                if (missing.Count > 0)
                    throw new InvalidOperationException("The avatar lacks bones the lite model's \"" + renderer.name + "\" is skinned to: " + string.Join(", ", missing));

                renderer.sharedMesh = source.sharedMesh;
                renderer.bones = source.bones.Select(bone => bones[bone.name]).ToArray();
            }
        }
    }
}
