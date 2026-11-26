using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Text;
using nadena.dev.ndmf;
using UnityEngine;
using VRC.SDK3.Avatars.Components;
using Wirenook.Cass.Editor;

namespace Wirenook.Validation.Editor
{
    /// <summary>
    /// Plays a built variant's Base controller through a script, in the
    /// editor and without play mode: FeaturePlay's counterpart for the
    /// layer that moves the body. The script sets what VRChat would
    /// (VelocityX, VelocityZ, VelocityY, Upright, Grounded, VRMode) and
    /// looks at the result. Steps are separated by semicolons:
    ///
    ///     Name=1              set an animator parameter
    ///     wait 1.5            let that many seconds pass
    ///     shot walking        a picture called "walking": the side and the front quarter
    ///     strip walk 8 0.5    eight pictures from the side over half a second, in one row
    ///     feet 2              over two seconds, how far each planted foot creeps over the
    ///                         ground the velocity parameters say is passing, and how low it gets
    ///     state               which state the first layer is in
    ///
    /// Only the Base controller runs. The Additive layer, tracking and IK do not.
    /// </summary>
    public static class LocomotionPlay
    {
        private const float Frame = 1f / 120f;
        private const int Layer = 31;
        private const int Wide = 300, Tall = 400;

        private static readonly string[] States =
        {
            "Standing", "Crouching", "Prone", "SmallHop", "Short Fall", "LongFall", "QuickLand", "HardLand", "RestoreTracking", "RestoreToHop",
        };

