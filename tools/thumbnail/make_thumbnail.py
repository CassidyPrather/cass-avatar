#!/usr/bin/env python3
"""Composes the 1200x900 image VRChat shows for one avatar variant.

    tools/thumbnail/make_thumbnail.py --manifest manifest.json --out thumbnail.png

VRChat shows this picture a couple of hundred pixels wide, beside the
avatar's name, tags, description and performance rank. So it carries no
text and repeats none of that: it is the avatar's head and shoulders over a
wirenook.net backdrop, and one icon per kind of feature the variant has.
README.md beside this file documents the manifest.

Pillow only: no network, no Inkscape. Feature icons are the PNG
exports in net.wirenook.assets' Icons/ directory.
"""

import argparse
import dataclasses
import math
import pathlib
import sys

from PIL import Image, ImageDraw, ImageFilter

# Nothing in this repository ignores __pycache__, and the build runs this
# script in place; without this every run would leave untracked files behind.
sys.dont_write_bytecode = True

import manifest as manifest_module  # noqa: E402
from manifest import Manifest, ManifestError  # noqa: E402
from paint import BLUE, ICE, INK, LAVENDER, PANEL_STRONG, VIOLET, WHITE, Box, Painter, rgba  # noqa: E402

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent.parent
DEFAULT_ICONS = REPO / "modules" / "wirenook-assets" / "Packages" / "net.wirenook.assets" / "Icons"

CANVAS = (1200, 900)
# The bust stands on the bottom edge and may use nearly the whole picture.
AVATAR_FIT = Box(70, 36, 1130, 900)
# The icons sit in one row along the bottom, over the avatar's chest.
ICON_ROW = Box(36, 0, 1164, 868)
ICON_MAX = 196
ICON_GAP = 18


class ThumbnailError(Exception):
    """The thumbnail cannot be drawn; the message is ready to show the user."""


@dataclasses.dataclass(frozen=True)
class Placement:
    """Where one stamp ended up, so callers and tests can check the layout."""

    stamp: str
    box: Box


@dataclasses.dataclass(frozen=True)
class Result:
    image: Image.Image
    placements: list[Placement]
    warnings: list[str]


# ---------------------------------------------------------------- backdrop


def _gradient(size: tuple[int, int], degrees: float, stops: list[tuple[float, str]]) -> Image.Image:
    """A CSS-style linear gradient: `degrees` as CSS counts them, stops as (0..1, colour).

    Computed on a coarse grid and scaled up; a gradient has no detail to lose,
    and this keeps the per-pixel arithmetic out of Python.
    """
    columns, rows = 48, 36
    x_step, y_step = math.sin(math.radians(degrees)), -math.cos(math.radians(degrees))
    reach = [x * x_step + y * y_step for x in (0, columns - 1) for y in (0, rows - 1)]
    low, span = min(reach), max(reach) - min(reach)
    colours = [(position, rgba(colour)[:3]) for position, colour in stops]

    def colour_at(along: float) -> tuple[int, ...]:
        for (start, first), (end, second) in zip(colours, colours[1:]):
            if along <= end:
                mix = (along - start) / (end - start)
                return tuple(round(a + (b - a) * mix) for a, b in zip(first, second))
        return colours[-1][1]

    coarse = Image.new("RGB", (columns, rows))
    coarse.putdata([colour_at((x * x_step + y * y_step - low) / span) for y in range(rows) for x in range(columns)])
    return coarse.resize(size, Image.BICUBIC)


def _sparkle(cx: float, cy: float, radius: float) -> list[tuple[float, float]]:
    """The four-point star the site tiles down its left edge."""
    points = []
    for index in range(8):
        reach = radius if index % 2 == 0 else radius * 0.34
        angle = math.radians(-90 + index * 45)
        points.append((cx + reach * math.cos(angle), cy + reach * math.sin(angle)))
    return points


