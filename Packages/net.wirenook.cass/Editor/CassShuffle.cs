using System;
using System.Collections.Generic;
using System.Linq;
using nadena.dev.modular_avatar.core;
using UnityEditor;
using UnityEditor.Animations;
using UnityEngine;
using VRC.Dynamics;
using VRC.SDK3.Avatars.Components;
using VRC.SDK3.Dynamics.Contact.Components;
using VRC.SDKBase;
using Wirenook.Assets.Editor;
using Wirenook.Cass.Core;

namespace Wirenook.Cass.Editor
{
    /// <summary>
    /// Generates the outfit shuffle: a feature for a variant of its own that
    /// changes what the avatar is wearing every time someone looks away from
    /// it and back.
    ///
    /// "Someone" is each viewer separately. Nothing here is synced: every
    /// client notices for itself when it stops drawing the avatar, and rolls
    /// its own outfit when it starts again, so two people looking at the
    /// same avatar need not agree on what it has on, and nobody ever sees
    /// the change happen.
    ///
    /// Noticing is the trick VRLabs' IsRendering Detection established. An
    /// animator of its own, under the avatar, is set to stop entirely while
    /// nothing it animates is being drawn, and all it does is hold a contact
    /// sender switched on. The avatar's main animator holds the same sender
    /// switched off. While the avatar is in view the inner animator runs
    /// after the main one and wins, a receiver beside the sender feels it,
    /// and "seen" is true; out of view the inner animator stops, the main
    /// one's "off" stands, and "seen" goes false. Only the idea is taken
    /// from VRLabs' prefab (MIT), none of its files.
    ///
    /// The outfit is laid over the wearer's own choices by a layer that
    /// comes after the outfit layers and writes every outfit tile, so it
    /// needs no parameters of theirs and cannot disturb what they sync.
    /// </summary>
    public static class CassShuffle
    {
        public const string PrefabPath = CassSpec.PrefabFolder + "/Features/Cass Outfit Shuffle.prefab";
        private const string ShuffleController = CassSpec.GeneratedFolder + "/shuffle-fx.controller";
        private const string SeenController = CassSpec.GeneratedFolder + "/shuffle-seen-fx.controller";
        private const string WatchController = CassSpec.GeneratedFolder + "/shuffle-watch.controller";
        private const string BoundsMesh = CassSpec.GeneratedFolder + "/shuffle-bounds.asset";

        /// <summary>True on a client while it is drawing the avatar. Never synced.</summary>
        private const string Seen = "Shuffle/Seen";

        /// <summary>Which outfit this client has rolled. Never synced.</summary>
        private const string Pick = "Shuffle/Pick";

        /// <summary>Seconds the avatar has to be out of view before coming back counts, so the edge of the screen does not flicker outfits.</summary>
        private const float AwaySeconds = 0.6f;

        /// <summary>
        /// The outfits it rolls between, as values of the outfit switches in
        /// uv-tiles.json; a switch left out rests at its default.
        /// </summary>
        private static readonly (string name, (string parameter, bool value)[] wearing)[] Outfits =
        {
            ("everyday", new (string, bool)[0]),
            ("hat", new[] { ("Outfit/Hat", true) }),
            ("shorts", new[] { ("Outfit/Skirt", false) }),
            ("no vest", new[] { ("Outfit/Vest", false) }),
            ("long hair", new[] { ("Hair/Long", true) }),
            ("long hair and hat", new[] { ("Hair/Long", true), ("Outfit/Hat", true) }),
            ("shorts and hat, no vest", new[] { ("Outfit/Skirt", false), ("Outfit/Vest", false), ("Outfit/Hat", true) }),
            ("shorts, long hair", new[] { ("Outfit/Skirt", false), ("Hair/Long", true) }),
            ("barefoot, long hair", new[] { ("Outfit/Shoes", false), ("Hair/Long", true) }),
            ("shorts, no vest", new[] { ("Outfit/Skirt", false), ("Outfit/Vest", false) }),
        };

