using System;
using System.Linq;
using UnityEditor;
using UnityEngine;

namespace Wirenook.Cass.Editor
{
    /// <summary>
    /// Import settings for everything Blender exports into BlenderExports/.
    /// They are applied in code on every import rather than stored per file,
    /// so re-exporting a model, or adding a new one, can never drift from what
    /// VRChat and the rest of the pipeline need.
    /// </summary>
    public sealed class CassModelImporter : AssetPostprocessor
    {
        /// <summary>Bump to make Unity re-import the models after these rules change.</summary>
        public override uint GetVersion() => 6;

        private bool Applies => assetPath.Replace('\\', '/').StartsWith(CassSpec.ExportFolder + "/", StringComparison.Ordinal);

        private void OnPreprocessModel()
        {
            if (!Applies) return;
            var importer = (ModelImporter)assetImporter;

            importer.importCameras = false;
            importer.importLights = false;
            importer.importVisibility = false;
            importer.importAnimation = false;
            // The exporter already writes Y-up data with identity transforms.
            // Unity's own axis baking would mirror the model along Z instead
            // of X, turning the avatar to face backwards.
            importer.bakeAxisConversion = false;

            // VRChat refuses to rank an avatar whose meshes are not readable.
            importer.isReadable = true;
            importer.meshCompression = ModelImporterMeshCompression.Off;
            importer.weldVertices = true;
            importer.importBlendShapes = true;
            // Shape keys carry no lighting change on a toon face; importing or
            // recalculating their normals makes expressions flicker in shade.
            importer.importBlendShapeNormals = ModelImporterNormals.None;
            importer.importNormals = ModelImporterNormals.Import;
            importer.skinWeights = ModelImporterSkinWeights.Standard;

            importer.materialImportMode = ModelImporterMaterialImportMode.ImportStandard;
            importer.materialLocation = ModelImporterMaterialLocation.InPrefab;

            ConfigureHumanoid(importer);
        }

        private void ConfigureHumanoid(ModelImporter importer)
        {
            var skeleton = CassSpec.Skeleton();
            context.DependsOnSourceAsset(CassSpec.Package + "/Spec/skeleton.json");

            importer.animationType = ModelImporterAnimationType.Human;
            importer.avatarSetup = ModelImporterAvatarSetup.CreateFromThisModel;

            var description = importer.humanDescription;
            description.human = skeleton.Humanoid
                .Select(pair => new HumanBone
                {
                    humanName = HumanTrait.BoneName[(int)pair.Key],
                    boneName = pair.Value,
                    limit = new HumanLimit { useDefaultValues = true },
                })
                .ToArray();
            // Unity's stock muscle settings; an empty description would zero them.
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
            if (!Applies) return;

            // Exported materials are only names; each maps to the generated
            // material of the same name, so the model prefab arrives dressed
            // and nothing downstream has to override material slots.
            foreach (var renderer in root.GetComponentsInChildren<Renderer>(true))
            {
                var materials = renderer.sharedMaterials;
                for (var i = 0; i < materials.Length; i++)
                {
                    if (materials[i] == null) continue;
                    var path = CassMaterials.PathFor(materials[i].name);
                    context.DependsOnArtifact(path);
                    var generated = AssetDatabase.LoadAssetAtPath<Material>(path);
                    if (generated != null) materials[i] = generated;
                }

                renderer.sharedMaterials = materials;
            }
        }
    }
}
