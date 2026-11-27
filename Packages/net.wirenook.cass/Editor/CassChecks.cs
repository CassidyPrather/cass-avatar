using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
using nadena.dev.modular_avatar.core;
using nadena.dev.ndmf;
using UnityEditor.Animations;
using UnityEngine;
using VRC.SDK3.Avatars.Components;
using VRC.SDK3A.Editor;
using VRC.SDKBase.Validation.Performance;
using Wirenook.Assets.Core;
using Wirenook.Assets.Editor;

namespace Wirenook.Cass.Editor
{
    /// <summary>
    /// Checks a variant the way it would be uploaded: after the build-time
    /// tools have merged, optimised and rewritten it. Several of the avatar's
    /// promises (the MMD mesh name and layer order, the blendshapes trackers
    /// need, the performance rank) are only true or false of that result, so
    /// they cannot be checked on the prefab alone.
    /// </summary>
    public static class CassChecks
    {
        /// <summary>The most synced parameter bits VRChat accepts on an avatar.</summary>
        private const int ParameterBudget = 256;

        /// <summary>Stations VRChat keeps working on one avatar.</summary>
        private const int StationBudget = 6;

        /// <returns>A report ending in "ok" or listing every failed check.</returns>
        public static string Verify(string slug)
        {
            var problems = new List<string>();
            var notes = new List<string>();
            var platform = WirenookPlatform.Current;
            var variant = CassSpec.Variants().Variants.First(candidate => candidate.Slug == slug);
            if (!variant.Platforms.Contains(platform))
                return slug + " (" + WirenookPlatform.Name(platform) + "): not built for this platform" + System.Environment.NewLine + "ok";
            // Not a failure of this checkout: the variant is for whoever holds the asset.
            var absent = variant.Absent();
            if (absent.Count > 0)
                return slug + ": not checked. " + CassPrefabs.Unavailable(variant, absent) + System.Environment.NewLine + "ok";

            WrittenControllers(slug, problems);
            var report = CassBuild.Measure(slug, out var built);
            try
            {
                Policy(slug, report, problems, notes);
                var sharing = CassPrefabs.SharesBlueprintWith(slug);
                if (sharing != null)
                    problems.Add("It holds the same avatar id as " + sharing + ", so uploading one would replace the other. " +
                                 "Run a rebuild, which clears ids a variant inherited from the one it extends.");
                Rank(slug, report, problems);
                // What cass's own model has to keep. Another avatar's root says
                // what its model needs when it is generated.
                if (OnCass(variant))
                {
                    MmdContract(built, problems);
                    Blendshapes(built, problems);
                }
                else if (HasFace(slug) && built.transform.Find(CassSpec.Blendshapes().Mesh)?.GetComponent<SkinnedMeshRenderer>() == null)
                {
                    problems.Add("After the build there is no skinned mesh named " + CassSpec.Blendshapes().Mesh + " directly under the avatar root.");
                }

                Away(variant, built, problems);
                Unseen(built, problems);
                Presence(built, problems);
                Budgets(built, report, problems);
                Brightness(built, problems);
                RestPose(built, problems);
                if (platform != Platform.Pc)
                {
                    MobileShaders(built, problems);
                    SameParametersAsPc(slug, built, problems);
                }

                SdkValidation(built, problems, notes);
            }
            finally
            {
                UnityEngine.Object.DestroyImmediate(built);
                AvatarProcessor.CleanTemporaryAssets();
            }

            var summary = slug + " (" + report.platform + "): " + report.performanceRank + ", " + report.triangles + " triangles, " +
                          report.skinnedMeshes + " skinned + " + report.meshes + " static meshes, " +
                          report.materialSlots + " material slots, " + report.bones + " bones, " +
                          report.syncedParameterBits + " synced bits\n";
            foreach (var note in notes) summary += "  note: " + note + "\n";
            if (problems.Count == 0) return summary + "ok";
            return summary + "FAILED\n  " + string.Join("\n  ", problems);
        }

