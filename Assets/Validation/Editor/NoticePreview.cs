using System.IO;
using System.Linq;
using UnityEditor;
using UnityEngine;

namespace Wirenook.Validation.Editor
{
    /// <summary>
    /// Renders the screen notice from several validation cameras, to confirm
    /// the card lands in the same place in view whatever the camera is
    /// looking at. This checks the shader's placement in the editor only; a
    /// headset is the real test.
    /// </summary>
    public static class NoticePreview
    {
        private const string Prefab = "Packages/net.wirenook.adventure-tools/Prefabs/Wirenook Notice.prefab";

        /// <returns>The folder the pictures were written to.</returns>
        public static string Render()
        {
            var folder = Path.Combine(ContactSheets.OutputFolder, "notice");
            if (Directory.Exists(folder)) Directory.Delete(folder, true);

            var scene = ValidationScene.Open(out _);
            var instance = (GameObject)PrefabUtility.InstantiatePrefab(AssetDatabase.LoadAssetAtPath<GameObject>(Prefab), scene);
            try
            {
                var card = instance.GetComponentInChildren<MeshRenderer>(true);
                card.gameObject.SetActive(true);
                var block = new MaterialPropertyBlock();
                var cameras = ValidationScene.Cameras(scene).ToDictionary(camera => camera.name);

                var index = 0;
                foreach (var (camera, notice, show) in new[]
                         {
                             ("Front", 0, 1f), ("Three-Quarter", 1, 1f), ("High", 2, 1f), ("Face", 5, 1f),
                             ("Front", 3, 0.5f), ("Front", 7, 0f),
                         })
                {
                    block.SetFloat("_Index", notice);
                    block.SetFloat("_Show", show);
                    card.SetPropertyBlock(block);
                    ContactSheets.Capture(cameras[camera],
                        Path.Combine(folder, "notice", index++.ToString("000") + " " + camera + " card " + notice + " show " + show + ".png"));
                }
            }
            finally
            {
                Object.DestroyImmediate(instance);
            }

            ContactSheets.Compose(folder);
            return Path.GetFullPath(folder);
        }
    }
}
