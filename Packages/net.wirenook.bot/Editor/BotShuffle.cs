using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using nadena.dev.modular_avatar.core;
using UnityEditor;
using UnityEngine;
using Wirenook.Assets;
using Wirenook.Assets.Editor;
using Wirenook.Cass.Core;
using Wirenook.Cass.Editor;

namespace Wirenook.Bot.Editor
{
    /// <summary>
    /// Generates the fuller outfit shuffle, for the variant that is nothing
    /// else (cass-shuffle): cass's own (<see cref="CassShuffle"/>) with two
    /// guests in the rotation. It lives in this package because this is the
    /// one that knows both avatars.
    ///
    /// <b>The cyber wardrobe.</b> A wardrobe is otherwise a different avatar:
    /// its garments are the same meshes on the same UV tiles, exchanged at
    /// build time. Here the cyber garments ride along as meshes of their
    /// own, the low-polygon ones (the avatar has no triangles to spare for
    /// the others), and an outfit can take any garment from either wardrobe.
    ///
    /// <b>The robot.</b> In some rolls cass is gone altogether and the
    /// wirenook bot stands in her place. The two skeletons name their bones
    /// alike, and Modular Avatar merges an armature into the avatar's by
    /// name: each of the robot's bones becomes hers. So every rigid piece
    /// of the robot sits at her joint and turns as her limb turns. It is
    /// the robot drawn out to her build, with gaps where her limbs are
    /// longer than its own and a tangle where her fingers are, and it
    /// walks, sits and waves exactly as she does. The bones she has no
    /// name for (the projected ears, the tail) hang off the ones she has.
    /// Its face still works: the hands' expressions, the blink, and the
    /// visemes, which VRChat only puts on an avatar's own face and are done
    /// here from the <c>Viseme</c> parameter.
    ///
    /// Both guests are there all the time and hidden the way the outfits
    /// are, by UV tile: their materials are copies that rest with the tiles
    /// hidden, and a layer of this feature's own shows what a roll wears.
    /// With the switch off that layer shows nothing, and the Outfit menu
    /// rules as it does without the feature. Nothing is synced that cass's
    /// own shuffle does not sync.
    ///
    /// The feature says it replaces cass's own shuffle, which a variant of
    /// cass cannot take off; the build leaves that one out.
    /// </summary>
    public static class BotShuffle
    {
        public const string PrefabPath = BotBuild.Package + "/Prefabs/Cass Outfit Shuffle (Guests).prefab";
        public const string FeatureId = "outfit-shuffle-guests";

        private const string Generated = BotBuild.Package + "/Generated/Shuffle";
        private const string WearController = Generated + "/shuffle-guests-fx.controller";
        private const string GuestController = Generated + "/shuffle-guests-own-fx.controller";

        /// <summary>Of every twenty rolls, how many are the robot.</summary>
        private const int RobotPicks = 3;

        // The garments' tiles in uv-tiles.json.
        private const string Top = "outfit.default.top", Vest = "outfit.vest.layer", Skirt = "outfit.skirt.bottom",
            Shorts = "outfit.default.bottom", Boots = "outfit.default.shoes", Hat = "outfit.default.hat";

        /// <summary>
        /// The outfits with something from the cyber wardrobe in them: the
        /// outfit switches as in <see cref="CassShuffle.Outfits"/>, and the
        /// garments that are the cyber ones. A vest goes with the top it was
        /// fitted to.
        /// </summary>
        private static readonly (string name, (string parameter, bool value)[] wearing, string[] cyber)[] CyberOutfits =
        {
            ("cyber", new (string, bool)[0], new[] { Top, Vest, Skirt, Boots }),
            ("cyber with headset", new[] { ("Outfit/Hat", true) }, new[] { Top, Vest, Skirt, Boots, Hat }),
            ("cyber in shorts, long hair", new[] { ("Outfit/Skirt", false), ("Hair/Long", true) }, new[] { Top, Vest, Shorts, Boots }),
            ("cyber jacket, gingham skirt", new (string, bool)[0], new[] { Top, Vest }),
            ("sweater, cyber skirt and boots", new (string, bool)[0], new[] { Skirt, Boots }),
            ("cyber, no vest, headset, long hair", new[] { ("Outfit/Vest", false), ("Outfit/Hat", true), ("Hair/Long", true) }, new[] { Top, Skirt, Boots, Hat }),
            ("everyday with headset", new[] { ("Outfit/Hat", true) }, new[] { Hat }),
        };

