using System.Collections.Generic;
using System.Linq;

namespace Wirenook.Cass.Core
{
    /// <summary>One UV discard tile: a group of faces a single material float can hide.</summary>
    public sealed class Tile
    {
        public string Id;
        public int Column;
        public int Row;

        /// <summary>Whether the tile is visible when nothing animates it.</summary>
        public bool Shown = true;

        /// <summary>Body zones this tile fully covers while it is shown.</summary>
        public List<string> Hides = new List<string>();

        /// <summary>The menu toggle that controls this tile, if it has one.</summary>
        public TileToggle Toggle;
    }

    /// <summary>
    /// When a tile is shown: while its parameter has the value <see cref="When"/>,
    /// every parameter in <see cref="Needs"/> is on and every one in
    /// <see cref="Unless"/> is off. Two tiles that share a parameter with
    /// opposite <see cref="When"/> are alternatives (short hair or long);
    /// <see cref="Unless"/> lets one garment give way to another (shorts
    /// under a skirt) and <see cref="Needs"/> ties a layer to what it is
    /// worn over (a vest over a sweater).
    /// </summary>
    public sealed class TileToggle
    {
        public string Parameter;

        /// <summary>Menu label for the parameter. Left out, the tile has no menu entry of its own.</summary>
        public string Label;
        public string Icon;
        public bool When = true;
        public List<string> Needs = new List<string>();
        public List<string> Unless = new List<string>();
    }

    /// <summary>One parameter having one value.</summary>
    public readonly struct Condition : System.IEquatable<Condition>
    {
        public readonly string Parameter;
        public readonly bool Value;

        public Condition(string parameter, bool value)
        {
            Parameter = parameter;
            Value = value;
        }

        public Condition Opposite => new Condition(Parameter, !Value);

        public bool Equals(Condition other) => Parameter == other.Parameter && Value == other.Value;
        public override bool Equals(object other) => other is Condition condition && Equals(condition);
        public override int GetHashCode() => (Parameter ?? "").GetHashCode() * 2 + (Value ? 1 : 0);
        public override string ToString() => (Value ? "" : "not ") + Parameter;
    }

    /// <summary>
    /// The discard tile grid from uv-tiles.json, plus the rule that makes
    /// outfits safe to wear: a body zone is drawn only while no visible tile
    /// claims to cover it, so skin can never poke through a garment.
    /// </summary>
    public sealed class TileLayout
    {
        public int Columns = 4;
        public int Rows = 4;
        public List<Tile> Tiles = new List<Tile>();

        public Tile Get(string id)
        {
            var tile = Tiles.FirstOrDefault(candidate => candidate.Id == id);
            if (tile == null) throw new KeyNotFoundException("uv-tiles.json has no tile \"" + id + "\".");
            return tile;
        }

        /// <summary>Tiles other tiles can hide.</summary>
        public IEnumerable<Tile> Zones()
        {
            var hidden = new HashSet<string>(Tiles.SelectMany(tile => tile.Hides));
            return Tiles.Where(tile => hidden.Contains(tile.Id));
        }

        /// <summary>The tiles that cover <paramref name="zone"/> when shown.</summary>
        public IEnumerable<Tile> Covering(string zone)
        {
            return Tiles.Where(tile => tile.Hides.Contains(zone));
        }

        /// <summary>
        /// Final visibility of every tile, given which tiles are switched on.
        /// Tiles missing from <paramref name="switched"/> keep their resting state.
        /// </summary>
        public Dictionary<string, bool> Resolve(IReadOnlyDictionary<string, bool> switched = null)
        {
            var shown = Tiles.ToDictionary(
                tile => tile.Id,
                tile => switched != null && switched.TryGetValue(tile.Id, out var value) ? value : tile.Shown);

            foreach (var tile in Tiles)
            {
                if (!shown[tile.Id]) continue;
                foreach (var zone in tile.Hides) shown[zone] = false;
            }

            return shown;
        }

        /// <summary>Everything that has to hold for a switched tile to be shown.</summary>
        public static List<Condition> ShownWhen(Tile tile)
        {
            var conditions = new List<Condition> { new Condition(tile.Toggle.Parameter, tile.Toggle.When) };
            conditions.AddRange(tile.Toggle.Needs.Select(parameter => new Condition(parameter, true)));
            conditions.AddRange(tile.Toggle.Unless.Select(parameter => new Condition(parameter, false)));
            return conditions;
        }

