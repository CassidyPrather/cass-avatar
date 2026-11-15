"""The thumbnail manifest: what one avatar variant wants on its picture.

The schema is documented in README.md. The Unity build hands over its whole
build report, so keys this tool does not know are ignored; the keys it does
know are checked strictly, because a wrong type that was quietly skipped
would publish a thumbnail that is silently missing its icons.
"""

import dataclasses
import json
import pathlib
import re

_KEYS = ("icons", "cutout")
# Icon names are file stems in the shared Icons/ directory, which are
# kebab-case; anything else (a path, an extension) is a mistake in the manifest.
_ICON_NAME = re.compile(r"[a-z0-9]+(-[a-z0-9]+)*")


class ManifestError(ValueError):
    """The manifest is unusable; the message says which field and why."""


@dataclasses.dataclass(frozen=True)
class Manifest:
    # One per group of like features, in the order they are drawn.
    icons: tuple[str, ...] = ()
    # Absolute once loaded: a relative path in the file is relative to the file.
    cutout: pathlib.Path | None = None


def _misspelt(data: dict, known: tuple[str, ...], where: str) -> None:
    """Unknown keys are fine, except one that is a known key in the wrong case.

    `Icons` beside a schema that says `icons` is never extra data; ignoring
    it would drop every icon without a word.
    """
    by_folded = {key.lower(): key for key in known}
    for key in data:
        intended = by_folded.get(str(key).lower())
        if intended is not None and key != intended:
            raise ManifestError(f'{where}: unknown key "{key}"; did you mean "{intended}"?')


def parse(data: object, base: pathlib.Path) -> Manifest:
    """Validates decoded JSON. `base` is the directory a relative `cutout` is resolved against."""
    if not isinstance(data, dict):
        raise ManifestError("manifest: the top level must be a JSON object")
    _misspelt(data, _KEYS, "manifest")

    icons = data.get("icons") or []
    if not isinstance(icons, list):
        raise ManifestError('manifest: "icons" must be a list of icon names')
    seen: list[str] = []
    for index, icon in enumerate(icons):
        if not isinstance(icon, str) or not _ICON_NAME.fullmatch(icon.strip()):
            raise ManifestError(f'manifest: icons[{index}] must be a kebab-case icon name such as "face-tracking" '
                                f"(no path, no extension); got {icon!r}")
        # The same icon twice says nothing the first one did not.
        if icon.strip() not in seen:
            seen.append(icon.strip())

    cutout = data.get("cutout")
    if cutout is not None and not isinstance(cutout, str):
        raise ManifestError(f'manifest: "cutout" must be a string or null, got {type(cutout).__name__}')
    cutout = (cutout or "").strip()
    return Manifest(icons=tuple(seen), cutout=(base / cutout).resolve() if cutout else None)


def load(path: pathlib.Path) -> Manifest:
    try:
        # utf-8-sig: .NET writers may put a byte-order mark in front of the JSON.
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except OSError as error:
        raise ManifestError(f"{path}: cannot read manifest ({error.strerror})") from error
    except json.JSONDecodeError as error:
        raise ManifestError(f"{path}: not valid JSON (line {error.lineno}: {error.msg})") from error
    return parse(data, path.resolve().parent)
