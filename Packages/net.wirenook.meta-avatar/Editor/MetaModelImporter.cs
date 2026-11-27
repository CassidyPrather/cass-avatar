using System;
using System.Linq;
using Newtonsoft.Json.Linq;
using UnityEditor;
using UnityEngine;

namespace Wirenook.Meta.Editor
{
    /// <summary>
    /// Import settings for the meta figure's model and textures, applied in
    /// code on every import like the robot's (BotModelImporter).
    ///
    /// The skeleton is cass's by name, less the eyes and the jaw, which is
    /// what lets features that name a bone by path land on this avatar too.
    /// Which bone is which comes from this package's own Spec/skeleton.json,
    /// written by the model's generator.
    /// </summary>
    public sealed class MetaModelImporter : AssetPostprocessor
    {
        /// <summary>Bump to make Unity re-import the model after these rules change.</summary>
        public override uint GetVersion() => 1;

        private string Path => assetPath.Replace('\\', '/');

        private void OnPreprocessTexture()
        {
            if (!Path.StartsWith(MetaBuild.Package + "/Textures/", StringComparison.Ordinal)) return;
            var importer = (TextureImporter)assetImporter;
            // Pixel art: every texel a hard square, at any distance. Smaller
            // copies of the atlas would blend neighbouring patches together.
            importer.filterMode = FilterMode.Point;
            importer.mipmapEnabled = false;
            importer.textureCompression = TextureImporterCompression.Uncompressed;
            importer.npotScale = TextureImporterNPOTScale.None;
            importer.wrapMode = TextureWrapMode.Clamp;
            // The two masks are amounts, not colours.
            importer.sRGBTexture = !Path.EndsWith("-emission.png", StringComparison.Ordinal) &&
                                   !Path.EndsWith("-tint.png", StringComparison.Ordinal);
        }

        private void OnPreprocessModel()
        {
            if (Path != MetaBuild.ModelPath) return;
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
            importer.importBlendShapes = false;
            importer.importNormals = ModelImporterNormals.Import;
            importer.importTangents = ModelImporterTangents.CalculateMikk;
            importer.skinWeights = ModelImporterSkinWeights.Standard;
            importer.materialImportMode = ModelImporterMaterialImportMode.ImportStandard;
            importer.materialLocation = ModelImporterMaterialLocation.InPrefab;

            // Which bone is which is not set here but saved with the model's
            // import settings, by MetaBuild.Rebuild (see Describe).
        }

        /// <summary>
        /// Tells the model's importer which bone is which, from
        /// Spec/skeleton.json, and where every transform rests, from the
        /// model as it is imported now. Saved with the import settings and
        /// not set afresh on each import, for the reasons the robot's
        /// importer gives. Run a rebuild after exporting the model again,
        /// so that the rest poses are the new export's.
        ///
        /// The humanoid head is <c>Head</c>, which carries nothing;
        /// <c>HeadVisual</c> beside it is no part of the humanoid.
        /// </summary>
        public static void Describe(ModelImporter importer, GameObject model)
        {
            var humanoid = (JObject)MetaBuild.Skeleton()["humanoid"];
            importer.animationType = ModelImporterAnimationType.Human;
            importer.avatarSetup = ModelImporterAvatarSetup.CreateFromThisModel;
            importer.autoGenerateAvatarMappingIfUnspecified = false;
            var description = importer.humanDescription;
            description.human = humanoid.Properties()
                .Select(pair => new HumanBone
                {
                    humanName = HumanTrait.BoneName[(int)Enum.Parse(typeof(HumanBodyBones), pair.Name)],
                    boneName = (string)pair.Value,
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
            if (Path != MetaBuild.ModelPath) return;
            // Exported materials are only names; each maps to the generated material of the same name.
            foreach (var renderer in root.GetComponentsInChildren<Renderer>(true))
            {
                var materials = renderer.sharedMaterials;
                for (var i = 0; i < materials.Length; i++)
                {
                    if (materials[i] == null) continue;
                    var path = MetaBuild.MaterialPath(materials[i].name);
                    context.DependsOnArtifact(path);
                    var generated = AssetDatabase.LoadAssetAtPath<Material>(path);
                    if (generated != null) materials[i] = generated;
                }

                renderer.sharedMaterials = materials;
            }
        }
    }
}
