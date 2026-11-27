using System.Collections.Generic;
using System.Linq;
using nadena.dev.modular_avatar.core;
using UnityEngine;
using VRC.SDK3.Avatars.Components;
using VRC.SDKBase;
using Wirenook.AdventureTools.Editor;
using Wirenook.Assets.Editor;
using Wirenook.SelectiveAnimation.Core;
using Wirenook.SelectiveAnimation.Editor;
using Wirenook.SkillChecks;
using Wirenook.SkillChecks.Avatar.Editor;

namespace Wirenook.Meta.Crypt.Editor
{
    /// <summary>Curves the pieces share.</summary>
    internal static class Curves
    {
        public static AnimationCurve Flat(float seconds, float value) => AnimationCurve.Constant(0f, seconds, value);

        /// <summary>Holds each value until the next key.</summary>
        public static AnimationCurve Steps(params (float time, float value)[] keys)
        {
            return new AnimationCurve(keys.Select(key => new Keyframe(key.time, key.value, float.PositiveInfinity, float.PositiveInfinity)).ToArray());
        }

        public static AnimationCurve Eased(params (float time, float value)[] keys)
        {
            var curve = new AnimationCurve(keys.Select(key => new Keyframe(key.time, key.value)).ToArray());
            for (var key = 0; key < curve.length; key++) curve.SmoothTangents(key, 0f);
            return curve;
        }

        /// <summary>Straight lines from key to key.</summary>
        public static AnimationCurve Lines(params (float time, float value)[] keys)
        {
            var frames = new Keyframe[keys.Length];
            for (var index = 0; index < keys.Length; index++)
            {
                var into = index > 0 ? (keys[index].value - keys[index - 1].value) / (keys[index].time - keys[index - 1].time) : 0f;
                var outOf = index + 1 < keys.Length ? (keys[index + 1].value - keys[index].value) / (keys[index + 1].time - keys[index].time) : 0f;
                frames[index] = new Keyframe(keys[index].time, keys[index].value, into, outOf);
            }

            return new AnimationCurve(frames);
        }

        /// <summary>
        /// Goes from one value to another again and again, starting over
        /// at once each time, for <paramref name="total"/> seconds. The
        /// offset is how far into its first run it starts.
        /// </summary>
        public static AnimationCurve Saw(float period, float total, float from, float to, float offset = 0f)
        {
            var keys = new List<(float, float)>();
            const float snap = 0.001f;
            var start = -offset * period;
            float Along(float time) => Mathf.Repeat((time - start) / period, 1f);
            keys.Add((0f, from + (to - from) * Along(0f)));
            for (var turn = start + period; turn < total - snap; turn += period)
            {
                if (turn <= snap) continue;
                keys.Add((turn - snap, to));
                keys.Add((turn, from));
            }

            // Ends where it began, so the loop has no seam: a run that ends
            // with the clip ends at its far value, and starts over as the
            // clip does.
            var last = Along(total);
            keys.Add((total, last < 0.0005f || last > 0.9995f ? to : from + (to - from) * last));
            return Lines(keys.ToArray());
        }
    }

    /// <summary>
    /// Zones that are hot, cold or windy: a ring of dashes on the ground
    /// in the element's colour, motes that rise, fall or blow round inside
    /// it, on PC a faint tint over everything in it, and a contact sender
    /// with the trait, so that anything that reacts to VRChat's standard
    /// <c>Hot</c>, <c>Cold</c> or <c>Wind</c> tag reacts to standing in one.
    ///
    /// VRChat allows a contact three metres of radius at most, so these
    /// zones go from 0.75 m to 3 m: one that looked bigger than it acts
    /// would be a lie. The size is the zone's value on the stage.
    /// </summary>
    public sealed class ElementPiece : ICryptPiece
    {
        public sealed class Element
        {
            public string Name;
            public string Tag;
            public string Swatch;
            public string Mote;
            public string Icon;
            public Color Tint;
        }

        public static readonly Element[] Elements =
        {
            new Element { Name = "Hot", Tag = SkillTags.Hot, Swatch = "orange", Mote = "glow-warm", Icon = "trait-fire", Tint = new Color(1f, 0.42f, 0.1f) },
            new Element { Name = "Cold", Tag = SkillTags.Cold, Swatch = "ice", Mote = "white", Icon = "trait-ice", Tint = new Color(0.45f, 0.78f, 1f) },
            new Element { Name = "Windy", Tag = SkillTags.Wind, Swatch = "mint", Mote = "white", Icon = "trait-wind", Tint = new Color(0.62f, 1f, 0.82f) },
        };

        public const float SmallestRadius = 0.75f;
        public const float LargestRadius = 3f;

        /// <summary>Seconds the motes take to come round to where they began.</summary>
        public const float MoteSeconds = 12f;

        public static string ThingName(Element element) => element.Name + " Zone";

        private readonly Dictionary<Element, (Transform bone, Transform size, Transform[] motes, GameObject contacts)> _built =
            new Dictionary<Element, (Transform, Transform, Transform[], GameObject)>();

        public void Things(StagePlan plan)
        {
            foreach (var element in Elements) plan.Thing(ThingName(element), value: 0.5f, rehearsed: true);
        }

        public void Build(CryptSet crypt)
        {
            foreach (var element in Elements)
            {
                var bone = crypt.Stage.Hold(ThingName(element), crypt.Stage[ThingName(element)]);
                var size = GameMasterBuild.Bone(bone.gameObject, "Size", Vector3.zero);
                var first = GameMasterBuild.Bone(size.gameObject, "Motes", Vector3.zero);
                var second = GameMasterBuild.Bone(size.gameObject, "Motes 2", Vector3.zero);

                var solid = crypt.Solid.On(size).Colour(element.Swatch);
                const int dashes = 12;
                for (var dash = 0; dash < dashes; dash++)
                    solid.Bend(1f - 0.02f, 1f, 0f, 0.02f, dash * 360f / dashes, 200f / dashes, 2);

                Motes(crypt.Solid, element, first, 0f);
                Motes(crypt.Solid, element, second, 0.5f);
                crypt.Solid.At(Vector3.zero);

                var tint = crypt.Effect(GameMasterBuild.Material(CryptBuild.TintMaterial(element.Name)));
                crypt.Effects.On(size).Slot(tint).Colour("").Slice(0f, 1f, 0f, 360f, 8, 16);

                // The trait fills the zone: the sender is as big as the size bone's scale makes it.
                var contacts = crypt.Contacts(size, new Vector3(0f, 0.5f, 0f));
                CryptSet.Sender(contacts, 1f, element.Tag);
                _built[element] = (bone, size, new[] { first, second }, contacts);
            }
        }

        /// <summary>Six motes scattered about the zone, in a metre's radius; the second set is the first turned half way round.</summary>
        private static void Motes(ShapeMesh mesh, Element element, Transform bone, float turned)
        {
            mesh.On(bone).Colour(element.Mote);
            for (var mote = 0; mote < 6; mote++)
            {
                var around = (mote / 6f + turned / 6f + (mote % 2) * 0.07f) * 2f * Mathf.PI;
                var out_ = 0.25f + 0.11f * ((mote * 5) % 6);
                var at = new Vector3(Mathf.Cos(around) * out_, 0f, Mathf.Sin(around) * out_);
                switch (element.Name)
                {
                    case "Hot":
                        // An ember: a small diamond.
                        mesh.At(at).Ball(Vector3.zero, 0.035f, 2, 4);
                        break;
                    case "Cold":
                        // A flake: three thin bars crossed.
                        mesh.At(at, Quaternion.Euler(mote * 31f, mote * 47f, 0f));
                        mesh.Box(Vector3.zero, new Vector3(0.09f, 0.012f, 0.012f))
                            .Box(Vector3.zero, new Vector3(0.012f, 0.09f, 0.012f))
                            .Box(Vector3.zero, new Vector3(0.012f, 0.012f, 0.09f));
                        break;
                    default:
                        // A streak of air: a thin arc about the middle, at a height of its own.
                        mesh.At(new Vector3(0f, 0.25f + 0.2f * mote, 0f));
                        mesh.Bend(out_ + 0.25f, out_ + 0.262f, 0f, 0.012f, mote * 67f + turned * 180f, 55f, 4);
                        break;
                }
            }
        }

