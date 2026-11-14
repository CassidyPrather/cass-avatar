using System;
using System.Collections.Generic;
using System.Linq;
using UnityEditor;
using UnityEngine;
using VRC.SDK3.Avatars.Components;
using VRC.SDKBase;
using Wirenook.Assets.Editor;
using Wirenook.Cass.Core;

namespace Wirenook.Cass.Editor
{
    /// <summary>
    /// Generates the avatar's FX controller from the specs.
    ///
    /// Layer order is part of the contract with MMD worlds: they silence FX
    /// layers 1 and 2 so their dance animation can drive the face. Those two
    /// slots are therefore the hand-gesture layers, the only ones that touch
    /// the MMD-named blendshapes, and nothing may be inserted before them.
    /// </summary>
    public static class CassFx
    {
        public const string ControllerPath = CassSpec.GeneratedFolder + "/cass-fx.controller";

        /// <summary>The menu switch: let a face tracker drive the face, or animate it.</summary>
        public const string TrackingEnabled = "FT/Enabled";

        private const string UserFaceTracking = "UserFaceTracking";
        private const string UserEyeTracking = "UserEyeTracking";
        private const string BlinkPick = "Face/BlinkPick";

        /// <summary>The blendshape set that only carries speech visemes; it is never switched off.</summary>
        public const string VisemeSet = "visemes";

        private const float ExpressionFade = 0.1f;

        /// <summary>How fast a tracked region is handed over, in set weight per second.</summary>
        private const float HandoverSpeed = 10f;

        /// <summary>Seconds of open eyes before each blink; one is picked at random per blink.</summary>
        private static readonly float[] BlinkWaits = { 2.1f, 3.4f, 5.2f };

        public static void Rebuild()
        {
            var shapes = CassSpec.Blendshapes();
            var tiles = CassSpec.Tiles();
            var gestures = CassSpec.Gestures();
            var renderers = BodyMaterialRenderers();

            var fx = ControllerBuilder.Rebuild(ControllerPath);
            fx.Int("GestureLeft").Int("GestureRight")
                .Bool(UserFaceTracking).Bool(UserEyeTracking)
                .Bool(TrackingEnabled, true)
                .Int(BlinkPick);

            fx.Layer("Base").State("Idle");
            GestureLayer(fx, Hand.Left, gestures, shapes, tiles, renderers);
            GestureLayer(fx, Hand.Right, gestures, shapes, tiles, renderers);
            foreach (var region in GestureLayout.TrackedRegions) HandoverLayer(fx, region, gestures);
            BlinkLayer(fx, shapes.Mesh, gestures);
            OutfitLayers(fx, tiles, renderers);

            fx.Save();
        }

        /// <summary>
        /// Paths of every renderer wearing the body material. Tile switches
        /// animate all of them identically even where a renderer has no faces
        /// in that tile: renderers with matching animation are the ones the
        /// optimiser is allowed to merge into a single mesh at build time.
        /// </summary>
        private static List<string> BodyMaterialRenderers()
        {
            var model = AssetDatabase.LoadAssetAtPath<GameObject>(CassSpec.ModelPath);
            if (model == null) throw new System.IO.FileNotFoundException("Export the model from Blender first: " + CassSpec.ModelPath);
            var material = CassMaterials.Body;
            return model.GetComponentsInChildren<SkinnedMeshRenderer>(true)
                .Where(renderer => renderer.sharedMaterials.Contains(material))
                .Select(renderer => AnimationUtility.CalculateTransformPath(renderer.transform, model.transform))
                .ToList();
        }

        private static void GestureLayer(ControllerBuilder fx, Hand hand, GestureLayout gestures, BlendshapeSpec shapes,
            TileLayout tiles, List<string> renderers)
        {
            var parameter = hand == Hand.Left ? "GestureLeft" : "GestureRight";
            var layer = fx.Layer(hand + " Hand");
            var neutral = layer.State("Neutral");
            var mapped = gestures.For(hand);

            // Every value without an expression returns to neutral, so adding
            // or removing a row in the table can never strand the face.
            var toNeutral = layer.Any(neutral).Fade(ExpressionFade).Equal(parameter, 0);
            for (var value = 1; value <= 7; value++)
            {
                if (!mapped.ContainsKey(value)) toNeutral.Or().Equal(parameter, value);
            }

            foreach (var pair in mapped.OrderBy(entry => entry.Key))
            {
                var expression = gestures.Expressions[pair.Value];
                var full = layer.State(expression.Label, ExpressionClip(fx, expression, false, shapes, tiles, renderers));
                var tracked = layer.State(expression.Label + " (tracked)", ExpressionClip(fx, expression, true, shapes, tiles, renderers));

                layer.Any(tracked).Fade(ExpressionFade)
                    .Equal(parameter, pair.Key).IfTrue(TrackingEnabled).IfTrue(UserFaceTracking);
                layer.Any(full).Fade(ExpressionFade)
                    .Equal(parameter, pair.Key).IfFalse(TrackingEnabled)
                    .Or().Equal(parameter, pair.Key).IfFalse(UserFaceTracking);
            }
        }

