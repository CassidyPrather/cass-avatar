using System;
using System.Numerics;
using Wirenook.Locomotion;

namespace Wirenook.Bot.Editor
{
    /// <summary>
    /// The numbers the bot's motions share: how it stands, how long a step
    /// takes and how far one can reach, all from the lengths of its legs.
    ///
    /// The bot does not walk like a person and is not meant to. It is a
    /// machine with one clock: every step takes the same time whatever the
    /// speed, and only its length changes. Its feet go up, across and down
    /// in straight lines. Its body rides level. What its legs cannot do
    /// (step sideways at any speed, or keep up past a walk) it does not
    /// attempt: it lifts off the ground and slides.
    /// </summary>
    internal sealed class BotFrame
    {
        public const float Deg = MathF.PI / 180f;

        /// <summary>Share of each cycle a foot is on the ground. At a half, one lifts as the other lands.</summary>
        public const float Duty = 0.5f;

        /// <summary>Shares of a swing spent going straight up, and coming straight down.</summary>
        public const float Lift = 0.22f, Drop = 0.22f;

        /// <summary>The fastest it steps ahead or back, m/s: a little over VRChat's walk.</summary>
        public const float WalkSpeed = 2.2f;

        /// <summary>From here on, ahead or back, it only slides: under VRChat's run.</summary>
        public const float SkateSpeed = 3.1f;

        /// <summary>From here on, sideways, it only slides: under VRChat's strafe.</summary>
        public const float SlideSpeed = 1.4f;

        /// <summary>The same three, crouched, where VRChat halves every speed.</summary>
        public const float CrouchWalkSpeed = 2.05f, CrouchSkateSpeed = 2.8f, CrouchSlideSpeed = 0.95f;

        public readonly BodyProportions Body;

        /// <summary>How much of the upper body's motion is left: less for a player whose head and hands are tracked.</summary>
        public readonly float Upper;

        /// <summary>Seconds per cycle of two steps, at every speed.</summary>
        public readonly float Cycle;

        /// <summary>The fastest it steps sideways, m/s: what keeps one foot clear of the other.</summary>
        public readonly float SideStepSpeed;

        public BotFrame(BodyProportions body, float upper)
        {
            Body = body;
            Upper = upper;
            // A step may be as long as the leg reaches from the height it
            // walks at, less a margin; the clock is what makes that step
            // cover the ground at the fastest walk.
            float reach = 0.92f * MathF.Sqrt(1f - WalkHeight * WalkHeight) * body.LegLength;
            Cycle = 2f * reach / (WalkSpeed * Duty);
            float clear = MathF.Max(2f * HalfStance(false) - 0.45f * body.FootLength, 0.02f);
            SideStepSpeed = MathF.Min(clear / (Duty * Cycle), 0.6f);
        }

        /// <summary>Hip above ankle, as a share of the leg: standing, walking, sliding, and each crouched.</summary>
        public const float StandHeight = 0.985f, WalkHeight = 0.86f, HoverHeight = 0.9f;
        public const float CrouchHeight = 0.6f, CrouchWalkHeight = 0.56f;

        public float HalfStance(bool crouched) => 0.5f * Body.HipWidth * (crouched ? 1.9f : 1.25f);

        /// <summary>How high a stepping foot is carried.</summary>
        public float StepHeight(bool crouched) => (crouched ? 0.12f : 0.17f) * Body.LegLength;

        /// <summary>A foot flat on or over the ground, pointing ahead.</summary>
        public FootPose Foot(Side side, float halfStance, Vector3 offset, bool planted)
        {
            var ankle = new Vector3((int)side * halfStance, Body.AnkleHeight, 0f) + offset;
            return new FootPose
            {
                Ankle = ankle,
                Rotation = Quaternion.Identity,
                ToeBend = 0f,
                Contact = planted ? FootContact.Flat : FootContact.None,
                ContactPoint = new Vector3(ankle.X, 0f, ankle.Z),
                KneeDirection = Vector3.UnitZ,
            };
        }

        /// <summary>Both arms the same.</summary>
        public static void Arms(ref GaitPose pose, float swing, float spread, float elbow)
        {
            pose.LeftArm = pose.RightArm = new ArmPose { Swing = swing * Deg, Spread = spread * Deg, ElbowBend = elbow * Deg };
        }

