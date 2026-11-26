using System;
using System.Linq;
using System.Text;
using UnityEditor;
using UnityEngine;

namespace Wirenook.Validation.Editor
{
    /// <summary>
    /// Says what Unity made of a model's humanoid rig: whether its avatar is
    /// valid and human, which humanoid bones it could not find, and anything
    /// the importer had to say. VRChat's validation only reports the first
    /// thing it misses.
    /// </summary>
    public static class RigProbe
    {
        public static string Human(string modelPath)
        {
            var model = AssetDatabase.LoadAssetAtPath<GameObject>(modelPath);
            if (model == null) return "No model at " + modelPath;
            var report = new StringBuilder();
            var avatar = AssetDatabase.LoadAllAssetsAtPath(modelPath).OfType<Avatar>().FirstOrDefault();
            report.AppendLine("avatar: " + (avatar == null ? "none" : (avatar.isValid ? "valid" : "INVALID") + ", " + (avatar.isHuman ? "human" : "NOT HUMAN")));
            var instance = (GameObject)PrefabUtility.InstantiatePrefab(model);
            try
            {
                var animator = instance.GetComponent<Animator>();
                if (animator == null || !animator.isHuman)
                {
                    report.AppendLine("The model's animator is not human.");
                }
                else
                {
                    var missing = Enum.GetValues(typeof(HumanBodyBones)).Cast<HumanBodyBones>()
                        .Where(bone => bone != HumanBodyBones.LastBone && animator.GetBoneTransform(bone) == null)
                        .Select(bone => bone.ToString()).ToList();
                    report.AppendLine("unmapped: " + (missing.Count == 0 ? "(none)" : string.Join(", ", missing)));
                    report.AppendLine("mapped: " + string.Join(", ", new[] { HumanBodyBones.Spine, HumanBodyBones.Chest, HumanBodyBones.Neck, HumanBodyBones.LeftEye, HumanBodyBones.Jaw }
                        .Select(bone => bone + "=" + (animator.GetBoneTransform(bone) != null ? animator.GetBoneTransform(bone).name : "none"))));
                }
            }
            finally
            {
                UnityEngine.Object.DestroyImmediate(instance);
            }

            if (AssetImporter.GetAtPath(modelPath) is ModelImporter importer)
            {
                var human = importer.humanDescription.human;
                report.AppendLine("described: " + human.Length + " bones: " +
                                  string.Join(", ", human.Select(bone => bone.humanName + "=" + bone.boneName)));
            }

            return report.ToString().TrimEnd();
        }

        /// <summary>
        /// Builds a humanoid avatar for a model from the bone names of cass's
        /// skeleton spec, the way an importer would, and returns what Unity
        /// says about it. The importer itself falls back to guessing without
        /// a word when a description is not to its liking; this says why.
        /// </summary>
        public static string Try(string modelPath)
        {
            var model = AssetDatabase.LoadAssetAtPath<GameObject>(modelPath);
            if (model == null) return "No model at " + modelPath;
            var instance = (GameObject)PrefabUtility.InstantiatePrefab(model);
            var messages = new System.Collections.Generic.List<string>();
            Application.LogCallback listen = (text, stack, type) => { if (type != LogType.Log) messages.Add(type + ": " + text); };
            Application.logMessageReceived += listen;
            try
            {
                var skeleton = Wirenook.Cass.Editor.CassSpec.Skeleton();
                var description = new HumanDescription
                {
                    human = skeleton.Humanoid.Select(pair => new HumanBone
                    {
                        humanName = HumanTrait.BoneName[(int)pair.Key], boneName = pair.Value, limit = new HumanLimit { useDefaultValues = true },
                    }).ToArray(),
                    skeleton = instance.GetComponentsInChildren<Transform>(true).Select(transform => new SkeletonBone
                    {
                        name = transform.name, position = transform.localPosition, rotation = transform.localRotation, scale = transform.localScale,
                    }).ToArray(),
                    upperArmTwist = 0.5f, lowerArmTwist = 0.5f, upperLegTwist = 0.5f, lowerLegTwist = 0.5f, armStretch = 0.05f, legStretch = 0.05f,
                };
                var avatar = AvatarBuilder.BuildHumanAvatar(instance, description);
                messages.Insert(0, "built: " + (avatar == null ? "nothing" : (avatar.isValid ? "valid" : "INVALID") + ", " + (avatar.isHuman ? "human" : "NOT HUMAN")));
                if (avatar != null) UnityEngine.Object.DestroyImmediate(avatar);
            }
            finally
            {
                Application.logMessageReceived -= listen;
                UnityEngine.Object.DestroyImmediate(instance);
            }

            return string.Join(System.Environment.NewLine, messages);
        }
    }
}
