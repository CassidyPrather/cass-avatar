using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEngine;
using VRC.Core;
using VRC.Dynamics;
using VRC.SDK3.Avatars.Components;
using VRC.SDK3.Avatars.ScriptableObjects;
using VRC.SDK3.Dynamics.Constraint.Components;
using VRC.SDK3.Dynamics.PhysBone.Components;
using VRC.SDKBase;
using nadena.dev.modular_avatar.core;
using Wirenook.Assets;
using Wirenook.Assets.Editor;
using Wirenook.Cass.Core;

namespace Wirenook.Cass.Editor
{
    /// <summary>
    /// Builds the prefab chain: the Blender export, the one root avatar prefab
    /// that is a variant of it, and the upload variants layered on top.
    ///
    /// Prefabs are edited in place, never recreated: a variant stores its
    /// overrides against the ids inside its parent, and recreating the parent
    /// would orphan every one of them along with any hand edits.
    /// </summary>
    public static class CassPrefabs
    {
        public const string RootPath = CassSpec.PrefabFolder + "/cass-root.prefab";

        /// <summary>How far the eye bones turn at the edges of the gaze, in degrees.</summary>
        private const float EyeUp = 8f, EyeDown = 10f, EyeSide = 10f;

        /// <summary>
        /// How thick the skirt's chains are, in metres, and how far a bone of one may turn on its
        /// hinge, in degrees. blender/scripts/preview.py lays the skirt over posed legs with the same two.
        /// </summary>
        private const float SkirtRadius = 0.03f, SkirtLimit = 80f;

        /// <summary>A blendshape that moves the irises and nothing else, used to find where the eyes are.</summary>
        private const string IrisShape = "瞳小";

        public static string VariantPath(string slug) => CassSpec.PrefabFolder + "/Variants/" + slug + ".prefab";

        public static void Rebuild()
        {
            EnsureVariantOf(CassSpec.ModelPath, RootPath);
            Edit(RootPath, ConfigureRoot);

            var spec = CassSpec.Variants();
            foreach (var variant in spec.Variants)
            {
                // A variant that carries something kept out of the repository can only
                // be made where that thing is. Elsewhere its prefab is left exactly as
                // it was committed; touching it would drop the reference.
                var absent = variant.Absent();
                if (absent.Count > 0)
                {
                    Debug.Log("[cass] Variant " + variant.Slug + " is left as it is: " + Unavailable(variant, absent));
                    continue;
                }

                var parent = variant.Extends == null ? RootPath : VariantPath(variant.Extends);
                EnsureVariantOf(parent, VariantPath(variant.Slug));
                Edit(VariantPath(variant.Slug), root => ConfigureVariant(root, variant, spec));
            }

            SeparateBlueprints();
        }

        /// <summary>
        /// Gives every variant its own avatar id. A variant that extends
        /// another inherits its parent's blueprint id like any other
        /// property, and uploading it would then replace the parent's avatar
        /// on VRChat. Wherever a variant holds the same id as the one it
        /// extends, the id is cleared, so its first upload reserves a new one.
        /// </summary>
        public static void SeparateBlueprints()
        {
            // The spec lists a variant after the one it extends, so a cleared
            // id is what the next level down is compared against.
            foreach (var variant in CassSpec.Variants().Variants.Where(variant => variant.Extends != null))
            {
                var inherited = BlueprintOf(variant.Extends);
                if (string.IsNullOrEmpty(inherited) || BlueprintOf(variant.Slug) != inherited) continue;
                Edit(VariantPath(variant.Slug), root => root.GetComponent<PipelineManager>().blueprintId = "");
            }
        }

        /// <summary>The avatar id a variant uploads to; empty until its first upload.</summary>
        public static string BlueprintOf(string slug)
        {
            var prefab = AssetDatabase.LoadAssetAtPath<GameObject>(VariantPath(slug));
            var pipeline = prefab != null ? prefab.GetComponent<PipelineManager>() : null;
            return pipeline != null ? pipeline.blueprintId ?? "" : "";
        }

        /// <summary>Another variant holding the same avatar id as this one, or null.</summary>
        public static string SharesBlueprintWith(string slug)
        {
            var blueprint = BlueprintOf(slug);
            if (string.IsNullOrEmpty(blueprint)) return null;
            return CassSpec.Variants().Variants
                .Select(variant => variant.Slug)
                .FirstOrDefault(other => other != slug && BlueprintOf(other) == blueprint);
        }

