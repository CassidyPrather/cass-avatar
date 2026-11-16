using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using Newtonsoft.Json.Linq;
using UnityEngine;
using Wirenook.Assets.Editor;
using Wirenook.Cass.Core;

namespace Wirenook.Cass.Editor
{
    /// <summary>
    /// Reads the contracts under Spec/. Blender validates its export against
    /// the same files, so a name only ever has to be right in one place.
    /// </summary>
    public static class CassSpec
    {
        public const string Package = "Packages/net.wirenook.cass";
        public const string ExportFolder = Package + "/BlenderExports";
        public const string ModelPath = ExportFolder + "/cass.fbx";

        /// <summary>
        /// The same avatar at its low-polygon level: the same object names
        /// on the same skeleton. Mobile builds and variants that ask for it
        /// take their meshes from here (see <see cref="CassBuildPlugin"/>).
        /// </summary>
        public const string LiteModelPath = ExportFolder + "/cass-lite.fbx";
        public const string GeneratedFolder = Package + "/Generated";
        public const string PrefabFolder = Package + "/Prefabs";

        private static JObject Read(string file)
        {
            return JObject.Parse(File.ReadAllText(Path.Combine(Package, "Spec", file)));
        }

        public static BlendshapeSpec Blendshapes()
        {
            var json = Read("blendshapes.json");
            return new BlendshapeSpec
            {
                Mesh = (string)json["mesh"],
                Visemes = json["visemes"].Select(token => (string)token).ToList(),
                Tracking = json["faceTracking"]
                    .Select(token => new TrackingKey
                    {
                        Key = (string)token["key"],
                        Region = (string)token["region"],
                        Core = (string)token["tier"] == "core",
                    })
                    .ToList(),
                Mmd = json["mmd"].ToDictionary(token => (string)token["name"], token => (string)token["region"]),
            };
        }

        public static TileLayout Tiles()
        {
            var json = Read("uv-tiles.json");
            var layout = new TileLayout { Columns = (int)json["columns"], Rows = (int)json["rows"] };
            foreach (var token in json["tiles"])
            {
                var toggle = token["toggle"];
                layout.Tiles.Add(new Tile
                {
                    Id = (string)token["id"],
                    Column = (int)token["column"],
                    Row = (int)token["row"],
                    Shown = (bool)token["shown"],
                    Hides = token["hides"]?.Select(zone => (string)zone).ToList() ?? new List<string>(),
                    Toggle = toggle == null
                        ? null
                        : new TileToggle
                        {
                            Parameter = (string)toggle["parameter"],
                            Label = (string)toggle["label"],
                            Icon = (string)toggle["icon"],
                        },
                });
            }

            Require(layout.Validate(), "uv-tiles.json");
            return layout;
        }

        public static GestureLayout Gestures()
        {
            var json = Read("gestures.json");
            var values = json["gestureValues"].ToObject<Dictionary<string, int>>();
            var layout = new GestureLayout();

            foreach (var hand in new[] { Hand.Left, Hand.Right })
            {
                var table = (JObject)json[hand.ToString().ToLowerInvariant()];
                foreach (var entry in table)
                {
                    if (!values.TryGetValue(entry.Key, out var value))
                        throw new InvalidDataException("gestures.json: \"" + entry.Key + "\" is not a gesture name.");
                    layout.For(hand)[value] = (string)entry.Value;
                }
            }

            foreach (var entry in (JObject)json["expressions"])
            {
                var expression = new Expression
                {
                    Id = entry.Key,
                    Label = (string)entry.Value["label"],
                    Owns = entry.Value["owns"]?.Select(region => (string)region).ToList() ?? new List<string>(),
                };
                foreach (var shape in (JObject)entry.Value["shapes"] ?? new JObject())
                {
                    foreach (var name in GestureLayout.Expand(shape.Key))
                        expression.Shapes[name] = (float)shape.Value;
                }

                foreach (var tile in (JObject)entry.Value["tiles"] ?? new JObject())
                    expression.Tiles[tile.Key] = (bool)tile.Value;
                expression.Pose = (string)entry.Value["pose"];
                layout.Expressions[expression.Id] = expression;
            }

            var skeleton = Skeleton();
            foreach (var entry in (JObject)json["poses"] ?? new JObject())
            {
                var turns = new Dictionary<string, BoneTurn>();
                foreach (var bone in (JObject)entry.Value)
                {
                    var degrees = bone.Value.Select(value => (float)value).ToList();
                    if (degrees.Count != 3)
                        throw new InvalidDataException("gestures.json: pose \"" + entry.Key + "\" needs [forward, out, twist] for " + bone.Key + ".");
                    var sided = skeleton.IsExtra(bone.Key);
                    if (!sided && !(skeleton.IsExtra(bone.Key + ".L") && skeleton.IsExtra(bone.Key + ".R")))
                        throw new InvalidDataException("gestures.json: pose \"" + entry.Key + "\" turns \"" + bone.Key +
                                                       "\", which is not an extra bone in skeleton.json. Poses may not move humanoid bones.");
                    turns[bone.Key] = new BoneTurn { Forward = degrees[0], Out = degrees[1], Twist = degrees[2] };
                }

                layout.Poses[entry.Key] = turns;
            }

            var shapes = Blendshapes();
            Require(layout.Validate(shapes.All().ToList(), Tiles().Tiles.Select(tile => tile.Id).ToList()), "gestures.json");
            return layout;
        }