        /// <summary>
        /// Standing: legs all but straight, arms down and a little out,
        /// everything square. Crouched, it folds at the knees with the hips
        /// back and the chest tipped over them.
        /// </summary>
        public GaitPose Stand(bool crouched, float height)
        {
            float drop = (StandHeight - height) * Body.LegLength;
            float half = HalfStance(crouched);
            var pose = new GaitPose
            {
                PelvisPosition = new Vector3(0f, Body.AnkleHeight + height * Body.LegLength, crouched ? -0.3f * drop : 0f),
                PelvisRotation = Rot.Pitch(crouched ? 6f * Deg : 0f),
                ChestRotation = Rot.Pitch(crouched ? 16f * Deg * Upper : 0f),
                HeadRotation = Quaternion.Identity,
                LeftFoot = Foot(Side.Left, half, Vector3.Zero, true),
                RightFoot = Foot(Side.Right, half, Vector3.Zero, true),
            };
            if (crouched) Arms(ref pose, 20f, 10f, 70f);
            else Arms(ref pose, 0f, 7f, 12f);
            return pose;
        }

        public static float Wrap(float phase) => phase - MathF.Floor(phase);

        /// <summary>From 0 to 1 at a constant rate between two moments, and held outside them: how a servo moves.</summary>
        public static float Ramp(float from, float to, float at) => Math.Clamp((at - from) / (to - from), 0f, 1f);
    }

    /// <summary>Standing still, which for a machine is exactly that.</summary>
    internal sealed class BotStanding : IPoseCycle
    {
        private readonly GaitPose _pose;
        private readonly float _duration;

        public BotStanding(BotFrame frame, bool crouched)
        {
            _pose = frame.Stand(crouched, crouched ? BotFrame.CrouchHeight : BotFrame.StandHeight);
            // The same length as a walk cycle, so that mixing the two does not stretch the walk.
            _duration = frame.Cycle;
        }

        public float Duration => _duration;

        public Vector3 RootVelocity => Vector3.Zero;

        public GaitPose Evaluate(float phase) => _pose;
    }

    /// <summary>
    /// What it does with itself while standing: now and then a forearm
    /// ticks up and back, one after the other, and the knees take up their
    /// slack. Each move is at one speed and stops dead. Played as its
    /// difference from standing, over standing.
    /// </summary>
    internal sealed class BotFidget : IPoseCycle
    {
        private readonly BotFrame _frame;

        public BotFidget(BotFrame frame)
        {
            _frame = frame;
        }

        public float Duration => 7f;

        public Vector3 RootVelocity => Vector3.Zero;

        public GaitPose Evaluate(float phase)
        {
            float t = BotFrame.Wrap(phase) * Duration;
            var pose = _frame.Stand(false, BotFrame.StandHeight);

            // There and back in a tenth of a second each way, with a hold between.
            float Tick(float at, float hold) =>
                BotFrame.Ramp(at, at + 0.1f, t) - BotFrame.Ramp(at + 0.1f + hold, at + 0.2f + hold, t);

            pose.LeftArm.ElbowBend += 26f * BotFrame.Deg * Tick(1.6f, 0.35f);
            pose.RightArm.ElbowBend += 26f * BotFrame.Deg * Tick(2.3f, 0.35f);
            pose.PelvisPosition.Y -= 0.022f * _frame.Body.LegLength * Tick(4.9f, 0.5f);
            return pose;
        }
    }

    /// <summary>
    /// Stepping. Each foot holds the ground for half the cycle, then goes
    /// straight up, straight across and straight down, at constant speeds,
    /// while the other holds. The pelvis stays where it is: no rise, no
    /// sway, no turn. The arms are bent square and change places at each
    /// footfall, quickly, and wait there.
    ///
    /// Everything a foot does is in proportion to the velocity, at a cadence
    /// that never changes, so any mixture of these cycles (with each other
    /// or with standing) is the cycle for the velocity between: the blend
    /// tree needs no samples inside the range, and the feet hold the ground
    /// at every speed in it.
    /// </summary>
    internal sealed class BotStep : IPoseCycle
    {
        private readonly BotFrame _frame;
        private readonly Vector3 _velocity;
        private readonly bool _crouched;
        private readonly float _share;

