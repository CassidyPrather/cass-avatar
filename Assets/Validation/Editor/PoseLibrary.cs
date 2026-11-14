using System.Collections.Generic;
using System.Linq;
using UnityEditor;
using UnityEngine;

namespace Wirenook.Validation.Editor
{
    /// <summary>
    /// The poses an avatar is photographed in. Two sources: VRChat's own
    /// proxy animations, which are what players will actually see, and
    /// range-of-motion poses that push one joint group to each end of its
    /// humanoid range, which is where clothing and skin intersect.
    ///
    /// Every derived pose is a copy of VRChat's standing clip with a few
    /// curves replaced. A humanoid clip that names only some muscles is not
    /// "the current pose plus those": Unity fills in the rest itself and moves
    /// the body to the origin. Starting from a complete clip avoids that.
    /// </summary>
    public static class PoseLibrary
    {
        private const string ProxyFolder = "Packages/com.vrchat.avatars/Samples/AV3 Demo Assets/Animation/ProxyAnim";
        private const string StandClip = "proxy_stand_still";

        public readonly struct Pose
        {
            public readonly string Name;
            public readonly AnimationClip Clip;

            /// <summary>Normalised time to sample the clip at.</summary>
            public readonly float Time;

            /// <summary>True for the generated joint-limit poses, false for VRChat's own animations.</summary>
            public readonly bool RangeOfMotion;

            public Pose(string name, AnimationClip clip, float time, bool rangeOfMotion)
            {
                Name = name;
                Clip = clip;
                Time = time;
                RangeOfMotion = rangeOfMotion;
            }
        }

        // name, clip, normalised sample times
        private static readonly (string name, string clip, float[] times)[] Proxies =
        {
            ("Stand", StandClip, new[] { 0f }),
            ("Walk", "proxy_walk_forward", new[] { 0.0f, 0.25f }),
            ("Run", "proxy_run_forward", new[] { 0.0f, 0.25f }),
            ("Sprint", "proxy_sprint_forward", new[] { 0.25f }),
            ("Strafe", "proxy_strafe_right", new[] { 0.25f }),
            ("Crouch", "proxy_crouch_still", new[] { 0f }),
            ("Crouch Walk", "proxy_crouch_walk_forward", new[] { 0.25f }),
            ("Prone", "proxy_low_crawl_still", new[] { 0f }),
            ("Sit", "proxy_sit", new[] { 0f }),
            ("Fall", "proxy_fall_long", new[] { 0.5f }),
            ("AFK", "proxy_afk", new[] { 0.5f }),
            ("Wave", "proxy_stand_wave", new[] { 0.4f }),
            ("Cheer", "proxy_stand_cheer", new[] { 0.4f }),
            ("Backflip", "proxy_backflip", new[] { 0.45f }),
            ("Dance", "proxy_dance", new[] { 0.2f, 0.6f }),
            ("Die", "proxy_die", new[] { 0.9f }),
        };

        /// <summary>Muscle groups pushed to both ends of their range; -1 and +1 are the humanoid limits.</summary>
        private static readonly (string name, string[] muscles)[] Ranges =
        {
            ("Arms Down-Up", new[] { "Left Arm Down-Up", "Right Arm Down-Up", "Left Shoulder Down-Up", "Right Shoulder Down-Up" }),
            ("Arms Front-Back", new[] { "Left Arm Front-Back", "Right Arm Front-Back", "Left Shoulder Front-Back", "Right Shoulder Front-Back" }),
            ("Arms Twist", new[] { "Left Arm Twist In-Out", "Right Arm Twist In-Out", "Left Forearm Twist In-Out", "Right Forearm Twist In-Out" }),
            ("Elbows", new[] { "Left Forearm Stretch", "Right Forearm Stretch" }),
            ("Wrists", new[] { "Left Hand Down-Up", "Right Hand Down-Up" }),
            ("Legs Front-Back", new[] { "Left Upper Leg Front-Back", "Right Upper Leg Front-Back" }),
            ("Legs In-Out", new[] { "Left Upper Leg In-Out", "Right Upper Leg In-Out" }),
            ("Knees", new[] { "Left Lower Leg Stretch", "Right Lower Leg Stretch" }),
            ("Ankles", new[] { "Left Foot Up-Down", "Right Foot Up-Down" }),
            ("Torso Front-Back", new[] { "Spine Front-Back", "Chest Front-Back", "UpperChest Front-Back" }),
            ("Torso Left-Right", new[] { "Spine Left-Right", "Chest Left-Right", "UpperChest Left-Right" }),
            ("Torso Twist", new[] { "Spine Twist Left-Right", "Chest Twist Left-Right", "UpperChest Twist Left-Right" }),
            ("Head Nod", new[] { "Neck Nod Down-Up", "Head Nod Down-Up" }),
            ("Head Turn", new[] { "Neck Turn Left-Right", "Head Turn Left-Right" }),
            ("Head Tilt", new[] { "Neck Tilt Left-Right", "Head Tilt Left-Right" }),
        };

