using System.IO;
using System.Linq;
using System.Text;
using UnityEngine;

namespace Wirenook.Validation.Editor
{
    /// <summary>
    /// Opens an avatar bundle exactly as the SDK built it (a .vrca file) and
    /// reports what is inside: which vertex data each mesh kept, whether each
    /// shader works, and a picture. Everything else in this project inspects
    /// the avatar before Unity packs it; packing strips vertex channels it
    /// believes no shader reads and compiles the shaders for real, so this is
    /// the only look at what VRChat actually receives.
    ///
    /// The SDK leaves its last build in the temp folder, under
    /// VRChat/&lt;product name&gt;/.
    /// </summary>
    public static class BundleProbe
    {
        private const int Layer = 31;

        /// <summary>Inspects the bundle the SDK built most recently on this machine.</summary>
        public static string InspectLatest()
        {
            var folder = Path.Combine(Path.GetTempPath(), "VRChat");
            var latest = Directory.Exists(folder)
                ? new DirectoryInfo(folder).GetFiles("*.vrca", SearchOption.AllDirectories)
                    .OrderByDescending(file => file.LastWriteTimeUtc).FirstOrDefault()
                : null;
            if (latest == null) return "No built avatar found under " + folder + ". Build or upload one first.";
            return "bundle: " + latest.FullName + " (" + latest.LastWriteTime.ToString("yyyy-MM-dd HH:mm") + ")\n" +
                   Inspect(latest.FullName);
        }

        /// <returns>The report; the picture goes to dist/validation/bundle.png.</returns>
        public static string Inspect(string path)
        {
            var bundle = AssetBundle.LoadFromFile(path);
            if (bundle == null) throw new FileNotFoundException("Unity could not open that as an asset bundle.", path);

            GameObject instance = null;
            GameObject rig = null;
            RenderTexture target = null;
            try
            {
                var prefab = bundle.LoadAllAssets<GameObject>().FirstOrDefault();
                if (prefab == null) return "The bundle holds no prefab.";

                instance = Object.Instantiate(prefab, new Vector3(0f, -500f, 0f), Quaternion.identity);
                var text = new StringBuilder();
                var bounds = new Bounds(instance.transform.position, Vector3.zero);
                foreach (var renderer in instance.GetComponentsInChildren<Renderer>(true))
                {
                    renderer.gameObject.layer = Layer;
                    bounds.Encapsulate(renderer.bounds);

                    var mesh = renderer is SkinnedMeshRenderer skinned
                        ? skinned.sharedMesh
                        : renderer.GetComponent<MeshFilter>()?.sharedMesh;
                    text.AppendLine(renderer.name + ": " + (mesh == null ? "no mesh" :
                        mesh.vertexCount + " vertices, " + mesh.blendShapeCount + " blendshapes, " +
                        string.Join(" ", mesh.GetVertexAttributes().Select(a => a.attribute.ToString()))));

                    foreach (var material in renderer.sharedMaterials)
                    {
                        if (material == null) { text.AppendLine("  (empty material slot)"); continue; }
                        var shader = material.shader;
                        text.AppendLine("  " + material.name + ": " + shader.name +
                                        (shader.isSupported ? "" : " NOT SUPPORTED") +
                                        ", " + material.passCount + " passes");
                    }
                }

                rig = new GameObject("Bundle Probe");
                var light = new GameObject("Light").AddComponent<Light>();
                light.transform.SetParent(rig.transform);
                light.type = LightType.Directional;
                light.transform.rotation = Quaternion.Euler(35f, 200f, 0f);
                light.cullingMask = 1 << Layer;

                var camera = new GameObject("Camera").AddComponent<Camera>();
                camera.transform.SetParent(rig.transform);
                camera.cullingMask = 1 << Layer;
                camera.clearFlags = CameraClearFlags.SolidColor;
                camera.backgroundColor = new Color(0.35f, 0.38f, 0.42f);
                camera.fieldOfView = 30f;
                // Three-quarter view from the front; avatars face +Z.
                var distance = bounds.extents.magnitude / Mathf.Tan(camera.fieldOfView * 0.5f * Mathf.Deg2Rad) * 1.05f;
                camera.transform.position = bounds.center + Quaternion.Euler(8f, 205f, 0f) * Vector3.back * distance;
                camera.transform.LookAt(bounds.center);
                camera.nearClipPlane = 0.05f;
                camera.farClipPlane = distance * 3f;

                target = new RenderTexture(900, 1200, 24, RenderTextureFormat.ARGB32);
                camera.targetTexture = target;
                camera.Render();

                var previous = RenderTexture.active;
                RenderTexture.active = target;
                var picture = new Texture2D(target.width, target.height, TextureFormat.RGB24, false);
                picture.ReadPixels(new Rect(0, 0, target.width, target.height), 0, 0);
                RenderTexture.active = previous;
                camera.targetTexture = null;

                var output = Path.Combine("dist", "validation", "bundle.png");
                Directory.CreateDirectory(Path.GetDirectoryName(output));
                File.WriteAllBytes(output, picture.EncodeToPNG());
                Object.DestroyImmediate(picture);

                text.AppendLine("picture: " + Path.GetFullPath(output));
                return text.ToString();
            }
            finally
            {
                if (target != null) Object.DestroyImmediate(target);
                if (rig != null) Object.DestroyImmediate(rig);
                if (instance != null) Object.DestroyImmediate(instance);
                bundle.Unload(true);
            }
        }
    }
}