        public BotStep(BotFrame frame, float right, float forward, bool crouched)
        {
            _frame = frame;
            _velocity = new Vector3(right, 0f, forward);
            _crouched = crouched;
            _share = Math.Clamp(_velocity.Length() / (crouched ? BotFrame.CrouchWalkSpeed : BotFrame.WalkSpeed), 0f, 1f);
        }

        public float Duration => _frame.Cycle;

        public Vector3 RootVelocity => _velocity;

        public GaitPose Evaluate(float phase)
        {
            phase = BotFrame.Wrap(phase);
            // It sits lower the longer its steps are, and no lower than they need.
            float low = _share * _share;
            float height = _crouched
                ? BotFrame.CrouchHeight + (BotFrame.CrouchWalkHeight - BotFrame.CrouchHeight) * low
                : BotFrame.StandHeight + (BotFrame.WalkHeight - BotFrame.StandHeight) * low;
            var pose = _frame.Stand(_crouched, height);
            float half = _frame.HalfStance(_crouched);
            pose.LeftFoot = Step(Side.Left, half, phase);
            pose.RightFoot = Step(Side.Right, half, BotFrame.Wrap(phase + 0.5f));

            // Into the direction of travel, a little, as one piece.
            float lean = 2.2f * BotFrame.Deg * _frame.Upper;
            pose.ChestRotation = pose.ChestRotation * Rot.Euler(0f, lean * _velocity.Z, -lean * _velocity.X);

            // The arm across from a foot goes ahead as that foot lands, in an
            // eighth of a cycle centred on the footfall, and waits there.
            const float snap = 0.06f;
            float ahead = phase < snap ? phase / snap
                : phase < 0.5f - snap ? 1f
                : phase < 0.5f + snap ? (0.5f - phase) / snap
                : phase < 1f - snap ? -1f
                : (phase - 1f) / snap;
            // Ahead means the right arm: the left foot lands at phase 0.
            float direction = _velocity.Z >= 0f ? 1f : -1f;
            float swing = (_crouched ? 14f : 26f) * _share * _frame.Upper * direction;
            float carried = _crouched ? 20f : 6f;
            float elbow = _crouched ? 70f : 12f + 78f * _share;
            pose.RightArm = new ArmPose { Swing = (carried + swing * ahead) * BotFrame.Deg, Spread = 6f * BotFrame.Deg, ElbowBend = elbow * BotFrame.Deg };
            pose.LeftArm = new ArmPose { Swing = (carried - swing * ahead) * BotFrame.Deg, Spread = 6f * BotFrame.Deg, ElbowBend = elbow * BotFrame.Deg };
            return pose;
        }

        /// <summary>One foot at its own phase: 0 is the moment it lands, ahead.</summary>
        private FootPose Step(Side side, float half, float phase)
        {
            const float duty = BotFrame.Duty;
            // Distances are in cycles of travel: the ground passes under the root at one per cycle.
            float along, height;
            if (phase < duty)
            {
                along = duty * 0.5f - phase;
                height = 0f;
            }
            else
            {
                float swing = (phase - duty) / (1f - duty);
                float lifted = -duty * 0.5f - BotFrame.Lift * (1f - duty);
                float dropping = duty * 0.5f + BotFrame.Drop * (1f - duty);
                if (swing < BotFrame.Lift)
                {
                    // Still going back with the ground, so that over the ground it only goes up.
                    along = duty * 0.5f - phase;
                    height = swing / BotFrame.Lift;
                }
                else if (swing < 1f - BotFrame.Drop)
                {
                    along = lifted + (dropping - lifted) * (swing - BotFrame.Lift) / (1f - BotFrame.Lift - BotFrame.Drop);
                    height = 1f;
                }
                else
                {
                    along = duty * 0.5f + (1f - phase);
                    height = (1f - swing) / BotFrame.Drop;
                }
            }

            var offset = _velocity * (along * _frame.Cycle);
            // A slow step still comes off the ground far enough to be seen to.
            offset.Y = height * _frame.StepHeight(_crouched) * (0.4f + 0.6f * _share);
            return _frame.Foot(side, half, offset, phase < duty);
        }
    }

