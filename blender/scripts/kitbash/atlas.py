"""Bakes the avatar's one texture: the painted face beside the flat swatches.

Layout of Textures/cass-atlas.png (UV space, origin bottom-left):

    v 0.58 .. 1.00   the top strip of the HENGE face texture, where it always was,
                     so the face keeps its UVs. Eyes, lashes and brows are recoloured.
    v 0.40 .. 0.55   the heart and star pupils, drawn here over copies of the iris, at
                     the eye overlays' own UVs moved down by OVERLAY_SHIFT.
    u, v < 0.25      the palette (Textures/cass-palette.png) at four times its size;
                     a swatch's UV here is its palette UV divided by PALETTE_SHRINK.

    u < 0.50, v 0.256 .. 0.397     a patch of blue gingham for the skirt (GINGHAM_RECT). Faces are
                                  laid on it one at a time by `gingham_uv`: the pattern repeats,
                                  so a face may be moved a whole number of checks to fit, and the
                                  patch only has to be as big as the biggest face.

The rest is filled with the skin colour and is free for painted detail later.

    u 0.50 .. 1.00, v 0 .. 0.50   skin colour; the full-level body keeps its own UVs here,
    u 0.25 .. 0.50, v 0 .. 0.25   and the lite-level body here (BODY_REGIONS). Flat in
                                  colour, but the normal atlas has the body's normal map.

A second texture, cass-atlas-normal.png, has the same layout: the face's
normal map in the face strip, each body level's normal map in its region,
and a flat normal everywhere else. The face
mesh is coarse around the mouth and nose, and its author shades it through
this map; without it, toon shadow falls in creases there.
The `skin` swatch is not taken from the palette: it is the face texture's
own skin tone, so the flat-coloured body and the painted head match.
"""

import json

import bpy
import numpy as np

SIZE = 2048
FACE_STRIP_V = 0.58
OVERLAY_SHIFT = 0.45
HEART_COLOUR, HEART_RIM = (1.0, 0.31, 0.55), (1.0, 0.86, 0.92)
STAR_COLOUR, STAR_RIM = (1.0, 0.85, 0.29), (1.0, 0.97, 0.75)
PALETTE_SHRINK = 4.0
# Where each body level's own UV square sits in the atlas: (u, v) of its corner, and its size.
BODY_REGIONS = {"full": (0.5, 0.0, 0.5), "lite": (0.25, 0.0, 0.25)}
# The face's author uses its normal map at half strength and the body's at full; the
# material has one strength, so the face's map is flattened by this much as it is baked.
FACE_NORMAL_STRENGTH = 0.5

# The skirt's gingham. The patch, in pixels (x0, y0, x1, y1; rows count up from the bottom);
# the size of one repeat (a blue stripe and a white one); how many pixels a metre of cloth
# covers; the room left round the part of the patch that faces use, so that filtering and
# mip-mapping find more of the same pattern beyond a face's edge; and the colours of a check
# that no stripe, one stripe and two stripes cross.
GINGHAM_RECT = (8, 524, 1016, 812)
GINGHAM_PERIOD = 32
GINGHAM_SCALE = 1600.0
GINGHAM_MARGIN = 16
GINGHAM_COLOURS = ((0.955, 0.968, 1.0), (0.640, 0.765, 0.940), (0.365, 0.553, 0.812))

# What the source's pink eyes and red-brown lashes become.
EYE_HUE_SHIFT = -135.0 / 360.0
EYE_SATURATION = 0.92
EYE_VALUE = 1.06
EYE_PADDING = 0.004                            # around each iris's UV rect
BROW_RECT = (0.420, 0.945, 0.640, 0.985)
LASH_RECTS = ((0.645, 0.910, 1.000, 0.985), (0.545, 0.905, 0.640, 0.940))
BROW_COLOUR = (0.62, 0.44, 0.20)
LASH_COLOUR = (0.30, 0.18, 0.10)


