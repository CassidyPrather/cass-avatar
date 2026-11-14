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

    public sealed class TileToggle
    {
        public string Parameter;
        public string Label;
        public string Icon;
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

            return problems;
        }
    }
}
