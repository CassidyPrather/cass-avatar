#!/usr/bin/env python3
"""Layout and input tests for the thumbnail generator.

    python tools/thumbnail/test_thumbnail.py

Everything renders into a temporary directory with generated icons and a
generated cut-out, so the tests need neither Unity nor the shared icon set.
"""

import contextlib
import io
import itertools
import json
import pathlib
import sys
import tempfile
import unittest

from PIL import Image, ImageDraw

# The modules under test sit beside this file, not in a package; and nothing
# in the repository ignores __pycache__, so the run must not leave one behind.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
sys.dont_write_bytecode = True

import make_thumbnail  # noqa: E402  (needs the path line above)
import manifest as manifest_module  # noqa: E402
from manifest import ManifestError  # noqa: E402

ICON_NAMES = ["locomotion", "flight", "carry", "catch-up", "megaphone", "flashlight"]
# Stamps that others are drawn over on purpose.
BEHIND = {"cutout"}
# Layout is floating point: boxes that share an edge may differ in the last
# bit. A hundredth of a pixel is far below anything that could be seen.
SLACK = 0.01


class ThumbnailTest(unittest.TestCase):
    def setUp(self):
        self._directory = tempfile.TemporaryDirectory()
        self.addCleanup(self._directory.cleanup)
        self.directory = pathlib.Path(self._directory.name)
        self.icons = self.directory / "icons"
        self.icons.mkdir()
        for name in ICON_NAMES:
            icon = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
            ImageDraw.Draw(icon).ellipse([8, 8, 56, 56], fill=(255, 255, 255, 255))
            icon.save(self.icons / f"{name}.png")
        # A bust: wider than it is tall once trimmed, with a transparent margin.
        cutout = Image.new("RGBA", (400, 400), (0, 0, 0, 0))
        ImageDraw.Draw(cutout).rectangle([60, 80, 340, 399], fill=(200, 160, 120, 255))
        self.cutout = self.directory / "cutout.png"
        cutout.save(self.cutout)

    def compose(self, icons=(), cutout=True):
        data = {"icons": list(icons), "cutout": str(self.cutout) if cutout else None}
        return make_thumbnail.compose(manifest_module.parse(data, self.directory), icons=self.icons)

    def assert_sound(self, result):
        self.assertEqual(result.image.size, make_thumbnail.CANVAS)
        frame = make_thumbnail.Box(-SLACK, -SLACK, make_thumbnail.CANVAS[0] + SLACK, make_thumbnail.CANVAS[1] + SLACK)
        for placement in result.placements:
            self.assertTrue(frame.contains(placement.box), f"{placement.stamp} leaves the canvas: {placement.box}")
        separate = [placement for placement in result.placements if placement.stamp not in BEHIND]
        for first, second in itertools.combinations(separate, 2):
            self.assertFalse(first.box.inset(SLACK).overlaps(second.box.inset(SLACK)),
                             f"{first.stamp} {first.box} overlaps {second.stamp} {second.box}")

    def test_every_icon_count_stays_on_the_canvas_without_overlap(self):
        for count in (0, 1, 2, 6, 12, 30):
            with self.subTest(icons=count):
                names = [f"icon-{index}" for index in range(count)]
                result = self.compose(names)
                self.assert_sound(result)
                self.assertEqual(sum(placement.stamp == "icon" for placement in result.placements), count)

    def test_works_without_a_cutout(self):
        result = self.compose(ICON_NAMES, cutout=False)
        self.assert_sound(result)
        self.assertNotIn("cutout", {placement.stamp for placement in result.placements})

    def test_the_bust_stands_on_the_bottom_edge(self):
        box = next(placement.box for placement in self.compose().placements if placement.stamp == "cutout")
        self.assertAlmostEqual(box.bottom, make_thumbnail.CANVAS[1])

    def test_icons_are_large_enough_to_read_small(self):
        # VRChat lists avatars at roughly a sixth of this size; a tile under a
        # tenth of the width would be a dozen pixels there.
        tiles = [placement.box for placement in self.compose(ICON_NAMES).placements if placement.stamp == "icon"]
        self.assertGreaterEqual(min(tile.width for tile in tiles), make_thumbnail.CANVAS[0] / 10)

    def test_a_missing_icon_keeps_its_tile_and_warns(self):
        result = self.compose(["locomotion", "no-such-icon"])
        self.assertEqual(sum(placement.stamp == "icon" for placement in result.placements), 2)
        self.assertTrue(any("no-such-icon" in warning for warning in result.warnings))

    def test_a_repeated_icon_is_drawn_once(self):
        self.assertEqual(manifest_module.parse({"icons": ["flight", "flight", "carry"]}, self.directory).icons,
                         ("flight", "carry"))

    def test_unknown_keys_are_ignored(self):
        parsed = manifest_module.parse({"icons": ["flight"], "triangles": 9000, "name": "cass"}, self.directory)
        self.assertEqual(parsed.icons, ("flight",))

    def test_bad_manifests_name_the_field(self):
        cases = {
            "icons": ({"icons": "flight"}, {"icons": ["Icons/flight.png"]}, {"icons": [3]}, {"Icons": ["flight"]}),
            "cutout": ({"cutout": 3}, {"Cutout": "x.png"}),
        }
        for field, manifests in cases.items():
            for data in manifests:
                with self.subTest(data=data):
                    with self.assertRaises(ManifestError) as raised:
                        manifest_module.parse(data, self.directory)
                    self.assertIn(field, str(raised.exception).lower())
        with self.assertRaises(ManifestError):
            manifest_module.parse([], self.directory)

    def test_a_missing_or_empty_cutout_is_an_error(self):
        with self.assertRaises(make_thumbnail.ThumbnailError):
            make_thumbnail.compose(manifest_module.parse({"cutout": "absent.png"}, self.directory), icons=self.icons)
        Image.new("RGBA", (32, 32), (0, 0, 0, 0)).save(self.directory / "empty.png")
        with self.assertRaises(make_thumbnail.ThumbnailError):
            make_thumbnail.compose(manifest_module.parse({"cutout": "empty.png"}, self.directory), icons=self.icons)

    def test_command_line_writes_the_picture(self):
        manifest = self.directory / "manifest.json"
        manifest.write_text(json.dumps({"icons": ICON_NAMES, "cutout": "cutout.png"}), encoding="utf-8")
        out = self.directory / "out" / "thumbnail.png"
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            status = make_thumbnail.main(["--manifest", str(manifest), "--out", str(out), "--icons", str(self.icons)])
        self.assertEqual(status, 0)
        with Image.open(out) as written:
            self.assertEqual(written.size, make_thumbnail.CANVAS)

    def test_command_line_reports_a_bad_manifest(self):
        manifest = self.directory / "manifest.json"
        manifest.write_text("{", encoding="utf-8")
        errors = io.StringIO()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(errors):
            status = make_thumbnail.main(["--manifest", str(manifest), "--out", str(self.directory / "x.png")])
        self.assertEqual(status, 1)
        self.assertIn("not valid JSON", errors.getvalue())


if __name__ == "__main__":
    unittest.main()