        public void Layers(CryptSet crypt)
        {
            var fx = crypt.Fx;
            foreach (var element in Elements)
            {
                var name = ThingName(element);
                var thing = crypt.Stage[name];
                var (bone, size, motes, contacts) = _built[element];
                var sizePath = crypt.Path(size);
                fx.Layer(name + " Size").State("Size", fx.Clip(name.ToLowerInvariant() + " size", clip =>
                    PopToggle.Scale(clip, sizePath, AnimationCurve.Linear(0f, SmallestRadius, 1f, LargestRadius)))).MotionTime(thing.Value);

                crypt.Stage.Show(fx, name, new[] { crypt.Path(bone) }, thing.Shown, (clip, phase) =>
                {
                    if (phase != "on") return;
                    for (var set = 0; set < motes.Length; set++)
                    {
                        var path = crypt.Path(motes[set]);
                        var offset = set * 0.5f;
                        switch (element.Name)
                        {
                            case "Hot":
                                // Embers rise and dwindle.
                                clip.Curve(path, typeof(Transform), "m_LocalPosition.y", Curves.Saw(3f, MoteSeconds, 0.05f, 1.1f, offset));
                                PopToggle.Scale(clip, path, Curves.Saw(3f, MoteSeconds, 1f, 0.15f, offset));
                                break;
                            case "Cold":
                                // Flakes fall, turning.
                                clip.Curve(path, typeof(Transform), "m_LocalPosition.y", Curves.Saw(4f, MoteSeconds, 1.3f, 0.03f, offset));
                                clip.Curve(path, typeof(Transform), "localEulerAnglesRaw.y", AnimationCurve.Linear(0f, 0f, MoteSeconds, 360f));
                                break;
                            default:
                                // The air goes round, the two sets at different paces.
                                clip.Curve(path, typeof(Transform), "localEulerAnglesRaw.y",
                                    AnimationCurve.Linear(0f, 0f, MoteSeconds, 360f * (set == 0 ? 4f : 3f)));
                                break;
                        }
                    }

                    clip.Loop();
                });
                crypt.ContactsLayer(name, contacts, thing);
            }
        }

        public void Menu(CryptSet crypt, GameObject parent)
        {
            var folder = FeaturePrefab.Child(parent, "Menu Elements");
            FeaturePrefab.MenuFolder(folder, "Elements", "zone");
            foreach (var element in Elements)
            {
                var thing = crypt.Stage[ThingName(element)];
                var own = crypt.MenuThing(folder, thing, element.Name, element.Icon);
                crypt.Stage.MenuValue(FeaturePrefab.Child(own, "Menu Size"), thing, "Size", "zone");
            }
        }
    }

    /// <summary>
    /// A danger zone: it shows where it will strike before it does. A dark
    /// disc spreads from the middle of the ring for two seconds, and when
    /// it reaches the edge the ground jabs upward and, for a third of a
    /// second, the zone carries <c>Damage</c> and <c>DamageBlunt</c>.
    ///
    /// Nothing in it glows, flashes or is red: the warning is a slow, dark
    /// shape and the strike a dull one, for the sake of anyone a flash
    /// would hurt.
    ///
    /// Every client times the strike itself from the one synced bit that
    /// says "striking", so two people see it land within a network update
    /// of each other, and each is hit when they see it land.
    /// </summary>
    public sealed class DangerPiece : ICryptPiece
    {
        public const string ThingName = "Danger";

        public const float TelegraphSeconds = 2f;
        public const float HitSeconds = 0.35f;
        public const float RecoverSeconds = 0.8f;

        /// <summary>Seconds "strike once" holds the synced bit up: long enough for every client to have heard it.</summary>
        public const float OnceSeconds = 1f;

        public static string Striking(string prefix) => prefix + "/Striking";
        public static string Once(string prefix) => prefix + "/StrikeOnce";

        private Transform _bone;
        private Transform _size;
        private Transform _fill;
        private Transform _spikes;
        private GameObject _hit;

        public void Things(StagePlan plan)
        {
            plan.Thing(ThingName, value: 0.5f, rehearsed: true);
        }

        public void Build(CryptSet crypt)
        {
            _bone = crypt.Stage.Hold(ThingName, crypt.Stage[ThingName]);
            _size = GameMasterBuild.Bone(_bone.gameObject, "Size", Vector3.zero);
            _fill = GameMasterBuild.Bone(_size.gameObject, "Fill", Vector3.zero);
            _spikes = GameMasterBuild.Bone(_size.gameObject, "Spikes", Vector3.zero);

            // The edge: where it reaches. A plain ring, and eight teeth pointing in.
            var solid = crypt.Solid.On(_size).Colour("lilac-3").Bend(0.97f, 1f, 0f, 0.025f, 0f, 360f, 32);
            for (var tooth = 0; tooth < 8; tooth++)
                solid.Colour("violet").Bend(0.86f, 0.97f, 0f, 0.015f, tooth * 45f - 3f, 6f, 1);

            // The warning: a dark disc that grows to fill the ring.
            crypt.Solid.On(_fill).Colour("night-3").Ring(0f, 0.97f, segments: 24, y: 0.012f);

            // The strike: blunt teeth of the ground itself.
            crypt.Solid.On(_spikes).Colour("soot");
            for (var spike = 0; spike < 7; spike++)
            {
                var around = spike * 360f / 7f * Mathf.Deg2Rad;
                var out_ = spike == 0 ? 0f : 0.35f + 0.25f * (spike % 2);
                var height = 0.5f + 0.12f * (spike % 3);
                crypt.Solid.At(new Vector3(Mathf.Cos(around) * out_, 0f, Mathf.Sin(around) * out_), Quaternion.Euler(0f, spike * 40f, 0f))
                    .Box(new Vector3(0f, height * 0.5f, 0f), new Vector3(0.16f, height, 0.16f))
                    .Box(new Vector3(0.01f, height + 0.05f, -0.01f), new Vector3(0.1f, 0.1f, 0.1f))
                    .Box(new Vector3(0f, 0.04f, 0f), new Vector3(0.22f, 0.08f, 0.22f));
            }

            crypt.Solid.At(Vector3.zero);

            _hit = crypt.Contacts(_size, new Vector3(0f, 0.4f, 0f), "Hit");
            CryptSet.Sender(_hit, 1f, SkillTags.Damage, SkillTags.DamageBlunt);
            WirenookSounds.Source(_bone.gameObject, shared: false);
        }

        public void Layers(CryptSet crypt)
        {
            var fx = crypt.Fx;
            var thing = crypt.Stage[ThingName];
            var striking = Striking(crypt.Prefix);
            var once = Once(crypt.Prefix);
            fx.Bool(striking).Bool(once).Bool("IsLocal");

            var sizePath = crypt.Path(_size);
            fx.Layer("Danger Size").State("Size", fx.Clip("danger size", clip =>
                    PopToggle.Scale(clip, sizePath, AnimationCurve.Linear(0f, ElementPiece.SmallestRadius, 1f, ElementPiece.LargestRadius))))
                .MotionTime(thing.Value);
            crypt.Stage.Show(fx, ThingName, new[] { crypt.Path(_bone) }, thing.Shown);

            var fillPath = crypt.Path(_fill);
            var spikesPath = crypt.Path(_spikes);
            var hitPath = crypt.Path(_hit.transform);
            AnimationClip Phase(string name, float seconds, AnimationCurve fill, AnimationCurve spikes, bool hits) =>
                fx.Clip("danger " + name, clip =>
                {
                    PopToggle.Scale(clip, fillPath, fill);
                    PopToggle.Scale(clip, spikesPath, spikes);
                    clip.Active(hitPath, hits);
                    clip.Hold(seconds);
                });

            var layer = fx.Layer("Danger Strike");
            var idle = layer.State("Idle", Phase("idle", 1f / 60f, Curves.Flat(1f / 60f, 0f), Curves.Flat(1f / 60f, 0f), false));
            var telegraph = layer.State("Telegraph", Phase("telegraph", TelegraphSeconds,
                AnimationCurve.Linear(0f, 0.02f, TelegraphSeconds, 1f), Curves.Flat(TelegraphSeconds, 0f), false));
            var hit = layer.State("Hit", Phase("hit", HitSeconds,
                Curves.Flat(HitSeconds, 1f), Curves.Eased((0f, 0f), (0.08f, 1f), (HitSeconds, 1f)), true));
            var recover = layer.State("Recover", Phase("recover", RecoverSeconds,
                Curves.Eased((0f, 1f), (RecoverSeconds, 0f)), Curves.Eased((0f, 1f), (RecoverSeconds * 0.6f, 0f), (RecoverSeconds, 0f)), false));
            WirenookSounds.PlayOnEnter(hit, crypt.Path(_bone) + "/" + WirenookSounds.SourceName, "thud");

            var asked = thing.Real.And(Audience.WhenTrue(striking));
            idle.To(telegraph).For(asked);
            // A warning is called off if the zone is taken away; a strike that has begun finishes.
            telegraph.To(idle).For(thing.Real.Not());
            telegraph.To(hit).AfterTime(1f);
            hit.To(recover).AfterTime(1f);
            recover.To(idle).AfterTime(1f);

            // "Strike once": the wearer's client holds the bit up for a second and lets it go.
            var single = fx.Layer("Danger Once");
            var waiting = single.State("Waiting");
            var pulse = single.State("Pulse", fx.Clip("danger once", clip => clip.Hold(OnceSeconds)));
            var release = single.State("Release");
            pulse.Behaviour<VRCAvatarParameterDriver>(driver => Drive(driver, striking, 1f));
            release.Behaviour<VRCAvatarParameterDriver>(driver => Drive(driver, striking, 0f));
            waiting.To(pulse).IfTrue("IsLocal").IfTrue(once);
            pulse.To(release).AfterTime(1f);
            release.To(waiting).IfFalse(once);
        }

