using System.Collections.Generic;
using System.Linq;
using NUnit.Framework;
using Wirenook.Cass.Core;

namespace Wirenook.Cass.Tests
{
    public class UploadGuardTests
    {
        private static readonly string[] Tags = { "author_tag_ai", "author_tag_agplv3" };
        private const string Description = "Source: github.com/CassidyPrather/cass-avatar";

        [Test]
        public void AcceptsACompliantRecord()
        {
            var problems = UploadGuard.Check(new UploadPolicy(), "cass", Description, Tags, "public");
            Assert.AreEqual(0, problems.Count, string.Join(" ", problems));
        }

        [Test]
        public void RejectsADescriptionWithoutTheSourceLink()
        {
            var problems = UploadGuard.Check(new UploadPolicy(), "cass", "A rabbit in a hat.", Tags, "public");
            Assert.AreEqual(1, problems.Count);
            StringAssert.Contains("github.com/CassidyPrather/cass-avatar", problems[0]);
        }

        [Test]
        public void AcceptsAnAlternativeDistributionMarker()
        {
            var policy = new UploadPolicy { DistributionMarkers = new[] { "github.com/CassidyPrather/cass-avatar", "wirenook.net/vrchat" } };
            var problems = UploadGuard.Check(policy, "cass", "Get it at WIRENOOK.NET/vrchat", Tags, "public");
            Assert.AreEqual(0, problems.Count, string.Join(" ", problems));
        }

        [Test]
        public void AcceptsTheLinkAsVRChatStoresIt()
        {
            // Copied from a record read back after an upload.
            const string stored =
                "Source\u201A licence \uFF08AGPLv3\uFF09 and downloads\u02F8 github\u2024com\u2044CassidyPrather\u2044cass-avatar";
            var problems = UploadGuard.Check(new UploadPolicy(), "cass", stored, Tags, "public");
            Assert.AreEqual(0, problems.Count, string.Join(" ", problems));
        }

        [Test]
        public void RejectsMissingRequiredTags()
        {
            var problems = UploadGuard.Check(new UploadPolicy(), "cass", Description, new[] { "author_tag_ai" }, "public");
            Assert.AreEqual(1, problems.Count);
            StringAssert.Contains("author_tag_agplv3", problems[0]);
        }

        [Test]
        public void RejectsAPrivateUpload()
        {
            var problems = UploadGuard.Check(new UploadPolicy(), "cass", Description, Tags, "private");
            Assert.AreEqual(1, problems.Count);
            StringAssert.Contains("public", problems[0]);
        }

        [Test]
        public void ReportsEveryProblemAtOnce()
        {
            var problems = UploadGuard.Check(new UploadPolicy(), "", null, null, null);
            Assert.AreEqual(5, problems.Count);
        }
    }

    public class TileLayoutTests
    {
        private static TileLayout Layout()
        {
            return new TileLayout
            {
                Tiles = new List<Tile>
                {
                    new Tile { Id = "always", Column = 0, Row = 0 },
                    new Tile { Id = "body.torso", Column = 1, Row = 0 },
                    new Tile { Id = "body.arms", Column = 2, Row = 0 },
                    new Tile { Id = "sweater", Column = 0, Row = 1, Hides = new List<string> { "body.torso", "body.arms" } },
                    new Tile { Id = "vest", Column = 1, Row = 1, Shown = false, Hides = new List<string> { "body.torso" } },
                },
            };
        }

        [Test]
        public void AShownGarmentHidesTheSkinItCovers()
        {
            var shown = Layout().Resolve();
            Assert.IsTrue(shown["sweater"]);
            Assert.IsFalse(shown["body.torso"]);
            Assert.IsFalse(shown["body.arms"]);
            Assert.IsTrue(shown["always"]);
        }

        [Test]
        public void TakingTheGarmentOffShowsTheSkinAgain()
        {
            var shown = Layout().Resolve(new Dictionary<string, bool> { { "sweater", false } });
            Assert.IsTrue(shown["body.torso"]);
            Assert.IsTrue(shown["body.arms"]);
        }

