using System;
using System.Collections.Generic;
using System.Linq;
using nadena.dev.ndmf;
using UnityEditor;
using UnityEngine;
using VRC.Dynamics;
using VRC.SDK3.Dynamics.Constraint.Components;
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
    ///
    /// A mobile build also loses the physics of garments it cannot show
    /// (see <see cref="RemoveMobilePhysics"/>).
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
                var worn = root.GetComponent<CassWardrobe>();
                var wardrobe = worn != null ? worn.wardrobe : null;
                var lite = WirenookPlatform.IsMobile || root.GetComponent<CassLiteModel>() != null;
                if (lite || !string.IsNullOrEmpty(wardrobe)) UseModel(root, CassSpec.ModelFor(wardrobe, lite));
                if (WirenookPlatform.IsMobile)
                {
                    HideMobileTiles(root);
                    RemoveMobilePhysics(root);
                }
            });
        }

        /// <summary>
        /// Hides the tiles a mobile build is not to carry (uv-tiles.json,
        /// `mobile`), on copies of the materials that only this build sees.
        /// The mobile step that follows cuts whatever a material hides at
        /// rest out of the mesh (WirenookBuildPlugin), so this is what takes
        /// a garment out of Android and iOS builds while it stays the
        /// resting outfit on PC.
        /// </summary>
        public static void HideMobileTiles(GameObject avatar)
        {
            var left = CassSpec.Tiles().Tiles.Where(tile => tile.Shown && !tile.Mobile).ToList();
            if (left.Count == 0) return;

            var copies = new Dictionary<Material, Material>();
            foreach (var renderer in avatar.GetComponentsInChildren<Renderer>(true))
            {
                var materials = renderer.sharedMaterials;
                for (var i = 0; i < materials.Length; i++)
                {
                    var source = materials[i];
                    if (source == null || !source.HasProperty(ToonMaterial.TileProperty(0, 0))) continue;
                    if (!copies.TryGetValue(source, out var copy))
                    {
                        copy = new Material(source) { name = source.name };
                        foreach (var tile in left) copy.SetFloat(ToonMaterial.TileProperty(tile.Column, tile.Row), 1f);
                        copies[source] = copy;
                    }

                    materials[i] = copy;
                }

                renderer.sharedMaterials = materials;
            }
        }

        /// <summary>
        /// Removes the PhysBones a mobile build has no use or no room for,
        /// and the colliders nothing else uses.
        ///
        /// No mobile shader can hide a UV tile, so a tile hidden at rest is
        /// cut away for good (WirenookBuildPlugin). A chain that carries
        /// only such a tile (skeleton.json, `tile`) is then moving nothing,
        /// but VRChat would still count it, and past its limits strips every
        /// dynamic from the avatar. A chain marked `pcOnly` goes whether its
        /// garment is shown or not: the skirt's thirty bones against four
        /// colliders are several times what Android and iOS allow. Avatar
        /// Optimizer drops or merges the bare bones afterwards.
        ///
        /// A bone that is carried with a limb (`follow`) and has lost its
        /// physics this way takes the larger share of the limb's turn that
        /// the spec gives for that case: with no collider left to keep a
        /// knee from coming through the cloth, the cloth has to go further
        /// with the knee.
        /// </summary>
        public static void RemoveMobilePhysics(GameObject avatar)
        {
            var tiles = CassSpec.Tiles();
            var skeleton = CassSpec.Skeleton();
            var cut = new HashSet<string>(skeleton.ChainRoots()
                .Where(chain => chain.PcOnly || (chain.Tile != null && !(tiles.Get(chain.Tile).Shown && tiles.Get(chain.Tile).Mobile)))
                .Select(chain => chain.Name));
            if (cut.Count == 0) return;

            var kept = new HashSet<VRCPhysBoneColliderBase>();
            var orphaned = new HashSet<VRCPhysBoneColliderBase>();
            foreach (var bone in avatar.GetComponentsInChildren<VRCPhysBoneBase>(true))
            {
                var removed = cut.Contains(bone.GetRootTransform().name);
                (removed ? orphaned : kept).UnionWith(bone.colliders.Where(collider => collider != null));
                if (removed) UnityEngine.Object.DestroyImmediate(bone);
            }

            foreach (var collider in orphaned.Where(collider => !kept.Contains(collider)))
                UnityEngine.Object.DestroyImmediate(collider);

            var bones = avatar.GetComponentsInChildren<Transform>(true);
            foreach (var follow in skeleton.FollowBones().Where(bone => cut.Contains(bone.Name)))
            {
                var helper = bones.First(bone => bone.name == follow.Name);
                helper.GetComponent<VRCRotationConstraint>().GlobalWeight = follow.FollowWeightAlone;
            }
        }

        /// <summary>
        /// Exchanges every mesh that comes from the export the prefabs hold
        /// for its namesake in another: the low-polygon level, another
        /// wardrobe, or both.
        /// </summary>
        public static void UseModel(GameObject avatar, string modelPath)
        {
            var full = new HashSet<Mesh>(AssetDatabase.LoadAllAssetsAtPath(CassSpec.ModelPath).OfType<Mesh>());
            var lite = AssetDatabase.LoadAssetAtPath<GameObject>(modelPath);
            if (lite == null)
                throw new InvalidOperationException("The model this build is made from is missing; export it from Blender (scripts/cass.sh export): " + modelPath);
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
                    throw new InvalidOperationException(modelPath + " has no mesh named \"" + renderer.name + "\"; every export must have the same objects.");
                if (source.sharedMesh.blendShapeCount != renderer.sharedMesh.blendShapeCount)
                    throw new InvalidOperationException("\"" + renderer.name + "\" has " + source.sharedMesh.blendShapeCount +
                                                        " blendshapes in " + modelPath + " and " + renderer.sharedMesh.blendShapeCount + " in the full one.");

                var missing = source.bones.Where(bone => !bones.ContainsKey(bone.name)).Select(bone => bone.name).ToList();
                if (missing.Count > 0)
                    throw new InvalidOperationException("The avatar lacks bones that \"" + renderer.name + "\" in " + modelPath + " is skinned to: " + string.Join(", ", missing));

                renderer.sharedMesh = source.sharedMesh;
                renderer.bones = source.bones.Select(bone => bones[bone.name]).ToArray();
            }
        }
    }
}
