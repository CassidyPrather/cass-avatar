using System.Collections.Generic;
using System.Linq;
using System.Text;
using nadena.dev.ndmf;
using UnityEditor;
using UnityEditor.Animations;
using UnityEngine;
using VRC.SDK3.Avatars.Components;
using Wirenook.Cass.Editor;

namespace Wirenook.Validation.Editor
{
    /// <summary>
    /// Says what two models have to do with each other, for putting one
    /// avatar's meshes on another's skeleton: what each skinned mesh of a
    /// model holds tile by tile, and which bones two models share by name
    /// and how far apart those stand.
    /// </summary>
    public static class ShuffleProbe
    {
        /// <returns>Each skinned mesh of the model: triangles, blendshapes, materials, and triangles per UV tile of the second UV set.</returns>
        public static string Meshes(string modelPath)
        {
            var model = AssetDatabase.LoadAssetAtPath<GameObject>(modelPath);
            if (model == null) return "No model at " + modelPath;
            var report = new StringBuilder();
            foreach (var renderer in model.GetComponentsInChildren<SkinnedMeshRenderer>(true))
            {
                var mesh = renderer.sharedMesh;
                report.AppendLine(renderer.name + ": " + mesh.triangles.Length / 3 + " triangles, " + mesh.vertexCount + " vertices, " +
                                  mesh.blendShapeCount + " blendshapes, " + renderer.bones.Length + " bones, materials " +
                                  string.Join(", ", renderer.sharedMaterials.Select(material => material == null ? "(none)" : material.name)));
                var tiles = new List<Vector2>();
                mesh.GetUVs(1, tiles);
                if (tiles.Count == 0) continue;
                for (var sub = 0; sub < mesh.subMeshCount; sub++)
                {
                    var counts = new SortedDictionary<string, int>();
                    var triangles = mesh.GetTriangles(sub);
                    for (var i = 0; i < triangles.Length; i += 3)
                    {
                        var uv = tiles[triangles[i]];
                        var key = "(" + Mathf.FloorToInt(uv.x) + "," + Mathf.FloorToInt(uv.y) + ")";
                        counts[key] = counts.TryGetValue(key, out var count) ? count + 1 : 1;
                    }

                    report.AppendLine("  slot " + sub + ": " + string.Join(" ", counts.Select(pair => pair.Key + "=" + pair.Value)));
                }
            }

            return report.ToString();
        }

        /// <returns>
        /// Every layer-control behaviour in a built variant's FX controller whose state's layer name
        /// contains the fragment: which state sets which layer (by the name the index lands on) to what weight.
        /// </returns>
        public static string LayerControls(string slug, string fragment)
        {
            CassBuild.Measure(slug, out var built);
            try
            {
                var fx = (AnimatorController)built.GetComponent<VRCAvatarDescriptor>().baseAnimationLayers
                    .First(layer => layer.type == VRCAvatarDescriptor.AnimLayerType.FX).animatorController;
                var report = new StringBuilder();
                foreach (var layer in fx.layers.Where(layer => layer.name.Contains(fragment)))
                {
                    foreach (var state in layer.stateMachine.states.Select(child => child.state))
                    {
                        foreach (var control in state.behaviours.OfType<VRCAnimatorLayerControl>())
                            report.AppendLine(layer.name + " / " + state.name + ": layer " + control.layer + " (" +
                                              (control.layer < fx.layers.Length ? fx.layers[control.layer].name : "none") + ") to " + control.goalWeight);
                    }
                }

                return report.ToString();
            }
            finally
            {
                Object.DestroyImmediate(built);
                AvatarProcessor.CleanTemporaryAssets();
            }
        }

        /// <returns>The guest model's bones: which the host has by name, and where a few of each stand.</returns>
        public static string Bones(string hostPath, string guestPath)
        {
            var host = AssetDatabase.LoadAssetAtPath<GameObject>(hostPath);
            var guest = AssetDatabase.LoadAssetAtPath<GameObject>(guestPath);
            var hostBones = host.GetComponentsInChildren<Transform>(true).GroupBy(bone => bone.name).ToDictionary(group => group.Key, group => group.First());
            var report = new StringBuilder();
            var shared = new List<string>();
            var alone = new List<string>();
            foreach (var bone in guest.GetComponentsInChildren<Transform>(true))
                (hostBones.ContainsKey(bone.name) ? shared : alone).Add(bone.name);
            report.AppendLine("shared (" + shared.Count + "): " + string.Join(", ", shared));
            report.AppendLine("guest only (" + alone.Count + "): " + string.Join(", ", alone));
            foreach (var name in shared)
            {
                var there = guest.GetComponentsInChildren<Transform>(true).First(bone => bone.name == name);
                report.AppendLine(name + ": host " + hostBones[name].position.ToString("0.000") + " guest " + there.position.ToString("0.000") +
                                  " host scale " + hostBones[name].lossyScale.ToString("0.00") + " guest scale " + there.lossyScale.ToString("0.00"));
            }

            return report.ToString();
        }
    }
}
