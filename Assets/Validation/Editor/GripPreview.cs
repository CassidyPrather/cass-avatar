using System.IO;
using System.Linq;
using nadena.dev.ndmf;
using UnityEditor;
using UnityEngine;
using VRC.SDK3.Avatars.Components;
using Wirenook.Assets.Editor;
using Wirenook.Cass.Editor;

namespace Wirenook.Validation.Editor
{
    /// <summary>
    /// Renders each held prop of a built variant in its hand, with the
    /// finger pose the build gave that hand for it (HandPoses, in
    /// net.wirenook.assets). The poses are read back out of the built
    /// avatar's Gesture controller, so this is also the check that they got
    /// there. Fingers should close on the prop without passing through it.
    /// </summary>
    public static class GripPreview
    {
        /// <returns>The folder the pictures were written to, or a note that the variant holds nothing.</returns>
        public static string Render(string slug)
        {
            var folder = Path.Combine(ContactSheets.OutputFolder, "grips");
            if (Directory.Exists(folder)) Directory.Delete(folder, true);

            var scene = ValidationScene.Open(out _);
            CassBuild.Measure(slug, out var built);
            try
            {
                UnityEngine.SceneManagement.SceneManager.MoveGameObjectToScene(built, scene);
                CassPreview.SkinEveryRender(built);
                var gesture = built.GetComponent<VRCAvatarDescriptor>().baseAnimationLayers
                    .FirstOrDefault(layer => layer.type == VRCAvatarDescriptor.AnimLayerType.Gesture).animatorController;
                var poses = gesture == null
                    ? new AnimationClip[0]
                    : gesture.animationClips.Where(clip => clip != null && clip.name.Contains(HandPoses.ClipPrefix)).Distinct().OrderBy(clip => clip.name).ToArray();
                if (poses.Length == 0) return slug + " has no hand poses in its Gesture layer.";

                var arms = AssetDatabase.LoadAssetAtPath<AnimationClip>(
                    "Packages/com.vrchat.avatars/Samples/AV3 Demo Assets/Animation/ProxyAnim/proxy_tpose.anim");
                var toggles = CassPreview.Toggles(built);
                var animator = built.GetComponent<Animator>();
                var cameras = ValidationScene.Cameras(scene).ToDictionary(camera => camera.name);
                var close = new GameObject("Grip Preview Camera").AddComponent<Camera>();
                UnityEngine.SceneManagement.SceneManager.MoveGameObjectToScene(close.gameObject, scene);
                close.CopyFrom(cameras["Hand"]);
                var index = 0;
                foreach (var pose in poses)
                {
                    // "… hand pose right laser-pointer": the hand, then the feature's id.
                    var words = pose.name.Substring(pose.name.IndexOf(HandPoses.ClipPrefix, System.StringComparison.Ordinal) + HandPoses.ClipPrefix.Length).Split(new[] { ' ' }, 2);
                    var left = words[0] == "left";
                    var feature = words.Length > 1 ? words[1] : "";
                    var held = CassPreview.AllOff(toggles);
                    var toggle = toggles.FirstOrDefault(candidate =>
                    {
                        var name = candidate.Name.ToLowerInvariant().Replace(' ', '-');
                        return name.Length > 0 && (feature.Contains(name) || name.Contains(feature));
                    });
                    if (toggle.On != null) CassPreview.Hold(held, toggle.On);
                    CassPreview.Hold(held, pose);
                    // Arms out: standing, the hands hang inside the skirt.
                    CassPreview.Sample(built, arms, 0f, held);

                    // Four looks at the hand: from in front, from below (the palm), from above and from past the fingertips.
                    var hand = animator.GetBoneTransform(left ? HumanBodyBones.LeftHand : HumanBodyBones.RightHand);
                    var middle = animator.GetBoneTransform(left ? HumanBodyBones.LeftMiddleProximal : HumanBodyBones.RightMiddleProximal);
                    var target = Vector3.Lerp(hand.position, middle.position, 0.8f);
                    var outward = left ? Vector3.left : Vector3.right;
                    var views = new (string name, Vector3 from)[]
                    {
                        ("front", Vector3.forward * 0.45f + Vector3.up * 0.05f),
                        ("palm", Vector3.down * 0.42f + Vector3.forward * 0.12f),
                        ("above", Vector3.up * 0.42f + Vector3.back * 0.12f),
                        ("end", outward * 0.45f + Vector3.up * 0.12f + Vector3.forward * 0.12f),
                    };
                    foreach (var (name, from) in views)
                    {
                        close.transform.position = target + from;
                        close.transform.LookAt(target);
                        close.fieldOfView = 30f;
                        ContactSheets.Capture(close, Path.Combine(folder, "grips",
                            index++.ToString("000") + " " + (left ? "left " : "right ") + feature + (toggle.On == null ? " (prop not shown)" : "") + ", " + name + ".png"));
                    }
                }

                Object.DestroyImmediate(close.gameObject);
            }
            finally
            {
                Object.DestroyImmediate(built);
                AvatarProcessor.CleanTemporaryAssets();
            }

            ContactSheets.Compose(folder);
            return Path.GetFullPath(folder);
        }
    }
}
