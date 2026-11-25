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

        /// <summary>
        /// The normal map with the same layout: the face's own and the body
        /// base's own, flat elsewhere. Their authors shade them through
        /// these maps; without the face's, the coarse mesh around the mouth
        /// creases in shadow.
        /// </summary>
        public const string NormalPath = CassSpec.Package + "/Textures/cass-atlas-normal.png";

        /// <summary>White where the atlas glows: the palette's glowing swatches, which only some wardrobes wear.</summary>
        public const string EmissionPath = CassSpec.Package + "/Textures/cass-atlas-emission.png";

        /// <summary>lilToon's opaque shader with an outline pass; the editor picks it the same way.</summary>
        private const string OutlineShader = "Hidden/lilToonOutline";

        /// <summary>Where the generated material for a Blender material name lives.</summary>
        public static string PathFor(string blenderMaterialName)
        {
            return Folder + "/" + blenderMaterialName + ".mat";
        }

        public static Material Body => AssetDatabase.LoadAssetAtPath<Material>(PathFor("cass"));

        /// <summary>
        /// What makes the avatar read as drawn rather than rendered, on top
        /// of the shared toon set-up. Each effect is kept gentle: these are
        /// the settings that turn ugly fastest when pushed.
        /// </summary>
        private static void Look(Material material, Texture2D atlas)
        {
            var normal = AssetDatabase.LoadAssetAtPath<Texture2D>(NormalPath);
            material.SetFloat("_UseBumpMap", normal != null ? 1f : 0f);
            if (normal != null)
            {
                material.SetTexture("_BumpMap", normal);
                // Each source's own strength is baked into the map (the face's is halved there).
                material.SetFloat("_BumpScale", 1f);
            }

            // Softer and shorter shadow than the props': a face wants its
            // terminator away from the mouth and nose.
            material.SetFloat("_ShadowBorder", 0.42f);
            material.SetFloat("_ShadowBlur", 0.14f);
            material.SetFloat("_ShadowStrength", 0.85f);

            // Outline, coloured from the surface it surrounds: the texture,
            // darker and a little more saturated, never plain black.
            var outline = Shader.Find(OutlineShader);
            if (outline == null) throw new System.InvalidOperationException("lilToon's outline shader (" + OutlineShader + ") is missing.");
            material.shader = outline;
            material.SetFloat("_UseOutline", 1f);
            material.SetTexture("_OutlineTex", atlas);
            material.SetColor("_OutlineColor", Color.white);
            // Hue shift, saturation, value, gamma applied to the outline texture.
            material.SetVector("_OutlineTexHSVG", new Vector4(0f, 1.25f, 0.5f, 1f));
            material.SetFloat("_OutlineWidth", 0.07f);
            // Keeps the line from swelling when seen up close.
            material.SetFloat("_OutlineFixWidth", 0.6f);
            material.SetFloat("_OutlineEnableLighting", 1f);
            material.SetFloat("_OutlineVertexR2Width", 0f);

            // A thin, soft light on edges that face away from the viewer, and
            // a matching soft darkening just inside them.
            material.SetFloat("_UseRim", 1f);
            material.SetColor("_RimColor", new Color(1f, 0.97f, 0.92f, 0.22f));
            material.SetFloat("_RimBorder", 0.55f);
            material.SetFloat("_RimBlur", 0.45f);
            material.SetFloat("_RimFresnelPower", 4f);
            material.SetFloat("_RimEnableLighting", 1f);
            material.SetFloat("_RimShadowMask", 0.5f);
            material.SetFloat("_RimBackfaceMask", 1f);
            material.SetFloat("_UseRimShade", 1f);
            material.SetColor("_RimShadeColor", new Color(0.72f, 0.62f, 0.72f, 0.3f));
            material.SetFloat("_RimShadeBorder", 0.5f);
            material.SetFloat("_RimShadeBlur", 0.7f);
            material.SetFloat("_RimShadeFresnelPower", 2f);
            EditorUtility.SetDirty(material);
        }

        public static void Rebuild()
        {
            var atlas = AssetDatabase.LoadAssetAtPath<Texture2D>(AtlasPath);
            if (atlas == null)
                throw new System.IO.FileNotFoundException("Build the model first (scripts/blender-build.sh bakes the atlas): " + AtlasPath);

            var material = AssetFolders.LoadOrCreate(PathFor("cass"), () => new Material(Shader.Find(ToonMaterial.ShaderName)));
            // Double-sided: hair strands, the hat's brim and the open ends of
            // garments are single sheets that are seen from both sides.
            // Configure also makes the surface and its outline mark the
            // stencil (ToonMaterial.AvatarStencil), which is how the mosaic
            // censor knows the avatar from the room behind it.
            // The mask is optional: without it nothing glows, as before it existed.
            ToonMaterial.Configure(material, atlas, AssetDatabase.LoadAssetAtPath<Texture2D>(EmissionPath), doubleSided: true);
            Look(material, atlas);

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