        private static void EnsureVariantOf(string parentPath, string path)
        {
            if (File.Exists(path)) return;
            var parent = AssetDatabase.LoadAssetAtPath<GameObject>(parentPath);
            if (parent == null) throw new FileNotFoundException("Cannot create " + path + ": its parent prefab is missing.", parentPath);

            AssetFolders.Ensure(Path.GetDirectoryName(path));
            var instance = (GameObject)PrefabUtility.InstantiatePrefab(parent);
            try
            {
                // Saving an unmodified prefab instance as a new asset makes a variant of it.
                PrefabUtility.SaveAsPrefabAsset(instance, path);
            }
            finally
            {
                UnityEngine.Object.DestroyImmediate(instance);
            }
        }

        private static void Edit(string path, Action<GameObject> configure)
        {
            var root = PrefabUtility.LoadPrefabContents(path);
            try
            {
                configure(root);
                PrefabUtility.SaveAsPrefabAsset(root, path);
            }
            finally
            {
                PrefabUtility.UnloadPrefabContents(root);
            }
        }

        private static void ConfigureRoot(GameObject root)
        {
            var shapes = CassSpec.Blendshapes();
            var skeleton = CassSpec.Skeleton();

            // MMD worlds animate "Body" as a path from the avatar root, so the
            // mesh has to be a direct child with exactly that name.
            var bodyTransform = root.transform.Find(shapes.Mesh);
            var body = bodyTransform != null ? bodyTransform.GetComponent<SkinnedMeshRenderer>() : null;
            if (body == null)
                throw new InvalidOperationException("The model needs a skinned mesh named \"" + shapes.Mesh + "\" directly under its root.");
            RequireShapes(body, shapes);

            var descriptor = Ensure<VRCAvatarDescriptor>(root);
            Ensure<PipelineManager>(root);

            var leftEye = Bone(root, skeleton, HumanBodyBones.LeftEye);
            var rightEye = Bone(root, skeleton, HumanBodyBones.RightEye);
            descriptor.ViewPosition = ViewPoint(root, body);

            ConfigureLayers(descriptor);
            ConfigureEyes(descriptor, leftEye, rightEye);
            ConfigureFace(descriptor, body, shapes);

            // Keep the walk cycle while moving in full-body tracking; trackers
            // alone leave the legs sliding stiffly between steps.
            descriptor.autoLocomotion = true;
            descriptor.autoFootsteps = true;

            var tiles = CassSpec.Tiles();
            foreach (var chain in skeleton.ChainRoots())
            {
                var colliders = skeleton.CollidersFor(chain.Physics)
                    .Select(collider => ConfigureCollider(Find(root, collider.Bone), Find(root, collider.To), collider.Radius))
                    .ToList();
                var bone = ConfigurePhysBone(Find(root, chain.Name), chain.Physics, colliders);
                // A chain that carries one garment rests as that garment does, and the
                // FX layer that shows the garment switches it on (CassFx.OutfitLayers).
                // Nobody pays for the physics of cloth they cannot see.
                bone.enabled = chain.Tile == null || tiles.Get(chain.Tile).Shown;
                bone.resetWhenDisabled = chain.Tile != null;
            }

            foreach (var twist in skeleton.TwistBones())
                ConfigureTwist(Find(root, twist.Name), Find(root, twist.TwistSource), twist.TwistWeight);
            foreach (var follow in skeleton.FollowBones())
                ConfigureFollow(Find(root, follow.Name), Find(root, follow.FollowSource), follow.FollowWeight);
            UnifyRenderers(root, skeleton);
            ConfigureOptimizer(root);

            // First among the children, so "Outfit" comes before whatever
            // the variants' features add to the menu.
            var outfit = FeaturePrefab.Child(root, "Outfit Menu");
            outfit.transform.SetSiblingIndex(0);
            Ensure<ModularAvatarMenuInstaller>(outfit).menuToAppend =
                AssetDatabase.LoadAssetAtPath<VRCExpressionsMenu>(CassMenus.OutfitEntryPath);
            Ensure<WirenookPcOnly>(outfit);
        }

