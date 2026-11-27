using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEngine;
using Wirenook.AdventureTools.Editor;
using Wirenook.Assets.Editor;

namespace Wirenook.Meta.Crypt.Editor
{
    /// <summary>
    /// The crypt's pieces in the meta figure's look: flat colour with pixels
    /// standing out of it, every pixel a hard square 1/128 m across, as on
    /// the figure itself (blender/meta, <c>PX</c>).
    ///
    /// The pieces are flat-coloured shapes that take their colour from one
    /// point of the wirenook palette each, so there is no room on their own
    /// UV set for a drawing. The detail is laid over instead, by the two
    /// extra layers lilToon has: each is a small tile of see-through
    /// pixels, darker and lighter than whatever is under them, repeated
    /// over every face at the figure's pixel size, and each is masked to
    /// the swatches it suits. One tile is wood grain, which runs along the
    /// longest edge of each face, so along a plank and up a post. The
    /// other is grit, for stone, metal and paper. Things that glow get
    /// neither.
    ///
    /// Where on the tiles a point of a face falls is a UV set of its own
    /// (the fourth), worked out here from the mesh once it is built.
    ///
    /// It costs two 64 by 64 textures and two masks, and no material slot,
    /// mesh or triangle.
    /// </summary>
    public static class CryptDetail
    {
        /// <summary>Pixels to a metre: the figure's.</summary>
        public const float PixelsPerMetre = 128f;

        /// <summary>Pixels along a side of a tile.</summary>
        public const int Tile = 64;

        /// <summary>
        /// The UV set that says where on the tiles a point is: the fourth.
        /// The toon shader reads a sign's number out of the same set, and
        /// knows a sign by that number being negative (Shaders/Toon), so
        /// nothing here may go below zero; <see cref="Unwrap"/> measures
        /// every face from its own least corner, which keeps it so.
        /// </summary>
        public const int UvChannel = 3;

        private const string Folder = CryptBuild.Package + "/Generated/Crypt";
        public const string WoodTile = Folder + "/crypt-detail-wood.png";
        public const string WoodMask = Folder + "/crypt-detail-wood-mask.png";
        public const string GritTile = Folder + "/crypt-detail-grit.png";
        public const string GritMask = Folder + "/crypt-detail-grit-mask.png";

        /// <summary>The swatches that are wood, and how strongly the grain shows on each.</summary>
        private static readonly (string swatch, float amount)[] Wood = { ("wood", 1f), ("wood-dark", 1f) };

        /// <summary>The swatches that are stone, metal or paper, and how strongly the grit shows on each.</summary>
        private static readonly (string swatch, float amount)[] Grit =
        {
            ("grey-dark", 0.55f), ("grey-mid", 0.9f), ("grey-light", 0.8f), ("silver", 0.9f), ("brass", 0.85f), ("soot", 0.4f),
            ("night-1", 0.5f), ("night-3", 0.8f), ("violet", 0.8f), ("lilac-1", 0.7f), ("lilac-3", 0.8f), ("lilac-4", 0.6f),
            ("paper", 0.7f), ("cream", 0.7f), ("banana", 0.6f),
        };

