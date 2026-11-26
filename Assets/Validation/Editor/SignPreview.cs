using System.Collections.Generic;
using System.IO;
using System.Linq;
using nadena.dev.ndmf;
using UnityEngine;
using Wirenook.Assets.Editor;
using Wirenook.Cass.Editor;

namespace Wirenook.Validation.Editor
{
    /// <summary>
    /// Renders every sign a built variant carries, one at a time, unfolded.
    /// Signs are geometry in the avatar's mesh that the toon shader turns to
    /// face the viewer (SignMesh in net.wirenook.assets); folded away they
    /// are nothing, so no other picture shows them. The numbers are read
    /// back from the built meshes' fourth UV set, which is also the check
    /// that the optimiser kept that set.
    /// </summary>
    public static class SignPreview
    {
        /// <returns>The folder the pictures were written to, or a note that the variant has no signs.</returns>
        public static string Render(string slug)
        {
            var folder = Path.Combine(ContactSheets.OutputFolder, "signs");
            if (Directory.Exists(folder)) Directory.Delete(folder, true);

            var scene = ValidationScene.Open(out _);
            CassBuild.Measure(slug, out var built);
            try
            {
                UnityEngine.SceneManagement.SceneManager.MoveGameObjectToScene(built, scene);
                CassPreview.StandAtRest(built);
                var renderers = built.GetComponentsInChildren<Renderer>(true);
                var numbers = new SortedSet<int>();
                foreach (var skinned in built.GetComponentsInChildren<SkinnedMeshRenderer>(true))
                {
                    var which = new List<Vector2>();
                    if (skinned.sharedMesh != null) skinned.sharedMesh.GetUVs(3, which);
                    foreach (var value in which.Where(value => value.x < -0.5f)) numbers.Add(Mathf.RoundToInt(-value.x));
                }

                if (numbers.Count == 0) return slug + " has no signs in its built meshes.";

                var cameras = ValidationScene.Cameras(scene).ToDictionary(camera => camera.name);
                var block = new MaterialPropertyBlock();
                var index = 0;
                foreach (var number in numbers)
                {
                    block.Clear();
                    block.SetFloat(ToonMaterial.Sign, number);
                    block.SetFloat(ToonMaterial.SignShow, 1f);
                    // Away as well, where the avatar has a screen: it shares the third UV set with the signs.
                    block.SetFloat(ToonMaterial.Screen, 1f);
                    foreach (var renderer in renderers) renderer.SetPropertyBlock(block);
                    foreach (var view in new[] { "Upper Body", "Three-Quarter" })
                        ContactSheets.Capture(cameras[view], Path.Combine(folder, "signs", index++.ToString("000") + " sign " + number + ", " + view + ".png"));
                }

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