        /// <summary>
        /// Gives every mesh the same root bone, bounds and light-probe anchor.
        /// Unity picks these per mesh on import (a hat hangs off the head, boots
        /// off the hips), and renderers that disagree on them cannot be merged
        /// into one at build time. Sharing an anchor also stops the parts of
        /// the avatar from being lit by different probes in the same world.
        /// </summary>
        private static void UnifyRenderers(GameObject root, SkeletonSpec skeleton)
        {
            var renderers = root.GetComponentsInChildren<SkinnedMeshRenderer>(true);
            var hips = Bone(root, skeleton, HumanBodyBones.Hips);
            var chest = Bone(root, skeleton, HumanBodyBones.Chest);

            // The model is in its rest pose here, so the meshes' own bounds
            // describe the whole avatar; a margin covers what posing adds.
            var all = new Bounds(hips.position, Vector3.zero);
            foreach (var renderer in renderers)
            {
                var mesh = renderer.sharedMesh.bounds;
                all.Encapsulate(renderer.transform.TransformPoint(mesh.min));
                all.Encapsulate(renderer.transform.TransformPoint(mesh.max));
            }

            var local = new Bounds(hips.InverseTransformPoint(all.center), all.size * 1.1f);
            foreach (var renderer in renderers)
            {
                renderer.rootBone = hips;
                renderer.localBounds = local;
                renderer.probeAnchor = chest;
                renderer.updateWhenOffscreen = false;
            }
        }

        private static void RequireShapes(SkinnedMeshRenderer body, BlendshapeSpec shapes)
        {
            var mesh = body.sharedMesh;
            var required = shapes.Visemes
                .Concat(shapes.Tracking.Where(key => key.Core).Select(key => key.Key))
                .Concat(shapes.Mmd.Keys);
            var missing = required.Where(name => mesh.GetBlendShapeIndex(name) < 0).ToList();
            if (missing.Count > 0)
            {
                throw new InvalidOperationException(
                    shapes.Mesh + " is missing " + missing.Count + " required blendshape(s): " + string.Join(", ", missing));
            }
        }

        private static void ConfigureLayers(VRCAvatarDescriptor descriptor)
        {
            var fx = AssetDatabase.LoadAssetAtPath<RuntimeAnimatorController>(CassFx.ControllerPath);
            descriptor.customizeAnimationLayers = true;
            descriptor.baseAnimationLayers = new[]
            {
                Layer(VRCAvatarDescriptor.AnimLayerType.Base, null),
                Layer(VRCAvatarDescriptor.AnimLayerType.Additive, null),
                Layer(VRCAvatarDescriptor.AnimLayerType.Gesture, null),
                Layer(VRCAvatarDescriptor.AnimLayerType.Action, null),
                Layer(VRCAvatarDescriptor.AnimLayerType.FX, fx),
            };
            descriptor.specialAnimationLayers = new[]
            {
                Layer(VRCAvatarDescriptor.AnimLayerType.Sitting, null),
                Layer(VRCAvatarDescriptor.AnimLayerType.TPose, null),
                Layer(VRCAvatarDescriptor.AnimLayerType.IKPose, null),
            };

            descriptor.customExpressions = true;
            descriptor.expressionsMenu = AssetDatabase.LoadAssetAtPath<VRCExpressionsMenu>(CassMenus.MenuPath);
            descriptor.expressionParameters = AssetDatabase.LoadAssetAtPath<VRCExpressionParameters>(CassMenus.ParametersPath);
        }

        private static VRCAvatarDescriptor.CustomAnimLayer Layer(VRCAvatarDescriptor.AnimLayerType type,
            RuntimeAnimatorController controller)
        {
            return new VRCAvatarDescriptor.CustomAnimLayer
            {
                type = type,
                animatorController = controller,
                isDefault = controller == null,
            };
        }

        private static void ConfigureEyes(VRCAvatarDescriptor descriptor, Transform leftEye, Transform rightEye)
        {
            descriptor.enableEyeLook = true;
            var eyes = descriptor.customEyeLookSettings;
            eyes.eyeMovement = new VRCAvatarDescriptor.CustomEyeLookSettings.EyeMovements { confidence = 0.5f, excitement = 0.5f };
            eyes.leftEye = leftEye;
            eyes.rightEye = rightEye;
            // The gaze turns the eye bones. The irises are shells over the
            // face that slide across the eye whites, pivoting on bones deep
            // inside the head, so a few degrees carries them a long way; the
            // limits were measured on the model (blender/README.md).
            eyes.eyeGazeMode = VRCAvatarDescriptor.CustomEyeLookSettings.EyeGazeMode.BoneRotation;
            eyes.eyesLookingStraight = Rotations(Quaternion.identity);
            eyes.eyesLookingUp = Rotations(Quaternion.Euler(-EyeUp, 0f, 0f));
            eyes.eyesLookingDown = Rotations(Quaternion.Euler(EyeDown, 0f, 0f));
            eyes.eyesLookingLeft = Rotations(Quaternion.Euler(0f, -EyeSide, 0f));
            eyes.eyesLookingRight = Rotations(Quaternion.Euler(0f, EyeSide, 0f));
            // Eyelids come from the tracker when one is live and from the FX
            // blink layer otherwise; see CassFx.
            eyes.eyelidType = VRCAvatarDescriptor.EyelidType.FaceTracking;
            descriptor.customEyeLookSettings = eyes;
        }