        /// <summary>
        /// Gives a mesh made of <see cref="ShapeMesh"/>
        /// faces its place on the tiles. Every face is laid flat with its
        /// longest edge along the tile's rows and its corner on a pixel, so
        /// no face shows half a pixel along that edge.
        /// </summary>
        public static void Unwrap(Mesh mesh)
        {
            var positions = mesh.vertices;
            var placed = new Vector2[positions.Length];
            var triangles = mesh.triangles;
            // A face is a fan: its triangles follow one another and all begin at its first corner.
            var start = 0;
            while (start < triangles.Length)
            {
                var first = triangles[start];
                var last = first;
                var end = start;
                while (end < triangles.Length && triangles[end] == first)
                {
                    last = Mathf.Max(last, Mathf.Max(triangles[end + 1], triangles[end + 2]));
                    end += 3;
                }

                var count = last - first + 1;
                var normal = Vector3.Cross(positions[triangles[start + 1]] - positions[first], positions[triangles[start + 2]] - positions[first]).normalized;
                var along = Vector3.zero;
                for (var corner = 0; corner < count; corner++)
                {
                    var edge = positions[first + (corner + 1) % count] - positions[first + corner];
                    if (edge.sqrMagnitude > along.sqrMagnitude + 1e-9f) along = edge;
                }

                if (normal.sqrMagnitude < 0.5f || along.sqrMagnitude < 1e-12f)
                {
                    start = end;
                    continue;
                }

                along.Normalize();
                // A plank's grain should not turn end for end between its front and its back.
                var greatest = Mathf.Abs(along.x) >= Mathf.Abs(along.y) && Mathf.Abs(along.x) >= Mathf.Abs(along.z) ? along.x
                    : Mathf.Abs(along.y) >= Mathf.Abs(along.z) ? along.y : along.z;
                if (greatest < 0f) along = -along;
                var across = Vector3.Cross(normal, along).normalized;
                var least = new Vector2(float.MaxValue, float.MaxValue);
                for (var corner = 0; corner < count; corner++)
                {
                    var at = positions[first + corner];
                    least = Vector2.Min(least, new Vector2(Vector3.Dot(at, along), Vector3.Dot(at, across)));
                }

                for (var corner = 0; corner < count; corner++)
                {
                    var at = positions[first + corner];
                    placed[first + corner] = (new Vector2(Vector3.Dot(at, along), Vector3.Dot(at, across)) - least) * (PixelsPerMetre / Tile);
                }

                start = end;
            }

            mesh.SetUVs(UvChannel, placed);
            EditorUtility.SetDirty(mesh);
        }

        /// <summary>Writes the tiles and masks, and tells a toon material to lay them over itself.</summary>
        public static void Paint(Material material)
        {
            var wood = Texture(WoodTile, Tile, Tile, WoodPixels(), repeats: true, colour: true);
            var grit = Texture(GritTile, Tile, Tile, GritPixels(), repeats: true, colour: true);
            var palette = AssetDatabase.LoadAssetAtPath<Texture2D>(WirenookMaterials.PalettePath);
            if (palette == null) throw new FileNotFoundException("Missing " + WirenookMaterials.PalettePath + ".", WirenookMaterials.PalettePath);
            var woodMask = Texture(WoodMask, palette.width, palette.height, MaskPixels(palette, Wood), repeats: false, colour: false);
            var gritMask = Texture(GritMask, palette.width, palette.height, MaskPixels(palette, Grit), repeats: false, colour: false);

            void Layer(string name, Texture2D tile, Texture2D mask)
            {
                material.SetFloat("_Use" + name + "Tex", 1f);
                material.SetColor(name == "Main2nd" ? "_Color2nd" : "_Color3rd", Color.white);
                material.SetTexture("_" + name + "Tex", tile);
                material.SetTextureScale("_" + name + "Tex", Vector2.one);
                material.SetTextureOffset("_" + name + "Tex", Vector2.zero);
                material.SetFloat("_" + name + "Tex_UVMode", UvChannel);
                material.SetTexture("_" + name + "BlendMask", mask);
                // Laid over: a tile's pixels are black or white and mostly clear.
                material.SetFloat("_" + name + "TexBlendMode", 0f);
                material.SetFloat("_" + name + "TexAlphaMode", 0f);
                material.SetFloat("_" + name + "EnableLighting", 1f);
            }

            Layer("Main2nd", wood, woodMask);
            Layer("Main3rd", grit, gritMask);
            EditorUtility.SetDirty(material);
        }

