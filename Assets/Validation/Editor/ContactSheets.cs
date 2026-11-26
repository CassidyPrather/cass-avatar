using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using nadena.dev.ndmf;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;
using Wirenook.Assets.Editor;
using Wirenook.Cass.Core;
using Wirenook.Cass.Editor;
using Debug = UnityEngine.Debug;

namespace Wirenook.Validation.Editor
{
    /// <summary>
    /// Photographs a built avatar variant in the validation scene and lays the
    /// pictures out as labelled contact sheets under dist/validation/. It
    /// renders the avatar after the build-time optimisers have run, so what is
    /// reviewed is what would be uploaded.
    /// </summary>
    public static class ContactSheets
    {
        public const string OutputFolder = "dist/validation";
        private const int TileWidth = 420;
        private const int TileHeight = 560;

        [MenuItem("Tools/Wirenook/Validation/Render Contact Sheets (cass)")]
        private static void RenderDefault() => Debug.Log(Render("cass"));

        /// <returns>The folder the sheets were written to.</returns>
        public static string Render(string slug)
        {
            // A mobile build looks different enough to keep its own pictures.
            var platform = Wirenook.Assets.Editor.WirenookPlatform.Current;
            var folder = Path.Combine(OutputFolder, platform == Wirenook.Assets.Editor.Platform.Pc
                ? slug
                : slug + "-" + Wirenook.Assets.Editor.WirenookPlatform.Name(platform));
            if (Directory.Exists(folder)) Directory.Delete(folder, true);

            var previous = SceneManager.GetActiveScene();
            var scene = ValidationScene.Open(out var added);
            GameObject avatar = null;
            List<PoseLibrary.Pose> poses = null;
            try
            {
                // Lighting conditions write the scene-wide ambient light, which
                // belongs to whichever scene is active.
                SceneManager.SetActiveScene(scene);
                CassBuild.Measure(slug, out avatar);
                avatar.transform.SetPositionAndRotation(Vector3.zero, Quaternion.identity);

                CassPreview.SkinEveryRender(avatar);
                var features = CassPreview.Toggles(avatar);
                Held = CassPreview.AllOff(features);

                var cameras = ValidationScene.Cameras(scene).ToDictionary(camera => camera.name);
                var conditions = ValidationScene.Conditions(scene).ToList();
                var neutral = conditions.First(condition => condition.name == "Neutral");
                poses = PoseLibrary.All();
                var stand = poses.First(pose => pose.Name == "Stand");

                neutral.Activate();
                Apply(avatar, stand);
                var index = 0;
                foreach (var camera in cameras.Values)
                    Capture(camera, Tile(folder, "1 cameras", index++, camera.name));

                index = 0;
                foreach (var condition in conditions)
                {
                    condition.Activate();
                    Capture(cameras["Three-Quarter"], Tile(folder, "2 lighting", index++, condition.name));
                    Capture(cameras["Face Three-Quarter"], Tile(folder, "2 lighting", index++, condition.name + " (face)"));
                }

                neutral.Activate();
                index = 0;
                foreach (var pose in poses.Where(pose => !pose.RangeOfMotion))
                {
                    Apply(avatar, pose);
                    Capture(cameras["Three-Quarter"], Tile(folder, "3 animations", index++, pose.Name));
                    Capture(cameras["Three-Quarter Back"], Tile(folder, "3 animations", index++, pose.Name + " (back)"));
                }

                index = 0;
                foreach (var pose in poses.Where(pose => pose.RangeOfMotion))
                {
                    Apply(avatar, pose);
                    Capture(cameras["Three-Quarter"], Tile(folder, "4 range of motion", index++, pose.Name));
                    Capture(cameras["Three-Quarter Back"], Tile(folder, "4 range of motion", index++, pose.Name + " (back)"));
                }

                Apply(avatar, stand);
                Expressions(avatar, cameras["Face"], folder);
                Outfits(avatar, cameras["Three-Quarter"], folder);

                index = 0;
                foreach (var feature in features)
                {
                    CassPreview.Hold(Held, feature.On);
                    Apply(avatar, stand);
                    FollowConstraints(avatar);
                    Capture(cameras["Three-Quarter"], Tile(folder, "8 features", index++, feature.Name));
                    Capture(cameras["Back"], Tile(folder, "8 features", index++, feature.Name + " (back)"));
                    CassPreview.Hold(Held, feature.Off);
                }
            }
            finally
            {
                if (poses != null) PoseLibrary.Release(poses);
                if (avatar != null) UnityEngine.Object.DestroyImmediate(avatar);
                AvatarProcessor.CleanTemporaryAssets();
                ValidationScene.Conditions(scene).First(condition => condition.name == "Neutral").Activate();
                if (added)
                {
                    if (previous.IsValid()) SceneManager.SetActiveScene(previous);
                    EditorSceneManager.CloseScene(scene, true);
                }
            }

            Compose(folder);
            return Path.GetFullPath(folder);
        }

