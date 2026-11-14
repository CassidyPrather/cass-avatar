using UnityEditor;
using UnityEngine;
using Wirenook.Assets.Editor;

namespace Wirenook.Cass.Editor
{
    /// <summary>Generates the avatar's materials from the palette and the tile layout.</summary>
    public static class CassMaterials
    {
        public const string Folder = CassSpec.Package + "/Materials";
        public const string PalettePath = CassSpec.Package + "/Textures/cass-palette.png";

        /// <summary>Where the generated material for a Blender material name lives.</summary>
        public static string PathFor(string blenderMaterialName)
        {
            return Folder + "/" + blenderMaterialName + ".mat";
        }

        public static Material Body => AssetDatabase.LoadAssetAtPath<Material>(PathFor("cass"));

        public static void Rebuild()
        {
            var palette = AssetDatabase.LoadAssetAtPath<Texture2D>(PalettePath);
            if (palette == null)
                throw new System.IO.FileNotFoundException("Bake the palette first (see README): " + PalettePath);

            var material = AssetFolders.LoadOrCreate(PathFor("cass"), () => new Material(Shader.Find(ToonMaterial.ShaderName)));
            // Double-sided while the model is a placeholder built from single
            // sheets; a closed hand-made mesh should turn this off again.
            ToonMaterial.Configure(material, palette, null, doubleSided: true);

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
