using System.IO;
using System.Linq;
using UnityEditor;
using UnityEngine;

namespace Wirenook.Validation.Editor
{
    /// <summary>
    /// Photographs a prefab on its own, framed to its bounds, under the
    /// validation scene's lighting: a quick look at how a prop imported
    /// (scale, facing, materials) without placing it on an avatar.
    /// </summary>
    public static class PropPreview
    {
        /// <param name="prefabPath">Asset path of the prefab or model.</param>
        /// <returns>The picture's path.</returns>
        public static string Render(string prefabPath)
        {
            var prefab = AssetDatabase.LoadAssetAtPath<GameObject>(prefabPath);
            if (prefab == null) throw new FileNotFoundException("No prefab at that path.", prefabPath);

            var folder = Path.Combine(ContactSheets.OutputFolder, "props", Path.GetFileNameWithoutExtension(prefabPath));
            if (Directory.Exists(folder)) Directory.Delete(folder, true);

            var scene = ValidationScene.Open(out _);
            var instance = (GameObject)PrefabUtility.InstantiatePrefab(prefab, scene);
            var cameraObject = new GameObject("Prop Camera") { hideFlags = HideFlags.HideAndDontSave };
            try
            {
                // Above the floor, so ground-standing props are not cut by it.
                instance.transform.position = new Vector3(0f, 1f, 0f);
                var renderers = instance.GetComponentsInChildren<Renderer>(true).Where(renderer => renderer.enabled).ToList();
                if (renderers.Count == 0) throw new InvalidDataException(prefabPath + " has nothing to render.");
                var bounds = renderers[0].bounds;
                foreach (var renderer in renderers) bounds.Encapsulate(renderer.bounds);

                var camera = cameraObject.AddComponent<Camera>();
                camera.clearFlags = CameraClearFlags.SolidColor;
                camera.backgroundColor = new Color(0.30f, 0.31f, 0.35f);
                camera.fieldOfView = 24f;
                camera.nearClipPlane = 0.01f;
                camera.enabled = false;

                var distance = bounds.extents.magnitude * 1.15f / Mathf.Sin(camera.fieldOfView * 0.5f * Mathf.Deg2Rad);
                var index = 0;
                foreach (var (name, yaw, pitch) in new[] { ("Three-Quarter", 35f, 15f), ("Front", 0f, 0f), ("Side", 90f, 0f), ("Back", 180f, 10f), ("Top", 0f, 80f) })
                {
                    // Seen from +Z is the front, as for avatars.
                    var offset = Quaternion.Euler(-pitch, yaw, 0f) * Vector3.forward * distance;
                    camera.transform.position = bounds.center + offset;
                    camera.transform.LookAt(bounds.center);
                    ContactSheets.Capture(camera, Path.Combine(folder, "views", index++.ToString("000") + " " + name + ".png"));
                }

                var size = bounds.size;
                File.WriteAllText(Path.Combine(folder, "size.txt"),
                    "bounds " + size.x.ToString("0.000") + " x " + size.y.ToString("0.000") + " x " + size.z.ToString("0.000") + " m\n" +
                    "renderers " + string.Join(", ", renderers.Select(renderer => renderer.GetType().Name + " " + renderer.name +
                        " [" + string.Join("|", renderer.sharedMaterials.Select(material => material != null ? material.name : "none")) + "]")) + "\n");
            }
            finally
            {
                Object.DestroyImmediate(cameraObject);
                Object.DestroyImmediate(instance);
            }

            ContactSheets.Compose(folder);
            return Path.GetFullPath(Path.Combine(folder, "views.png")) + "\n" + File.ReadAllText(Path.Combine(folder, "size.txt"));
        }
    }
}
