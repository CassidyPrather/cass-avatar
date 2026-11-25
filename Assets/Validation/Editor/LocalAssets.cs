using System.IO;
using System.Linq;
using UnityEditor;
using Wirenook.Cass.Editor;

namespace Wirenook.Validation.Editor
{
    /// <summary>
    /// Things a variant carries that are not in the repository: bought
    /// assets whose terms do not allow passing them on. Spec/variants.json
    /// names each by the GUID its author shipped it with (`local`), and
    /// that is all the repository holds of it. Whoever holds a licence
    /// imports the author's package themselves; a variant that needs
    /// something absent is skipped by every command, with a note saying so.
    /// </summary>
    public static class LocalAssets
    {
        /// <summary>Which variants need local assets, and whether each asset is in this project.</summary>
        public static string List()
        {
            var lines = CassSpec.Variants().Variants.Where(variant => variant.Local.Count > 0).SelectMany(variant =>
                variant.Local.Select(asset =>
                {
                    var path = AssetDatabase.GUIDToAssetPath(asset.Guid);
                    return variant.Slug + ": " + asset.Credit + " - " + (string.IsNullOrEmpty(path) ? "ABSENT" : "present at " + path);
                })).ToList();
            return lines.Count == 0 ? "No variant needs a local asset." : string.Join("\n", lines);
        }

        /// <summary>
        /// Imports a .unitypackage without the import dialog. For the
        /// author's own package of a local asset; where it lands is the
        /// author's choice of path, which has to be git-ignored.
        /// </summary>
        public static string Import(string packagePath)
        {
            if (!File.Exists(packagePath)) throw new FileNotFoundException("No such package.", packagePath);
            AssetDatabase.ImportPackage(packagePath, false);
            return "Importing " + Path.GetFileName(packagePath) + "; refresh, then run LocalAssets.List.";
        }
    }
}