        private static VRCAvatarDescriptor.CustomEyeLookSettings.EyeRotations Rotations(Quaternion rotation)
        {
            return new VRCAvatarDescriptor.CustomEyeLookSettings.EyeRotations { linked = true, left = rotation, right = rotation };
        }

        /// <summary>
        /// Native face tracking. The tracking keys are split into one
        /// blendshape set per face region so the FX controller can hand a
        /// single region to a gesture and leave the tracker the rest. Those
        /// sets start at weight 0 and are raised only while a tracker is live.
        /// Speech visemes get a set of their own that is always on.
        /// </summary>
        private static void ConfigureFace(VRCAvatarDescriptor descriptor, SkinnedMeshRenderer body, BlendshapeSpec shapes)
        {
            descriptor.lipSync = VRC_AvatarDescriptor.LipSyncStyle.VisemeBlendShapeFaceTracking;
            descriptor.VisemeSkinnedMesh = body;
            descriptor.VisemeBlendShapes = shapes.Visemes.ToArray();

            descriptor.enableFaceTracking = true;
            descriptor.useAllTrackingKeys = true;
            descriptor.faceTrackingMeshes = new List<SkinnedMeshRenderer> { body };

            var keyCount = (int)VRCAvatarDescriptor.FaceTrackingKey.Max;
            var sets = new List<VRCAvatarDescriptor.FaceTrackingBlendshapesSet>();
            foreach (var region in GestureLayout.TrackedRegions)
            {
                var set = EmptySet(region, 0f, keyCount, shapes.Visemes.Count);
                foreach (var key in shapes.Tracking.Where(key => key.Region == region))
                {
                    if (body.sharedMesh.GetBlendShapeIndex(key.Key) < 0) continue;
                    if (!Enum.TryParse<VRCAvatarDescriptor.FaceTrackingKey>(key.Key, out var index))
                        throw new InvalidDataException("blendshapes.json: \"" + key.Key + "\" is not a tracking key in this SDK.");
                    set.faceTrackingBlendshapeNames[(int)index] = key.Key;
                }

                sets.Add(set);
            }

            var visemes = EmptySet(CassFx.VisemeSet, 1f, keyCount, shapes.Visemes.Count);
            for (var i = 0; i < shapes.Visemes.Count; i++) visemes.visemeBlendshapeNames[i] = shapes.Visemes[i];
            sets.Add(visemes);

            descriptor.faceTrackingBlendshapesSetList = sets;
            // While a tracker is moving the mouth, let it; speech visemes on
            // top of a tracked mouth double every syllable.
            descriptor.visemeDampenMode = VRCAvatarDescriptor.VisemeDampenMode.DampenVisemes;
            descriptor.visemeDampenAmount = 0.8f;
        }

        private static VRCAvatarDescriptor.FaceTrackingBlendshapesSet EmptySet(string name, float weight, int keys, int visemes)
        {
            return new VRCAvatarDescriptor.FaceTrackingBlendshapesSet
            {
                setName = name,
                setWeight = weight,
                faceTrackingBlendshapeNames = Enumerable.Repeat("", keys).ToArray(),
                faceTrackingBlendshapeMultipliers = Enumerable.Repeat(1f, keys).ToArray(),
                visemeBlendshapeNames = Enumerable.Repeat("", visemes).ToArray(),
                visemeBlendshapeMultipliers = Enumerable.Repeat(1f, visemes).ToArray(),
            };
        }

