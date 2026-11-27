using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using Newtonsoft.Json.Linq;
using UnityEditor;
using UnityEngine;
using VRC.Core;
using VRC.Dynamics;
using VRC.SDK3.Avatars.Components;
using VRC.SDK3.Avatars.ScriptableObjects;
using VRC.SDK3.Dynamics.Constraint.Components;
using VRC.SDK3.Dynamics.PhysBone.Components;
using VRC.SDKBase;
using Wirenook.Assets;
using Wirenook.Assets.Editor;
using Wirenook.Cass.Editor;

namespace Wirenook.Meta.Editor
{
    /// <summary>
    /// Generates the meta figure, a game master in a hooded robe: its
    /// material, its FX controller and its root avatar prefab, from the
    /// model Blender exports (blender/meta/) and the two files its
    /// generator writes beside it (Spec/skeleton.json, Spec/model.json).
    ///
    /// It is a third avatar on the cass pipeline, as the robot is the
    /// second: its variants are listed in net.wirenook.cass's
    /// Spec/variants.json with `root` naming this package's root prefab,
    /// and are given their features, built, checked and uploaded by the
    /// same commands. It is the base of the avatars that run a game and
    /// watch one, so it is kept as light as an avatar gets: one mesh, one
    /// material, no face.
    ///
    /// Two things about it are unusual.
    ///
    /// The humanoid head bone, <c>Head</c>, carries nothing. A player's
    /// voice and nameplate follow that bone, and avatars built on this one
    /// move it away on purpose, for some viewers, to go unheard by them. So
    /// the hood is on <c>HeadVisual</c>, a bone beside it under the neck,
    /// which is made to turn as <c>Head</c> turns and is hidden from its
    /// own wearer the way VRChat hides a head.
    ///
    /// Its trim is painted in the signature colour
    /// (<see cref="WirenookSignature"/>): the wearer turns a dial and the
    /// trim, and whatever the avatar carries that follows the same
    /// convention, takes the colour they chose.
    /// </summary>
    public static class MetaBuild
    {
        public const string Package = "Packages/net.wirenook.meta-avatar";
        public const string ModelPath = Package + "/BlenderExports/meta.fbx";
        public const string RootPath = Package + "/Prefabs/meta-root.prefab";
        private const string Generated = Package + "/Generated";
        private const string FxPath = Generated + "/meta-fx.controller";
        private const string MenuPath = Generated + "/meta-menu.asset";
        private const string ParametersPath = Generated + "/meta-parameters.asset";

        /// <summary>The one mesh. The pipeline looks for a mesh of this name directly under the avatar root.</summary>
        private const string Mesh = "Body";

        /// <summary>The object that holds the physics of the hood's point and the cuffs; left out of mobile builds.</summary>
        public const string SwayHolder = "Sway";

        public static string MaterialPath(string blenderMaterialName) => Package + "/Materials/" + blenderMaterialName + ".mat";

        public static JObject Skeleton() => JObject.Parse(File.ReadAllText(Package + "/Spec/skeleton.json"));

        public static JObject Model() => JObject.Parse(File.ReadAllText(Package + "/Spec/model.json"));

        [MenuItem("Tools/Wirenook/Meta/Rebuild")]
        [AvatarRootBuilder]
        public static void Rebuild()
        {
            Materials();
            // The model picks up the generated material by name on import,
            // and its humanoid description is saved with it (see MetaModelImporter.Describe).
            var importer = AssetImporter.GetAtPath(ModelPath) as ModelImporter
                           ?? throw new FileNotFoundException("Export the model from Blender first (blender/meta/export_meta.py).", ModelPath);
            MetaModelImporter.Describe(importer, AssetDatabase.LoadAssetAtPath<GameObject>(ModelPath));
            importer.SaveAndReimport();
            Fx();
            Menus();
            Root();
            AssetDatabase.SaveAssets();
            Debug.Log("[meta] Rebuilt generated assets.");
        }

        private static Texture2D Texture(JObject model, string which)
        {
            var path = Package + "/" + (string)model["atlas"][which];
            return AssetDatabase.LoadAssetAtPath<Texture2D>(path)
                   ?? throw new FileNotFoundException("Build the model first (blender/meta/build_meta.py writes the textures).", path);
        }

