using System.IO;
using System.Linq;
using nadena.dev.ndmf;
using UnityEditor;
using UnityEngine;
using Wirenook.Assets.Editor;
using Wirenook.Cass.Editor;

namespace Wirenook.Validation.Editor
{
    /// <summary>
    /// Renders what the toon shader's additions do to a built variant: the
    /// error screen on the eyes, the sign that faces each camera, and the
    /// glitch at a simmer and at its hardest. The properties are set by
    /// hand, as the away feature's animator would set them; the first
    /// pictures have them all at rest and should show the avatar exactly as
    /// it always was.
    ///
    /// The glitch re-rolls with the clock, so no two runs give the same
    /// picture. That is as intended; look for whether it reads as a fault,
    /// not for a particular shape.
    /// </summary>
    public static class AwayPreview
    {
        /// <returns>The folder the pictures were written to.</returns>
        public static string Render(string slug)
        {
            var folder = Path.Combine(ContactSheets.OutputFolder, "away");
            if (Directory.Exists(folder)) Directory.Delete(folder, true);

            var scene = ValidationScene.Open(out _);
            CassBuild.Measure(slug, out var built);
            try
            {
                UnityEngine.SceneManagement.SceneManager.MoveGameObjectToScene(built, scene);
                CassPreview.SkinEveryRender(built);
                CassPreview.StandAtRest(built);
                var renderers = built.GetComponentsInChildren<Renderer>(true);
                var block = new MaterialPropertyBlock();
                var cameras = ValidationScene.Cameras(scene).ToList();
                var index = 0;

                void Shoot(string label, float glitch, float screen, float sign, params string[] views)
                {
                    block.Clear();
                    block.SetFloat(ToonMaterial.Glitch, glitch);
                    block.SetFloat(ToonMaterial.Screen, screen);
                    block.SetFloat(ToonMaterial.Sign, sign > 0f ? 1f : 0f);
                    block.SetFloat(ToonMaterial.SignShow, sign);
                    foreach (var renderer in renderers) renderer.SetPropertyBlock(block);
                    foreach (var camera in cameras.Where(camera => views.Length == 0 || views.Contains(camera.name)))
                        ContactSheets.Capture(camera, Path.Combine(folder, "away", index++.ToString("000") + " " + label + ", " + camera.name + ".png"));
                }

                Shoot("at rest", 0f, 0f, 0f, "Three-Quarter", "Upper Body");
                Shoot("screens", 0f, 1f, 0f, "Face", "Nose To Nose", "Face Three-Quarter");
                // Every camera once: the sign should face each of them, and stand on its side of the avatar.
                Shoot("away", 0.15f, 1f, 1f);
                Shoot("window half out", 0f, 1f, 0.5f, "Three-Quarter");
                Shoot("jolt", 0.9f, 1f, 1f, "Three-Quarter", "Front", "Upper Body", "Left");
                Shoot("worst", 1f, 1f, 1f, "Three-Quarter", "Front");
                foreach (var renderer in renderers) renderer.SetPropertyBlock(null);
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