        /// <summary>
        /// Where the wearer looks out from: between the irises, on the
        /// surface of the eyes. The eye bones cannot say, since they pivot
        /// from inside the head, so the irises are found by the vertices
        /// that the small-pupil blendshape moves.
        /// </summary>
        private static Vector3 ViewPoint(GameObject root, SkinnedMeshRenderer body)
        {
            var mesh = body.sharedMesh;
            var index = mesh.GetBlendShapeIndex(IrisShape);
            if (index < 0) throw new InvalidOperationException(mesh.name + " has no \"" + IrisShape + "\" blendshape to find the irises by.");
            var deltas = new Vector3[mesh.vertexCount];
            mesh.GetBlendShapeFrameVertices(index, 0, deltas, null, null);
            var vertices = mesh.vertices;
            var found = false;
            var bounds = new Bounds();
            for (var i = 0; i < vertices.Length; i++)
            {
                if (deltas[i].sqrMagnitude < 1e-10f) continue;
                var point = root.transform.InverseTransformPoint(body.transform.TransformPoint(vertices[i]));
                if (found) bounds.Encapsulate(point);
                else bounds = new Bounds(point, Vector3.zero);
                found = true;
            }

            if (!found) throw new InvalidOperationException("\"" + IrisShape + "\" moves no vertex of " + mesh.name + ".");
            return new Vector3(0f, bounds.center.y, bounds.max.z);
        }

        /// <summary>
        /// PhysBone settings by the name a chain root carries in skeleton.json:
        /// one component per ear, one for the tail, one for all of the hair
        /// and one for the skirt.
        ///
        /// Integration is Simplified throughout, which reads pull and spring.
        /// Stiffness only acts under Advanced integration; it is set so that
        /// a chain switched over starts from a sensible value.
        /// </summary>
        private static VRCPhysBone ConfigurePhysBone(Transform chainRoot, string physics, List<VRCPhysBoneColliderBase> colliders)
        {
            var bone = Ensure<VRCPhysBone>(chainRoot.gameObject);
            bone.rootTransform = chainRoot;
            bone.integrationType = VRCPhysBoneBase.IntegrationType.Simplified;
            bone.limitType = VRCPhysBoneBase.LimitType.Angle;
            bone.limitRotation = Vector3.zero;
            bone.allowCollision = VRCPhysBoneBase.AdvancedBool.True;
            bone.colliders = colliders;
            bone.multiChildType = VRCPhysBoneBase.MultiChildType.Ignore;
            bone.endpointPosition = Vector3.zero;
            bone.gravityFalloff = 0f;
            bone.isAnimated = false;

            switch (physics)
            {
                case "ears":
                    // Stiff: they stand up, give a little when the head moves and come
                    // straight back, without the wobble a soft ear has. Still grabbable,
                    // posable and stretchy; these are for friends to play with. The
                    // narrow limit also keeps them off the brim of the hat.
                    bone.pull = 0.7f;
                    bone.spring = 0.2f;
                    bone.stiffness = 0.75f;
                    bone.gravity = 0f;
                    bone.immobile = 0.4f;
                    bone.radius = 0.03f;
                    // An ear turns where it meets the head and stays nearly
                    // straight above that: the base may swing this far, the
                    // tip a third of it.
                    bone.maxAngleX = 30f;
                    bone.maxAngleXCurve = AnimationCurve.Linear(0f, 1f, 1f, 0.35f);
                    Touchable(bone, true);
                    bone.grabMovement = 0.6f;
                    bone.maxStretch = 0.5f;
                    bone.maxSquish = 0.3f;
                    bone.stretchMotion = 0.4f;
                    // The gesture poses turn these bones (CassFx.PoseLayer);
                    // physics has to swing around the pose, not the rest.
                    bone.isAnimated = true;
                    break;
                case "tail":
                    // Short and springy; it should flick, not dangle.
                    bone.pull = 0.35f;
                    bone.spring = 0.6f;
                    bone.stiffness = 0.35f;
                    bone.gravity = 0f;
                    bone.immobile = 0f;
                    bone.radius = 0.035f;
                    bone.maxAngleX = 40f;
                    Touchable(bone, true);
                    bone.grabMovement = 0.5f;
                    bone.maxStretch = 0.2f;
                    bone.maxSquish = 0.2f;
                    bone.stretchMotion = 0.2f;
                    bone.isAnimated = true;
                    break;
                case "hair":
                    // The root does not move; each chain under it swings on its own.
                    // Mostly follows the head, with enough lag to read as hair.
                    bone.pull = 0.18f;
                    bone.spring = 0.35f;
                    bone.stiffness = 0.15f;
                    bone.gravity = 0.12f;
                    bone.immobile = 0.35f;
                    bone.radius = 0.025f;
                    bone.maxAngleX = 35f;
                    Touchable(bone, false);
                    bone.maxStretch = 0f;
                    bone.maxSquish = 0f;
                    bone.stretchMotion = 0f;
                    break;
                case "skirt":
                    // Cloth on ten chains of three bones, hung from three roots: one that
                    // stays with the hips, and a lift for each leg that a constraint turns
                    // part of the way with the thigh (ConfigureFollow). Physics moves no
                    // root; each chain swings on a hinge, straight out from the body or
                    // back in, so a leg that lifts a chain cannot shed it to one side. Low pull and
                    // some spring let the hem trail and settle; gravity is felt only away
                    // from rest, so the skirt keeps its flare standing and drapes when
                    // it is lifted or the hips tilt. Part of the wearer's own travel is
                    // left out, or a run would press the whole front against the legs.
                    bone.pull = 0.2f;
                    bone.spring = 0.35f;
                    bone.stiffness = 0.2f;
                    bone.gravity = 0.25f;
                    bone.gravityFalloff = 1f;
                    bone.immobile = 0.35f;
                    bone.radius = SkirtRadius;
                    bone.limitType = VRCPhysBoneBase.LimitType.Hinge;
                    bone.maxAngleX = SkirtLimit;
                    // The chains have no leaf bones, so the last bone of each gets its length from here.
                    bone.endpointPosition = SkirtEndpoint(chainRoot);
                    Touchable(bone, false);
                    bone.maxStretch = 0f;
                    bone.maxSquish = 0f;
                    bone.stretchMotion = 0f;
                    break;
                default:
                    throw new InvalidDataException("skeleton.json: \"" + physics + "\" (on " + chainRoot.name + ") is not a known set of physics settings.");
            }

            return bone;
        }

