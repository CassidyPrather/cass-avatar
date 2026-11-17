using System.IO;
using System.Linq;
using nadena.dev.ndmf;
using UnityEditor;
using UnityEngine;
using Wirenook.Cass.Editor;

namespace Wirenook.Validation.Editor
{
    /// <summary>
    /// Renders the nap (the pose the avatar holds while its wearer is away)
    /// on a built variant at several moments of its loop, from the front and
    /// the side. The pose was baked on the SDK's sample robot, so this is
    /// also the check that it suits this avatar's proportions.
    /// </summary>
    public static class NapPreview
    {
        private const string Controller = "Packages/net.wirenook.locomotion/Generated/Nap Action.controller";

        /// <returns>The folder the pictures were written to.</returns>
        public static string Render(string slug)
        {
            var folder = Path.Combine(ContactSheets.OutputFolder, "nap");
            if (Directory.Exists(folder)) Directory.Delete(folder, true);

            var nap = AssetDatabase.LoadAllAssetsAtPath(Controller).OfType<AnimationClip>().First(clip => clip.name == "nap");
            var scene = ValidationScene.Open(out _);
            CassBuild.Measure(slug, out var built);
            try
            {
                UnityEngine.SceneManagement.SceneManager.MoveGameObjectToScene(built, scene);
                CassPreview.SkinEveryRender(built);
                var held = CassPreview.AllOff(CassPreview.Toggles(built));
                var cameras = ValidationScene.Cameras(scene).ToDictionary(camera => camera.name);
                var index = 0;
                foreach (var phase in new[] { 0f, 0.45f, 0.86f, 0.95f })
                {
                    CassPreview.Sample(built, nap, phase * nap.length, held);
                    foreach (var camera in new[] { "Three-Quarter", "Left", "Upper Body" })
                    {
                        ContactSheets.Capture(cameras[camera],
                            Path.Combine(folder, "nap", index++.ToString("000") + " " + camera + " at " + phase.ToString("0.00") + ".png"));
                    }
                }
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
