using System.IO;
using System.Linq;
using nadena.dev.ndmf;
using UnityEditor;
using UnityEngine;
using Wirenook.Cass.Editor;

namespace Wirenook.Validation.Editor
{
    /// <summary>
    /// Renders a built variant standing, with one more clip laid over the
    /// stand: a hand pose from the SDK's samples, say, to see how this
    /// avatar's fingers make it. The clip is given by its asset path.
    /// </summary>
    public static class PosePreview
    {
        /// <returns>The folder the pictures were written to.</returns>
        public static string Render(string slug, string clipPath)
        {
            var clip = AssetDatabase.LoadAssetAtPath<AnimationClip>(clipPath)
                       ?? throw new FileNotFoundException("No animation clip there.", clipPath);
            var folder = Path.Combine(ContactSheets.OutputFolder, "pose", slug + " " + clip.name);
            if (Directory.Exists(folder)) Directory.Delete(folder, true);

            var scene = ValidationScene.Open(out _);
            CassBuild.Measure(slug, out var built);
            try
            {
                UnityEngine.SceneManagement.SceneManager.MoveGameObjectToScene(built, scene);
                CassPreview.SkinEveryRender(built);
                var held = CassPreview.AllOff(CassPreview.Toggles(built));
                // The stand first, then the clip over it: a hand pose names the fingers only.
                var both = Object.Instantiate(CassPreview.StandClip);
                both.hideFlags = HideFlags.HideAndDontSave;
                foreach (var binding in AnimationUtility.GetCurveBindings(clip))
                    AnimationUtility.SetEditorCurve(both, binding, AnimationUtility.GetEditorCurve(clip, binding));
                CassPreview.Sample(built, both, 0f, held);
                Object.DestroyImmediate(both);

                var cameras = ValidationScene.Cameras(scene).ToDictionary(camera => camera.name);
                var index = 0;
                foreach (var camera in new[] { "Three-Quarter", "Upper Body", "Hand", "Right" })
                    ContactSheets.Capture(cameras[camera], Path.Combine(folder, "pose", index++.ToString("000") + " " + camera + ".png"));
            }
            finally
            {
                Object.DestroyImmediate(built);
                AvatarProcessor.CleanTemporaryAssets();
            }

            ContactSheets.Compose(folder);
            return Path.GetFullPath(folder);
        }
    }
}