def _load(path):
    image = bpy.data.images.load(str(path), check_existing=False)
    width, height = image.size
    pixels = np.empty(width * height * 4, dtype=np.float32)
    image.pixels.foreach_get(pixels)
    bpy.data.images.remove(image)
    return pixels.reshape(height, width, 4).astype(np.float64)


def _rgb_to_hsv(rgb):
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    high, low = rgb.max(axis=-1), rgb.min(axis=-1)
    span = high - low
    safe = np.where(span == 0, 1.0, span)
    hue = np.where(high == r, ((g - b) / safe) % 6.0, np.where(high == g, (b - r) / safe + 2.0, (r - g) / safe + 4.0)) / 6.0
    hue = np.where(span == 0, 0.0, hue)
    saturation = np.where(high == 0, 0.0, span / np.where(high == 0, 1.0, high))
    return np.stack([hue, saturation, high], axis=-1)


def _hsv_to_rgb(hsv):
    h, s, v = hsv[..., 0] * 6.0, hsv[..., 1], hsv[..., 2]
    i = np.floor(h).astype(int) % 6
    f = h - np.floor(h)
    p, q, t = v * (1 - s), v * (1 - s * f), v * (1 - s * (1 - f))
    choices = [(v, t, p), (q, v, p), (p, v, t), (p, q, v), (t, p, v), (v, p, q)]
    out = np.zeros(hsv.shape)
    for index, (r, g, b) in enumerate(choices):
        mask = i == index
        out[..., 0][mask], out[..., 1][mask], out[..., 2][mask] = r[mask], g[mask], b[mask]
    return out


def _rows(v0, v1):
    return slice(int(round(v0 * SIZE)), int(round(v1 * SIZE)))


def _window(rect):
    u0, v0, u1, v1 = rect
    return _rows(v0, v1), slice(int(round(u0 * SIZE)), int(round(u1 * SIZE)))


def _blue_eyes(rgb):
    hsv = _rgb_to_hsv(rgb)
    hsv[..., 0] = (hsv[..., 0] + EYE_HUE_SHIFT) % 1.0
    hsv[..., 1] = np.clip(hsv[..., 1] * EYE_SATURATION, 0.0, 1.0)
    hsv[..., 2] = np.clip(hsv[..., 2] * EYE_VALUE, 0.0, 1.0)
    return _hsv_to_rgb(hsv)


def _coverage(inside, height, width, oversample=3):
    """Antialiased mask of an implicit shape. `inside(x, y)` takes coordinates in -1..1 (y up), x scaled to the cell's aspect."""
    ys = (np.arange(height * oversample) + 0.5) / (height * oversample) * 2.0 - 1.0
    xs = ((np.arange(width * oversample) + 0.5) / (width * oversample) * 2.0 - 1.0) * (width / height)
    x, y = np.meshgrid(xs, ys)
    mask = inside(x, y).astype(np.float64)
    return mask.reshape(height, oversample, width, oversample).mean(axis=(1, 3))[..., None]


def _heart(x, y, size):
    x, y = x / size, (y + 0.05) / size
    return (x * x + y * y - 1.0) ** 3 - x * x * y ** 3 <= 0.0


def _star(x, y, size, cx=0.0, cy=0.0):
    x, y = np.abs(x - cx) / size, np.abs(y - cy) / size
    return x ** 0.62 + y ** 0.62 <= 1.0