        /// <summary>
        /// The switch parameters, in the order the tiles introduce them, each
        /// with the value it rests at: the one that leaves its tile as
        /// <see cref="Tile.Shown"/> says.
        /// </summary>
        public List<Condition> Defaults()
        {
            var defaults = new List<Condition>();
            foreach (var tile in Tiles.Where(candidate => candidate.Toggle != null))
            {
                if (defaults.Any(known => known.Parameter == tile.Toggle.Parameter)) continue;
                defaults.Add(new Condition(tile.Toggle.Parameter, tile.Shown ? tile.Toggle.When : !tile.Toggle.When));
            }

            return defaults;
        }

        /// <summary>
        /// Final visibility of every tile for a set of parameter values.
        /// Parameters missing from <paramref name="parameters"/> rest at their defaults.
        /// </summary>
        public Dictionary<string, bool> ResolveFor(IReadOnlyDictionary<string, bool> parameters = null)
        {
            var values = Defaults().ToDictionary(known => known.Parameter, known => known.Value);
            if (parameters != null)
            {
                foreach (var given in parameters) values[given.Key] = given.Value;
            }

            var switched = Tiles.Where(tile => tile.Toggle != null).ToDictionary(
                tile => tile.Id,
                tile => ShownWhen(tile).All(condition => values.TryGetValue(condition.Parameter, out var value) && value == condition.Value));
            return Resolve(switched);
        }

        /// <summary>
        /// Turns "none of these hold" into "one of these holds". Each entry
        /// of <paramref name="anyOf"/> is a set of conditions that must all
        /// hold; so is each entry of the result. Sets that contradict
        /// themselves are dropped, which can leave nothing: then "none of
        /// these" can never be true.
        /// </summary>
        public static List<List<Condition>> NoneOf(IEnumerable<List<Condition>> anyOf)
        {
            var result = new List<List<Condition>> { new List<Condition>() };
            foreach (var all in anyOf)
            {
                // One of this set's conditions has to fail, whichever way the rest went.
                var next = new List<List<Condition>>();
                foreach (var chosen in result)
                {
                    foreach (var condition in all)
                    {
                        var failed = condition.Opposite;
                        if (chosen.Contains(condition)) continue;
                        var extended = new List<Condition>(chosen);
                        if (!extended.Contains(failed)) extended.Add(failed);
                        if (!next.Any(known => known.Count == extended.Count && known.All(extended.Contains))) next.Add(extended);
                    }
                }

                result = next;
            }

            return result;
        }

        /// <returns>One sentence per problem; empty when the layout is consistent.</returns>
        public List<string> Validate()
        {
            var problems = new List<string>();
            var seen = new Dictionary<(int, int), string>();
            foreach (var tile in Tiles)
            {
                if (tile.Column < 0 || tile.Column >= Columns || tile.Row < 0 || tile.Row >= Rows)
                    problems.Add("Tile " + tile.Id + " is outside the " + Columns + "x" + Rows + " grid.");
                if (seen.TryGetValue((tile.Column, tile.Row), out var other))
                    problems.Add("Tiles " + other + " and " + tile.Id + " share cell (" + tile.Column + "," + tile.Row + ").");
                seen[(tile.Column, tile.Row)] = tile.Id;

                foreach (var zone in tile.Hides)
                {
                    if (Tiles.All(candidate => candidate.Id != zone))
                        problems.Add("Tile " + tile.Id + " hides " + zone + ", which does not exist.");
                }
            }

            var origin = Tiles.FirstOrDefault(tile => tile.Column == 0 && tile.Row == 0);
            if (origin == null || origin.Id != "always")
                problems.Add("Cell (0,0) must be the tile \"always\": geometry with no second UV set lands there.");
            if (Tiles.GroupBy(tile => tile.Id).Any(group => group.Count() > 1))
                problems.Add("Tile ids must be unique.");

            var defaults = Defaults();
            foreach (var tile in Tiles.Where(candidate => candidate.Toggle != null))
            {
                foreach (var other in tile.Toggle.Needs.Concat(tile.Toggle.Unless))
                {
                    if (defaults.All(known => known.Parameter != other))
                        problems.Add("Tile " + tile.Id + " depends on " + other + ", which no tile switches on.");
                }

                // A parameter rests at one value, so every tile it switches
                // has to agree with that value about how it rests.
                var rests = ShownWhen(tile).All(condition => defaults.Contains(condition));
                if (rests != tile.Shown)
                {
                    problems.Add("Tile " + tile.Id + " is marked " + (tile.Shown ? "shown" : "hidden") +
                                 " at rest, but its parameters rest so that it is " + (rests ? "shown" : "hidden") + ".");
                }
            }

            return problems;
        }
    }
}