        private static void Materials()
        {
            var model = Model();
            // The shared toon set-up: no brightness floor, the stencil mark,
            // the glitch and the signs. No outline: the pixels are the drawing.
            var solid = AssetFolders.LoadOrCreate(MaterialPath((string)model["material"]), () => new Material(Shader.Find(ToonMaterial.ShaderName)));
            ToonMaterial.Configure(solid, Texture(model, "texture"), Texture(model, "emission"), doubleSided: false);
            // Runes and gems should read at full strength, in the colour they are painted.
            solid.SetColor("_EmissionColor", Color.white);
            WirenookSignature.Paint(solid, Texture(model, "tint"));
            EditorUtility.SetDirty(solid);
            AssetDatabase.SaveAssets();
        }

        /// <summary>
        /// The FX controller, which does nothing: the figure has no face to
        /// move. Layers 1 and 2 are still kept, empty, because that is where
        /// every avatar on this pipeline has its hand expressions, MMD
        /// worlds silence exactly those two, and features are merged in
        /// after them.
        /// </summary>
        private static void Fx()
        {
            var fx = ControllerBuilder.Rebuild(FxPath);
            fx.Layer("Base").State("Idle");
            fx.Layer("Left Hand (unused)").State("Idle");
            fx.Layer("Right Hand (unused)").State("Idle");
            fx.Save();
        }

        /// <summary>An empty menu and parameter list: everything in them comes from features, through Modular Avatar.</summary>
        private static void Menus()
        {
            var parameters = AssetFolders.LoadOrCreate(ParametersPath, ScriptableObject.CreateInstance<VRCExpressionParameters>);
            parameters.parameters = new VRCExpressionParameters.Parameter[0];
            EditorUtility.SetDirty(parameters);
            var menu = AssetFolders.LoadOrCreate(MenuPath, ScriptableObject.CreateInstance<VRCExpressionsMenu>);
            menu.controls = new List<VRCExpressionsMenu.Control>();
            EditorUtility.SetDirty(menu);
        }

        private static void Root()
        {
            var prefab = AssetDatabase.LoadAssetAtPath<GameObject>(ModelPath);
            if (prefab == null) throw new FileNotFoundException("Export the model from Blender first (blender/meta/export_meta.py).", ModelPath);
            if (!File.Exists(RootPath))
            {
                AssetFolders.Ensure(Path.GetDirectoryName(RootPath));
                var instance = (GameObject)PrefabUtility.InstantiatePrefab(prefab);
                try
                {
                    // Saving an unmodified prefab instance as a new asset makes a variant of it.
                    PrefabUtility.SaveAsPrefabAsset(instance, RootPath);
                }
                finally
                {
                    UnityEngine.Object.DestroyImmediate(instance);
                }
            }

            var model = Model();
            var skeleton = Skeleton();
            var root = PrefabUtility.LoadPrefabContents(RootPath);
            try
            {
                var bodyTransform = root.transform.Find(Mesh);
                var body = bodyTransform != null ? bodyTransform.GetComponent<SkinnedMeshRenderer>() : null;
                if (body == null) throw new InvalidOperationException("The model needs a skinned mesh named \"" + Mesh + "\" directly under its root.");

                var descriptor = FeaturePrefab.Ensure<VRCAvatarDescriptor>(root);
                FeaturePrefab.Ensure<PipelineManager>(root);

                // Inside the hood, where eyes would be.
                var view = model["viewPosition"]["unity"];
                descriptor.ViewPosition = new Vector3((float)view[0], (float)view[1], (float)view[2]);

                // No mouth to move. VRChat still writes Viseme and Voice for
                // any feature that wants to answer to the wearer's voice.
                descriptor.lipSync = VRC_AvatarDescriptor.LipSyncStyle.VisemeParameterOnly;
                descriptor.VisemeSkinnedMesh = null;
                descriptor.enableEyeLook = false;

                var controller = AssetDatabase.LoadAssetAtPath<RuntimeAnimatorController>(FxPath);
                descriptor.customizeAnimationLayers = true;
                descriptor.baseAnimationLayers = new[]
                {
                    Layer(VRCAvatarDescriptor.AnimLayerType.Base, null),
                    Layer(VRCAvatarDescriptor.AnimLayerType.Additive, null),
                    Layer(VRCAvatarDescriptor.AnimLayerType.Gesture, null),
                    Layer(VRCAvatarDescriptor.AnimLayerType.Action, null),
                    Layer(VRCAvatarDescriptor.AnimLayerType.FX, controller),
                };
                descriptor.specialAnimationLayers = new[]
                {
                    Layer(VRCAvatarDescriptor.AnimLayerType.Sitting, null),
                    Layer(VRCAvatarDescriptor.AnimLayerType.TPose, null),
                    Layer(VRCAvatarDescriptor.AnimLayerType.IKPose, null),
                };
                descriptor.customExpressions = true;
                descriptor.expressionsMenu = AssetDatabase.LoadAssetAtPath<VRCExpressionsMenu>(MenuPath);
                descriptor.expressionParameters = AssetDatabase.LoadAssetAtPath<VRCExpressionParameters>(ParametersPath);
                descriptor.autoLocomotion = true;
                descriptor.autoFootsteps = true;

                SeenHead(root, skeleton);
                Sway(root, model);

                // One mesh now, and props and signs that join it later need
                // it to be alike in what a build compares; and the optimiser
                // that does the joining.
                CassPrefabs.UnifyRenderers(root, CassSpec.Skeleton());
                CassPrefabs.ConfigureOptimizer(root);
                // There is no face for an MMD world to animate, and keeping the
                // mesh apart for one would cost the rank a second skinned mesh
                // as soon as a prop joined the avatar.
                Optimizer(root, "mmdWorldCompatibility", false);

                PrefabUtility.SaveAsPrefabAsset(root, RootPath);
            }
            finally
            {
                PrefabUtility.UnloadPrefabContents(root);
            }
        }