def _paint(base, shape):
    """Draws a heart or a star pupil over an iris. Shapes are drawn, not sampled, so they stay crisp."""
    height, width = base.shape[:2]
    layers = {
        "heart": [
            (lambda x, y: _heart(x, y, 0.40), HEART_RIM),
            (lambda x, y: _heart(x, y, 0.33), HEART_COLOUR),
            (lambda x, y: _star(x, y, 0.09, -0.13, 0.20), (1.0, 1.0, 1.0)),
        ],
        "star": [
            (lambda x, y: _star(x, y, 0.58), STAR_RIM),
            (lambda x, y: _star(x, y, 0.47), STAR_COLOUR),
            (lambda x, y: _star(x, y, 0.20), (1.0, 0.98, 0.80)),
            (lambda x, y: _star(x, y, 0.16, 0.36, -0.52), STAR_COLOUR),
            (lambda x, y: _star(x, y, 0.12, -0.38, 0.55), STAR_COLOUR),
        ],
    }[shape]
    out = base.copy()
    for inside, colour in layers:
        mask = _coverage(inside, height, width)
        out = out * (1.0 - mask) + np.array(colour) * mask
    return out


def _retint(rgb, colour):
    """Recolours the red-brown line art in a window, keeping its own light and dark."""
    hsv = _rgb_to_hsv(rgb)
    line = (hsv[..., 1] > 0.35) & ((hsv[..., 0] < 0.09) | (hsv[..., 0] > 0.95))
    if not line.any():
        return rgb
    luminance = rgb @ np.array([0.299, 0.587, 0.114])
    reference = np.median(luminance[line])
    shade = np.clip(luminance / reference, 0.0, 1.6)[..., None]
    out = rgb.copy()
    out[line] = np.clip(np.array(colour) * shade, 0.0, 1.0)[line]
    return out


def _resample(image, rect, height, width):
    """Bilinear sample of `image` (rows bottom-up) over a UV rect, onto a height x width grid."""
    u0, v0, u1, v1 = rect
    xs = (u0 + (np.arange(width) + 0.5) / width * (u1 - u0)) * image.shape[1] - 0.5
    ys = (v0 + (np.arange(height) + 0.5) / height * (v1 - v0)) * image.shape[0] - 0.5
    x0 = np.clip(np.floor(xs).astype(int), 0, image.shape[1] - 2)
    y0 = np.clip(np.floor(ys).astype(int), 0, image.shape[0] - 2)
    fx = np.clip(xs - x0, 0.0, 1.0)[None, :, None]
    fy = np.clip(ys - y0, 0.0, 1.0)[:, None, None]
    a = image[y0][:, x0]
    b = image[y0][:, x0 + 1]
    c = image[y0 + 1][:, x0]
    d = image[y0 + 1][:, x0 + 1]
    return (a * (1 - fx) + b * fx) * (1 - fy) + (c * (1 - fx) + d * fx) * fy


def _gingham(atlas):
    """Paints the gingham patch: woven stripes both ways, darker where they cross."""
    x0, y0, x1, y1 = GINGHAM_RECT
    across = (np.arange(x0, x1) - x0 - GINGHAM_MARGIN) % GINGHAM_PERIOD < GINGHAM_PERIOD // 2
    up = (np.arange(y0, y1) - y0 - GINGHAM_MARGIN) % GINGHAM_PERIOD < GINGHAM_PERIOD // 2
    atlas[y0:y1, x0:x1] = np.array(GINGHAM_COLOURS)[up[:, None].astype(int) + across[None, :].astype(int)]


def gingham_uv(cloth):
    """UVs for one face on the gingham patch. `cloth` is (n, 2): where each corner is on the cloth, in metres.

    The face is moved a whole number of repeats so that it starts in the
    patch's first one; neighbouring faces land on different parts of the
    patch and still meet on the same line of the pattern.
    """
    cloth = np.asarray(cloth, dtype=np.float64)
    period = GINGHAM_PERIOD / GINGHAM_SCALE
    pixels = (cloth - np.floor(cloth.min(axis=0) / period + 1e-9) * period) * GINGHAM_SCALE
    x0, y0, x1, y1 = GINGHAM_RECT
    room = np.array((x1 - x0, y1 - y0)) - 2 * GINGHAM_MARGIN
    if (pixels.max(axis=0) > room).any():
        raise RuntimeError(f"a face of {np.round(np.ptp(cloth, axis=0), 3)} m is too big for the gingham patch "
                           f"({np.round(room / GINGHAM_SCALE - period, 3)} m); divide the cloth more finely")
    return (np.array((x0, y0)) + GINGHAM_MARGIN + pixels) / SIZE


