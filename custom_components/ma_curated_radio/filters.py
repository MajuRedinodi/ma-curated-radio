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

# Spoken-word and filler entries that a genuine top-tracks ranking will
# surface because they are recent and getting plays, but which nobody
# wants queued. Duration catches most of it; these catch the long ones.
NON_SONG_MARKERS: Final = (
    "track by track",
    "commentary",
    "interlude",
    "skit",
    "voice memo",
    "spoken word",
)


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


def sequence(lists: list[list[str]], max_consecutive: int = 2) -> list[str]:
    """Order tracks across artists, capping how many play back to back.

    At each position it takes from whichever artist has the most left,
    which produces plain round-robin when every artist contributes the same
    number of tracks, and spreads the surplus when one contributes more (a
    seed-heavy "artist radio" batch). An artist that has just played
    ``max_consecutive`` times in a row is skipped over.

    The cap is a preference, not a guarantee: when only the blocked
    artist has tracks left, playing them beats dropping them.
    """
    pools = [list(items) for items in lists if items]
    if not pools:
        return []

    ordered: list[str] = []
    last: int | None = None
    run = 0

    while any(pools):
        pick = None
        for index, pool in enumerate(pools):
            if not pool or (index == last and run >= max_consecutive):
                continue
            if pick is None or len(pool) > len(pools[pick]):
                pick = index
        if pick is None:
            # Everything else is exhausted; the tail is one artist's.
            pick = next(i for i, pool in enumerate(pools) if pool)

        ordered.append(pools[pick].pop(0))
        run = run + 1 if pick == last else 1
        last = pick

    return ordered


def is_too_short(duration: int, minimum: int) -> bool:
    """Return True for anything too brief to be a song.

    Commentary tracks, interludes and album skits run well under two
    minutes. A duration of zero means the provider did not say, in which
    case the track gets the benefit of the doubt.
    """
    return 0 < duration < minimum


def is_non_song(name: str, version: str) -> bool:
    """Return True for commentary and filler that runs long enough to pass.

    Taylor Swift's "Track by Track" entries are the motivating case: they
    are her talking about each song, they chart alongside the songs, and a
    real top-tracks ranking puts them right at the top.
    """
    haystack = f"{name} {version}".lower()
    return any(marker in haystack for marker in NON_SONG_MARKERS)
