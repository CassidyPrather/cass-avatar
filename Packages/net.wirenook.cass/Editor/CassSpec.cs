using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using Newtonsoft.Json.Linq;
using UnityEngine;
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
                layout.Expressions[expression.Id] = expression;
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
                spec.Extra.Add(new ExtraBone { Name = (string)token["name"], Parent = (string)token["parent"] });
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
                    Summary = (string)token["summary"] ?? "",
                    WorstRank = (string)token["worstRank"] ?? "Good",
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

        /// <summary>The first bone of every extra chain: the ones physics components attach to.</summary>
        public IEnumerable<ExtraBone> ChainRoots()
        {
            var extras = new HashSet<string>(Extra.Select(bone => bone.Name));
            return Extra.Where(bone => !extras.Contains(bone.Parent));
        }
    }

    public sealed class ExtraBone
    {
        public string Name;
        public string Parent;
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

        public string Summary;

        /// <summary>The worst VRChat performance rank this variant may build to.</summary>
        public string WorstRank;

        /// <summary>Asset paths of the feature prefabs this variant adds.</summary>
        public List<string> Features;
    }
}