def body_uv(uv, level):
    """A body level's own UVs moved into its region of the atlas."""
    u, v, size = BODY_REGIONS[level]
    return np.array((u, v)) + np.asarray(uv) * size


def _weaken(normal_rgb, strength):
    """Scales a tangent-space normal map's tilt and renormalises it."""
    vector = normal_rgb * 2.0 - 1.0
    vector[..., :2] *= strength
    vector /= np.maximum(np.linalg.norm(vector, axis=-1, keepdims=True), 1e-6)
    return vector * 0.5 + 0.5


def build_normal(face_normal_png, body_normal_pngs, out_png):
    """Writes the normal atlas: flat, except under the face and under each body level's UVs."""
    source = _load(face_normal_png)[..., :3]
    if source.shape[0] != SIZE:
        raise RuntimeError("the face normal map is expected to be 2048 x 2048")
    atlas = np.empty((SIZE, SIZE, 3))
    atlas[:] = (0.5, 0.5, 1.0)
    strip = _rows(FACE_STRIP_V, 1.0)
    atlas[strip] = _weaken(source[strip], FACE_NORMAL_STRENGTH)
    for level, path in body_normal_pngs.items():
        u, v, size = BODY_REGIONS[level]
        pixels = int(round(size * SIZE))
        body = _load(path)[..., :3]
        if body.shape[0] % pixels:
            raise RuntimeError(f"{path} is {body.shape[0]} px, which does not divide into its {pixels} px region")
        factor = body.shape[0] // pixels
        body = body.reshape(pixels, factor, pixels, factor, 3).mean(axis=(1, 3))
        y, x = int(round(v * SIZE)), int(round(u * SIZE))
        atlas[y:y + pixels, x:x + pixels] = body
    image = bpy.data.images.new("cass-atlas-normal-bake", SIZE, SIZE, alpha=False)
    image.colorspace_settings.name = "Non-Color"
    rgba = np.ones((SIZE, SIZE, 4), dtype=np.float32)
    rgba[..., :3] = atlas
    image.pixels.foreach_set(rgba.ravel())
    image.filepath_raw = str(out_png)
    image.file_format = "PNG"
    image.save()
    bpy.data.images.remove(image)


def build_emission(palette_emission_png, out_png):
    """Writes the atlas's emission mask: white where a swatch glows, black everywhere else.

    Only swatches glow, and the palette is the atlas's bottom-left quarter of
    each axis, so the mask is the palette's own at its own size, in that
    corner of a picture four times as wide. It need be no finer: the face
    and the gingham, which fill the rest of the atlas, do not glow.
    """
    mask = _load(palette_emission_png)[..., :3]
    size = mask.shape[0] * int(PALETTE_SHRINK)
    whole = np.zeros((size, size, 4), dtype=np.float32)
    whole[..., 3] = 1.0
    whole[:mask.shape[0], :mask.shape[1], :3] = mask
    image = bpy.data.images.new("cass-atlas-emission-bake", size, size, alpha=False)
    image.pixels.foreach_set(whole.ravel())
    image.filepath_raw = str(out_png)
    image.file_format = "PNG"
    image.save()
    bpy.data.images.remove(image)


