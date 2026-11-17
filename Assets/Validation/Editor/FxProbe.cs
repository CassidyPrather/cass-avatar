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
