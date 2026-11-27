using System;
using System.Linq;
using UnityEditor;
using UnityEngine;
using UnityEngine.Rendering;
using Wirenook.AdventureTools.Editor;
using Wirenook.Assets.Editor;

namespace Wirenook.Meta.Crypt.Editor
{
    /// <summary>
    /// Generates the game master's kit for one module, The Sunken Crypt:
    /// the kit of net.wirenook.adventure-tools with one more tool in its
    /// list (<see cref="CryptTool"/>), as an example of making the kit
    /// over for an adventure.
    ///
    /// The prefab stands in for the plain kit on an avatar that is made
    /// from one carrying it (<c>meta-dm-crypt</c> extends <c>meta-dm</c>):
    /// it names the plain kit as what it replaces, and keeps the plain
    /// kit's parameter names, since those of a feature that is left out of
    /// a build stay declared.
    /// </summary>
    public static class CryptBuild
    {
        public const string Package = "Packages/net.wirenook.meta-avatar";
        private const string Generated = Package + "/Generated/Crypt";
        private const string Prefabs = Package + "/Prefabs";

        public const string KitPrefab = Prefabs + "/Wirenook Game Master (Crypt).prefab";
        public const string KitController = Generated + "/crypt-game-master-fx.controller";
        private const string KitMeshes = Generated + "/crypt-game-master";

        public const string SolidMesh = Generated + "/crypt-solid.asset";
        public const string EffectsMesh = Generated + "/crypt-effects.asset";

        /// <summary>What the crypt's solid shapes are drawn with: the wirenook palette, glowing where the palette glows, with pixel detail laid over (<see cref="CryptDetail"/>).</summary>
        public const string CryptMaterial = Generated + "/crypt.mat";

        public const string RiftWindowMaterial = Generated + "/crypt-rift-window.mat";
        public const string RiftBeyondMaterial = Generated + "/crypt-rift-beyond.mat";
        public const string RiftRimMaterial = Generated + "/crypt-rift-rim.mat";

        public const string FeatureId = "game-master-crypt";

        /// <summary>The stencil bit the rift marks its window with: the one below the three the stage's volumes count in.</summary>
        public const int RiftBit = 0x08;

        /// <summary>The faint colour laid over everything inside a zone of one element.</summary>
        public static string TintMaterial(string element) => Generated + "/crypt-tint-" + element.ToLowerInvariant() + ".mat";

        /// <summary>The whole kit, in menu order: the plain kit's tools, then the crypt.</summary>
        public static System.Collections.Generic.List<IStageTool> Tools()
        {
            var tools = GameMasterBuild.Kit();
            tools.Add(new CryptTool());
            return tools;
        }

        public static GameMasterOptions Options() => new GameMasterOptions
        {
            Tools = Tools(),
            FeatureId = FeatureId,
            FeatureLabel = "Game master's kit for The Sunken Crypt",
            Replaces = new[] { GameMasterBuild.FeatureId },
            Carried = { (GameMasterBuild.RoleplayNoticePrefab, true) },
        };

        [MenuItem("Tools/Wirenook/Meta/Rebuild Crypt")]
        public static void Rebuild()
        {
            AssetFolders.Ensure(Generated);
            AssetFolders.Ensure(Prefabs);
            Stage.Prepare();
            // The kit's own materials, and the roleplay notices it carries, are the plain kit's.
            GameMasterBuild.Materials();
            Materials();
            GameMasterBuild.Build(KitPrefab, KitController, KitMeshes, Options());
            AssetDatabase.SaveAssets();
            Debug.Log("[meta] Rebuilt the game master's kit for the crypt.");
        }

        /// <summary>Checks the generated kit as far as the editor can; see <see cref="CryptCheck"/>.</summary>
        [MenuItem("Tools/Wirenook/Meta/Verify Crypt")]
        public static string Verify()
        {
            var report = CryptCheck.Run();
            Debug.Log("[meta] " + report);
            return report;
        }

