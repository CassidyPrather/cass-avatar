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
        public override uint GetVersion() => 10;

        private bool Applies => assetPath.Replace('\\', '/').StartsWith(CassSpec.ExportFolder + "/", StringComparison.Ordinal);

        private void OnPreprocessTexture()
        {
            if (assetPath.Replace('\\', '/') != CassMaterials.NormalPath) return;
            var importer = (TextureImporter)assetImporter;
            importer.textureType = TextureImporterType.NormalMap;
            importer.sRGBTexture = false;
            importer.mipmapEnabled = true;
        }

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
            // The face is shaded through a normal map.
            importer.importTangents = ModelImporterTangents.CalculateMikk;
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
            // Unity keeps the bone positions it measured on the first import and
            // warns when a later export no longer matches them. The model is the
            // only authority on where its bones are, so measure afresh every time.
            description.skeleton = Array.Empty<SkeletonBone>();
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

            Screens(root);
        }

        /// <summary>
        /// How much of an eye its screen's picture spans, each way. The iris
        /// is a disc, and partly under the lids; the picture is kept to the
        /// middle of it, where it is always seen whole.
        /// </summary>
        private const float PictureOfEye = 0.5f;

        /// <summary>
        /// Writes, for every vertex of the tile the away screen is drawn on
        /// (<see cref="CassMaterials.ScreenTile"/>, the eyes), where on its
        /// screen it is, into the third UV set: (0,0) to (1,1) across the
        /// picture, measured across each eye as the model stands. The eyes
        /// are several discs laid over one another, each on its own patch
        /// of the atlas, so the atlas cannot say this; where the vertex is
        /// can.
        /// </summary>
        private void Screens(GameObject root)
        {
            context.DependsOnSourceAsset(CassSpec.Package + "/Spec/uv-tiles.json");
            var tile = CassSpec.Tiles().Get(CassMaterials.ScreenTile);
            foreach (var renderer in root.GetComponentsInChildren<SkinnedMeshRenderer>(true))
            {
                var mesh = renderer.sharedMesh;
                if (mesh == null) continue;
                var tiles = new System.Collections.Generic.List<Vector2>();
                mesh.GetUVs(Wirenook.Assets.Editor.ToonMaterial.TileUvChannel, tiles);
                if (tiles.Count != mesh.vertexCount) continue;

                var points = mesh.vertices.Select(vertex => root.transform.InverseTransformPoint(renderer.transform.TransformPoint(vertex))).ToArray();
                var onScreen = Enumerable.Range(0, points.Length)
                    .Where(i => Mathf.FloorToInt(tiles[i].x) == tile.Column && Mathf.FloorToInt(tiles[i].y) == tile.Row).ToList();
                if (onScreen.Count == 0) continue;

                var places = new Vector2[points.Length];
                // One screen for each side of the face; an eye is wholly on one side.
                foreach (var eye in onScreen.GroupBy(i => points[i].x > 0f))
                {
                    var min = new Vector2(eye.Min(i => points[i].x), eye.Min(i => points[i].y));
                    var max = new Vector2(eye.Max(i => points[i].x), eye.Max(i => points[i].y));
                    // A little below the middle: the upper lid covers more of the iris than the lower.
                    var centre = (min + max) / 2f - new Vector2(0f, (max.y - min.y) * 0.08f);
                    var size = (max - min) * PictureOfEye;
                    foreach (var i in eye)
                        places[i] = new Vector2((points[i].x - centre.x) / size.x + 0.5f, (points[i].y - centre.y) / size.y + 0.5f);
                }

                mesh.SetUVs(Wirenook.Assets.Editor.ToonMaterial.ScreenUvChannel, places);
            }
        }
    }
}
