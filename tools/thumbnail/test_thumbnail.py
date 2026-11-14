#!/usr/bin/env python3
"""Layout and input tests for the thumbnail generator.

    python tools/thumbnail/test_thumbnail.py

Everything renders into a temporary directory with generated icons and a
generated cut-out, so the tests need neither Unity nor the shared icon set.
Headings use the bundled fallback face, so results do not depend on whether
the optional display font happens to be on this machine.
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

ICON_NAMES = ["outfit", "expressions", "flight", "lantern"]
# Stamps that hold other stamps; everything else must keep to itself.
CONTAINERS = {"window"}
# Layout is floating point: boxes that share an edge may differ in the last
# bit. A hundredth of a pixel is far below anything that could be seen.
SLACK = 0.01


def base_manifest() -> dict:
    return {
        "name": "cass",
        "variant": "cass-adv",
        "version": "0.1.0",
        "performanceRank": "Good",
        "features": [],
        "tags": ["ai", "AGPLv3"],
        "url": "github.com/CassidyPrather/cass-avatar",
        "cutout": None,
    }


def features(count: int) -> list[dict]:
    return [
        {"id": f"feature-{index}", "label": f"Feature number {index}", "icon": ICON_NAMES[index % len(ICON_NAMES)]}
        for index in range(count)
    ]


class ThumbnailTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._scratch = tempfile.TemporaryDirectory()
        cls.scratch = pathlib.Path(cls._scratch.name)
        cls.icons = cls.scratch / "icons"
        cls.icons.mkdir()
        for name in ICON_NAMES:
            icon = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
            ImageDraw.Draw(icon).ellipse([40, 40, 216, 216], fill="#d7fbff", outline="#271452", width=8)
            icon.save(cls.icons / f"{name}.png")
        # A tall figure with a wide transparent margin, as Unity renders one.
        tall = Image.new("RGBA", (800, 1600), (0, 0, 0, 0))
        ImageDraw.Draw(tall).ellipse([300, 100, 500, 1500], fill="#365fc6")
        tall.save(cls.scratch / "tall.png")
        wide = Image.new("RGBA", (1600, 400), (0, 0, 0, 0))
        ImageDraw.Draw(wide).ellipse([50, 50, 1550, 350], fill="#6d2c95")
        wide.save(cls.scratch / "wide.png")
        cls.fonts = make_thumbnail.load_fonts(display=None)

    @classmethod
    def tearDownClass(cls):
        cls._scratch.cleanup()

    def compose(self, **changes) -> make_thumbnail.Result:
        data = {**base_manifest(), **changes}
        manifest = manifest_module.parse(data, self.scratch)
        result = make_thumbnail.compose(manifest, icons=self.icons, fonts=self.fonts)
        self.assert_sound(result)
        return result

    def assert_sound(self, result: make_thumbnail.Result) -> None:
        """Right size and mode, nothing off the canvas, no stamp on top of another."""
        self.assertEqual(result.image.size, (1200, 900))
        self.assertEqual(result.image.mode, "RGB")
        window = next(placement.box for placement in result.placements if placement.stamp == "window")
        leaves = [placement for placement in result.placements if placement.stamp not in CONTAINERS]
        for placement in result.placements:
            self.assertTrue(make_thumbnail.FRAME.contains(placement.box.inset(SLACK)), f"{placement} leaves the canvas")
        for placement in leaves:
            if placement.stamp != "cutout":
                self.assertTrue(window.contains(placement.box.inset(SLACK)), f"{placement} leaves the card")
        for first, second in itertools.combinations(leaves, 2):
            self.assertFalse(first.box.inset(SLACK).overlaps(second.box), f"{first} overlaps {second}")
        cutouts = [placement.box for placement in result.placements if placement.stamp == "cutout"]
        for box in cutouts:
            self.assertFalse(box.overlaps(window), "the cut-out runs under the card")

    def stamps(self, result: make_thumbnail.Result) -> list[str]:
        return [placement.stamp for placement in result.placements]

    # ---- layout edge cases

    def test_no_features(self):
        result = self.compose(features=[])
        self.assertNotIn("feature", self.stamps(result))

    def test_twelve_features(self):
        result = self.compose(features=features(12), cutout="tall.png")
        self.assertEqual(self.stamps(result).count("feature"), 12)
        self.assertEqual(result.warnings, [])

    def test_more_features_than_fit_are_summarised(self):
        result = self.compose(features=features(60), cutout="tall.png")
        self.assertIn("features-more", self.stamps(result))
        self.assertLess(self.stamps(result).count("feature"), 60)
        self.assertTrue(any("more" in warning for warning in result.warnings))

    def test_long_text_everywhere(self):
        self.compose(
            name="cassiopeia-the-extremely-long-named-avatar " * 3,
            variant="cassiopeia-adventure-tools-quest-fallback-edition-" * 4,
            version="12.345.678-beta.9+build.20261114.abcdef0123456789" * 2,
            performanceRank="VeryPoor",
            features=[{"id": f"f{index}", "label": "A label that goes on and on and on " * 4, "icon": "outfit"}
                      for index in range(12)],
            tags=[f"a-rather-long-tag-number-{index}" for index in range(30)] + ["x" * 400],
            url="https://github.com/CassidyPrather/cass-avatar/tree/main/" + "deep/" * 60,
            cutout="tall.png",
        )

    def test_missing_cutout_centres_the_card(self):
        result = self.compose(cutout=None, features=features(5))
        self.assertNotIn("cutout", self.stamps(result))
        window = next(placement.box for placement in result.placements if placement.stamp == "window")
        self.assertAlmostEqual((window.left + window.right) / 2, 600, delta=1)

    def test_missing_rank(self):
        result = self.compose(performanceRank=None, features=features(3))
        self.assertNotIn("rank", self.stamps(result))

    def test_every_rank(self):
        for rank in manifest_module.PERFORMANCE_RANKS:
            with self.subTest(rank=rank):
                self.assertIn("rank", self.stamps(self.compose(performanceRank=rank)))

    def test_only_the_required_fields(self):
        result = self.compose(performanceRank=None, features=[], tags=[], url=None, cutout=None)
        self.assertEqual(sorted(self.stamps(result)), ["name", "variant", "version", "window"])

    def test_missing_icon_is_skipped_with_a_warning(self):
        result = self.compose(features=[{"id": "ghost", "label": "Ghost", "icon": "no-such-icon"}])
        self.assertEqual(self.stamps(result).count("feature"), 1)
        self.assertTrue(any("no-such-icon" in warning for warning in result.warnings))

    def test_feature_without_an_icon_is_drawn_quietly(self):
        for icon in ("", None):
            with self.subTest(icon=icon):
                result = self.compose(features=[{"id": "plain", "label": "Plain", "icon": icon}])
                self.assertEqual(self.stamps(result).count("feature"), 1)
                self.assertEqual(result.warnings, [])

    def test_build_report_extras_are_ignored(self):
        # The Unity build passes its whole report: statistics ride along, and
        # the SDK's "None" rank means the avatar was not rated.
        result = self.compose(performanceRank="None", triangles=69420, droppedTags=["x"],
                              belowExcellent={"Bones": "Good"})
        self.assertNotIn("rank", self.stamps(result))

    def test_cutout_is_fitted_whole(self):
        for name in ("tall.png", "wide.png"):
            with self.subTest(cutout=name):
                result = self.compose(cutout=name)
                box = next(placement.box for placement in result.placements if placement.stamp == "cutout")
                self.assertTrue(make_thumbnail.AVATAR_FIT.contains(box.inset(SLACK)),
                                "the cut-out is cropped by its frame")
                visible = make_thumbnail.load_cutout(self.scratch / name)
                self.assertAlmostEqual(box.width / box.height, visible.width / visible.height, places=2)

    def test_display_font_falls_back_when_absent(self):
        fonts = make_thumbnail.load_fonts(display=self.scratch / "not-here.ttf")
        self.assertFalse(fonts.has_display)

    # ---- command line and input errors

    def run_cli(self, data: object, *extra: str) -> tuple[int, str, pathlib.Path]:
        manifest_path = self.scratch / "manifest.json"
        manifest_path.write_text(json.dumps(data), encoding="utf-8")
        out = self.scratch / "out" / "thumbnail.png"
        out.unlink(missing_ok=True)
        errors = io.StringIO()
        with contextlib.redirect_stderr(errors), contextlib.redirect_stdout(io.StringIO()):
            code = make_thumbnail.main(["--manifest", str(manifest_path), "--out", str(out),
                                        "--icons", str(self.icons), *extra])
        return code, errors.getvalue(), out

    def test_cli_writes_a_png(self):
        code, errors, out = self.run_cli({**base_manifest(), "features": features(4), "cutout": "tall.png"})
        self.assertEqual(code, 0, errors)
        with Image.open(out) as image:
            self.assertEqual(image.format, "PNG")
            self.assertEqual(image.size, (1200, 900))
            self.assertEqual(image.mode, "RGB")

    def test_cli_reports_a_missing_cutout_file(self):
        code, errors, out = self.run_cli({**base_manifest(), "cutout": "nowhere.png"})
        self.assertEqual(code, 1)
        self.assertIn("nowhere.png", errors)
        self.assertFalse(out.exists())

    def test_cli_reports_invalid_json(self):
        manifest_path = self.scratch / "broken.json"
        manifest_path.write_text("{ not json", encoding="utf-8")
        with contextlib.redirect_stderr(io.StringIO()) as errors:
            code = make_thumbnail.main(["--manifest", str(manifest_path), "--out", str(self.scratch / "x.png")])
        self.assertEqual(code, 1)
        self.assertIn("not valid JSON", errors.getvalue())

    def test_invalid_manifests_name_the_field(self):
        cases = {
            "name": {"name": None},
            "variant": {"variant": 7},
            "version": {"version": "  "},
            "performanceRank": {"performanceRank": "Great"},
            "features": {"features": "outfit"},
            "features[0]": {"features": [{"id": "a", "icon": "outfit"}]},
            "features[1]": {"features": [{"id": "a", "label": "A", "icon": "outfit"}, "flight"]},
            "icon": {"features": [{"id": "a", "label": "A", "icon": "../secret.png"}]},
            "tags": {"tags": ["ai", 3]},
            "url": {"url": ["github.com"]},
            "cutout": {"cutout": 5},
            "did you mean": {"performancerank": "Good"},
        }
        for expected, changes in cases.items():
            with self.subTest(field=expected):
                with self.assertRaises(ManifestError) as raised:
                    manifest_module.parse({**base_manifest(), **changes}, self.scratch)
                self.assertIn(expected, str(raised.exception))
        with self.assertRaises(ManifestError):
            manifest_module.parse(["not", "an", "object"], self.scratch)

    def test_sample_manifest_is_valid(self):
        sample = pathlib.Path(__file__).resolve().parent / "sample-manifest.json"
        manifest = manifest_module.load(sample)
        self.assertEqual(len(manifest.features), 12)


if __name__ == "__main__":
    unittest.main()
