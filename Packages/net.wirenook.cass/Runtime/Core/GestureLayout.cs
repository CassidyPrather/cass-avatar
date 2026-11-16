using System;
using System.Collections.Generic;
using System.Linq;

namespace Wirenook.Cass.Core
{
    /// <summary>A facial expression a hand gesture selects.</summary>
    public sealed class Expression
    {
        public string Id;
        public string Label;

        /// <summary>Face regions this expression takes over from face tracking while held.</summary>
        public List<string> Owns = new List<string>();

        /// <summary>Blendshape weights, 0-100, already expanded to concrete names.</summary>
        public Dictionary<string, float> Shapes = new Dictionary<string, float>();

        /// <summary>Discard tiles the expression flips: true shows, false hides.</summary>
        public Dictionary<string, bool> Tiles = new Dictionary<string, bool>();

        /// <summary>Name of the bone pose (ears, tail) held with the expression; null leaves them at rest.</summary>
        public string Pose;
    }

    /// <summary>
    /// How far one bone turns in a pose, in degrees about the avatar's own
    /// axes rather than the bone's: <see cref="Forward"/> tips it towards
    /// the way the avatar faces, <see cref="Out"/> leans it away from the
    /// middle of the body, <see cref="Twist"/> turns it about the vertical.
    /// </summary>
    public struct BoneTurn
    {
        public float Forward;
        public float Out;
        public float Twist;
    }

    public enum Hand
    {
        Left,
        Right,
    }

    /// <summary>
    /// The gesture-to-expression table from gestures.json and the rules for
    /// sharing the face with a tracker.
    /// </summary>
    public sealed class GestureLayout
    {
        /// <summary>Regions a tracker can drive, each backed by its own blendshape set.</summary>
        public static readonly string[] TrackedRegions = { "eyes", "brows", "mouth" };

        /// <summary>Region for shapes no tracker drives (blush, tears); always safe to animate.</summary>
        public const string FreeRegion = "other";

        public Dictionary<int, string> Left = new Dictionary<int, string>();
        public Dictionary<int, string> Right = new Dictionary<int, string>();
        public Dictionary<string, Expression> Expressions = new Dictionary<string, Expression>();

        /// <summary>
        /// Bone poses by name. Each maps a bone to its turn; a name without a
        /// side suffix (<c>Ear2</c>) stands for the <c>.L</c> and <c>.R</c>
        /// bones, mirrored.
        /// </summary>
        public Dictionary<string, Dictionary<string, BoneTurn>> Poses = new Dictionary<string, Dictionary<string, BoneTurn>>();

        public Dictionary<int, string> For(Hand hand) => hand == Hand.Left ? Left : Right;

        /// <summary>Expands the <c>Name*</c> shorthand to its Left and Right blendshapes.</summary>
        public static IEnumerable<string> Expand(string shape)
        {
            if (!shape.EndsWith("*", StringComparison.Ordinal)) return new[] { shape };
            var stem = shape.Substring(0, shape.Length - 1);
            return new[] { stem + "Left", stem + "Right" };
        }

        /// <summary>
        /// The blendshapes an expression animates. With a tracker live it keeps
        /// only the regions it owns, so the tracker goes on driving the rest of
        /// the face: closed gesture eyes over a mouth that is still talking.
        /// </summary>
        /// <param name="regionOf">Maps a blendshape name to its face region.</param>
        public static Dictionary<string, float> ShapesFor(Expression expression, bool tracked, Func<string, string> regionOf)
        {
            if (!tracked) return new Dictionary<string, float>(expression.Shapes);
            return expression.Shapes
                .Where(pair =>
                {
                    var region = regionOf(pair.Key);
                    return region == FreeRegion || expression.Owns.Contains(region);
                })
                .ToDictionary(pair => pair.Key, pair => pair.Value);
        }

        /// <summary>Gesture values on one hand whose expression owns <paramref name="region"/>.</summary>
        public List<int> OwningGestures(Hand hand, string region)
        {
            return For(hand)
                .Where(pair => Expressions[pair.Value].Owns.Contains(region))
                .Select(pair => pair.Key)
                .OrderBy(value => value)
                .ToList();
        }

        /// <summary>
        /// The pose held for a pair of gesture values. As with the face, the
        /// right hand wins: its expression's pose if it has one, otherwise
        /// the left hand's. Null means rest.
        /// </summary>
        public string PoseFor(int left, int right)
        {
            foreach (var (hand, value) in new[] { (Hand.Right, right), (Hand.Left, left) })
            {
                if (For(hand).TryGetValue(value, out var id) && Expressions.TryGetValue(id, out var expression) &&
                    expression.Pose != null)
                    return expression.Pose;
            }

            return null;
        }

        /// <summary>
        /// A pose's turns with the unsided names expanded to both sides. Both
        /// sides get the same turn; "away from the middle" is the opposite
        /// rotation on each side, which is for whoever applies it to work out
        /// from where the bone is. A sided entry overrides an unsided one.
        /// </summary>
        /// <param name="isBone">Whether a name is a bone of the skeleton as it stands.</param>
        public Dictionary<string, BoneTurn> ExpandPose(string pose, Func<string, bool> isBone)
        {
            var expanded = new Dictionary<string, BoneTurn>();
            foreach (var pair in Poses[pose].Where(pair => !isBone(pair.Key)))
            {
                expanded[pair.Key + ".L"] = pair.Value;
                expanded[pair.Key + ".R"] = pair.Value;
            }

            foreach (var pair in Poses[pose].Where(pair => isBone(pair.Key))) expanded[pair.Key] = pair.Value;
            return expanded;
        }

        /// <returns>One sentence per problem; empty when the table is usable.</returns>
        public List<string> Validate(ICollection<string> knownShapes, ICollection<string> knownTiles)
        {
            var problems = new List<string>();
            foreach (var hand in new[] { Hand.Left, Hand.Right })
            {
                foreach (var pair in For(hand))
                {
                    if (pair.Key < 1 || pair.Key > 7)
                        problems.Add(hand + " hand maps gesture value " + pair.Key + ", but VRChat reports 1 to 7.");
                    if (!Expressions.ContainsKey(pair.Value))
                        problems.Add(hand + " hand gesture " + pair.Key + " selects the unknown expression \"" + pair.Value + "\".");
                }
            }

            foreach (var expression in Expressions.Values)
            {
                foreach (var region in expression.Owns)
                {
                    if (!TrackedRegions.Contains(region))
                        problems.Add("Expression " + expression.Id + " owns \"" + region + "\", which is not a tracked region.");
                }

                foreach (var shape in expression.Shapes.Keys)
                {
                    if (!knownShapes.Contains(shape))
                        problems.Add("Expression " + expression.Id + " uses the blendshape \"" + shape + "\", which blendshapes.json does not define.");
                }

                foreach (var tile in expression.Tiles.Keys)
                {
                    if (!knownTiles.Contains(tile))
                        problems.Add("Expression " + expression.Id + " flips the tile \"" + tile + "\", which uv-tiles.json does not define.");
                }

                if (expression.Pose != null && !Poses.ContainsKey(expression.Pose))
                    problems.Add("Expression " + expression.Id + " holds the pose \"" + expression.Pose + "\", which gestures.json does not define.");
            }

            return problems;
        }
    }
}