        /// <summary>
        /// Every avatar shows its wearer is away in exactly one way, the one
        /// its variant names for this platform, and has the "AFK" switch in
        /// its menu once. The flavours are told apart by a layer each is
        /// known to bring; vanishing also needs the vanishing act it works.
        /// </summary>
        private static void Away(Variant variant, GameObject built, List<string> problems)
        {
            var descriptor = built.GetComponent<VRCAvatarDescriptor>();
            List<string> Layers(VRCAvatarDescriptor.AnimLayerType type) =>
                (descriptor.baseAnimationLayers.FirstOrDefault(layer => layer.type == type).animatorController as AnimatorController)
                ?.layers.Select(layer => layer.name).ToList() ?? new List<string>();
            var fx = Layers(VRCAvatarDescriptor.AnimLayerType.FX);
            var action = Layers(VRCAvatarDescriptor.AnimLayerType.Action);

            var found = new List<string>();
            if (action.Contains("Nap")) found.Add(WirenookAway.Nap);
            if (fx.Contains("Away") && action.Contains("Away")) found.Add(WirenookAway.Crash);
            if (fx.Contains("Away Vanish")) found.Add(WirenookAway.Vanish);

            var wanted = variant.AfkFor(WirenookPlatform.Current);
            if (wanted == null)
                problems.Add("The variant does not say how it shows its wearer is away: give it, or the variant it extends, an \"afk\" in variants.json.");
            else if (found.Count != 1 || found[0] != wanted)
                problems.Add("It should show its wearer is away by the " + wanted + " and nothing else; the build has " +
                             (found.Count == 0 ? "no away feature" : string.Join(" and ", found)) + ".");
            if (wanted == WirenookAway.Vanish && !fx.Contains("Vanish Body"))
                problems.Add("It vanishes while away, which is the vanishing act of net.wirenook.party-tricks worked for it, and the build has no vanishing act.");

            var switches = 0;
            void Count(VRC.SDK3.Avatars.ScriptableObjects.VRCExpressionsMenu menu, HashSet<UnityEngine.Object> seen)
            {
                if (menu == null || !seen.Add(menu)) return;
                foreach (var control in menu.controls)
                {
                    if (control.parameter != null && control.parameter.name == WirenookSignals.Away) switches++;
                    Count(control.subMenu, seen);
                }
            }

            Count(descriptor.expressionsMenu, new HashSet<UnityEngine.Object>());
            if (switches != 1)
                problems.Add("The menu has " + switches + " switches for " + WirenookSignals.Away + "; every avatar has the one \"AFK\" switch.");
            else if (!descriptor.expressionsMenu.controls.Any(control => control.parameter != null && control.parameter.name == WirenookSignals.Away))
                problems.Add("The \"AFK\" switch is not in the top level of the menu.");
        }

        /// <summary>The layer of the invisible switch (net.wirenook.adventure-tools, PresenceBuild.UnseenLayer).</summary>
        private const string UnseenLayer = "Unseen";

        private static AnimatorController Fx(GameObject built)
        {
            return built.GetComponent<VRCAvatarDescriptor>().baseAnimationLayers
                .FirstOrDefault(layer => layer.type == VRCAvatarDescriptor.AnimLayerType.FX).animatorController as AnimatorController;
        }

        private static int Switches(VRC.SDK3.Avatars.ScriptableObjects.VRCExpressionsMenu menu, string parameter, HashSet<UnityEngine.Object> seen)
        {
            if (menu == null || !seen.Add(menu)) return 0;
            return menu.controls.Sum(control =>
                (control.parameter != null && control.parameter.name == parameter ? 1 : 0) + Switches(control.subMenu, parameter, seen));
        }