def stamp_background(painter: Painter) -> None:
    """Sky, cloud, the sparkle field on the left edge and the ruler ticks: the site's page."""
    painter.image.paste(_gradient(painter.image.size, 155, [(0, "#65b8e6"), (0.48, "#519ed5"), (1, "#8abbe9")]))

    # Clouds are soft enough to draw small and scale up, which is far cheaper
    # than blurring at full size.
    small = (CANVAS[0] // 4, CANVAS[1] // 4)
    clouds = Image.new("RGBA", small, (0, 0, 0, 0))
    cloud_draw = ImageDraw.Draw(clouds)
    for cx, cy, rx, ry, colour, alpha in (
        (150, 700, 330, 170, VIOLET, 0.34), (420, 820, 300, 110, LAVENDER, 0.50),
        (1010, 150, 300, 120, VIOLET, 0.24), (760, 60, 260, 90, LAVENDER, 0.42),
        (1080, 760, 280, 150, LAVENDER, 0.46), (640, 470, 260, 130, ICE, 0.22),
        (120, 170, 220, 100, ICE, 0.20),
    ):
        cloud_draw.ellipse([(cx - rx) / 4, (cy - ry) / 4, (cx + rx) / 4, (cy + ry) / 4], fill=rgba(colour, alpha))
    painter.overlay(clouds.filter(ImageFilter.GaussianBlur(18)))

    # Two interleaved lattices of stars that thin out to the right.
    pitch, reach = 18, 250
    for colour, alpha, shift in (("#8b13d6", 0.75, 0), ("#ddc8eb", 0.50, pitch / 2)):
        for row in range(CANVAS[1] // pitch + 2):
            for column in range(reach // pitch + 1):
                x, y = column * pitch + shift + 6, row * pitch + shift + 4
                fade = 1 - x / reach
                if fade > 0.04:
                    painter.polygon(_sparkle(x, y, 4.5), fill=rgba(colour, alpha * fade))

    # Ruler ticks along the top and right edges, every fifth one longer.
    tick = rgba(PANEL_STRONG, 0.75)
    for index, x in enumerate(range(150, CANVAS[0], 12)):
        painter.line([(x, 0), (x, 16 if index % 5 == 0 else 8)], tick, 1.5)
    for index, y in enumerate(range(12, CANVAS[1], 12)):
        length = 16 if index % 5 == 0 else 8
        painter.line([(CANVAS[0] - length, y), (CANVAS[0], y)], tick, 1.5)


# ------------------------------------------------------------------ avatar


def load_cutout(path: pathlib.Path) -> Image.Image:
    """Opens the avatar render and trims it to what is actually visible."""
    try:
        image = Image.open(path).convert("RGBA")
    except FileNotFoundError as error:
        raise ThumbnailError(f"cutout: {path} does not exist") from error
    except OSError as error:
        raise ThumbnailError(f"cutout: {path} is not a readable image ({error})") from error
    # Unity pads the render; fitting the padded frame would shrink the avatar.
    # Faint antialiasing fringe is ignored so it cannot hold the box open.
    visible = image.getchannel("A").point(lambda alpha: 255 if alpha > 8 else 0).getbbox()
    if visible is None:
        raise ThumbnailError(f"cutout: {path} is fully transparent")
    return image.crop(visible)


def stamp_cutout(painter: Painter, cutout: Image.Image) -> Placement:
    """The avatar's bust in front of a moon ring, standing on the bottom edge.

    The cut-out is scaled to fit AVATAR_FIT whole: it is never cropped, so a
    tall hat makes the avatar smaller rather than losing its top.
    """
    fit = AVATAR_FIT
    centre = (fit.left + fit.right) / 2
    scale = min(fit.width / cutout.width, fit.height / cutout.height)
    width, height = cutout.width * scale, cutout.height * scale
    box = Box(centre - width / 2, fit.bottom - height, centre + width / 2, fit.bottom)

    # Ring and sparkles, after the "rabbit in a moon ring" logo, behind the head.
    radius = 330
    ring_y = box.top + 0.45 * box.height
    painter.ellipse(Box(centre - radius, ring_y - radius, centre + radius, ring_y + radius),
                    fill=rgba(ICE, 0.20), outline=rgba(WHITE, 0.9), width=5)
    outer = radius + 24
    painter.ellipse(Box(centre - outer, ring_y - outer, centre + outer, ring_y + outer),
                    outline=rgba(WHITE, 0.45), width=2.5)
    for degrees, size in ((-38, 34), (152, 22), (118, 13)):
        angle = math.radians(degrees)
        painter.polygon(_sparkle(centre + outer * math.cos(angle), ring_y + outer * math.sin(angle), size),
                        fill=rgba(PANEL_STRONG))

    # The banner's lettering treatment: the silhouette swept down-right in
    # hard violet. Steps of 3 px are close enough to read as one solid edge.
    silhouette = Image.new("RGBA", cutout.size, rgba(VIOLET))
    silhouette.putalpha(cutout.getchannel("A"))
    for offset in (15, 12, 9, 6, 3):
        painter.paste(silhouette, Box(box.left + offset, box.top + offset, box.right + offset, box.bottom + offset))
    painter.paste(cutout, box)
    return Placement("cutout", box)


# ------------------------------------------------------------------- icons


def load_icon(icons: pathlib.Path, name: str) -> Image.Image | None:
    try:
        return Image.open(icons / f"{name}.png").convert("RGBA")
    except (FileNotFoundError, OSError):
        return None


def stamp_icons(painter: Painter, names: tuple[str, ...], icons: pathlib.Path, warnings: list[str]) -> list[Placement]:
    """One tile per icon, in a single centred row that shrinks to fit them all.

    The tile is the expression menu's own dark wheel in miniature: the icons
    were drawn to sit on dark, and the light rim sets a tile off from
    whatever part of the avatar is behind it.
    """
    if not names:
        return []
    row = ICON_ROW
    count = len(names)
    tile = min(ICON_MAX, (row.width - ICON_GAP * (count - 1)) / count)
    left = (row.left + row.right) / 2 - (tile * count + ICON_GAP * (count - 1)) / 2
    top = row.bottom - tile
    radius = tile * 0.2
    rim = max(3.0, tile * 0.035)

    placements = []
    for name in names:
        box = Box(left, top, left + tile, top + tile)
        painter.rect(Box(box.left + rim, box.top + 2 * rim, box.right + rim, box.bottom + 2 * rim),
                     fill=rgba(INK, 0.45), radius=radius)
        painter.rect(box, fill=PANEL_STRONG, radius=radius)
        painter.rect(box.inset(rim), fill=BLUE, radius=radius - rim)
        icon = load_icon(icons, name)
        if icon is not None:
            painter.paste(icon, box.inset(tile * 0.1))
        else:
            warnings.append(f"icons: no icon {name!r} in {icons}; its tile is drawn with a placeholder")
            painter.polygon(_sparkle((box.left + box.right) / 2, (box.top + box.bottom) / 2, tile * 0.26), fill=ICE)
        placements.append(Placement("icon", box))
        left += tile + ICON_GAP
    return placements


# ----------------------------------------------------------------- compose


def compose(manifest: Manifest, *, icons: pathlib.Path = DEFAULT_ICONS) -> Result:
    """Draws every stamp the manifest has data for and reports where each one went."""
    painter = Painter(*CANVAS)
    placements: list[Placement] = []
    warnings: list[str] = []

    stamp_background(painter)
    if manifest.cutout:
        placements.append(stamp_cutout(painter, load_cutout(manifest.cutout)))
    placements.extend(stamp_icons(painter, manifest.icons, icons, warnings))
    return Result(painter.finish(), placements, warnings)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split(chr(10) * 2)[0])
    parser.add_argument("--manifest", type=pathlib.Path, required=True, help="manifest JSON (see README.md)")
    parser.add_argument("--out", type=pathlib.Path, required=True, help="PNG to write")
    parser.add_argument("--icons", type=pathlib.Path, default=DEFAULT_ICONS,
                        help="directory of <icon>.png feature icons (default: the shared Icons/)")
    arguments = parser.parse_args(argv)

    try:
        manifest = manifest_module.load(arguments.manifest)
        result = compose(manifest, icons=arguments.icons)
    except (ManifestError, ThumbnailError) as error:
        print(f"thumbnail: {error}", file=sys.stderr)
        return 1

    for warning in result.warnings:
        print(f"thumbnail: warning: {warning}", file=sys.stderr)
    arguments.out.parent.mkdir(parents=True, exist_ok=True)
    result.image.save(arguments.out, format="PNG", optimize=True)
    stamps = ", ".join(sorted({placement.stamp for placement in result.placements})) or "none"
    print(f"thumbnail: {arguments.out}: {CANVAS[0]}x{CANVAS[1]}; stamps: {stamps}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
