using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using System.Text;
using UnityEditor;
using UnityEditor.Animations;
using UnityEngine;
using Wirenook.Locomotion;
using Wirenook.Locomotion.Editor;

namespace Wirenook.Bot.Editor
{
    /// <summary>
    /// Generates the bot's own locomotion: the motions in BotMotion.cs,
    /// baked on the bot's skeleton and laid out over velocity, in a Base
    /// controller with VRChat's default state machine (both from
    /// net.wirenook.locomotion's CustomLocomotion) and a prefab that
    /// installs it. The prefab is a feature like any other: a variant
    /// lists it in Spec/variants.json in place of the package's walk.
    ///
    /// Over velocity it is a grid. Inside the rectangle its legs can keep
    /// up with (ahead and back to a walk, sideways as far as one foot
    /// clears the other) it steps. At and beyond the next grid lines out
    /// (sideways at <see cref="BotFrame.SlideSpeed"/>, ahead or back at
    /// <see cref="BotFrame.SkateSpeed"/>) it slides. VRChat's own walk, run
    /// and strafe speeds each sit inside one or the other, so a keyboard
    /// never holds the mixture between; a thumbstick passes through it.
    /// </summary>
    public static class BotLocomotion
    {
        public const string Folder = BotBuild.Package + "/Generated/Locomotion";
        public const string PrefabPath = BotBuild.Package + "/Prefabs/Bot Locomotion.prefab";

        /// <summary>How much of the upper body's motion a player with tracked head and hands is given.</summary>
        private const float TrackedShare = 0.35f;

        /// <summary>How far it tips when sliding: sideways, ahead at a run and at a sprint, and back.</summary>
        private const float TipAcross = 12f, TipAhead = 20f, TipSprint = 28f, TipBack = -13f;

        /// <summary>Faster than VRChat's run: for worlds that raise it.</summary>
        private const float SprintSpeed = 6f;

        /// <summary>What the controllers were last baked from; see <see cref="RebuildIfStale"/>.</summary>
        private const string StampPath = Folder + "/baked-from.txt";

        [MenuItem("Tools/Wirenook/Bot/Rebuild Locomotion")]
        private static void RebuildMenu() => Debug.Log(Rebuild());

        /// <summary>
        /// Bakes only when something the bake is made from has changed: the
        /// model, these motions, or the package that bakes them. The Base
        /// controller is some megabytes of keys, and a bake that changes
        /// nothing would still write all of them out under new ids.
        /// </summary>
        public static string RebuildIfStale()
        {
            string stamp = Stamp();
            bool current = File.Exists(StampPath) && File.ReadAllText(StampPath).Trim() == stamp &&
                           File.Exists(Folder + "/" + CustomLocomotion.BaseFile) && File.Exists(PrefabPath);
            if (current) return "The bot's locomotion is up to date.";
            string report = Rebuild();
            File.WriteAllText(StampPath, stamp + "\n");
            AssetDatabase.ImportAsset(StampPath);
            return report;
        }

        private static string Stamp()
        {
            string locomotion = UnityEditor.PackageManager.PackageInfo.FindForAssetPath("Packages/net.wirenook.locomotion").resolvedPath;
            var sources = new[] { BotBuild.Package + "/Editor/BotMotion.cs", BotBuild.Package + "/Editor/BotLocomotion.cs", BotBuild.ModelPath + ".meta" }
                .Concat(Directory.GetFiles(locomotion, "*.cs", SearchOption.AllDirectories).OrderBy(path => path, System.StringComparer.Ordinal));
            using var hash = SHA1.Create();
            using var all = new MemoryStream();
            foreach (string source in sources)
            {
                // Without carriage returns, so that a checkout's line endings do not make it stale.
                var text = Encoding.UTF8.GetBytes(File.ReadAllText(source).Replace("\r", ""));
                all.Write(text, 0, text.Length);
            }

            var model = File.ReadAllBytes(BotBuild.ModelPath);
            all.Write(model, 0, model.Length);
            return string.Concat(hash.ComputeHash(all.ToArray()).Select(part => part.ToString("x2")));
        }

        public static string Rebuild()
        {
            var body = CustomLocomotion.Measure(BotBuild.ModelPath);
            var options = new CustomLocomotionOptions
            {
                RigPath = BotBuild.ModelPath,
                Folder = Folder,
                PrefabPath = PrefabPath,
                Id = "bot-locomotion",
                Label = "Machine locomotion",
                Blend = BlendTreeType.FreeformCartesian2D,
                ProneLiesStill = true,
            };
            // Stepping, at speeds between the samples as well as on them, and in both directions.
            options.FootSpeedsAt.AddRange(new[]
            {
                new Vector2(0f, 0.4f), new Vector2(0f, 1f), new Vector2(0f, 1.6f), new Vector2(0f, 2f),
                new Vector2(0f, -1f), new Vector2(0f, -2f), new Vector2(0.15f, 1.5f), new Vector2(-0.15f, 0f),
            });
            var frame = new BotFrame(body, 1f);
            var desktop = Motions(frame, null);
            return CustomLocomotion.Build(desktop, Motions(new BotFrame(body, TrackedShare), desktop), options) +
                   "\ncycle " + frame.Cycle.ToString("F3") + " s at every speed; steps sideways up to " +
                   frame.SideStepSpeed.ToString("F2") + " m/s";
        }

