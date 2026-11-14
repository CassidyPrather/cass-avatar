#!/usr/bin/env python3
"""Composes the 1200x900 image VRChat shows for one avatar variant.

    tools/thumbnail/make_thumbnail.py --manifest manifest.json --out thumbnail.png

The picture is a stack of independent stamps over a wirenook.net backdrop: the
avatar cut-out, its name, variant and version, a performance-rank badge, the
enabled features, tags and a source link. Each stamp is drawn only when the
manifest carries its data, so one tool serves every variant. README.md beside
this file documents the manifest.

Pillow only: no network, no Inkscape. Feature icons are the PNG
exports in net.wirenook.assets' Icons/ directory.
"""

import argparse
import dataclasses
import math
import pathlib
import sys
from typing import Callable

from PIL import Image, ImageDraw, ImageFilter

# Nothing in this repository ignores __pycache__, and the build runs this
# script in place; without this every run would leave untracked files behind.
sys.dont_write_bytecode = True

import manifest as manifest_module  # noqa: E402
from manifest import Manifest, ManifestError  # noqa: E402
from paint import (  # noqa: E402
    BLUE, ICE, INK, LAVENDER, ORANGE, PANEL, PANEL_STRONG, PINK, SUPERSAMPLE, VIOLET, WHITE, Box, Fonts, Painter, rgba,
)

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent.parent
DEFAULT_ICONS = REPO / "modules" / "wirenook-assets" / "Packages" / "net.wirenook.assets" / "Icons"
# The site's display face. Its licence is unconfirmed, so it is never copied
# into this repository: it is used when a checkout of the site sits beside
# this one, and headings fall back to Atkinson Hyperlegible Bold otherwise.
DEFAULT_DISPLAY_FONT = REPO.parent / "cass-website" / "static" / "fonts" / "Unique.ttf"

CANVAS = (1200, 900)
FRAME = Box(0, 0, *CANVAS)
# With a cut-out the avatar stands on the left and the card takes the right;
# without one the card is centred so the picture does not look half empty.
AVATAR_FIT = Box(56, 48, 484, 806)
COLUMN_BESIDE_AVATAR = Box(540, 36, 1164, 864)
COLUMN_ALONE = Box(288, 36, 912, 864)
WINDOW_BORDER = 9
WINDOW_PADDING = 20
GAP = 14

# Conventional traffic-light order, taken from the shared palette. Hue alone
# fails for red-green colour blindness, so every badge also spells the rank
# out and fills one pip per step: the pips and the word carry it in greyscale.
RANKS = {
    "Excellent": ("Excellent", 5, "#4dff7a"),
    "Good": ("Good", 4, "#6fcf8f"),
    "Medium": ("Medium", 3, "#ffd27a"),
    "Poor": ("Poor", 2, "#ff8a3d"),
    "VeryPoor": ("Very Poor", 1, "#ff3b3b"),
}


class ThumbnailError(Exception):
    """The thumbnail cannot be drawn; the message is ready to show the user."""


@dataclasses.dataclass(frozen=True)
class Placement:
    """Where one stamp ended up, so callers and tests can check the layout."""

    stamp: str
    box: Box


@dataclasses.dataclass(frozen=True)
class Item:
    """One chip-sized thing that flows left to right inside the card."""

    stamp: str
    width: float
    height: float
    paint: Callable[[Painter, float, float], None]
    # A pushed item sits at the right end of its row, like the site's status chip.
    pushed: bool = False


