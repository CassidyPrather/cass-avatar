#!/usr/bin/env python3
"""Lays the validation renders out as labelled contact sheets.

    tools/contact_sheet.py dist/validation/cass

Unity's ContactSheets tool writes one PNG per shot into a folder per sheet
(`1 cameras/000 Front.png`, ...). This turns each folder into a single
`<sheet>.png` beside it, every tile captioned with its file name, so a whole
round of model checks is a handful of images instead of a few hundred.
"""

import pathlib
import sys

from PIL import Image, ImageDraw, ImageFont

CAPTION_HEIGHT = 26
GAP = 6
# Wide enough to compare neighbours, narrow enough to stay readable when the
# sheet is viewed scaled down.
MAX_COLUMNS = 8
BACKGROUND = (24, 22, 34)
CAPTION = (232, 236, 244)


def font(size: int) -> ImageFont.ImageFont:
    bundled = pathlib.Path(__file__).parent / "thumbnail" / "fonts" / "AtkinsonHyperlegible-Regular.ttf"
    for candidate in (bundled, pathlib.Path("C:/Windows/Fonts/segoeui.ttf")):
        if candidate.exists():
            return ImageFont.truetype(str(candidate), size)
    return ImageFont.load_default()


def compose(folder: pathlib.Path) -> pathlib.Path:
    tiles = sorted(folder.glob("*.png"))
    if not tiles:
        raise SystemExit(f"contact-sheet: no tiles in {folder}")

    first = Image.open(tiles[0])
    width, height = first.size
    columns = min(MAX_COLUMNS, len(tiles))
    rows = -(-len(tiles) // columns)
    cell_width, cell_height = width + GAP, height + CAPTION_HEIGHT + GAP

    sheet = Image.new("RGB", (columns * cell_width + GAP, rows * cell_height + GAP), BACKGROUND)
    draw = ImageDraw.Draw(sheet)
    caption_font = font(17)
    for index, tile in enumerate(tiles):
        x = GAP + (index % columns) * cell_width
        y = GAP + (index // columns) * cell_height
        sheet.paste(Image.open(tile).convert("RGB"), (x, y))
        # Drop the ordering prefix Unity added to keep the tiles sorted.
        label = tile.stem.split(" ", 1)[-1]
        while label and draw.textlength(label, font=caption_font) > width - 8:
            label = label[:-2].rstrip() + "…" if len(label) > 2 else ""
        draw.text((x + 4, y + height + 3), label, fill=CAPTION, font=caption_font)

    out = folder.with_suffix(".png")
    sheet.save(out, optimize=True)
    return out


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    root = pathlib.Path(sys.argv[1])
    sheets = [compose(folder) for folder in sorted(root.iterdir()) if folder.is_dir()]
    for sheet in sheets:
        print(f"contact-sheet: {sheet}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