def build(face_png, palette_png, palette_json, out_png, out_json, overlays, skin_uvs):
    """Writes the atlas and returns {swatch name: (u, v)}.

    `overlays` lists (shape, UV rect of the overlay in the source, UV rect of
    the iris it covers in the face texture). `skin_uvs` are face
    texture UVs of the head's skin; their median is the body's colour.
    """
    face = _load(face_png)[..., :3]
    palette = _load(palette_png)[..., :3]
    if face.shape[0] != SIZE:
        raise RuntimeError("the face texture is expected to be 2048 x 2048")

    samples = np.array([face[min(SIZE - 1, int(v * SIZE)), min(SIZE - 1, int(u % 1.0 * SIZE))] for u, v in skin_uvs])
    skin = np.median(samples, axis=0)
    print(f"atlas: skin colour {tuple(int(round(c * 255)) for c in skin)} from {len(samples)} samples")
    atlas = np.empty((SIZE, SIZE, 3))
    atlas[:] = skin

    strip = _rows(FACE_STRIP_V, 1.0)
    atlas[strip] = face[strip]
    # Only the texels the irises use are recoloured; the artwork around them is skin and lashes.
    blue_face = face.copy()
    for u0, v0, u1, v1 in sorted({iris for _shape, _overlay, iris in overlays}):
        rows, columns = _window((u0 - EYE_PADDING, v0 - EYE_PADDING, min(1.0, u1 + EYE_PADDING), v1 + EYE_PADDING))
        blue_face[rows, columns] = _blue_eyes(face[rows, columns])
        atlas[rows, columns] = blue_face[rows, columns]
    rows, columns = _window(BROW_RECT)
    atlas[rows, columns] = _retint(atlas[rows, columns], BROW_COLOUR)
    for rect in LASH_RECTS:
        rows, columns = _window(rect)
        atlas[rows, columns] = _retint(atlas[rows, columns], LASH_COLOUR)

    # Each overlay is the recoloured iris with a heart or a star drawn over it. The source
    # paints its own in the pink of its irises, which does not survive the recolour.
    shift = int(round(OVERLAY_SHIFT * SIZE))
    for shape, overlay, iris in overlays:
        rows, columns = _window(overlay)
        size = (rows.stop - rows.start, columns.stop - columns.start)
        atlas[rows.start - shift:rows.stop - shift, columns] = _paint(_resample(blue_face, iris, *size), shape)

    _gingham(atlas)

    scale = int(PALETTE_SHRINK)
    big = np.repeat(np.repeat(palette, scale, axis=0), scale, axis=1)
    if big.shape[0] * PALETTE_SHRINK != SIZE:
        # The palette occupies exactly a quarter of each axis only at 512 px.
        raise RuntimeError(f"the palette is {palette.shape[0]} px; the atlas expects {SIZE // scale // scale} px")
    atlas[:big.shape[0], :big.shape[1]] = big

    spec = json.loads(open(palette_json, encoding="utf-8").read())
    swatches = {name: (entry["uv"][0] / PALETTE_SHRINK, entry["uv"][1] / PALETTE_SHRINK) for name, entry in spec["swatches"].items()}
    cell = spec["cell"] * scale
    u, v = swatches["skin"]
    x, y = int(u * SIZE) - cell // 2, int(v * SIZE) - cell // 2
    atlas[y:y + cell, x:x + cell] = skin

    image = bpy.data.images.new("cass-atlas-bake", SIZE, SIZE, alpha=False)
    rgba = np.ones((SIZE, SIZE, 4), dtype=np.float32)
    rgba[..., :3] = np.clip(atlas, 0.0, 1.0)
    image.pixels.foreach_set(rgba.ravel())
    image.filepath_raw = str(out_png)
    image.file_format = "PNG"
    image.save()
    bpy.data.images.remove(image)

    skin_hex = "#" + "".join(f"{int(round(c * 255)):02x}" for c in skin)
    document = {
        "$comment": "Written by blender/scripts/build_cass.py. Swatch UVs into cass-atlas.png; `skin` is sampled from the face texture.",
        "size": [SIZE, SIZE],
        "swatches": {name: {"uv": [round(u, 6), round(v, 6)],
                            "color": skin_hex if name == "skin" else spec["swatches"][name]["color"]}
                     for name, (u, v) in swatches.items()},
    }
    with open(out_json, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(document, indent=2) + "\n")
    return swatches
