using System.IO;
using nadena.dev.ndmf;
using UnityEditor;
using UnityEngine;
using Wirenook.Cass.Editor;

namespace Wirenook.Validation.Editor
{
    /// <summary>
    /// Says how large a variant's download would be, without uploading it:
    /// builds the variant as an upload would, packs it into an asset bundle
    /// here and measures the file. It is Unity's own packing with its default
    /// compression (LZMA), not the SDK's build, so read it as a size to
    /// compare variants by; <see cref="BundleProbe"/> is for the bundle the
    /// SDK really made.
    /// </summary>
    public static class BundleSize
    {
        private const string Folder = "Assets/__BundleSize";

        /// <returns>The bundle's size, and where it was written (dist/bundle-size).</returns>
        public static string Measure(string slug)
        {
            CassBuild.Measure(slug, out var built);
            try
            {
                if (!AssetDatabase.IsValidFolder(Folder)) AssetDatabase.CreateFolder("Assets", "__BundleSize");
                var prefab = Folder + "/" + slug + ".prefab";
                PrefabUtility.SaveAsPrefabAsset(built, prefab);
                var output = Path.GetFullPath("dist/bundle-size");
                Directory.CreateDirectory(output);
                var name = slug + ".bundle";
                var manifest = BuildPipeline.BuildAssetBundles(output,
                    new[] { new AssetBundleBuild { assetBundleName = name, assetNames = new[] { prefab } } },
                    BuildAssetBundleOptions.ForceRebuildAssetBundle, EditorUserBuildSettings.activeBuildTarget);
                if (manifest == null) return "Unity did not build the bundle; see the editor log.";
                var file = new FileInfo(Path.Combine(output, name));
                return slug + ": " + (file.Length / 1048576f).ToString("0.00") + " MB (" + file.Length + " bytes), " + file.FullName;
            }
            finally
            {
                Object.DestroyImmediate(built);
                AssetDatabase.DeleteAsset(Folder);
                AvatarProcessor.CleanTemporaryAssets();
            }
        }
    }
}
