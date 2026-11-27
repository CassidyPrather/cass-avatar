using System;
using System.Collections.Generic;
using System.Linq;
using UnityEditor;
using UnityEngine;
using VRC.SDK3.Avatars.Components;

namespace Wirenook.Cass.Editor
{
    /// <summary>
    /// Poses a built avatar for a picture. No animator runs in the editor, so
    /// a built avatar stands in its T-pose with every prop out at once; this
    /// puts it in a pose with its toggles in a chosen state instead.
    ///
    /// Everything goes through one sampled clip per picture. Sampling a clip
    /// on a humanoid returns whatever the clip does not mention to rest, so a
    /// picture cannot be built up from several samples; the toggle values are
    /// written into a copy of the pose clip and that copy is sampled.
    /// </summary>
    public static class CassPreview
    {
        private const string StandClipPath =
            "Packages/com.vrchat.avatars/Samples/AV3 Demo Assets/Animation/ProxyAnim/proxy_stand_still.anim";

        /// <summary>One prop toggle: the clips that show and hide it.</summary>
        public readonly struct Toggle
        {
            public readonly string Name;
            public readonly AnimationClip On;
            public readonly AnimationClip Off;

            public Toggle(string name, AnimationClip on, AnimationClip off)
            {
                Name = name;
                On = on;
                Off = off;
            }
        }

        /// <summary>VRChat's own standing pose, from the SDK's sample animations.</summary>
        public static AnimationClip StandClip
        {
            get
            {
                var clip = AssetDatabase.LoadAssetAtPath<AnimationClip>(StandClipPath);
                if (clip == null)
                    throw new System.IO.FileNotFoundException("The VRChat SDK's sample animations are missing; reinstall the Avatars SDK.", StandClipPath);
                return clip;
            }
        }

        /// <summary>
        /// The prop toggles in a built avatar's FX controller, recognised by
        /// the clip names the shared pop toggle uses ("X on" and "X off").
        /// </summary>
        public static List<Toggle> Toggles(GameObject built)
        {
            var fx = built.GetComponent<VRCAvatarDescriptor>().baseAnimationLayers
                .FirstOrDefault(layer => layer.type == VRCAvatarDescriptor.AnimLayerType.FX)
                .animatorController;
            var clips = fx != null ? fx.animationClips.Where(clip => clip != null).ToList() : new List<AnimationClip>();
            var toggles = new List<Toggle>();
            foreach (var on in clips.Where(clip => clip.name.EndsWith(" on", StringComparison.Ordinal)).OrderBy(clip => clip.name))
            {
                var name = on.name.Substring(0, on.name.Length - " on".Length);
                var off = clips.FirstOrDefault(clip => clip.name == name + " off");
                // Modular Avatar prefixes the clips it re-roots; that is not part of the feature's name.
                var label = name.StartsWith("rebased ", StringComparison.Ordinal) ? name.Substring("rebased ".Length) : name;
                if (off != null && toggles.All(toggle => toggle.Name != label)) toggles.Add(new Toggle(label, on, off));
            }

            return toggles;
        }

        /// <summary>The property values that put every toggle in its off state.</summary>
        public static Dictionary<EditorCurveBinding, float> AllOff(IEnumerable<Toggle> toggles)
        {
            var held = new Dictionary<EditorCurveBinding, float>();
            foreach (var toggle in toggles) Hold(held, toggle.Off);
            return held;
        }

        /// <summary>Adds a clip's first frame to a set of held values, replacing any it already holds.</summary>
        public static void Hold(Dictionary<EditorCurveBinding, float> held, AnimationClip clip)
        {
            foreach (var binding in AnimationUtility.GetCurveBindings(clip))
                held[binding] = AnimationUtility.GetEditorCurve(clip, binding).Evaluate(0f);
        }

        /// <summary>Samples a pose with the held values applied in the same sample.</summary>
        public static void Sample(GameObject avatar, AnimationClip pose, float time, Dictionary<EditorCurveBinding, float> held)
        {
            var combined = UnityEngine.Object.Instantiate(pose);
            combined.hideFlags = HideFlags.HideAndDontSave;
            foreach (var value in held)
            {
                combined.SetCurve(value.Key.path, value.Key.type, value.Key.propertyName,
                    AnimationCurve.Constant(0f, Mathf.Max(pose.length, 1f / 60f), value.Value));
            }

            // Plain sampling rather than the editor's animation preview mode,
            // which holds everything the avatar's animators bind, the face's
            // blendshapes included, at its resting value.
            var position = avatar.transform.position;
            var rotation = avatar.transform.rotation;
            combined.SampleAnimation(avatar, time);
            UnityEngine.Object.DestroyImmediate(combined);
            // Clips with root motion would walk the avatar away.
            avatar.transform.SetPositionAndRotation(position, rotation);
            FollowTurns(avatar);
        }

        /// <summary>
        /// Turns every object that a rotation constraint makes copy another
        /// outright (one source, full weight, every axis) the way its source
        /// is turned. VRChat's constraints only solve while the game runs,
        /// so in a picture taken here a head that is seen through such a
        /// twin (the meta figure's hood) would otherwise stay facing the way
        /// the neck does whatever the pose. Constraints that take a share of
        /// a turn (twist helpers, the skirt's lift) are left as they rest.
        /// </summary>
        public static void FollowTurns(GameObject avatar)
        {
            foreach (var constraint in avatar.GetComponentsInChildren<VRC.SDK3.Dynamics.Constraint.Components.VRCRotationConstraint>(true))
            {
                if (!constraint.IsActive || constraint.Sources.Count != 1 || constraint.GlobalWeight < 1f) continue;
                var source = constraint.Sources[0];
                if (source.SourceTransform == null || source.Weight < 1f) continue;
                if (!constraint.AffectsRotationX || !constraint.AffectsRotationY || !constraint.AffectsRotationZ) continue;
                var target = constraint.TargetTransform != null ? constraint.TargetTransform : constraint.transform;
                var offset = Quaternion.Euler(constraint.RotationOffset);
                if (constraint.SolveInLocalSpace) target.localRotation = source.SourceTransform.localRotation * offset;
                else target.rotation = source.SourceTransform.rotation * offset;
            }
        }

        /// <summary>
        /// Makes every skinned mesh re-skin on each render. Unity skins once
        /// per frame, and tools that take several pictures do so within one
        /// editor frame; without this each picture after the first would show
        /// the first pose and face again.
        /// </summary>
        public static void SkinEveryRender(GameObject avatar)
        {
            foreach (var skinned in avatar.GetComponentsInChildren<SkinnedMeshRenderer>(true))
                skinned.forceMatrixRecalculationPerRender = true;
        }

        /// <summary>Standing, with every toggle off: the avatar as it loads in.</summary>
        public static void StandAtRest(GameObject built)
        {
            SkinEveryRender(built);
            Sample(built, StandClip, 0f, AllOff(Toggles(built)));
        }
    }
}