        /// <summary>
        /// Checks that the skirt's chains are built the way its hinge needs,
        /// and returns the offset that stands in for the leaf bone the model
        /// does not have.
        ///
        /// A hinge limit turns a bone about its own X axis. Blender rolls each
        /// skirt bone so that its Y axis runs down the cloth and its Z axis
        /// points out from the body, which puts X along the cloth and makes
        /// the hinge swing outward. A chain rolled any other way would be
        /// held flat against the leg that pushes it, so that is an error here
        /// and not something to find out in game.
        /// </summary>
        private static Vector3 SkirtEndpoint(Transform skirtRoot)
        {
            var avatar = skirtRoot.root;
            var lengths = new List<float>();
            foreach (Transform first in skirtRoot)
            {
                // Out from the middle of the body, not from the root: a lift sits at a hip joint, to one side.
                var outward = avatar.InverseTransformDirection(first.position - skirtRoot.parent.position);
                outward.y = 0f;
                var faces = avatar.InverseTransformDirection(first.forward);
                if (Vector3.Dot(faces, outward.normalized) < 0.7f)
                    throw new InvalidDataException("Skirt bone " + first.name + " does not have its Z axis pointing out from the body; its hinge would not swing outward.");

                var last = first;
                while (last.childCount > 0)
                {
                    last = last.GetChild(0);
                    if (last.localPosition.normalized.y < 0.95f)
                        throw new InvalidDataException("Skirt bone " + last.name + " is not along its parent's Y axis.");
                }

                lengths.Add(last.localPosition.magnitude);
            }

            if (lengths.Count == 0) throw new InvalidDataException(skirtRoot.name + " has no chains under it.");
            return new Vector3(0f, lengths.Average(), 0f);
        }

        /// <summary>
        /// A capsule along a bone, from its joint to the next one, that the
        /// chains listing it are kept outside of. It pushes nothing else: not
        /// the avatar's other chains, and not other people's.
        /// </summary>
        private static VRCPhysBoneColliderBase ConfigureCollider(Transform bone, Transform next, float radius)
        {
            var collider = Ensure<VRCPhysBoneCollider>(bone.gameObject);
            var along = bone.InverseTransformPoint(next.position);
            collider.rootTransform = bone;
            collider.shapeType = VRCPhysBoneColliderBase.ShapeType.Capsule;
            collider.insideBounds = false;
            collider.bonesAsSpheres = false;
            collider.globalCollision = VRCPhysBoneBase.AdvancedBool.False;
            collider.radius = radius;
            // The height counts the round ends, which are centred on the two joints.
            collider.height = along.magnitude + 2f * radius;
            collider.position = along * 0.5f;
            collider.rotation = Quaternion.FromToRotation(Vector3.up, along);
            return collider;
        }

        private static void Touchable(VRCPhysBone bone, bool touchable)
        {
            var allow = touchable ? VRCPhysBoneBase.AdvancedBool.True : VRCPhysBoneBase.AdvancedBool.False;
            bone.allowGrabbing = allow;
            bone.allowPosing = allow;
        }

