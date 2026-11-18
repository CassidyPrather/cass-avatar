using System.IO;
using System.Linq;
using nadena.dev.ndmf;
using UnityEditor;
using UnityEngine;
using VRC.SDK3.Avatars.Components;
using Wirenook.Cass.Editor;

namespace Wirenook.Validation.Editor
{
    /// <summary>
    /// Renders clips of a generated locomotion controller (a gait, a crouch,
    /// a fall, a landing) on a built variant at four moments each, from the
    /// front quarter and the side. The gait model only knows a pelvis, two
    /// feet and a few angles; this is where a pose is seen on the avatar's
    /// own body and clothes.
    /// </summary>
    public static class GaitPreview
    {
        /// <param name="controllerPath">A Base controller written by the locomotion package.</param>
        /// <param name="clips">Clip names, separated by commas, as the bake report lists them.</param>
        /// <param name="hold">
        /// Clips of the variant's FX controller to hold meanwhile, separated by commas: for example
        /// "outfit.skirt.bottom shown,outfit.default.bottom hidden" to see the skirt. May be empty.
        /// </param>
        /// <returns>The folder the pictures were written to.</returns>
        public static string Render(string slug, string controllerPath, string clips, string hold)
        {
            var folder = Path.Combine(ContactSheets.OutputFolder, "gaits");
            if (Directory.Exists(folder)) Directory.Delete(folder, true);

            var all = AssetDatabase.LoadAllAssetsAtPath(controllerPath).OfType<AnimationClip>().ToList();
            if (all.Count == 0) throw new FileNotFoundException("No clips in a controller at " + controllerPath + ".", controllerPath);
            var wanted = clips.Split(',').Select(name => name.Trim()).Where(name => name.Length > 0).Select(name =>
                all.FirstOrDefault(clip => clip.name == name) ??
                throw new System.ArgumentException("The controller has no clip called \"" + name + "\".")).ToList();
            var worn = hold.Split(',').Select(name => name.Trim()).Where(name => name.Length > 0).ToList();

            var scene = ValidationScene.Open(out _);
            CassBuild.Measure(slug, out var built);
            try
            {
                UnityEngine.SceneManagement.SceneManager.MoveGameObjectToScene(built, scene);
                CassPreview.SkinEveryRender(built);
                var held = CassPreview.AllOff(CassPreview.Toggles(built));
                var fx = built.GetComponent<VRCAvatarDescriptor>().baseAnimationLayers
                    .First(layer => layer.type == VRCAvatarDescriptor.AnimLayerType.FX).animatorController;
                foreach (var name in worn)
                {
                    // Modular Avatar prefixes the clips it re-roots.
                    var state = fx.animationClips.FirstOrDefault(clip => clip.name == name || clip.name == "rebased " + name) ??
                                throw new System.ArgumentException("The variant's FX controller has no clip called \"" + name + "\".");
                    CassPreview.Hold(held, state);
                }

                var cameras = ValidationScene.Cameras(scene).ToDictionary(camera => camera.name);
                var index = 0;
                foreach (var clip in wanted)
                {
                    foreach (var phase in new[] { 0.05f, 0.3f, 0.55f, 0.8f })
                    {
                        CassPreview.Sample(built, clip, phase * clip.length, held);
                        foreach (var camera in new[] { "Three-Quarter", "Left" })
                        {
                            ContactSheets.Capture(cameras[camera], Path.Combine(folder, clip.name.Replace(':', ' '),
                                index++.ToString("000") + " " + camera + " at " + phase.ToString("0.00") + ".png"));
                        }
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
