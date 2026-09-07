"""Track and artist filtering rules.

Ported from the YAML/Jinja implementation this integration replaces. The
comparisons are kept identical so a batch built here matches one the
blueprint would have built from the same inputs, with one deliberate
exception documented on :func:`is_live`.
"""

from __future__ import annotations

import re
from typing import Final

# Word boundaries for the live-version check: anything that is not a letter
# or a digit separates words, so parentheses and dashes do not glue a
# keyword to its punctuation.
_WORDS = re.compile(r"[^a-z0-9]+")

HOLIDAY_TOKENS: Final = (
    "christmas",
    "xmas",
    "santa",
    "jingle",
    "yuletide",
    "noel",
)

# Last.fm returns collaboration credits as if they were standalone artists
# ("Lady Gaga, Bruno Mars"). Searching those mostly yields cover/live/piano
# versions of the one collab song rather than real additional variety.
COLLAB_MARKERS: Final = (",", " & ")


def base_title(name: str) -> str:
    """Normalise a track title for duplicate detection.

    Lowercased and truncated at the first ``" - "`` or ``"("`` so that
    "Song - Remastered 2011" and "Song (Radio Edit)" collapse onto "song".
    """
    return name.split(" - ", maxsplit=1)[0].split("(", maxsplit=1)[0].strip().lower()


def is_live(name: str, version: str) -> bool:
    """Return True for live recordings.

    Substring match on the version field, standalone-word match on the title
    so "Alive" and "Living on a Prayer" are left alone.

    Tokenising on non-alphanumerics rather than whitespace is a deliberate
    departure from the YAML this replaces: splitting on spaces alone left
    "Song (Live)" as the token "(live)", so the most common form of the
    thing this filter exists to catch only got caught when the provider
    also populated the version field.
    """
    return "live" in version.lower() or "live" in _WORDS.split(name.lower())


def is_holiday(name: str, version: str, album: str) -> bool:
    """Return True for holiday content, regardless of season.

    Checks title, version and album name together: a provider's popularity
    ranking will happily surface an artist's Christmas album in September.
    """
    haystack = f"{name} {version} {album}".lower()
    return any(token in haystack for token in HOLIDAY_TOKENS)


def clean_similar_artists(names: list[str], seed_artist: str) -> list[str]:
    """Drop empties, the seed artist itself, and collaboration credits."""
    seen: set[str] = set()
    cleaned: list[str] = []
    for name in names:
        candidate = (name or "").strip()
        if not candidate or candidate == seed_artist:
            continue
        if any(marker in candidate for marker in COLLAB_MARKERS):
            continue
        key = candidate.lower()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(candidate)
    return cleaned


def matches_provider(uri: str, provider_filter: str) -> bool:
    """Return True if a media URI is allowed by the provider filter.

    The filter is a comma-separated list of URI scheme prefixes (e.g.
    ``tidal`` or ``tidal,qobuz``). Empty means allow every provider.
    """
    if not provider_filter.strip():
        return True
    allowed = [p.strip().lower() for p in provider_filter.split(",") if p.strip()]
    scheme = uri.split("://", 1)[0].lower()
    return any(scheme == p or scheme.startswith(p) for p in allowed)


def interleave(lists: list[list[str]]) -> list[str]:
    """Round-robin interleave, one item per list per pass.

    Keeps a single artist from playing twice in a row unless every other
    artist's list has already run out.
    """
    if not lists:
        return []
    ordered: list[str] = []
    for index in range(max(len(items) for items in lists)):
        for items in lists:
            if index < len(items):
                ordered.append(items[index])
    return ordered