        /// <summary>
        /// The body base's arm twist helpers. Each sits on its parent and
        /// carries the skin around the middle of the limb; it follows part
        /// of how far the next joint has turned about the bone's length, so
        /// a turned wrist winds the forearm gradually instead of pinching it
        /// at the joint. The sources and weights are the base's own.
        /// </summary>
        private static void ConfigureTwist(Transform helper, Transform source, float weight)
        {
            var constraint = Ensure<VRCRotationConstraint>(helper.gameObject);
            constraint.ClearSources();
            constraint.AddSource(new VRCConstraintSource { SourceTransform = source, Weight = 1f });
            constraint.GlobalWeight = weight;
            constraint.SolveInLocalSpace = true;
            // Bones are exported with Y along their length.
            constraint.AffectsRotationX = false;
            constraint.AffectsRotationY = true;
            constraint.AffectsRotationZ = false;
            constraint.FreezeToWorld = false;
            constraint.RebakeOffsetsWhenUnfrozen = false;
            // Measures the rest offset between the two bones, then locks and switches on.
            constraint.ActivateConstraint();
        }

        /// <summary>
        /// A bone that is carried part of the way with a limb: the skirt's
        /// lifts, which the chains in front of each thigh hang from. Both
        /// are children of the hips, and the constraint works on their
        /// rotations against the hips, so the helper takes the given share
        /// of however far the limb has turned from rest, on every axis. The
        /// cloth is then where the leg is going before any physics has run.
        /// </summary>
        public static void ConfigureFollow(Transform helper, Transform source, float weight)
        {
            if (helper.parent != source.parent)
                throw new InvalidDataException(helper.name + " follows " + source.name + " but does not share its parent; the constraint measures both against it.");
            var constraint = Ensure<VRCRotationConstraint>(helper.gameObject);
            // Measured from rest: a helper left turned by an earlier weight would bake that turn in.
            constraint.IsActive = false;
            helper.localRotation = RestRotation(helper);
            constraint.ClearSources();
            constraint.AddSource(new VRCConstraintSource { SourceTransform = source, Weight = 1f });
            constraint.GlobalWeight = weight;
            constraint.SolveInLocalSpace = true;
            constraint.AffectsRotationX = true;
            constraint.AffectsRotationY = true;
            constraint.AffectsRotationZ = true;
            constraint.FreezeToWorld = false;
            constraint.RebakeOffsetsWhenUnfrozen = false;
            constraint.ActivateConstraint();
        }

        /// <summary>A bone's rotation in the model as imported.</summary>
        private static Quaternion RestRotation(Transform bone)
        {
            var model = AssetDatabase.LoadAssetAtPath<GameObject>(CassSpec.ModelPath);
            var resting = model.GetComponentsInChildren<Transform>(true).FirstOrDefault(candidate => candidate.name == bone.name);
            return resting != null ? resting.localRotation : bone.localRotation;
        }

        /// <summary>
        /// Avatar Optimizer's Trace and Optimize does the lossless build-time
        /// work: merging the meshes into one, merging identical material
        /// slots, dropping unused blendshapes and bones. Its components are
        /// not public API, so it is added by name and configured as data.
        /// </summary>
        private static void ConfigureOptimizer(GameObject root)
        {
            var type = Type.GetType("Anatawa12.AvatarOptimizer.TraceAndOptimize, com.anatawa12.avatar-optimizer.runtime");
            if (type == null)
                throw new InvalidOperationException("Avatar Optimizer (com.anatawa12.avatar-optimizer) is not installed.");
            var optimizer = root.GetComponent(type) ?? root.AddComponent(type);
            var serialized = new SerializedObject(optimizer);
            // Keeps the mesh name "Body" and the MMD blendshapes through the merge.
            serialized.FindProperty("mmdWorldCompatibility").boolValue = true;
            serialized.ApplyModifiedPropertiesWithoutUndo();
        }

        /// <summary>Why a variant cannot be made, built or uploaded in this project.</summary>
        public static string Unavailable(Variant variant, List<LocalAsset> absent)
        {
            return variant.Slug + " needs " + string.Join(" and ", absent.Select(asset => asset.Credit)) +
                   ", which is not in this project. It is not part of the repository; whoever holds a licence imports it themselves.";
        }

