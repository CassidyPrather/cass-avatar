using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using Newtonsoft.Json.Linq;
using UnityEditor;
using UnityEngine;
using VRC.Core;
using VRC.SDK3.Avatars.Components;
using VRC.SDK3.Avatars.ScriptableObjects;
using VRC.SDK3.Dynamics.PhysBone.Components;
using VRC.Dynamics;
using VRC.SDKBase;
using Wirenook.Assets.Editor;
using Wirenook.Cass.Core;
using Wirenook.Cass.Editor;

namespace Wirenook.Bot.Editor
{
    /// <summary>
    /// Generates the wirenook bot: its materials, its FX controller and its
    /// root avatar prefab, from the model Blender exports and the sprite
    /// face's contract (Spec/face.json).
    ///
    /// The bot is a second avatar in the cass pipeline. It has its own
    /// model, face and animator, and everything else is cass's: variants of
    /// it are listed in net.wirenook.cass's Spec/variants.json (with `root`
    /// naming this package's root prefab) and are given their features,
    /// built, checked and uploaded by the same commands. It exists to be an
    /// avatar that is nothing like cass and still takes cass's drop-in
    /// features unchanged.
    ///
    /// The face is sprites. Each shape key of the model slides one textured
    /// quad out in front of the screen's backing plate and slides the
    /// neutral quad of its layer (eyes or mouth) back behind it; nothing
    /// else on the mesh ever moves. VRChat's visemes and MMD worlds'
    /// animation drive the keys with those names directly, which is the
    /// whole of what lets a sprite face speak and dance.
    /// </summary>
    public static class BotBuild
    {
        public const string Package = "Packages/net.wirenook.bot";
        public const string ModelPath = Package + "/BlenderExports/bot.fbx";
        public const string RootPath = Package + "/Prefabs/bot-root.prefab";
        private const string Generated = Package + "/Generated";
        private const string FxPath = Generated + "/bot-fx.controller";
        private const string MenuPath = Generated + "/bot-menu.asset";
        private const string ParametersPath = Generated + "/bot-parameters.asset";

        /// <summary>The mesh the face is on. MMD worlds animate a mesh of this name directly under the avatar root.</summary>
        private const string Mesh = "Body";

        /// <summary>Seconds between blinks, and how long the eyes stay shut.</summary>
        private const float BlinkEvery = 4.2f, BlinkFor = 0.12f;

        public static string MaterialPath(string blenderMaterialName) => Package + "/Materials/" + blenderMaterialName + ".mat";

        [MenuItem("Tools/Wirenook/Bot/Rebuild")]
        [AvatarRootBuilder]
        public static void Rebuild()
        {
            Materials();
            // The model picks up the generated materials by name on import,
            // and its humanoid description is saved with it (see BotModelImporter.Describe).
            var importer = AssetImporter.GetAtPath(ModelPath) as ModelImporter
                           ?? throw new FileNotFoundException("Export the model from Blender first (blender/bot/export_bot.py).", ModelPath);
            BotModelImporter.Describe(importer, AssetDatabase.LoadAssetAtPath<GameObject>(ModelPath));
            importer.SaveAndReimport();
            Fx();
            Menus();
            Root();
            AssetDatabase.SaveAssets();
            Debug.Log("[bot] Rebuilt generated assets.");
        }

        private static JObject Face() => JObject.Parse(File.ReadAllText(Package + "/Spec/face.json"));

        private static void Materials()
        {
            var atlas = AssetDatabase.LoadAssetAtPath<Texture2D>(Package + "/Textures/bot-atlas.png");
            var emission = AssetDatabase.LoadAssetAtPath<Texture2D>(Package + "/Textures/bot-atlas-emission.png");
            if (atlas == null) throw new FileNotFoundException("Build the model first (blender/bot/build_bot.py writes the atlas).", Package + "/Textures/bot-atlas.png");

            // The shared toon set-up: no brightness floor, the stencil mark,
            // the glitch and the signs. No outline: the pixels are the drawing.
            var solid = AssetFolders.LoadOrCreate(MaterialPath("bot"), () => new Material(Shader.Find(ToonMaterial.ShaderName)));
            ToonMaterial.Configure(solid, atlas, emission, doubleSided: false);
            // A screen and status lights should read at full strength.
            solid.SetColor("_EmissionColor", Color.white);
            EditorUtility.SetDirty(solid);

            // Light that adds to what is behind it, for the projected ears
            // and tail. Unlit, and it leaves the stencil alone: a hologram
            // is not part of the figure.
            var holo = AssetFolders.LoadOrCreate(MaterialPath("bot-holo"), () => new Material(Shader.Find(ToonMaterial.ShaderName)));
            var transparent = Shader.Find("Hidden/lilToonTransparent");
            if (transparent == null) throw new FileNotFoundException("lilToon's transparent shader is missing; is lilToon installed?");
            holo.shader = transparent;
            holo.SetTexture("_MainTex", atlas);
            holo.SetColor("_Color", new Color(1f, 1f, 1f, 0.7f));
            holo.SetFloat("_Cull", 0f);
            holo.SetFloat("_AsUnlit", 1f);
            holo.SetFloat("_LightMinLimit", 0f);
            holo.SetFloat("_UseShadow", 0f);
            holo.SetFloat("_SrcBlend", (float)UnityEngine.Rendering.BlendMode.SrcAlpha);
            holo.SetFloat("_DstBlend", (float)UnityEngine.Rendering.BlendMode.One);
            holo.SetFloat("_ZWrite", 0f);
            holo.SetFloat("_UDIMDiscardCompile", 1f);
            holo.SetFloat("_UDIMDiscardUV", ToonMaterial.TileUvChannel);
            holo.renderQueue = (int)UnityEngine.Rendering.RenderQueue.Transparent;
            EditorUtility.SetDirty(holo);
            AssetDatabase.SaveAssets();
        }

