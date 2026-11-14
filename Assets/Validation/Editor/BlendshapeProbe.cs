using System.IO;
using System.Linq;
using UnityEditor;
using UnityEngine;

namespace Wirenook.Validation.Editor
{
    /// <summary>
    /// Photographs a model's face with one blendshape at full weight, straight
    /// from the imported asset with no build step in between. If a shape shows
    /// here but not in the contact sheets, the build lost it; if it shows in
    /// neither, the import did.
    /// </summary>
    public static class BlendshapeProbe
    {
        /// <returns>What was set, and where the picture was written.</returns>
        public static string Render(string assetPath, string meshObject, string shape)
        {
            var asset = AssetDatabase.LoadAssetAtPath<GameObject>(assetPath);
            if (asset == null) throw new FileNotFoundException("No model at that path.", assetPath);

            var scene = ValidationScene.Open(out _);
            var instance = (GameObject)PrefabUtility.InstantiatePrefab(asset, scene);
            return Shoot(scene, instance, meshObject, shape);
        }

        /// <summary>The same picture of a variant after the full build.</summary>
        public static string RenderBuilt(string slug, string meshObject, string shape)
        {
            var scene = ValidationScene.Open(out _);
            UnityEngine.SceneManagement.SceneManager.SetActiveScene(scene);
            Wirenook.Cass.Editor.CassBuild.Measure(slug, out var built);
            try
            {
                return Shoot(scene, built, meshObject, shape + " (built)", shape);
            }
            finally
            {
                nadena.dev.ndmf.AvatarProcessor.CleanTemporaryAssets();
            }
        }

        private static string Shoot(UnityEngine.SceneManagement.Scene scene, GameObject instance, string meshObject, string label, string shape = null)
        {
            shape = shape ?? label;
            try
            {
                var renderer = instance.GetComponentsInChildren<SkinnedMeshRenderer>(true).First(candidate => candidate.name == meshObject);
                var index = renderer.sharedMesh.GetBlendShapeIndex(shape);
                if (index < 0) return meshObject + " has no blendshape named " + shape;
                renderer.SetBlendShapeWeight(index, 100f);

                var camera = ValidationScene.Cameras(scene).First(candidate => candidate.name == "Face");
                var path = Path.Combine(ContactSheets.OutputFolder, "probe", label + ".png");
                ContactSheets.Capture(camera, path);
                var mesh = renderer.sharedMesh;
                var deltas = new Vector3[mesh.vertexCount];
                mesh.GetBlendShapeFrameVertices(index, mesh.GetBlendShapeFrameCount(index) - 1, deltas, null, null);
                return "set " + shape + " (index " + index + " of " + mesh.blendShapeCount + ") to " + renderer.GetBlendShapeWeight(index) +
                       "; the shape moves " + deltas.Count(delta => delta.sqrMagnitude > 1e-12f) + " of " + mesh.vertexCount +
                       " vertices by up to " + deltas.Max(delta => delta.magnitude).ToString("0.#####") + " m; wrote " + Path.GetFullPath(path);
            }
            finally
            {
                Object.DestroyImmediate(instance);
            }
        }
    }
}
