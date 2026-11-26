using System.Globalization;
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEngine;
using Wirenook.Assets.Editor;

namespace Wirenook.Validation.Editor
{
    /// <summary>
    /// Pictures of a one-piece prop (OnePieceProp) with its parts at chosen
    /// sizes: the mesh is one, and what unfolds it is the shader, so a
    /// picture of the mesh alone would show the parts folded away.
    /// </summary>
    public static class PartsPreview
    {
        /// <param name="prefabPath">A prefab with a one-piece prop somewhere in it.</param>
        /// <param name="sizes">Sets of four sizes, as "0,0,0,0;1,0,0,0".</param>
        /// <returns>The folder the pictures are in: dist/validation/parts.</returns>
        public static string Render(string prefabPath, string sizes)
        {
            var prefab = AssetDatabase.LoadAssetAtPath<GameObject>(prefabPath);
            if (prefab == null) return "No prefab at " + prefabPath;
            var folder = Path.GetFullPath("dist/validation/parts");
            Directory.CreateDirectory(folder);

            const int layer = 31;
            var instance = (GameObject)PrefabUtility.InstantiatePrefab(prefab);
            var cameraObject = new GameObject("Parts Camera") { hideFlags = HideFlags.HideAndDontSave };
            var lightObject = new GameObject("Parts Light") { hideFlags = HideFlags.HideAndDontSave };
            var target = RenderTexture.GetTemporary(512, 512, 24, RenderTextureFormat.ARGB32, RenderTextureReadWrite.sRGB);
            var previous = RenderTexture.active;
            try
            {
                var renderer = instance.GetComponentsInChildren<MeshRenderer>(true)
                    .FirstOrDefault(candidate => candidate.sharedMaterials.Any(material => material != null && material.HasProperty(ToonMaterial.Parts)) &&
                                                 candidate.GetComponent<MeshFilter>().sharedMesh.name.EndsWith("in one piece"));
                if (renderer == null) return "Nothing in " + prefabPath + " is a one-piece prop.";
                foreach (var transform in instance.GetComponentsInChildren<Transform>(true)) transform.gameObject.layer = 0;
                renderer.gameObject.layer = layer;
                // A prop that is switched on from a menu rests folded to nothing.
                renderer.transform.localScale = Vector3.one;

                var light = lightObject.AddComponent<Light>();
                light.type = LightType.Directional;
                light.transform.rotation = Quaternion.Euler(40f, 150f, 0f);

                var bounds = renderer.bounds;
                var camera = cameraObject.AddComponent<Camera>();
                camera.clearFlags = CameraClearFlags.SolidColor;
                camera.backgroundColor = new Color(0.3f, 0.3f, 0.34f);
                camera.fieldOfView = 24f;
                camera.nearClipPlane = 0.05f;
                camera.farClipPlane = 30f;
                camera.targetTexture = target;
                camera.cullingMask = 1 << layer;
                var reach = bounds.extents.magnitude;
                camera.transform.position = bounds.center + Quaternion.Euler(20f, 205f, 0f) * Vector3.back * (reach * 1.15f / Mathf.Tan(12f * Mathf.Deg2Rad));
                camera.transform.LookAt(bounds.center);

                var block = new MaterialPropertyBlock();
                var index = 0;
                foreach (var set in sizes.Split(';'))
                {
                    var values = set.Split(',').Select(value => float.Parse(value, CultureInfo.InvariantCulture)).ToArray();
                    block.SetVector(ToonMaterial.Parts, new Vector4(values[0], values[1], values[2], values[3]));
                    renderer.SetPropertyBlock(block);
                    camera.Render();
                    RenderTexture.active = target;
                    var image = new Texture2D(512, 512, TextureFormat.RGB24, false);
                    image.ReadPixels(new Rect(0, 0, 512, 512), 0, 0);
                    image.Apply();
                    File.WriteAllBytes(Path.Combine(folder, prefab.name + " " + index++ + " (" + set.Replace(",", " ") + ").png"), image.EncodeToPNG());
                    Object.DestroyImmediate(image);
                }

                return folder;
            }
            finally
            {
                RenderTexture.active = previous;
                RenderTexture.ReleaseTemporary(target);
                Object.DestroyImmediate(cameraObject);
                Object.DestroyImmediate(lightObject);
                Object.DestroyImmediate(instance);
            }
        }
    }
}
