using System;
using System.Linq;
using UnityEditor;
using UnityEngine;
using Wirenook.Cass.Editor;

namespace Wirenook.Bot.Editor
{
    /// <summary>
    /// Import settings for the bot's model and textures, applied in code on
    /// every import like the cass avatar's (CassModelImporter).
    ///
    /// The skeleton is cass's by name: the bot was built on the humanoid bone
    /// names of net.wirenook.cass's Spec/skeleton.json, which is what lets
    /// features that name a bone by path land on either avatar.
    /// </summary>
    public sealed class BotModelImporter : AssetPostprocessor
    {
        /// <summary>Bump to make Unity re-import the model after these rules change.</summary>
        public override uint GetVersion() => 4;

        private string Path => assetPath.Replace('\\', '/');

        private void OnPreprocessTexture()
        {
            if (!Path.StartsWith(BotBuild.Package + "/Textures/", StringComparison.Ordinal)) return;
            var importer = (TextureImporter)assetImporter;
            // Pixel art: every texel a hard square, at any distance. Smaller
            // copies of the atlas would blend neighbouring patches together.
            importer.filterMode = FilterMode.Point;
            importer.mipmapEnabled = false;
            importer.textureCompression = TextureImporterCompression.Uncompressed;
            importer.npotScale = TextureImporterNPOTScale.None;
            importer.wrapMode = TextureWrapMode.Clamp;
            importer.sRGBTexture = !Path.EndsWith("-emission.png", StringComparison.Ordinal);
        }

        private void OnPreprocessModel()
        {
            if (Path != BotBuild.ModelPath) return;
            var importer = (ModelImporter)assetImporter;
            importer.importCameras = false;
            importer.importLights = false;
            importer.importVisibility = false;
            importer.importAnimation = false;
            // The exporter already writes Y-up data with identity transforms (it is cass's exporter).
            importer.bakeAxisConversion = false;
            // VRChat refuses to rank an avatar whose meshes are not readable.
            importer.isReadable = true;
            importer.meshCompression = ModelImporterMeshCompression.Off;
            importer.weldVertices = true;
            importer.importBlendShapes = true;
            importer.importBlendShapeNormals = ModelImporterNormals.None;
            importer.importNormals = ModelImporterNormals.Import;
            importer.importTangents = ModelImporterTangents.CalculateMikk;
            importer.skinWeights = ModelImporterSkinWeights.Standard;
            importer.materialImportMode = ModelImporterMaterialImportMode.ImportStandard;
            importer.materialLocation = ModelImporterMaterialLocation.InPrefab;

            // Which bone is which is not set here but saved with the model's
            // import settings, by BotBuild.Rebuild (see Describe).
        }

        /// <summary>
        /// Tells the model's importer which bone is which, from cass's
        /// skeleton spec, and where every transform rests, from the model as
        /// it is imported now. Unity is not to guess at what the spec
        /// leaves out: left to, it took the projected ears for eyes and
        /// dropped the chest.
        ///
        /// This is saved with the import settings and not set afresh on
        /// each import, as cass's is. Given only names at import, Unity
        /// went on using a guess of its own for this model without saying
        /// so; given names without rest poses in its saved settings, it
        /// refuses to make an avatar at all. Run a rebuild after exporting
        /// the model again, so that the rest poses are the new export's.
        /// </summary>
        public static void Describe(ModelImporter importer, GameObject model)
        {
            var skeleton = CassSpec.Skeleton();
            importer.animationType = ModelImporterAnimationType.Human;
            importer.avatarSetup = ModelImporterAvatarSetup.CreateFromThisModel;
            importer.autoGenerateAvatarMappingIfUnspecified = false;
            var description = importer.humanDescription;
            description.human = skeleton.Humanoid
                .Select(pair => new HumanBone
                {
                    humanName = HumanTrait.BoneName[(int)pair.Key],
                    boneName = pair.Value,
                    limit = new HumanLimit { useDefaultValues = true },
                })
                .ToArray();
            description.skeleton = model.GetComponentsInChildren<Transform>(true)
                .Select(transform => new SkeletonBone
                {
                    // Unity knows the root by the name an instance of the model has.
                    name = transform == model.transform ? model.name + "(Clone)" : transform.name,
                    position = transform.localPosition,
                    rotation = transform.localRotation,
                    scale = transform.localScale,
                })
                .ToArray();
            description.upperArmTwist = 0.5f;
            description.lowerArmTwist = 0.5f;
            description.upperLegTwist = 0.5f;
            description.lowerLegTwist = 0.5f;
            description.armStretch = 0.05f;
            description.legStretch = 0.05f;
            description.feetSpacing = 0f;
            description.hasTranslationDoF = false;
            importer.humanDescription = description;
        }

        private void OnPostprocessModel(GameObject root)
        {
            if (Path != BotBuild.ModelPath) return;
            // Exported materials are only names; each maps to the generated material of the same name.
            foreach (var renderer in root.GetComponentsInChildren<Renderer>(true))
            {
                var materials = renderer.sharedMaterials;
                for (var i = 0; i < materials.Length; i++)
                {
                    if (materials[i] == null) continue;
                    var path = BotBuild.MaterialPath(materials[i].name);
                    context.DependsOnArtifact(path);
                    var generated = AssetDatabase.LoadAssetAtPath<Material>(path);
                    if (generated != null) materials[i] = generated;
                }

                renderer.sharedMaterials = materials;
            }
        }
    }
}