        /// <summary>
        /// Every avatar has the invisible switch, once, and its one layer
        /// reaches every renderer the build left: a renderer it missed
        /// would go on being drawn for people the wearer is hidden from.
        /// </summary>
        private static void Unseen(GameObject built, List<string> problems)
        {
            const string layerName = UnseenLayer;
            var layer = Fx(built)?.layers.FirstOrDefault(candidate => candidate.name == layerName);
            if (layer == null)
            {
                problems.Add("Every avatar carries the invisible switch (net.wirenook.adventure-tools; a rebuild places it), and the build has no \"" + layerName + "\" layer.");
                return;
            }

            var renderers = built.GetComponentsInChildren<Renderer>(true)
                .Select(renderer => UnityEditor.AnimationUtility.CalculateTransformPath(renderer.transform, built.transform))
                .Distinct()
                .ToList();
            foreach (var state in layer.stateMachine.states)
            {
                var clip = state.state.motion as AnimationClip;
                var reached = clip == null
                    ? new HashSet<string>()
                    : new HashSet<string>(UnityEditor.AnimationUtility.GetCurveBindings(clip)
                        // The optimiser merges meshes that are switched alike and
                        // then switches the merged one by its object.
                        .Where(binding => binding.propertyName == "m_Enabled" && typeof(Renderer).IsAssignableFrom(binding.type) ||
                                          binding.propertyName == "m_IsActive" && binding.type == typeof(GameObject))
                        .Select(binding => binding.path));
                var missed = renderers.Where(path => !reached.Contains(path)).ToList();
                if (missed.Count > 0)
                    problems.Add("The invisible switch's \"" + state.state.name + "\" does not reach " + missed.Count + " of " + renderers.Count +
                                 " renderers: " + string.Join(", ", missed.Take(4)) + (missed.Count > 4 ? ", ..." : ""));
            }

            var switches = Switches(built.GetComponent<VRCAvatarDescriptor>().expressionsMenu, WirenookSignals.Unseen, new HashSet<UnityEngine.Object>());
            if (switches != 1)
                problems.Add("The menu has " + switches + " switches for " + WirenookSignals.Unseen + "; every avatar has the one \"Invisible\" switch.");
        }

        /// <summary>
        /// Where a variant carries presence (who sees and who hears the
        /// wearer, net.wirenook.adventure-tools): the build has pointed the
        /// mover of the head at the humanoid head bone, nothing hangs under
        /// that bone to be carried off with it, and on Android and iOS no
        /// animation swaps in a material VRChat would refuse there.
        /// </summary>
        private static void Presence(GameObject built, List<string> problems)
        {
            var fx = Fx(built);
            if (fx == null || fx.layers.All(layer => layer.name != "Presence Heard")) return;

            var animator = built.GetComponent<Animator>();
            var head = animator != null && animator.isHuman ? animator.GetBoneTransform(HumanBodyBones.Head) : null;
            var movers = built.GetComponentsInChildren<VRC.SDK3.Dynamics.Constraint.Components.VRCPositionConstraint>(true)
                .Where(constraint => head != null && constraint.TargetTransform == head)
                .ToList();
            if (movers.Count != 1)
                problems.Add("It carries presence, and " + movers.Count + " constraints move its head bone; \"heard by\" needs the one. " +
                             "(On a rig whose head bone carries the head, the build leaves the mover out.)");
            else if (movers[0].IsActive)
                problems.Add("Its head bone is moved as it rests; a client that plays no animations would not hear the wearer.");
            if (head != null && head.childCount > 0)
                problems.Add("Its head bone is moved for people who are not to hear the wearer, and " + head.childCount +
                             " objects hang under it and would go with it: " +
                             string.Join(", ", head.Cast<Transform>().Take(4).Select(child => child.name)));

            if (!WirenookPlatform.IsMobile) return;
            var foreign = fx.animationClips
                .SelectMany(clip => UnityEditor.AnimationUtility.GetObjectReferenceCurveBindings(clip)
                    .SelectMany(binding => UnityEditor.AnimationUtility.GetObjectReferenceCurve(clip, binding)))
                .Select(key => key.value as Material)
                .Where(material => material != null && !material.shader.name.StartsWith("VRChat/Mobile/", StringComparison.Ordinal))
                .Select(material => material.name + " (" + material.shader.name + ")")
                .Distinct()
                .ToList();
            if (foreign.Count > 0)
                problems.Add("Animations swap in materials with shaders mobile builds may not use: " + string.Join(", ", foreign));
        }