        /// <returns>What was measured, and the folder the pictures are in: dist/validation/locomotion/&lt;slug&gt;.</returns>
        public static string Run(string slug, string script)
        {
            var folder = Path.GetFullPath(Path.Combine("dist/validation/locomotion", slug));
            if (Directory.Exists(folder)) Directory.Delete(folder, true);
            Directory.CreateDirectory(folder);

            var report = new StringBuilder();
            CassBuild.Measure(slug, out var built);
            var cameraObject = new GameObject("Locomotion Play Camera") { hideFlags = HideFlags.HideAndDontSave };
            var lightObject = new GameObject("Locomotion Play Light") { hideFlags = HideFlags.HideAndDontSave };
            var floor = GameObject.CreatePrimitive(PrimitiveType.Cube);
            floor.hideFlags = HideFlags.HideAndDontSave;
            var target = RenderTexture.GetTemporary(Wide, Tall, 24, RenderTextureFormat.ARGB32, RenderTextureReadWrite.sRGB);
            var previous = RenderTexture.active;
            try
            {
                foreach (var transform in built.GetComponentsInChildren<Transform>(true)) transform.gameObject.layer = Layer;
                foreach (var skin in built.GetComponentsInChildren<SkinnedMeshRenderer>(true)) skin.forceMatrixRecalculationPerRender = true;
                var descriptor = built.GetComponent<VRCAvatarDescriptor>();
                var controller = descriptor.baseAnimationLayers
                    .First(playable => playable.type == VRCAvatarDescriptor.AnimLayerType.Base).animatorController;
                if (controller == null) return slug + " has no Base controller of its own: it plays VRChat's default.";
                // Modular Avatar keeps the name of the layer it replaced; the layers say whose it is.
                report.AppendLine("Base controller: " + controller.name + ", layers: " + string.Join(", ",
                    ((UnityEditor.Animations.AnimatorController)controller).layers.Select(layer => layer.name)));
                var animator = built.GetComponent<Animator>();
                animator.runtimeAnimatorController = controller;
                animator.cullingMode = AnimatorCullingMode.AlwaysAnimate;
                animator.applyRootMotion = false;
                animator.Rebind();
                animator.Update(0f);
                var parameters = animator.parameters.ToDictionary(parameter => parameter.name);

                // A thin slab whose top is the ground, so that a foot through it shows.
                floor.layer = Layer;
                floor.transform.position = new Vector3(0f, -0.01f, 0f);
                floor.transform.localScale = new Vector3(3f, 0.02f, 3f);

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
                camera.cullingMask = 1 << Layer;

                float height = descriptor.ViewPosition.y * 1.1f;
                var centre = built.transform.position + Vector3.up * height * 0.5f;
                float distance = height * 3.3f;

                Color32[] Picture(Vector3 from)
                {
                    camera.transform.position = centre + from * distance;
                    camera.transform.LookAt(centre);
                    camera.Render();
                    RenderTexture.active = target;
                    var image = new Texture2D(Wide, Tall, TextureFormat.RGB24, false);
                    image.ReadPixels(new Rect(0, 0, Wide, Tall), 0, 0);
                    image.Apply();
                    var pixels = image.GetPixels32();
                    Object.DestroyImmediate(image);
                    return pixels;
                }

                void Save(string name, List<Color32[]> pictures)
                {
                    var sheet = new Texture2D(Wide * pictures.Count, Tall, TextureFormat.RGB24, false);
                    for (var i = 0; i < pictures.Count; i++) sheet.SetPixels32(i * Wide, 0, Wide, Tall, pictures[i]);
                    sheet.Apply();
                    File.WriteAllBytes(Path.Combine(folder, name + ".png"), sheet.EncodeToPNG());
                    Object.DestroyImmediate(sheet);
                }

                // The avatar faces +Z: from its left it is seen walking toward the right of the picture.
                var side = Vector3.left;
                var quarter = Quaternion.Euler(12f, 205f, 0f) * Vector3.back;

                var shots = 0;
                foreach (var step in script.Split(';').Select(part => part.Trim()).Where(part => part.Length > 0))
                {
                    var words = step.Split(' ');
                    if (words[0] == "wait")
                    {
                        var seconds = float.Parse(words[1], CultureInfo.InvariantCulture);
                        for (var time = 0f; time < seconds; time += Frame) animator.Update(Frame);
                    }
                    else if (words[0] == "state")
                    {
                        var info = animator.GetCurrentAnimatorStateInfo(0);
                        report.AppendLine("state: " + (States.FirstOrDefault(info.IsName) ?? "unknown") +
                                          (animator.IsInTransition(0) ? " (in transition)" : ""));
                    }
                    else if (words[0] == "shot")
                    {
                        Save(shots++.ToString("00") + " " + words[1], new List<Color32[]> { Picture(side), Picture(quarter) });
                    }
                    else if (words[0] == "strip")
                    {
                        var count = int.Parse(words[2]);
                        var seconds = float.Parse(words[3], CultureInfo.InvariantCulture);
                        var pictures = new List<Color32[]>();
                        for (var i = 0; i < count; i++)
                        {
                            pictures.Add(Picture(side));
                            for (var time = 0f; time < seconds / count - Frame / 2f; time += Frame) animator.Update(Frame);
                        }

                        Save(shots++.ToString("00") + " " + words[1], pictures);
                    }
                    else if (words[0] == "feet")
                    {
                        var velocity = new Vector3(animator.GetFloat("VelocityX"), 0f, animator.GetFloat("VelocityZ"));
                        report.AppendLine("at (" + velocity.x.ToString("0.##") + ", " + velocity.z.ToString("0.##") + ") m/s: " +
                                          Feet(animator, built.transform, velocity, float.Parse(words[1], CultureInfo.InvariantCulture)));
                    }
                    else if (step.Contains("="))
                    {
                        var name = step.Split('=')[0].Trim();
                        var value = float.Parse(step.Split('=')[1], CultureInfo.InvariantCulture);
                        if (!parameters.TryGetValue(name, out var parameter)) return "The Base controller has no parameter named " + name;
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
                Object.DestroyImmediate(floor);
                Object.DestroyImmediate(built);
                AvatarProcessor.CleanTemporaryAssets();
            }
        }

        /// <summary>
        /// A foot counts as planted while its ankle is within a few
        /// millimetres of the lowest it gets, for a run of frames. Planted,
        /// it should go back through the avatar's space at exactly the
        /// velocity; how far it strays from that in one stance is its creep.
        /// </summary>
        private static string Feet(Animator animator, Transform root, Vector3 velocity, float seconds)
        {
            var bones = new[] { animator.GetBoneTransform(HumanBodyBones.LeftFoot), animator.GetBoneTransform(HumanBodyBones.RightFoot) };
            var frames = Mathf.RoundToInt(seconds / Frame);
            var tracks = new[] { new Vector3[frames], new Vector3[frames] };
            for (var i = 0; i < frames; i++)
            {
                animator.Update(Frame);
                for (var foot = 0; foot < 2; foot++) tracks[foot][i] = root.InverseTransformPoint(bones[foot].position);
            }

            const float near = 0.004f;
            const int margin = 2;
            var text = new StringBuilder();
            for (var foot = 0; foot < 2; foot++)
            {
                var track = tracks[foot];
                var lowest = track.Min(point => point.y);
                var highest = track.Max(point => point.y);
                float creep = 0f, travel = 0f, time = 0f;
                var start = -1;
                for (var i = 0; i <= frames; i++)
                {
                    var down = i < frames && track[i].y <= lowest + near;
                    if (down && start < 0) start = i;
                    if (down || start < 0) continue;
                    // Frames at either end of a run are a foot arriving or leaving.
                    int from = start + margin, to = i - 1 - margin;
                    for (var j = from; j <= to; j++)
                    {
                        var held = track[j] + velocity * ((j - from) * Frame) - track[from];
                        held.y = 0f;
                        creep = Mathf.Max(creep, held.magnitude);
                    }

                    if (to > from)
                    {
                        var moved = track[to] - track[from];
                        moved.y = 0f;
                        travel += moved.magnitude;
                        time += (to - from) * Frame;
                    }

                    start = -1;
                }

                text.Append((foot == 0 ? "left" : ", right") + " foot creeps " + (creep * 1000f).ToString("F1") + " mm in a stance" +
                            (time > 0f && velocity.magnitude > 0f ? " (passes at " + (travel / time / velocity.magnitude).ToString("P0") + " of the ground's speed)" : "") +
                            ", ankle from " + (lowest * 1000f).ToString("F0") + " to " + (highest * 1000f).ToString("F0") + " mm up");
            }

            return text.ToString();
        }
    }
}
