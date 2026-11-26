using System.Collections.Generic;
using System.Globalization;
using System.IO;
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
    /// Plays a built variant's FX controller through a script, in the
    /// editor and without play mode, and takes pictures along the way. It
    /// is for features that are a course of events (a fire that catches, a
    /// marshmallow that toasts), where a picture of one clip says little.
    ///
    /// The script is steps separated by semicolons:
    ///
    ///     Name=1          set an animator parameter
    ///     wait 1.5        let that many seconds pass
    ///     shot lit>Campfire:1.6
    ///                     a picture called "lit" of the object named
    ///                     Campfire, from 1.6 m (1.2 m when left out)
    ///     read Name       put the parameter's value in the report
    ///
    /// Unity's own animator does the work, so layers, blend trees and
    /// animated parameters behave as they will in VRChat. VRChat's own
    /// parts do not run: contacts, parameter drivers, constraints, sound.
    /// The script stands in for contacts by setting what a receiver would.
    /// The body is left in the humanoid's own rest pose, sunk through the
    /// floor, since nothing here animates it; pictures go by where the
    /// named object is.
    /// </summary>
    public static class FeaturePlay
    {
        /// <returns>What was read, and the folder the pictures are in: dist/validation/play/&lt;slug&gt;.</returns>
        public static string Run(string slug, string script)
        {
            var folder = Path.GetFullPath(Path.Combine("dist/validation/play", slug));
            if (Directory.Exists(folder)) Directory.Delete(folder, true);
            Directory.CreateDirectory(folder);

            const int layer = 31;
            var report = new StringBuilder();
            CassBuild.Measure(slug, out var built);
            var cameraObject = new GameObject("Feature Play Camera") { hideFlags = HideFlags.HideAndDontSave };
            var lightObject = new GameObject("Feature Play Light") { hideFlags = HideFlags.HideAndDontSave };
            var target = RenderTexture.GetTemporary(512, 512, 24, RenderTextureFormat.ARGB32, RenderTextureReadWrite.sRGB);
            var previous = RenderTexture.active;
            try
            {
                foreach (var transform in built.GetComponentsInChildren<Transform>(true)) transform.gameObject.layer = layer;
                // Unity skins a mesh once a frame, and every picture here is taken within one.
                foreach (var skin in built.GetComponentsInChildren<SkinnedMeshRenderer>(true)) skin.forceMatrixRecalculationPerRender = true;
                var descriptor = built.GetComponent<VRCAvatarDescriptor>();
                var animator = built.GetComponent<Animator>();
                animator.runtimeAnimatorController = descriptor.baseAnimationLayers
                    .First(playable => playable.type == VRCAvatarDescriptor.AnimLayerType.FX).animatorController;
                animator.cullingMode = AnimatorCullingMode.AlwaysAnimate;
                animator.Rebind();
                animator.Update(0f);
                var parameters = animator.parameters.ToDictionary(parameter => parameter.name);

                var light = lightObject.AddComponent<Light>();
                light.type = LightType.Directional;
                light.transform.rotation = Quaternion.Euler(40f, 150f, 0f);
                var camera = cameraObject.AddComponent<Camera>();
                camera.clearFlags = CameraClearFlags.SolidColor;
                camera.backgroundColor = new Color(0.3f, 0.3f, 0.34f);
                camera.fieldOfView = 24f;
                camera.nearClipPlane = 0.02f;
                camera.farClipPlane = 30f;
                camera.targetTexture = target;
                camera.cullingMask = 1 << layer;

                var shots = 0;
                foreach (var step in script.Split(';').Select(part => part.Trim()).Where(part => part.Length > 0))
                {
                    if (step.StartsWith("wait "))
                    {
                        var seconds = float.Parse(step.Substring(5), CultureInfo.InvariantCulture);
                        for (var time = 0f; time < seconds; time += 1f / 60f) animator.Update(1f / 60f);
                    }
                    else if (step.StartsWith("read "))
                    {
                        var name = step.Substring(5).Trim();
                        if (!parameters.TryGetValue(name, out var parameter)) return "The FX controller has no parameter named " + name;
                        report.AppendLine(name + " = " + (parameter.type == AnimatorControllerParameterType.Bool
                            ? animator.GetBool(name).ToString()
                            : parameter.type == AnimatorControllerParameterType.Int
                                ? animator.GetInteger(name).ToString()
                                : animator.GetFloat(name).ToString("0.000", CultureInfo.InvariantCulture)));
                    }
                    else if (step.StartsWith("shot "))
                    {
                        var parts = step.Substring(5).Split('>');
                        var aim = parts[1].Split(':');
                        var distance = aim.Length > 1 ? float.Parse(aim[1], CultureInfo.InvariantCulture) : 1.2f;
                        // The optimiser folds a chain of objects into one and joins their names with dollar signs.
                        var subject = built.GetComponentsInChildren<Transform>(true)
                            .FirstOrDefault(transform => transform.name == aim[0] || transform.name.Split('$').Contains(aim[0]));
                        if (subject == null) return "The built avatar has nothing named " + aim[0];
                        camera.transform.position = subject.position + Quaternion.Euler(22f, 205f, 0f) * Vector3.back * distance;
                        camera.transform.LookAt(subject.position);
                        camera.Render();
                        RenderTexture.active = target;
                        var image = new Texture2D(512, 512, TextureFormat.RGB24, false);
                        image.ReadPixels(new Rect(0, 0, 512, 512), 0, 0);
                        image.Apply();
                        File.WriteAllBytes(Path.Combine(folder, shots++.ToString("00") + " " + parts[0].Trim() + ".png"), image.EncodeToPNG());
                        Object.DestroyImmediate(image);
                    }
                    else if (step.Contains("="))
                    {
                        var name = step.Split('=')[0].Trim();
                        var value = float.Parse(step.Split('=')[1], CultureInfo.InvariantCulture);
                        if (!parameters.TryGetValue(name, out var parameter)) return "The FX controller has no parameter named " + name;
                        switch (parameter.type)
                        {
                            case AnimatorControllerParameterType.Bool: animator.SetBool(name, value != 0f); break;
                            case AnimatorControllerParameterType.Int: animator.SetInteger(name, Mathf.RoundToInt(value)); break;
                            default: animator.SetFloat(name, value); break;
                        }
                    }
                    else
                    {
                        return "Not a step: " + step;
                    }
                }

                report.Append(folder);
                return report.ToString();
            }
            finally
            {
                RenderTexture.active = previous;
                RenderTexture.ReleaseTemporary(target);
                Object.DestroyImmediate(cameraObject);
                Object.DestroyImmediate(lightObject);
                Object.DestroyImmediate(built);
                AvatarProcessor.CleanTemporaryAssets();
            }
        }
    }
}
