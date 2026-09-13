"""Track and artist filtering rules.

Ported from the YAML/Jinja implementation this integration replaces. The
comparisons are kept identical so a batch built here matches one the
blueprint would have built from the same inputs, with one deliberate
exception documented on :func:`is_live`.
"""

from __future__ import annotations

import random
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final

# Word boundaries for the live-version check: anything that is not a letter
# or a digit separates words, so parentheses and dashes do not glue a
# keyword to its punctuation.
_WORDS = re.compile(r"[^a-z0-9]+")

# Words that mark a recording as live. "Live" alone missed The Band's
# "Helpless (Concert Version)", from The Last Waltz, which reached a
# queue with live filtering switched on. Checked as whole words in a
# title so "Alive" and "Living on a Prayer" survive, and as substrings
# in the version field, which is already terse and deliberate.
LIVE_MARKERS: Final = (
    "live",
    "concert",
    "unplugged",
)

# Words that mark a reworking rather than the record people mean, judged
# the same way as live versions.
REMIX_MARKERS: Final = ("remix", "rmx")

# Club and dance reworkings, which are remixes under another name. "Mix"
# alone is useless: half the catalogue is an "Album Mix" or a "Single Mix"
# of the record everybody knows.
REMIX_PHRASES: Final = (
    "club mix",
    "dance mix",
    "extended mix",
    "dub mix",
    "house mix",
    "12\" mix",
)

# Holiday content, checked as substrings against title, version and
# album together.
#
# Mostly phrases rather than words, because the single words that would
# catch these songs are exactly the words ordinary songs use. "Winter"
# would take Vivaldi and Tori Amos, "snow" would take Snow Patrol,
# "holiday" would take Madonna and Green Day and Lindsey Buckingham's
# "Holiday Road", and "bells" would take Chime Bell and Hell's Bells.
# Phrases carry no such risk: nothing that is not a Christmas record is
# called "Winter Wonderland".
#
# The list is unbounded by nature and will always miss something. It is
# ordered roughly by how often a thing turns up in a mainstream
# artist's back catalogue, which is where the misses actually hurt: a
# soul singer's one Christmas single sitting in an August batch.
HOLIDAY_TOKENS: Final = (
    # The obvious ones.
    "christmas",
    "xmas",
    "santa",
    "yuletide",
    "navidad",
    # Standards whose titles never say Christmas. Emeli Sandé's "Winter
    # Wonderland", on "The Best Man Holiday" soundtrack, reached a
    # September queue past every word above.
    "winter wonderland",
    "let it snow",
    "sleigh ride",
    "sleigh bells",
    "jingle",
    "silver bells",
    "frosty the snowman",
    "rudolph",
    "holly jolly",
    "mistletoe",
    "auld lang syne",
    "baby it's cold outside",
    "baby its cold outside",
    # Carols.
    "silent night",
    "holy night",
    "the first noel",
    "deck the hall",
    "drummer boy",
    "away in a manger",
    "come all ye faithful",
    "hark the herald",
    "god rest ye merry",
    "god rest you merry",
    "good king wenceslas",
    "carol of the bells",
    "what child is this",
    "ding dong merrily",
    "twelve days of",
    "we three kings",
    "o christmas tree",
    "greensleeves",
)

# Last.fm returns collaboration credits as if they were standalone artists
# ("Lady Gaga, Bruno Mars"). Searching those mostly yields cover/live/piano
# versions of the one collab song rather than real additional variety.
COLLAB_MARKERS: Final = (",", " & ")

# Below this many artists a pool has no meaningful median, and dropping
# one of three neighbours costs more than the outlier does.
MIN_POOL_FOR_FLOOR: Final = 4

# Tier labels. Defined here rather than in const.py because this module
# deliberately imports nothing from Home Assistant or from the rest of
# the integration, so its logic can be tested without either.
TIER_POWER: Final = "P"
TIER_SECONDARY: Final = "S"
TIER_DEEP: Final = "D"

# The rotation an hour is built to. Terciles supply each tier equally, so
# a pattern asking for more Power than that spends them early and leaves
# the closing third with nothing: measured on a real batch, a Power-heavy
# pattern left its last six tracks entirely Secondary and Deep. Power
# first so an hour opens strongly, then Deep while that opening is still
# in the ear, then Secondary to recover.
TIER_PATTERN: Final = [TIER_POWER, TIER_DEEP, TIER_SECONDARY]

