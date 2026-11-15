using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using nadena.dev.ndmf;
using Newtonsoft.Json;
using UnityEditor;
using UnityEngine;
using VRC.SDK3.Avatars.Components;
using VRC.SDKBase.Validation.Performance;
using VRC.SDKBase.Validation.Performance.Stats;
using Wirenook.Assets;
using Wirenook.Assets.Core;
using Wirenook.Assets.Editor;
using Wirenook.Cass.Core;

namespace Wirenook.Cass.Editor
{
    /// <summary>
    /// Entry points for regenerating the avatar's assets and for building a
    /// variant the way an upload would, without uploading it.
    /// </summary>
    public static class CassBuild
    {
        public const string ReportFolder = "dist/build-report";

        /// <summary>The avatar's name; variants are this, or this plus a slug.</summary>
        public const string AvatarName = "cass";

        /// <summary>
        /// Regenerates everything derived from the specs and the Blender
        /// export: materials, FX controller, menus and the prefab chain. Safe
        /// to run at any time; it rewrites generated assets in place.
        /// </summary>
        [MenuItem("Tools/Wirenook/Cass/Rebuild Generated Assets")]
        public static void Rebuild()
        {
            ToonMaterial.EnableClippingCanceller();
            CassMaterials.Rebuild();
            // The model picks up the generated material by name on import.
            AssetDatabase.ImportAsset(CassSpec.ModelPath, ImportAssetOptions.ForceUpdate);
            CassFx.Rebuild();
            CassMenus.Rebuild();
            CassPrefabs.Rebuild();
            AssetDatabase.SaveAssets();
            Debug.Log("[cass] Rebuilt generated assets.");
        }

        public static GameObject LoadVariant(string slug)
        {
            var prefab = AssetDatabase.LoadAssetAtPath<GameObject>(CassPrefabs.VariantPath(slug));
            if (prefab == null)
                throw new FileNotFoundException("No variant \"" + slug + "\"; variants are listed in Spec/variants.json.", CassPrefabs.VariantPath(slug));
            return prefab;
        }

        /// <summary>The tags a variant uploads with: the required ones, then its features' by priority.</summary>
        public static List<string> ComposeTags(GameObject avatar, out List<string> dropped)
        {
            var policy = new UploadPolicy();
            var profile = avatar.GetComponent<AvatarUploadProfile>();
            var candidates = avatar.GetComponentsInChildren<WirenookFeature>(true)
                .Where(feature => !string.IsNullOrWhiteSpace(feature.tag))
                .Select(feature => new FeatureTags.Candidate(feature.tag, feature.tagPriority))
                // Hand-picked tags outrank anything a feature contributes.
                .Concat((profile != null ? profile.extraTags : new List<string>())
                    .Select(tag => new FeatureTags.Candidate(tag, int.MaxValue)));
            return FeatureTags.Compose(policy.RequiredTags, candidates, out dropped);
        }

        /// <summary>
        /// Runs the non-destructive build (Modular Avatar, Avatar Optimizer and
        /// friends) on a throwaway copy of a variant, measures the result the
        /// way VRChat ranks it, and writes dist/build-report/&lt;slug&gt;.json.
        /// </summary>
        /// <returns>The report as JSON.</returns>
        public static string TestBuild(string slug)
        {
            var report = Measure(slug, out var built);
            UnityEngine.Object.DestroyImmediate(built);
            AvatarProcessor.CleanTemporaryAssets();
            return WriteReport(report);
        }