        private static AnimationClip ExpressionClip(ControllerBuilder fx, Expression expression, bool tracked,
            BlendshapeSpec shapes, TileLayout tiles, List<string> renderers)
        {
            return fx.Clip(expression.Id + (tracked ? " (tracked)" : ""), clip =>
            {
                foreach (var shape in GestureLayout.ShapesFor(expression, tracked, shapes.RegionOf))
                    clip.Blendshape(shapes.Mesh, shape.Key, shape.Value);

                foreach (var flip in expression.Tiles)
                {
                    var tile = tiles.Get(flip.Key);
                    foreach (var renderer in renderers)
                        clip.Material<SkinnedMeshRenderer>(renderer, ToonMaterial.TileProperty(tile.Column, tile.Row), flip.Value ? 0f : 1f);
                }

                // An expression that keeps nothing under tracking still needs a length.
                if (clip.Clip.empty) clip.Hold(0.1f);
            });
        }

        /// <summary>
        /// Decides who drives one face region. The tracker has it only while
        /// the menu allows tracking, a tracker is actually sending, and neither
        /// hand holds an expression that owns the region. Fading the region's
        /// blendshape set in and out makes the hand-over a blend, not a snap.
        /// </summary>
        private static void HandoverLayer(ControllerBuilder fx, string region, GestureLayout gestures)
        {
            var layer = fx.Layer("Tracking: " + region);
            var animated = layer.State("Animated");
            var tracked = layer.State("Tracked");
            animated.Behaviour<VRCAnimatorFaceTrackingBlendshapesSet>(behaviour => SetWeight(behaviour, region, 0f));
            tracked.Behaviour<VRCAnimatorFaceTrackingBlendshapesSet>(behaviour => SetWeight(behaviour, region, 1f));

            var left = gestures.OwningGestures(Hand.Left, region);
            var right = gestures.OwningGestures(Hand.Right, region);

            var toTracked = animated.To(tracked);
            var first = true;
            foreach (var source in Sources(region))
            {
                if (!first) toTracked.Or();
                first = false;
                toTracked.IfTrue(TrackingEnabled).IfTrue(source);
                foreach (var gesture in left) toTracked.NotEqual("GestureLeft", gesture);
                foreach (var gesture in right) toTracked.NotEqual("GestureRight", gesture);
            }

            var toAnimated = tracked.To(animated).IfFalse(TrackingEnabled);
            toAnimated.Or();
            foreach (var source in Sources(region)) toAnimated.IfFalse(source);
            foreach (var gesture in left) toAnimated.Or().Equal("GestureLeft", gesture);
            foreach (var gesture in right) toAnimated.Or().Equal("GestureRight", gesture);
        }

        /// <summary>An eye tracker alone is enough to drive the eyes; the rest of the face needs a face tracker.</summary>
        private static string[] Sources(string region)
        {
            return region == "eyes" ? new[] { UserFaceTracking, UserEyeTracking } : new[] { UserFaceTracking };
        }

        private static void SetWeight(VRCAnimatorFaceTrackingBlendshapesSet behaviour, string set, float weight)
        {
            behaviour.blendSets = new List<VRC_AnimatorFaceTrackingBlendshapesSet.BlendSet>
            {
                new VRC_AnimatorFaceTrackingBlendshapesSet.BlendSet
                {
                    type = VRC_AnimatorFaceTrackingBlendshapesSet.SourceType.Value,
                    blendshapesSetName = set,
                    weight = weight,
                    lerpSpeed = HandoverSpeed,
                },
            };
        }

