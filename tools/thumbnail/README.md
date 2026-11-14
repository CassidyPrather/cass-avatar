# Thumbnail generator

Draws the 1200x900 (4:3) picture VRChat shows for an avatar, from a small
JSON manifest. One tool serves every upload variant: each part of the
picture is a stamp that is drawn only when the manifest has data for it.

```bash
python tools/thumbnail/make_thumbnail.py --manifest tools/thumbnail/sample-manifest.json --out thumbnail.png
python tools/thumbnail/test_thumbnail.py
```

Needs Python 3.10+ and Pillow 10. Nothing else: no network, no Inkscape.

## Manifest

```json
{
  "name": "cass",
  "variant": "cass-adv",
  "version": "0.1.0",
  "performanceRank": "Medium",
  "features": [{ "id": "flight", "label": "Flight", "icon": "flight" }],
  "tags": ["ai", "AGPLv3"],
  "url": "github.com/CassidyPrather/cass-avatar",
  "cutout": "cass-adv-cutout.png"
}
```

| Key | Type | Stamp |
| --- | --- | --- |
| `name` | string, required | Avatar name, in the heading face |
| `variant` | string, required | Variant slug chip |
| `version` | string, required | Version chip; a leading digit gets a `v` |
| `performanceRank` | `Excellent`, `Good`, `Medium`, `Poor`, `VeryPoor` or null | Rank badge; the SDK's `None` (not rated) counts as null |
| `features` | list of `{id, label, icon}` | Feature grid; omitted when empty |
| `tags` | list of strings | Tag chips |
| `url` | string or null | Source link strip |
| `cutout` | string or null | Path to the avatar render, relative to the manifest |

`performanceRank`, `features`, `tags`, `url` and `cutout` may be left out;
that is the same as null or an empty list, and so is an empty string. A
wrong type, a missing required field or a rank outside the five is an error
that names the field.

Keys the tool does not know are ignored, so the Unity build can pass its
whole build report as the manifest. The one exception is a known key in the
wrong case (`performancerank`), which is an error rather than a badge that
silently goes missing.

In a feature, `id` is the build's own name for it and `label` is what gets
printed; both are required. `icon` is the stem of a PNG in the icons
directory (`flight` for `flight.png`), kebab-case, no path and no extension.
Null or `""` means the feature has no icon and gets a placeholder tile.

The cut-out is an RGBA PNG of the avatar on a transparent background. Its
transparent margin is trimmed, then it is scaled, up or down, to fit its
frame whole and stood on the pedestal. It is never cropped. A `cutout` that
names a missing or unreadable file is an error; null leaves the avatar out
and centres the card.

## Options

| Option | Default | |
| --- | --- | --- |
| `--manifest` | required | Manifest JSON |
| `--out` | required | PNG to write; parent directories are created |
| `--icons` | `modules/wirenook-assets/Packages/net.wirenook.assets/Icons` | Directory of `<icon>.png` |
| `--display-font` | `../cass-website/static/fonts/Unique.ttf` beside this repository | Heading face |

Exit status is 0 on success and 1 on a bad manifest or cut-out, with the
reason on stderr. Things that degrade rather than fail (an icon that is
named but not found, more features than fit) are reported as warnings on
stderr and still exit 0.

## How it holds together

- Text is shrunk to fit its box, down to a floor, and then cut short with
  `...`. Nothing is ever drawn outside its box.
- The rank badge sits at the right of the title row; a long name pushes it
  down a row.
- The feature grid takes whatever height the rest of the card leaves: one
  column up to four features, two after that, three when two would not fit.
  Beyond that the last cell reads `+N more`, with a warning.
- Tags wrap to at most two rows; the rest collapse into a `+N` chip.
- A feature whose icon cannot be found keeps its row and gets a placeholder
  tile.
- The performance rank is shown three ways (colour, five pips, the word),
  so it survives colour blindness and greyscale.

`compose()` returns the image together with the box of every stamp it drew.
The tests use those boxes to assert that nothing leaves the canvas and no two
stamps overlap, across the awkward cases: no features, twelve, sixty, long
text in every field, no cut-out, no rank, a missing icon, a full build
report.

## Files

| File | |
| --- | --- |
| `make_thumbnail.py` | Command line, the stamps, and the layout |
| `manifest.py` | Manifest loading and validation |
| `paint.py` | Colours, fonts and the supersampled canvas |
| `sample-manifest.json` | A twelve-feature example without a cut-out |
| `test_thumbnail.py` | `unittest` suite; renders into a temporary directory |
| `fonts/` | Atkinson Hyperlegible Regular and Bold, with their licence |

## Fonts

Body text is Atkinson Hyperlegible, bundled under the SIL Open Font License
1.1 (`fonts/OFL.txt`).

Headings use the site's display face, Unique, only when its file is found at
`--display-font`. Its licence is unconfirmed, so it is not in this
repository and must not be added. Without it headings are set in Atkinson
Hyperlegible Bold. The tool prints which face it used.
