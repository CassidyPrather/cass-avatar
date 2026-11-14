"""The thumbnail manifest: what one avatar variant wants printed on its card.

The schema is documented in README.md. The Unity build hands over its whole
build report, so keys this tool does not know are ignored; the keys it does
know are checked strictly, because a wrong type that was quietly skipped
would publish a thumbnail that is silently missing its badge.
"""

import dataclasses
import json
import pathlib
import re

# VRChat's five overall performance ranks, spelt as the SDK's enum spells them.
PERFORMANCE_RANKS = ("Excellent", "Good", "Medium", "Poor", "VeryPoor")
# The same enum's value for "not rated"; the build writes it when the SDK has
# no statistics, and it means the same as leaving the rank out.
UNRATED = "None"

_KEYS = ("name", "variant", "version", "performanceRank", "features", "tags", "url", "cutout")
_FEATURE_KEYS = ("id", "label", "icon")
# Icon names are file stems in the shared Icons/ directory, which are
# kebab-case; anything else (a path, an extension) is a mistake in the manifest.
_ICON_NAME = re.compile(r"[a-z0-9]+(-[a-z0-9]+)*")


class ManifestError(ValueError):
    """The manifest is unusable; the message says which field and why."""


@dataclasses.dataclass(frozen=True)
class Feature:
    id: str
    label: str
    # None: the feature has no icon of its own and gets the placeholder tile.
    icon: str | None


@dataclasses.dataclass(frozen=True)
class Manifest:
    name: str
    variant: str
    version: str
    performance_rank: str | None = None
    features: tuple[Feature, ...] = ()
    tags: tuple[str, ...] = ()
    url: str | None = None
    # Absolute once loaded: a relative path in the file is relative to the file.
    cutout: pathlib.Path | None = None


def _misspelt(data: dict, known: tuple[str, ...], where: str) -> None:
    """Unknown keys are fine, except one that is a known key in the wrong case.

    `performancerank` beside a schema that says `performanceRank` is never
    extra data; ignoring it would drop the badge without a word.
    """
    by_folded = {key.lower(): key for key in known}
    for key in data:
        intended = by_folded.get(str(key).lower())
        if intended is not None and key != intended:
            raise ManifestError(f'{where}: unknown key "{key}"; did you mean "{intended}"?')


def _required(data: dict, key: str, where: str) -> str:
    value = data.get(key)
    if value is None:
        raise ManifestError(f'{where}: "{key}" is required')
    if not isinstance(value, str):
        raise ManifestError(f'{where}: "{key}" must be a string, got {type(value).__name__}')
    if not value.strip():
        raise ManifestError(f'{where}: "{key}" must not be empty')
    return value.strip()


def _optional(data: dict, key: str, where: str) -> str | None:
    """A string, or None when the key is absent, null or blank."""
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ManifestError(f'{where}: "{key}" must be a string or null, got {type(value).__name__}')
    return value.strip() or None


def _feature(entry: object, where: str) -> Feature:
    if not isinstance(entry, dict):
        raise ManifestError(f"{where}: must be an object with id, label and icon")
    _misspelt(entry, _FEATURE_KEYS, where)
    icon = _optional(entry, "icon", where)
    if icon is not None and not _ICON_NAME.fullmatch(icon):
        raise ManifestError(f'{where}: "icon" must be a kebab-case icon name such as "face-tracking" '
                            f"(no path, no extension); got {icon!r}")
    return Feature(_required(entry, "id", where), _required(entry, "label", where), icon)


def parse(data: object, base: pathlib.Path) -> Manifest:
    """Validates decoded JSON. `base` is the directory a relative `cutout` is resolved against."""
    if not isinstance(data, dict):
        raise ManifestError("manifest: the top level must be a JSON object")
    _misspelt(data, _KEYS, "manifest")

    rank = _optional(data, "performanceRank", "manifest")
    if rank == UNRATED:
        rank = None
    if rank is not None and rank not in PERFORMANCE_RANKS:
        raise ManifestError(f'manifest: "performanceRank" must be null or one of '
                            f'{", ".join(PERFORMANCE_RANKS)}; got {rank!r}')

    features = data.get("features") or []
    if not isinstance(features, list):
        raise ManifestError('manifest: "features" must be a list')
    tags = data.get("tags") or []
    if not isinstance(tags, list) or not all(isinstance(tag, str) and tag.strip() for tag in tags):
        raise ManifestError('manifest: "tags" must be a list of non-empty strings')

    cutout = _optional(data, "cutout", "manifest")
    return Manifest(
        name=_required(data, "name", "manifest"),
        variant=_required(data, "variant", "manifest"),
        version=_required(data, "version", "manifest"),
        performance_rank=rank,
        features=tuple(_feature(entry, f"features[{index}]") for index, entry in enumerate(features)),
        tags=tuple(tag.strip() for tag in tags),
        url=_optional(data, "url", "manifest"),
        cutout=(base / cutout).resolve() if cutout else None,
    )


def load(path: pathlib.Path) -> Manifest:
    try:
        # utf-8-sig: .NET writers may put a byte-order mark in front of the JSON.
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except OSError as error:
        raise ManifestError(f"{path}: cannot read manifest ({error.strerror})") from error
    except json.JSONDecodeError as error:
        raise ManifestError(f"{path}: not valid JSON (line {error.lineno}: {error.msg})") from error
    return parse(data, path.resolve().parent)