    /// <summary>
    /// Sliding: off the ground on whatever is in its feet, the whole body
    /// tipped as one piece toward where it is going, toes down, legs locked.
    /// It is what the bot does sideways and at speed, where stepping would
    /// need joints or time it does not have. Nothing moves but a slow bob.
    /// </summary>
    internal sealed class BotSlide : IPoseCycle
    {
        private const float ToeDown = 26f;

        private readonly BotFrame _frame;
        private readonly Vector3 _velocity;
        private readonly bool _crouched;
        private readonly float _forward, _right;

        /// <param name="leanForward">Degrees tipped ahead; negative is back.</param>
        /// <param name="leanRight">Degrees tipped to the right.</param>
        public BotSlide(BotFrame frame, float right, float forward, float leanRight, float leanForward, bool crouched)
        {
            _frame = frame;
            _velocity = new Vector3(right, 0f, forward);
            _crouched = crouched;
            _forward = leanForward;
            _right = leanRight;
        }

        public float Duration => _frame.Cycle;

        public Vector3 RootVelocity => _velocity;

        public GaitPose Evaluate(float phase)
        {
            var body = _frame.Body;
            float height = _crouched ? BotFrame.CrouchWalkHeight : BotFrame.HoverHeight;
            var pose = _frame.Stand(_crouched, height);
            float half = 0.8f * _frame.HalfStance(_crouched);

            // High enough that the toes, pointed down, clear the ground when it tips.
            float bob = 0.012f * MathF.Sin(2f * MathF.PI * BotFrame.Wrap(phase));
            float clear = 0.75f * body.FootLength * MathF.Sin(ToeDown * BotFrame.Deg) + 0.05f + bob;
            float tipped = MathF.Max(MathF.Abs(_forward), MathF.Abs(_right)) * BotFrame.Deg;
            clear += MathF.Sin(tipped) * (half + 0.75f * body.FootLength);

            // One rigid piece, turned about the point on the ground under it.
            var tip = Rot.Euler(0f, _forward * BotFrame.Deg, -_right * BotFrame.Deg);
            var lift = new Vector3(0f, clear, 0f);
            pose.PelvisPosition = Rot.Apply(tip, pose.PelvisPosition) + lift;
            pose.PelvisRotation = tip * pose.PelvisRotation;
            // A tracked head stays where its wearer holds it, and the chest with it.
            var upper = Quaternion.Slerp(Quaternion.Identity, tip, _frame.Upper);
            pose.ChestRotation = upper * pose.ChestRotation;
            pose.HeadRotation = upper;
            pose.LeftFoot = Hung(Side.Left, half, tip, lift);
            pose.RightFoot = Hung(Side.Right, half, tip, lift);

            // Swept back going ahead, held out ahead going back, and out to
            // the sides going sideways: where a thing with no wings would put them.
            float ahead = _forward / 20f, across = MathF.Abs(_right) / 12f;
            float swing = ahead > 0f ? -42f * MathF.Min(ahead, 1.2f) : -28f * MathF.Max(ahead, -1.2f);
            float spread = 9f + 20f * MathF.Min(across, 1.2f) + 5f * MathF.Min(MathF.Abs(ahead), 1f);
            BotFrame.Arms(ref pose, swing * _frame.Upper, spread, _crouched ? 40f : 6f);
            return pose;
        }

        private FootPose Hung(Side side, float half, Quaternion tip, Vector3 lift)
        {
            var foot = _frame.Foot(side, half, Vector3.Zero, false);
            foot.Ankle = Rot.Apply(tip, foot.Ankle) + lift;
            foot.Rotation = tip * Rot.Pitch(ToeDown * BotFrame.Deg);
            foot.KneeDirection = Rot.Apply(tip, Vector3.UnitZ);
            foot.ContactPoint = new Vector3(foot.Ankle.X, 0f, foot.Ankle.Z);
            return foot;
        }
    }

    internal enum BotAirMoment
    {
        /// <summary>Going up: straight as a rocket, toes down, arms pinned back like fins.</summary>
        Rising,

        /// <summary>Coming down: gear out. Knees bent, feet apart and flat, arms out to steady.</summary>
        Falling,

        /// <summary>A long drop: everything spread to brake.</summary>
        Plunging,
    }

