"""Geometry and texture kit for the bot generator: pixel canvases, the atlas, and a mesh builder.

Everything is authored in "pixels": one pixel is PX metres (1/128 m), and one texel of the atlas
covers one square pixel of surface, so a face that is 12 x 8 pixels in the model is a 12 x 8 texel
island in the texture. Faces are unwrapped by flat projection onto their own plane, which keeps the
texels square on the model whatever the shape of the face.

No bpy here except in `Builder.to_mesh`; the canvas and the atlas run under plain Python too.
"""

import contextlib
import math
import struct
import zlib

import numpy as np

PX = 1.0 / 128.0

BAYER4 = np.array([[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]], dtype=np.float64) / 16.0


def vec(*values):
    return np.array(values, dtype=np.float64)


def unit(v):
    v = np.asarray(v, dtype=np.float64)
    length = float(np.linalg.norm(v))
    if length < 1e-12:
        raise ValueError("cannot normalise a zero vector")
    return v / length


# --------------------------------------------------------------------------
# Pixel canvas
# --------------------------------------------------------------------------


class Canvas:
    """A small RGB picture with an emission mask, drawn in whole pixels. (0, 0) is the top left."""

    def __init__(self, w, h, palette):
        self.w, self.h = int(w), int(h)
        self.rgb = np.zeros((self.h, self.w, 3), dtype=np.uint8)
        self.glow = np.zeros((self.h, self.w), dtype=np.uint8)
        self.palette = palette

    def colour(self, c):
        return self.palette[c] if isinstance(c, str) else tuple(c)

    def _clip(self, x0, y0, x1, y1):
        return max(0, int(x0)), max(0, int(y0)), min(self.w, int(x1)), min(self.h, int(y1))

    def rect(self, x0, y0, x1, y1, c, glow=None):
        """Fills the half-open rectangle [x0, x1) x [y0, y1)."""
        x0, y0, x1, y1 = self._clip(x0, y0, x1, y1)
        if x1 <= x0 or y1 <= y0:
            return
        if c is not None:
            self.rgb[y0:y1, x0:x1] = self.colour(c)
        if glow is not None:
            self.glow[y0:y1, x0:x1] = 255 if glow else 0

    def fill(self, c, glow=None):
        self.rect(0, 0, self.w, self.h, c, glow)

    def px(self, x, y, c, glow=None):
        self.rect(x, y, x + 1, y + 1, c, glow)

    def hline(self, y, c, x0=0, x1=None, glow=None):
        self.rect(x0, y, self.w if x1 is None else x1, y + 1, c, glow)

    def vline(self, x, c, y0=0, y1=None, glow=None):
        self.rect(x, y0, x + 1, self.h if y1 is None else y1, c, glow)

    def border(self, c, sides="tblr", inset=0, glow=None):
        i = inset
        if "t" in sides:
            self.rect(i, i, self.w - i, i + 1, c, glow)
        if "b" in sides:
            self.rect(i, self.h - i - 1, self.w - i, self.h - i, c, glow)
        if "l" in sides:
            self.rect(i, i, i + 1, self.h - i, c, glow)
        if "r" in sides:
            self.rect(self.w - i - 1, i, self.w - i, self.h - i, c, glow)

    def frame(self, x0, y0, x1, y1, c, glow=None):
        """A one-pixel outline of the half-open rectangle."""
        self.rect(x0, y0, x1, y0 + 1, c, glow)
        self.rect(x0, y1 - 1, x1, y1, c, glow)
        self.rect(x0, y0, x0 + 1, y1, c, glow)
        self.rect(x1 - 1, y0, x1, y1, c, glow)

    def checker(self, x0, y0, x1, y1, c1, c2, size=2, phase=0):
        x0, y0, x1, y1 = self._clip(x0, y0, x1, y1)
        for y in range(y0, y1):
            for x in range(x0, x1):
                odd = ((x - x0) // size + (y - y0) // size + phase) % 2
                self.rgb[y, x] = self.colour(c2 if odd else c1)

    def dither(self, x0, y0, x1, y1, c, amount, glow=None):
        """Ordered dither: paints `c` on the share `amount` (0..1) of the pixels."""
        x0, y0, x1, y1 = self._clip(x0, y0, x1, y1)
        for y in range(y0, y1):
            for x in range(x0, x1):
                if BAYER4[y % 4, x % 4] < amount:
                    self.rgb[y, x] = self.colour(c)
                    if glow is not None:
                        self.glow[y, x] = 255 if glow else 0

    def fade(self, x0, y0, x1, y1, c, start=0.0, end=1.0, axis="y", glow=None):
        """A dithered ramp of `c`, from `start` at the top (or left) to `end` at the bottom (or right)."""
        x0, y0, x1, y1 = self._clip(x0, y0, x1, y1)
        span = max(1, (y1 - y0 if axis == "y" else x1 - x0) - 1)
        for y in range(y0, y1):
            for x in range(x0, x1):
                t = ((y - y0) if axis == "y" else (x - x0)) / span
                if BAYER4[y % 4, x % 4] < start + (end - start) * t:
                    self.rgb[y, x] = self.colour(c)
                    if glow is not None:
                        self.glow[y, x] = 255 if glow else 0

    def dots(self, x0, y0, x1, y1, c, pitch=2, glow=None):
        """A dot matrix: one pixel every `pitch` in both directions."""
        x0, y0, x1, y1 = self._clip(x0, y0, x1, y1)
        for y in range(y0, y1, pitch):
            for x in range(x0, x1, pitch):
                self.px(x, y, c, glow)

    def disc(self, cx, cy, r, c, glow=None):
        """A filled circle about the point (cx, cy), which may lie between pixels."""
        for y in range(self.h):
            for x in range(self.w):
                if (x + 0.5 - cx) ** 2 + (y + 0.5 - cy) ** 2 <= r * r:
                    self.px(x, y, c, glow)

    def ring(self, cx, cy, r_outer, r_inner, c, glow=None):
        for y in range(self.h):
            for x in range(self.w):
                d = (x + 0.5 - cx) ** 2 + (y + 0.5 - cy) ** 2
                if r_inner * r_inner < d <= r_outer * r_outer:
                    self.px(x, y, c, glow)

    def art(self, x, y, rows, legend, glow=""):
        """Draws rows of characters; `legend` maps a character to a colour, anything else is skipped."""
        for j, row in enumerate(rows):
            for i, ch in enumerate(row):
                if ch in legend:
                    self.px(x + i, y + j, legend[ch], True if ch in glow else None)

    def text(self, x, y, string, c, glow=None):
        """Tiny 3 x 5 capitals and digits. Returns the x after the last glyph."""
        for ch in string:
            glyph = FONT.get(ch)
            if glyph is None:
                x += 2
                continue
            for j, row in enumerate(glyph):
                for i, bit in enumerate(row):
                    if bit == "#":
                        self.px(x + i, y + j, c, glow)
            x += len(glyph[0]) + 1
        return x


FONT = {
    "0": ("###", "# #", "# #", "# #", "###"), "1": (" # ", "## ", " # ", " # ", "###"),
    "2": ("###", "  #", "###", "#  ", "###"), "3": ("###", "  #", "###", "  #", "###"),
    "4": ("# #", "# #", "###", "  #", "  #"), "5": ("###", "#  ", "###", "  #", "###"),
    "6": ("###", "#  ", "###", "# #", "###"), "7": ("###", "  #", "  #", " # ", " # "),
    "8": ("###", "# #", "###", "# #", "###"), "9": ("###", "# #", "###", "  #", "###"),
    "A": ("###", "# #", "###", "# #", "# #"), "B": ("## ", "# #", "## ", "# #", "## "),
    "C": ("###", "#  ", "#  ", "#  ", "###"), "D": ("## ", "# #", "# #", "# #", "## "),
    "E": ("###", "#  ", "## ", "#  ", "###"), "I": ("###", " # ", " # ", " # ", "###"),
    "K": ("# #", "# #", "## ", "# #", "# #"), "N": ("#  #", "## #", "# ##", "#  #", "#  #"),
    "O": ("###", "# #", "# #", "# #", "###"), "R": ("###", "# #", "## ", "# #", "# #"),
    "T": ("###", " # ", " # ", " # ", " # "), "W": ("#   #", "#   #", "# # #", "## ##", "#   #"),
    "-": ("   ", "   ", "###", "   ", "   "), ".": (" ", " ", " ", " ", "#"),
    ":": (" ", "#", " ", "#", " "), "(": (" #", "# ", "# ", "# ", " #"),
}


def write_png(path, pixels):
    """Writes an (h, w, 3) uint8 array as an 8-bit RGB PNG. Deterministic: no metadata, fixed compression."""
    pixels = np.ascontiguousarray(pixels, dtype=np.uint8)
    h, w = pixels.shape[:2]
    raw = b"".join(b"\x00" + pixels[y].tobytes() for y in range(h))

    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    data = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
    data += chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")
    with open(path, "wb") as handle:
        handle.write(data)


# --------------------------------------------------------------------------
# Atlas
# --------------------------------------------------------------------------


class Island:
    """A rectangle of whole texels. `pad` texels of its own edge colour are kept all round it."""

    def __init__(self, key, w, h, paint, pad):
        self.key, self.w, self.h, self.paint, self.pad = key, int(w), int(h), paint, int(pad)
        self.x = self.y = None

    def uv(self, x, y, size):
        """Island pixel coordinates (y down) -> UV (origin bottom-left)."""
        return ((self.x + x) / size, 1.0 - (self.y + y) / size)


class Atlas:
    def __init__(self, size, palette, background="ink"):
        self.size = int(size)
        self.palette = palette
        self.background = background
        self.islands = {}

    def island(self, key, w, h, paint, pad=1):
        """The island of that key and size, made on first use. The key is completed with the size, so
        two faces share texels exactly when they ask for the same key at the same size."""
        full = f"{key}:{int(w)}x{int(h)}"
        found = self.islands.get(full)
        if found is None:
            found = self.islands[full] = Island(full, w, h, paint, pad)
        return found

    def pack(self):
        """Shelf packing, tallest first. Deterministic: ties are broken by the key."""
        order = sorted(self.islands.values(), key=lambda i: (-(i.h + 2 * i.pad), -(i.w + 2 * i.pad), i.key))
        shelves = []  # [y, height, x cursor]
        bottom = 0
        for island in order:
            w, h = island.w + 2 * island.pad, island.h + 2 * island.pad
            if w > self.size:
                raise RuntimeError(f"atlas: island {island.key} is wider than the atlas")
            for shelf in shelves:
                if shelf[2] + w <= self.size and h <= shelf[1]:
                    island.x, island.y = shelf[2] + island.pad, shelf[0] + island.pad
                    shelf[2] += w
                    break
            else:
                if bottom + h > self.size:
                    used = sum((i.w + 2 * i.pad) * (i.h + 2 * i.pad) for i in order)
                    raise RuntimeError(f"atlas: {len(order)} islands ({used} texels with padding) do not fit {self.size} x {self.size}")
                shelves.append([bottom, h, w])
                island.x, island.y = island.pad, bottom + island.pad
                bottom += h
        self.used_rows = bottom
        return bottom

    def render(self):
        """Paints every island. Returns (rgb, glow) as uint8 arrays of the atlas size."""
        rgb = np.empty((self.size, self.size, 3), dtype=np.uint8)
        rgb[:, :] = self.palette[self.background]
        glow = np.zeros((self.size, self.size), dtype=np.uint8)
        for island in sorted(self.islands.values(), key=lambda i: i.key):
            canvas = Canvas(island.w, island.h, self.palette)
            island.paint(canvas)
            p = island.pad
            # The padding repeats the island's own edge texels, so a sample that lands a hair
            # outside the island (or a coarser mip level) finds the colour it would have found inside.
            colour = np.pad(canvas.rgb, ((p, p), (p, p), (0, 0)), mode="edge")
            light = np.pad(canvas.glow, ((p, p), (p, p)), mode="edge")
            rgb[island.y - p:island.y + island.h + p, island.x - p:island.x + island.w + p] = colour
            glow[island.y - p:island.y + island.h + p, island.x - p:island.x + island.w + p] = light
        return rgb, glow


# --------------------------------------------------------------------------
# Ring helpers (2D outlines, counter-clockwise)
# --------------------------------------------------------------------------


def rrect(hx, hy, chamfer=0.0, cx=0.0, cy=0.0):
    """A rectangle of half-sizes (hx, hy), corners cut by `chamfer`. Starts at the lower left, side 0 is the low-y edge."""
    c = chamfer
    if c <= 0.0:
        points = [(-hx, -hy), (hx, -hy), (hx, hy), (-hx, hy)]
    else:
        points = [(-hx + c, -hy), (hx - c, -hy), (hx, -hy + c), (hx, hy - c), (hx - c, hy), (-hx + c, hy), (-hx, hy - c), (-hx, -hy + c)]
    return [(cx + a, cy + b) for a, b in points]


def ngon(n, ra, rb=None):
    """A regular n-gon whose side 0 faces the low-y direction."""
    rb = ra if rb is None else rb
    phase = -math.pi / 2.0 - math.pi / n
    return [(ra * math.cos(phase + 2.0 * math.pi * i / n), rb * math.sin(phase + 2.0 * math.pi * i / n)) for i in range(n)]


def frame(axis, front):
    """The 2D basis (ea, eb) for rings about `axis` whose low-y side faces `front`. ea x eb = axis."""
    axis = unit(axis)
    front = np.asarray(front, dtype=np.float64)
    eb = unit(-(front - axis * float(front @ axis)))
    ea = np.cross(eb, axis)
    return ea, eb


def place(outline, origin, ea, eb):
    origin = np.asarray(origin, dtype=np.float64)
    return [origin + a * ea + b * eb for a, b in outline]


# --------------------------------------------------------------------------
# Mesh builder
# --------------------------------------------------------------------------


class Solid:
    def __init__(self, name, weights, closed, material, tag, sprite):
        self.name, self.weights, self.closed, self.material, self.tag, self.sprite = name, weights, closed, material, tag, sprite
        self.faces = []  # (points [n x 3], island, uv [n x 2] island pixels, weights per point)
        self.count = 0


def _newell(points):
    n = np.zeros(3)
    for i in range(len(points)):
        a, b = points[i], points[(i + 1) % len(points)]
        n += np.array([(a[1] - b[1]) * (a[2] + b[2]), (a[2] - b[2]) * (a[0] + b[0]), (a[0] - b[0]) * (a[1] + b[1])])
    return n


def swatch(colour, glow=False):
    """A paint that is one flat colour; faces painted with it collapse onto a single texel."""
    def paint(canvas):
        canvas.fill(colour, glow)
    paint.swatch = f"{colour}{'+glow' if glow else ''}"
    return paint


class Builder:
    """Collects faces in pixel units, grouped into solids, and turns them into one Blender mesh."""

    def __init__(self, atlas):
        self.atlas = atlas
        self.solids = []
        self._solid = None
        self._mirror = False

    # -- grouping ----------------------------------------------------------

    @contextlib.contextmanager
    def solid(self, name, bone=None, weights=None, closed=True, material=0, tag=None, sprite=False):
        """Everything emitted inside is one welded piece. `bone` is the bone it follows rigidly;
        `weights` is instead a function of a point returning {bone: weight}. A closed solid is
        checked to be a watertight, outward-facing surface."""
        if self._solid is not None:
            raise RuntimeError("solids do not nest")
        if weights is None:
            weights = (lambda point, bone=bone: {bone: 1.0})
        self._solid = Solid(name, weights, closed, material, tag, sprite)
        yield self._solid
        solid, self._solid = self._solid, None
        if solid.closed:
            self._check_closed(solid)
        self.solids.append(solid)

    @contextlib.contextmanager
    def mirrored(self):
        """Everything emitted inside lands on the other side (x negated), on the .R bones, sharing
        the texels of the side it mirrors."""
        self._mirror = True
        yield
        self._mirror = False

    def _side(self, name):
        return name.replace(".L", ".R") if self._mirror else name

    # -- faces ---------------------------------------------------------------

    def _emit(self, points, island, uvs):
        solid = self._solid
        points = [np.asarray(p, dtype=np.float64) for p in points]
        weights = [{self._side(bone): w for bone, w in solid.weights(p).items()} for p in points]
        if self._mirror:
            points = [p * np.array([-1.0, 1.0, 1.0]) for p in points][::-1]
            uvs, weights = list(uvs)[::-1], weights[::-1]
        solid.faces.append((points, island, [tuple(uv) for uv in uvs], weights))

    def _auto_key(self, key):
        solid = self._solid
        solid.count += 1
        return key if key is not None else f"{solid.name}#{solid.count}"

    def planar(self, polygons, up, paint, key=None, pad=1):
        """Convex flat polygons that share one plane and one island, unwrapped by projection.

        Points go counter-clockwise seen from outside. `up` is the direction that is up in the
        picture. A polygon of more than four corners is cut into quads."""
        polygons = [[np.asarray(p, dtype=np.float64) for p in polygon] for polygon in polygons]
        key = self._auto_key(key)
        normal = unit(sum((_newell(polygon) for polygon in polygons), np.zeros(3)))
        up = np.asarray(up, dtype=np.float64)
        v = unit(up - normal * float(up @ normal))
        u = np.cross(v, normal)
        flat = [[(float(p @ u), float(p @ v)) for p in polygon] for polygon in polygons]
        us = [c[0] for polygon in flat for c in polygon]
        vs = [c[1] for polygon in flat for c in polygon]
        w = max(1, math.ceil(max(us) - min(us) - 1e-6))
        h = max(1, math.ceil(max(vs) - min(vs) - 1e-6))
        if getattr(paint, "swatch", None):
            island = self.atlas.island(f"swatch/{paint.swatch}", 1, 1, paint, pad=1)
            flat = [[(0.5, 0.5)] * len(polygon) for polygon in polygons]
        else:
            island = self.atlas.island(key, w, h, paint, pad)
            ox = min(us) - (w - (max(us) - min(us))) / 2.0
            oy = max(vs) + (h - (max(vs) - min(vs))) / 2.0
            flat = [[(cu - ox, oy - cv) for cu, cv in polygon] for polygon in flat]
        for polygon, uvs in zip(polygons, flat):
            for part in self._convex_parts(polygon, normal):
                self._emit([polygon[i] for i in part], island, [uvs[i] for i in part])
        return island

    def poly(self, points, up, paint, key=None, pad=1):
        return self.planar([points], up, paint, key, pad)

    def face_uv(self, points, uvs, island):
        """A triangle or flat quad with its island pixel coordinates given outright."""
        points = [np.asarray(p, dtype=np.float64) for p in points]
        normal = _newell(points)
        if len(points) == 4 and float(np.linalg.norm(normal)) > 1e-12:
            for part in self._convex_parts(points, unit(normal)):
                self._emit([points[i] for i in part], island, [uvs[i] for i in part])
        else:
            self._emit(points, island, uvs)

    @staticmethod
    def _convex_parts(polygon, normal):
        """Index lists that cut a polygon into triangles and flat convex quads."""
        n = len(polygon)
        if n == 3:
            return [[0, 1, 2]]
        if n == 4:
            offset = abs(float((polygon[3] - polygon[0]) @ unit(np.cross(polygon[1] - polygon[0], polygon[2] - polygon[0]))))
            convex = all(float(np.cross(polygon[(i + 1) % 4] - polygon[i], polygon[(i + 2) % 4] - polygon[(i + 1) % 4]) @ normal) > 1e-9
                         for i in range(4))
            if offset < 1e-4 and convex:
                return [[0, 1, 2, 3]]
            return [[0, 1, 2], [0, 2, 3]]
        parts, a, b = [], 0, n - 1
        while b - a >= 3:
            parts.append([a, a + 1, b - 1, b])
            a, b = a + 1, b - 1
        if b - a == 2:
            parts.append([a, a + 1, b])
        return parts

    # -- primitives -------------------------------------------------------------

    def loft(self, rings, wall, cap0=None, cap1=None, up0=None, up1=None, key=None, up=None):
        """Walls between consecutive rings of equal length, and flat caps on the ends.

        `rings` are lists of points going counter-clockwise about the direction from the first
        ring to the last. `wall` is a paint, or a function marked with `per_side` that takes
        (band, side) and returns a paint or (paint, key); two walls that return the same key at
        the same size share their texels. A wall's picture has the direction of the loft as its
        up, unless `up(band, side)` returns another. A cap left as None is not made."""
        rings = [[np.asarray(p, dtype=np.float64) for p in ring] for ring in rings]
        n = len(rings[0])
        base = self._auto_key(key)
        for k in range(len(rings) - 1):
            a, b = rings[k], rings[k + 1]
            for i in range(n):
                j = (i + 1) % n
                chosen = wall(k, i) if getattr(wall, "per_side", False) else wall
                paint, suffix = chosen if isinstance(chosen, tuple) else (chosen, f"w{k}.{i}")
                quad = []
                for p in (a[i], a[j], b[j], b[i]):
                    if not any(self._key(p) == self._key(q) for q in quad):
                        quad.append(p)
                if len(quad) < 3 or float(np.linalg.norm(_newell(quad))) < 1e-9:
                    continue
                rise = (b[i] + b[j]) / 2.0 - (a[i] + a[j]) / 2.0
                chosen_up = up(k, i) if up is not None else None
                self.planar([quad], rise if chosen_up is None else chosen_up, paint, f"{base}/{suffix}")
        axis = unit(np.mean(rings[-1], axis=0) - np.mean(rings[0], axis=0))
        fallback = unit(np.cross(axis, [1.0, 0.0, 0.0]) if abs(axis[0]) < 0.9 else np.cross(axis, [0.0, 0.0, 1.0]))
        if cap0 is not None:
            self.planar([rings[0][::-1]], fallback if up0 is None else up0, cap0, f"{base}/cap0")
        if cap1 is not None:
            self.planar([rings[-1]], fallback if up1 is None else up1, cap1, f"{base}/cap1")

    def ball(self, centre, radius, paint, key, segments=6, rings=4, axis=(0.0, 0.0, 1.0), front=(0.0, -1.0, 0.0), cell=(3, 3),
             project=None):
        """A low-polygon sphere. Unwrapped by longitude and latitude onto one island of
        segments x rings cells, or, with `project` = (u axis, v axis, size), flat along a
        direction onto a square island of that size, both halves landing on the same texels."""
        centre = np.asarray(centre, dtype=np.float64)
        axis = unit(axis)
        ea, eb = frame(axis, front)
        cw, ch = cell
        if project is None:
            island = self.atlas.island(key, segments * cw, rings * ch, paint)
        else:
            island = self.atlas.island(key, project[2], project[2], paint)
        outline = ngon(segments, 1.0)

        def point(row, i):
            polar = math.pi * row / rings
            a, b = outline[i % segments]
            return centre + radius * (math.cos(polar) * axis + math.sin(polar) * (a * ea + b * eb))

        def flat(p):
            u_axis, v_axis, size = project
            return (size / 2.0 + float((p - centre) @ np.asarray(u_axis)), size / 2.0 - float((p - centre) @ np.asarray(v_axis)))

        for row in range(rings):
            for i in range(segments):
                # Seen from outside with the axis up, a larger longitude index lies to the right.
                top_l, top_r = point(row, i), point(row, i + 1)
                bottom_l, bottom_r = point(row + 1, i), point(row + 1, i + 1)
                x0, x1, y0, y1 = i * cw, (i + 1) * cw, row * ch, (row + 1) * ch
                if row == 0:
                    points, uvs = [top_l, bottom_l, bottom_r], [((x0 + x1) / 2.0, y0), (x0, y1), (x1, y1)]
                elif row == rings - 1:
                    points, uvs = [top_l, bottom_l, top_r], [(x0, y0), ((x0 + x1) / 2.0, y1), (x1, y0)]
                else:
                    points, uvs = [top_l, bottom_l, bottom_r, top_r], [(x0, y0), (x0, y1), (x1, y1), (x1, y0)]
                if project is not None:
                    uvs = [flat(p) for p in points]
                self._emit(points, island, uvs)
        return island

    # -- checks -------------------------------------------------------------------

    @staticmethod
    def _key(point):
        return tuple(int(round(float(c) * 2000.0)) for c in point)

    def _check_closed(self, solid):
        edges = {}
        volume = 0.0
        for points, _island, _uvs, _weights in solid.faces:
            keys = [self._key(p) for p in points]
            for i in range(len(keys)):
                edge = (keys[i], keys[(i + 1) % len(keys)])
                edges[edge] = edges.get(edge, 0) + 1
            for i in range(1, len(points) - 1):
                volume += float(points[0] @ np.cross(points[i], points[i + 1])) / 6.0
        bad = sum(1 for (a, b), count in edges.items() if count != 1 or edges.get((b, a), 0) != 1)
        if bad:
            raise RuntimeError(f"solid {solid.name}: {bad} edge(s) are open or wound inconsistently; the surface is not closed")
        if volume <= 0.0:
            raise RuntimeError(f"solid {solid.name}: faces point inward (signed volume {volume:.3f})")

    # -- output -----------------------------------------------------------------------

    def triangle_count(self):
        return sum(len(face[0]) - 2 for solid in self.solids for face in solid.faces)

    def collect(self, chosen=lambda solid: True):
        """Welds each chosen solid's vertices and returns plain lists for mesh creation.

        Returns a dict with `vertices` (pixels), `faces` (index tuples), `loops` (island, u, v per
        face corner), `materials` (per face), `solids` (per face, the name of its solid), `weights`
        (per vertex), `sprite` (per vertex, bool) and `tags` (tag -> vertex indices)."""
        vertices, faces, loops, materials, weights, sprite, tags, solids = [], [], [], [], [], [], {}, []
        for solid in self.solids:
            if not chosen(solid):
                continue
            index = {}
            for points, island, uvs, point_weights in solid.faces:
                # Every corner lies on its island's own texels; the padding is never mapped.
                if any(not (-1e-6 <= u <= island.w + 1e-6 and -1e-6 <= v <= island.h + 1e-6) for u, v in uvs):
                    raise RuntimeError(f"solid {solid.name}: a face leaves its island {island.key}")
                face = []
                for p, w in zip(points, point_weights):
                    k = self._key(p)
                    if k not in index:
                        index[k] = len(vertices)
                        vertices.append(tuple(float(c) for c in p))
                        weights.append(w)
                        sprite.append(solid.sprite)
                        if solid.tag is not None:
                            tags.setdefault(solid.tag, []).append(index[k])
                    face.append(index[k])
                faces.append(tuple(face))
                loops.append([(island, uv[0], uv[1]) for uv in uvs])
                materials.append(solid.material)
                solids.append(solid.name)
        return {"vertices": vertices, "faces": faces, "loops": loops, "materials": materials, "solids": solids,
                "weights": weights, "sprite": sprite, "tags": tags}