        private static void Apply(GameObject avatar, PoseLibrary.Pose pose)
        {
            Apply(avatar, pose.Clip, pose.Time * pose.Clip.length);
        }

        /// <summary>The toggle states every picture holds besides its pose.</summary>
        private static Dictionary<EditorCurveBinding, float> Held = new Dictionary<EditorCurveBinding, float>();

        private static void Apply(GameObject avatar, AnimationClip clip, float time)
        {
            CassPreview.Sample(avatar, clip, time, Held);
            avatar.transform.SetPositionAndRotation(Vector3.zero, Quaternion.identity);
        }

        /// <summary>
        /// Moves every parent-constrained object onto its source. VRChat's
        /// constraints only solve while the game runs, so in the editor a prop
        /// that trails or is dropped beside the avatar would otherwise sit at
        /// the avatar's origin, inside it.
        /// </summary>
        private static void FollowConstraints(GameObject avatar)
        {
            foreach (var constraint in avatar.GetComponentsInChildren<VRC.SDK3.Dynamics.Constraint.Components.VRCParentConstraint>(true))
            {
                if (constraint.Sources.Count == 0 || constraint.Sources[0].SourceTransform == null) continue;
                var source = constraint.Sources[0].SourceTransform;
                var target = constraint.TargetTransform != null ? constraint.TargetTransform : constraint.transform;
                target.SetPositionAndRotation(source.position, source.rotation);
            }
        }

        /// <summary>Every gesture expression as an untracked player would show it, plus the speech visemes.</summary>
        private static void Expressions(GameObject avatar, Camera camera, string folder)
        {
            var shapes = CassSpec.Blendshapes();
            var gestures = CassSpec.Gestures();
            var tiles = CassSpec.Tiles();
            var body = avatar.GetComponentsInChildren<SkinnedMeshRenderer>(true).First(renderer => renderer.name == shapes.Mesh);
            var block = new MaterialPropertyBlock();
            void Shoot(string sheet, int index, string label, IEnumerable<KeyValuePair<string, float>> weights)
            {
                var mesh = body.sharedMesh;
                var set = new List<int>();
                foreach (var weight in weights)
                {
                    // The optimiser drops shapes nothing can drive; one missing
                    // here could never show on the built avatar either.
                    var shape = mesh.GetBlendShapeIndex(weight.Key);
                    if (shape < 0) continue;
                    body.SetBlendShapeWeight(shape, weight.Value);
                    set.Add(shape);
                }

                Capture(camera, Tile(folder, sheet, index, label));
                foreach (var shape in set) body.SetBlendShapeWeight(shape, 0f);
            }

            var rest = new Dictionary<string, float>();
            var tileIndex = 0;
            Shoot("5 expressions", tileIndex++, "Neutral", rest);
            foreach (var hand in new[] { Hand.Left, Hand.Right })
            {
                foreach (var entry in gestures.For(hand).OrderBy(pair => pair.Key))
                {
                    var expression = gestures.Expressions[entry.Value];
                    block.Clear();
                    foreach (var flip in expression.Tiles)
                    {
                        var tile = tiles.Get(flip.Key);
                        block.SetFloat(ToonMaterial.TileProperty(tile.Column, tile.Row), flip.Value ? 0f : 1f);
                    }

                    body.SetPropertyBlock(block);
                    Shoot("5 expressions", tileIndex++, hand + " " + entry.Key + " - " + expression.Label, expression.Shapes);
                    body.SetPropertyBlock(null);
                }
            }

            tileIndex = 0;
            foreach (var viseme in shapes.Visemes)
                Shoot("6 visemes", tileIndex++, viseme, new Dictionary<string, float> { { viseme, 100f } });
            Shoot("6 visemes", tileIndex, "(rest)", rest);
        }