        internal static void Drive(VRCAvatarParameterDriver driver, string name, float value)
        {
            driver.localOnly = true;
            driver.parameters = new List<VRC_AvatarParameterDriver.Parameter>
            {
                new VRC_AvatarParameterDriver.Parameter { type = VRC_AvatarParameterDriver.ChangeType.Set, name = name, value = value },
            };
        }

        public void Menu(CryptSet crypt, GameObject parent)
        {
            var thing = crypt.Stage[ThingName];
            crypt.Kit.Parameters.Add(FeaturePrefab.SyncedBool(Striking(crypt.Prefix)));
            crypt.Kit.Parameters.Add(GameMasterBuild.Mine(Once(crypt.Prefix), ParameterSyncType.Bool));

            var folder = crypt.MenuThing(parent, thing, "Danger", "target");
            crypt.Stage.MenuValue(FeaturePrefab.Child(folder, "Menu Size"), thing, "Size", "zone");
            var button = FeaturePrefab.Child(folder, "Menu Once");
            FeaturePrefab.MenuButton(button, "Strike once", "target", Once(crypt.Prefix));
            GameMasterBuild.Local(button);
            FeaturePrefab.MenuToggle(FeaturePrefab.Child(folder, "Menu Keep"), "Keep striking", "target", Striking(crypt.Prefix));
        }
    }

    /// <summary>
    /// A barricade of five planks between two posts. Hands on it take it
    /// apart, a plank at a time from the top, in ten seconds of touching
    /// all told; so does fire, and then it burns. It is one skill check
    /// (net.wirenook.contacts) that advances while a hand or anything
    /// tagged <c>Fire</c> or <c>Hot</c> touches it, keeps what has been
    /// done when it is let go, and stays down once it is down.
    ///
    /// An avatar cannot stop anyone walking: the barricade bars the way
    /// by agreement, like everything else at the table. The game master
    /// puts it back by taking it away and setting it out again.
    ///
    /// Its value on the stage is which way it faces.
    /// </summary>
    public sealed class BarricadePiece : ICryptPiece
    {
        public const string ThingName = "Barricade";
        public const int Planks = 5;

        /// <summary>Seconds of touching that take the whole of it down.</summary>
        public const float TakesSeconds = 10f;

        public static string Plank(int plank) => "barricade.plank." + plank;

        public AvatarCheck Check { get; private set; }

        private Transform _bone;
        private Transform _turn;
        private Transform _flames;
        private GameObject _contacts;

        public void Things(StagePlan plan)
        {
            plan.Thing(ThingName, rehearsed: true);
        }

        public void Build(CryptSet crypt)
        {
            var thing = crypt.Stage[ThingName];
            _bone = crypt.Stage.Hold(ThingName, thing);
            _turn = crypt.Turn(_bone);
            _flames = GameMasterBuild.Bone(_turn.gameObject, "Flames", new Vector3(0f, 0.2f, 0f));

            var solid = crypt.Solid.On(_turn).Colour("wood-dark")
                .Box(new Vector3(-0.98f, 0.8f, 0f), new Vector3(0.14f, 1.6f, 0.14f))
                .Box(new Vector3(0.98f, 0.8f, 0f), new Vector3(0.14f, 1.6f, 0.14f))
                .Colour("wood").Box(new Vector3(-0.98f, 1.62f, 0f), new Vector3(0.1f, 0.05f, 0.1f))
                .Box(new Vector3(0.98f, 1.62f, 0f), new Vector3(0.1f, 0.05f, 0.1f));
            for (var plank = 1; plank <= Planks; plank++)
            {
                // Nailed up in a hurry: none of them quite level.
                var height = 0.26f + 0.28f * (plank - 1);
                var tilt = new[] { 2.5f, -3f, 1.5f, -2f, 3.5f }[plank - 1];
                solid.At(new Vector3(0f, height, 0.075f * (plank % 2 == 0 ? -1f : 1f)), Quaternion.Euler(0f, 0f, tilt))
                    .Colour(plank % 2 == 0 ? "wood" : "wood-dark")
                    .Vanishing(Plank(plank), new Vector3(0f, -height, 0f))
                    .Box(Vector3.zero, new Vector3(2.1f, 0.2f, 0.05f));
                // A nail through each end, its head on the side the plank was hammered from.
                var face = plank % 2 == 0 ? -0.029f : 0.029f;
                solid.Colour("grey-dark")
                    .Box(new Vector3(-0.98f, 0.03f * (plank % 3 - 1), face), new Vector3(0.03f, 0.03f, 0.008f))
                    .Box(new Vector3(0.98f, -0.03f * (plank % 3 - 1), face), new Vector3(0.03f, 0.03f, 0.008f));
            }

            solid.Vanishing(null).At(Vector3.zero);

            // Fire along the foot of it, while it burns.
            var flames = crypt.Solid.On(_flames);
            for (var flame = 0; flame < 5; flame++)
            {
                var along = -0.8f + 0.4f * flame;
                flames.Colour(flame % 2 == 0 ? "glow-orange" : "glow-warm")
                    .At(new Vector3(along, 0.12f + 0.05f * (flame % 3), 0f), Quaternion.identity, 1f + 0.3f * (flame % 2))
                    .Ball(Vector3.zero, 0.11f, 2, 4);
            }

            flames.At(Vector3.zero);

            Check = new AvatarCheck("crypt-barricade", new CheckSpec
            {
                AdvanceRate = 1f / TakesSeconds,
                Latch = true,
            }.Need(TagGroup.AnyOf(SkillTags.Hand, SkillTags.Finger, SkillTags.Fire, SkillTags.Hot)))
            {
                Sync = true,
                // Taken away, or back behind the scenes, it is whole again.
                EmptyWhile = gone => gone.IfFalse(thing.On).Or().IfFalse(crypt.Stage.Live),
            };

            _contacts = crypt.Contacts(_turn, new Vector3(0f, 0.8f, 0f));
            AvatarSkillCheck.Receiver(_contacts, Check, 1.05f);
            WirenookSounds.Source(_bone.gameObject, shared: false);
        }