        /// <summary>Shorts that give way to a skirt, a vest that needs its sweater, and hair that is short or long.</summary>
        private static TileLayout Wardrobe()
        {
            return new TileLayout
            {
                Tiles = new List<Tile>
                {
                    new Tile { Id = "always", Column = 0, Row = 0 },
                    new Tile { Id = "body.torso", Column = 1, Row = 0 },
                    new Tile { Id = "body.hips", Column = 2, Row = 0 },
                    new Tile
                    {
                        Id = "sweater", Column = 0, Row = 1, Hides = new List<string> { "body.torso" },
                        Toggle = new TileToggle { Parameter = "Top", Label = "Sweater" },
                    },
                    new Tile
                    {
                        Id = "shorts", Column = 1, Row = 1, Hides = new List<string> { "body.hips" },
                        Toggle = new TileToggle { Parameter = "Bottom", Label = "Shorts", Unless = new List<string> { "Skirt" } },
                    },
                    new Tile
                    {
                        Id = "skirt", Column = 2, Row = 1, Shown = false, Hides = new List<string> { "body.hips" },
                        Toggle = new TileToggle { Parameter = "Skirt", Label = "Skirt" },
                    },
                    new Tile
                    {
                        Id = "vest", Column = 3, Row = 1, Shown = false,
                        Toggle = new TileToggle { Parameter = "Vest", Label = "Vest", Needs = new List<string> { "Top" } },
                    },
                    new Tile { Id = "hair.short", Column = 0, Row = 2, Toggle = new TileToggle { Parameter = "Long", When = false } },
                    new Tile { Id = "hair.long", Column = 1, Row = 2, Shown = false, Toggle = new TileToggle { Parameter = "Long", Label = "Long Hair" } },
                },
            };
        }

        private static Dictionary<string, bool> Wearing(params (string parameter, bool value)[] parameters)
        {
            return Wardrobe().ResolveFor(parameters.ToDictionary(entry => entry.parameter, entry => entry.value));
        }

        [Test]
        public void SwitchParametersRestSoThatEveryTileRestsAsMarked()
        {
            var layout = Wardrobe();
            CollectionAssert.IsEmpty(layout.Validate());
            CollectionAssert.AreEqual(new[] { "Top", "Bottom", "Skirt", "Vest", "Long" }, layout.Defaults().Select(known => known.Parameter).ToList());
            CollectionAssert.AreEqual(new[] { true, true, false, false, false }, layout.Defaults().Select(known => known.Value).ToList());

            var resting = layout.ResolveFor();
            foreach (var tile in layout.Tiles.Where(tile => tile.Toggle != null))
                Assert.AreEqual(tile.Shown, resting[tile.Id], tile.Id);
        }

        [Test]
        public void AlternativesShareOneSwitch()
        {
            var shown = Wearing(("Long", true));
            Assert.IsTrue(shown["hair.long"]);
            Assert.IsFalse(shown["hair.short"]);
        }

        [Test]
        public void AGarmentGivesWayToTheOneNamedInUnless()
        {
            var shown = Wearing(("Skirt", true));
            Assert.IsTrue(shown["skirt"]);
            Assert.IsFalse(shown["shorts"], "the shorts are still switched on, and hidden");
            Assert.IsFalse(shown["body.hips"]);

            shown = Wearing(("Skirt", true), ("Bottom", false));
            Assert.IsFalse(shown["body.hips"], "the skirt alone still covers the hips");

            shown = Wearing(("Bottom", false));
            Assert.IsTrue(shown["body.hips"], "with neither, the hips show");
        }

        [Test]
        public void ALayerIsOnlyShownOverWhatItNeeds()
        {
            Assert.IsTrue(Wearing(("Vest", true))["vest"]);
            Assert.IsFalse(Wearing(("Vest", true), ("Top", false))["vest"]);
        }

        [Test]
        public void ATileWhoseParametersRestAgainstItsMarkIsAProblem()
        {
            // Short and long hair share a switch, so they cannot both rest shown.
            var layout = Wardrobe();
            layout.Get("hair.long").Shown = true;
            Assert.IsTrue(layout.Validate().Any(problem => problem.Contains("hair.long")));

            // The shorts rest shown, which a skirt that also rests shown would not allow.
            layout = Wardrobe();
            layout.Get("skirt").Shown = true;
            Assert.IsTrue(layout.Validate().Any(problem => problem.Contains("shorts")));

            layout = Wardrobe();
            layout.Get("shorts").Toggle.Unless.Add("Cape");
            Assert.IsTrue(layout.Validate().Any(problem => problem.Contains("Cape")));
        }