        /// <summary>
        /// Whether another avatar's variant has a face to keep: a mesh of
        /// the face's name directly under its root with shape keys on it,
        /// as the robot has. Visemes and MMD worlds find such a mesh by that
        /// name, so it has to come through the build under it. A mesh
        /// without shape keys (the meta figure's one mesh) answers to
        /// nothing by name, and the optimiser is free to merge it away.
        /// </summary>
        private static bool HasFace(string slug)
        {
            var face = CassBuild.LoadVariant(slug).transform.Find(CassSpec.Blendshapes().Mesh)?.GetComponent<SkinnedMeshRenderer>();
            return face != null && face.sharedMesh != null && face.sharedMesh.blendShapeCount > 0;
        }

        /// <summary>Whether a variant stands on cass's own root, directly or through the variants it extends.</summary>
        private static bool OnCass(Variant variant)
        {
            var all = CassSpec.Variants().Variants;
            while (variant.Extends != null) variant = all.First(candidate => candidate.Slug == variant.Extends);
            return variant.Root == null;
        }

        private static void Policy(string slug, BuildReport report, List<string> problems, List<string> notes)
        {
            var prefab = CassBuild.LoadVariant(slug);
            var profile = prefab.GetComponent<AvatarUploadProfile>();
            if (profile == null)
            {
                problems.Add("The variant has no Avatar Upload Profile.");
                return;
            }

            var policy = profile.Policy();
            problems.AddRange(Core.UploadGuard.Check(
                policy, profile.avatarName, profile.ComposeDescription(), report.apiTags, policy.ReleaseStatus));
            if (policy.ReleaseStatus != "public")
                notes.Add("uploads " + policy.ReleaseStatus + ": " + (profile.carries.Count > 0
                    ? "it carries " + string.Join("; ", profile.carries)
                    : "it is marked unreleased in Spec/variants.json"));
            foreach (var tag in report.droppedTags)
                notes.Add("tag " + tag + " does not fit in VRChat's " + FeatureTags.Limit + " tags and is left out");
        }

        private static void Rank(string slug, BuildReport report, List<string> problems)
        {
            var target = CassSpec.Variants().Variants.First(variant => variant.Slug == slug).WorstRankFor(WirenookPlatform.Current);
            if (!Enum.TryParse<PerformanceRating>(report.performanceRank, out var actual) ||
                !Enum.TryParse<PerformanceRating>(target, out var worst))
            {
                problems.Add("Could not read the performance rank (" + report.performanceRank + ") or the target (" + target + ").");
                return;
            }

            if (actual <= worst) return;
            problems.Add("Ranks " + actual + " on " + WirenookPlatform.Name(WirenookPlatform.Current) +
                         ", but this variant must be " + worst + " or better there. Worse than Excellent: " +
                         string.Join(", ", report.belowExcellent.Select(pair => pair.Key + " " + pair.Value)));
        }