        /// <summary>
        /// Puts a variant's local assets under its root, each once. They are
        /// found by GUID, never by path, and are not Wirenook features: no
        /// marker, no tag, and nothing here looks inside them.
        /// </summary>
        private static void PlaceLocalAssets(GameObject root, Variant variant)
        {
            foreach (var asset in variant.Local)
            {
                var prefab = AssetDatabase.LoadAssetAtPath<GameObject>(AssetDatabase.GUIDToAssetPath(asset.Guid));
                if (prefab == null) throw new InvalidDataException("The asset with GUID " + asset.Guid + " (" + asset.Name + ") is not a prefab.");
                var placed = root.transform.Cast<Transform>().FirstOrDefault(child =>
                    PrefabUtility.GetCorrespondingObjectFromOriginalSource(child.gameObject) == prefab ||
                    PrefabUtility.GetCorrespondingObjectFromSource(child.gameObject) == prefab);
                if (placed == null) placed = ((GameObject)PrefabUtility.InstantiatePrefab(prefab, root.transform)).transform;
                if (asset.AtView)
                {
                    placed.localPosition = root.GetComponent<VRCAvatarDescriptor>().ViewPosition;
                    placed.localRotation = Quaternion.identity;
                }
            }
        }

        private static void ConfigureVariant(GameObject root, Variant variant, VariantSpec spec)
        {
            root.name = variant.Slug;

            var profile = Ensure<AvatarUploadProfile>(root);
            profile.avatarName = variant.Slug;
            profile.description = spec.Description;
            profile.carries = variant.Local.Select(asset => asset.Credit).ToList();
            PlaceLocalAssets(root, variant);

            var lite = root.GetComponent<CassLiteModel>();
            if (variant.Lite) Ensure<CassLiteModel>(root);
            else if (lite != null) UnityEngine.Object.DestroyImmediate(lite, true);

            var wardrobe = root.GetComponent<CassWardrobe>();
            if (!string.IsNullOrEmpty(variant.Wardrobe)) Ensure<CassWardrobe>(root).wardrobe = variant.Wardrobe;
            else if (wardrobe != null) UnityEngine.Object.DestroyImmediate(wardrobe, true);

            // A feature this variant used to list was placed here by an
            // earlier rebuild, and is taken out again. Only what was added
            // at this variant can be: what a parent variant placed is the
            // parent's to remove.
            foreach (var child in root.transform.Cast<Transform>().ToList())
            {
                if (!PrefabUtility.IsAddedGameObjectOverride(child.gameObject)) continue;
                if (child.GetComponentInChildren<Wirenook.Assets.WirenookFeature>(true) == null) continue;
                var source = PrefabUtility.GetCorrespondingObjectFromSource(child.gameObject);
                var placedFrom = source != null ? AssetDatabase.GetAssetPath(source) : null;
                if (string.IsNullOrEmpty(placedFrom) || variant.Features.Contains(placedFrom)) continue;
                Debug.Log("[cass] Variant " + variant.Slug + " no longer lists " + placedFrom + "; removed.");
                UnityEngine.Object.DestroyImmediate(child.gameObject);
            }

            foreach (var path in variant.Features)
            {
                var feature = AssetDatabase.LoadAssetAtPath<GameObject>(path);
                if (feature == null)
                {
                    Debug.LogWarning("[cass] Variant " + variant.Slug + " skips a feature that is not installed: " + path);
                    continue;
                }

                var present = root.transform.Cast<Transform>()
                    .Any(child => PrefabUtility.GetCorrespondingObjectFromOriginalSource(child.gameObject) == feature ||
                                  PrefabUtility.GetCorrespondingObjectFromSource(child.gameObject) == feature);
                if (!present) PrefabUtility.InstantiatePrefab(feature, root.transform);
            }

            // Hand-held props ship without a pose, since rigs disagree on how
            // a hand bone is oriented; fit them to this avatar's hands.
            var skeleton = CassSpec.Skeleton();
            HandGrip.FitAll(root, bone => skeleton.Humanoid.TryGetValue(bone, out var name) ? Find(root, name) : null);
        }

        private static T Ensure<T>(GameObject target) where T : Component
        {
            var component = target.GetComponent<T>();
            return component != null ? component : target.AddComponent<T>();
        }

        private static Transform Bone(GameObject root, SkeletonSpec skeleton, HumanBodyBones bone)
        {
            if (!skeleton.Humanoid.TryGetValue(bone, out var name))
                throw new InvalidDataException("skeleton.json does not map " + bone + ".");
            return Find(root, name);
        }

        private static Transform Find(GameObject root, string name)
        {
            var found = root.GetComponentsInChildren<Transform>(true).FirstOrDefault(transform => transform.name == name);
            if (found == null) throw new InvalidOperationException("The model has no bone named \"" + name + "\".");
            return found;
        }
    }
}