        [Test]
        public void NoneOfIsTheExactOppositeOfAnyOf()
        {
            var layout = Wardrobe();
            var covers = layout.Covering("body.hips").Select(TileLayout.ShownWhen).ToList();
            var uncovered = TileLayout.NoneOf(covers);
            Assert.IsNotEmpty(uncovered);

            // Every combination of the two parameters involved, both ways round.
            foreach (var bottom in new[] { false, true })
            {
                foreach (var skirt in new[] { false, true })
                {
                    var values = new Dictionary<string, bool> { { "Bottom", bottom }, { "Skirt", skirt } };
                    bool Holds(List<Condition> all) => all.All(condition => values[condition.Parameter] == condition.Value);
                    Assert.AreEqual(!covers.Any(Holds), uncovered.Any(Holds), "Bottom " + bottom + ", Skirt " + skirt);
                    Assert.AreEqual(!covers.Any(Holds), layout.ResolveFor(values)["body.hips"], "resolved the same way");
                }
            }

            // Something and its opposite can never both fail to hold.
            var always = new List<List<Condition>>
            {
                new List<Condition> { new Condition("A", true) }, new List<Condition> { new Condition("A", false) },
            };
            CollectionAssert.IsEmpty(TileLayout.NoneOf(always));
        }

        [Test]
        public void AZoneStaysHiddenWhileAnyGarmentCoversIt()
        {
            var shown = Layout().Resolve(new Dictionary<string, bool> { { "sweater", false }, { "vest", true } });
            Assert.IsFalse(shown["body.torso"]);
            Assert.IsTrue(shown["body.arms"]);
        }

        [Test]
        public void ZonesAreTheTilesSomethingCanHide()
        {
            var zones = Layout().Zones().Select(tile => tile.Id).ToList();
            CollectionAssert.AreEquivalent(new[] { "body.torso", "body.arms" }, zones);
        }

        [Test]
        public void ValidLayoutHasNoProblems()
        {
            Assert.AreEqual(0, Layout().Validate().Count);
        }

        [Test]
        public void DetectsSharedCellsAndUnknownZones()
        {
            var layout = Layout();
            layout.Tiles.Add(new Tile { Id = "clash", Column = 1, Row = 0, Hides = new List<string> { "body.tail" } });
            var problems = layout.Validate();
            Assert.AreEqual(2, problems.Count, string.Join(" ", problems));
        }

        [Test]
        public void RequiresTheAlwaysTileAtTheOrigin()
        {
            var layout = Layout();
            layout.Tiles[0].Id = "something-else";
            Assert.AreEqual(1, layout.Validate().Count);
        }
    }

    public class GestureLayoutTests
    {
        private static string RegionOf(string shape)
        {
            if (shape.StartsWith("Eye")) return "eyes";
            if (shape.StartsWith("Brow")) return "brows";
            if (shape == "Blush") return GestureLayout.FreeRegion;
            return "mouth";
        }

        private static GestureLayout Layout()
        {
            var layout = new GestureLayout();
            layout.Expressions["sleepy"] = new Expression
            {
                Id = "sleepy",
                Owns = new List<string> { "eyes" },
                Shapes = new Dictionary<string, float> { { "EyeClosedLeft", 100 }, { "EyeClosedRight", 100 }, { "MouthSmile", 40 }, { "Blush", 50 } },
            };
            layout.Expressions["angry"] = new Expression
            {
                Id = "angry",
                Owns = new List<string> { "brows" },
                Shapes = new Dictionary<string, float> { { "BrowDown", 100 }, { "MouthFrown", 60 } },
            };
            layout.Left[1] = "sleepy";
            layout.Left[3] = "angry";
            layout.Right[2] = "sleepy";
            return layout;
        }

        [Test]
        public void ExpandsThePairShorthand()
        {
            CollectionAssert.AreEqual(new[] { "EyeClosedLeft", "EyeClosedRight" }, GestureLayout.Expand("EyeClosed*").ToList());
            CollectionAssert.AreEqual(new[] { "JawOpen" }, GestureLayout.Expand("JawOpen").ToList());
        }

        [Test]
        public void UntrackedExpressionsAnimateEverything()
        {
            var shapes = GestureLayout.ShapesFor(Layout().Expressions["sleepy"], false, RegionOf);
            Assert.AreEqual(4, shapes.Count);
        }