        public void Layers(CryptSet crypt)
        {
            var fx = crypt.Fx;
            var thing = crypt.Stage[ThingName];
            crypt.TurnLayer(ThingName, _turn, thing);
            crypt.Stage.Show(fx, ThingName, new[] { crypt.Path(_bone) }, thing.Shown);
            crypt.ContactsLayer(ThingName, _contacts, thing);

            // Progress takes the planks off from the top, each over the last part of its share.
            Check.Look = clip =>
            {
                for (var plank = Planks; plank >= 1; plank--)
                {
                    var order = Planks - plank;
                    var from = (order + 0.6f) / Planks;
                    var until = (order + 1f) / Planks;
                    var keys = new List<(float, float)> { (0f, 0f), (from, 0f), (until, 100f) };
                    if (until < 1f) keys.Add((1f, 100f));
                    clip.Blendshape(CryptSet.SolidName, Plank(plank), Curves.Lines(keys.ToArray()));
                }
            };
            AvatarSkillCheck.Layers(fx, Check);

            var source = crypt.Path(_bone) + "/" + WirenookSounds.SourceName;

            // A clack as each plank comes off.
            var falls = fx.Layer("Barricade Planks");
            var standing = falls.State("Standing 0");
            var first = standing;
            for (var down = 1; down <= Planks; down++)
            {
                var next = falls.State("Standing " + down);
                WirenookSounds.PlayOnEnter(next, source, "plank");
                standing.To(next).Greater(Check.Progress, down / (float)Planks - 0.002f);
                next.To(first).Less(Check.Progress, 0.05f);
                standing = next;
            }

            // Flames while fire is on it and there is anything left to burn.
            var flamesPath = crypt.Path(_flames);
            var burning = thing.Real.And(Audience.WhenBelow(Check.Progress, 0.999f))
                .And(Audience.WhenAbove(Check.Touching(SkillTags.Fire)).Or(Audience.WhenAbove(Check.Touching(SkillTags.Hot))));
            var lit = fx.Clip("barricade burning", clip =>
            {
                PopToggle.Scale(clip, flamesPath, Curves.Eased((0f, 0.85f), (0.11f, 1.1f), (0.2f, 0.9f), (0.33f, 1.15f), (0.45f, 0.85f)));
                clip.Loop();
            });
            var unlit = fx.Clip("barricade not burning", clip => PopToggle.Scale(clip, flamesPath, Curves.Flat(1f / 60f, 0f)));
            burning.Layer(fx, "Barricade Burning", lit, unlit);
        }

        public void Menu(CryptSet crypt, GameObject parent)
        {
            var thing = crypt.Stage[ThingName];
            crypt.Kit.Parameters.AddRange(AvatarSkillCheck.Parameters(Check));
            var folder = crypt.MenuThing(parent, thing, "Barricade", "shield");
            crypt.Stage.MenuValue(FeaturePrefab.Child(folder, "Menu Turn"), thing, "Turn", "reset");
        }
    }

    /// <summary>
    /// A chest with a padlock, and its key. The key is a thing of its own,
    /// which the game master sets down wherever it is to be found. A hand
    /// on the key takes it: it is gone from where it lay, and from then
    /// on a hand on the padlock opens the chest. Before that the padlock
    /// only rattles.
    ///
    /// Two skill checks: "found", which a hand completes in under half a
    /// second and which then stays complete, and "opened", which needs a
    /// hand and "found" (one check reading another, a signal). Both are
    /// synced, so the key is found for everyone when the wearer's client
    /// says so: one key for the party.
    ///
    /// The chest's value on the stage is which way it faces.
    /// </summary>
    public sealed class ChestPiece : ICryptPiece
    {
        public const string ChestName = "Chest";
        public const string KeyName = "Chest Key";
        private const string FoundSignal = "@found";

        public AvatarCheck Found { get; private set; }
        public AvatarCheck Opened { get; private set; }

        private Transform _chest;
        private Transform _turn;
        private Transform _lid;
        private Transform _shake;
        private Transform _padlock;
        private Transform _glow;
        private Transform _key;
        private Transform _bob;
        private GameObject _chestContacts;
        private GameObject _keyContacts;

        public void Things(StagePlan plan)
        {
            plan.Thing(ChestName, rehearsed: true);
            plan.Thing(KeyName, rehearsed: true);
        }

        public void Build(CryptSet crypt)
        {
            var chest = crypt.Stage[ChestName];
            var key = crypt.Stage[KeyName];
            _chest = crypt.Stage.Hold(ChestName, chest);
            _turn = crypt.Turn(_chest);
            _lid = GameMasterBuild.Bone(_turn.gameObject, "Lid", new Vector3(0f, 0.4f, -0.225f));
            _shake = GameMasterBuild.Bone(_turn.gameObject, "Padlock Shake", new Vector3(0f, 0.36f, 0.235f));
            _padlock = GameMasterBuild.Bone(_shake.gameObject, "Padlock", Vector3.zero);
            _glow = GameMasterBuild.Bone(_turn.gameObject, "Glow", new Vector3(0f, 0.34f, 0f));

            crypt.Solid.On(_turn).Colour("wood").Box(new Vector3(0f, 0.2f, 0f), new Vector3(0.7f, 0.4f, 0.45f))
                .Colour("brass").Box(new Vector3(-0.24f, 0.2f, 0f), new Vector3(0.05f, 0.41f, 0.46f))
                .Box(new Vector3(0.24f, 0.2f, 0f), new Vector3(0.05f, 0.41f, 0.46f));
            foreach (var band in new[] { -0.24f, 0.24f })
                foreach (var stud in new[] { 0.07f, 0.2f, 0.33f })
                    crypt.Solid.Colour("grey-dark").Box(new Vector3(band, stud, 0.233f), new Vector3(0.022f, 0.022f, 0.008f));
            crypt.Solid.Colour("glow-cyan");
            CryptDetail.Rune(crypt.Solid, CryptDetail.Runes[0], new Vector3(-0.135f, 0.2f, 0.225f), 0.018f);
            CryptDetail.Rune(crypt.Solid, CryptDetail.Runes[1], new Vector3(0.135f, 0.2f, 0.225f), 0.018f);
            crypt.Solid.On(_lid).Colour("wood-dark").Box(new Vector3(0f, 0.06f, 0.225f), new Vector3(0.72f, 0.12f, 0.47f))
                .Colour("brass").Box(new Vector3(-0.24f, 0.06f, 0.225f), new Vector3(0.05f, 0.13f, 0.48f))
                .Box(new Vector3(0.24f, 0.06f, 0.225f), new Vector3(0.05f, 0.13f, 0.48f))
                .Box(new Vector3(0f, 0.02f, 0.46f), new Vector3(0.12f, 0.08f, 0.02f))
                // The lid steps up towards its middle.
                .Colour("wood-dark").Box(new Vector3(0f, 0.14f, 0.225f), new Vector3(0.6f, 0.04f, 0.33f))
                .Colour("brass").Box(new Vector3(-0.24f, 0.14f, 0.225f), new Vector3(0.05f, 0.05f, 0.34f))
                .Box(new Vector3(0.24f, 0.14f, 0.225f), new Vector3(0.05f, 0.05f, 0.34f));
            // The padlock hangs from the hasp at the front: a body, and a shackle standing over it.
            crypt.Solid.On(_padlock).Colour("brass").Box(new Vector3(0f, -0.07f, 0.02f), new Vector3(0.12f, 0.1f, 0.045f))
                .Colour("soot").Box(new Vector3(0f, -0.075f, 0.044f), new Vector3(0.02f, 0.035f, 0.004f))
                .Colour("silver").At(new Vector3(0f, -0.02f, 0.02f), Quaternion.Euler(-90f, 0f, 0f))
                .Bend(0.028f, 0.044f, -0.008f, 0.008f, 0f, 180f, 6).At(Vector3.zero);
            // What is inside, once it is open.
            crypt.Solid.On(_glow).Colour("glow-warm").Ball(Vector3.zero, 0.1f, 3, 6)
                .Colour("banana").Box(new Vector3(-0.16f, -0.05f, 0.05f), new Vector3(0.09f, 0.03f, 0.09f))
                .Box(new Vector3(0.15f, -0.04f, -0.06f), new Vector3(0.09f, 0.03f, 0.09f))
                .Box(new Vector3(0.05f, -0.06f, 0.12f), new Vector3(0.09f, 0.03f, 0.09f));

            _key = crypt.Stage.Hold(KeyName, key);
            _bob = GameMasterBuild.Bone(_key.gameObject, "Bob", new Vector3(0f, 0.45f, 0f));
            // A key standing on its tip: a bow, a shaft and two teeth.
            crypt.Solid.On(_bob).Colour("brass")
                .At(new Vector3(0f, 0.13f, 0f), Quaternion.Euler(90f, 0f, 0f)).Ring(0.035f, 0.065f, segments: 10)
                .At(Vector3.zero).Box(new Vector3(0f, -0.02f, 0f), new Vector3(0.024f, 0.2f, 0.02f))
                .Box(new Vector3(0.03f, -0.1f, 0f), new Vector3(0.045f, 0.025f, 0.02f))
                .Box(new Vector3(0.024f, -0.06f, 0f), new Vector3(0.032f, 0.02f, 0.02f));

            Found = new AvatarCheck("crypt-found", new CheckSpec
            {
                AdvanceRate = 1f / 0.4f,
                IdleRate = -1f / 0.4f,
                Latch = true,
            }.Need(TagGroup.AnyOf(SkillTags.Hand, SkillTags.Finger)))
            {
                Sync = true,
                EmptyWhile = gone => gone.IfFalse(key.On).Or().IfFalse(crypt.Stage.Live),
            };
            Opened = new AvatarCheck("crypt-opened", new CheckSpec
            {
                AdvanceRate = 1f / 0.6f,
                IdleRate = -1f / 0.4f,
                Latch = true,
            }.Signal(SignalSpec.WhenComplete(FoundSignal))
                .Need(TagGroup.AnyOf(SkillTags.Hand, SkillTags.Finger))
                .Need(TagGroup.AnyOf(FoundSignal)))
            {
                Sync = true,
                EmptyWhile = gone => gone.IfFalse(chest.On).Or().IfFalse(crypt.Stage.Live),
            };
            Opened.Signals[FoundSignal] = Found;

            _keyContacts = crypt.Contacts(_bob, Vector3.zero);
            AvatarSkillCheck.Receiver(_keyContacts, Found, 0.2f);
            _chestContacts = crypt.Contacts(_turn, new Vector3(0f, 0.3f, 0.2f));
            AvatarSkillCheck.Receiver(_chestContacts, Opened, 0.3f);
            WirenookSounds.Source(_chest.gameObject, shared: false);
        }