        /// <summary>
        /// MMD worlds drive the face by animating a mesh called Body directly
        /// under the avatar root, and silence FX layers 1 and 2 while they do.
        /// </summary>
        private static void MmdContract(GameObject built, List<string> problems)
        {
            var shapes = CassSpec.Blendshapes();
            var body = built.transform.Find(shapes.Mesh);
            if (body == null || body.GetComponent<SkinnedMeshRenderer>() == null)
            {
                problems.Add("After the build there is no skinned mesh named " + shapes.Mesh + " directly under the avatar root.");
                return;
            }

            var descriptor = built.GetComponent<VRCAvatarDescriptor>();
            var fx = descriptor.baseAnimationLayers
                .FirstOrDefault(layer => layer.type == VRCAvatarDescriptor.AnimLayerType.FX)
                .animatorController as AnimatorController;
            if (fx == null)
            {
                problems.Add("The built avatar has no FX controller.");
                return;
            }

            var names = fx.layers.Select(layer => layer.name).ToList();
            if (names.Count < 3 || !names[1].Contains("Left Hand") || !names[2].Contains("Right Hand"))
            {
                problems.Add("FX layers 1 and 2 must be the hand gesture layers for MMD worlds; the build produced: " +
                             string.Join(", ", names.Take(4)));
            }
        }

        /// <summary>
        /// A feature may merge a controller that is generated but not
        /// committed: the walk-style sampler's are too large to keep. Until
        /// they are written the feature merges nothing, the build succeeds
        /// without it, and nothing in the result says so. This is checked on
        /// the prefab, since the build removes the components that would tell.
        /// </summary>
        private static void WrittenControllers(string slug, List<string> problems)
        {
            foreach (var merge in CassBuild.LoadVariant(slug).GetComponentsInChildren<ModularAvatarMergeAnimator>(true))
            {
                if (merge.animator != null) continue;
                problems.Add("\"" + merge.gameObject.name + "\" merges a " + merge.layerType + " controller that does not exist, so it would " +
                             "install nothing. If it is the walk-style sampler, write its controllers with scripts/cass.sh gaits styles.");
            }
        }

        /// <summary>Optimisers drop blendshapes they believe nothing drives; these must survive.</summary>
        private static void Blendshapes(GameObject built, List<string> problems)
        {
            var shapes = CassSpec.Blendshapes();
            var body = built.transform.Find(shapes.Mesh);
            var mesh = body != null ? body.GetComponent<SkinnedMeshRenderer>()?.sharedMesh : null;
            if (mesh == null) return;

            void Require(string kind, IEnumerable<string> names)
            {
                var missing = names.Where(name => mesh.GetBlendShapeIndex(name) < 0).ToList();
                if (missing.Count > 0)
                    problems.Add(missing.Count + " " + kind + " blendshape(s) did not survive the build: " + string.Join(", ", missing.Take(8)) +
                                 (missing.Count > 8 ? ", ..." : ""));
            }

            Require("viseme", shapes.Visemes);
            Require("face-tracking", shapes.Tracking.Where(key => key.Core).Select(key => key.Key));
            Require("MMD", shapes.Mmd.Keys);
        }

        private static void Budgets(GameObject built, BuildReport report, List<string> problems)
        {
            if (report.syncedParameterBits > ParameterBudget)
                problems.Add("Uses " + report.syncedParameterBits + " synced parameter bits; VRChat allows " + ParameterBudget + ".");

            var stations = built.GetComponentsInChildren<VRCStation>(true).Length;
            if (stations > StationBudget)
                problems.Add("Has " + stations + " stations; VRChat disables all but " + StationBudget + ".");

            if (WirenookPlatform.Current == Platform.Pc) return;

            // Past any one of these, VRChat removes every component of the
            // limited kinds from a mobile avatar, whatever the viewer has
            // chosen to show. Rank is a preference; these are not.
            void Limit(string what, int count, int most)
            {
                if (count > most)
                    problems.Add("Has " + count + " " + what + "; past " + most + " VRChat strips all dynamics from a mobile avatar.");
            }

            Limit("PhysBone components", built.GetComponentsInChildren<VRC.Dynamics.VRCPhysBoneBase>(true).Length, 8);
            Limit("PhysBone colliders", built.GetComponentsInChildren<VRC.Dynamics.VRCPhysBoneColliderBase>(true).Length, 16);
            Limit("contacts", built.GetComponentsInChildren<VRC.Dynamics.ContactBase>(true).Length, 16);
            Limit("constraints", built.GetComponentsInChildren<VRC.Dynamics.VRCConstraintBase>(true).Length, 150);
        }