@dataclasses.dataclass(frozen=True)
class Block:
    """One full-width row of the card: its height, and how to draw it at (left, top)."""

    height: float
    paint: Callable[[Painter, float, float], list[Placement]]


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
    """The avatar on a wireframe pedestal in front of a moon ring.

    The cut-out is scaled to fit AVATAR_FIT whole: it is never cropped, so a
    tall avatar gets narrower rather than losing its head.
    """
    fit = AVATAR_FIT
    centre = (fit.left + fit.right) / 2
    scale = min(fit.width / cutout.width, fit.height / cutout.height)
    width, height = cutout.width * scale, cutout.height * scale
    box = Box(centre - width / 2, fit.bottom - height, centre + width / 2, fit.bottom)

    # Ring and sparkles, after the "rabbit in a moon ring" logo. It rides at
    # chest height on a standing figure and stays clear of the pedestal behind
    # a short or wide one.
    radius = 212
    ring_y = min(box.top + 0.43 * box.height, fit.bottom - radius - 60)
    painter.ellipse(Box(centre - radius, ring_y - radius, centre + radius, ring_y + radius),
                    fill=rgba(ICE, 0.20), outline=rgba(WHITE, 0.9), width=3)
    outer = radius + 16
    painter.ellipse(Box(centre - outer, ring_y - outer, centre + outer, ring_y + outer),
                    outline=rgba(WHITE, 0.45), width=1.5)
    for degrees, size in ((-38, 20), (152, 13), (118, 8)):
        angle = math.radians(degrees)
        painter.polygon(_sparkle(centre + outer * math.cos(angle), ring_y + outer * math.sin(angle), size),
                        fill=rgba(PANEL_STRONG))

    # Pedestal: two rings of a truncated pyramid joined by struts, in the pink
    # wireframe of the site's pylon.
    wire = rgba(PINK, 0.95)
    sides = 10
    rings = []
    for y, rx, ry in ((fit.bottom - 4, 168, 20), (fit.bottom + 46, 214, 28)):
        ring = [(centre + rx * math.cos(math.tau * index / sides + 0.3),
                 y + ry * math.sin(math.tau * index / sides + 0.3)) for index in range(sides)]
        painter.line(ring + ring[:1], wire, 2)
        rings.append(ring)
    for top, bottom in zip(*rings):
        painter.line([top, bottom], wire, 2)

    # The banner's lettering treatment: the silhouette swept down-right in
    # hard violet. Steps of 2 px are close enough to read as one solid edge.
    silhouette = Image.new("RGBA", cutout.size, rgba(VIOLET))
    silhouette.putalpha(cutout.getchannel("A"))
    for offset in (8, 6, 4, 2):
        painter.paste(silhouette, Box(box.left + offset, box.top + offset, box.right + offset, box.bottom + offset))
    painter.paste(cutout, box)
    return Placement("cutout", box)


# -------------------------------------------------------------------- card


def _stripes(size: tuple[int, int]) -> Image.Image:
    """The site's index-window fill: a sky-to-lavender wash under tilted pinstripes.

    `size` is in real (supersampled) pixels.
    """
    width, height = size
    image = _gradient(size, 160, [(0, "#5fb0de"), (1, "#b4a6f4")])
    draw = ImageDraw.Draw(image, "RGBA")
    # CSS repeating-linear-gradient(172deg, ...): bands 8 degrees off horizontal.
    drop = math.tan(math.radians(8)) * width
    period = 15 * SUPERSAMPLE
    violet_band = period * 0.55
    for top in range(-period, height + round(drop) + period, period):
        for start, end, colour in ((0, violet_band, (84, 80, 188, 51)), (violet_band, period, (111, 244, 255, 61))):
            draw.polygon([(0, top + start), (width, top + start - drop), (width, top + end - drop), (0, top + end)],
                         fill=colour)
    return image