        public static void Rebuild()
        {
            var tiles = CassSpec.Tiles();
            var known = tiles.Defaults().Select(parameter => parameter.Parameter).ToList();
            foreach (var (name, wearing) in Outfits)
            {
                foreach (var (parameter, _) in wearing)
                {
                    if (!known.Contains(parameter))
                        throw new InvalidOperationException("The shuffle's \"" + name + "\" outfit names " + parameter + ", which uv-tiles.json does not have.");
                }
            }

            var model = AssetDatabase.LoadAssetAtPath<GameObject>(CassSpec.ModelPath);
            if (model == null) throw new System.IO.FileNotFoundException("Export the model from Blender first: " + CassSpec.ModelPath);
            var material = CassMaterials.Body;
            var renderers = model.GetComponentsInChildren<SkinnedMeshRenderer>(true)
                .Where(renderer => renderer.sharedMaterials.Contains(material))
                .Select(renderer => AnimationUtility.CalculateTransformPath(renderer.transform, model.transform))
                .ToList();

            // Something for the inner animator to be culled by: a renderer
            // that draws nothing and has bounds the size of the figure.
            var bounds = AssetFolders.LoadOrCreate(BoundsMesh, () => new Mesh());
            bounds.Clear();
            bounds.name = "shuffle-bounds";
            bounds.vertices = new[] { Vector3.zero, Vector3.zero, Vector3.zero };
            bounds.triangles = new[] { 0, 1, 2 };
            bounds.bounds = new Bounds(new Vector3(0f, 0.1f, 0f), new Vector3(1.4f, 2.4f, 1.4f));
            EditorUtility.SetDirty(bounds);

            // The inner animator: one state that holds the sender on.
            var watch = ControllerBuilder.Rebuild(WatchController);
            watch.Layer("Hold").State("On", watch.Clip("sender on", clip =>
                clip.Constant("Sender", typeof(VRCContactSender), "m_Enabled", 1f).Loop()));
            watch.Save();

            FeaturePrefab.Edit(PrefabPath, root =>
            {
                var mount = FeaturePrefab.Child(root, "Mount");
                FeaturePrefab.AttachToBone(mount, HumanBodyBones.Hips);
                mount.GetComponent<ModularAvatarBoneProxy>().attachmentMode = BoneProxyAttachmentMode.AsChildKeepRotation;

                var inner = FeaturePrefab.Child(mount, "Watch");
                var animator = FeaturePrefab.Ensure<Animator>(inner);
                animator.runtimeAnimatorController = watch.Controller;
                animator.cullingMode = AnimatorCullingMode.CullCompletely;
                animator.applyRootMotion = false;

                var drawn = FeaturePrefab.Child(inner, "Bounds");
                FeaturePrefab.Ensure<MeshFilter>(drawn).sharedMesh = bounds;
                var renderer = FeaturePrefab.Ensure<MeshRenderer>(drawn);
                renderer.sharedMaterial = material;
                renderer.shadowCastingMode = UnityEngine.Rendering.ShadowCastingMode.Off;
                renderer.receiveShadows = false;

                const string tag = "Wirenook/Cass/Shuffle";
                var senderHolder = FeaturePrefab.Child(inner, "Sender");
                var sender = FeaturePrefab.Ensure<VRCContactSender>(senderHolder);
                sender.shapeType = ContactBase.ShapeType.Sphere;
                sender.radius = 0.05f;
                sender.collisionTags = new List<string> { tag };
                // Every client feels for itself, so this is not local-only.
                sender.localOnly = false;
                sender.enabled = false;

                var receiver = FeaturePrefab.Ensure<VRCContactReceiver>(FeaturePrefab.Child(mount, "Receiver"));
                receiver.shapeType = ContactBase.ShapeType.Sphere;
                receiver.radius = 0.05f;
                receiver.collisionTags = new List<string> { tag };
                receiver.localOnly = false;
                receiver.allowSelf = true;
                receiver.allowOthers = false;
                receiver.receiverType = ContactReceiver.ReceiverType.Constant;
                receiver.parameter = Seen;

                // The main animator's half: the sender held off.
                var seen = ControllerBuilder.Rebuild(SeenController);
                seen.Layer("Shuffle Seen").State("Off", seen.Clip("sender off", clip =>
                    clip.Constant(FeaturePrefab.PathTo(root, senderHolder.transform), typeof(VRCContactSender), "m_Enabled", 0f)));
                seen.Save();
                FeaturePrefab.Merge(root, seen.Controller);

                var fx = ControllerBuilder.Rebuild(ShuffleController);
                fx.Bool(Seen).Int(Pick);

                // Rolling. Out of view for a moment arms it; back in view rolls.
                var roll = fx.Layer("Shuffle Roll");
                var watching = roll.State("Watching");
                var leaving = roll.State("Leaving", fx.Clip("shuffle away", clip => clip.Hold(AwaySeconds)));
                var armed = roll.State("Armed");
                var rolling = roll.State("Rolling");
                rolling.Behaviour<VRCAvatarParameterDriver>(driver =>
                {
                    // On every client, each for itself.
                    driver.localOnly = false;
                    driver.parameters = new List<VRC_AvatarParameterDriver.Parameter>
                    {
                        new VRC_AvatarParameterDriver.Parameter
                        {
                            type = VRC_AvatarParameterDriver.ChangeType.Random, name = Pick, valueMin = 0, valueMax = Outfits.Length - 1,
                        },
                    };
                });
                watching.To(leaving).IfFalse(Seen);
                leaving.To(watching).IfTrue(Seen);
                leaving.To(armed).AfterTime(1f);
                armed.To(rolling).IfTrue(Seen);
                rolling.To(watching).AfterTime(0f);

                // Wearing. One state per outfit, each writing every tile a
                // switch or a garment can change, on every renderer that
                // wears the body material (the ones the build merges).
                var changing = tiles.Tiles.Where(tile => tile.Toggle != null).Concat(tiles.Zones()).Distinct().ToList();
                var wear = fx.Layer("Shuffle Wear");
                for (var outfit = 0; outfit < Outfits.Length; outfit++)
                {
                    var shown = tiles.ResolveFor(Outfits[outfit].wearing.ToDictionary(entry => entry.parameter, entry => entry.value));
                    var state = wear.State(Outfits[outfit].name, fx.Clip("shuffle " + Outfits[outfit].name, clip =>
                    {
                        foreach (var tile in changing)
                        {
                            foreach (var path in renderers)
                                clip.Material<SkinnedMeshRenderer>(path, ToonMaterial.TileProperty(tile.Column, tile.Row), shown[tile.Id] ? 0f : 1f);
                        }
                    }));
                    wear.Any(state).Equal(Pick, outfit);
                }

                fx.Save();

                // Renderers are named by their path from the avatar's root,
                // so this half is merged on an object of its own.
                var holder = FeaturePrefab.Child(root, "Wear");
                var merge = FeaturePrefab.Ensure<ModularAvatarMergeAnimator>(holder);
                merge.animator = fx.Controller;
                merge.layerType = VRCAvatarDescriptor.AnimLayerType.FX;
                merge.pathMode = MergeAnimatorPathMode.Absolute;
                merge.matchAvatarWriteDefaults = true;
                merge.deleteAttachedAnimator = true;

                FeaturePrefab.Parameters(root,
                    new ParameterConfig { nameOrPrefix = Seen, syncType = ParameterSyncType.NotSynced, localOnly = true },
                    new ParameterConfig { nameOrPrefix = Pick, syncType = ParameterSyncType.NotSynced, localOnly = true });
                // The outfits are UV tiles, which no mobile shader can hide.
                FeaturePrefab.Describe(root, "outfit-shuffle", "Outfit shuffle", "outfit", "outfit shuffle", 50, pcOnly: true);
            });
        }
    }
}
