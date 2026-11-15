"""The drawing surface: wirenook colours and a supersampled canvas.

Layout code works in the thumbnail's own 1200x900 units. Pillow does not
antialias shapes, so the canvas is really SUPERSAMPLE times larger and is
scaled down once at the end; every method here takes and returns logical
units and does the multiplication itself.
"""

import dataclasses

from PIL import Image, ImageDraw

SUPERSAMPLE = 2

# https://wirenook.net/style/ tokens; the same values as the shared
# Textures/wirenook-palette.toml in net.wirenook.assets.
SKY = "#5aa8dc"
ICE = "#d7fbff"
CYAN = "#73f4ff"
BLUE = "#365fc6"
VIOLET = "#6d2c95"
LAVENDER = "#b9a8ff"
PINK = "#ffd6f5"
MAGENTA = "#ff00e6"
INK = "#271452"
PANEL = "#d8f7ff"
PANEL_STRONG = "#e7fcff"
ORANGE = "#ff6600"
WHITE = "#ffffff"


def rgba(colour: str, alpha: float = 1.0) -> tuple[int, int, int, int]:
    red, green, blue = (int(colour[index : index + 2], 16) for index in (1, 3, 5))
    return red, green, blue, round(alpha * 255)


@dataclasses.dataclass(frozen=True)
class Box:
    left: float
    top: float
    right: float
    bottom: float

    @property
    def width(self) -> float:
        return self.right - self.left

    @property
    def height(self) -> float:
        return self.bottom - self.top

    def inset(self, amount: float) -> "Box":
        return Box(self.left + amount, self.top + amount, self.right - amount, self.bottom - amount)

    def overlaps(self, other: "Box") -> bool:
        return (self.left < other.right and other.left < self.right
                and self.top < other.bottom and other.top < self.bottom)

    def contains(self, other: "Box") -> bool:
        return (self.left <= other.left and self.top <= other.top
                and other.right <= self.right and other.bottom <= self.bottom)


class Painter:
    def __init__(self, width: int, height: int):
        self.size = (width, height)
        self.image = Image.new("RGB", (width * SUPERSAMPLE, height * SUPERSAMPLE), SKY)
        # "RGBA" on an RGB image makes fills with alpha blend instead of replace.
        self.draw = ImageDraw.Draw(self.image, "RGBA")

    @staticmethod
    def px(value: float) -> int:
        return round(value * SUPERSAMPLE)

    def _box(self, box: Box) -> tuple[int, int, int, int]:
        # Pillow's far edges are inclusive; without the -1 neighbours overlap by a pixel.
        return self.px(box.left), self.px(box.top), self.px(box.right) - 1, self.px(box.bottom) - 1

    # ---- shapes

    def rect(self, box: Box, fill=None, outline=None, width: float = 1, radius: float = 0) -> None:
        self.draw.rounded_rectangle(self._box(box), radius=self.px(radius), fill=fill,
                                    outline=outline, width=self.px(width))

    def ellipse(self, box: Box, fill=None, outline=None, width: float = 1) -> None:
        self.draw.ellipse(self._box(box), fill=fill, outline=outline, width=self.px(width))

    def line(self, points: list[tuple[float, float]], fill, width: float = 1) -> None:
        self.draw.line([(self.px(x), self.px(y)) for x, y in points], fill=fill,
                       width=max(1, self.px(width)), joint="curve")

    def polygon(self, points: list[tuple[float, float]], fill=None) -> None:
        self.draw.polygon([(self.px(x), self.px(y)) for x, y in points], fill=fill)

    def paste(self, image: Image.Image, box: Box) -> None:
        """Scales `image` to exactly fill `box` and composites it by its alpha."""
        size = (max(1, self.px(box.width)), max(1, self.px(box.height)))
        scaled = image.convert("RGBA").resize(size, Image.LANCZOS)
        self.image.paste(scaled, (self.px(box.left), self.px(box.top)), scaled)

    def overlay(self, layer: Image.Image) -> None:
        """Composites a full-canvas RGBA layer, at any resolution, over the picture."""
        if layer.size != self.image.size:
            layer = layer.resize(self.image.size, Image.BICUBIC)
        self.image.paste(layer, (0, 0), layer)

    # ---- output

    def finish(self) -> Image.Image:
        return self.image.resize(self.size, Image.LANCZOS)