        public void Layers(CryptSet crypt)
        {
            var fx = crypt.Fx;
            var chest = crypt.Stage[ChestName];
            var key = crypt.Stage[KeyName];
            crypt.TurnLayer(ChestName, _turn, chest);
            crypt.Stage.Show(fx, ChestName, new[] { crypt.Path(_chest) }, chest.Shown);
            crypt.ContactsLayer(ChestName, _chestContacts, chest);

            var bobPath = crypt.Path(_bob);
            crypt.Stage.Show(fx, KeyName, new[] { crypt.Path(_key) }, key.Shown);
            crypt.ContactsLayer(KeyName, _keyContacts, key);

            // Taken: the key hops and is gone. Until then it turns slowly where it lies.
            Found.Look = clip =>
            {
                PopToggle.Scale(clip, bobPath, Curves.Eased((0f, 1f), (0.5f, 1.25f), (1f, 0f)));
                clip.Curve(bobPath, typeof(Transform), "m_LocalPosition.y", Curves.Eased((0f, 0.45f), (1f, 0.9f)));
            };
            var lidPath = crypt.Path(_lid);
            var padlockPath = crypt.Path(_padlock);
            var glowPath = crypt.Path(_glow);
            Opened.Look = clip =>
            {
                // The padlock drops away first; then the lid goes back and the light comes up.
                PopToggle.Scale(clip, padlockPath, Curves.Eased((0f, 1f), (0.25f, 1f), (0.45f, 0f), (1f, 0f)));
                clip.Curve(padlockPath, typeof(Transform), "m_LocalPosition.y", Curves.Eased((0f, 0f), (0.2f, 0.03f), (0.45f, -0.3f), (1f, -0.3f)));
                clip.Curve(lidPath, typeof(Transform), "localEulerAnglesRaw.x", Curves.Eased((0f, 0f), (0.4f, 0f), (1f, -78f)));
                PopToggle.Scale(clip, glowPath, Curves.Eased((0f, 0f), (0.5f, 0f), (1f, 1f)));
            };
            AvatarSkillCheck.Layers(fx, Found);
            AvatarSkillCheck.Layers(fx, Opened);

            fx.Layer("Chest Key Turning").State("Turning", fx.Clip("chest key turning", clip =>
                clip.Curve(bobPath, typeof(Transform), "localEulerAnglesRaw.y", AnimationCurve.Linear(0f, 0f, 6f, 360f)).Loop()));

            // The padlock: it rattles under a hand that has no key, and gives to one that has.
            var source = crypt.Path(_chest) + "/" + WirenookSounds.SourceName;
            var shakePath = crypt.Path(_shake);
            var still = fx.Clip("chest padlock still", clip =>
                clip.Curve(shakePath, typeof(Transform), "localEulerAnglesRaw.z", Curves.Flat(1f / 60f, 0f)));
            var shaken = fx.Clip("chest padlock rattled", clip =>
                clip.Curve(shakePath, typeof(Transform), "localEulerAnglesRaw.z",
                    Curves.Eased((0f, 0f), (0.06f, 16f), (0.14f, -13f), (0.22f, 10f), (0.3f, -7f), (0.4f, 3f), (0.5f, 0f))));
            var touched = Audience.WhenAbove(Opened.Touching(SkillTags.Hand)).Or(Audience.WhenAbove(Opened.Touching(SkillTags.Finger)));
            var locked = chest.Real.And(Audience.WhenBelow(Found.Progress, 0.999f)).And(Audience.WhenBelow(Opened.Progress, 0.001f));
            fx.Declare(touched).Declare(locked);
            var lockLayer = fx.Layer("Chest Padlock");
            var shut = lockLayer.State("Shut", still);
            var rattle = lockLayer.State("Rattle", shaken);
            var held = lockLayer.State("Held", still);
            var open = lockLayer.State("Open", still);
            WirenookSounds.PlayOnEnter(rattle, source, "rattle");
            WirenookSounds.PlayOnEnter(open, source, "unlock");
            shut.To(rattle).For(locked.And(touched));
            rattle.To(held).AfterTime(1f);
            // One rattle for each time a hand comes to it.
            held.To(shut).For(touched.Not());
            foreach (var state in new[] { shut, held }) state.To(open).Greater(Opened.Progress, 0.3f);
            open.To(shut).Less(Opened.Progress, 0.001f);

            // A chime, from the game master, when the key is taken.
            var taken = fx.Layer("Chest Key Taken");
            var lying = taken.State("Lying");
            var gone = taken.State("Taken");
            WirenookSounds.PlayOnEnter(gone, GameMaster.SoundPath, "collect");
            lying.To(gone).Greater(Found.Progress, 0.999f);
            gone.To(lying).Less(Found.Progress, 0.5f);
        }

        public void Menu(CryptSet crypt, GameObject parent)
        {
            var chest = crypt.Stage[ChestName];
            var key = crypt.Stage[KeyName];
            crypt.Kit.Parameters.AddRange(AvatarSkillCheck.Parameters(Found));
            crypt.Kit.Parameters.AddRange(AvatarSkillCheck.Parameters(Opened));
            var folder = crypt.MenuThing(parent, chest, "Chest", "key");
            crypt.Stage.MenuValue(FeaturePrefab.Child(folder, "Menu Turn"), chest, "Turn", "reset");
            crypt.Stage.MenuAim(FeaturePrefab.Child(folder, "Menu Aim Key"), key, "Aim its key", "key");
            crypt.Stage.MenuShown(FeaturePrefab.Child(folder, "Menu Key Shown"), key, "Key set out", "key");
        }
    }

    /// <summary>
    /// A blade on a long arm, swinging from a pivot hung wherever the game
    /// master sets it: under a beam, a doorway, a ceiling. It has no
    /// frame of its own. The blade carries <c>Damage</c> and
    /// <c>DamageSharp</c> wherever it is in its swing.
    ///
    /// Everyone sees it swing in step. The wearer's client keeps the time:
    /// while the pendulum is set out it turns one synced bit over at each
    /// end of the swing, and that bit says which end the blade is going
    /// to. Every client, the wearer's too, swings the blade across when
    /// the bit turns over and then holds it at the end until it turns
    /// again. The crossing takes a little less than the time between two
    /// turns, so the blade waits a moment at each end, where a pendulum
    /// is still anyway; an update that comes late eats into that wait
    /// and the lateness is not carried into the next swing. Someone who
    /// arrives part way through is shown the blade at the end it is going
    /// to, and is in step from the next turn.
    ///
    /// What is left is the time an update takes to cross the network:
    /// viewers see the blade a fraction of a second after the wearer
    /// does, and each is cut by the blade they see.
    ///
    /// Its value on the stage is which way it faces.
    /// </summary>
    public sealed class PendulumPiece : ICryptPiece
    {
        public const string ThingName = "Pendulum";

        /// <summary>Seconds for a swing there and back, by the wearer's clock.</summary>
        public const float SwingSeconds = 2.6f;

        /// <summary>Seconds the blade waits at each end, when updates come on time: the slack that takes up a late one.</summary>
        public const float HoldSeconds = 0.14f;

        /// <summary>How far to each side it swings, in degrees.</summary>
        public const float SwingDegrees = 38f;

        /// <summary>Metres from the pivot down to the middle of the crescent.</summary>
        public const float ArmLength = 2.02f;