        /// <summary>
        /// Combinations no single muscle group reaches, and the usual places
        /// shorts, sleeves and boots give out.
        /// </summary>
        private static readonly (string name, (string muscle, float value)[] muscles)[] Combined =
        {
            ("Squat", new[]
            {
                ("Left Upper Leg Front-Back", -0.9f), ("Right Upper Leg Front-Back", -0.9f),
                ("Left Lower Leg Stretch", -1f), ("Right Lower Leg Stretch", -1f),
                ("Left Upper Leg In-Out", 0.4f), ("Right Upper Leg In-Out", 0.4f),
                ("Spine Front-Back", -0.4f),
            }),
            ("High Kick", new[]
            {
                ("Left Upper Leg Front-Back", -1f), ("Left Lower Leg Stretch", 1f),
                ("Right Arm Down-Up", 0.8f), ("Left Arm Front-Back", 0.6f),
                ("Spine Front-Back", 0.3f),
            }),
            ("Hug", new[]
            {
                ("Left Arm Front-Back", 0.9f), ("Right Arm Front-Back", 0.9f),
                ("Left Arm Down-Up", 0.1f), ("Right Arm Down-Up", 0.1f),
                ("Left Forearm Stretch", -0.7f), ("Right Forearm Stretch", -0.7f),
            }),
            ("Fists", HandMuscles(-1f)),
            ("Splayed Hands", HandMuscles(1f)),
        };

        private static (string, float)[] HandMuscles(float value)
        {
            var muscles = new List<(string, float)>();
            foreach (var side in new[] { "Left", "Right" })
            {
                foreach (var finger in new[] { "Thumb", "Index", "Middle", "Ring", "Little" })
                {
                    for (var joint = 1; joint <= 3; joint++)
                        muscles.Add((side + "Hand." + finger + "." + joint + " Stretched", value));
                    muscles.Add((side + "Hand." + finger + ".Spread", value));
                }
            }

            return muscles.ToArray();
        }

        private static AnimationClip Proxy(string name)
        {
            return AssetDatabase.LoadAssetAtPath<AnimationClip>(ProxyFolder + "/" + name + ".anim");
        }

        /// <summary>
        /// A copy of the standing clip with the given muscles held at the given
        /// values. The caller owns the clip and should destroy it when done.
        /// </summary>
        public static AnimationClip Standing(IEnumerable<(string muscle, float value)> muscles)
        {
            var clip = StandingCopy();
            foreach (var (muscle, value) in muscles)
                clip.SetCurve("", typeof(Animator), muscle, AnimationCurve.Constant(0f, clip.length, value));
            return clip;
        }

        private static AnimationClip StandingCopy()
        {
            var stand = Proxy(StandClip);
            if (stand == null)
                throw new System.IO.FileNotFoundException("The VRChat SDK's sample animations are missing; reinstall the Avatars SDK.", ProxyFolder);
            var clip = Object.Instantiate(stand);
            clip.hideFlags = HideFlags.HideAndDontSave;
            return clip;
        }

        /// <summary>
        /// Every pose, proxy animations first. The range-of-motion clips are
        /// built on the spot; destroy them with <see cref="Release"/>.
        /// </summary>
        public static List<Pose> All()
        {
            var poses = new List<Pose>();
            foreach (var (name, clipName, times) in Proxies)
            {
                var clip = Proxy(clipName);
                if (clip == null)
                {
                    Debug.LogWarning("[validation] The SDK no longer ships " + clipName + "; skipping that pose.");
                    continue;
                }

                for (var i = 0; i < times.Length; i++)
                    poses.Add(new Pose(times.Length > 1 ? name + " " + (i + 1) : name, clip, times[i], false));
            }

            foreach (var range in Ranges)
            {
                poses.Add(new Pose(range.name + " (min)", Standing(range.muscles.Select(muscle => (muscle, -1f))), 0f, true));
                poses.Add(new Pose(range.name + " (max)", Standing(range.muscles.Select(muscle => (muscle, 1f))), 0f, true));
            }

            foreach (var combination in Combined)
                poses.Add(new Pose(combination.name, Standing(combination.muscles), 0f, true));
            return poses;
        }

        /// <summary>Destroys the clips <see cref="All"/> built.</summary>
        public static void Release(IEnumerable<Pose> poses)
        {
            foreach (var pose in poses.Where(pose => pose.RangeOfMotion)) Object.DestroyImmediate(pose.Clip);
        }
    }
}