        /// <summary>
        /// A rune in the figure's hand: a glyph three pixels wide and five
        /// tall, each pixel a small stud standing out of a face that looks
        /// along +Z, in whatever colour the mesh is on.
        /// </summary>
        /// <param name="rows">From the top, '#' for a pixel.</param>
        /// <param name="centre">The middle of the glyph, on the face.</param>
        /// <param name="pixel">Metres across one pixel.</param>
        public static void Rune(ShapeMesh mesh, string[] rows, Vector3 centre, float pixel)
        {
            for (var row = 0; row < rows.Length; row++)
            {
                for (var column = 0; column < rows[row].Length; column++)
                {
                    if (rows[row][column] != '#') continue;
                    var at = centre + new Vector3((column - (rows[row].Length - 1) * 0.5f) * pixel, ((rows.Length - 1) * 0.5f - row) * pixel, 0.003f);
                    mesh.Box(at, new Vector3(pixel, pixel, 0.006f));
                }
            }
        }

        /// <summary>Two of the runes the figure wears (blender/meta/meta_model.py, RUNES).</summary>
        public static readonly string[][] Runes =
        {
            new[] { ".#.", "###", "#.#", "###", ".#." },
            new[] { "#.#", ".#.", "###", ".#.", ".#." },
        };

        private static int Hash(int x, int y, int salt)
        {
            unchecked
            {
                var n = (uint)(x * 73856093) ^ (uint)(y * 19349663) ^ (uint)((salt + 1) * 83492791);
                n ^= n >> 13;
                n *= 0x5bd1e995;
                n ^= n >> 15;
                return (int)(n & 0x7fffffff);
            }
        }

        private static readonly Color32 Clear = new Color32(0, 0, 0, 0);
        private static Color32 Dark(float amount) => new Color32(18, 8, 30, (byte)Mathf.RoundToInt(255f * amount));
        private static Color32 Light(float amount) => new Color32(255, 250, 240, (byte)Mathf.RoundToInt(255f * amount));

        /// <summary>Grain: runs of darker and lighter pixels along the rows, a knot, and the odd fleck.</summary>
        private static Color32[] WoodPixels()
        {
            var pixels = Enumerable.Repeat(Clear, Tile * Tile).ToArray();
            void Put(int x, int y, Color32 colour) => pixels[(y % Tile + Tile) % Tile * Tile + (x % Tile + Tile) % Tile] = colour;

            for (var y = 0; y < Tile; y++)
            {
                // Most rows carry a run or two; which, and how long, is the row's own.
                var kind = Hash(0, y, 11) % 7;
                if (kind >= 4) continue;
                var x = Hash(1, y, 11) % Tile;
                var runs = 1 + Hash(2, y, 11) % 3;
                for (var run = 0; run < runs; run++)
                {
                    var length = 5 + Hash(3 + run, y, 11) % 17;
                    var colour = kind == 0 ? Light(0.2f) : Dark(kind == 1 ? 0.3f : 0.18f);
                    for (var step = 0; step < length; step++) Put(x + step, y, colour);
                    x += length + 4 + Hash(7 + run, y, 11) % 15;
                }
            }

            // Two knots: a dark eye with a ring the grain goes round.
            foreach (var (cx, cy) in new[] { (17, 21), (46, 50) })
            {
                Put(cx, cy, Dark(0.5f));
                Put(cx + 1, cy, Dark(0.5f));
                for (var step = -2; step <= 3; step++)
                {
                    Put(cx + step, cy - 2, Dark(0.26f));
                    Put(cx + step, cy + 2, Dark(0.26f));
                    Put(cx + step, cy - 1, Clear);
                    Put(cx + step, cy + 1, Clear);
                }

                Put(cx - 3, cy - 1, Dark(0.26f));
                Put(cx - 3, cy, Dark(0.26f));
                Put(cx - 3, cy + 1, Dark(0.26f));
                Put(cx + 4, cy - 1, Dark(0.26f));
                Put(cx + 4, cy, Dark(0.26f));
                Put(cx + 4, cy + 1, Dark(0.26f));
                Put(cx - 1, cy, Clear);
                Put(cx + 2, cy, Clear);
            }

            return pixels;
        }