        /// <summary>Metres above the ground the pivot hangs.</summary>
        public const float PivotHeight = 3.2f;

        /// <summary>Synced bool: the end of the swing the blade is going to, or resting at.</summary>
        public static string Swing(string prefix) => prefix + "/Swing";

        private Transform _bone;
        private Transform _turn;
        private Transform _arm;
        private GameObject _contacts;

        public void Things(StagePlan plan)
        {
            plan.Thing(ThingName, rehearsed: true);
        }

        public void Build(CryptSet crypt)
        {
            _bone = crypt.Stage.Hold(ThingName, crypt.Stage[ThingName]);
            _turn = crypt.Turn(_bone);
            _arm = GameMasterBuild.Bone(_turn.gameObject, "Arm", new Vector3(0f, PivotHeight, 0f));

            // The pivot: a bracket and the pin the arm turns on. Nothing holds it up but the game master's say-so.
            crypt.Solid.On(_turn).Colour("grey-dark")
                .Box(new Vector3(0f, PivotHeight + 0.11f, 0f), new Vector3(0.34f, 0.06f, 0.34f))
                .Box(new Vector3(0f, PivotHeight + 0.02f, 0.1f), new Vector3(0.12f, 0.2f, 0.04f))
                .Box(new Vector3(0f, PivotHeight + 0.02f, -0.1f), new Vector3(0.12f, 0.2f, 0.04f))
                .Colour("brass").Box(new Vector3(0f, PivotHeight, 0f), new Vector3(0.05f, 0.05f, 0.3f));

            // The arm, and at its end a crescent with the edge downward. The
            // crescent's inner edge is 0.3 m below its middle: the arm runs
            // on past that into the steel, and a collar grips the two.
            const float inner = 0.3f;
            const float outer = 0.6f;
            var grip = ArmLength + inner;
            crypt.Solid.On(_arm).Colour("grey-dark")
                .Box(new Vector3(0f, -(grip + 0.1f) * 0.5f, 0f), new Vector3(0.06f, grip + 0.1f, 0.06f))
                .Box(new Vector3(0f, -0.02f, 0f), new Vector3(0.1f, 0.14f, 0.1f))
                .Colour("brass").Box(new Vector3(0f, -(grip + 0.03f), 0f), new Vector3(0.2f, 0.12f, 0.07f))
                .Colour("grey-dark").Box(new Vector3(0f, -(grip + 0.03f), 0f), new Vector3(0.05f, 0.05f, 0.1f))
                .At(new Vector3(0f, -ArmLength, 0f), Quaternion.Euler(-90f, 0f, 0f))
                .Colour("silver").Bend(inner, outer, -0.012f, 0.012f, 200f, 140f, 7)
                .Colour("white").Bend(outer, outer + 0.03f, -0.004f, 0.004f, 200f, 140f, 7)
                .At(Vector3.zero);

            _contacts = crypt.Contacts(_arm, new Vector3(0f, -(ArmLength + 0.48f), 0f));
            CryptSet.Sender(_contacts, 0.35f, SkillTags.Damage, SkillTags.DamageSharp);
        }

        public void Layers(CryptSet crypt)
        {
            var fx = crypt.Fx;
            var thing = crypt.Stage[ThingName];
            var swing = Swing(crypt.Prefix);
            fx.Bool(swing).Bool("IsLocal");
            crypt.TurnLayer(ThingName, _turn, thing);
            crypt.Stage.Show(fx, ThingName, new[] { crypt.Path(_bone) }, thing.Shown);
            crypt.ContactsLayer(ThingName, _contacts, thing);

            var armPath = crypt.Path(_arm);
            const float half = SwingSeconds * 0.5f;
            const float crossing = half - HoldSeconds;
            AnimationClip At(string name, float degrees) => fx.Clip("pendulum " + name, clip =>
                clip.Curve(armPath, typeof(Transform), "localEulerAnglesRaw.z", Curves.Flat(1f / 60f, degrees)));
            // Still at both ends and quickest through the middle, as a pendulum is.
            AnimationClip Across(string name, float from, float to) => fx.Clip("pendulum " + name, clip =>
                clip.Curve(armPath, typeof(Transform), "localEulerAnglesRaw.z",
                    new AnimationCurve(new Keyframe(0f, from, 0f, 0f), new Keyframe(crossing, to, 0f, 0f))));

            // Every client: across when the bit turns over, then wait for it to turn again.
            var layer = fx.Layer("Pendulum Swing");
            var join = layer.State("Join", At("joining", SwingDegrees));
            var near = layer.State("Near", At("near end", SwingDegrees));
            var away = layer.State("Away", Across("away", SwingDegrees, -SwingDegrees));
            var far = layer.State("Far", At("far end", -SwingDegrees));
            var back = layer.State("Back", Across("back", -SwingDegrees, SwingDegrees));
            // Whoever comes to it part way through starts at the end it is going to.
            join.To(far).IfTrue(swing);
            join.To(near).IfFalse(swing);
            near.To(away).IfTrue(swing);
            away.To(far).AfterTime(1f);
            far.To(back).IfFalse(swing);
            back.To(near).AfterTime(1f);

            // The wearer's client: the clock, running while the pendulum is set out.
            var clock = fx.Layer("Pendulum Clock");
            var stopped = clock.State("Stopped");
            var tick = clock.State("Tick", fx.Clip("pendulum tick", clip => clip.Hold(half)));
            var tock = clock.State("Tock", fx.Clip("pendulum tock", clip => clip.Hold(half)));
            tick.Behaviour<VRCAvatarParameterDriver>(driver => DangerPiece.Drive(driver, swing, 1f));
            tock.Behaviour<VRCAvatarParameterDriver>(driver => DangerPiece.Drive(driver, swing, 0f));
            stopped.To(tick).IfTrue("IsLocal").IfTrue(thing.On);
            tick.To(tock).AfterTime(1f);
            // It stops with the blade on its way back to the near end, where it starts from next time.
            tock.To(stopped).IfFalse(thing.On);
            tock.To(tick).AfterTime(1f);
        }

        public void Menu(CryptSet crypt, GameObject parent)
        {
            var thing = crypt.Stage[ThingName];
            crypt.Kit.Parameters.Add(FeaturePrefab.SyncedBool(Swing(crypt.Prefix)));
            var folder = crypt.MenuThing(parent, thing, "Pendulum", "hammer");
            crypt.Stage.MenuValue(FeaturePrefab.Child(folder, "Menu Turn"), thing, "Turn", "reset");
        }
    }

    /// <summary>
    /// A rift: a tear in the air, the way a sheet of paper tears. A tall
    /// ragged gash hangs there, and round it the torn edge of the world
    /// curls back in flaps, white on the side that was hidden. Through
    /// the gash there is a sky with an eye in it, and rocks adrift
    /// between here and there that slide against that sky as the viewer
    /// moves. Scraps of the torn sheet drift round it, and a hum comes
    /// out of it. Hands on it draw it shut over eight seconds, the two
    /// sides coming together to a seam before the seam closes; left half
    /// shut it creeps open again; shut, it stays shut.
    ///
    /// It is not a flat cut-out. The gash is a crumpled, lens-shaped
    /// body with two faces and an edge, and flaps stand off both faces,
    /// so it has a shape from the side and from behind, where it is a
    /// window as well.
    ///
    /// The window is stencil work (Shaders/WirenookRift): the body marks
    /// its pixels and writes its depth, the far side is drawn only on
    /// marked pixels and only behind the body's surface, and the body is
    /// drawn once more to take the mark off, with bands of light along
    /// the torn edge. It needs a shader of this package's own, so it is
    /// PC only, like the variant.
    ///
    /// Sealing is a skill check, synced: the wearer's client says when it
    /// is shut. Its value on the stage is which way it faces; the far
    /// side turns with it, so the eye is always behind the same face.
    /// </summary>
    public sealed class RiftPiece : ICryptPiece
    {
        public const string ThingName = "Rift";

        /// <summary>Metres from the middle of the tear that a hand counts as on it, less the margin the receiver adds.</summary>
        public const float Radius = 0.55f;

        /// <summary>Metres from the tip of the tear to its other tip.</summary>
        public const float Tall = 1.7f;

        /// <summary>Metres across the tear, about, where it gapes widest.</summary>
        public const float Wide = 0.84f;

        /// <summary>Metres above the ground its middle hangs.</summary>
        public const float Height = 1.45f;

        /// <summary>Seconds of hands on it that seal it.</summary>
        public const float SealSeconds = 8f;