        /// <summary>Builds a variant and leaves the processed copy in the scene, for inspection.</summary>
        public static BuildReport Measure(string slug, out GameObject built)
        {
            var prefab = LoadVariant(slug);
            built = UnityEngine.Object.Instantiate(prefab);
            built.name = slug;

            var features = built.GetComponentsInChildren<WirenookFeature>(true)
                .Select(feature => new BuildReport.Feature
                {
                    id = feature.id,
                    label = feature.label,
                    icon = feature.icon != null ? feature.icon.name : "",
                    summaryIcon = feature.summaryIcon != null ? feature.summaryIcon.name
                        : feature.icon != null ? feature.icon.name : "",
                })
                .ToList();
            var tags = ComposeTags(built, out var dropped);

            AvatarProcessor.ProcessAvatar(built);

            var stats = new AvatarPerformanceStats(false);
            // VRChat ranks Android and iOS avatars on a stricter scale.
            AvatarPerformance.CalculatePerformanceStats(slug, built, stats, WirenookPlatform.IsMobile);

            var renderers = built.GetComponentsInChildren<Renderer>(true);
            var report = new BuildReport
            {
                name = AvatarName,
                variant = slug,
                platform = WirenookPlatform.Name(WirenookPlatform.Current),
                version = PackageVersion(),
                performanceRank = stats.GetPerformanceRatingForCategory(AvatarPerformanceCategory.Overall).ToString(),
                features = features,
                icons = features.Select(feature => feature.summaryIcon).Where(icon => icon.Length > 0).Distinct().ToList(),
                tags = tags.Select(FeatureTags.Normalize).ToList(),
                apiTags = tags,
                droppedTags = dropped,
                triangles = stats.polyCount ?? 0,
                skinnedMeshes = stats.skinnedMeshCount ?? 0,
                meshes = stats.meshCount ?? 0,
                materialSlots = stats.materialCount ?? 0,
                bones = stats.boneCount ?? 0,
                textureMegabytes = stats.textureMegabytes ?? 0f,
                faceTrackingOperations = stats.faceTrackingOperations ?? 0,
                syncedParameterBits = SyncedBits(built),
                renderers = renderers.Select(renderer => renderer.name).ToList(),
            };

            foreach (AvatarPerformanceCategory category in Enum.GetValues(typeof(AvatarPerformanceCategory)))
            {
                if (category == AvatarPerformanceCategory.None || category == AvatarPerformanceCategory.Overall ||
                    category == AvatarPerformanceCategory.AvatarPerformanceCategoryCount) continue;
                var rating = stats.GetPerformanceRatingForCategory(category);
                // Only what costs rank is worth reading; everything else is Excellent.
                if (rating > PerformanceRating.Excellent) report.belowExcellent[category.ToString()] = rating.ToString();
            }

            return report;
        }

        private static int SyncedBits(GameObject avatar)
        {
            var descriptor = avatar.GetComponent<VRCAvatarDescriptor>();
            return descriptor != null && descriptor.expressionParameters != null
                ? descriptor.expressionParameters.CalcTotalCost()
                : 0;
        }

        public static string PackageVersion()
        {
            var manifest = File.ReadAllText(CassSpec.Package + "/package.json");
            return (string)Newtonsoft.Json.Linq.JObject.Parse(manifest)["version"];
        }

        private static string WriteReport(BuildReport report)
        {
            Directory.CreateDirectory(ReportFolder);
            var json = JsonConvert.SerializeObject(report, Formatting.Indented);
            File.WriteAllText(Path.Combine(ReportFolder, report.variant + ".json"), json + "\n");
            return json;
        }
    }

    /// <summary>
    /// What a build of one variant produced. The thumbnail generator reads
    /// <see cref="icons"/> and <see cref="cutout"/> as its manifest, so their
    /// names are part of that tool's input format.
    /// </summary>
    [Serializable]
    public sealed class BuildReport
    {
        [Serializable]
        public sealed class Feature
        {
            public string id;
            public string label;
            public string icon;
            public string summaryIcon;
        }

        public string name;
        public string variant;
        public string platform;
        public string version;
        public string performanceRank;
        public List<Feature> features = new List<Feature>();
        /// <summary>Tags as people read them, without VRChat's prefix.</summary>
        public List<string> tags = new List<string>();

        /// <summary>One icon per group of like features, for the thumbnail.</summary>
        public List<string> icons = new List<string>();
        public string cutout;

        /// <summary>Tags as VRChat stores them.</summary>
        public List<string> apiTags = new List<string>();
        public List<string> droppedTags = new List<string>();
        public int triangles;
        public int skinnedMeshes;
        public int meshes;
        public int materialSlots;
        public int bones;
        public float textureMegabytes;
        public int faceTrackingOperations;
        public int syncedParameterBits;
        public List<string> renderers = new List<string>();

        /// <summary>Performance categories ranked worse than Excellent, with their rank.</summary>
        public Dictionary<string, string> belowExcellent = new Dictionary<string, string>();
    }
}
