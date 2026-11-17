using System.IO;
using System.Linq;
using UnityEditor;
using UnityEngine;

namespace Wirenook.Validation.Editor
{
    /// <summary>
    /// Renders the mosaic censor over the avatar, for each area, and with
    /// VRChat's mirror and camera flags set by hand to confirm each mode
    /// applies when it should and not otherwise. This checks the shader in
    /// the editor only; mirrors, cameras and a headset are the real test.
    /// </summary>
    public static class CensorPreview
    {
        private const string Prefab = "Packages/net.wirenook.party-tricks/Prefabs/Wirenook Censor.prefab";
        private const string Avatar = "Packages/net.wirenook.cass/Prefabs/Variants/cass.prefab";

        /// <returns>The folder the pictures were written to.</returns>
        public static string Render()
        {
            var folder = Path.Combine(ContactSheets.OutputFolder, "censor");
            if (Directory.Exists(folder)) Directory.Delete(folder, true);

            var scene = ValidationScene.Open(out _);
            var avatar = (GameObject)PrefabUtility.InstantiatePrefab(AssetDatabase.LoadAssetAtPath<GameObject>(Avatar), scene);
            var instance = (GameObject)PrefabUtility.InstantiatePrefab(AssetDatabase.LoadAssetAtPath<GameObject>(Prefab), scene);
            try
            {
                var animator = avatar.GetComponent<Animator>();
                var volume = instance.GetComponentInChildren<MeshRenderer>(true);
                volume.gameObject.SetActive(true);
                var block = new MaterialPropertyBlock();
                var cameras = ValidationScene.Cameras(scene).ToDictionary(camera => camera.name);

                // The sizes the animator would give the volume, and where the
                // constraint would hold it.
                var head = animator.GetBoneTransform(HumanBodyBones.Head).position + new Vector3(0f, 0.11f, -0.02f);
                var hips = animator.GetBoneTransform(HumanBodyBones.Hips).position + new Vector3(0f, 0.13f, 0f);
                var headSize = new Vector3(0.46f, 0.5f, 0.46f);
                var bodySize = new Vector3(1.15f, 2.4f, 1.15f);

                var index = 0;
                foreach (var (label, camera, body, mode, mirror, photo) in new[]
                         {
                             ("head, always", "Front", false, 0, 0f, 0f),
                             ("head, always", "Face Three-Quarter", false, 0, 0f, 0f),
                             ("head, always", "Left", false, 0, 0f, 0f),
                             ("body, always", "Front", true, 0, 0f, 0f),
                             ("body, always", "Three-Quarter", true, 0, 0f, 0f),
                             ("head, mirrors only, no mirror", "Upper Body", false, 1, 0f, 0f),
                             ("head, mirrors only, in a mirror", "Upper Body", false, 1, 1f, 0f),
                             ("head, photos only, in a mirror", "Upper Body", false, 2, 1f, 0f),
                             ("head, photos only, in a photo", "Upper Body", false, 2, 0f, 3f),
                             ("head, either, in a photo", "Upper Body", false, 3, 0f, 1f),
                             ("head, both, in a photo", "Upper Body", false, 4, 0f, 1f),
                             ("head, both, mirror in a photo", "Upper Body", false, 4, 2f, 1f),
                         })
                {
                    volume.transform.position = body ? hips : head;
                    volume.transform.localScale = body ? bodySize : headSize;
                    block.SetFloat("_Show", 1f);
                    block.SetFloat("_Mode", mode);
                    volume.SetPropertyBlock(block);
                    Shader.SetGlobalFloat("_VRChatMirrorMode", mirror);
                    Shader.SetGlobalFloat("_VRChatCameraMode", photo);
                    ContactSheets.Capture(cameras[camera],
                        Path.Combine(folder, "censor", index++.ToString("000") + " " + label + ".png"));
                }
            }
            finally
            {
                Shader.SetGlobalFloat("_VRChatMirrorMode", 0f);
                Shader.SetGlobalFloat("_VRChatCameraMode", 0f);
                Object.DestroyImmediate(instance);
                Object.DestroyImmediate(avatar);
            }

            ContactSheets.Compose(folder);
            return Path.GetFullPath(folder);
        }
    }
}
