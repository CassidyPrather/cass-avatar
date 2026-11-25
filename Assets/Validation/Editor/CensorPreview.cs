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
    ///
    /// The censor pixelates the avatar and nothing else, which the stage's
    /// plain grey could not show either way. A chequered board stands
    /// behind the avatar in every picture, and in the whole-body ones a
    /// plain ball hangs beside the knees, inside the volume: the board's
    /// squares and the ball should stay sharp right up to the avatar's
    /// outline. If they are pixelated too, the stencil is not doing its
    /// work; if nothing is, the avatar's material is not marking it
    /// (rebuild the materials).
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
            var props = new GameObject("Censor Preview Props");
            UnityEngine.SceneManagement.SceneManager.MoveGameObjectToScene(props, scene);
            Texture2D chequers = null;
            Material chequered = null;
            Material plain = null;
            try
            {
                var animator = avatar.GetComponent<Animator>();
                var volume = instance.GetComponentInChildren<MeshRenderer>(true);
                volume.gameObject.SetActive(true);
                var block = new MaterialPropertyBlock();
                var cameras = ValidationScene.Cameras(scene).ToDictionary(camera => camera.name);

                // Squares 12.5 cm across, a few of the censor's blocks each:
                // large enough to stay squares if they are pixelated, small
                // enough that it shows when they are.
                const int squares = 32;
                chequers = new Texture2D(squares, squares, TextureFormat.RGB24, false) { filterMode = FilterMode.Point };
                for (var y = 0; y < squares; y++)
                {
                    for (var x = 0; x < squares; x++)
                        chequers.SetPixel(x, y, (x + y) % 2 == 0 ? new Color(0.85f, 0.85f, 0.8f) : new Color(0.2f, 0.25f, 0.45f));
                }

                chequers.Apply();
                chequered = new Material(Shader.Find("Unlit/Texture")) { mainTexture = chequers };
                plain = new Material(Shader.Find("Unlit/Color")) { color = new Color(0.95f, 0.55f, 0.1f) };

                var board = GameObject.CreatePrimitive(PrimitiveType.Quad);
                Object.DestroyImmediate(board.GetComponent<Collider>());
                board.transform.SetParent(props.transform, false);
                board.transform.localScale = new Vector3(4f, 4f, 1f);
                board.GetComponent<Renderer>().sharedMaterial = chequered;

                var ball = GameObject.CreatePrimitive(PrimitiveType.Sphere);
                Object.DestroyImmediate(ball.GetComponent<Collider>());
                ball.transform.SetParent(props.transform, false);
                ball.transform.localScale = Vector3.one * 0.08f;
                ball.GetComponent<Renderer>().sharedMaterial = plain;

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

                    // The board faces this camera from 1.2 m behind the
                    // avatar. The ball is beside the knees as this camera
                    // sees them: inside the whole-body volume, clear of the
                    // body. The head's volume has no such room to spare.
                    var view = cameras[camera].transform;
                    board.transform.SetPositionAndRotation(hips + view.forward * 1.2f, view.rotation);
                    ball.SetActive(body);
                    ball.transform.position = hips + view.right * 0.38f - Vector3.up * 0.6f;

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
                Object.DestroyImmediate(props);
                Object.DestroyImmediate(chequered);
                Object.DestroyImmediate(plain);
                Object.DestroyImmediate(chequers);
                Object.DestroyImmediate(instance);
                Object.DestroyImmediate(avatar);
            }

            ContactSheets.Compose(folder);
            return Path.GetFullPath(folder);
        }
    }
}
