using System.Collections.Generic;
using System.Linq;
using System.Text;
using UnityEditor;
using UnityEngine;
using Wirenook.Assets.Editor;
using Wirenook.Cass.Editor;

namespace Wirenook.Validation.Editor
{
    /// <summary>
    /// Lists what the model has in one UV discard tile: each connected patch
    /// of faces, with the mesh it is in, which side of the figure it is on,
    /// how many triangles, its size in the world and where it lies on the
    /// main UV set. For finding out what a tile really holds before code
    /// relies on it.
    /// </summary>
    public static class TileProbe
    {
        public static string Islands(string tileId)
        {
            var tile = CassSpec.Tiles().Get(tileId);
            var model = AssetDatabase.LoadAssetAtPath<GameObject>(CassSpec.ModelPath);
            var report = new StringBuilder();
            foreach (var renderer in model.GetComponentsInChildren<SkinnedMeshRenderer>(true))
            {
                var mesh = renderer.sharedMesh;
                var uv = new List<Vector2>();
                var tiles = new List<Vector2>();
                mesh.GetUVs(0, uv);
                mesh.GetUVs(ToonMaterial.TileUvChannel, tiles);
                if (tiles.Count != mesh.vertexCount) continue;
                var vertices = mesh.vertices;
                var triangles = mesh.triangles;
                var parent = Enumerable.Range(0, vertices.Length).ToArray();
                int Find(int a)
                {
                    while (parent[a] != a) a = parent[a] = parent[parent[a]];
                    return a;
                }

                var inTile = new List<int>();
                for (var t = 0; t < triangles.Length; t += 3)
                {
                    var a = triangles[t];
                    if (Mathf.FloorToInt(tiles[a].x) != tile.Column || Mathf.FloorToInt(tiles[a].y) != tile.Row) continue;
                    inTile.Add(t);
                    parent[Find(triangles[t + 1])] = Find(a);
                    parent[Find(triangles[t + 2])] = Find(a);
                }

                foreach (var island in inTile.GroupBy(t => Find(triangles[t])))
                {
                    var corners = island.SelectMany(t => new[] { triangles[t], triangles[t + 1], triangles[t + 2] }).Distinct().ToList();
                    var points = corners.Select(i => model.transform.InverseTransformPoint(renderer.transform.TransformPoint(vertices[i]))).ToList();
                    var min = new Vector2(corners.Min(i => uv[i].x), corners.Min(i => uv[i].y));
                    var max = new Vector2(corners.Max(i => uv[i].x), corners.Max(i => uv[i].y));
                    var low = new Vector3(points.Min(p => p.x), points.Min(p => p.y), points.Min(p => p.z));
                    var high = new Vector3(points.Max(p => p.x), points.Max(p => p.y), points.Max(p => p.z));
                    report.AppendLine(renderer.name + ": " + island.Count() + " triangles, x " + low.x.ToString("0.000") + ".." + high.x.ToString("0.000") +
                                      ", y " + low.y.ToString("0.000") + ".." + high.y.ToString("0.000") + ", z " + low.z.ToString("0.000") + ".." + high.z.ToString("0.000") +
                                      ", uv " + min.ToString("0.000") + ".." + max.ToString("0.000"));
                }
            }

            return report.ToString().TrimEnd();
        }
    }
}
