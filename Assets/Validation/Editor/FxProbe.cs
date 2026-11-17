using System.Linq;
using System.Text;
using nadena.dev.ndmf;
using UnityEditor;
using UnityEngine;
using VRC.SDK3.Avatars.Components;
using Wirenook.Cass.Editor;

namespace Wirenook.Validation.Editor
{
    /// <summary>
    /// Reads back what a build left in an avatar's FX controller: its layers,
    /// and what the clips whose names match a fragment animate. For checking
    /// that a feature's animation arrived, and arrived pointing at objects
    /// that exist, without a picture.
    /// </summary>
    public static class FxProbe
    {
        /// <returns>The built variant's FX layers, in order, with their states.</returns>
        public static string Layers(string slug)
        {
            return Probe(slug, (built, fx, text) =>
            {
                for (var i = 0; i < fx.layers.Length; i++)
                {
                    var layer = fx.layers[i];
                    text.AppendLine(i + " " + layer.name + ": " +
                                    string.Join(", ", layer.stateMachine.states.Select(state => state.state.name)));
                }
            });
        }

        /// <returns>
        /// Every curve of every clip whose name contains <paramref name="fragment"/>:
        /// its path, property, first value, and whether the path leads to an
        /// object in the built avatar.
        /// </returns>
        public static string Clips(string slug, string fragment)
        {
            return Probe(slug, (built, fx, text) =>
            {
                foreach (var clip in fx.animationClips.Where(clip => clip != null && clip.name.Contains(fragment)).Distinct())
                {
                    text.AppendLine(clip.name + " (" + clip.length.ToString("0.###") + " s)");
                    foreach (var binding in AnimationUtility.GetCurveBindings(clip))
                    {
                        var found = binding.type == typeof(Animator) || built.transform.Find(binding.path) != null;
                        text.AppendLine("  " + (found ? "" : "MISSING ") + binding.path + " : " + binding.type.Name + "." +
                                        binding.propertyName + " = " +
                                        AnimationUtility.GetEditorCurve(clip, binding).Evaluate(0f).ToString("0.####"));
                    }
                }
            });
        }

        /// <returns>Every object in the built variant whose name contains <paramref name="fragment"/>, with its scale and components.</returns>
        public static string Objects(string slug, string fragment)
        {
            return Probe(slug, (built, fx, text) =>
            {
                foreach (var found in built.GetComponentsInChildren<Transform>(true).Where(candidate => candidate.name.Contains(fragment)))
                {
                    text.AppendLine(AnimationUtility.CalculateTransformPath(found, built.transform) + "  scale " + found.localScale +
                                    (found.gameObject.activeSelf ? "" : "  (inactive)") + "  [" +
                                    string.Join(", ", found.GetComponents<Component>().Select(component => component.GetType().Name)) + "]");
                }
            });
        }

        /// <summary>
        /// Builds a variant with one more feature prefab placed on it, for
        /// trying a feature before any variant carries it.
        /// </summary>
        /// <returns>The build's rank and counts, and the FX layers and clip curves whose names contain <paramref name="fragment"/>.</returns>
        public static string Try(string slug, string featurePrefabPath, string fragment)
        {
            var built = Object.Instantiate(CassBuild.LoadVariant(slug));
            built.name = slug;
            try
            {
                var feature = AssetDatabase.LoadAssetAtPath<GameObject>(featurePrefabPath);
                if (feature == null) throw new System.IO.FileNotFoundException("No such prefab.", featurePrefabPath);
                // A plain copy: the build does not take prefab instances.
                Object.Instantiate(feature, built.transform).name = feature.name;
                AvatarProcessor.ProcessAvatar(built);

                var stats = new VRC.SDKBase.Validation.Performance.Stats.AvatarPerformanceStats(false);
                VRC.SDKBase.Validation.Performance.AvatarPerformance.CalculatePerformanceStats(slug, built, stats,
                    Wirenook.Assets.Editor.WirenookPlatform.IsMobile);
                var text = new StringBuilder();
                text.AppendLine(stats.GetPerformanceRatingForCategory(VRC.SDKBase.Validation.Performance.AvatarPerformanceCategory.Overall) +
                                ", " + stats.polyCount + " triangles, " + stats.skinnedMeshCount + " skinned + " + stats.meshCount +
                                " static meshes, " + stats.materialCount + " material slots, " + stats.boneCount + " bones, " +
                                stats.constraintsCount + " constraints, " + stats.contactCount + " contacts, " +
                                built.GetComponent<VRCAvatarDescriptor>().expressionParameters.CalcTotalCost() + " synced bits");

                var fx = built.GetComponent<VRCAvatarDescriptor>().baseAnimationLayers
                    .First(layer => layer.type == VRCAvatarDescriptor.AnimLayerType.FX)
                    .animatorController as UnityEditor.Animations.AnimatorController;
                foreach (var layer in fx.layers.Where(layer => layer.name.Contains(fragment)))
                    text.AppendLine("layer " + layer.name + ": " + string.Join(", ", layer.stateMachine.states.Select(state => state.state.name)));
                foreach (var clip in fx.animationClips.Where(clip => clip != null && clip.name.Contains(fragment)).Distinct())
                {
                    var bindings = AnimationUtility.GetCurveBindings(clip);
                    var missing = bindings.Count(binding => binding.type != typeof(Animator) && built.transform.Find(binding.path) == null);
                    text.AppendLine("clip " + clip.name + ": " + bindings.Length + " curves, " + missing + " to missing objects");
                }

                return text.ToString();
            }
            finally
            {
                Object.DestroyImmediate(built);
                AvatarProcessor.CleanTemporaryAssets();
            }
        }