        /// <summary>Grit: the figure's cloth, more or less, a fleck of light or dark in every twenty pixels, and a few pits.</summary>
        private static Color32[] GritPixels()
        {
            var pixels = Enumerable.Repeat(Clear, Tile * Tile).ToArray();
            for (var y = 0; y < Tile; y++)
            {
                for (var x = 0; x < Tile; x++)
                {
                    var n = Hash(x, y, 3) % 41;
                    if (n == 0) pixels[y * Tile + x] = Light(0.26f);
                    else if (n == 1 || n == 2) pixels[y * Tile + x] = Dark(0.3f);
                }
            }

            // Pits and scratches: a few short dark strokes with a light pixel under one end.
            for (var pit = 0; pit < 9; pit++)
            {
                var x = Hash(pit, 0, 5) % (Tile - 4);
                var y = 1 + Hash(pit, 1, 5) % (Tile - 2);
                var length = 2 + Hash(pit, 2, 5) % 3;
                for (var step = 0; step < length; step++) pixels[y * Tile + x + step] = Dark(0.38f);
                pixels[(y - 1) * Tile + x + length - 1] = Light(0.22f);
            }

            return pixels;
        }

        /// <summary>A picture the shape of the palette: each swatch's square as bright as the detail is strong on it, black elsewhere.</summary>
        private static Color32[] MaskPixels(Texture2D palette, (string swatch, float amount)[] shown)
        {
            // The palette's squares are sixteen pixels across (wirenook-palette.json, "cell").
            const int cell = 16;
            var pixels = Enumerable.Repeat(new Color32(0, 0, 0, 255), palette.width * palette.height).ToArray();
            foreach (var (swatch, amount) in shown)
            {
                var uv = WirenookPalette.Uv(swatch);
                var left = Mathf.FloorToInt(uv.x * palette.width / cell) * cell;
                var bottom = Mathf.FloorToInt(uv.y * palette.height / cell) * cell;
                var value = (byte)Mathf.RoundToInt(255f * amount);
                for (var y = bottom; y < bottom + cell; y++)
                    for (var x = left; x < left + cell; x++)
                        pixels[y * palette.width + x] = new Color32(value, value, value, 255);
            }

            return pixels;
        }

        /// <summary>Writes a picture if it is not already the one on disk, and imports it as pixel art.</summary>
        private static Texture2D Texture(string path, int width, int height, Color32[] pixels, bool repeats, bool colour)
        {
            var picture = new Texture2D(width, height, TextureFormat.RGBA32, false);
            picture.SetPixels32(pixels);
            picture.Apply();
            var bytes = picture.EncodeToPNG();
            UnityEngine.Object.DestroyImmediate(picture);
            if (!File.Exists(path) || !File.ReadAllBytes(path).SequenceEqual(bytes))
            {
                File.WriteAllBytes(path, bytes);
                AssetDatabase.ImportAsset(path, ImportAssetOptions.ForceSynchronousImport);
            }

            var importer = (TextureImporter)AssetImporter.GetAtPath(path);
            var wrap = repeats ? TextureWrapMode.Repeat : TextureWrapMode.Clamp;
            if (importer.filterMode != FilterMode.Point || importer.mipmapEnabled || importer.wrapMode != wrap || importer.sRGBTexture != colour ||
                importer.textureCompression != TextureImporterCompression.Uncompressed || importer.npotScale != TextureImporterNPOTScale.None ||
                importer.alphaIsTransparency)
            {
                // Pixel art: every texel a hard square at any distance, and no neighbour bled into it.
                importer.filterMode = FilterMode.Point;
                importer.mipmapEnabled = false;
                importer.wrapMode = wrap;
                importer.sRGBTexture = colour;
                importer.textureCompression = TextureImporterCompression.Uncompressed;
                importer.npotScale = TextureImporterNPOTScale.None;
                importer.alphaIsTransparency = false;
                importer.SaveAndReimport();
            }

            var texture = AssetDatabase.LoadAssetAtPath<Texture2D>(path);
            if (texture == null) throw new FileNotFoundException("Could not import " + path + ".", path);
            return texture;
        }
    }
}
