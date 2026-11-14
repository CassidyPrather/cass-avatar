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
            }

            return problems;
        }
    }
}
