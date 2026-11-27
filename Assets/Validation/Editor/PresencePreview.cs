using System.Collections.Generic;
using System.IO;
using System.Linq;
using nadena.dev.ndmf;
using UnityEditor;
using UnityEngine;
using VRC.SDK3.Avatars.Components;
using Wirenook.Assets.Editor;
using Wirenook.Cass.Editor;

namespace Wirenook.Validation.Editor
{
    /// <summary>
    /// Renders a built variant as each kind of viewer's client draws it
    /// under presence (net.wirenook.adventure-tools): as it is, for whoever
    /// it is shown to; as a spectre in several signature colours, for those
    /// backstage and for its wearer; and not at all, for everyone else. The
    /// pictures go through the clips the build left in the FX controller:
    /// the same curves, on the same renderers, that a client plays. Made
    /// for the platform builds are pretending to be, so the mobile spectre
    /// (a swapped material) can be looked at beside the PC one (a property
    /// of the avatar's own shader).
    /// </summary>
    public static class PresencePreview
    {
        private static readonly float[] Hues = { 0f, 0.33f, 0.67f };

        /// <returns>The folder the pictures were written to, and what each clip moved.</returns>
        public static string Render(string slug)
        {
            var platform = WirenookPlatform.Current;
            var folder = Path.Combine(ContactSheets.OutputFolder, "presence",
                platform == Platform.Pc ? slug : slug + "-" + WirenookPlatform.Name(platform));
            if (Directory.Exists(folder)) Directory.Delete(folder, true);

            var scene = ValidationScene.Open(out _);
            CassBuild.Measure(slug, out var built);
            try
            {
                UnityEngine.SceneManagement.SceneManager.MoveGameObjectToScene(built, scene);
                var fx = built.GetComponent<VRCAvatarDescriptor>().baseAnimationLayers
                    .First(layer => layer.type == VRCAvatarDescriptor.AnimLayerType.FX).animatorController;
                var controller = (UnityEditor.Animations.AnimatorController)fx;
                AnimationClip Of(string layer, string state) => controller.layers
                    .Where(candidate => candidate.name == layer)
                    .SelectMany(candidate => candidate.stateMachine.states)
                    .Where(candidate => candidate.state.name == state)
                    .Select(candidate => candidate.state.motion as AnimationClip)
                    .FirstOrDefault();

                var drawn = Of("Unseen", "Drawn");
                var notDrawn = Of("Unseen", "Not drawn");
                var spectre = Of("Presence Spectral", "Spectre");
                var turn = Of("Signature", "Hue");
                if (notDrawn == null) return slug + " has no invisible switch: its build has no \"Unseen\" layer.";
                if (spectre == null) return slug + " does not carry presence: its build has no \"Presence Spectral\" layer.";

                var resting = built.GetComponentsInChildren<Renderer>(true).ToDictionary(renderer => renderer, renderer => renderer.sharedMaterials);
                CassPreview.SkinEveryRender(built);
                var cameras = ValidationScene.Cameras(scene).ToDictionary(camera => camera.name);
                var index = 0;

                void Picture(string label, AnimationClip body, AnimationClip look, float hue)
                {
                    foreach (var pair in resting) pair.Key.sharedMaterials = pair.Value;
                    var held = CassPreview.AllOff(CassPreview.Toggles(built));
                    foreach (var clip in new[] { turn, body, look }.Where(clip => clip != null))
                    {
                        foreach (var binding in AnimationUtility.GetCurveBindings(clip))
                        {
                            // The animator's own parameters are not the avatar's to show.
                            if (binding.type == typeof(Animator)) continue;
                            held[binding] = AnimationUtility.GetEditorCurve(clip, binding).Evaluate(hue * clip.length);
                        }
                    }

                    // A material swap is not a number; put the materials on by hand, as the animator would.
                    if (look != null)
                    {
                        foreach (var binding in AnimationUtility.GetObjectReferenceCurveBindings(look))
                        {
                            var target = built.transform.Find(binding.path);
                            var renderer = target != null ? target.GetComponent<Renderer>() : null;
                            var keys = AnimationUtility.GetObjectReferenceCurve(look, binding);
                            var start = binding.propertyName.IndexOf('[');
                            if (renderer == null || keys.Length == 0 || start < 0) continue;
                            var slot = int.Parse(binding.propertyName.Substring(start + 1).TrimEnd(']'));
                            var materials = renderer.sharedMaterials;
                            if (slot < materials.Length) materials[slot] = keys[0].value as Material;
                            renderer.sharedMaterials = materials;
                        }
                    }

                    CassPreview.Sample(built, CassPreview.StandClip, 0f, held);
                    foreach (var camera in new[] { "Three-Quarter", "Upper Body" })
                        ContactSheets.Capture(cameras[camera], Path.Combine(folder, "presence", index++.ToString("000") + " " + camera + ", " + label + ".png"));
                }

                Picture("shown to you", drawn, null, 0f);
                foreach (var hue in Hues) Picture("a spectre, colour " + hue.ToString("0.00"), drawn, spectre, hue);
                Picture("not shown to you", notDrawn, null, 0f);

                string Moves(AnimationClip clip) => clip == null
                    ? "(none)"
                    : string.Join(", ", AnimationUtility.GetCurveBindings(clip).Select(binding => binding.path + ":" + binding.propertyName)
                        .Concat(AnimationUtility.GetObjectReferenceCurveBindings(clip).Select(binding => binding.path + ":" + binding.propertyName + " (material)"))
                        .Distinct());
                ContactSheets.Compose(folder);
                return Path.GetFullPath(folder) + "\nnot drawn moves " + Moves(notDrawn) + "\nthe spectre moves " + Moves(spectre);
            }
            finally
            {
                Object.DestroyImmediate(built);
                AvatarProcessor.CleanTemporaryAssets();
            }
        }
    }
}
