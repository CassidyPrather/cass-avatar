using System.Linq;
using System.Text;
using UnityEditor;
using UnityEngine;
using VRC.SDK3.Avatars.Components;

namespace Wirenook.Validation.Editor
{
    /// <summary>
    /// Runs an avatar prefab's FX controller in the editor, without play
    /// mode, with chosen parameter values, and says which blendshapes of the
    /// face came out above zero, with a picture. It answers what pictures of single clips
    /// cannot: what the layers do to each other. Unity's own animator does
    /// the work, so Write Defaults and layer order behave as they will in
    /// VRChat; VRChat's behaviours (drivers, tracking control) do not run.
    /// </summary>
    public static class LayerProbe
    {
        /// <summary>
        /// A picture of the face as the animator left it, from in front of
        /// the place the avatar sees from, in dist/validation/layers.
        /// </summary>
        private static string Picture(GameObject instance, Transform head, Vector3 seesFrom, Vector3 faces, Vector3 up, string settings)
        {
            // Whatever else the open scene holds stays out of the picture.
            const int layer = 31;
            foreach (var transform in instance.GetComponentsInChildren<Transform>(true)) transform.gameObject.layer = layer;
            // An animator with nothing to say about the body leaves it in
            // the humanoid's own idea of a rest pose, sunk through the floor,
            // so the camera goes by where the head is now.
            var view = head.TransformPoint(seesFrom);
            var forward = head.TransformDirection(faces);
            var upward = head.TransformDirection(up);
            var cameraObject = new GameObject("Layer Probe Camera") { hideFlags = HideFlags.HideAndDontSave };
            var target = RenderTexture.GetTemporary(512, 512, 24, RenderTextureFormat.ARGB32, RenderTextureReadWrite.sRGB);
            var previous = RenderTexture.active;
            try
            {
                var camera = cameraObject.AddComponent<Camera>();
                camera.clearFlags = CameraClearFlags.SolidColor;
                camera.backgroundColor = new Color(0.3f, 0.3f, 0.34f);
                camera.fieldOfView = 20f;
                camera.nearClipPlane = 0.05f;
                camera.farClipPlane = 20f;
                camera.targetTexture = target;
                camera.cullingMask = 1 << layer;
                camera.transform.position = view + forward * 1.9f + upward * 0.05f;
                camera.transform.LookAt(view + upward * 0.05f, upward);
                camera.Render();
                RenderTexture.active = target;
                var image = new Texture2D(512, 512, TextureFormat.RGB24, false);
                image.ReadPixels(new Rect(0, 0, 512, 512), 0, 0);
                image.Apply();
                var folder = System.IO.Path.GetFullPath("dist/validation/layers");
                System.IO.Directory.CreateDirectory(folder);
                var name = instance.name + " " + string.Concat(settings.Select(character => char.IsLetterOrDigit(character) || character == '=' ? character : '-'));
                var path = System.IO.Path.Combine(folder, name + ".png");
                System.IO.File.WriteAllBytes(path, image.EncodeToPNG());
                Object.DestroyImmediate(image);
                return path;
            }
            finally
            {
                RenderTexture.active = previous;
                RenderTexture.ReleaseTemporary(target);
                Object.DestroyImmediate(cameraObject);
            }
        }

        /// <param name="prefabPath">An avatar prefab whose descriptor names an FX controller.</param>
        /// <param name="settings">Parameters to set, as "Name=1;Other=0".</param>
        /// <returns>The face mesh's blendshapes that are above zero after two seconds of the animator.</returns>
        public static string Face(string prefabPath, string settings)
        {
            var prefab = AssetDatabase.LoadAssetAtPath<GameObject>(prefabPath);
            if (prefab == null) return "No prefab at " + prefabPath;
            var instance = (GameObject)PrefabUtility.InstantiatePrefab(prefab);
            try
            {
                var descriptor = instance.GetComponent<VRCAvatarDescriptor>();
                var fx = descriptor.baseAnimationLayers.First(layer => layer.type == VRCAvatarDescriptor.AnimLayerType.FX).animatorController;
                var animator = instance.GetComponent<Animator>();
                var head = animator.GetBoneTransform(HumanBodyBones.Head);
                var seesFrom = head.InverseTransformPoint(instance.transform.TransformPoint(descriptor.ViewPosition));
                var faces = head.InverseTransformDirection(instance.transform.forward);
                var up = head.InverseTransformDirection(instance.transform.up);
                animator.runtimeAnimatorController = fx;
                // Out of every camera's view an animator still runs its states but writes nothing.
                animator.cullingMode = AnimatorCullingMode.AlwaysAnimate;
                animator.Rebind();
                animator.Update(0f);
                foreach (var setting in settings.Split(';').Where(part => part.Contains("=")))
                {
                    var name = setting.Split('=')[0].Trim();
                    var value = float.Parse(setting.Split('=')[1], System.Globalization.CultureInfo.InvariantCulture);
                    var parameter = animator.parameters.FirstOrDefault(candidate => candidate.name == name);
                    if (parameter == null) return "The FX controller has no parameter named " + name;
                    switch (parameter.type)
                    {
                        case AnimatorControllerParameterType.Bool: animator.SetBool(name, value != 0f); break;
                        case AnimatorControllerParameterType.Int: animator.SetInteger(name, Mathf.RoundToInt(value)); break;
                        default: animator.SetFloat(name, value); break;
                    }
                }

                for (var step = 0; step < 40; step++) animator.Update(0.05f);

                var body = instance.transform.Find("Body").GetComponent<SkinnedMeshRenderer>();
                var report = new StringBuilder();
                for (var layer = 0; layer < animator.layerCount; layer++)
                {
                    var state = animator.GetCurrentAnimatorStateInfo(layer);
                    var clips = animator.GetCurrentAnimatorClipInfo(layer);
                    report.AppendLine(layer + " " + animator.GetLayerName(layer) + ": " + (clips.Length > 0 ? clips[0].clip.name : "(no clip)") +
                                      (state.loop ? " (looping)" : ""));
                    if (layer >= 6) break;
                }

                var raised = Enumerable.Range(0, body.sharedMesh.blendShapeCount)
                    .Where(index => body.GetBlendShapeWeight(index) > 0.5f)
                    .Select(index => body.sharedMesh.GetBlendShapeName(index) + "=" + body.GetBlendShapeWeight(index).ToString("0"))
                    .ToList();
                report.Append("raised: " + (raised.Count == 0 ? "(none)" : string.Join(", ", raised)));
                report.AppendLine().Append("picture: " + Picture(instance, head, seesFrom, faces, up, settings));
                return report.ToString();
            }
            finally
            {
                Object.DestroyImmediate(instance);
            }
        }
    }
}