        private static T Asset<T>(string path) where T : UnityEngine.Object
        {
            var asset = AssetDatabase.LoadAssetAtPath<T>(path);
            if (asset == null) throw new System.IO.FileNotFoundException("Missing " + path + ".", path);
            return asset;
        }

        /// <summary>The materials the crypt is drawn with. Call before the kit is built.</summary>
        public static void Materials()
        {
            var palette = Asset<Texture2D>(WirenookMaterials.PalettePath);
            var glow = Asset<Texture2D>(WirenookMaterials.EmissionPath);
            var crypt = AssetFolders.LoadOrCreate(CryptMaterial, () => new Material(Shader.Find(ToonMaterial.ShaderName)));
            // Rings and blades are single sheets, seen from both sides.
            ToonMaterial.Configure(crypt, palette, glow, doubleSided: true);
            // Grain and grit in the figure's pixels, over the flat colours.
            CryptDetail.Paint(crypt);
            EditorUtility.SetDirty(crypt);

            var volume = Shader.Find("Wirenook/Stage Volume");
            if (volume == null) throw new InvalidOperationException("The shader Wirenook/Stage Volume is missing; it comes with net.wirenook.adventure-tools.");
            foreach (var element in ElementPiece.Elements)
            {
                var tint = AssetFolders.LoadOrCreate(TintMaterial(element.Name), () => new Material(volume));
                tint.shader = volume;
                tint.SetColor("_Colour", element.Tint);
                tint.SetFloat("_Own", 1f);
                tint.SetFloat("_Strength", 0.09f);
                tint.SetFloat("_Dim", 0f);
                tint.SetFloat("_Rim", 0.12f);
                // The bit the plain zones' tint counts in: where a zone of an element and a marker overlap, neither is tinted.
                tint.SetFloat("_Bit", 0x10);
                tint.SetFloat("_Spare", ToonMaterial.AvatarStencil);
                tint.SetFloat("_SpareWhen", (float)CompareFunction.Never);
                EditorUtility.SetDirty(tint);
            }

            var rift = Shader.Find("Wirenook/Rift");
            if (rift == null) throw new InvalidOperationException("The shader Wirenook/Rift is missing from " + Package + "/Shaders.");
            Material Part(string path, int part, int queue, CompareFunction depth, bool writes, CullMode cull, bool colour,
                CompareFunction stencil, StencilOp then)
            {
                var material = AssetFolders.LoadOrCreate(path, () => new Material(rift));
                material.shader = rift;
                material.SetFloat("_Part", part);
                material.SetFloat("_Bit", RiftBit);
                material.SetFloat("_ZTest", (float)depth);
                material.SetFloat("_ZWrite", writes ? 1f : 0f);
                material.SetFloat("_Cull", (float)cull);
                material.SetFloat("_ColorMask", colour ? 15f : 0f);
                material.SetFloat("_StencilComp", (float)stencil);
                material.SetFloat("_StencilPass", (float)then);
                // Behind the tear's front face and a little above its middle; the far side turns with the tear.
                material.SetVector("_EyeDirection", new Vector4(0.07f, 0.1f, -1f, 0f));
                material.SetFloat(RiftPiece.Heading, 0f);
                material.renderQueue = queue;
                EditorUtility.SetDirty(material);
                return material;
            }

            // In this order: the queues are what make it so.
            var first = (int)RenderQueue.Transparent - 120;
            Part(RiftWindowMaterial, 0, first, CompareFunction.LessEqual, true, CullMode.Back, false, CompareFunction.Always, StencilOp.Replace);
            Part(RiftBeyondMaterial, 1, first + 1, CompareFunction.Greater, false, CullMode.Off, true, CompareFunction.Equal, StencilOp.Keep);
            Part(RiftRimMaterial, 2, first + 2, CompareFunction.LessEqual, false, CullMode.Back, true, CompareFunction.Equal, StencilOp.Zero);
            AssetDatabase.SaveAssets();
        }
    }
}
