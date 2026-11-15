using System;
using System.Diagnostics;
using System.IO;
using Newtonsoft.Json;
using UnityEngine;
using Debug = UnityEngine.Debug;

namespace Wirenook.Cass.Editor
{
    /// <summary>
    /// Produces the image VRChat shows for an avatar: a cut-out render of the
    /// built avatar's head and shoulders, composed by tools/thumbnail with
    /// one icon per kind of feature in its build report.
    /// </summary>
    public static class CassThumbnail
    {
        public const string Folder = "dist/thumbnail";
        public const int Width = 1200;
        public const int Height = 900;

        /// <summary>A layer nothing else in a project is expected to use.</summary>
        private const int CutoutLayer = 31;

        /// <summary>
        /// Renders <paramref name="avatar"/> from the chest up, alone on a
        /// transparent background, as it looks when it first loads in. VRChat
        /// shows thumbnails small, and a whole standing figure leaves the face
        /// a few pixels. The avatar is a throwaway build copy; this moves it
        /// to its own layer.
        /// </summary>
        public static string RenderCutout(GameObject avatar, string path)
        {
            CassPreview.StandAtRest(avatar);
            // Whatever else is in the open scene must stay out of the picture.
            foreach (var transform in avatar.GetComponentsInChildren<Transform>(true))
                transform.gameObject.layer = CutoutLayer;

            var bounds = new Bounds(avatar.transform.position, Vector3.zero);
            var any = false;
            // Frame the body, not every renderer: a prop that is switched off
            // still reports bounds, and one left in the world reports them
            // wherever it was dropped.
            foreach (var renderer in avatar.GetComponentsInChildren<SkinnedMeshRenderer>())
            {
                if (!any) bounds = renderer.bounds;
                else bounds.Encapsulate(renderer.bounds);
                any = true;
            }

            if (!any) throw new InvalidOperationException("Nothing to render: " + avatar.name + " has no renderers.");

            var animator = avatar.GetComponent<Animator>();
            var head = animator != null ? animator.GetBoneTransform(HumanBodyBones.Head) : null;
            var chest = animator != null ? animator.GetBoneTransform(HumanBodyBones.Chest) : null;
            if (head == null || chest == null)
                throw new InvalidOperationException("A bust needs a humanoid rig with head and chest bones; " + avatar.name + " has none.");

            // From the chest bone to the top of whatever the head carries
            // (ears, a hat), centred on the head.
            var top = bounds.max.y;
            var bottom = chest.position.y;
            var centre = new Vector3(head.position.x, (top + bottom) * 0.5f, head.position.z);
            var reach = (top - bottom) * 0.5f;

            // A square cut-out; the composer scales it into its own layout.
            const int size = 1024;
            var cameraObject = new GameObject("Thumbnail Camera") { hideFlags = HideFlags.HideAndDontSave };
            var lightObject = new GameObject("Thumbnail Light") { hideFlags = HideFlags.HideAndDontSave };
            var target = RenderTexture.GetTemporary(size, size, 24, RenderTextureFormat.ARGB32, RenderTextureReadWrite.sRGB);
            var previous = RenderTexture.active;
            try
            {
                var light = lightObject.AddComponent<Light>();
                light.type = LightType.Directional;
                light.intensity = 1f;
                light.transform.rotation = Quaternion.Euler(25f, 160f, 0f);

                var camera = cameraObject.AddComponent<Camera>();
                camera.clearFlags = CameraClearFlags.SolidColor;
                camera.backgroundColor = new Color(0f, 0f, 0f, 0f);
                camera.fieldOfView = 20f;
                camera.nearClipPlane = 0.05f;
                camera.farClipPlane = 50f;
                camera.targetTexture = target;
                camera.cullingMask = 1 << CutoutLayer;

                // From the front and slightly to the side, far enough back
                // that the frame runs from the chest to just above the top.
                var direction = avatar.transform.rotation * Quaternion.Euler(4f, 200f, 0f) * Vector3.back;
                var distance = reach * 1.04f / Mathf.Tan(camera.fieldOfView * 0.5f * Mathf.Deg2Rad);
                camera.transform.position = centre + direction * distance;
                camera.transform.LookAt(centre);
                camera.Render();

                RenderTexture.active = target;
                var image = new Texture2D(size, size, TextureFormat.RGBA32, false);
                image.ReadPixels(new Rect(0, 0, size, size), 0, 0);
                image.Apply();
                Directory.CreateDirectory(Path.GetDirectoryName(path));
                File.WriteAllBytes(path, image.EncodeToPNG());
                UnityEngine.Object.DestroyImmediate(image);
            }
            finally
            {
                RenderTexture.active = previous;
                RenderTexture.ReleaseTemporary(target);
                UnityEngine.Object.DestroyImmediate(cameraObject);
                UnityEngine.Object.DestroyImmediate(lightObject);
            }

            return path;
        }

        /// <summary>
        /// Composes the final thumbnail from a build report. The composer is a
        /// Python tool so the layout can be iterated on without Unity.
        /// </summary>
        /// <returns>Path of the thumbnail PNG.</returns>
        public static string Compose(BuildReport report)
        {
            Directory.CreateDirectory(Folder);
            var manifest = Path.GetFullPath(Path.Combine(Folder, report.variant + ".json"));
            var output = Path.GetFullPath(Path.Combine(Folder, report.variant + ".png"));
            File.WriteAllText(manifest, JsonConvert.SerializeObject(report, Formatting.Indented));

            var script = Path.GetFullPath("tools/thumbnail/make_thumbnail.py");
            var process = Process.Start(new ProcessStartInfo
            {
                FileName = "python",
                Arguments = "\"" + script + "\" --manifest \"" + manifest + "\" --out \"" + output + "\"",
                UseShellExecute = false,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
                CreateNoWindow = true,
            });
            var errors = process.StandardError.ReadToEnd();
            process.WaitForExit();
            if (process.ExitCode != 0 || !File.Exists(output))
                throw new InvalidOperationException("tools/thumbnail/make_thumbnail.py failed:\n" + errors);

            Debug.Log("[cass] Thumbnail: " + output);
            return output;
        }
    }
}
