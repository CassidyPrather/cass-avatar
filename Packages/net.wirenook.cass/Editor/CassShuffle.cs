using System;
using System.Collections.Generic;
using System.Linq;
using nadena.dev.modular_avatar.core;
using UnityEditor;
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
    /// Generates the outfit shuffle: a switch in the Outfit menu that makes
    /// the avatar change what it is wearing every time someone looks away
    /// from it and back.
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
    /// That layer has no state in which it writes nothing (with Write
    /// Defaults on there is no such state), so the switch works on its
    /// weight instead: at none, the layer changes nothing and the wearer's
    /// own choices show.
    ///
    /// The parts are public: a fuller shuffle (the wirenook bot's package
    /// has one, which rolls other clothes and another body as well) is put
    /// together from the same ones.
    /// </summary>
    public static class CassShuffle
    {
        public const string PrefabPath = CassSpec.PrefabFolder + "/Features/Cass Outfit Shuffle.prefab";

        /// <summary>What the feature is called in builds and reports; a fuller shuffle says it replaces this.</summary>
        public const string FeatureId = "outfit-shuffle";

        private const string ShuffleController = CassSpec.GeneratedFolder + "/shuffle-fx.controller";
        private const string SeenController = CassSpec.GeneratedFolder + "/shuffle-seen-fx.controller";
        private const string WatchController = CassSpec.GeneratedFolder + "/shuffle-watch.controller";
        private const string BoundsMesh = CassSpec.GeneratedFolder + "/shuffle-bounds.asset";

        /// <summary>True on a client while it is drawing the avatar. Never synced.</summary>
        public const string Seen = "Shuffle/Seen";

        /// <summary>Which outfit this client has rolled. Never synced.</summary>
        public const string Pick = "Shuffle/Pick";

        /// <summary>The menu's switch. Synced and kept, off to begin with.</summary>
        public const string Switch = "Outfit/Shuffle";

        /// <summary>Seconds the avatar has to be out of view before coming back counts, so the edge of the screen does not flicker outfits.</summary>
        private const float AwaySeconds = 0.6f;

        /// <summary>
        /// The outfits it rolls between, as values of the outfit switches in
        /// uv-tiles.json; a switch left out rests at its default.
        /// </summary>
        public static readonly (string name, (string parameter, bool value)[] wearing)[] Outfits =
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
            FeaturePrefab.Edit(PrefabPath, root =>
            {
                Watch(root);

                // The layers are named by their place in this controller:
                // rolling 0, wearing 1, the switch 2. Modular Avatar moves
                // the numbers along when it merges.
                var fx = ControllerBuilder.Rebuild(ShuffleController);
                Roll(fx, Outfits.Length);
                Wear(fx, Outfits.Select((outfit, pick) => (outfit.name, Shown(outfit.wearing), new[] { pick })).ToList());
                Switching(fx, wearLayer: 1);
                fx.Save();

                Install(root, fx.Controller);
                // The outfits are UV tiles, which no mobile shader can hide.
                FeaturePrefab.Describe(root, FeatureId, "Outfit shuffle", "outfit", "outfit shuffle", 50, pcOnly: true);
            });
        }

        /// <summary>Which tiles show when the outfit switches have these values and the rest are at their defaults, by tile id.</summary>
        public static Dictionary<string, bool> Shown(IEnumerable<(string parameter, bool value)> wearing)
        {
            var tiles = CassSpec.Tiles();
            var known = tiles.Defaults().Select(parameter => parameter.Parameter).ToList();
            var switches = wearing.ToList();
            foreach (var (parameter, _) in switches)
            {
                if (!known.Contains(parameter))
                    throw new InvalidOperationException("A shuffled outfit names " + parameter + ", which uv-tiles.json does not have.");
            }

            return tiles.ResolveFor(switches.ToDictionary(entry => entry.parameter, entry => entry.value));
        }

        /// <summary>The tiles a switch or a garment can change: what the wearing layer writes.</summary>
        public static List<Tile> Changing()
        {
            var tiles = CassSpec.Tiles();
            return tiles.Tiles.Where(tile => tile.Toggle != null).Concat(tiles.Zones()).Distinct().ToList();
        }

        /// <summary>Paths, from the avatar's root, of the model's renderers that wear the body material (the ones the build merges).</summary>
        public static List<string> BodyRenderers()
        {
            var model = AssetDatabase.LoadAssetAtPath<GameObject>(CassSpec.ModelPath);
            if (model == null) throw new System.IO.FileNotFoundException("Export the model from Blender first: " + CassSpec.ModelPath);
            return model.GetComponentsInChildren<SkinnedMeshRenderer>(true)
                .Where(renderer => renderer.sharedMaterials.Contains(CassMaterials.Body))
                .Select(renderer => AnimationUtility.CalculateTransformPath(renderer.transform, model.transform))
                .ToList();
        }

        /// <summary>
        /// The part that notices being looked at: under <paramref name="root"/>,
        /// an animator that stops while it is not drawn, the contact it
        /// holds on, and the receiver that reads <see cref="Seen"/> from it;
        /// and the main animator's half, which holds the contact off.
        /// </summary>
        public static void Watch(GameObject root)
        {
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
            renderer.sharedMaterial = CassMaterials.Body;
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

            // The main animator's half: the sender held off. The path is the
            // same in every prefab built from these parts, so they share it.
            var seen = ControllerBuilder.Rebuild(SeenController);
            seen.Layer("Shuffle Seen").State("Off", seen.Clip("sender off", clip =>
                clip.Constant(FeaturePrefab.PathTo(root, senderHolder.transform), typeof(VRCContactSender), "m_Enabled", 0f)));
            seen.Save();
            FeaturePrefab.Merge(root, seen.Controller);
        }

        /// <summary>
        /// The layer that rolls: out of view for a moment arms it, and back
        /// in view sets <see cref="Pick"/> to a whole number below
        /// <paramref name="picks"/>, on every client for itself.
        /// </summary>
        public static void Roll(ControllerBuilder fx, int picks)
        {
            fx.Bool(Seen).Int(Pick);
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
                        type = VRC_AvatarParameterDriver.ChangeType.Random, name = Pick, valueMin = 0, valueMax = picks - 1,
                    },
                };
            });
            watching.To(leaving).IfFalse(Seen);
            leaving.To(watching).IfTrue(Seen);
            leaving.To(armed).AfterTime(1f);
            armed.To(rolling).IfTrue(Seen);
            rolling.To(watching).AfterTime(0f);
        }

        /// <summary>
        /// The layer that wears: one state per outfit, each writing every
        /// tile a switch or a garment can change (<see cref="Changing"/>), on
        /// every renderer that wears the body material. It starts with no
        /// weight; <see cref="Switching"/> gives it some.
        /// </summary>
        /// <param name="outfits">Each outfit's name, which tiles show in it (by id; a tile left out is hidden), and the picks that wear it.</param>
        public static void Wear(ControllerBuilder fx, IList<(string name, Dictionary<string, bool> shown, int[] picks)> outfits)
        {
            var renderers = BodyRenderers();
            var changing = Changing();
            var wear = fx.Layer("Shuffle Wear", weight: 0f);
            foreach (var (name, shown, picks) in outfits)
            {
                var state = wear.State(name, fx.Clip("shuffle " + name, clip =>
                {
                    foreach (var tile in changing)
                    {
                        var hidden = !(shown.TryGetValue(tile.Id, out var on) && on);
                        foreach (var path in renderers)
                            clip.Material<SkinnedMeshRenderer>(path, ToonMaterial.TileProperty(tile.Column, tile.Row), hidden ? 1f : 0f);
                    }
                }));
                var when = wear.Any(state);
                for (var i = 0; i < picks.Length; i++)
                {
                    if (i > 0) when.Or();
                    when.Equal(Pick, picks[i]);
                }
            }
        }

        /// <summary>
        /// The layer that hides what <see cref="Wear"/> leaves alone: the
        /// tiles no switch changes (the head and hands, the eyes), for a
        /// roll in which the whole figure is to be gone. One state, and no
        /// weight until <see cref="Switching"/> gives it some. The wearing
        /// layer cannot do this itself: it would then be writing the eyes'
        /// tiles in every outfit, over the gestures that change them.
        ///
        /// Props that the build joins to the avatar's mesh sit on the tile
        /// that is never otherwise hidden, and go with it.
        /// </summary>
        public static void Bare(ControllerBuilder fx)
        {
            var renderers = BodyRenderers();
            var changing = Changing();
            var rest = CassSpec.Tiles().Tiles.Where(tile => !changing.Contains(tile)).ToList();
            fx.Layer("Shuffle Bare", weight: 0f).State("Gone", fx.Clip("shuffle bare", clip =>
            {
                foreach (var tile in rest)
                {
                    foreach (var path in renderers)
                        clip.Material<SkinnedMeshRenderer>(path, ToonMaterial.TileProperty(tile.Column, tile.Row), 1f);
                }
            }));
        }

        /// <summary>
        /// The layer the menu's switch works: it gives the wearing layer its
        /// weight while the switch is on and takes it away again. With a
        /// <paramref name="bareLayer"/> it also gives that layer weight while
        /// the pick is one of <paramref name="barePicks"/>. Layers are named
        /// by their place in this controller.
        /// </summary>
        public static void Switching(ControllerBuilder fx, int wearLayer, int bareLayer = -1, int[] barePicks = null)
        {
            fx.Bool(Switch);
            var switching = fx.Layer("Shuffle Switch");
            void Weigh(StateBuilder state, int layer, float weight) => state.Behaviour<VRCAnimatorLayerControl>(control =>
            {
                control.playable = VRC_AnimatorLayerControl.BlendableLayer.FX;
                control.layer = layer;
                control.goalWeight = weight;
                control.blendDuration = 0f;
            });

            var plain = switching.State("Plain");
            var shuffled = switching.State("Shuffled");
            Weigh(plain, wearLayer, 0f);
            Weigh(shuffled, wearLayer, 1f);
            plain.To(shuffled).IfTrue(Switch);
            shuffled.To(plain).IfFalse(Switch);
            if (bareLayer < 0) return;

            barePicks = barePicks ?? new int[0];
            var bare = switching.State("Shuffled Bare");
            Weigh(plain, bareLayer, 0f);
            Weigh(shuffled, bareLayer, 0f);
            Weigh(bare, wearLayer, 1f);
            Weigh(bare, bareLayer, 1f);
            foreach (var pick in barePicks)
            {
                // Not from Plain: the switch has to have been on for a frame first.
                shuffled.To(bare).IfTrue(Switch).Equal(Pick, pick);
            }

            bare.To(plain).IfFalse(Switch);
            var back = bare.To(shuffled);
            foreach (var pick in barePicks) back.NotEqual(Pick, pick);
        }

        /// <summary>
        /// Merges the wearing controller, puts the switch in the Outfit menu
        /// and declares the parameters. The controller names the body's
        /// renderers by their path from the avatar's root, so it is merged
        /// on an object of its own.
        /// </summary>
        public static void Install(GameObject root, RuntimeAnimatorController controller)
        {
            var holder = FeaturePrefab.Child(root, "Wear");
            var merge = FeaturePrefab.Ensure<ModularAvatarMergeAnimator>(holder);
            merge.animator = controller;
            merge.layerType = VRCAvatarDescriptor.AnimLayerType.FX;
            merge.pathMode = MergeAnimatorPathMode.Absolute;
            merge.matchAvatarWriteDefaults = true;
            merge.deleteAttachedAnimator = true;

            // Into the Outfit menu, beside the garments it shuffles.
            var entry = FeaturePrefab.Child(root, "Menu");
            FeaturePrefab.InstallMenu(entry);
            entry.GetComponent<ModularAvatarMenuInstaller>().installTargetMenu =
                AssetDatabase.LoadAssetAtPath<VRC.SDK3.Avatars.ScriptableObjects.VRCExpressionsMenu>(CassMenus.OutfitMenuPath);
            FeaturePrefab.MenuToggle(entry, "Shuffle", "reset", Switch);

            FeaturePrefab.Parameters(root,
                FeaturePrefab.SyncedBool(Switch, saved: true),
                new ParameterConfig { nameOrPrefix = Seen, syncType = ParameterSyncType.NotSynced, localOnly = true },
                new ParameterConfig { nameOrPrefix = Pick, syncType = ParameterSyncType.NotSynced, localOnly = true });
        }
    }
}