def stamp_window(painter: Painter, box: Box) -> None:
    """The striped, double-bordered window every page of the site sits in."""
    # Its soft violet shadow, drawn small and scaled up like the clouds.
    small = (CANVAS[0] // 4, CANVAS[1] // 4)
    shadow = Image.new("RGBA", small, (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rectangle(
        [box.left / 4, (box.top + 18) / 4, box.right / 4, (box.bottom + 18) / 4], fill=rgba("#41187f", 0.42))
    painter.overlay(shadow.filter(ImageFilter.GaussianBlur(7)))

    size = (painter.px(box.width), painter.px(box.height))
    painter.image.paste(_stripes(size), (painter.px(box.left), painter.px(box.top)))
    # "5px double": two lines with the stripes showing between them.
    third = WINDOW_BORDER / 3
    painter.rect(box, outline=rgba(PANEL_STRONG, 0.95), width=third)
    painter.rect(box.inset(2 * third), outline=rgba(PANEL_STRONG, 0.95), width=third)


def _chip(painter: Painter, stamp: str, text: str, *, face: str, size: float, min_size: float, height: float,
          pad: float, fill: str, colour: str, max_width: float, border: str | None = None) -> Item:
    """A flat rectangular label, the site's chip: hugs its text, never wider than `max_width`."""
    text, size = painter.fit(text, face, size, min_size, max_width - 2 * pad)
    width = painter.text_width(text, face, size) + 2 * pad

    def paint(painter: Painter, left: float, top: float) -> None:
        box = Box(left, top, left + width, top + height)
        painter.rect(box, fill=fill, outline=border, width=1.5)
        painter.text(left + pad, top + height / 2, text, face, size, colour)

    return Item(stamp, width, height, paint)


def name_item(painter: Painter, name: str, max_width: float) -> Item:
    return _chip(painter, "name", name, face="display", size=86, min_size=40, height=108, pad=24,
                 fill=PANEL_STRONG, colour=INK, max_width=max_width, border=WHITE)


def variant_item(painter: Painter, variant: str, max_width: float) -> Item:
    return _chip(painter, "variant", variant, face="bold", size=26, min_size=16, height=46, pad=14,
                 fill=INK, colour=PANEL_STRONG, max_width=max_width)


def version_item(painter: Painter, version: str, max_width: float) -> Item:
    # Bare numbers get the conventional "v"; anything else is printed as given.
    text = f"v{version}" if version[:1].isdigit() else version
    return _chip(painter, "version", text, face="regular", size=26, min_size=16, height=46, pad=14,
                 fill=PANEL_STRONG, colour=INK, max_width=max_width, border=WHITE)


def tag_item(painter: Painter, tag: str, max_width: float) -> Item:
    return _chip(painter, "tag", tag, face="regular", size=22, min_size=14, height=38, pad=13,
                 fill=PANEL_STRONG, colour=INK, max_width=max_width, border=WHITE)


def rank_item(painter: Painter, rank: str) -> Item:
    """Performance rank: an ink "PERF" tab, then pips and the rank spelt out on its colour."""
    label, filled, colour = RANKS[rank]
    height, pad, pip, pip_gap = 46, 12, 11, 4
    tab_size, size = 17, 25
    tab_width = painter.text_width("PERF", "bold", tab_size) + 2 * pad
    pips_width = 5 * pip + 4 * pip_gap
    width = tab_width + pad + pips_width + 10 + painter.text_width(label, "bold", size) + pad

    def paint(painter: Painter, left: float, top: float) -> None:
        middle = top + height / 2
        painter.rect(Box(left, top, left + width, top + height), fill=colour)
        painter.rect(Box(left, top, left + tab_width, top + height), fill=INK)
        painter.text(left + pad, middle, "PERF", "bold", tab_size, PANEL_STRONG)
        x = left + tab_width + pad
        for index in range(5):
            box = Box(x, middle - pip / 2, x + pip, middle + pip / 2)
            if index < filled:
                painter.rect(box, fill=INK)
            else:
                painter.rect(box, outline=INK, width=1.5)
            x += pip + pip_gap
        painter.text(x - pip_gap + 10, middle, label, "bold", size, INK)
        painter.rect(Box(left, top, left + width, top + height), outline=INK, width=2)

    return Item("rank", width, height, paint, pushed=True)


def _wrap(items: list[Item], width: float) -> list[list[Item]]:
    rows: list[list[Item]] = [[]]
    used = 0.0
    for item in items:
        if rows[-1] and used + GAP + item.width > width:
            rows.append([])
            used = 0.0
        used += (GAP if rows[-1] else 0) + item.width
        rows[-1].append(item)
    return rows


def flow_block(items: list[Item], width: float, max_rows: int | None = None,
               summarise: Callable[[int], Item] | None = None) -> Block:
    """Lays items out left to right, wrapping to a new row when one does not fit.

    With `max_rows`, items that would start a further row are dropped from the
    end and replaced by `summarise(how_many_dropped)`, so a long list costs a
    bounded amount of the card's height.
    """
    rows = _wrap(items, width)
    kept = len(items)
    while max_rows is not None and len(rows) > max_rows and kept > 0:
        kept -= 1
        rows = _wrap(items[:kept] + [summarise(len(items) - kept)], width)
    heights = [max(item.height for item in row) for row in rows]

    def paint(painter: Painter, left: float, top: float) -> list[Placement]:
        placements = []
        for row, row_height in zip(rows, heights):
            x = left
            for item in row:
                # Only the last item of a row can be pushed without crossing a neighbour.
                if item.pushed and item is row[-1]:
                    x = left + width - item.width
                y = top + (row_height - item.height) / 2
                item.paint(painter, x, y)
                placements.append(Placement(item.stamp, Box(x, y, x + item.width, y + item.height)))
                x += item.width + GAP
            top += row_height + GAP
        return placements

    return Block(sum(heights) + GAP * (len(rows) - 1), paint)


def load_icon(icons: pathlib.Path, name: str) -> Image.Image | None:
    try:
        return Image.open(icons / f"{name}.png").convert("RGBA")
    except (FileNotFoundError, OSError):
        return None


def features_block(painter: Painter, features, icons: pathlib.Path, width: float, max_height: float,
                   warnings: list[str]) -> Block:
    """The enabled features as a grid of icon tiles and labels on an ice panel.

    Rows share whatever height is left in the card, between a comfortable
    maximum and a floor below which labels stop being readable. If even the
    floor does not hold every feature, the grid is cut short and its last
    cell says how many are missing rather than letting anything overflow.
    """
    pad, row_max, row_min, column_gap = 16, 62, 36, 16
    inner_height = max_height - 2 * pad
    count = len(features)

    columns = 1 if count <= 4 else 2
    if math.ceil(count / columns) * row_min > inner_height:
        columns = 3
    rows = min(math.ceil(count / columns), max(1, int(inner_height // row_min)))
    row_height = max(row_min, min(row_max, inner_height / rows))
    capacity = rows * columns
    shown = list(features[:capacity])
    hidden = count - len(shown)
    if hidden:
        # The summary takes a cell of its own, so one more feature makes way for it.
        shown.pop()
        hidden += 1
        warnings.append(f"features: only {len(shown)} of {count} fit; the rest are summarised as +{hidden} more")

    cell_width = (width - 2 * pad - column_gap * (columns - 1)) / columns
    tile = row_height - 8
    label_size = min(27, tile * 0.52)
    label_left = tile + 12

    cells = []
    for feature in shown:
        icon = load_icon(icons, feature.icon) if feature.icon else None
        if icon is None and feature.icon:
            warnings.append(f"features: no icon {feature.icon!r} in {icons}; {feature.id!r} is drawn without one")
        text, size = painter.fit(feature.label, "regular", label_size, 13, cell_width - label_left)
        cells.append((icon, text, size))
    more = f"+{hidden} more" if hidden else None
    height = rows * row_height + 2 * pad

    def paint(painter: Painter, left: float, top: float) -> list[Placement]:
        painter.rect(Box(left, top, left + width, top + height), fill=PANEL, outline=WHITE, width=1.5)
        placements = []
        for index in range(len(cells) + (1 if more else 0)):
            # Column-major, so the list reads down the first column and then the next.
            column, row = divmod(index, rows)
            x = left + pad + column * (cell_width + column_gap)
            y = top + pad + row * row_height
            middle = y + row_height / 2
            if index == len(cells):
                painter.text(x + 4, middle, more, "bold", label_size, VIOLET)
                placements.append(Placement("features-more", Box(x, y, x + cell_width, y + row_height)))
                continue
            icon, text, size = cells[index]
            # The tile is the menu's own dark wheel in miniature: the icons
            # were drawn to sit on dark, and it sets them off from the panel.
            tile_box = Box(x, middle - tile / 2, x + tile, middle + tile / 2)
            painter.rect(tile_box, fill=BLUE, radius=tile * 0.18)
            painter.rect(tile_box, outline=INK, width=1.5, radius=tile * 0.18)
            if icon is not None:
                painter.paste(icon, tile_box.inset(tile * 0.07))
            else:
                painter.polygon(_sparkle((tile_box.left + tile_box.right) / 2, middle, tile * 0.22), fill=ICE)
            painter.text(x + label_left, middle, text, "regular", size, INK)
            placements.append(Placement("feature", Box(x, y, x + cell_width, y + row_height)))
        return placements

    return Block(height, paint)


def url_block(painter: Painter, url: str, width: float) -> Block:
    """The source link on a strip with the orange bar the site gives a quoted brief."""
    height, bar, pad = 48, 8, 16
    text, size = painter.fit(url, "regular", 24, 14, width - bar - 2 * pad)

    def paint(painter: Painter, left: float, top: float) -> list[Placement]:
        box = Box(left, top, left + width, top + height)
        painter.rect(box, fill=PANEL_STRONG)
        painter.rect(Box(left, top, left + bar, top + height), fill=ORANGE)
        painter.text(left + bar + pad, top + height / 2, text, "regular", size, VIOLET)
        return [Placement("url", box)]

    return Block(height, paint)


# ----------------------------------------------------------------- compose


def compose(manifest: Manifest, *, icons: pathlib.Path = DEFAULT_ICONS, fonts: Fonts) -> Result:
    """Draws every stamp the manifest has data for and reports where each one went."""
    painter = Painter(*CANVAS, fonts)
    placements: list[Placement] = []
    warnings: list[str] = []

    stamp_background(painter)
    cutout = load_cutout(manifest.cutout) if manifest.cutout else None
    if cutout is not None:
        placements.append(stamp_cutout(painter, cutout))
    column = COLUMN_BESIDE_AVATAR if cutout is not None else COLUMN_ALONE
    width = column.width - 2 * (WINDOW_BORDER + WINDOW_PADDING)

    # The rank sits at the right of the title row, where the site keeps its
    # status chip, unless a long name leaves no room; then it joins the row below.
    header = [name_item(painter, manifest.name, width)]
    details = [variant_item(painter, manifest.variant, width), version_item(painter, manifest.version, width)]
    if manifest.performance_rank:
        rank = rank_item(painter, manifest.performance_rank)
        (header if header[0].width + GAP + rank.width <= width else details).append(rank)

    above = [flow_block(header, width), flow_block(details, width)]
    below = []
    if manifest.tags:
        below.append(flow_block([tag_item(painter, tag, width) for tag in manifest.tags], width, max_rows=2,
                                summarise=lambda dropped: tag_item(painter, f"+{dropped}", width)))
    if manifest.url:
        below.append(url_block(painter, manifest.url, width))

    blocks = above + below
    if manifest.features:
        chrome = 2 * (WINDOW_BORDER + WINDOW_PADDING) + GAP * len(blocks)
        room = column.height - chrome - sum(block.height for block in blocks)
        blocks = above + [features_block(painter, manifest.features, icons, width, room, warnings)] + below

    height = sum(block.height for block in blocks) + GAP * (len(blocks) - 1) + 2 * (WINDOW_BORDER + WINDOW_PADDING)
    top = column.top + (column.height - height) / 2
    window = Box(column.left, top, column.right, top + height)
    stamp_window(painter, window)
    placements.append(Placement("window", window))

    y = top + WINDOW_BORDER + WINDOW_PADDING
    for block in blocks:
        placements.extend(block.paint(painter, column.left + WINDOW_BORDER + WINDOW_PADDING, y))
        y += block.height + GAP

    return Result(painter.finish(), placements, warnings)


def load_fonts(display: pathlib.Path | None = DEFAULT_DISPLAY_FONT) -> Fonts:
    """The bundled body faces, plus the display face when its file is there."""
    if display is not None and not display.is_file():
        display = None
    return Fonts(HERE / "fonts" / "AtkinsonHyperlegible-Regular.ttf",
                 HERE / "fonts" / "AtkinsonHyperlegible-Bold.ttf", display)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--manifest", type=pathlib.Path, required=True, help="manifest JSON (see README.md)")
    parser.add_argument("--out", type=pathlib.Path, required=True, help="PNG to write")
    parser.add_argument("--icons", type=pathlib.Path, default=DEFAULT_ICONS,
                        help="directory of <icon>.png feature icons (default: the shared Icons/)")
    parser.add_argument("--display-font", type=pathlib.Path, default=DEFAULT_DISPLAY_FONT,
                        help="heading face; Atkinson Hyperlegible Bold is used when the file is absent")
    arguments = parser.parse_args(argv)

    try:
        manifest = manifest_module.load(arguments.manifest)
        fonts = load_fonts(arguments.display_font)
        result = compose(manifest, icons=arguments.icons, fonts=fonts)
    except (ManifestError, ThumbnailError) as error:
        print(f"thumbnail: {error}", file=sys.stderr)
        return 1

    for warning in result.warnings:
        print(f"thumbnail: warning: {warning}", file=sys.stderr)
    arguments.out.parent.mkdir(parents=True, exist_ok=True)
    result.image.save(arguments.out, format="PNG", optimize=True)
    heading = arguments.display_font.name if fonts.has_display else "Atkinson Hyperlegible Bold (fallback)"
    stamps = ", ".join(sorted({placement.stamp for placement in result.placements}))
    print(f"thumbnail: {arguments.out}: {CANVAS[0]}x{CANVAS[1]}, headings in {heading}; stamps: {stamps}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