        /// <summary>One line per baked clip: where its feet are against where its motion put them.</summary>
        public static string Describe()
        {
            var body = CustomLocomotion.Measure(BotBuild.ModelPath);
            var desktop = Motions(new BotFrame(body, 1f), null);
            return CustomLocomotion.Describe(desktop, Motions(new BotFrame(body, TrackedShare), desktop), BotBuild.ModelPath);
        }

        /// <param name="desktop">
        /// For the tracked set, the desktop one: the two step alike (a
        /// tracked player's own arms and head replace what differs), so the
        /// tracked set takes its stepping from there and the clips are stored once.
        /// </param>
        private static CustomMotions Motions(BotFrame frame, CustomMotions desktop)
        {
            var motions = new CustomMotions
            {
                Idle = new BotStanding(frame, false),
                CrouchIdle = new BotStanding(frame, true),
                Rising = new BotAir(frame, BotAirMoment.Rising),
                Falling = new BotAir(frame, BotAirMoment.Falling),
                Plunging = new BotAir(frame, BotAirMoment.Plunging),
                SoftLanding = new BotLanding(frame, false),
                HardLanding = new BotLanding(frame, true),
                Fidget = new BotFidget(frame),
            };

            float step = frame.SideStepSpeed;
            Grid(motions.Moving, desktop?.Moving, frame, false, new[] { 0f, step, BotFrame.SlideSpeed },
                new[]
                {
                    -BotFrame.SkateSpeed, -BotFrame.WalkSpeed, -BotFrame.WalkSpeed * 0.75f, -BotFrame.WalkSpeed / 2f,
                    -BotFrame.WalkSpeed / 4f, 0f, BotFrame.WalkSpeed / 4f, BotFrame.WalkSpeed / 2f, BotFrame.WalkSpeed * 0.75f,
                    BotFrame.WalkSpeed, BotFrame.SkateSpeed, SprintSpeed,
                },
                BotFrame.WalkSpeed);
            Grid(motions.Crouching, desktop?.Crouching, frame, true, new[] { 0f, step, BotFrame.CrouchSlideSpeed },
                new[]
                {
                    -BotFrame.CrouchSkateSpeed, -BotFrame.CrouchWalkSpeed, -BotFrame.CrouchWalkSpeed / 2f, 0f,
                    BotFrame.CrouchWalkSpeed / 2f, BotFrame.CrouchWalkSpeed, BotFrame.CrouchSkateSpeed,
                },
                BotFrame.CrouchWalkSpeed);
            return motions;
        }

        /// <summary>
        /// A motion at every crossing of the grid's lines but the middle,
        /// which is standing. The last line across is where it slides
        /// sideways; the lines past <paramref name="walk"/>, ahead and back, are where it slides that way.
        /// </summary>
        private static void Grid(List<CustomGait> gaits, List<CustomGait> stepsFrom, BotFrame frame, bool crouched, float[] across,
            float[] along, float walk)
        {
            string prefix = crouched ? "crouch " : "";
            float slide = across[across.Length - 1];
            foreach (float forward in along)
            {
                foreach (float right in across)
                {
                    if (right == 0f && forward == 0f) continue;
                    string at = " " + right.ToString("0.##") + " " + forward.ToString("0.##");
                    bool fast = Mathf.Abs(forward) > walk + 0.001f;
                    if (!fast && right < slide)
                    {
                        gaits.Add(stepsFrom?.First(gait => gait.Name == prefix + "step" + at) ??
                                  new CustomGait(prefix + "step" + at, right, forward, new BotStep(frame, right, forward, crouched)));
                        continue;
                    }

                    float tipAcross = TipAcross * right / slide * (fast ? 0.75f : 1f);
                    float tipAlong = fast
                        ? forward < 0f ? TipBack : forward > BotFrame.SkateSpeed + 0.001f && !crouched ? TipSprint : TipAhead
                        : 0.35f * (forward > 0f ? TipAhead : -TipBack) * forward / walk;
                    gaits.Add(new CustomGait(prefix + "slide" + at, right, forward,
                        new BotSlide(frame, right, forward, tipAcross, tipAlong, crouched)));
                }
            }
        }
    }
}