        /// <summary>VRChat refuses an Android or iOS avatar that uses any shader but its own mobile ones.</summary>
        private static void MobileShaders(GameObject built, List<string> problems)
        {
            var foreign = built.GetComponentsInChildren<Renderer>(true)
                .SelectMany(renderer => renderer.sharedMaterials)
                .Where(material => material != null && !material.shader.name.StartsWith("VRChat/Mobile/", StringComparison.Ordinal))
                .Select(material => material.name + " (" + material.shader.name + ")")
                .Distinct()
                .ToList();
            if (foreign.Count > 0)
                problems.Add("Materials with shaders mobile builds may not use: " + string.Join(", ", foreign));
        }

        /// <summary>
        /// VRChat syncs expression parameters by their position in the list.
        /// If the mobile build's list differs from the PC build's, people on
        /// one platform see the other's toggles land on the wrong things.
        /// </summary>
        private static void SameParametersAsPc(string slug, GameObject built, List<string> problems)
        {
            var here = WirenookPlatform.Name(WirenookPlatform.Current);
            var mobile = Parameters(built);
            List<string> pc;
            WirenookPlatform.Pretend("pc");
            try
            {
                CassBuild.Measure(slug, out var pcBuilt);
                pc = Parameters(pcBuilt);
                UnityEngine.Object.DestroyImmediate(pcBuilt);
            }
            finally
            {
                WirenookPlatform.Pretend(here);
            }

            if (pc.SequenceEqual(mobile)) return;
            var first = Enumerable.Range(0, Math.Max(pc.Count, mobile.Count))
                .First(index => index >= pc.Count || index >= mobile.Count || pc[index] != mobile[index]);
            problems.Add("The expression parameters differ from the PC build's, so they would sync wrongly across platforms. " +
                         "First difference at position " + first + ": PC has " + (first < pc.Count ? pc[first] : "nothing") +
                         ", this build has " + (first < mobile.Count ? mobile[first] : "nothing") + ".");
        }

        private static List<string> Parameters(GameObject built)
        {
            var asset = built.GetComponent<VRCAvatarDescriptor>().expressionParameters;
            return asset == null
                ? new List<string>()
                : asset.parameters.Select(parameter => parameter.name + ":" + parameter.valueType + (parameter.networkSynced ? ":synced" : "")).ToList();
        }

        /// <summary>
        /// Whatever the FX layers scale or switch must rest the way their
        /// default states hold it. A viewer whose safety settings block the
        /// avatar's animations sees it as it rests, so a prop that rests at
        /// full size and relies on the animator to hide it shows for them
        /// permanently.
        /// </summary>
        private static void RestPose(GameObject built, List<string> problems)
        {
            var fx = built.GetComponent<VRCAvatarDescriptor>().baseAnimationLayers
                .FirstOrDefault(layer => layer.type == VRCAvatarDescriptor.AnimLayerType.FX)
                .animatorController as AnimatorController;
            if (fx == null) return;

            var showing = new List<string>();
            foreach (var layer in fx.layers)
            {
                // The invisible switch starts every avatar undrawn for a
                // moment, on purpose, and then draws it: one that loads
                // hidden from someone must not be shown to them on the way.
                // As it rests, an avatar is drawn (or is not, where it says
                // so itself), which is the right thing for a viewer who
                // plays no animations.
                if (layer.name == UnseenLayer) continue;
                var state = layer.stateMachine != null ? layer.stateMachine.defaultState : null;
                if (state == null || !(state.motion is AnimationClip clip)) continue;

                foreach (var binding in UnityEditor.AnimationUtility.GetCurveBindings(clip))
                {
                    var target = built.transform.Find(binding.path);
                    if (target == null) continue;

                    float rest;
                    if (binding.type == typeof(GameObject) && binding.propertyName == "m_IsActive")
                        rest = target.gameObject.activeSelf ? 1f : 0f;
                    else if (binding.type == typeof(Transform) && binding.propertyName == "m_LocalScale.x")
                        rest = target.localScale.x;
                    else if (binding.type == typeof(Transform) && binding.propertyName == "m_LocalScale.y")
                        rest = target.localScale.y;
                    else if (binding.type == typeof(Transform) && binding.propertyName == "m_LocalScale.z")
                        rest = target.localScale.z;
                    else
                        continue;

                    var starts = UnityEditor.AnimationUtility.GetEditorCurve(clip, binding).Evaluate(0f);
                    if (!Mathf.Approximately(rest, starts)) showing.Add(target.name + " (layer " + layer.name + ")");
                }
            }

            if (showing.Count > 0)
                problems.Add("These rest differently from how their animator starts them, so they look wrong " +
                             "to anyone who has the avatar's animations blocked: " + string.Join(", ", showing.Distinct()));
        }

