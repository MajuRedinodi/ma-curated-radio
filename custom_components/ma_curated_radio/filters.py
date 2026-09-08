"""Track and artist filtering rules.

Ported from the YAML/Jinja implementation this integration replaces. The
comparisons are kept identical so a batch built here matches one the
blueprint would have built from the same inputs, with one deliberate
exception documented on :func:`is_live`.
"""

from __future__ import annotations

import random
import re
from datetime import datetime
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


def clean_similar_artists(
    candidates: list[tuple[str, float]], seed_artist: str
) -> list[tuple[str, float]]:
    """Drop empties, the seed artist itself, and collaboration credits.

    Takes and returns (name, match) pairs so the ranking survives to the
    point where artists are actually chosen.
    """
    seen: set[str] = set()
    cleaned: list[tuple[str, float]] = []
    for name, match in candidates:
        candidate = (name or "").strip()
        if not candidate or candidate == seed_artist:
            continue
        if any(marker in candidate for marker in COLLAB_MARKERS):
            continue
        key = candidate.lower()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append((candidate, match))
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


def weighted_sample(
    candidates: list[tuple[str, float]], count: int, exponent: float
) -> list[str]:
    """Choose ``count`` artists, biased toward the best-matching ones.

    Last.fm ranks similar artists by a match score, and that ranking is a
    decent proxy for how well known an artist is. Sampling uniformly from
    a deep pool, which is what this used to do, is why batches filled up
    with defensible neighbours nobody had heard of.

    ``exponent`` sets the bias: 0 is a flat shuffle, higher values crowd
    selection toward the top of the list. Keep it low. Match scores fall
    away steeply, so an exponent much above 2 stops the tail appearing at
    all rather than merely making it rare, which would defeat the point of
    drawing from a deep pool. Uses the Efraimidis-Spirakis one-pass
    method, so a whole batch is drawn in a single sort without
    replacement.
    """
    if count <= 0 or not candidates:
        return []

    keyed: list[tuple[float, str]] = []
    for name, match in candidates:
        weight = max(match, 0.0) ** exponent if exponent else 1.0
        # A zero weight would divide by zero and can never be picked;
        # a tiny one keeps it last in line rather than absent.
        weight = max(weight, 1e-9)
        keyed.append((random.random() ** (1.0 / weight), name))

    keyed.sort(key=lambda pair: pair[0], reverse=True)
    return [name for _, name in keyed[:count]]


def freshness(released: datetime | None, window_days: int, now: datetime) -> float:
    """How new a track is, 1.0 for today down to 0.0 at the window edge.

    Outside the window, or with no release date at all, this is zero, so a
    provider that does not report release dates simply never triggers any
    promotion.
    """
    if released is None or window_days <= 0:
        return 0.0
    age_days = (now - released).days
    if age_days < 0 or age_days > window_days:
        return 0.0
    return 1.0 - (age_days / window_days)


def hotness(
    released: datetime | None, popularity: int, window_days: int, now: datetime
) -> float:
    """Score a track for being both new and genuinely popular.

    Provider top-track rankings are cumulative, so a song released last
    month sits below five years of catalogue however big it is right now.
    This is what lifts it: a track has to be recent *and* popular to be
    promoted, so a new flop stays where the provider put it.

    Zero for anything old, unpopular, or missing metadata, which leaves
    the provider's own ordering untouched.
    """
    if popularity <= 0:
        return 0.0
    return freshness(released, window_days, now) * min(popularity, 100) / 100


def credits_artist(credited: list[str], wanted: str) -> bool:
    """Return True if ``wanted`` is actually one of a track's artists.

    Music Assistant's search matches loosely, so asking for Madonna can
    return "Madonna Madonna" by Rosanna Rocci: the right words, the wrong
    record. Collaborations are fine and common ("Lady Gaga/Colby O'Donis"),
    so this asks whether the artist appears among the credits at all,
    not whether they are the only name on it.
    """
    target = wanted.strip().lower()
    if not target:
        return True
    return any(name.strip().lower() == target for name in credited)