        public static SkeletonSpec Skeleton()
        {
            var json = Read("skeleton.json");
            var spec = new SkeletonSpec();
            foreach (var entry in (JObject)json["humanoid"])
            {
                if (!Enum.TryParse<HumanBodyBones>(entry.Key, out var bone))
                    throw new InvalidDataException("skeleton.json: \"" + entry.Key + "\" is not a Unity humanoid bone.");
                spec.Humanoid[bone] = (string)entry.Value;
            }

            foreach (var token in json["extra"] ?? new JArray())
            {
                var twist = token["twist"];
                spec.Extra.Add(new ExtraBone
                {
                    Name = (string)token["name"],
                    Parent = (string)token["parent"],
                    Physics = (string)token["physics"],
                    TwistSource = twist == null ? null : (string)twist["source"],
                    TwistWeight = twist == null ? 0f : (float)twist["weight"],
                });
            }

            return spec;
        }

        public static VariantSpec Variants()
        {
            var json = Read("variants.json");
            var spec = new VariantSpec { Description = (string)json["description"] };
            foreach (var token in json["variants"])
            {
                spec.Variants.Add(new Variant
                {
                    Slug = (string)token["slug"],
                    Extends = (string)token["extends"],
                    Lite = (string)token["model"] == "lite",
                    WorstRank = (string)token["worstRank"] ?? "Good",
                    WorstRankMobile = (string)token["worstRankMobile"] ?? (string)token["worstRank"] ?? "Good",
                    Platforms = token["platforms"]?.Select(name => WirenookPlatform.Parse((string)name)).ToList()
                                ?? new List<Platform> { Platform.Pc, Platform.Android, Platform.Ios },
                    Features = token["features"]?.Select(path => (string)path).ToList() ?? new List<string>(),
                });
            }

            return spec;
        }

        private static void Require(List<string> problems, string file)
        {
            if (problems.Count == 0) return;
            throw new InvalidDataException(file + " is inconsistent:\n  " + string.Join("\n  ", problems));
        }
    }

    public sealed class TrackingKey
    {
        public string Key;
        public string Region;

        /// <summary>Core keys must exist on the mesh; the rest are welcome extras.</summary>
        public bool Core;
    }

    public sealed class BlendshapeSpec
    {
        public string Mesh;
        public List<string> Visemes;
        public List<TrackingKey> Tracking;

        /// <summary>MMD blendshape name to face region.</summary>
        public Dictionary<string, string> Mmd;

        public IEnumerable<string> All()
        {
            return Visemes.Concat(Tracking.Select(key => key.Key)).Concat(Mmd.Keys);
        }

        /// <summary>The face region a blendshape belongs to, for sharing the face with a tracker.</summary>
        public string RegionOf(string shape)
        {
            var tracked = Tracking.FirstOrDefault(key => key.Key == shape);
            if (tracked != null) return tracked.Region;
            if (Mmd.TryGetValue(shape, out var region)) return region;
            if (Visemes.Contains(shape)) return "mouth";
            throw new KeyNotFoundException("blendshapes.json does not define \"" + shape + "\".");
        }
    }

    public sealed class SkeletonSpec
    {
        public Dictionary<HumanBodyBones, string> Humanoid = new Dictionary<HumanBodyBones, string>();

        /// <summary>Bones outside the humanoid rig, such as the ear chains.</summary>
        public List<ExtraBone> Extra = new List<ExtraBone>();

        /// <summary>The bones physics components attach to, each the first of a chain.</summary>
        public IEnumerable<ExtraBone> ChainRoots() => Extra.Where(bone => bone.Physics != null);

        /// <summary>The helpers that follow a neighbour's twist.</summary>
        public IEnumerable<ExtraBone> TwistBones() => Extra.Where(bone => bone.TwistSource != null);

        public bool IsExtra(string name) => Extra.Any(bone => bone.Name == name);
    }

    public sealed class ExtraBone
    {
        public string Name;
        public string Parent;

        /// <summary>On the first bone of a chain: which PhysBone settings it gets. Null elsewhere.</summary>
        public string Physics;

        /// <summary>On a twist helper: the bone whose turn about its length it follows. Null elsewhere.</summary>
        public string TwistSource;

        /// <summary>How much of the source's twist a twist helper takes, 0 to 1.</summary>
        public float TwistWeight;
    }

    public sealed class VariantSpec
    {
        /// <summary>Description text shared by every variant; it carries the source link.</summary>
        public string Description;

        public List<Variant> Variants = new List<Variant>();
    }

    public sealed class Variant
    {
        public string Slug;

        /// <summary>Slug of the variant this one builds on; null builds on the root prefab.</summary>
        public string Extends;

        /// <summary>Builds from the low-polygon model on every platform, not only on mobile.</summary>
        public bool Lite;

        /// <summary>The worst VRChat performance rank this variant may build to on PC.</summary>
        public string WorstRank;

        /// <summary>The same for Android and iOS, which VRChat ranks on a much stricter scale.</summary>
        public string WorstRankMobile;

        /// <summary>The platforms this variant is built and uploaded for.</summary>
        public List<Platform> Platforms;

        public string WorstRankFor(Platform platform) => platform == Platform.Pc ? WorstRank : WorstRankMobile;

        /// <summary>Asset paths of the feature prefabs this variant adds.</summary>
        public List<string> Features;
    }
}