        /// <summary>
        /// Runs the checks the SDK panel runs on the built avatar before it
        /// will upload one. Anything it lists as an error stops an upload
        /// after the build, with the avatar id already reserved, so it is
        /// worth hearing about here first. The SDK offers no public way to
        /// ask, hence the reflection; if a later SDK moves these members the
        /// check reports that it was skipped instead of failing.
        /// </summary>
        private static void SdkValidation(GameObject built, List<string> problems, List<string> notes)
        {
            const string skipped = "The VRChat SDK's own upload validation was skipped: ";
            if (!VRCSdkControlPanel.TryGetBuilder<IVRCSdkAvatarBuilderApi>(out var api))
            {
                notes.Add(skipped + "its control panel is not open.");
                return;
            }

            const BindingFlags hidden = BindingFlags.Instance | BindingFlags.NonPublic | BindingFlags.DeclaredOnly;
            FieldInfo panelField = null;
            MethodInfo check = null;
            for (var type = api.GetType(); type != null; type = type.BaseType)
            {
                panelField ??= type.GetField("_builder", hidden);
                check ??= type.GetMethod("OnGUIAvatarCheck", hidden);
            }

            var descriptor = built.GetComponent<VRCAvatarDescriptor>();
            if (!(panelField?.GetValue(api) is VRCSdkControlPanel panel) || check == null || descriptor == null)
            {
                notes.Add(skipped + "this SDK version keeps it somewhere this check does not know.");
                return;
            }

            panel.ResetIssues();
            try
            {
                check.Invoke(api, new object[] { descriptor });
                foreach (var issue in panel.GetGuiErrorsOrIssuesForItem(descriptor))
                    problems.Add("VRChat SDK: " + issue.issueText.Replace('\n', ' '));
            }
            finally
            {
                // The panel lists issues for whatever is selected in it; leave
                // it to collect its own again.
                panel.ResetIssues();
            }
        }

        /// <summary>No lit material may keep a brightness floor: in the dark the avatar should be dark.</summary>
        private static void Brightness(GameObject built, List<string> problems)
        {
            var floored = built.GetComponentsInChildren<Renderer>(true)
                .SelectMany(renderer => renderer.sharedMaterials)
                .Where(material => material != null && material.HasProperty("_LightMinLimit") &&
                                   material.GetFloat("_LightMinLimit") > 0f &&
                                   // Unlit materials ignore the limit; they are meant to glow.
                                   !(material.HasProperty("_AsUnlit") && material.GetFloat("_AsUnlit") >= 1f))
                .Select(material => material.name)
                .Distinct()
                .ToList();
            if (floored.Count > 0)
                problems.Add("Materials with a minimum brightness above zero: " + string.Join(", ", floored));
        }
    }
}