        public static void Rebuild()
        {
            AssetFolders.Ensure(Generated);
            var tiles = CassSpec.Tiles();
            var garments = new[] { Top, Vest, Skirt, Shorts, Boots, Hat }.Select(tiles.Get).ToList();

            // What each pick wears. Cass's own outfits first, then the ones
            // with cyber garments, then the robot, which has several picks.
            var outfits = new List<(string name, Dictionary<string, bool> shown, string[] cyber)>();
            foreach (var (name, wearing) in CassShuffle.Outfits) outfits.Add((name, CassShuffle.Shown(wearing), new string[0]));
            foreach (var (name, wearing, cyber) in CyberOutfits) outfits.Add((name, CassShuffle.Shown(wearing), cyber));
            var robotPicks = Enumerable.Range(outfits.Count, RobotPicks).ToArray();
            var picks = outfits.Count + RobotPicks;

            // Copies of the materials that rest with the guests hidden.
            var cyberMaterial = Hidden(CassMaterials.Body, "cass (shuffle guest)", garments);
            var always = new List<Tile> { tiles.Get("always") };
            var robotMaterials = new[] { "bot", "bot-holo" }.ToDictionary(
                name => name,
                name => Hidden(AssetDatabase.LoadAssetAtPath<Material>(BotBuild.MaterialPath(name)), name + " (shuffle guest)", always));

            FeaturePrefab.Edit(PrefabPath, root =>
            {
                CassShuffle.Watch(root);

                // Cass herself, by paths from the avatar's root. Layers by
                // their place: rolling 0, wearing 1, bare 2, the switch 3.
                var wear = ControllerBuilder.Rebuild(WearController);
                CassShuffle.Roll(wear, picks);
                var worn = new List<(string name, Dictionary<string, bool> shown, int[] picks)>();
                for (var pick = 0; pick < outfits.Count; pick++)
                {
                    // A garment that is the cyber one is not also hers.
                    var hers = outfits[pick].shown.ToDictionary(entry => entry.Key, entry => entry.Value && !outfits[pick].cyber.Contains(entry.Key));
                    worn.Add((outfits[pick].name, hers, new[] { pick }));
                }

                worn.Add(("robot", new Dictionary<string, bool>(), robotPicks));
                CassShuffle.Wear(wear, worn);
                CassShuffle.Bare(wear);
                CassShuffle.Switching(wear, wearLayer: 1, bareLayer: 2, barePicks: robotPicks);
                wear.Save();
                CassShuffle.Install(root, wear.Controller);

                // The guests, by paths from their own holder.
                var guests = FeaturePrefab.Child(root, "Guests");
                var cyberModel = Guest(FeaturePrefab.Child(guests, "Cyber"), CassSpec.ModelFor("cyber", lite: true));
                var cyberRenderers = new List<string>();
                foreach (var renderer in cyberModel.GetComponentsInChildren<SkinnedMeshRenderer>(true))
                {
                    var garment = renderer.name.StartsWith("Outfit_", StringComparison.Ordinal);
                    // Her body is there already. Modular Avatar leaves out what is tagged so.
                    renderer.gameObject.tag = garment ? "Untagged" : "EditorOnly";
                    renderer.gameObject.SetActive(garment);
                    if (!garment) continue;
                    renderer.sharedMaterials = renderer.sharedMaterials.Select(_ => cyberMaterial).ToArray();
                    cyberRenderers.Add(FeaturePrefab.PathTo(guests, renderer.transform));
                }

                var robotModel = Guest(FeaturePrefab.Child(guests, "Robot"), BotBuild.ModelPath);
                var robotRenderers = new List<string>();
                foreach (var renderer in robotModel.GetComponentsInChildren<SkinnedMeshRenderer>(true))
                {
                    renderer.sharedMaterials = renderer.sharedMaterials
                        .Select(material => robotMaterials.TryGetValue(material.name.Replace(" (shuffle guest)", ""), out var copy) ? copy : material)
                        .ToArray();
                    robotRenderers.Add(FeaturePrefab.PathTo(guests, renderer.transform));
                }

                var robotFace = FeaturePrefab.PathTo(guests, robotModel.transform.Find("Body")
                                                             ?? throw new InvalidOperationException("The robot's model has no mesh named Body."));

                var own = ControllerBuilder.Rebuild(GuestController);
                own.Int(CassShuffle.Pick).Bool(CassShuffle.Switch).Int("GestureLeft").Int("GestureRight").Int("Viseme");

                AnimationClip Showing(string name, ICollection<string> cyber, bool robot) => own.Clip("shuffle guests " + name, clip =>
                {
                    foreach (var path in cyberRenderers)
                    {
                        foreach (var tile in garments)
                            clip.Material<SkinnedMeshRenderer>(path, ToonMaterial.TileProperty(tile.Column, tile.Row), cyber.Contains(tile.Id) ? 0f : 1f);
                    }

                    foreach (var path in robotRenderers)
                        clip.Material<SkinnedMeshRenderer>(path, ToonMaterial.TileProperty(always[0].Column, always[0].Row), robot ? 0f : 1f);
                });

                // One state for nobody, where it starts and where it is with
                // the switch off; one for each roll that has a guest in it.
                var layer = own.Layer("Shuffle Guests");
                var nobody = layer.State("Nobody", Showing("nobody", new string[0], false));
                var none = layer.Any(nobody).IfFalse(CassShuffle.Switch);
                for (var pick = 0; pick < outfits.Count; pick++)
                {
                    if (outfits[pick].cyber.Length == 0)
                    {
                        none.Or().Equal(CassShuffle.Pick, pick);
                        continue;
                    }

                    // Only what the outfit's switches leave showing: the vest goes when the top does.
                    var showing = outfits[pick].cyber.Where(id => outfits[pick].shown.TryGetValue(id, out var on) && on).ToList();
                    var state = layer.State(outfits[pick].name, Showing(outfits[pick].name, showing, false));
                    layer.Any(state).IfTrue(CassShuffle.Switch).Equal(CassShuffle.Pick, pick);
                }

                var robotState = layer.State("robot", Showing("robot", new string[0], true));
                foreach (var pick in robotPicks) layer.Any(robotState).IfTrue(CassShuffle.Switch).Equal(CassShuffle.Pick, pick);

                // The robot's face goes on working whether it shows or not.
                BotBuild.Hands(own, "Robot Face", robotFace);
                BotBuild.Blink(own, "Robot Blink", robotFace, staresWhileAway: false);
                var visemes = BotBuild.Visemes();
                var speech = own.Layer("Robot Visemes");
                for (var viseme = 0; viseme < visemes.Length; viseme++)
                {
                    var shape = visemes[viseme];
                    var state = speech.State(shape, own.Clip("robot " + shape, clip => clip.Blendshape(robotFace, shape, 100f)));
                    speech.Any(state).Equal("Viseme", viseme);
                }

                own.Save();
                FeaturePrefab.Merge(guests, own.Controller);

                FeaturePrefab.Ensure<WirenookReplaces>(root).features = new[] { CassShuffle.FeatureId };
                // The outfits are UV tiles, which no mobile shader can hide.
                FeaturePrefab.Describe(root, FeatureId, "Outfit shuffle, with guests", "outfit", "outfit shuffle", 50, pcOnly: true);
            });
        }