        /// <summary>Seconds a rift left half sealed takes to open all the way again.</summary>
        public const float ReopenSeconds = 20f;

        /// <summary>The material property that tells the far side which way the tear faces, as a share of a turn.</summary>
        public const string Heading = "_Heading";

        // The tear, row by row from its lower tip to its upper: how far the
        // line of it wanders to one side, how far each edge stands off that
        // line (as a share of the width there), and how far the row is
        // crumpled out of the flat.
        private const int Rows = 9;
        private static readonly float[] Wander = { 0f, 0.05f, -0.04f, 0.07f, -0.01f, -0.08f, 0.03f, -0.05f, 0f };
        private static readonly float[] Left = { 0f, 0.95f, 0.55f, 1f, 0.7f, 1.05f, 0.6f, 0.9f, 0f };
        private static readonly float[] Right = { 0f, 0.6f, 1f, 0.65f, 1.1f, 0.75f, 0.95f, 0.5f, 0f };
        private static readonly float[] Crumple = { 0f, 0.05f, -0.06f, 0.04f, -0.03f, 0.07f, -0.05f, 0.03f, 0f };

        // Each face is cut into bands from the edge inwards; the last drawing of the body lights the outer two.
        private static readonly float[] Bands = { 1f, 0.86f, 0.66f, 0f };
        private static readonly string[] BandLight = { "0.9", "0.38", "0" };

        public AvatarCheck Sealed { get; private set; }

        private Transform _bone;
        private Transform _float;
        private Transform _tear;
        private Transform _shards;
        private Transform _drift;
        private GameObject _contacts;

        public void Things(StagePlan plan)
        {
            plan.Thing(ThingName, rehearsed: true);
        }

        /// <summary>How wide open the tear is at a row, from nothing at the tips to one in the middle.</summary>
        private static float Gape(int row) => Mathf.Pow(Mathf.Sin(Mathf.PI * row / (Rows - 1f)), 0.7f);

        /// <summary>
        /// A point of the tear's body.
        /// </summary>
        /// <param name="across">From -1, the left edge, through 0, the line of the tear, to 1, the right edge.</param>
        /// <param name="face">1 for the front face, -1 for the back.</param>
        private static Vector3 Point(int row, float across, float face)
        {
            var gape = Gape(row);
            var reach = Wide * 0.5f * gape * (across < 0f ? Left[row] : Right[row]);
            // A few centimetres thick at the edge, and bellying out towards the middle.
            var depth = gape < 0.001f ? 0f : 0.03f + 0.1f * gape * (1f - Mathf.Abs(across));
            return new Vector3(Wander[row] + across * reach, (row / (Rows - 1f) - 0.5f) * Tall, Crumple[row] + face * depth);
        }

        /// <summary>A flat face through corners that may coincide, as they do at the tips of the tear, seen from the side <paramref name="toward"/> points to.</summary>
        private static void Patch(ShapeMesh mesh, Vector3 toward, params Vector3[] corners)
        {
            var distinct = new List<Vector3>();
            foreach (var corner in corners)
                if (distinct.Count == 0 || (distinct[distinct.Count - 1] - corner).sqrMagnitude > 1e-10f)
                    distinct.Add(corner);
            if (distinct.Count > 1 && (distinct[0] - distinct[distinct.Count - 1]).sqrMagnitude < 1e-10f) distinct.RemoveAt(distinct.Count - 1);
            if (distinct.Count < 3) return;
            var normal = Vector3.Cross(distinct[1] - distinct[0], distinct[2] - distinct[0]);
            if (normal.sqrMagnitude < 1e-14f) return;
            normal.Normalize();
            if (Vector3.Dot(normal, toward) < 0f) normal = -normal;
            mesh.Face(normal, distinct.ToArray());
        }

        /// <summary>The tear's body: two faces in bands and the edge between them. Drawn twice, by the window and by the rim, from the same points.</summary>
        private static void Body(ShapeMesh mesh, bool lit)
        {
            for (var row = 0; row < Rows - 1; row++)
            {
                foreach (var side in new[] { -1f, 1f })
                {
                    foreach (var face in new[] { 1f, -1f })
                    {
                        for (var band = 0; band < Bands.Length - 1; band++)
                        {
                            mesh.Colour(lit ? BandLight[band] : "");
                            Patch(mesh, new Vector3(0f, 0f, face),
                                Point(row, side * Bands[band], face), Point(row, side * Bands[band + 1], face),
                                Point(row + 1, side * Bands[band + 1], face), Point(row + 1, side * Bands[band], face));
                        }
                    }

                    mesh.Colour(lit ? BandLight[0] : "");
                    Patch(mesh, new Vector3(side, 0f, 0f),
                        Point(row, side, 1f), Point(row, side, -1f), Point(row + 1, side, -1f), Point(row + 1, side, 1f));
                }
            }

            mesh.Colour("");
        }

        /// <summary>
        /// A slab of the torn sheet with some thickness: white on the side
        /// <paramref name="toward"/> points to, which is the side that was
        /// hidden until it tore, and grey underneath.
        /// </summary>
        private static void Slab(ShapeMesh mesh, Vector3 toward, Vector3 thickness, string top, bool[] open, params Vector3[] outline)
        {
            var under = outline.Select(corner => corner - thickness).ToArray();
            var middle = outline.Aggregate(Vector3.zero, (sum, corner) => sum + corner) / outline.Length;
            mesh.Colour(top);
            Patch(mesh, toward, outline);
            mesh.Colour("lilac-1");
            Patch(mesh, -toward, under);
            mesh.Colour("lilac-4");
            for (var edge = 0; edge < outline.Length; edge++)
            {
                if (open[edge]) continue;
                var next = (edge + 1) % outline.Length;
                Patch(mesh, (outline[edge] + outline[next]) * 0.5f - middle, outline[edge], outline[next], under[next], under[edge]);
            }
        }

        /// <summary>The flaps of the torn sheet, curled back from the edge on both faces: two to each stretch of the edge, none two alike.</summary>
        private static void Flaps(ShapeMesh mesh)
        {
            var lengths = new[] { 0.2f, 0.09f, 0.26f, 0.13f, 0.17f, 0.07f, 0.23f, 0.11f, 0.15f, 0.28f, 0.1f };
            var leans = new[] { 0.25f, 0.7f, 0.45f, 0.8f, 0.35f, 0.6f, 0.15f };
            var tops = new[] { "paper", "cream", "paper", "white", "cream" };
            var flap = 0;
            for (var row = 0; row < Rows - 1; row++)
            {
                foreach (var side in new[] { -1f, 1f })
                {
                    foreach (var face in new[] { 1f, -1f })
                    {
                        for (var part = 0; part < 2; part++)
                        {
                            flap++;
                            // The back keeps fewer: the sheet tore towards the front.
                            if (face < 0f && flap % 3 == 0) continue;
                            var start = Point(row, side, face);
                            var end = Point(row + 1, side, face);
                            var from = Vector3.Lerp(start, end, part * 0.5f);
                            var to = Vector3.Lerp(start, end, part * 0.5f + 0.5f);
                            var along = (to - from).normalized;
                            // Away from the gash, in the plane of the sheet.
                            var away = new Vector3(along.y, -along.x, 0f).normalized;
                            if (away.x * side < 0f) away = -away;
                            var out_ = new Vector3(0f, 0f, face);
                            var open = Mathf.Lerp(Gape(row), Gape(row + 1), part * 0.5f + 0.25f);
                            var length = lengths[flap % lengths.Length] * (0.5f + 0.5f * open);
                            // It lies nearly flat where it joins and lifts as it goes: a curl.
                            var lift = away * (0.4f * length) + out_ * (0.08f * length);
                            var bendFrom = Vector3.Lerp(from, to, 0.08f) + lift;
                            var bendTo = Vector3.Lerp(from, to, 0.92f) + lift;
                            var tip = Vector3.Lerp(from, to, leans[flap % leans.Length]) + away * length + out_ * (0.65f * length);

                            var normal = Vector3.Cross(to - from, bendFrom - from).normalized;
                            if (Vector3.Dot(normal, out_) < 0f) normal = -normal;
                            var thickness = normal * 0.016f;
                            var top = tops[flap % tops.Length];
                            Slab(mesh, normal, thickness, top, new[] { true, false, true, false }, from, to, bendTo, bendFrom);
                            Slab(mesh, normal, thickness, top, new[] { true, false, false }, bendFrom, bendTo, tip);
                        }
                    }
                }
            }
        }