        /// <summary>
        /// Each outfit switch flipped in turn, then all on and all off: checks
        /// the skin underneath comes back whole and the alternatives give way
        /// to each other.
        /// </summary>
        private static void Outfits(GameObject avatar, Camera camera, string folder)
        {
            var tiles = CassSpec.Tiles();
            var switches = tiles.Offered();
            var offered = new HashSet<string>(switches.Select(tile => tile.Toggle.Parameter));
            var defaults = tiles.Defaults().Where(known => offered.Contains(known.Parameter)).ToList();
            var renderers = avatar.GetComponentsInChildren<Renderer>(true);
            var block = new MaterialPropertyBlock();

            void Shoot(string label, Dictionary<string, bool> parameters, int index)
            {
                var shown = tiles.ResolveFor(parameters);
                block.Clear();
                foreach (var tile in tiles.Tiles)
                    block.SetFloat(ToonMaterial.TileProperty(tile.Column, tile.Row), shown[tile.Id] ? 0f : 1f);
                foreach (var renderer in renderers) renderer.SetPropertyBlock(block);
                Capture(camera, Tile(folder, "7 outfit", index, label));
            }

            var index = 0;
            Shoot("Dressed", null, index++);
            foreach (var tile in switches)
            {
                var rests = defaults.First(known => known.Parameter == tile.Toggle.Parameter).Value;
                Shoot((rests ? "No " : "") + tile.Toggle.Label, new Dictionary<string, bool> { { tile.Toggle.Parameter, !rests } }, index++);
            }

            Shoot("Everything On", defaults.ToDictionary(known => known.Parameter, known => true), index++);
            Shoot("Everything Off", defaults.ToDictionary(known => known.Parameter, known => false), index);
            foreach (var renderer in renderers) renderer.SetPropertyBlock(null);
        }

        private static string Tile(string folder, string sheet, int index, string label)
        {
            var safe = string.Concat(label.Select(character => Path.GetInvalidFileNameChars().Contains(character) ? '_' : character));
            return Path.Combine(folder, sheet, index.ToString("000") + " " + safe + ".png");
        }

        public static void Capture(Camera camera, string path)
        {
            var target = RenderTexture.GetTemporary(TileWidth, TileHeight, 24, RenderTextureFormat.ARGB32, RenderTextureReadWrite.sRGB);
            var previous = RenderTexture.active;
            try
            {
                camera.targetTexture = target;
                camera.Render();
                RenderTexture.active = target;
                var image = new Texture2D(TileWidth, TileHeight, TextureFormat.RGB24, false);
                image.ReadPixels(new Rect(0, 0, TileWidth, TileHeight), 0, 0);
                image.Apply();
                Directory.CreateDirectory(Path.GetDirectoryName(path));
                File.WriteAllBytes(path, image.EncodeToPNG());
                UnityEngine.Object.DestroyImmediate(image);
            }
            finally
            {
                camera.targetTexture = null;
                RenderTexture.active = previous;
                RenderTexture.ReleaseTemporary(target);
            }
        }

        /// <summary>Labels and tiles the pictures; a script outside Unity so the layout is easy to change.</summary>
        public static void Compose(string folder)
        {
            var process = Process.Start(new ProcessStartInfo
            {
                FileName = "python",
                Arguments = "\"" + Path.GetFullPath("tools/contact_sheet.py") + "\" \"" + Path.GetFullPath(folder) + "\"",
                UseShellExecute = false,
                RedirectStandardError = true,
                RedirectStandardOutput = true,
                CreateNoWindow = true,
            });
            var errors = process.StandardError.ReadToEnd();
            process.WaitForExit();
            if (process.ExitCode != 0)
                throw new InvalidOperationException("tools/contact_sheet.py failed:\n" + errors);
        }
    }
}