        /// <summary>
        /// The FX controller. Layers 1 and 2 are the ones MMD worlds
        /// silence, so the hands' expressions are there and nothing else is.
        ///
        /// Both hands are read by the first of them, which keeps the rule
        /// about whose expression shows in one place: the right hand wins
        /// while it holds an expression; otherwise the left does.
        /// </summary>
        private static void Fx()
        {
            var gestures = CassSpec.Gestures();
            var map = JObject.Parse(File.ReadAllText(Package + "/Spec/expressions.json"))["expressions"];
            var keys = new HashSet<string>(Face()["shapeKeys"].Select(key => (string)key["name"]));

            var fx = ControllerBuilder.Rebuild(FxPath);
            fx.Int("GestureLeft").Int("GestureRight").Bool(WirenookSignals.Afk).Bool(WirenookSignals.Away);
            fx.Layer("Base").State("Idle");

            AnimationClip Expression(string id) => fx.Clip("expression " + id, clip =>
            {
                var sprites = map[id] ?? throw new InvalidDataException("Spec/expressions.json has no entry for cass's expression \"" + id + "\".");
                foreach (var layer in new[] { "eyes", "mouth" })
                {
                    var sprite = (string)sprites[layer];
                    if (sprite == null) continue;
                    var key = layer + "." + sprite;
                    if (!keys.Contains(key)) throw new InvalidDataException("Spec/expressions.json names " + key + ", which the model's face has no key for.");
                    clip.Blendshape(Mesh, key, 100f);
                }

                if ((bool?)sprites["blush"] ?? false) clip.Blendshape(Mesh, "face.blush", 100f);
                if (clip.Clip.empty) clip.Hold(0.1f);
            });

            var right = gestures.For(Hand.Right).OrderBy(pair => pair.Key).ToList();
            var left = gestures.For(Hand.Left).OrderBy(pair => pair.Key).ToList();
            var hands = fx.Layer("Left Hand, Right Hand");
            var neutral = hands.State("Neutral");
            // A sprite is there or it is not; nothing here fades.
            var rest = hands.Any(neutral);
            foreach (var pair in right) rest.NotEqual("GestureRight", pair.Key);
            foreach (var pair in left) rest.NotEqual("GestureLeft", pair.Key);
            foreach (var pair in right)
            {
                var state = hands.State("Right " + gestures.Expressions[pair.Value].Label, Expression(pair.Value));
                hands.Any(state).Equal("GestureRight", pair.Key);
            }

            foreach (var pair in left)
            {
                var state = hands.State("Left " + gestures.Expressions[pair.Value].Label, Expression(pair.Value));
                var when = hands.Any(state).Equal("GestureLeft", pair.Key);
                foreach (var other in right) when.NotEqual("GestureRight", other.Key);
            }

            // The second of the two layers MMD worlds silence. It is kept,
            // empty, so that nothing else lands in that place.
            fx.Layer("Right Hand (spare)").State("Idle");

            // A machine's blink: on the clock. It uses the eyelid keys, not
            // the MMD blink, so it lives outside the two silenced layers.
            var blink = fx.Layer("Blink");
            var shut = new AnimationCurve(new Keyframe(0f, 0f), new Keyframe(BlinkEvery - BlinkFor, 100f), new Keyframe(BlinkEvery, 0f));
            for (var key = 0; key < shut.length; key++)
            {
                AnimationUtility.SetKeyLeftTangentMode(shut, key, AnimationUtility.TangentMode.Constant);
                AnimationUtility.SetKeyRightTangentMode(shut, key, AnimationUtility.TangentMode.Constant);
            }

            var blinking = blink.State("Blinking", fx.Clip("blink", clip =>
                clip.Blendshape(Mesh, "EyeClosedLeft", shut).Blendshape(Mesh, "EyeClosedRight", shut).Loop()));
            var staring = blink.State("Away", fx.Clip("blink away", clip =>
                clip.Blendshape(Mesh, "EyeClosedLeft", 0f).Blendshape(Mesh, "EyeClosedRight", 0f)));
            blinking.To(staring).IfTrue(WirenookSignals.Afk).Or().IfTrue(WirenookSignals.Away);
            staring.To(blinking).IfFalse(WirenookSignals.Afk).IfFalse(WirenookSignals.Away);

            // Away, the whole screen is the error screen. The away feature
            // (net.wirenook.party-tricks) does the rest: this is the one
            // part of being away that is the avatar's own to draw.
            var away = fx.Layer("Away Face");
            var here = away.State("Here", fx.Clip("face here", clip => clip.Blendshape(Mesh, "face.bluescreen", 0f)));
            var gone = away.State("Away", fx.Clip("face away", clip => clip.Blendshape(Mesh, "face.bluescreen", 100f)));
            here.To(gone).IfTrue(WirenookSignals.Afk).Or().IfTrue(WirenookSignals.Away);
            gone.To(here).IfFalse(WirenookSignals.Afk).IfFalse(WirenookSignals.Away);
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
            var model = AssetDatabase.LoadAssetAtPath<GameObject>(ModelPath);
            if (model == null) throw new FileNotFoundException("Export the model from Blender first (blender/bot/export_bot.py).", ModelPath);
            if (!File.Exists(RootPath))
            {
                AssetFolders.Ensure(Path.GetDirectoryName(RootPath));
                var instance = (GameObject)PrefabUtility.InstantiatePrefab(model);
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

            var face = Face();
            var root = PrefabUtility.LoadPrefabContents(RootPath);
            try
            {
                var bodyTransform = root.transform.Find(Mesh);
                var body = bodyTransform != null ? bodyTransform.GetComponent<SkinnedMeshRenderer>() : null;
                if (body == null) throw new InvalidOperationException("The model needs a skinned mesh named \"" + Mesh + "\" directly under its root.");
                var missing = face["shapeKeys"].Select(key => (string)key["name"]).Where(name => body.sharedMesh.GetBlendShapeIndex(name) < 0).ToList();
                if (missing.Count > 0)
                    throw new InvalidOperationException(Mesh + " is missing " + missing.Count + " shape key(s) that face.json lists: " + string.Join(", ", missing.Take(8)));

                var descriptor = FeaturePrefab.Ensure<VRCAvatarDescriptor>(root);
                FeaturePrefab.Ensure<PipelineManager>(root);

                // Between the eyes, a little behind the screen: the view should
                // not swing out in front of the head when it turns.
                var view = face["viewPosition"]["unity"];
                descriptor.ViewPosition = new Vector3((float)view[0], (float)view[1], (float)view[2] - 0.05f);

                descriptor.lipSync = VRC_AvatarDescriptor.LipSyncStyle.VisemeBlendShape;
                descriptor.VisemeSkinnedMesh = body;
                descriptor.VisemeBlendShapes = face["shapeKeys"].Where(key => (string)key["group"] == "viseme").Select(key => (string)key["name"]).ToArray();
                if (descriptor.VisemeBlendShapes.Length != 15)
                    throw new InvalidDataException("face.json should list VRChat's fifteen visemes, in its order; it lists " + descriptor.VisemeBlendShapes.Length + ".");
                // Its eyes are pictures on a screen; there is nothing to turn.
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

                // The projected ears and tail sway a little: light, but light that lags.
                foreach (var chain in new[] { "Ear.L", "Ear.R", "Tail" })
                {
                    var bone = root.GetComponentsInChildren<Transform>(true).FirstOrDefault(transform => transform.name == chain)
                               ?? throw new InvalidOperationException("The model has no bone named \"" + chain + "\".");
                    var sway = FeaturePrefab.Ensure<VRCPhysBone>(bone.gameObject);
                    sway.rootTransform = bone;
                    sway.integrationType = VRCPhysBoneBase.IntegrationType.Simplified;
                    sway.pull = 0.45f;
                    sway.spring = 0.35f;
                    sway.gravity = 0f;
                    sway.immobile = 0.3f;
                    sway.limitType = VRCPhysBoneBase.LimitType.Angle;
                    sway.maxAngleX = 28f;
                    sway.radius = 0.03f;
                    sway.allowCollision = VRCPhysBoneBase.AdvancedBool.False;
                    sway.allowGrabbing = VRCPhysBoneBase.AdvancedBool.True;
                    sway.allowPosing = VRCPhysBoneBase.AdvancedBool.True;
                }

                // The face and the shell alike in what a build compares, so
                // that props and signs can join the shell, and the optimiser
                // that does the joining.
                CassPrefabs.UnifyRenderers(root, CassSpec.Skeleton());
                CassPrefabs.ConfigureOptimizer(root);

                PrefabUtility.SaveAsPrefabAsset(root, RootPath);
            }
            finally
            {
                PrefabUtility.UnloadPrefabContents(root);
            }
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
