using System.IO;
using System.Linq;
using UnityEditor;
using UnityEngine;

namespace Wirenook.Validation.Editor
{
    /// <summary>
    /// Renders the beacon from cameras that can see it and cameras that
    /// cannot, to confirm the pin stands over its origin and the arrow points
    /// the way to turn. This checks the shader's placement in the editor
    /// only; a headset is the real test.
    /// </summary>
    public static class BeaconPreview
    {
        private const string Prefab = "Packages/net.wirenook.adventure-tools/Prefabs/Wirenook Beacon.prefab";

        /// <returns>The folder the pictures were written to.</returns>
        public static string Render()
        {
            var folder = Path.Combine(ContactSheets.OutputFolder, "beacon");
            if (Directory.Exists(folder)) Directory.Delete(folder, true);

            var scene = ValidationScene.Open(out _);
            var instance = (GameObject)PrefabUtility.InstantiatePrefab(AssetDatabase.LoadAssetAtPath<GameObject>(Prefab), scene);
            var rig = new GameObject("Beacon Preview Camera");
            try
            {
                var mark = instance.GetComponentInChildren<MeshRenderer>(true);
                mark.gameObject.SetActive(true);
                mark.transform.localScale = Vector3.one;
                // Where a head would be.
                mark.transform.position = new Vector3(0f, 1.35f, 0f);
                var block = new MaterialPropertyBlock();
                block.SetFloat("_Show", 1f);
                mark.SetPropertyBlock(block);

                var front = ValidationScene.Cameras(scene).First(candidate => candidate.name == "Front");
                var camera = rig.AddComponent<Camera>();
                camera.CopyFrom(front);

                var index = 0;
                foreach (var (label, position, yaw, pitch) in new[]
                         {
                             ("in view, near", new Vector3(0f, 1.3f, 5f), 180f, 0f),
                             ("in view, far", new Vector3(0f, 1.6f, 45f), 180f, 0f),
                             ("too close", new Vector3(0f, 1.3f, 1.5f), 180f, 0f),
                             ("to the right", new Vector3(0f, 1.3f, 6f), 90f, 0f),
                             ("to the left", new Vector3(0f, 1.3f, 6f), 270f, 0f),
                             ("behind", new Vector3(0f, 1.3f, 6f), 0f, 0f),
                             ("above", new Vector3(0f, 1.3f, 6f), 180f, 70f),
                             ("below, right", new Vector3(0f, 9f, 6f), 110f, 0f),
                             ("out of range", new Vector3(0f, 1.3f, 120f), 90f, 0f),
                         })
                {
                    camera.transform.SetPositionAndRotation(position, Quaternion.Euler(pitch, yaw, 0f));
                    ContactSheets.Capture(camera, Path.Combine(folder, "beacon", index++.ToString("000") + " " + label + ".png"));
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
