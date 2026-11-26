using System.Collections.Generic;
using System.Linq;
using System.Text;
using UnityEditor;
using UnityEngine;

namespace Wirenook.Validation.Editor
{
    /// <summary>
    /// Lists, for every mesh in a model or prefab, which UV sets it has and
    /// the range each spans. The toon shader reads meaning out of the third
    /// and fourth sets (screens and signs), so a mesh that arrives with
    /// something else in them is drawn wrongly; this is how to find it.
    /// </summary>
    public static class UvProbe
    {
        public static string Channels(string assetPath)
        {
            return Describe(AssetDatabase.LoadAllAssetsAtPath(assetPath).OfType<Mesh>()
                .Concat(AssetDatabase.LoadAssetAtPath<GameObject>(assetPath) is GameObject root ? Of(root) : Enumerable.Empty<Mesh>()));
        }

        /// <summary>The same for a variant as built: what the optimiser left in each set.</summary>
        public static string Built(string slug)
        {
            Wirenook.Cass.Editor.CassBuild.Measure(slug, out var built);
            try
            {
                return Describe(Of(built));
            }
            finally
            {
                Object.DestroyImmediate(built);
                nadena.dev.ndmf.AvatarProcessor.CleanTemporaryAssets();
            }
        }

        private static IEnumerable<Mesh> Of(GameObject root)
        {
            return root.GetComponentsInChildren<SkinnedMeshRenderer>(true).Select(renderer => renderer.sharedMesh)
                .Concat(root.GetComponentsInChildren<MeshFilter>(true).Select(filter => filter.sharedMesh));
        }

        private static string Describe(IEnumerable<Mesh> found)
        {
            var report = new StringBuilder();
            var meshes = found.Where(mesh => mesh != null).Distinct().OrderBy(mesh => mesh.name);
            foreach (var mesh in meshes)
            {
                report.Append(mesh.name + " (" + mesh.vertexCount + " vertices):");
                for (var channel = 0; channel < 8; channel++)
                {
                    var uv = new List<Vector4>();
                    mesh.GetUVs(channel, uv);
                    if (uv.Count == 0) continue;
                    report.Append(" uv" + channel + " x " + uv.Min(v => v.x).ToString("0.###") + ".." + uv.Max(v => v.x).ToString("0.###") +
                                  " y " + uv.Min(v => v.y).ToString("0.###") + ".." + uv.Max(v => v.y).ToString("0.###") + ";");
                }

                report.AppendLine();
            }

            return report.ToString().TrimEnd();
        }
    }
}
