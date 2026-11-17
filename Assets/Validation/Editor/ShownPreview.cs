using System.IO;
using System.Linq;
using UnityEditor;
using UnityEngine;

namespace Wirenook.Validation.Editor
{
    /// <summary>
    /// Renders a feature prefab with some of its hidden parts brought out.
    /// Feature prefabs rest with their props scaled to nothing, so a plain
    /// picture of one is empty; this scales the named objects back up, one
    /// picture set per name, and frames whatever is then visible.
    /// </summary>
    public static class ShownPreview
    {
        /// <param name="prefabPath">The feature prefab.</param>
        /// <param name="names">Comma-separated names of objects to show, each in turn.</param>
        /// <returns>The folder the pictures were written to.</returns>
        public static string Render(string prefabPath, string names)
        {
            var label = Path.GetFileNameWithoutExtension(prefabPath);
            var folder = Path.Combine(ContactSheets.OutputFolder, "shown", label);
            if (Directory.Exists(folder)) Directory.Delete(folder, true);

            var scene = ValidationScene.Open(out _);
            var instance = (GameObject)PrefabUtility.InstantiatePrefab(AssetDatabase.LoadAssetAtPath<GameObject>(prefabPath), scene);
            var rig = new GameObject("Shown Preview Camera");
            try
            {
                var camera = rig.AddComponent<Camera>();
                camera.CopyFrom(ValidationScene.Cameras(scene).First(candidate => candidate.name == "Front"));
                var index = 0;
                foreach (var name in names.Split(','))
                {
                    var shown = instance.GetComponentsInChildren<Transform>(true).First(candidate => candidate.name == name.Trim());
                    var rest = shown.localScale;
                    shown.localScale = Vector3.one;
                    foreach (var parent in shown.GetComponentsInParent<Transform>(true)) parent.gameObject.SetActive(true);

                    var renderers = shown.GetComponentsInChildren<Renderer>(true);
                    var bounds = renderers[0].bounds;
                    foreach (var renderer in renderers) bounds.Encapsulate(renderer.bounds);
                    var reach = bounds.extents.magnitude / Mathf.Tan(0.5f * camera.fieldOfView * Mathf.Deg2Rad) * 1.15f;
                    foreach (var (view, yaw, pitch) in new[] { ("front", 180f, 12f), ("three-quarter", 215f, 22f), ("back", 0f, 12f), ("top", 180f, 80f) })
                    {
                        var rotation = Quaternion.Euler(pitch, yaw, 0f);
                        camera.transform.SetPositionAndRotation(bounds.center - rotation * Vector3.forward * reach, rotation);
                        ContactSheets.Capture(camera, Path.Combine(folder, "shown", index++.ToString("000") + " " + name.Trim() + " " + view + ".png"));
                    }

                    shown.localScale = rest;
                }
            }
            finally
            {
                Object.DestroyImmediate(rig);
                Object.DestroyImmediate(instance);
            }

            ContactSheets.Compose(folder);
            return Path.GetFullPath(folder);
        }
    }
}
