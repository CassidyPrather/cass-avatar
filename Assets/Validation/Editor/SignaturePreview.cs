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
    /// Renders a built variant with its signature colour turned to several
    /// amounts (<see cref="WirenookSignature"/>), through the clip the build
    /// left in its FX controller: the same curves, on the same renderers,
    /// that the wearer's dial moves in game. Made for the platform builds
    /// are pretending to be, so a mobile build's stand-in shader can be
    /// looked at beside the PC one.
    /// </summary>
    public static class SignaturePreview
    {
        private static readonly float[] Amounts = { 0f, 0.17f, 0.33f, 0.5f, 0.67f, 0.83f };

        /// <returns>The folder the pictures were written to.</returns>
        public static string Render(string slug)
        {
            var platform = WirenookPlatform.Current;
            var folder = Path.Combine(ContactSheets.OutputFolder, "signature",
                platform == Platform.Pc ? slug : slug + "-" + WirenookPlatform.Name(platform));
            if (Directory.Exists(folder)) Directory.Delete(folder, true);

            var scene = ValidationScene.Open(out _);
            CassBuild.Measure(slug, out var built);
            try
            {
                UnityEngine.SceneManagement.SceneManager.MoveGameObjectToScene(built, scene);
                var fx = built.GetComponent<VRCAvatarDescriptor>().baseAnimationLayers
                    .First(layer => layer.type == VRCAvatarDescriptor.AnimLayerType.FX).animatorController;
                var turn = fx.animationClips.FirstOrDefault(clip => clip != null && clip.name.EndsWith("signature", System.StringComparison.Ordinal));
                if (turn == null) return slug + " has no signature colour: its build left no clip named \"signature\".";
                var bindings = AnimationUtility.GetCurveBindings(turn);
                if (bindings.Length == 0) return slug + ": the signature clip moves nothing; no material on the avatar follows it.";

                CassPreview.SkinEveryRender(built);
                var cameras = ValidationScene.Cameras(scene).ToDictionary(camera => camera.name);
                var index = 0;
                foreach (var amount in Amounts)
                {
                    var held = CassPreview.AllOff(CassPreview.Toggles(built));
                    foreach (var binding in bindings)
                        held[binding] = AnimationUtility.GetEditorCurve(turn, binding).Evaluate(amount * turn.length);
                    CassPreview.Sample(built, CassPreview.StandClip, 0f, held);
                    foreach (var camera in new[] { "Three-Quarter", "Upper Body" })
                    {
                        ContactSheets.Capture(cameras[camera],
                            Path.Combine(folder, "signature", index++.ToString("000") + " " + camera + " at " + amount.ToString("0.00") + ".png"));
                    }
                }

                var moved = string.Join(", ", bindings.Select(binding => binding.path + ":" + binding.propertyName).Distinct());
                ContactSheets.Compose(folder);
                return Path.GetFullPath(folder) + "\nmoves " + moved;
            }
            finally
            {
                Object.DestroyImmediate(built);
                AvatarProcessor.CleanTemporaryAssets();
            }
        }
    }
}