        [Test]
        public void TrackedExpressionsKeepOnlyOwnedRegionsAndFreeShapes()
        {
            var shapes = GestureLayout.ShapesFor(Layout().Expressions["sleepy"], true, RegionOf);
            CollectionAssert.AreEquivalent(new[] { "EyeClosedLeft", "EyeClosedRight", "Blush" }, shapes.Keys.ToList());
        }

        [Test]
        public void FindsTheGesturesThatOwnARegion()
        {
            var layout = Layout();
            CollectionAssert.AreEqual(new[] { 1 }, layout.OwningGestures(Hand.Left, "eyes"));
            CollectionAssert.AreEqual(new[] { 3 }, layout.OwningGestures(Hand.Left, "brows"));
            CollectionAssert.AreEqual(new[] { 2 }, layout.OwningGestures(Hand.Right, "eyes"));
            Assert.AreEqual(0, layout.OwningGestures(Hand.Right, "mouth").Count);
        }

        [Test]
        public void ValidatesShapesTilesRegionsAndGestureValues()
        {
            var layout = Layout();
            var known = new[] { "EyeClosedLeft", "EyeClosedRight", "MouthSmile", "Blush", "BrowDown", "MouthFrown" };
            Assert.AreEqual(0, layout.Validate(known, new string[0]).Count);

            layout.Expressions["angry"].Shapes["Nope"] = 1;
            layout.Expressions["angry"].Tiles["face.missing"] = true;
            layout.Expressions["angry"].Owns.Add("ears");
            layout.Left[9] = "ghost";
            var problems = layout.Validate(known, new string[0]);
            Assert.AreEqual(5, problems.Count, string.Join(" ", problems));
        }

        private static GestureLayout Posed()
        {
            var layout = Layout();
            layout.Poses["droop"] = new Dictionary<string, BoneTurn>
            {
                { "Ear2", new BoneTurn { Forward = -10, Out = 50 } },
                { "Ear2.R", new BoneTurn { Forward = 60 } },
                { "Tail1", new BoneTurn { Forward = -15 } },
            };
            layout.Poses["back"] = new Dictionary<string, BoneTurn> { { "Ear1", new BoneTurn { Forward = -40 } } };
            layout.Expressions["sleepy"].Pose = "droop";
            return layout;
        }

        [Test]
        public void TheRightHandsPoseWinsOnlyWhenItHasOne()
        {
            var layout = Posed();
            Assert.IsNull(layout.PoseFor(0, 0));
            Assert.AreEqual("droop", layout.PoseFor(1, 0));
            // Left 3 is "angry", which has no pose; right 2 is "sleepy".
            Assert.AreEqual("droop", layout.PoseFor(3, 2));
            Assert.IsNull(layout.PoseFor(3, 0));

            layout.Expressions["angry"].Pose = "back";
            Assert.AreEqual("back", layout.PoseFor(3, 0));
            Assert.AreEqual("droop", layout.PoseFor(3, 2));
            // A right-hand gesture with no expression leaves the left hand's pose alone.
            Assert.AreEqual("back", layout.PoseFor(3, 5));
        }

        [Test]
        public void PosesExpandToBothSidesAndSidedEntriesOverride()
        {
            var bones = new[] { "Ear2.L", "Ear2.R", "Tail1" };
            var pose = Posed().ExpandPose("droop", name => bones.Contains(name));

            CollectionAssert.AreEquivalent(bones, pose.Keys.ToList());
            Assert.AreEqual(50f, pose["Ear2.L"].Out);
            Assert.AreEqual(-10f, pose["Ear2.L"].Forward);
            Assert.AreEqual(60f, pose["Ear2.R"].Forward);
            Assert.AreEqual(0f, pose["Ear2.R"].Out);
            Assert.AreEqual(-15f, pose["Tail1"].Forward);
        }

        [Test]
        public void ValidatesThatAnExpressionsPoseExists()
        {
            var layout = Posed();
            var known = new[] { "EyeClosedLeft", "EyeClosedRight", "MouthSmile", "Blush", "BrowDown", "MouthFrown" };
            Assert.AreEqual(0, layout.Validate(known, new string[0]).Count);

            layout.Expressions["angry"].Pose = "missing";
            Assert.AreEqual(1, layout.Validate(known, new string[0]).Count);
        }
    }
}