# Spoken-word and filler entries that a genuine top-tracks ranking will
# surface because they are recent and getting plays, but which nobody
# wants queued. Duration catches most of it; these catch the long ones.
# Imitations, not covers. A real cover is welcome and often the best
# thing in a batch, so nothing here matches on "cover" or "version":
# these phrases appear only on records made to sound like someone else.
# Tidal surfaces them, and searching for Tom Petty returned one.
IMITATION_MARKERS: Final = (
    "karaoke",
    "made popular by",
    "in the style of",
    "originally performed by",
    "tribute to",
    "backing track",
)

NON_SONG_MARKERS: Final = (
    "track by track",
    "commentary",
    "interlude",
    "skit",
    "voice memo",
    "spoken word",
)


# Tempo and movement markings, which classical releases append to a
# title with a comma. Deliberately a closed list rather than "split on
# the comma", because that would collapse "Hello, Goodbye" onto "Hello".
TEMPO_MARKINGS: Final = (
    "adagio",
    "allegretto",
    "allegro",
    "andante",
    "grave",
    "largo",
    "larghetto",
    "lento",
    "moderato",
    "presto",
    "vivace",
)

# Punctuation that carries no meaning in a title, so "No. 5" and "No 5"
# are the same piece.
_PUNCTUATION = re.compile(r"[.,;:'\"]")


def base_title(name: str) -> str:
    """Normalise a track title for duplicate detection.

    Truncated at the first ``" - "`` or ``"("`` so that "Song -
    Remastered 2011" and "Song (Radio Edit)" collapse onto "song", then
    stripped of a trailing tempo marking and of punctuation.

    The last two are for classical, where the same piece arrives as
    "Hungarian Dance No 5" and "Hungarian Dance No. 5, Allegro molto".
    Both reached one queue together.

    Also truncated at " / ", for the medley titles a provider gives the
    same record under. Chicago's "Hard to Say I'm Sorry / Get Away" and
    "Hard to Say I'm Sorry" are one song, and both played in one batch.
    """
    title = (
        name.split(" - ", maxsplit=1)[0]
        .split(" / ", maxsplit=1)[0]
        .split("(", maxsplit=1)[0]
    )
    head, sep, tail = title.rpartition(",")
    if sep and tail.strip().lower().startswith(TEMPO_MARKINGS):
        title = head
    return _PUNCTUATION.sub("", title).strip().lower()


def is_demo(name: str, version: str, album: str) -> bool:
    """Return True for demos and rough mixes.

    An unfinished recording, which nobody asking for a band's hits wants.
    A search for .38 Special handed back "F2D" from an album called "Demo
    2", and it opened an hour of their neighbours' biggest records.

    Whole words only, in the title, version and album, so "Demolition
    Man" and "Democracy" are left alone.
    """
    text = " ".join((name, version, album)).lower()
    words = set(_WORDS.split(text))
    return bool(words & {"demo", "demos"}) or "rough mix" in text


def is_remix(name: str, version: str) -> bool:
    """Return True for remixes and club mixes.

    Off by default, because a remix is sometimes the version people know.
    On, it is for a station whose era the remix is not from: Elton John and
    Dua Lipa's "Cold Heart" arrived in an hour of seventies rock, which is
    right for the artist and wrong for everything around it.

    Whole words in the title, substrings in the version field, the same way
    live versions are judged.
    """
    haystack = version.lower()
    words = set(_WORDS.split(name.lower()))
    if bool(words & {"remix", "rmx", "remixes"}) or any(
        marker in haystack for marker in REMIX_MARKERS
    ):
        return True
    text = f"{name} {version}".lower()
    return any(phrase in text for phrase in REMIX_PHRASES)


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
    haystack = version.lower()
    words = set(_WORDS.split(name.lower()))
    return any(
        marker in haystack or marker in words for marker in LIVE_MARKERS
    )


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