        /// <summary>
        /// Makes each bone that Spec/skeleton.json calls the seen twin of a
        /// humanoid bone (the hood's, <c>HeadVisual</c>) turn as that bone
        /// turns, and hides it from its wearer's own view, which VRChat
        /// does by itself only for the humanoid head and what hangs off it.
        ///
        /// It copies the turn and not the place: the two rest in one place
        /// under one parent, and the place is exactly what the twin must
        /// not copy when the humanoid bone is sent away.
        /// </summary>
        private static void SeenHead(GameObject root, JObject skeleton)
        {
            var twins = skeleton["extra"].Where(bone => bone["visual"] != null).ToList();
            var chop = FeaturePrefab.Ensure<VRCHeadChop>(root);
            chop.globalScaleFactor = 1f;
            chop.targetBones = twins.Select(twin => new VRCHeadChop.HeadChopBone
            {
                transform = FeaturePrefab.Find(root, (string)twin["name"]),
                scaleFactor = 0f,
                applyCondition = VRCHeadChop.HeadChopBone.ApplyCondition.AlwaysApply,
            }).ToArray();

            foreach (var twin in twins)
            {
                var seen = FeaturePrefab.Find(root, (string)twin["name"]);
                var humanoid = FeaturePrefab.Find(root, (string)twin["visual"]);
                if (seen.parent != humanoid.parent || (seen.localPosition - humanoid.localPosition).sqrMagnitude > 1e-10f)
                    throw new InvalidOperationException(seen.name + " must rest where " + humanoid.name + " does, under the same parent.");
                if (humanoid.childCount > 0)
                    throw new InvalidOperationException(humanoid.name + " has children; everything of the head belongs under " + seen.name + ".");

                var follow = FeaturePrefab.Ensure<VRCRotationConstraint>(seen.gameObject);
                follow.ClearSources();
                follow.AddSource(new VRCConstraintSource { SourceTransform = humanoid, Weight = 1f });
                follow.RotationOffset = Vector3.zero;
                follow.RotationAtRest = seen.localEulerAngles;
                // Siblings: the one's turn under the neck is the other's.
                follow.SolveInLocalSpace = true;
                follow.IsActive = true;
                follow.Locked = true;
                follow.FreezeToWorld = false;

                // Says so to the features: what they attach to the head goes
                // to the twin, and one of them may move the humanoid bone.
                if ((string)twin["visual"] == "Head") FeaturePrefab.Ensure<WirenookFreeHead>(root).visual = seen;
            }
        }