    /// <summary>Off the ground. Each moment is one pose, held.</summary>
    internal sealed class BotAir : IPoseCycle
    {
        private readonly GaitPose _pose;
        private readonly float _duration;

        public BotAir(BotFrame frame, BotAirMoment moment)
        {
            _duration = frame.Cycle;
            var body = frame.Body;
            float half = frame.HalfStance(false);
            var pose = frame.Stand(false, BotFrame.StandHeight);
            switch (moment)
            {
                case BotAirMoment.Rising:
                    pose.LeftFoot = Pointed(frame, Side.Left, 0.7f * half, 60f);
                    pose.RightFoot = Pointed(frame, Side.Right, 0.7f * half, 60f);
                    BotFrame.Arms(ref pose, -18f * frame.Upper, 16f, 0f);
                    break;
                case BotAirMoment.Falling:
                    pose.LeftFoot = frame.Foot(Side.Left, 1.7f * half, new Vector3(0f, 0.2f * body.LegLength, 0.04f), false);
                    pose.RightFoot = frame.Foot(Side.Right, 1.7f * half, new Vector3(0f, 0.2f * body.LegLength, 0.04f), false);
                    BotFrame.Arms(ref pose, 0f, 42f, 20f);
                    break;
                default:
                    pose.LeftFoot = frame.Foot(Side.Left, 2.6f * half, new Vector3(0f, 0.1f * body.LegLength, 0f), false);
                    pose.RightFoot = frame.Foot(Side.Right, 2.6f * half, new Vector3(0f, 0.1f * body.LegLength, 0f), false);
                    pose.ChestRotation = Rot.Pitch(8f * BotFrame.Deg * frame.Upper);
                    BotFrame.Arms(ref pose, 0f, 82f, 0f);
                    break;
            }

            _pose = pose;
        }

        private static FootPose Pointed(BotFrame frame, Side side, float half, float degrees)
        {
            var foot = frame.Foot(side, half, Vector3.Zero, false);
            foot.Rotation = Rot.Pitch(degrees * BotFrame.Deg);
            return foot;
        }

        public float Duration => _duration;

        public Vector3 RootVelocity => Vector3.Zero;

        public GaitPose Evaluate(float phase) => _pose;
    }

    /// <summary>
    /// Landing: the knees take it at once and lock, and then the body comes
    /// back up a notch at a time. A hard one goes deeper, waits longer and
    /// puts the arms out.
    /// </summary>
    internal sealed class BotLanding : IPoseCycle
    {
        private readonly BotFrame _frame;
        private readonly bool _hard;

        public BotLanding(BotFrame frame, bool hard)
        {
            _frame = frame;
            _hard = hard;
        }

        // The state machine leaves a soft landing when its clip ends, and a hard one at six tenths of it.
        public float Duration => _hard ? 0.9f : 0.4f;

        public Vector3 RootVelocity => Vector3.Zero;

        public GaitPose Evaluate(float phase)
        {
            phase = Math.Clamp(phase, 0f, 1f);
            float depth = _hard ? 0.4f : 0.2f;
            // Down already at the first frame (the fade into this state is
            // the drop), and up in two notches.
            float risen = _hard
                ? 0.4f * BotFrame.Ramp(0.3f, 0.36f, phase) + 0.35f * BotFrame.Ramp(0.5f, 0.56f, phase)
                : 0.5f * BotFrame.Ramp(0.45f, 0.6f, phase) + 0.5f * BotFrame.Ramp(0.8f, 0.95f, phase);
            float sunk = depth * (1f - risen);
            var pose = _frame.Stand(false, BotFrame.StandHeight - sunk);
            pose.PelvisPosition.Z = -0.25f * sunk * _frame.Body.LegLength;
            pose.ChestRotation = Rot.Pitch(30f * BotFrame.Deg * sunk * _frame.Upper);
            // Wider than it stands, where the fall had them, and not moving: the feet are down.
            float half = 1.5f * _frame.HalfStance(false);
            pose.LeftFoot = _frame.Foot(Side.Left, half, Vector3.Zero, true);
            pose.RightFoot = _frame.Foot(Side.Right, half, Vector3.Zero, true);
            BotFrame.Arms(ref pose, 0f, 7f + (_hard ? 90f : 50f) * sunk, 12f);
            return pose;
        }
    }
}