        public void Build(CryptSet crypt)
        {
            var thing = crypt.Stage[ThingName];
            _bone = crypt.Stage.Hold(ThingName, thing);
            // The bone it hangs from is also the one its heading turns.
            _float = GameMasterBuild.Bone(_bone.gameObject, "Float", new Vector3(0f, Height, 0f));
            _tear = GameMasterBuild.Bone(_float.gameObject, "Tear", Vector3.zero);
            _shards = GameMasterBuild.Bone(_tear.gameObject, "Shards", Vector3.zero);
            var beyond = GameMasterBuild.Bone(_tear.gameObject, "Beyond", Vector3.zero);
            _drift = GameMasterBuild.Bone(beyond.gameObject, "Drift", Vector3.zero);

            // On this side: the torn edge of the sheet, curled back.
            Flaps(crypt.Solid.On(_tear));

            // Scraps of it going round, and three motes of light.
            var solid = crypt.Solid.On(_shards);
            for (var scrap = 0; scrap < 5; scrap++)
            {
                var around = (scrap * 72f + 20f) * Mathf.Deg2Rad;
                var out_ = 0.62f + 0.07f * (scrap % 3);
                var at = new Vector3(Mathf.Cos(around) * out_, (scrap * 2 % 5 - 2) * 0.3f, Mathf.Sin(around) * out_);
                var size = 0.07f + 0.02f * (scrap % 3);
                solid.At(at, Quaternion.Euler(scrap * 37f, scrap * 61f, scrap * 23f));
                Slab(solid, Vector3.forward, Vector3.forward * 0.012f, scrap % 2 == 0 ? "paper" : "cream", new[] { false, false, false, false },
                    new Vector3(-size, -size * 0.7f, 0f), new Vector3(size * 0.8f, -size, 0f),
                    new Vector3(size, size * 0.5f, 0f), new Vector3(-size * 0.3f, size, 0f));
            }

            for (var mote = 0; mote < 3; mote++)
            {
                var around = (mote * 120f + 30f) * Mathf.Deg2Rad;
                solid.Colour("glow-lavender").At(new Vector3(Mathf.Cos(around) * 0.58f, 0.35f * mote - 0.35f, Mathf.Sin(around) * 0.58f))
                    .Ball(Vector3.zero, 0.025f, 2, 4);
            }

            solid.At(Vector3.zero);

            // The window, the far side, and the window again to close the mark.
            var window = crypt.Effect(GameMasterBuild.Material(CryptBuild.RiftWindowMaterial));
            var far = crypt.Effect(GameMasterBuild.Material(CryptBuild.RiftBeyondMaterial));
            var rim = crypt.Effect(GameMasterBuild.Material(CryptBuild.RiftRimMaterial));
            Body(crypt.Effects.On(_tear).Slot(window), false);

            // The far side is drawn in the order it is added, farthest
            // first: the sky all round, then the rocks adrift in it.
            crypt.Effects.On(beyond).Slot(far).Colour("sky").Ball(Vector3.zero, 3.2f, 6, 12);
            crypt.Effects.On(_drift).Slot(far);
            for (var rock = 0; rock < 16; rock++)
            {
                // Splinters of stone standing in the air, the farther the larger, lit a little from behind.
                var around = (rock * 137.5f) * Mathf.Deg2Rad;
                var out_ = 3f - 0.1f * rock;
                var at = new Vector3(Mathf.Cos(around) * out_, ((rock * 7) % 11 - 5) * 0.14f, Mathf.Sin(around) * out_);
                var size = 0.2f + 0.02f * (16 - rock);
                crypt.Effects.Colour(rock % 4 == 0 ? "0.22" : rock % 4 == 2 ? "0.08" : "0")
                    .At(at, Quaternion.Euler(rock * 17f % 40f - 20f, rock * 61f, rock * 13f % 36f - 18f), size)
                    .Ball(Vector3.zero, 0.5f, 2, 4)
                    .At(at + new Vector3(0f, -0.2f * size, 0f), Quaternion.Euler(rock * 29f % 30f, rock * 47f, 45f), size)
                    .Box(Vector3.zero, new Vector3(0.14f, 0.62f, 0.14f));
            }

            crypt.Effects.At(Vector3.zero);
            Body(crypt.Effects.On(_tear).Slot(rim), true);

            Sealed = new AvatarCheck("crypt-sealed", new CheckSpec
            {
                AdvanceRate = 1f / SealSeconds,
                IdleRate = -1f / ReopenSeconds,
                Latch = true,
            }.Need(TagGroup.AnyOf(SkillTags.Hand, SkillTags.Finger)))
            {
                Sync = true,
                EmptyWhile = gone => gone.IfFalse(thing.On).Or().IfFalse(crypt.Stage.Live),
            };
            _contacts = crypt.Contacts(_float, Vector3.zero);
            AvatarSkillCheck.Receiver(_contacts, Sealed, Radius + 0.15f);
            WirenookSounds.Source(_bone.gameObject, shared: false);
        }

        public void Layers(CryptSet crypt)
        {
            var fx = crypt.Fx;
            var thing = crypt.Stage[ThingName];
            var shardsPath = crypt.Path(_shards);
            var driftPath = crypt.Path(_drift);
            crypt.Stage.Show(fx, ThingName, new[] { crypt.Path(_bone) }, thing.Shown, (clip, phase) =>
            {
                if (phase != "on") return;
                clip.Curve(shardsPath, typeof(Transform), "localEulerAnglesRaw.y", AnimationCurve.Linear(0f, 0f, 60f, 360f * 3f));
                clip.Curve(driftPath, typeof(Transform), "localEulerAnglesRaw.y", AnimationCurve.Linear(0f, 0f, 60f, -360f));
                clip.Loop();
            });
            crypt.ContactsLayer(ThingName, _contacts, thing);

            // Its heading: the tear turns, and the far side is told so that it turns too.
            var floatPath = crypt.Path(_float);
            fx.Layer("Rift Turn").State("Turn", fx.Clip("rift turn", clip => clip
                .Curve(floatPath, typeof(Transform), "localEulerAnglesRaw.y", AnimationCurve.Linear(0f, 0f, 1f, 360f))
                .Material<SkinnedMeshRenderer>(CryptSet.EffectsName, Heading, AnimationCurve.Linear(0f, 0f, 1f, 1f)))).MotionTime(thing.Value);

            // Sealing draws the two sides together to a seam, and then the seam shut.
            var tearPath = crypt.Path(_tear);
            Sealed.Look = clip =>
            {
                var closing = Curves.Eased((0f, 1f), (0.78f, 0.1f), (1f, 0f));
                clip.Curve(tearPath, typeof(Transform), "m_LocalScale.x", closing)
                    .Curve(tearPath, typeof(Transform), "m_LocalScale.z", closing)
                    .Curve(tearPath, typeof(Transform), "m_LocalScale.y", Curves.Eased((0f, 1f), (0.78f, 0.88f), (1f, 0f)));
            };
            AvatarSkillCheck.Layers(fx, Sealed);

            // It hums for as long as it is open, and sighs shut.
            var source = crypt.Path(_bone) + "/" + WirenookSounds.SourceName;
            var open = thing.Real.And(Audience.WhenBelow(Sealed.Progress, 0.999f));
            var shut = thing.Real.And(Audience.WhenAbove(Sealed.Progress, 0.999f));
            fx.Declare(open).Declare(shut);
            var layer = fx.Layer("Rift Hum");
            var quiet = layer.State("Quiet");
            var humming = layer.State("Humming");
            var sealed_ = layer.State("Sealed");
            WirenookSounds.StopOnEnter(quiet, source);
            WirenookSounds.PlayOnEnter(humming, source, "hum", loop: true);
            WirenookSounds.PlayOnEnter(sealed_, source, "seal");
            quiet.To(humming).For(open);
            humming.To(sealed_).For(shut);
            humming.To(quiet).For(thing.Real.Not());
            sealed_.To(quiet).For(thing.Real.Not());
            sealed_.To(humming).For(open);
        }

        public void Menu(CryptSet crypt, GameObject parent)
        {
            var thing = crypt.Stage[ThingName];
            crypt.Kit.Parameters.AddRange(AvatarSkillCheck.Parameters(Sealed));
            var folder = crypt.MenuThing(parent, thing, "Rift", "ring");
            crypt.Stage.MenuValue(FeaturePrefab.Child(folder, "Menu Turn"), thing, "Turn", "reset");
        }
    }
}
