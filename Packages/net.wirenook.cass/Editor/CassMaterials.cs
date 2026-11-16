using UnityEditor;
using UnityEngine;
using Wirenook.Assets.Editor;

namespace Wirenook.Cass.Editor
{
    /// <summary>Generates the avatar's materials from its texture atlas and the tile layout.</summary>
    public static class CassMaterials
    {
        public const string Folder = CassSpec.Package + "/Materials";
        /// <summary>
        /// The one texture the model wears: the painted face and the flat
        /// swatches of the palette, baked together by blender/scripts/build_cass.py.
        /// </summary>
        public const string AtlasPath = CassSpec.Package + "/Textures/cass-atlas.png";

        /// <summary>Where the generated material for a Blender material name lives.</summary>
        public static string PathFor(string blenderMaterialName)
        {
            return Folder + "/" + blenderMaterialName + ".mat";
        }

        public static Material Body => AssetDatabase.LoadAssetAtPath<Material>(PathFor("cass"));

        public static void Rebuild()
        {
            var atlas = AssetDatabase.LoadAssetAtPath<Texture2D>(AtlasPath);
            if (atlas == null)
                throw new System.IO.FileNotFoundException("Build the model first (scripts/blender-build.sh bakes the atlas): " + AtlasPath);

            var material = AssetFolders.LoadOrCreate(PathFor("cass"), () => new Material(Shader.Find(ToonMaterial.ShaderName)));
            // Double-sided: hair strands, the hat's brim and the open ends of
            // garments are single sheets that are seen from both sides.
            ToonMaterial.Configure(material, atlas, null, doubleSided: true);

            // Bake the resting look into the asset, so the avatar is dressed in
            // the editor and on the first frame, before any animator has run.
            var layout = CassSpec.Tiles();
            var shown = layout.Resolve();
            foreach (var tile in layout.Tiles)
                ToonMaterial.SetTileShown(material, tile.Column, tile.Row, shown[tile.Id]);

            AssetDatabase.SaveAssetIfDirty(material);
        }
    }
}