def tier_of(
    sized: list[tuple[str, list[str], int]],
    decay: float,
    rank: Mapping[str, int] | None = None,
) -> dict[str, str]:
    """Label each track Power, Secondary or Deep, relative to this pool.

    Scores a track as its artist's size decayed by its position in that
    artist's own ordering, so no per-track lookup is needed: the provider
    already ranks an artist's tracks by relevance, and one listener count
    per artist is enough. Checked against real per-track counts on a nine
    artist pool it agreed 66% of the time against 33% for chance, and
    confused Power with Deep exactly once in 66 tracks. Adjacent
    misreadings are cheap; inversions would not be.

    Terciles of the pool in front of it, never absolute numbers. A fixed
    threshold tuned on rock would mark an entire country station as deep
    cuts, because Last.fm undercounts the genre by about ten times.

    ``rank`` gives each track's position in its artist's ordering when that
    differs from its position in this batch; see ``reach_of``.
    """
    # An unknown size means the lookup missed, not that the artist is
    # tiny. Scoring it as zero would put every one of its tracks in the
    # Deep tier, and the artist most likely to be missing is the one just
    # picked, so the station would file what you asked for as its weakest
    # material. Treat unknown as typical instead.
    known = sorted(size for _, _, size in sized if size > 0)
    fallback = known[len(known) // 2] if known else 1

    scored: list[tuple[str, float]] = []
    for _, uris, size in sized:
        weight = size if size > 0 else fallback
        for index, uri in enumerate(uris):
            position = rank.get(uri, index) if rank else index
            scored.append((uri, weight * (decay**position)))
    scored.sort(key=lambda pair: pair[1], reverse=True)
    third = len(scored) // 3
    tiers: dict[str, str] = {}
    for index, (uri, _) in enumerate(scored):
        tiers[uri] = TIER_POWER if index < third else (
            TIER_SECONDARY if index < third * 2 else TIER_DEEP
        )
    return tiers


def reach_of(
    sized: list[tuple[str, list[str], int]],
    decay: float,
    rank: Mapping[str, int] | None = None,
) -> dict[str, int]:
    """Estimated audience for each track, on an absolute scale.

    An artist's own audience, decayed by how far down that artist's
    ordering the track sits. The same score the tiering sorts on, kept
    unnormalised so batches can be compared with each other: tiers are
    relative to their own pool and say nothing across pools, while this
    does.

    Unknown artist sizes take the pool median, for the same reason they
    do when tiering: a lookup miss is not evidence that an artist is
    small.

    ``rank`` is each track's position in its artist's ordering, when that
    differs from its position in this batch. It does on every refill:
    songs already played are excluded before a batch is chosen, so
    counting positions within the batch scores an artist's fourth song
    as though it were their first. A refill of the same artists' deeper
    songs then reported exactly the same median reach as the hour of
    hits before it.
    """
    known = sorted(size for _, _, size in sized if size > 0)
    fallback = known[len(known) // 2] if known else 0
    reach: dict[str, int] = {}
    for _, uris, size in sized:
        weight = size if size > 0 else fallback
        for index, uri in enumerate(uris):
            position = rank.get(uri, index) if rank else index
            reach[uri] = int(weight * (decay**position))
    return reach


def sequence_tiered(
    lists: list[list[str]],
    tiers: dict[str, str],
    pattern: list[str],
    *,
    max_consecutive: int = 2,
    leading: int | None = None,
    length: int = 0,
) -> list[str]:
    """Order tracks to a tier pattern rather than by plain round-robin.

    Round-robin plays every artist's biggest track, then every artist's
    second, so an hour front-loads its hits and decays. Measured on a
    real nine artist batch the last third averaged 105k listeners against
    768k for the first, with six successively weaker tracks in a row.
    Rotating tiers instead halved the worst run and nearly doubled the
    closing third.

    ``length`` stops early, which is what separates how deep a batch may
    reach from how long it plays. Drawing three tracks an artist and
    playing all of them is a two hour batch that reseeds half as often;
    drawing three and playing nineteen is the same hour as before, with
    the third tracks landing in the slots that want something deeper.
    Zero plays everything drawn.

    The pattern is a preference. When no artist can supply the tier a
    slot wants, the best available plays anyway: an hour with a slightly
    wrong texture beats an hour with a hole in it.
    """
    pools = [list(items) for items in lists if items]
    if not pools:
        return []

    capped = 0 < length < sum(len(pool) for pool in pools)
    wanted = length if capped else sum(len(pool) for pool in pools)

    ordered: list[str] = []
    played: dict[int, int] = {}
    last: int | None = leading
    run = 1 if leading is not None else 0

    while len(ordered) < wanted and any(pools):
        want = pattern[len(ordered) % len(pattern)]
        pick = None
        best: tuple[int, ...] | None = None
        for index, pool in enumerate(pools):
            if not pool or (index == last and run >= max_consecutive):
                continue
            fit = 0 if tiers.get(pool[0]) == want else 1
            # Uncapped, every pool has to be emptied, so take from the
            # fullest to avoid stranding one artist's tracks at the end.
            # Capped, there is no such obligation, and preferring the
            # fullest would simply hand the extra slots to whichever
            # artist drew most, which is the seed. Spread by who has
            # played least instead.
            key = (
                (fit, played.get(index, 0), -len(pool))
                if capped
                else (fit, -len(pool))
            )
            if best is None or key < best:
                best, pick = key, index
        if pick is None:
            pick = next(i for i, pool in enumerate(pools) if pool)

        ordered.append(pools[pick].pop(0))
        played[pick] = played.get(pick, 0) + 1
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
    return any(
        marker in haystack for marker in (*NON_SONG_MARKERS, *IMITATION_MARKERS)
    )


def drop_outliers(
    sized: list[tuple[str, int]], floor_pct: int
) -> tuple[list[str], list[tuple[str, int]]]:
    """Drop artists far smaller than the rest of their own pool.

    Returns the artists to keep and the ones dropped with their sizes.

    Measured against the pool's own median, never against the seed and
    never against a fixed number. Both alternatives were tried against
    four observed pools and both fail:

    * A fixed threshold cannot work across genres. Last.fm undercounts
      country by roughly an order of magnitude, so Hank Williams Jr.'s
      "Family Tradition" has fewer listeners than an obscure 1973 duo's
      best track. Any absolute floor tuned on rock erases country.
    * The seed is a poor reference too. Hank Jr. was the smallest artist
      in his own pool at 10% of the biggest, and that hour was good.

    What actually marks a bad neighbour is sitting far below its own
    neighbourhood. Christine McVie at 2% of her pool's median was the one
    real defect across four pools; the next lowest anywhere was 12%, so
    the default sits in open space rather than on a cliff edge.
    """
    if floor_pct <= 0 or len(sized) < MIN_POOL_FOR_FLOOR:
        return [name for name, _ in sized], []
    known = sorted(size for _, size in sized if size > 0)
    if not known:
        return [name for name, _ in sized], []
    median = known[len(known) // 2]
    threshold = median * floor_pct / 100
    keep, dropped = [], []
    for name, size in sized:
        # An unknown size is never grounds for dropping an artist: a
        # Last.fm miss should cost variety, not silently narrow the pool.
        if size > 0 and size < threshold:
            dropped.append((name, size))
        else:
            keep.append(name)
    return keep, dropped


@dataclass(frozen=True, slots=True)
class SelectionRules:
    """Everything about a batch that is a setting rather than a track.

    Deliberately primitives rather than the integration's own option
    constants, so this module keeps importing nothing and stays testable
    on its own.
    """

    provider: str = ""
    min_duration: int = 0
    clean_only: bool = False
    prefer_explicit: bool = False
    skip_live: bool = True
    skip_remix: bool = False
    skip_holiday: bool = True
    fresh_days: int = 0


def select_fresh_first(
    tracks: list[Any],
    rules: SelectionRules,
    *,
    heard: Mapping[str, float],
    current_uri: str = "",
    excluded_titles: set[str] | None = None,
    excluded_uris: set[str] | None = None,
    excluded_artists: set[str] | None = None,
    limit: int = 0,
    now: datetime | None = None,
) -> tuple[list[str], list[str]]:
    """Like select_tracks, but songs heard today wait their turn.

    They are passed over while the artist has anything fresh, and fill in
    only when it does not. Selection starts from an artist's biggest song,
    so without this a returning artist replayed the same hits the moment
    the repeat window let them go: a Don Henley morning replayed thirteen
    of its first hour's nineteen songs.

    Both passes apply every other rule, the depth limit included, so a
    shortage of fresh songs is made up with a hit heard earlier rather than
    with a deeper cut nobody heard at all. ``heard`` maps each title to
    when it was last heard, and the one heard longest ago comes back first.
    """
    titles_out = set(excluded_titles or ())
    uris_out = set(excluded_uris or ())
    fresh, fresh_titles = select_tracks(
        tracks,
        rules,
        current_uri=current_uri,
        excluded_titles=titles_out | set(heard),
        excluded_uris=set(uris_out),
        excluded_artists=excluded_artists,
        limit=limit,
        now=now,
    )
    if not limit or len(fresh) >= limit:
        return fresh, fresh_titles
    rest, rest_titles = select_tracks(
        tracks,
        rules,
        current_uri=current_uri,
        excluded_titles=titles_out | set(fresh_titles),
        excluded_uris=uris_out | set(fresh),
        excluded_artists=excluded_artists,
        limit=0,
        now=now,
    )
    oldest = sorted(range(len(rest)), key=lambda i: heard.get(rest_titles[i], 0.0))
    wanted = sorted(oldest[: limit - len(fresh)])
    return (
        fresh + [rest[i] for i in wanted],
        fresh_titles + [rest_titles[i] for i in wanted],
    )


def select_tracks(
    tracks: list[Any],
    rules: SelectionRules,
    *,
    current_uri: str = "",
    excluded_titles: set[str] | None = None,
    excluded_uris: set[str] | None = None,
    excluded_artists: set[str] | None = None,
    limit: int = 0,
    now: datetime | None = None,
) -> tuple[list[str], list[str]]:
    """Filter one artist's tracks down to this batch's picks.

    Returns the chosen URIs and their normalised titles, in order. Takes
    anything with the attributes of a track rather than a declared type,
    so nothing here has to know about Music Assistant.

    ``excluded_artists`` are artists that already have a pool of their
    own in this batch. A track crediting one of them belongs to that
    pool, not this one, and letting it through here is how the same act
    got into a batch twice under two names: Jeff Lynne and Electric Light
    Orchestra between them played three in a row while the run cap saw
    two different artists.

    """
    titles_out: set[str] = excluded_titles or set()
    uris_out: set[str] = excluded_uris or set()
    artists_out: set[str] = excluded_artists or set()

    uris: list[str] = []
    titles: list[str] = []
    for track in _ordered_for_selection(tracks, rules, now):
        if limit and len(uris) >= limit:
            break
        if not track.uri or track.uri == current_uri or track.uri in uris_out:
            continue
        # A collaboration credited to an artist already covered is that
        # artist's record, however it is filed.
        if any(name.strip().lower() in artists_out for name in track.artists):
            continue
        # A karaoke or tribute act names itself, so the credits give it
        # away even when the title does not.
        if any(
            marker in name.lower()
            for name in track.artists
            for marker in IMITATION_MARKERS
        ):
            continue
        if not matches_provider(track.uri, rules.provider):
            continue
        # Commentary, interludes and skits chart alongside the songs, so
        # a genuine top-tracks ranking hands them straight over.
        if is_too_short(track.duration, rules.min_duration):
            continue
        if rules.clean_only and track.explicit:
            continue
        # Commentary, skits and demos: none of them is the song itself.
        if is_non_song(track.name, track.version) or is_demo(
            track.name, track.version, track.album
        ):
            continue
        # Versions of the song that are not the song people mean.
        if (rules.skip_live and is_live(track.name, track.version)) or (
            rules.skip_remix and is_remix(track.name, track.version)
        ):
            continue
        if rules.skip_holiday and is_holiday(track.name, track.version, track.album):
            continue
        title = base_title(track.name)
        if not title or title in titles_out or title in titles:
            continue
        uris.append(track.uri)
        titles.append(title)
    return uris, titles


def _ordered_for_selection(
    tracks: list[Any], rules: SelectionRules, now: datetime | None
) -> list[Any]:
    """Apply every ordering preference before the batch is cut.

    Explicit preference is a sort rather than a filter because a clean
    edit is usually a separate release with its own title, so nothing
    marks it as a version of the original. Putting the explicit tracks
    first pushes the edit outside the per-artist cut instead.
    """
    ordered = tracks
    if rules.fresh_days > 0 and now is not None:
        # Providers rank by cumulative plays, which buries anything
        # recent. Tracks scoring zero, meaning old, unpopular, or without
        # the metadata to tell, keep the provider's ordering exactly: the
        # sort is stable, so this is a no-op wherever the data is absent.
        ordered = sorted(
            ordered,
            key=lambda t: hotness(t.released, t.popularity, rules.fresh_days, now),
            reverse=True,
        )
    if rules.prefer_explicit:
        ordered = sorted(ordered, key=lambda track: not track.explicit)
    return ordered


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


# A backing band written into an artist's name. Last.fm and a provider
# frequently disagree about whether to include one: Last.fm returns "Tom
# Petty and The Heartbreakers" where Tidal credits plain "Tom Petty",
# and an exact comparison then rejects every track that artist has.
_BACKING_BAND = re.compile(r"\s+(?:and|with|&|feat\.?|featuring)\s+the\s+.+$")


def _same_artist(a: str, b: str) -> bool:
    """Whether two artist names are the same act.

    Deliberately narrow. Matching on a prefix would be the obvious
    generalisation and is wrong: "The Band" is a prefix of "The Band
    Perry" at a word boundary, and they share nothing. Only a trailing
    backing band is stripped, which is the disagreement that actually
    occurs.
    """
    first, second = a.strip().lower(), b.strip().lower()
    if first == second:
        return True
    return _BACKING_BAND.sub("", first) == _BACKING_BAND.sub("", second)


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
    return any(_same_artist(name, target) for name in credited)


def without_backing_band(name: str) -> str:
    """The artist's name without a trailing backing band, or "".

    Returns empty when there is nothing to strip, so a caller can tell
    whether a second attempt is worth making.

    Worth making, because the name decides what a provider search
    returns and not merely whether its results are accepted. Searching
    Tidal for "Tom Petty and The Heartbreakers" yields four Stevie Nicks
    collaborations and a karaoke record; searching for "Tom Petty" yields
    Free Fallin', I Won't Back Down and Mary Jane's Last Dance.
    """
    stripped = _BACKING_BAND.sub("", name.strip())
    return "" if stripped.lower() == name.strip().lower() else stripped


def strong_artists(sized: list[tuple[str, int]]) -> list[str]:
    """The artists in a batch at or above its median audience.

    A refill reseeds off the batch that just played, and a big artist's
    neighbours are mostly smaller than it, simply because there are far
    more small artists than big ones. Reseeding off whichever happened to
    be playing therefore steps down more often than up, and over an
    evening that is a one-way ratchet into obscurity. An observed session
    halved in one hop: a Carole King batch at a median reach of 759,000
    reseeded to Janis Ian at 338,000, whose own pool was Eva Cassidy and
    Steve Forbert.

    Returning the upper half rather than the single largest is
    deliberate. Always taking the biggest would pin a station to one
    artist and stop it moving at all, and the movement is the point; this
    only stops the movement being consistently downward.

    Artists of unknown size are included, on the same principle as
    everywhere else here: a Last.fm miss is not evidence of being small.
    """
    if not sized:
        return []
    known = sorted(size for _, size in sized if size > 0)
    if not known:
        return [name for name, _ in sized]
    median = known[len(known) // 2]
    return [name for name, size in sized if size == 0 or size >= median]


def close_to_home(
    strong: list[str],
    degree_of: Callable[[str], int | None],
    *,
    fenced: bool,
) -> list[str]:
    """Narrow reseed candidates to those nearest the station's origin.

    Choosing only by size lets a refill pick an artist who is big but sits
    at the edge of the station, and that artist's neighbours then define
    the next hour. Observed: a Sam Smith station reseeded from Christina
    Aguilera and spent the following hour on Jessie J, JoJo, Lindsay Lohan
    and Ashley Tisdale.

    So among the stronger half, prefer artists within one step of the
    origin, then within two, and only then anyone. A preference rather
    than a filter, so a station that has legitimately travelled still
    reseeds from somewhere. Simulated over ten origins and four refills
    each, this took sideways refills from 3% to none, kept reach and
    cost about three artists of variety across five batches.

    Unfenced, as in Discovery, wandering is the point and nothing is
    narrowed.
    """
    if not fenced:
        return strong
    for limit in (1, 2):
        close = [a for a in strong if (d := degree_of(a)) is not None and d <= limit]
        if close:
            return close
    return strong


def move_on(strong: list[str], last_lead: str) -> list[str]:
    """Reseed candidates without the artist who led the last batch.

    Preferring artists close to the origin makes the origin itself the
    closest candidate of all, and a refill built around the origin again
    is a near copy of the hour before. Observed: a Texas Hold 'Em station
    refilled from Beyoncé and returned Destiny's Child, The Carters and
    Janet Jackson again, plus Kelly Rowland, Chloe x Halle and Chlöe, so six
    of its nine artists were Beyoncé, her group, her family or her label.

    So a refill always moves at least one step. The station can still come
    home, just not two hours running. If the last lead is the only
    candidate, it stays: repeating beats stopping.
    """
    target = last_lead.strip().lower()
    if not target:
        return strong
    rest = [a for a in strong if a.strip().lower() != target]
    return rest or strong


# Below this share of a pair's audience, the first credited name is a
# footnote rather than how the act is known. Measured on the two cases that
# define it: "Sonny" alone draws 34% of Sonny & Cher, and is how that duo
# is known; "Stone Poneys" alone draws 1% of Stone Poneys & Linda Ronstadt,
# and is not. Thirtyfold apart, so the line needs no precision.
FOOTNOTE_SHARE: Final = 0.10


def lead_among_credits(
    first: str, sizes: Mapping[str, int], pair_size: int
) -> str:
    """Which credited artist a pick's station should be built around.

    The first credit, unless it is a footnote to the pair: then whichever
    credited artist has the largest audience of their own. "Different
    Drum" is credited to Stone Poneys and to Linda Ronstadt, and building
    around the first credit gave a station three obscure 1967 album cuts
    at 8,278 listeners and none of her hits.

    Deliberately not simply "the biggest credit". The Beat Goes On is
    credited to Sonny and to Cher, Cher alone is far bigger than the duo,
    and a Cher-led station would put Believe into a 1967 hour. Sonny is
    how that duo is known, which is what the share measures.
    """
    first_size = sizes.get(first, 0)
    if not pair_size or first_size >= pair_size * FOOTNOTE_SHARE:
        return first
    best = max(sizes.items(), key=lambda item: item[1], default=(first, 0))
    return best[0] if best[1] > first_size else first


# How many of a candidate's neighbours stand for its neighbourhood: the
# same number a batch would draw from it by default.
NEIGHBOURHOOD_SIZE: Final = 8


def neighbourhood_strength(
    neighbours: list[str], sizes: Mapping[str, int], take: int = NEIGHBOURHOOD_SIZE
) -> int:
    """The median audience of the pool an artist would bring.

    A reseed artist's own size says little about its neighbours'. Boney M.
    was big enough for the stronger half of an ABBA batch, and its
    neighbours were Dschinghis Khan, Eruption, Fancy and Ottawan: the next
    hour fell to a sixth of the reach. Unknown sizes are left out rather
    than counted as zero.
    """
    known = sorted(sizes[n] for n in neighbours[:take] if sizes.get(n, 0) > 0)
    return known[len(known) // 2] if known else 0


def lean_toward_strength(
    candidates: list[str], strengths: Mapping[str, int], rng: random.Random
) -> str:
    """Choose a reseed artist, weighted by the strength of its neighbourhood.

    Weighted rather than always the strongest. Simulated over eleven
    origins and four refills, always taking the strongest neighbourhood
    ended stations 70% stronger but looped: Fleetwood Mac alternated
    between the same two neighbourhoods all evening, Nancy Sinatra sat at
    one value for three refills, and Dasha climbed out of country. Leaning
    toward strength ended them about 17% stronger than a flat choice, with
    a gentler worst refill and no loss of lane or variety.
    """
    if len(candidates) == 1:
        return candidates[0]
    weights = [max(strengths.get(name, 0), 1) for name in candidates]
    return rng.choices(candidates, weights=weights, k=1)[0]


# A second act sharing a name is dropped only when the main one clearly
# dominates the results. A genuine catalogue split across two provider
# pages, which happens with reissues, stays whole.
NAMESAKE_DOMINANCE: Final = 0.6


def keep_one_act(tracks: list[Any], wanted: str) -> list[Any]:
    """Drop tracks by a different artist who merely shares the name.

    A search for .38 Special returned "F2D", from "Demo 2", by a scream
    metal band that is also called .38 Special. The credit check passed,
    because the names match exactly, and it played in an hour of arena
    rock. Names are not unique; the provider's artist ID is.

    Keeps the ID credited on most of the results, which is the act the
    search is really about, and drops the others only when that ID holds a
    clear majority. Tracks without IDs are kept, since there is nothing to
    judge them by.
    """
    ids: list[str] = []
    for track in tracks:
        match = ""
        for name, uri in zip(track.artists, track.artist_uris, strict=False):
            if uri and credits_artist([name], wanted):
                match = uri
                break
        ids.append(match)
    counts: dict[str, int] = {}
    for uri in ids:
        if uri:
            counts[uri] = counts.get(uri, 0) + 1
    if len(counts) <= 1:
        return tracks
    main, main_count = max(counts.items(), key=lambda item: item[1])
    if main_count < NAMESAKE_DOMINANCE * sum(counts.values()):
        return tracks
    return [t for t, uri in zip(tracks, ids, strict=True) if not uri or uri == main]


# The listeners a song past an artist's A-tracks needs, as a share of the
# station's typical artist audience. On an 80s rock station that is about
# 45k, which lets REO Speedwagon play eleven songs, down to "Keep Pushin'"
# and "Back on the Road Again" but not the Hi Infidelity album tracks,
# Loverboy four, Mr. Mister their two, and leaves the Beatles, Michael
# Jackson and ABBA effectively uncapped: their fiftieth songs are better
# known than most bands' first. A tenth was tried first and cut singles.
DEPTH_BAR_SHARE: Final = 0.05


def depth_bar(sizes: Mapping[str, int]) -> int:
    """The listeners a song beyond an artist's A-tracks must have.

    Relative to the station in front of it, like every other popularity
    judgement here, so a country station is not held to rock's numbers.
    Zero, meaning no limit, when no audience is known.
    """
    known = sorted(size for size in sizes.values() if size > 0)
    typical = known[len(known) // 2] if known else 0
    return int(typical * DEPTH_BAR_SHARE)


def too_deep(
    tracks: list[Any],
    rank: Mapping[str, int],
    known: Sequence[tuple[str, int]] | None,
    bar: int,
    a_tracks: int,
) -> set[str]:
    """The URIs of an artist's songs that are past what this station plays.

    An artist's A-tracks are always allowed: their ``a_tracks`` biggest
    songs on Last.fm, however small the artist is. Every other song needs
    at least ``bar`` listeners, and a song Last.fm does not list among the
    artist's best known is taken to be short of it.

    The provider's own order deliberately confers nothing. It used to: the
    first few results were treated as A-tracks too, and a search for Sugar
    put a techno record called "Candy from Strangers" first, credited to a
    different act of the same name. Last.fm lists it 27th for Sugar at
    8,664 listeners against 86,542 for their biggest, so the bar would have
    caught it had the provider's order not waved it through.

    Nothing is cut when the numbers are missing (``known`` is None or
    empty, or the bar is zero), or when no song the provider returned
    appears in the Last.fm list at all. That last case is a name the two
    services do not share rather than an artist with no known songs, and
    classical is full of them.

    This is also what stops a tight fence, refilling from the same artists,
    from reaching further down each of them every time it comes round.
    """
    if not known or bar <= 0:
        return set()
    listeners: dict[str, int] = {}
    for title, count in known:
        key = base_title(title)
        listeners[key] = max(count, listeners.get(key, 0))
    titles = {base_title(track.name) for track in tracks}
    if not titles & set(listeners):
        return set()
    biggest = {base_title(title) for title, _ in known[:a_tracks]}
    return {
        track.uri
        for track in tracks
        if rank.get(track.uri) is not None
        and base_title(track.name) not in biggest
        and listeners.get(base_title(track.name), 0) < bar
    }
