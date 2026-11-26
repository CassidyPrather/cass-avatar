using System;
using System.Collections.Generic;
using System.Linq;
using UnityEditor;
using UnityEditor.Animations;
using UnityEngine;
using VRC.SDK3.Avatars.Components;
using VRC.SDK3.Dynamics.PhysBone.Components;
using VRC.SDKBase;
using Wirenook.Assets;
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

        /// <summary>VRChat's own flag for a wearer who has stepped away; it syncs it itself.</summary>
        private const string Afk = WirenookSignals.Afk;

        /// <summary>
        /// The same, said from the menu: the switch of the away feature
        /// (net.wirenook.party-tricks). Never on in a variant without it.
        /// </summary>
        private const string Away = WirenookSignals.Away;

        /// <summary>The blendshape set that only carries speech visemes; it is never switched off.</summary>
        public const string VisemeSet = "visemes";

        private const float ExpressionFade = 0.1f;

        /// <summary>Ears move slower than a face; they have further to go.</summary>
        private const float PoseFade = 0.18f;

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
            // A hand some feature is using as a button shows no expression (HandLayers).
            // Everything below reads the gesture a hand is making through these names.
            var claims = HandClaims();
            _gesture = new Dictionary<Hand, string>
            {
                { Hand.Left, claims[Hand.Left].Count > 0 ? "Hands/Left" : "GestureLeft" },
                { Hand.Right, claims[Hand.Right].Count > 0 ? "Hands/Right" : "GestureRight" },
            };

            fx.Int("GestureLeft").Int("GestureRight")
                .Bool(UserFaceTracking).Bool(UserEyeTracking)
                .Bool(TrackingEnabled, true)
                .Bool(Afk).Bool(Away)
                .Int(BlinkPick);

            fx.Layer("Base").State("Idle");
            GestureLayer(fx, Hand.Left, gestures, shapes, tiles, renderers);
            GestureLayer(fx, Hand.Right, gestures, shapes, tiles, renderers);
            foreach (var region in GestureLayout.TrackedRegions) HandoverLayer(fx, region, gestures);
            BlinkLayer(fx, shapes.Mesh, gestures);
            OutfitLayers(fx, tiles, renderers);
            PoseLayer(fx, gestures, tiles);
            // Last: nothing may come before the two gesture layers, and a frame's delay is nothing here.
            foreach (var hand in new[] { Hand.Left, Hand.Right }) HandLayer(fx, hand, claims[hand]);

            fx.Save();
        }

        /// <summary>
        /// The animator parameter each hand's gesture is read from: VRChat's
        /// own, or the one <see cref="HandLayer"/> keeps for a hand that
        /// features use as a button. Set by <see cref="Rebuild"/>.
        /// </summary>
        private static Dictionary<Hand, string> _gesture;

        /// <summary>How long a hand goes on resting after a feature lets go of it, if it has not relaxed by then.</summary>
        private const float HandRelease = 1.2f;

        /// <summary>
        /// The parameters that say a hand is in use as a button, by hand:
        /// every <see cref="WirenookHandClaim"/> on a feature any variant
        /// lists. The controller is shared by all variants, so it knows them
        /// all; in a variant without the feature the parameter is never on.
        /// </summary>
        private static Dictionary<Hand, List<string>> HandClaims()
        {
            var claims = new Dictionary<Hand, List<string>> { { Hand.Left, new List<string>() }, { Hand.Right, new List<string>() } };
            foreach (var path in CassSpec.Variants().Variants.SelectMany(variant => variant.Features).Distinct())
            {
                var feature = AssetDatabase.LoadAssetAtPath<GameObject>(path);
                if (feature == null) continue;
                foreach (var claim in feature.GetComponentsInChildren<WirenookHandClaim>(true))
                {
                    if (string.IsNullOrWhiteSpace(claim.parameter)) continue;
                    var list = claims[claim.hand == WirenookHand.Left ? Hand.Left : Hand.Right];
                    if (!list.Contains(claim.parameter)) list.Add(claim.parameter);
                }
            }

            foreach (var list in claims.Values) list.Sort(string.CompareOrdinal);
            return claims;
        }

        /// <summary>
        /// Keeps the gesture a hand counts as making, for a hand that some
        /// feature uses as a button (a trigger pull that pings, or sets
        /// something down). While any of the features' parameters is on,
        /// that is no gesture at all, so the click is not also a grin; it
        /// stays so afterwards until the hand has relaxed, or a moment has
        /// passed, so that the fist that confirmed is never read as an
        /// expression either. Otherwise it is the gesture VRChat reports.
        ///
        /// Every state sets the parameter with a driver, and drivers that
        /// are not marked local run for every viewer, so everyone's copy of
        /// the avatar agrees. The expressions, the blink, the tracking
        /// hand-over and the ear poses all read this parameter for such a
        /// hand. A hand no feature claims is read from VRChat directly and
        /// has no layer.
        /// </summary>
        private static void HandLayer(ControllerBuilder fx, Hand hand, List<string> claims)
        {
            if (claims.Count == 0) return;
            var source = hand == Hand.Left ? "GestureLeft" : "GestureRight";
            var kept = _gesture[hand];
            fx.Int(kept);
            foreach (var claim in claims) fx.Bool(claim);

            void Keep(StateBuilder state, int value) => state.Behaviour<VRCAvatarParameterDriver>(driver =>
            {
                driver.localOnly = false;
                driver.parameters = new List<VRC_AvatarParameterDriver.Parameter>
                {
                    new VRC_AvatarParameterDriver.Parameter { type = VRC_AvatarParameterDriver.ChangeType.Set, name = kept, value = value },
                };
            });

            var layer = fx.Layer("Hand In Use: " + hand);
            // The first state is the layer's default: a free hand making no gesture.
            var free = Enumerable.Range(0, 8).Select(value =>
            {
                var state = layer.State("Free " + value);
                Keep(state, value);
                return state;
            }).ToList();
            var busy = layer.State("In Use");
            Keep(busy, 0);
            var releasing = layer.State("Let Go", fx.Clip("hand let go", clip => clip.Hold(HandRelease)));

            foreach (var from in Enumerable.Range(0, 8))
            {
                foreach (var to in Enumerable.Range(0, 8).Where(value => value != from))
                    free[from].To(free[to]).Equal(source, to);
            }

            var claimed = layer.Any(busy);
            for (var i = 0; i < claims.Count; i++)
            {
                if (i > 0) claimed.Or();
                claimed.IfTrue(claims[i]);
            }

            var letGo = busy.To(releasing);
            foreach (var claim in claims) letGo.IfFalse(claim);
            releasing.To(free[0]).Equal(source, 0);
            foreach (var value in Enumerable.Range(1, 7)) releasing.To(free[value]).AfterTime(1f).Equal(source, value);
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
            var parameter = _gesture[hand];
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

            // One expression at a time. Two recipes laid over each other
            // make a face neither of them meant, so while the right hand
            // holds an expression the left hand's layer rests.
            var yieldsTo = hand == Hand.Left
                ? gestures.For(Hand.Right).Keys.OrderBy(value => value).ToList()
                : new List<int>();
            foreach (var value in yieldsTo) toNeutral.Or().Equal(_gesture[Hand.Right], value);

            foreach (var pair in mapped.OrderBy(entry => entry.Key))
            {
                var expression = gestures.Expressions[pair.Value];
                var full = layer.State(expression.Label, ExpressionClip(fx, expression, false, shapes, tiles, renderers));
                var tracked = layer.State(expression.Label + " (tracked)", ExpressionClip(fx, expression, true, shapes, tiles, renderers));

                var toTracked = layer.Any(tracked).Fade(ExpressionFade)
                    .Equal(parameter, pair.Key).IfTrue(TrackingEnabled).IfTrue(UserFaceTracking);
                foreach (var value in yieldsTo) toTracked.NotEqual(_gesture[Hand.Right], value);
                var toFull = layer.Any(full).Fade(ExpressionFade)
                    .Equal(parameter, pair.Key).IfFalse(TrackingEnabled);
                foreach (var value in yieldsTo) toFull.NotEqual(_gesture[Hand.Right], value);
                toFull.Or().Equal(parameter, pair.Key).IfFalse(UserFaceTracking);
                foreach (var value in yieldsTo) toFull.NotEqual(_gesture[Hand.Right], value);
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
                foreach (var gesture in left) toTracked.NotEqual(_gesture[Hand.Left], gesture);
                foreach (var gesture in right) toTracked.NotEqual(_gesture[Hand.Right], gesture);
            }

            var toAnimated = tracked.To(animated).IfFalse(TrackingEnabled);
            toAnimated.Or();
            foreach (var source in Sources(region)) toAnimated.IfFalse(source);
            foreach (var gesture in left) toAnimated.Or().Equal(_gesture[Hand.Left], gesture);
            foreach (var gesture in right) toAnimated.Or().Equal(_gesture[Hand.Right], gesture);
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
            foreach (var gesture in left) stop.Or().Equal(_gesture[Hand.Left], gesture);
            foreach (var gesture in right) stop.Or().Equal(_gesture[Hand.Right], gesture);

            var resume = suppressed.To(pick).IfFalse(TrackingEnabled);
            foreach (var gesture in left) resume.NotEqual(_gesture[Hand.Left], gesture);
            foreach (var gesture in right) resume.NotEqual(_gesture[Hand.Right], gesture);
            resume.Or().IfFalse(UserFaceTracking).IfFalse(UserEyeTracking);
            foreach (var gesture in left) resume.NotEqual(_gesture[Hand.Left], gesture);
            foreach (var gesture in right) resume.NotEqual(_gesture[Hand.Right], gesture);

            // Away, the eyes stay open and do not blink: the away feature
            // draws its error screen on them, and a screen does not blink.
            // Like the blink, this is the tracking eyelid shapes and not
            // the MMD ones.
            var staring = layer.State("Away", fx.Clip("away eyes", clip =>
                clip.Blendshape(mesh, "EyeClosedLeft", 0f).Blendshape(mesh, "EyeClosedRight", 0f)));
            WhileAway(layer, staring, pick, 0.1f);
        }

        /// <summary>
        /// Gives a layer a state it holds for as long as the wearer is away,
        /// whatever else it would be doing. Call it last: the any-state
        /// transitions the layer already has are told to stand down while
        /// away, or they would pull it straight back out.
        /// </summary>
        private static void WhileAway(LayerBuilder layer, StateBuilder away, StateBuilder back, float fade)
        {
            StandDownWhileAway(layer);
            layer.Any(away).Fade(fade).IfTrue(Afk).Or().IfTrue(Away);
            away.To(back).Fade(fade).IfFalse(Afk).IfFalse(Away);
        }

        /// <summary>Keeps every any-state transition a layer has so far from firing while the wearer is away, by either sign.</summary>
        private static void StandDownWhileAway(LayerBuilder layer)
        {
            foreach (var transition in layer.Machine.anyStateTransitions)
            {
                transition.AddCondition(AnimatorConditionMode.IfNot, 0f, Afk);
                transition.AddCondition(AnimatorConditionMode.IfNot, 0f, Away);
            }
        }

        /// <summary>
        /// Ears and tail follow the hand gestures too, as bone poses from
        /// gestures.json. They get a layer of their own rather than riding
        /// in the expression clips: the two gesture layers are the ones MMD
        /// worlds silence, and with one layer per hand a neutral right hand
        /// would write the rest pose over whatever the left hand asked for.
        /// Here one state machine reads both hands and the right hand wins
        /// only when its expression has a pose.
        ///
        /// A pose is stored per bone as a turn about the avatar's axes; it
        /// is converted here to the local rotation each bone needs, measured
        /// on the model at rest. The PhysBones on these chains are marked as
        /// animated, so physics swings around the pose instead of the rest.
        /// </summary>
        private static void PoseLayer(ControllerBuilder fx, GestureLayout gestures, TileLayout tiles)
        {
            if (gestures.Poses.Count == 0) return;
            var model = AssetDatabase.LoadAssetAtPath<GameObject>(CassSpec.ModelPath);
            if (model == null) throw new System.IO.FileNotFoundException("Export the model from Blender first: " + CassSpec.ModelPath);
            var skeleton = CassSpec.Skeleton();

            // A garment can ask for the poses to be held another way while it
            // is worn (the hat, whose brim the ears stand in). Each pose is
            // then two states, and which one is entered goes by the garment's
            // own switch.
            if (gestures.PosesWhile.Count > 1)
                throw new InvalidOperationException("gestures.json gives poses for more than one garment; the pose layer knows how to follow one.");
            var garment = gestures.PosesWhile.Keys.FirstOrDefault();
            var worn = default(Condition);
            if (garment != null)
            {
                var shown = TileLayout.ShownWhen(tiles.Get(garment));
                if (shown.Count != 1)
                    throw new InvalidOperationException("Poses can follow a garment with a switch of its own; " + garment + " is shown by " + shown.Count + " conditions.");
                worn = shown[0];
            }

            var names = gestures.Poses.Keys.ToList();
            var free = names.ToDictionary(pose => pose, pose => gestures.ExpandPose(pose, skeleton.IsExtra));
            var under = names.Where(pose => garment != null && gestures.PosesWhile[garment].ContainsKey(pose))
                .ToDictionary(pose => pose, pose => gestures.ExpandPose(pose, skeleton.IsExtra, garment));
            var transforms = model.GetComponentsInChildren<Transform>(true);
            // Every clip writes every posed bone, so no pose can leave another's bones where they were.
            var bones = free.Values.Concat(under.Values).SelectMany(pose => pose.Keys).Distinct().OrderBy(name => name)
                .Select(name => transforms.FirstOrDefault(transform => transform.name == name) ??
                                throw new InvalidOperationException("The model has no bone named \"" + name + "\"."))
                .ToList();

            AnimationClip Clip(string name, Dictionary<string, BoneTurn> turns) => fx.Clip("pose " + name, clip =>
            {
                foreach (var bone in bones)
                {
                    var turn = default(BoneTurn);
                    turns?.TryGetValue(bone.name, out turn);
                    var rotation = Turned(model.transform, bone, turn);
                    var path = AnimationUtility.CalculateTransformPath(bone, model.transform);
                    clip.Constant(path, typeof(Transform), "m_LocalRotation.x", rotation.x)
                        .Constant(path, typeof(Transform), "m_LocalRotation.y", rotation.y)
                        .Constant(path, typeof(Transform), "m_LocalRotation.z", rotation.z)
                        .Constant(path, typeof(Transform), "m_LocalRotation.w", rotation.w);
                }
            });

            var layer = fx.Layer("Poses");
            var rest = layer.State("Rest", Clip("rest", null));
            var held = gestures.Expressions.Values.Select(expression => expression.Pose)
                .Append(gestures.Poses.ContainsKey(AwayPose) ? AwayPose : null).Where(pose => pose != null).Distinct()
                .OrderBy(pose => pose).ToList();
            var states = held.ToDictionary(pose => pose, pose => layer.State(pose, Clip(pose, free[pose])));
            var statesUnder = held.Where(under.ContainsKey)
                .ToDictionary(pose => pose, pose => layer.State(pose + " under " + garment, Clip(pose + " under " + garment, under[pose])));

            // One transition for a pose that is held one way, two for a pose the garment changes.
            IEnumerable<TransitionBuilder> Into(string pose, float fade)
            {
                if (pose == null || !statesUnder.ContainsKey(pose))
                {
                    yield return layer.Any(pose == null ? rest : states[pose]).Fade(fade);
                    yield break;
                }

                yield return layer.Any(states[pose]).Fade(fade).When(worn.Parameter, worn.Value ? AnimatorConditionMode.IfNot : AnimatorConditionMode.If);
                yield return layer.Any(statesUnder[pose]).Fade(fade).When(worn.Parameter, worn.Value ? AnimatorConditionMode.If : AnimatorConditionMode.IfNot);
            }

            for (var right = 0; right <= 7; right++)
            {
                // PoseFor ignores the left hand whenever the right one has a pose.
                var decided = gestures.PoseFor(0, right);
                if (decided != null && gestures.For(Hand.Right).ContainsKey(right) &&
                    gestures.Expressions[gestures.For(Hand.Right)[right]].Pose != null)
                {
                    foreach (var transition in Into(decided, PoseFade)) transition.Equal(_gesture[Hand.Right], right);
                    continue;
                }

                for (var left = 0; left <= 7; left++)
                {
                    foreach (var transition in Into(gestures.PoseFor(left, right), PoseFade))
                        transition.Equal(_gesture[Hand.Right], right).Equal(_gesture[Hand.Left], left);
                }
            }

            // Away, the ears hang. The transitions the layer has so far stand
            // down while away, or they would pull it straight back out.
            if (gestures.Poses.ContainsKey(AwayPose))
            {
                StandDownWhileAway(layer);
                // Each way into the pose once for each sign of being away.
                foreach (var sign in new[] { Afk, Away })
                {
                    foreach (var transition in Into(AwayPose, 0.5f)) transition.IfTrue(sign);
                }

                states[AwayPose].To(rest).Fade(0.5f).IfFalse(Afk).IfFalse(Away);
                if (statesUnder.TryGetValue(AwayPose, out var hanging)) hanging.To(rest).Fade(0.5f).IfFalse(Afk).IfFalse(Away);
            }
        }

        /// <summary>The pose from gestures.json the ears and tail take while the wearer is away.</summary>
        private const string AwayPose = "droop";

        /// <summary>
        /// The local rotation that turns a bone, from where it rests, about
        /// the avatar's axes. "Out" leans away from the middle of the body,
        /// so it and the twist change sign with the side the bone is on.
        /// </summary>
        private static Quaternion Turned(Transform root, Transform bone, BoneTurn turn)
        {
            // Unity avatars face +Z with their left at -X; a bone on the centre line counts as left.
            var side = root.InverseTransformPoint(bone.position).x > 1e-4f ? -1f : 1f;
            var delta = Quaternion.AngleAxis(turn.Twist * side, Vector3.up) *
                        Quaternion.AngleAxis(turn.Out * side, Vector3.forward) *
                        Quaternion.AngleAxis(turn.Forward, Vector3.right);
            var rest = Quaternion.Inverse(root.rotation) * bone.rotation;
            return bone.localRotation * (Quaternion.Inverse(rest) * delta * rest);
        }

        /// <summary>
        /// One layer per switched tile, and one per body zone a garment can
        /// cover. A tile is shown while everything its rule asks for holds
        /// (see <see cref="TileToggle"/>). A zone is drawn only while no
        /// garment over it is shown, so two outfits that both cover the torso
        /// cannot disagree about it.
        ///
        /// A garment that hangs on physics chains of its own (skeleton.json,
        /// `tile`) has their PhysBone switched with it, so the chains are
        /// only simulated while there is cloth on them to see.
        /// </summary>
        private static void OutfitLayers(ControllerBuilder fx, TileLayout tiles, List<string> renderers)
        {
            foreach (var parameter in tiles.Defaults()) fx.Bool(parameter.Parameter, parameter.Value);

            var model = AssetDatabase.LoadAssetAtPath<GameObject>(CassSpec.ModelPath);
            if (model == null) throw new System.IO.FileNotFoundException("Export the model from Blender first: " + CassSpec.ModelPath);
            var bones = model.GetComponentsInChildren<Transform>(true);
            var chains = CassSpec.Skeleton().ChainRoots().Where(chain => chain.Tile != null)
                .ToLookup(chain => tiles.Get(chain.Tile).Id, chain => AnimationUtility.CalculateTransformPath(
                    bones.FirstOrDefault(bone => bone.name == chain.Name) ??
                    throw new InvalidOperationException("The model has no bone named \"" + chain.Name + "\"."), model.transform));

            foreach (var tile in tiles.Tiles.Where(candidate => candidate.Toggle != null))
            {
                var shown = TileLayout.ShownWhen(tile);
                // Unity rejects dots in state machine names.
                var layer = fx.Layer("Outfit: " + tile.Id.Replace('.', ' '));
                TileSwitch(fx, layer, tile, renderers, chains[tile.Id].ToList(), tile.Shown,
                    show => AnyOf(show, new List<List<Condition>> { shown }),
                    hide => AnyOf(hide, shown.Select(condition => new List<Condition> { condition.Opposite }).ToList()));
            }

            var resting = tiles.Resolve();
            foreach (var zone in tiles.Zones())
            {
                var covers = tiles.Covering(zone.Id).Where(tile => tile.Toggle != null).Select(TileLayout.ShownWhen).ToList();
                if (covers.Count == 0) continue;

                var layer = fx.Layer("Zone: " + zone.Id.Replace('.', ' '));
                TileSwitch(fx, layer, zone, renderers, new List<string>(), resting[zone.Id],
                    show => AnyOf(show, TileLayout.NoneOf(covers)),
                    hide => AnyOf(hide, covers));
            }
        }

        /// <summary>
        /// Makes a transition fire when every condition of any one set holds.
        /// With no sets it must never fire, and a transition with no
        /// conditions fires at once, so it is given two that contradict.
        /// </summary>
        private static void AnyOf(TransitionBuilder transition, List<List<Condition>> sets)
        {
            if (sets.Count == 0)
            {
                transition.IfTrue(TrackingEnabled).IfFalse(TrackingEnabled);
                return;
            }

            for (var i = 0; i < sets.Count; i++)
            {
                if (i > 0) transition.Or();
                foreach (var condition in sets[i])
                {
                    if (condition.Value) transition.IfTrue(condition.Parameter);
                    else transition.IfFalse(condition.Parameter);
                }
            }
        }

        private static void TileSwitch(ControllerBuilder fx, LayerBuilder layer, Tile tile, List<string> renderers,
            List<string> chains, bool startsShown, Action<TransitionBuilder> whenShown, Action<TransitionBuilder> whenHidden)
        {
            AnimationClip Clip(bool shown) => fx.Clip(tile.Id + (shown ? " shown" : " hidden"), clip =>
            {
                foreach (var renderer in renderers)
                    clip.Material<SkinnedMeshRenderer>(renderer, ToonMaterial.TileProperty(tile.Column, tile.Row), shown ? 0f : 1f);
                foreach (var chain in chains)
                    clip.Constant(chain, typeof(VRCPhysBone), "m_Enabled", shown ? 1f : 0f);
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