        /// <summary>
        /// Builds a variant with one more feature prefab on it and lists one
        /// of its playable layers ("Action", "FX", ...): each animator layer
        /// with its weight and states, and where each layer-weight control in
        /// it points after the build has renumbered the layers.
        /// </summary>
        public static string TryPlayable(string slug, string featurePrefabPath, string playable)
        {
            var built = Object.Instantiate(CassBuild.LoadVariant(slug));
            built.name = slug;
            try
            {
                if (!string.IsNullOrEmpty(featurePrefabPath))
                {
                    var feature = AssetDatabase.LoadAssetAtPath<GameObject>(featurePrefabPath);
                    if (feature == null) throw new System.IO.FileNotFoundException("No such prefab.", featurePrefabPath);
                    Object.Instantiate(feature, built.transform).name = feature.name;
                }

                AvatarProcessor.ProcessAvatar(built);
                var type = (VRCAvatarDescriptor.AnimLayerType)System.Enum.Parse(typeof(VRCAvatarDescriptor.AnimLayerType), playable);
                var slot = built.GetComponent<VRCAvatarDescriptor>().baseAnimationLayers.First(layer => layer.type == type);
                var controller = slot.animatorController as UnityEditor.Animations.AnimatorController;
                var text = new StringBuilder();
                text.AppendLine(playable + ": " + (slot.isDefault ? "VRChat's default" : controller != null ? controller.name : "none"));
                if (controller == null) return text.ToString();
                for (var i = 0; i < controller.layers.Length; i++)
                {
                    var layer = controller.layers[i];
                    text.AppendLine(i + " " + layer.name + " (weight " + layer.defaultWeight + "): " +
                                    string.Join(", ", layer.stateMachine.states.Select(state => state.state.name)));
                    foreach (var state in layer.stateMachine.states)
                    {
                        foreach (var fade in state.state.behaviours.OfType<VRCAnimatorLayerControl>())
                        {
                            var target = fade.layer >= 0 && fade.layer < controller.layers.Length ? controller.layers[fade.layer].name : "NOTHING";
                            text.AppendLine("    " + state.state.name + " sets " + fade.playable + " layer " + fade.layer + " (" + target +
                                            ") to " + fade.goalWeight + " over " + fade.blendDuration + " s");
                        }
                    }
                }

                return text.ToString();
            }
            finally
            {
                Object.DestroyImmediate(built);
                AvatarProcessor.CleanTemporaryAssets();
            }
        }

        private static string Probe(string slug, System.Action<GameObject, UnityEditor.Animations.AnimatorController, StringBuilder> read)
        {
            CassBuild.Measure(slug, out var built);
            try
            {
                var fx = built.GetComponent<VRCAvatarDescriptor>().baseAnimationLayers
                    .First(layer => layer.type == VRCAvatarDescriptor.AnimLayerType.FX)
                    .animatorController as UnityEditor.Animations.AnimatorController;
                var text = new StringBuilder();
                read(built, fx, text);
                return text.ToString();
            }
            finally
            {
                Object.DestroyImmediate(built);
                AvatarProcessor.CleanTemporaryAssets();
            }
        }
    }
}