        /// <summary>
        /// The hood's point and the lobe of each cuff hang and lag a little.
        /// The physics sits on objects of its own under one holder that
        /// mobile builds leave out, bones and all else untouched: left
        /// rigid, the figure still looks right, and without them it has no
        /// physics for VRChat to count there.
        /// </summary>
        private static void Sway(GameObject root, JObject model)
        {
            var holder = FeaturePrefab.Child(root, SwayHolder);
            FeaturePrefab.Ensure<WirenookPcOnly>(holder);
            var wanted = new HashSet<string>();
            foreach (var chain in model["sway"])
            {
                var bones = chain["bones"].Select(bone => FeaturePrefab.Find(root, (string)bone)).ToList();
                var kind = (string)chain["kind"];
                wanted.Add(bones[0].name);
                var sway = FeaturePrefab.Ensure<VRCPhysBone>(FeaturePrefab.Child(holder, bones[0].name));
                sway.rootTransform = bones[0];
                // The far end of the last bone: a chain of one bone has nothing to swing without it.
                var end = chain["endUnity"];
                var last = bones[bones.Count - 1];
                sway.endpointPosition = last.InverseTransformPoint(root.transform.TransformPoint(
                    new Vector3((float)end[0], (float)end[1], (float)end[2])));
                sway.integrationType = VRCPhysBoneBase.IntegrationType.Simplified;
                sway.multiChildType = VRCPhysBoneBase.MultiChildType.Ignore;
                sway.limitType = VRCPhysBoneBase.LimitType.Angle;
                sway.allowCollision = VRCPhysBoneBase.AdvancedBool.False;
                // Not for grabbing: whoever runs a game should not be led about by the hood.
                sway.allowGrabbing = VRCPhysBoneBase.AdvancedBool.False;
                sway.allowPosing = VRCPhysBoneBase.AdvancedBool.False;
                sway.isAnimated = false;
                sway.radius = 0.03f;
                switch (kind)
                {
                    case "hood":
                        // Cloth with some body: it trails a turn of the head and settles.
                        sway.pull = 0.35f;
                        sway.spring = 0.3f;
                        sway.stiffness = 0.2f;
                        sway.gravity = 0.15f;
                        sway.gravityFalloff = 1f;
                        sway.immobile = 0.2f;
                        sway.maxAngleX = 30f;
                        break;
                    case "sleeve":
                        // The lobe hangs: it wants to point down whichever way the arm goes.
                        sway.pull = 0.2f;
                        sway.spring = 0.35f;
                        sway.stiffness = 0f;
                        sway.gravity = 0.7f;
                        sway.gravityFalloff = 0f;
                        sway.immobile = 0f;
                        sway.maxAngleX = 75f;
                        break;
                    default:
                        throw new InvalidDataException("Spec/model.json lists a sway chain of kind \"" + kind + "\"; there are hood and sleeve.");
                }
            }

            // A chain the model no longer has.
            foreach (var stale in holder.transform.Cast<Transform>().Where(child => !wanted.Contains(child.name)).ToList())
                UnityEngine.Object.DestroyImmediate(stale.gameObject);
        }

        private static void Optimizer(GameObject root, string setting, bool value)
        {
            var type = Type.GetType("Anatawa12.AvatarOptimizer.TraceAndOptimize, com.anatawa12.avatar-optimizer.runtime");
            var serialized = new SerializedObject(root.GetComponent(type));
            serialized.FindProperty(setting).boolValue = value;
            serialized.ApplyModifiedPropertiesWithoutUndo();
        }

        private static VRCAvatarDescriptor.CustomAnimLayer Layer(VRCAvatarDescriptor.AnimLayerType type, RuntimeAnimatorController controller)
        {
            return new VRCAvatarDescriptor.CustomAnimLayer
            {
                type = type,
                animatorController = controller,
                isDefault = controller == null,
            };
        }
    }
}
