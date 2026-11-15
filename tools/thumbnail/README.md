# Thumbnail generator

Draws the 1200x900 (4:3) picture VRChat shows for an avatar, from a small
JSON manifest.

VRChat shows the picture a couple of hundred pixels wide, next to the
avatar's name, description, tags and performance rank. So the picture has no
text and repeats none of those: it is the avatar's head and shoulders over
a wirenook.net backdrop, with one icon per kind of feature the variant has.

```bash
python tools/thumbnail/make_thumbnail.py --manifest tools/thumbnail/sample-manifest.json --out thumbnail.png
python tools/thumbnail/test_thumbnail.py
```

Needs Python 3.10+ and Pillow 10. Nothing else: no network, no Inkscape.

## Manifest

```json
{
  "icons": ["locomotion", "flight", "flashlight"],
  "cutout": "cass-adv-cutout.png"
}
```

| Key | Type | |
| --- | --- | --- |
| `icons` | list of strings | One tile each, in a row along the bottom |
| `cutout` | string or null | Path to the avatar render, relative to the manifest |

Both may be left out. Keys the tool does not know are ignored, so the Unity
build passes its whole build report as the manifest. The one exception is a
known key in the wrong case (`Icons`), which is an error rather than a
picture that silently loses its icons.

An icon is the stem of a PNG in the icons directory (`flight` for
`flight.png`), kebab-case, no path and no extension. A name listed twice is
drawn once. The build lists each feature's *summary icon*, which like
features share, so a flashlight and a lantern show as one light and the
pointer, megaphone and notices as one megaphone.

The cut-out is an RGBA PNG of the avatar from the chest up on a transparent
background. Its transparent margin is trimmed, then it is scaled, up or
down, to fit the picture whole and stood on the bottom edge. It is never
cropped. A `cutout` that names a missing or unreadable file is an error;
null leaves the avatar out.

## Options

| Option | Default | |
| --- | --- | --- |
| `--manifest` | required | Manifest JSON |
| `--out` | required | PNG to write; parent directories are created |
| `--icons` | `modules/wirenook-assets/Packages/net.wirenook.assets/Icons` | Directory of `<icon>.png` |

Exit status is 0 on success and 1 on a bad manifest or cut-out, with the
reason on stderr. An icon that is named but not found keeps its tile, gets
a placeholder, and is reported as a warning on stderr; the exit status is
still 0.

## How it holds together

- The icons share one row. Tiles are as large as fit, up to a maximum, so a
  variant with many kinds of feature gets smaller tiles rather than a
  second row. If the tiles are getting too small to read, group more
  features under one summary icon.
- The row sits over the avatar's chest; the face stays clear above it.

`compose()` returns the image together with the box of every stamp it drew.
The tests use those boxes to assert that nothing leaves the canvas and no
two icons overlap, from no icons to thirty.

## Files

| File | |
| --- | --- |
| `make_thumbnail.py` | Command line, the stamps, and the layout |
| `manifest.py` | Manifest loading and validation |
| `paint.py` | Colours and the supersampled canvas |
| `sample-manifest.json` | A six-icon example without a cut-out |
| `test_thumbnail.py` | `unittest` suite; renders into a temporary directory |
