using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using Newtonsoft.Json.Linq;
using UnityEditor;
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

        /// <summary>
        /// The export a build takes its meshes from: one per wardrobe and
        /// fidelity level, all on the same skeleton. No wardrobe named is
        /// the first one, the one the prefabs hold.
        /// </summary>
        public static string ModelFor(string wardrobe, bool lite)
        {
            return ExportFolder + "/cass" + (string.IsNullOrEmpty(wardrobe) ? "" : "-" + wardrobe) + (lite ? "-lite" : "") + ".fbx";
        }
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
                    Mobile = (bool?)token["mobile"] ?? true,
                    Cover = (bool?)token["cover"] ?? false,
                    Hides = token["hides"]?.Select(zone => (string)zone).ToList() ?? new List<string>(),
                    Toggle = toggle == null
                        ? null
                        : new TileToggle
                        {
                            Parameter = (string)toggle["parameter"],
                            Label = (string)toggle["label"],
                            Icon = (string)toggle["icon"],
                            When = (bool?)toggle["when"] ?? true,
                            Rests = (bool?)toggle["rests"],
                            Needs = toggle["needs"]?.Select(parameter => (string)parameter).ToList() ?? new List<string>(),
                            Unless = toggle["unless"]?.Select(parameter => (string)parameter).ToList() ?? new List<string>(),
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
            Dictionary<string, Dictionary<string, BoneTurn>> PosesIn(JObject table)
            {
                var poses = new Dictionary<string, Dictionary<string, BoneTurn>>();
                foreach (var entry in table ?? new JObject())
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

                    poses[entry.Key] = turns;
                }

                return poses;
            }

            layout.Poses = PosesIn((JObject)json["poses"]);
            foreach (var worn in (JObject)json["posesWhile"] ?? new JObject())
                layout.PosesWhile[worn.Key] = PosesIn((JObject)worn.Value);

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
                var follow = token["follow"];
                spec.Extra.Add(new ExtraBone
                {
                    Name = (string)token["name"],
                    Parent = (string)token["parent"],
                    Physics = (string)token["physics"],
                    Tile = (string)token["tile"],
                    PcOnly = (bool?)token["pcOnly"] ?? false,
                    FollowSource = follow == null ? null : (string)follow["source"],
                    FollowWeight = follow == null ? 0f : (float)follow["weight"],
                    FollowWeightAlone = follow == null ? 0f : (float?)follow["weightAlone"] ?? (float)follow["weight"],
                    TwistSource = twist == null ? null : (string)twist["source"],
                    TwistWeight = twist == null ? 0f : (float)twist["weight"],
                });
            }

            foreach (var token in json["colliders"] ?? new JArray())
            {
                spec.Colliders.Add(new BoneCollider
                {
                    Bone = (string)token["bone"],
                    To = (string)token["to"],
                    Radius = (float)token["radius"],
                    Physics = (token["physics"] ?? new JArray()).Select(name => (string)name).ToList(),
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
                    Wardrobe = (string)token["wardrobe"],
                    WorstRank = (string)token["worstRank"] ?? "Good",
                    WorstRankMobile = (string)token["worstRankMobile"] ?? (string)token["worstRank"] ?? "Good",
                    Platforms = token["platforms"]?.Select(name => WirenookPlatform.Parse((string)name)).ToList()
                                ?? new List<Platform> { Platform.Pc, Platform.Android, Platform.Ios },
                    // A feature is a prefab's path, or that and where it is built for.
                    Features = token["features"]?.Select(FeaturePath).ToList() ?? new List<string>(),
                    PcOnlyFeatures = token["features"]?.Where(feature => feature is JObject && ((bool?)feature["pcOnly"] ?? false))
                        .Select(FeaturePath).ToList() ?? new List<string>(),
                    Local = token["local"]?.Select(asset => new LocalAsset
                    {
                        Guid = (string)asset["guid"],
                        Name = (string)asset["name"],
                        Author = (string)asset["author"],
                        Url = (string)asset["url"],
                        AtView = (bool?)asset["atView"] ?? false,
                    }).ToList() ?? new List<LocalAsset>(),
                });
            }

            foreach (var token in json["deprecated"] ?? new JArray())
            {
                spec.Deprecated.Add(new DeprecatedVariant
                {
                    Slug = (string)token["slug"],
                    AvatarId = (string)token["avatarId"],
                    ReplacedBy = (string)token["replacedBy"],
                    Why = (string)token["why"],
                });
            }

            return spec;
        }

        private static string FeaturePath(JToken feature) => feature is JObject ? (string)feature["path"] : (string)feature;

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

        /// <summary>The bones that are carried part of the way with a limb.</summary>
        public IEnumerable<ExtraBone> FollowBones() => Extra.Where(bone => bone.FollowSource != null);

        /// <summary>The capsules that keep physics chains off the body.</summary>
        public List<BoneCollider> Colliders = new List<BoneCollider>();

        /// <summary>The capsules that push the chains with one set of physics settings.</summary>
        public IEnumerable<BoneCollider> CollidersFor(string physics) => Colliders.Where(collider => collider.Physics.Contains(physics));

        public bool IsExtra(string name) => Extra.Any(bone => bone.Name == name);
    }

    public sealed class ExtraBone
    {
        public string Name;
        public string Parent;

        /// <summary>On the first bone of a chain: which PhysBone settings it gets. Null elsewhere.</summary>
        public string Physics;

        /// <summary>
        /// On the first bone of a chain that carries only one garment: the UV
        /// tile the garment is on. The chain's physics runs while that tile
        /// is shown and is left out of a build that cuts the tile away. Null
        /// for chains that are always worn.
        /// </summary>
        public string Tile;

        /// <summary>
        /// On the first bone of a chain: its physics is more than Android and
        /// iOS have room for, and builds for them leave it out.
        /// </summary>
        public bool PcOnly;

        /// <summary>On a bone that is carried with a limb: the bone it turns with. Null elsewhere.</summary>
        public string FollowSource;

        /// <summary>How much of the source's turn from rest such a bone takes, 0 to 1.</summary>
        public float FollowWeight;

        /// <summary>The same for a build that leaves the bone's physics out, where nothing else keeps the limb from coming through.</summary>
        public float FollowWeightAlone;

        /// <summary>On a twist helper: the bone whose turn about its length it follows. Null elsewhere.</summary>
        public string TwistSource;

        /// <summary>How much of the source's twist a twist helper takes, 0 to 1.</summary>
        public float TwistWeight;
    }

    /// <summary>A capsule along a bone, from its joint to the joint of the next.</summary>
    public sealed class BoneCollider
    {
        public string Bone;

        /// <summary>The bone whose joint the capsule ends at.</summary>
        public string To;

        /// <summary>The capsule's thickness, in metres.</summary>
        public float Radius;

        /// <summary>The physics settings (<see cref="ExtraBone.Physics"/>) whose chains it pushes.</summary>
        public List<string> Physics = new List<string>();
    }

    public sealed class VariantSpec
    {
        /// <summary>Description text shared by every variant; it carries the source link.</summary>
        public string Description;

        public List<Variant> Variants = new List<Variant>();

        /// <summary>Variants that are no longer made, and where what they carried went.</summary>
        public List<DeprecatedVariant> Deprecated = new List<DeprecatedVariant>();
    }

    /// <summary>
    /// What is left of a variant that is no longer made: its slug, the
    /// avatar id it was uploaded under (so that it can be taken down from
    /// VRChat), and which variant has what it had.
    /// </summary>
    public sealed class DeprecatedVariant
    {
        public string Slug;
        public string AvatarId;
        public string ReplacedBy;
        public string Why;
    }

    public sealed class Variant
    {
        public string Slug;

        /// <summary>Slug of the variant this one builds on; null builds on the root prefab.</summary>
        public string Extends;

        /// <summary>Builds from the low-polygon model on every platform, not only on mobile.</summary>
        public bool Lite;

        /// <summary>The wardrobe the variant is built wearing; null is the first one, which the prefabs hold.</summary>
        public string Wardrobe;

        /// <summary>The worst VRChat performance rank this variant may build to on PC.</summary>
        public string WorstRank;

        /// <summary>The same for Android and iOS, which VRChat ranks on a much stricter scale.</summary>
        public string WorstRankMobile;

        /// <summary>The platforms this variant is built and uploaded for.</summary>
        public List<Platform> Platforms;

        public string WorstRankFor(Platform platform) => platform == Platform.Pc ? WorstRank : WorstRankMobile;

        /// <summary>Asset paths of the feature prefabs this variant adds.</summary>
        public List<string> Features;

        /// <summary>
        /// Those of <see cref="Features"/> that this variant leaves out of
        /// its Android and iOS builds though the feature itself could work
        /// there: what the variant cannot afford under the mobile ranks.
        /// </summary>
        public List<string> PcOnlyFeatures = new List<string>();

        /// <summary>
        /// Prefabs this variant adds that are not in the repository: things
        /// whose terms do not allow passing them on, kept only on the
        /// machine of whoever holds the licence. A variant with any of them
        /// can only be made where they are all present, and uploads private.
        /// </summary>
        public List<LocalAsset> Local = new List<LocalAsset>();

        /// <summary>The local assets that are not in this project, by name.</summary>
        public List<LocalAsset> Absent() => Local.Where(asset => string.IsNullOrEmpty(AssetDatabase.GUIDToAssetPath(asset.Guid))).ToList();
    }

    /// <summary>
    /// A prefab known only by its GUID, which is all the repository holds of
    /// it. The GUID is the one in the asset's own .meta file as its author
    /// shipped it, so importing the author's package is enough to find it.
    /// </summary>
    public sealed class LocalAsset
    {
        public string Guid;
        public string Name;
        public string Author;
        public string Url;

        /// <summary>Placed at the avatar's view position instead of its feet (a visor, a HUD).</summary>
        public bool AtView;

        /// <summary>How an avatar that carries it credits it.</summary>
        public string Credit => Name + " by " + Author + " (" + Url + ")";
    }
}