        /// <summary>
        /// A model nested under <paramref name="holder"/> whose bones become
        /// the avatar's bones of the same names (Modular Avatar's Merge
        /// Armature), wherever its own stood.
        /// </summary>
        private static GameObject Guest(GameObject holder, string modelPath)
        {
            var model = FeaturePrefab.Model(holder, modelPath);
            model.transform.localScale = Vector3.one;
            var armature = model.transform.Find("Armature")
                           ?? throw new InvalidOperationException(modelPath + " has no object named Armature under its root.");
            var merge = FeaturePrefab.Ensure<ModularAvatarMergeArmature>(armature.gameObject);
            merge.mergeTarget = new AvatarObjectReference { referencePath = "Armature" };
            merge.prefix = "";
            merge.suffix = "";
            merge.LockMode = ArmatureLockMode.NotLocked;
            merge.mangleNames = true;
            // One root bone, bounds and probe anchor for all of its meshes, so that the build may merge them.
            CassPrefabs.UnifyRenderers(model, CassSpec.Skeleton());
            return model;
        }

        /// <summary>A copy of a material, kept up with it, that rests with these tiles hidden.</summary>
        private static Material Hidden(Material source, string name, IEnumerable<Tile> tiles)
        {
            if (source == null) throw new FileNotFoundException("A material the shuffle's guests wear is missing; rebuild the avatars' materials first.");
            var copy = AssetFolders.LoadOrCreate(Generated + "/" + name + ".mat", () => new Material(source));
            copy.shader = source.shader;
            copy.CopyPropertiesFromMaterial(source);
            copy.renderQueue = source.renderQueue;
            copy.name = name;
            foreach (var tile in tiles) copy.SetFloat(ToonMaterial.TileProperty(tile.Column, tile.Row), 1f);
            EditorUtility.SetDirty(copy);
            return copy;
        }
    }
}