        /// <summary>
        /// Animated blinking for whenever no tracker has the eyelids. It stops
        /// while a gesture owns the eyes, so a wink is never blinked through.
        /// It animates the tracking eyelid shapes rather than the MMD blink, so
        /// it sits outside the two layers MMD worlds silence without fighting them.
        /// </summary>
        private static void BlinkLayer(ControllerBuilder fx, string mesh, GestureLayout gestures)
        {
            var layer = fx.Layer("Blink");
            var pick = layer.State("Pick");
            var suppressed = layer.State("Suppressed");

            // Each viewer rolls their own blink timing; syncing it would spend
            // parameter bits on something nobody can tell apart.
            pick.Behaviour<VRCAvatarParameterDriver>(driver =>
            {
                driver.localOnly = false;
                driver.parameters = new List<VRC_AvatarParameterDriver.Parameter>
                {
                    new VRC_AvatarParameterDriver.Parameter
                    {
                        type = VRC_AvatarParameterDriver.ChangeType.Random,
                        name = BlinkPick,
                        valueMin = 0,
                        valueMax = BlinkWaits.Length - 1,
                    },
                };
            });

            for (var i = 0; i < BlinkWaits.Length; i++)
            {
                var wait = BlinkWaits[i];
                var blink = fx.Clip("blink after " + wait.ToString("0.0") + "s", clip =>
                {
                    var curve = new AnimationCurve(
                        new Keyframe(0f, 0f), new Keyframe(wait, 0f), new Keyframe(wait + 0.06f, 100f),
                        new Keyframe(wait + 0.10f, 100f), new Keyframe(wait + 0.22f, 0f));
                    for (var key = 0; key < curve.length; key++)
                        AnimationUtility.SetKeyLeftTangentMode(curve, key, AnimationUtility.TangentMode.Linear);
                    for (var key = 0; key < curve.length; key++)
                        AnimationUtility.SetKeyRightTangentMode(curve, key, AnimationUtility.TangentMode.Linear);
                    clip.Blendshape(mesh, "EyeClosedLeft", curve).Blendshape(mesh, "EyeClosedRight", curve);
                });
                var state = layer.State("Blink " + i, blink);
                pick.To(state).Equal(BlinkPick, i);
                state.To(pick).AfterTime(1f);
            }

            var left = gestures.OwningGestures(Hand.Left, "eyes");
            var right = gestures.OwningGestures(Hand.Right, "eyes");

            var stop = layer.Any(suppressed).Fade(0.05f).IfTrue(TrackingEnabled).IfTrue(UserFaceTracking);
            stop.Or().IfTrue(TrackingEnabled).IfTrue(UserEyeTracking);
            foreach (var gesture in left) stop.Or().Equal("GestureLeft", gesture);
            foreach (var gesture in right) stop.Or().Equal("GestureRight", gesture);

            var resume = suppressed.To(pick).IfFalse(TrackingEnabled);
            foreach (var gesture in left) resume.NotEqual("GestureLeft", gesture);
            foreach (var gesture in right) resume.NotEqual("GestureRight", gesture);
            resume.Or().IfFalse(UserFaceTracking).IfFalse(UserEyeTracking);
            foreach (var gesture in left) resume.NotEqual("GestureLeft", gesture);
            foreach (var gesture in right) resume.NotEqual("GestureRight", gesture);
        }

        /// <summary>
        /// One layer per garment switch, and one per body zone a garment can
        /// cover. A zone is drawn only while every garment over it is off, so
        /// two outfits that both cover the torso cannot disagree about it.
        /// </summary>
        private static void OutfitLayers(ControllerBuilder fx, TileLayout tiles, List<string> renderers)
        {
            foreach (var tile in tiles.Tiles.Where(candidate => candidate.Toggle != null))
            {
                fx.Bool(tile.Toggle.Parameter, tile.Shown);
                var layer = fx.Layer("Outfit: " + tile.Toggle.Label);
                TileSwitch(fx, layer, tile, renderers, tile.Shown,
                    show => show.IfTrue(tile.Toggle.Parameter),
                    hide => hide.IfFalse(tile.Toggle.Parameter));
            }

            var resting = tiles.Resolve();
            foreach (var zone in tiles.Zones())
            {
                var covers = tiles.Covering(zone.Id).Where(tile => tile.Toggle != null).Select(tile => tile.Toggle.Parameter).ToList();
                if (covers.Count == 0) continue;

                // Unity rejects dots in state machine names.
                var layer = fx.Layer("Zone: " + zone.Id.Replace('.', ' '));
                TileSwitch(fx, layer, zone, renderers, resting[zone.Id],
                    show =>
                    {
                        foreach (var parameter in covers) show.IfFalse(parameter);
                    },
                    hide =>
                    {
                        hide.IfTrue(covers[0]);
                        foreach (var parameter in covers.Skip(1)) hide.Or().IfTrue(parameter);
                    });
            }
        }

        private static void TileSwitch(ControllerBuilder fx, LayerBuilder layer, Tile tile, List<string> renderers,
            bool startsShown, Action<TransitionBuilder> whenShown, Action<TransitionBuilder> whenHidden)
        {
            AnimationClip Clip(bool shown) => fx.Clip(tile.Id + (shown ? " shown" : " hidden"), clip =>
            {
                foreach (var renderer in renderers)
                    clip.Material<SkinnedMeshRenderer>(renderer, ToonMaterial.TileProperty(tile.Column, tile.Row), shown ? 0f : 1f);
            });

            // The first state added is the layer default: it has to match what
            // the material shows before any parameter has synced.
            var first = layer.State(startsShown ? "Shown" : "Hidden", Clip(startsShown));
            var second = layer.State(startsShown ? "Hidden" : "Shown", Clip(!startsShown));
            var shownState = startsShown ? first : second;
            var hiddenState = startsShown ? second : first;
            whenShown(hiddenState.To(shownState));
            whenHidden(shownState.To(hiddenState));
        }
    }
}
