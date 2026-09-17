"""Track and artist filtering rules.

Every rule here is pinned to a song that reached somebody's evening and
should not have, or to one that was kept out and should not have been. The
comments name those songs on purpose: they are the test cases, and a rule
whose example no longer makes sense is a rule to question.
"""

from __future__ import annotations

import random
import re
import unicodedata
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
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
    "yuletide",
    "navidad",
    # Santa is handled separately, below: as a bare substring it took
    # Everclear's "Santa Monica" and every track on an album called
    # Santana, and as a short list of phrases it missed The Killers'
    # "Don't Shoot Me Santa" and Clarence Carter's "Back Door Santa".
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
    "baby its cold outside",
    "reindeer",
    "saint nick",
    "mele kalikimaka",
    "wintersong",
    # "Holiday" alone is Madonna, Green Day and "Holiday Road", but these
    # three phrases are only ever the season. Andy Williams' two biggest
    # results are "It's the Most Wonderful Time of the Year" and "Happy
    # Holiday / The Holiday Season", and neither says Christmas anywhere.
    "most wonderful time of the year",
    "happy holiday",
    "holiday season",
    # Songs everybody knows and nobody titles with the season.
    "fairytale of new york",
    "underneath the tree",
    # Carols.
    "silent night",
    "holy night",
    "stille nacht",
    "tannenbaum",
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
    # Not bare "boy child", which is a Scott Walker song.
    "marys boy child",
    "angels we have heard",
    "do you hear what i hear",
    "ding dong merrily",
    "twelve days of",
    "we three kings",
    "o christmas tree",
    "greensleeves",
)

# Records that say Christmas and are not Christmas records. Checked
# against the song's own name before anything else, because "christmas"
# as a substring is otherwise exactly the right rule and these are the
# whole of its cost. Ryuichi Sakamoto's "Merry Christmas Mr. Lawrence" is
# the piece he is best known for, and it was suppressed in every month of
# the year, on its own album and on the soundtrack both.
NOT_HOLIDAY: Final = (
    "merry christmas mr lawrence",
    "christmas in february",
    "christmas card from a hooker in minneapolis",
)

# The same, for titles too generic to exempt outright. A song called
# "Christmas" is The Who on Tommy, unless it is sitting on a Christmas
# record, in which case it is what it says it is.
NOT_HOLIDAY_OFF_SEASON: Final = ("christmas",)

# "Noel" cannot be matched as a word, let alone a substring: it is a
# first name, and the word boundary still takes every record Noel
# Gallagher has made. Only the two forms that are always the carol.
# Accent folding is what brings "The First Noël" within reach of either.
NOEL_PHRASE: Final = "first noel"
NOEL_ALBUM: Final = "noel"

# Last.fm returns collaboration credits as if they were standalone artists
# ("Lady Gaga, Bruno Mars"). Searching those mostly yields cover/live/piano
# versions of the one collab song rather than real additional variety.
#
# What marks one is NOT its punctuation, which is what a first attempt at
# this got wrong. A comma or an ampersand in a name is overwhelmingly an
# ordinary act, and dropping on the punctuation alone silently cost the
# stations that most want them: a James Taylor seed lost Simon &
# Garfunkel, Crosby, Stills & Nash and Peter, Paul and Mary; a Huey Lewis
# seed lost Hall & Oates, Kool & The Gang and Earth, Wind & Fire; a Tom
# Petty seed lost Bruce Springsteen & The E Street Band.
#
# What marks one is that every part of it is an artist the list already
# knows on its own. "Lady Gaga, Bruno Mars" arrives in a list that also
# holds Lady Gaga and Bruno Mars separately; "Simon & Garfunkel" arrives
# in a list holding neither Simon nor Garfunkel. Requiring *every* part
# to be known keeps the failure on the safe side: an unrecognised part
# means the name is kept, which at worst wastes one neighbour slot.
_COLLAB_SPLIT = re.compile(r"\s*,\s*|\s+&\s+")

# It takes two to be a collaboration.
MIN_COLLAB_PARTS: Final = 2

# Below this many artists a pool has no meaningful median.
#
# Four was the first guess, on the reasoning that dropping one of three
# neighbours costs more than the outlier does. It does not: the Artist
# seed style draws exactly three neighbours, so the floor was switched
# off for the whole style, and the very defect the rule was written for
# came back. Christine McVie at 4% of a three-artist median is kept at
# four and dropped at three. A median of three can only ever put one
# artist below the bar, so the cost is bounded at one neighbour.
MIN_POOL_FOR_FLOOR: Final = 3

# Tier labels. Defined here rather than in const.py because this module
# deliberately imports nothing from Home Assistant or from the rest of
# the integration, so its logic can be tested without either.
TIER_POWER: Final = "P"
TIER_SECONDARY: Final = "S"
TIER_DEEP: Final = "D"
# A familiar record from outside the era the station is holding to. What
# commercial radio means by Gold, which is old rather than obscure, and
# the one slot in an hour allowed to break the era fence. Nothing is
# filed here yet; the label and its slot exist so the clock is the final
# shape while what fills it is built.
TIER_GOLD: Final = "G"

# How much of its own artist's biggest song a record has to hold to count
# as one of the records that artist is known for. Measured against 49
# artists on 2026-09-15, and the three verdicts already reached by ear
# all land correctly:
#
#   Glenn Frey, "You Belong to the City"   #2   70.8%  -> Power
#   Mr. Mister, "Kyrie"                    #2   39.0%  -> Secondary
#   Sugar, "Candy from Strangers"          #27  10.0%  -> Deep
#
# The gap either side of these lines is wide rather than narrow. Real
# second hits measured 24 to 93 percent; real filler measured 1 to 10.
# A one-hit wonder collapses to a single Power by itself, because the
# next thing it has is single figures: Dexys' second record is 4% of
# their first, Soft Cell's 6%, Norman Greenbaum's 1%. A giant keeps its
# depth for the same reason, since the Beatles' twentieth song is still
# 54% of their first and Metallica's twentieth is 30%.
POWER_SHARE: Final = 0.50
SECONDARY_SHARE: Final = 0.20

# What a slot takes when nothing of the tier it asked for is left. An
# hour with a slightly wrong texture beats an hour with a hole in it, but
# which way it goes wrong matters: an unfilled Gold or Power slot should
# reach for the next most familiar thing, while an unfilled Deep slot
# should not answer a request for texture with the biggest record in the
# pool.
TIER_FALLBACK: Final = {
    TIER_GOLD: (TIER_GOLD, TIER_POWER, TIER_SECONDARY, TIER_DEEP),
    TIER_POWER: (TIER_POWER, TIER_SECONDARY, TIER_GOLD, TIER_DEEP),
    TIER_SECONDARY: (TIER_SECONDARY, TIER_POWER, TIER_GOLD, TIER_DEEP),
    TIER_DEEP: (TIER_DEEP, TIER_SECONDARY, TIER_GOLD, TIER_POWER),
}

# Categories that have to be kept apart from each other, whatever the
# clock asked for. A Deep next to a Deep is the thing that loses a
# listener, and a Gold next to a Deep is two oddities in a row.
#
# A rule rather than a pattern, because a pattern can only promise this
# while the pool can still answer it. Simulated against the real curves
# of twelve one-hit wonders, the clock ran out of Power by the last few
# slots and closed on "S S S D D": every clock in the file spaces its
# own Deeps correctly and it made no difference at the tail, where only
# the weak pools had anything left.
SPACED_TIERS: Final = (TIER_DEEP, TIER_GOLD)

# How many familiarity bands the artist draw is spread across, so a
# batch reaches the well-known, the middling and the further-out parts
# of a pool rather than clustering wherever the weighting points.
#
# Nothing to do with the length of a clock, though it used to be spelled
# len(TIER_PATTERN) back when every clock was three slots long, which
# made the coincidence invisible. A twenty-slot clock would have asked
# for twenty bands of one candidate each.
CANDIDATE_BANDS: Final = 3

# Spoken-word and filler entries that search returns alongside the real
# tracks, and that nobody wants queued. Duration catches most of it;
# these catch the long ones.
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

# How a provider separates a song's name from a note about the recording.
# Every common spelling, because they disagree: a hyphen, an en dash, an em
# dash, round brackets, square brackets.
_NOTE_SEPARATOR = re.compile(r"\s[-\u2013\u2014]\s")
NOTE_BRACKETS: Final = ("(", "[", "{")

# A title that opens this way is a recording, not a song: Led Zeppelin's
# "Live at the Olympia - Paris, France (October 10, 1969) - Dazed and
# Confused" says live before it says anything else, so nothing a provider
# appends carries the marker.
#
# Only counts when the title goes on to append something, which is the
# whole reason the rule exists: the venue is a prefix and the song's name
# follows it after a dash or a bracket. Without that requirement the rule
# read ordinary song titles as concerts, and Portugal. The Man's "Live in
# the Moment" could not be queued at all. "Live On Forever", "Live in the
# Sky" and "Live From Space" went the same way.
_LIVE_OPENING = re.compile(r"^(live|unplugged)\s+(at|from|in|on)\b", re.IGNORECASE)

# Live, in the languages a Latin or Brazilian catalogue marks it in.
# Phrases rather than words, checked against the note and the version:
# "vivo" on its own is an ordinary word in both languages.
LIVE_PHRASES: Final = ("en vivo", "en directo", "ao vivo")

# Santa, but not the places and saints named after him. Everclear's
# "Santa Monica", Bon Jovi's "Santa Fe" and Santa Esmeralda are songs;
# "Santa's Coming for Us" is not. Santana needs no exception: the word
# boundary excludes it.
#
# The Spanish adjective is the awkward part, since it is the same word
# and it follows its noun as often as it precedes one. The lookbehinds
# cover the constructions a title actually uses. Matched against
# accent-folded text, which is what brings "Santa María" and "Santa
# Lucía" within reach of the list below at all.
_SANTA = re.compile(
    r"(?<!\bsemana\s)(?<!\btierra\s)(?<!\bnoche\s)(?<!\bcasa\s)"
    # "santas" as well as "santa", because the possessive loses its
    # apostrophe to the folding and "Santa's Coming for Us" then had no
    # word boundary where the pattern expected one.
    r"\bsantas?\b(?!\s+(?:monica|fe|barbara|cruz|ana|clara|rosa|maria|"
    r"lucia|marta|teresa|esmeralda|cecilia|catarina|muerte|sangre|"
    r"misa|iglesia)\b)",
    re.IGNORECASE,
)

# A remix a provider does not mark at all, beyond the last word: Tidal
# writes "Savage Remix" and "Drunk in Love Remix" with no brackets, no
# dash, and nothing in the version field.
_TRAILING_REMIX = re.compile(r"\bremix(es)?\s*$", re.IGNORECASE)

# Punctuation that carries no meaning in a title, so "No. 5" and "No 5"
# are the same piece. Curly quotes are here too: the provider writes
# "Don't Stop Believin'" and Last.fm writes it straight, and a title that
# fails to match Last.fm's reads as a song nobody has heard of.
_PUNCTUATION = re.compile("[.,;:'\"‘’“”]")

# The same idea one step further, for comparing a phrase against a title
# rather than a title against a title. Exclamation and question marks are
# included because a carol is written "Hark! The Herald Angels Sing" by
# one service and without the bang by another, and accents are folded
# away because "The First Noël" and "Noel" are the same record. Both
# defeated the holiday list until they were folded here.
_LOOSE_PUNCTUATION = re.compile("[.,;:!?'\"‘’“”]")


def _folded(text: str) -> str:
    """Lowercased, accent-folded, and stripped of decorative punctuation.

    So that one service's spelling of a phrase matches another's. Used
    where a fixed list of phrases is matched against provider text, which
    is the case that suffers: the list can only ever hold one spelling.
    """
    decomposed = unicodedata.normalize("NFKD", text.lower())
    bare = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return _LOOSE_PUNCTUATION.sub("", bare)


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

    A parenthesis that opens the title is part of the song's name rather
    than a note about the recording, so only its brackets are dropped.
    Cutting there instead left nothing at all, and a song whose base title
    is empty is discarded: "(Don't Fear) The Reaper", "(Sittin' On) The
    Dock of the Bay" and "(I Can't Get No) Satisfaction" could never be
    queued. Keeping the words also matches the provider's other spelling of
    the same record, "Don't Fear the Reaper".

    Curly quotes fold onto straight ones and "&" onto "and", because the
    provider and Last.fm disagree about both and a title that does not
    match Last.fm's is read as a song nobody knows.
    """
    title, _ = _split_note(name)
    title = title.split(" / ", maxsplit=1)[0]
    for opener, closer in (("(", ")"), ("[", "]")):
        if title.startswith(opener):
            title = title.replace(opener, "", 1).replace(closer, " ", 1)
    head, sep, tail = title.rpartition(",")
    if sep and tail.strip().lower().startswith(TEMPO_MARKINGS):
        title = head
    title = title.replace(" & ", " and ")
    return " ".join(_PUNCTUATION.sub("", title).lower().split())


def is_demo(name: str, version: str, album: str) -> bool:
    """Return True for demos and rough mixes.

    An unfinished recording, which nobody asking for a band's hits wants.
    A search for .38 Special handed back "F2D" from an album called "Demo
    2", and it opened an hour of their neighbours' biggest records.

    Whole words only, in the title, version and album, so "Demolition
    Man" and "Democracy" are left alone.

    "Rough mix" is read in the title and version but not the album,
    because Pete Townshend and Ronnie Lane's 1977 record is called Rough
    Mix and every track on it was being thrown away as an unfinished one.
    """
    text = " ".join((name, version, album)).lower()
    words = set(_WORDS.split(text))
    return bool(words & {"demo", "demos"}) or "rough mix" in f"{name} {version}".lower()


def _split_note(name: str) -> tuple[str, str]:
    """Split a title into the song's own name and the provider's note.

    The note is what a provider appends to say which recording this is:
    after a dash, or inside brackets. Providers disagree about which
    punctuation to use, so all the common spellings count: "Song - Live",
    "Song (Live)", "Song [Live]", and the en dash and square brackets that
    a first attempt at this missed, which quietly let live versions
    through on the providers that use them.

    A bracket that opens the title is part of the song's name, not a note,
    so it is left in the name half: "(Don't Fear) The Reaper".
    """
    head, note = name, ""
    if split := _NOTE_SEPARATOR.search(head):
        head, note = head[: split.start()], head[split.end() :]
    for opener in NOTE_BRACKETS:
        # From index 1, because a bracket that opens the title belongs to
        # the name: OMD's "(Forever) Live And Die" is not a live recording.
        at = head.find(opener, 1)
        if at > 0:
            note = f"{note} {head[at:]}"
            head = head[:at]
    return head, note


def _recording_note(name: str) -> str:
    """What the provider appended to a title, lowercased.

    A marker for a live or remixed version lives here, never in the song's
    own name, and reading the whole title condemned songs that are simply
    called what they are called. With live filtering on, which is the
    default, "Live Wire", "Live to Tell", "Live Forever" and "Live and Let
    Die" could none of them be queued.
    """
    return _split_note(name)[1].lower()


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
    note = _recording_note(name)
    words = set(_WORDS.split(note))
    if (
        bool(words & {"remix", "rmx", "remixes"})
        or any(marker in haystack for marker in REMIX_MARKERS)
        or _TRAILING_REMIX.search(name)
    ):
        return True
    text = f"{note} {haystack}"
    return any(phrase in text for phrase in REMIX_PHRASES)


def is_live(name: str, version: str) -> bool:
    """Return True for live recordings.

    Substring match on the version field, standalone-word match on the
    recording note, so "Song (Live at Wembley)" and "Song - Live" are
    caught while "Alive" and "Living on a Prayer" are left alone.

    Tokenising on non-alphanumerics rather than whitespace is a deliberate
    departure from the YAML this replaces: splitting on spaces alone left
    "Song (Live)" as the token "(live)", so the most common form of the
    thing this filter exists to catch only got caught when the provider
    also populated the version field.
    """
    stripped = name.strip()
    if _LIVE_OPENING.match(stripped) and _appends_a_note(stripped):
        return True
    haystack = version.lower()
    note = _recording_note(name)
    if any(phrase in note or phrase in haystack for phrase in LIVE_PHRASES):
        return True
    words = set(_WORDS.split(note))
    return any(
        marker in haystack or marker in words for marker in LIVE_MARKERS
    )


def _appends_a_note(name: str) -> bool:
    """Whether a title carries anything after the song's own name."""
    return bool(_NOTE_SEPARATOR.search(name)) or any(
        name.find(opener, 1) > 0 for opener in NOTE_BRACKETS
    )


def is_holiday(name: str, version: str, album: str) -> bool:
    """Return True for holiday content, regardless of season.

    Checks title, version and album name together: a provider's popularity
    ranking will happily surface an artist's Christmas album in September.

    Santa is a word rather than a phrase, with the places named after him
    spelled out. A phrase list was tried and missed The Killers' "Don't
    Shoot Me Santa", Clarence Carter's "Back Door Santa", Sia's "Santa's
    Coming for Us" and Dylan's "Must Be Santa", none of which say
    Christmas anywhere. The word boundary already excludes Santana.

    Everything is compared accent-folded and stripped of punctuation,
    because a fixed list of phrases can only hold one spelling and the
    services do not agree on which: "Baby, It's Cold Outside" carries the
    comma on one and not the other, "Hark! The Herald Angels Sing" the
    exclamation mark, "The First Noël" the diaeresis. All three used to
    be caught only when the album name happened to say Christmas too.
    """
    title = _folded(base_title(name))
    record = _folded(album)
    if title in NOT_HOLIDAY:
        return False
    if title in NOT_HOLIDAY_OFF_SEASON and "christmas" not in record:
        return False
    haystack = _folded(f"{name} {version} {album}")
    if any(token in haystack for token in HOLIDAY_TOKENS):
        return True
    if NOEL_PHRASE in haystack or record == NOEL_ALBUM:
        return True
    return bool(_SANTA.search(haystack))


def clean_similar_artists(
    candidates: list[tuple[str, float]], seed_artist: str
) -> list[tuple[str, float]]:
    """Drop empties, the seed artist itself, and collaboration credits.

    Takes and returns (name, match) pairs so the ranking survives to the
    point where artists are actually chosen.

    The seed comparison goes through ``_same_artist`` rather than ``==``
    so that Last.fm returning "Bruce Springsteen & The E Street Band"
    alongside a Bruce Springsteen seed is recognised as the same act. It
    is one of the few places the two spellings reliably both appear, and
    an exact comparison spent a neighbour slot on a second pool for the
    artist already playing.
    """
    known = {
        name.strip().lower()
        for name, _ in candidates
        if name and not _COLLAB_SPLIT.search(name)
    }
    known.add(seed_artist.strip().lower())
    seen: set[str] = set()
    cleaned: list[tuple[str, float]] = []
    for name, match in candidates:
        candidate = (name or "").strip()
        if not candidate or _same_artist(candidate, seed_artist):
            continue
        if _is_collab_credit(candidate, known):
            continue
        key = candidate.lower()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append((candidate, match))
    return cleaned


def _is_collab_credit(name: str, known: set[str]) -> bool:
    """Whether a name is several artists the list already knows apart."""
    parts = [part.strip().lower() for part in _COLLAB_SPLIT.split(name)]
    if len(parts) < MIN_COLLAB_PARTS or not all(parts):
        return False
    return all(part in known for part in parts)


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


def _song_share(
    uri: str,
    position: int,
    decay: float,
    share: Mapping[str, float] | None,
) -> float:
    """How big a song is within its own artist's catalogue, 0 to 1.

    The real figure where Last.fm has the song, the geometric guess where
    it does not. Both are fractions of the artist's own audience, so the
    two can sit side by side in one pool: a track the two services spell
    differently falls back to the guess without changing the scale.
    """
    known = share.get(uri) if share else None
    return known if known is not None else decay**position


def tier_of(
    sized: list[tuple[str, list[str], int]],
    decay: float,
    rank: Mapping[str, int] | None = None,
    share: Mapping[str, float] | None = None,
) -> dict[str, str]:
    """Label each track Power, Secondary or Deep by how well known it is.

    A record's category is how much of its own artist's biggest song it
    holds, and nothing else. ``share`` carries the real figure where
    Last.fm has it: the song's listeners over the artist's biggest song's.
    Genre cancels, because the numerator and denominator are the same
    artist, which is what lets a country station work at all when Last.fm
    undercounts the genre tenfold.

    Without it the fraction is guessed at as ``decay ** position``, and
    that guess inverts on deep positions. Measured on real data: a
    one-hit wonder's second song scores 70% of their audience when its
    true share is 4%, while the Beatles' twentieth scores 0.1% when its
    true share is 54%. A share of 1.0 at position 0 is exactly what the
    decay gives, so the two agree at the head of a catalogue and diverge
    only where the guess was bad.

    **This used to cut terciles of the pool**, which is why an hour came
    out a third Deep whatever was in it. A tercile makes the category a
    statement about rank rather than about the record, so a pool of
    genuine smashes had five of them filed as Deep by arithmetic, and a
    thin pool had a third of it promoted to Power for the same reason.
    Commercial radio tests a title and files it on the answer; the pool
    it happens to sit in that hour has nothing to do with it.

    The consequence worth knowing: **the clock can no longer manufacture
    a tier that is not there.** Asking for Deep in a pool of hits now
    falls back to Secondary rather than demoting a hit, and asking for
    Power in a thin pool cannot invent one.

    Artist size is deliberately unused. It was the other half of the old
    score, and it is why a giant's fifth record outranked a mid-sized
    act's biggest. Median reach was separately measured not to predict
    recognisability at all: 575k scored 80%, 3.3M scored 70 to 75%, and
    140k scored 94%. It stays in ``reach_of`` for the sensor, where it
    describes a batch rather than deciding one.

    ``rank`` gives each track's position in its artist's ordering when that
    differs from its position in this batch; see ``reach_of``.
    """
    tiers: dict[str, str] = {}
    for _, uris, _size in sized:
        for index, uri in enumerate(uris):
            position = rank.get(uri, index) if rank else index
            held = _song_share(uri, position, decay, share)
            if held >= POWER_SHARE:
                tiers[uri] = TIER_POWER
            elif held >= SECONDARY_SHARE:
                tiers[uri] = TIER_SECONDARY
            else:
                tiers[uri] = TIER_DEEP
    return tiers


def reach_of(
    sized: list[tuple[str, list[str], int]],
    decay: float,
    rank: Mapping[str, int] | None = None,
    share: Mapping[str, float] | None = None,
) -> dict[str, int]:
    """Estimated audience for each track, on an absolute scale.

    An artist's own audience, scaled by how big the song is within that
    artist's catalogue. The same score the tiering sorts on, kept
    unnormalised so batches can be compared with each other: tiers are
    relative to their own pool and say nothing across pools, while this
    does.

    ``share`` is the real fraction where Last.fm has the song; see
    ``tier_of`` for why the guess it replaces was wrong. An artist's top
    track has a share of 1.0, which is what the guess already gave at
    position 0, so figures recorded for first batches before this existed
    remain comparable with figures recorded after it.

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
            reach[uri] = int(weight * _song_share(uri, position, decay, share))
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
    wrong texture beats an hour with a hole in it. Which way it gives is
    set by TIER_FALLBACK rather than left to chance, so an unfilled Gold
    slot reaches for a Power and an unfilled Deep slot reaches for a
    Secondary instead of answering a request for texture with the biggest
    record in the pool.
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
    previous = ""

    while len(ordered) < wanted and any(pools):
        want = pattern[len(ordered) % len(pattern)]
        order = TIER_FALLBACK.get(want, (want,))
        pick = None
        best: tuple[int, ...] | None = None
        for index, pool in enumerate(pools):
            if not pool or (index == last and run >= max_consecutive):
                continue
            held = tiers.get(pool[0], "")
            # Sorted ahead of the clock's own preference, so keeping two
            # unfamiliar records apart outranks filling the slot the
            # clock asked for. A preference that only holds while the
            # pool can answer it is not a rule, and the tail of a batch
            # is exactly where it stops being able to.
            stacked = int(held in SPACED_TIERS and previous in SPACED_TIERS)
            fit = order.index(held) if held in order else len(order)
            # Uncapped, every pool has to be emptied, so take from the
            # fullest to avoid stranding one artist's tracks at the end.
            # Capped, there is no such obligation, and preferring the
            # fullest would simply hand the extra slots to whichever
            # artist drew most, which is the seed. Spread by who has
            # played least instead.
            key = (
                (stacked, fit, played.get(index, 0), -len(pool))
                if capped
                else (stacked, fit, -len(pool))
            )
            if best is None or key < best:
                best, pick = key, index
        if pick is None:
            pick = next(i for i, pool in enumerate(pools) if pool)

        taken = pools[pick].pop(0)
        ordered.append(taken)
        previous = tiers.get(taken, "")
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
    are her talking about each song, they sit in the catalogue alongside
    the songs, and a search for her returns them with everything else.
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
    for track in _ordered_for_selection(tracks, rules):
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
        # Commentary, interludes and skits sit in the catalogue alongside
        # the songs, so a search hands them over with everything else.
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


def _ordered_for_selection(tracks: list[Any], rules: SelectionRules) -> list[Any]:
    """Apply every ordering preference before the batch is cut.

    Explicit preference is a sort rather than a filter because a clean
    edit is usually a separate release with its own title, so nothing
    marks it as a version of the original. Putting the explicit tracks
    first pushes the edit outside the per-artist cut instead.
    """
    ordered = tracks
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


# A backing band written into an artist's name. Last.fm and a provider
# frequently disagree about whether to include one: Last.fm returns "Tom
# Petty and The Heartbreakers" where Tidal credits plain "Tom Petty",
# and an exact comparison then rejects every track that artist has.
# Case-insensitive, which it was not. Every service capitalises the
# article, so the pattern only ever matched a name that had already been
# lowercased. _same_artist lowercases first and so worked; the search
# retry in without_backing_band does not, and quietly never fired at all:
# a station seeded on "Tom Petty and The Heartbreakers" kept searching
# Tidal under the long name and taking the karaoke record it returns.
_BACKING_BAND = re.compile(
    r"\s+(?:and|with|&|feat\.?|featuring)\s+(?:the|his|her)\s+.+$", re.IGNORECASE
)

# The three ways a service writes the same joining word. Folded to one so
# that "Crosby, Stills and Nash" and "Crosby, Stills & Nash" are one act,
# and so are "Mike + The Mechanics" and "Mike & The Mechanics".
_CONJUNCTION = re.compile(r"\s*(?:&|\+|\band\b)\s*")


def _normalised_artist(name: str) -> str:
    """An artist's name reduced to what two services can agree on."""
    return _CONJUNCTION.sub(" & ", _folded(name)).strip()


def _same_artist(a: str, b: str) -> bool:
    """Whether two artist names are the same act.

    Deliberately narrow on the structure of a name. Matching on a prefix
    would be the obvious generalisation and is wrong: "The Band" is a
    prefix of "The Band Perry" at a word boundary, and they share
    nothing. Only a trailing backing band is stripped, which is the
    disagreement that actually occurs.

    Generous about spelling, though, because that disagreement is pure
    noise: an ampersand against "and", a plus sign, a comma, an accent.
    "Bill Haley and His Comets" against "Bill Haley & His Comets" is not
    a question anyone needs the answer to. "His" and "her" are read as
    backing bands alongside "the" for the same reason.
    """
    first, second = _normalised_artist(a), _normalised_artist(b)
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
    # An unknown audience is not evidence of a small one, here as
    # everywhere else: without this, a first credit Last.fm has never heard
    # of hands the station to whoever it shares the record with.
    if not pair_size or not first_size or first_size >= pair_size * FOOTNOTE_SHARE:
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


_DECADE_TAG = re.compile(r"^(?:19|20)?([0-9]0)s$")

# Above this, a bare two-digit decade tag means the twentieth century.
# "40s" is the 1940s; "20s" is this one, not the Charleston.
_LAST_MODERN_DECADE: Final = 30

# Tags that describe a listener or a passport rather than a record. Left
# out of the genre comparison, which would otherwise match an American
# country album to an American hip-hop one on "american" alone.
_NOT_A_GENRE: Final = frozenset(
    {
        "american", "british", "english", "irish", "scottish", "usa", "uk",
        "australian", "canadian", "german", "swedish", "french", "japanese",
        "male vocalists", "female vocalists", "male vocalist",
        "female vocalist", "singer-songwriter", "favourites", "favorites",
        "favourite songs", "awesome", "love", "beautiful", "seen live",
        "albums i own", "vinyl", "my music", "cool", "classic", "the best",
        "under 2000 listeners", "memories", "sexy", "epic", "party",
    }
)


def lane_of(tags: Sequence[str], artist: str = "") -> tuple[set[int], set[str]]:
    """Split album tags into the decades and the genres they claim.

    Both halves matter and they fail differently. The decade is what
    separates The Jackson 5's 1970 Motown from the mid-80s pop station it
    was landing on, and a *missing* decade is itself a signal, since
    nobody tags a 2012 record "10s".

    The artist's own name is dropped, because half of Last.fm's top tags
    are the act being tagged. So are nationalities and the listener's own
    filing habits: "american" is not a genre, and matching on it pairs a
    country record with a hip-hop one.

    Deliberately keeps everything else, including noise. Rick Astley's
    album lists "brutal death metal", which is a joke the whole internet
    is in on, and it does no harm alongside "dance" and "pop": what
    matters is that the sets *overlap*, not that they are clean.
    """
    decades: set[int] = set()
    genres: set[str] = set()
    name = artist.strip().lower()
    for raw in tags:
        tag = raw.strip().lower()
        if not tag:
            continue
        if found := _DECADE_TAG.match(tag):
            decades.add(_full_decade(found.group(1)))
        elif tag not in _NOT_A_GENRE and (not name or name not in tag):
            genres.add(tag)
    return decades, genres


def _full_decade(pair: str) -> int:
    """"80" to 1980, "00" to 2000. Two digits cannot span a century.

    Without this, the 90s and the 00s read as ninety years apart rather
    than as neighbours, and the slack that keeps 1985 next to 1980 would
    have refused to put 1999 next to 2001.
    """
    value = int(pair)
    return 2000 + value if value <= _LAST_MODERN_DECADE else 1900 + value


def in_lane(
    candidate: tuple[set[int], set[str]],
    lane: tuple[set[int], set[str]],
    *,
    decade_slack: int = 1,
) -> bool:
    """Whether a record belongs in the same hour as the song that started it.

    Two independent tests, both of which have to pass, because each
    catches something the other does not. Genre alone would keep The
    Jackson 5 on a pop station; era alone would pair 80s soul with 80s
    thrash.

    **Nothing known means keep.** An untagged album is not evidence of a
    bad record, and rejecting on absence cost Billy Ocean's "Caribbean
    Queen", a 1984 number one, from a lane it obviously belongs in. That
    is also how ``too_deep`` and ``drop_outliers`` treat missing numbers,
    and the consistency is deliberate.

    **Adjacent decades count.** Album tags inherit an artist's centre of
    gravity rather than a record's date: Stevie Wonder's "Part-Time
    Lover" is 1985 and its album reads 70s, because that is where his
    audience lives. One decade of slack keeps it; two would let the 60s
    into an 80s hour.
    """
    want_decades, want_genres = lane
    got_decades, got_genres = candidate
    if not got_decades and not got_genres:
        # Nothing known at all. No evidence is not evidence against.
        return True
    if want_genres and got_genres and not (got_genres & want_genres):
        return False
    if not want_decades or not got_decades:
        # An era can only be enforced between two known eras. A missing
        # decade used to be read as "recent, therefore reject", which was
        # generalised from a single pop example and is catastrophic
        # elsewhere: country albums are largely not decade-tagged, and on
        # a real Colter Wall lane that rule would have thrown out ten of
        # fifteen artists, among them Loretta Lynn, Merle Haggard and
        # George Jones. Absence of evidence gets the same benefit of the
        # doubt it gets in ``too_deep`` and ``drop_outliers``.
        #
        # What this gives up is catching Bruno Mars's "Locked Out of
        # Heaven" on an 80s station. That is handled where it actually
        # matters instead: see ``lane_match``, which keeps an unplaceable
        # record out of the *reseed* even while letting it play. One
        # off-era song is a song; an off-era seed is the rest of the
        # evening.
        return True
    return any(
        abs(got - want) <= decade_slack * 10
        for got in got_decades
        for want in want_decades
    )


def stratified_bands(
    candidates: Sequence[tuple[str, float]],
    count: int,
    bands: int,
    rng: random.Random,
) -> list[tuple[int, list[str]]]:
    """The same draw as ``stratified_sample``, band by band and unresolved.

    Returns ``(wanted, order)`` per band: how many that band should
    contribute, and its candidates in the order to try them. The caller
    walks each band's order until it has ``wanted`` it is happy with,
    which is what lets a rejected candidate be replaced **from its own
    band**.

    That matters more than it looks. A batch whose Power candidate fails
    a check and is refilled from the tail is still the right length and
    the wrong shape, and the hour it plays is not the hour the clock
    asked for. Keeping the replacement inside the band is the whole
    reason this returns bands rather than a finished list.
    """
    if count <= 0 or not candidates:
        return []
    names = [name for name, _ in candidates]
    if bands <= 1 or len(names) <= count:
        return [(count, names)]
    size = max(1, len(names) // bands)
    out: list[tuple[int, list[str]]] = []
    for band in range(bands):
        start = band * size
        stop = len(names) if band == bands - 1 else start + size
        wanted = count // bands + (1 if band < count % bands else 0)
        pool = names[start:stop]
        rng.shuffle(pool)
        out.append((wanted, pool))
    return out


def stratified_sample(
    candidates: Sequence[tuple[str, float]],
    count: int,
    bands: int,
    rng: random.Random,
) -> list[str]:
    """Draw from the strong, the middle and the tail of a pool alike.

    Weighted sampling exists because a deep pool sampled flat filled
    batches with artists nobody knew (0.6.0). That was true of an
    *artist* pool, whose tail really is obscure. A song crowd's tail is
    not: measured to position 55 it was still All Night Long, Footloose,
    West End Girls, Maneater, Straight Up and Physical. Weighting a pool
    like that only crowds the draw onto the same few names every day.

    So the pool is cut into bands by rank and drawn from evenly. Three
    things follow. Every batch gets real anchors, because the top band is
    always represented. Every batch reaches the tail, which is where the
    forgotten hits live and which a weighted draw almost never touched.
    And the same seed gives a different station tomorrow, because a draw
    of nineteen from forty-five filtered records has more combinations
    than anyone will exhaust.

    The band a record came from is also the band it should play in, which
    is what lets the hour's shape drive the draw rather than merely
    tidying up afterwards: see ``tier_of``.

    Falls back to the whole pool when there is too little to band.
    """
    if count <= 0 or not candidates:
        return []
    names = [name for name, _ in candidates]
    if bands <= 1 or len(names) <= count:
        return names[:count]
    size = max(1, len(names) // bands)
    drawn: list[str] = []
    for band in range(bands):
        start = band * size
        stop = len(names) if band == bands - 1 else start + size
        share = count // bands + (1 if band < count % bands else 0)
        pool = names[start:stop]
        drawn.extend(rng.sample(pool, min(share, len(pool))))
    # A short band leaves room; fill it from whatever is left, nearest the
    # front first, rather than returning a batch shorter than asked for.
    if len(drawn) < count:
        taken = set(drawn)
        drawn.extend(
            name for name in names if name not in taken
        )
    return drawn[:count]


LANE_MATCH: Final = 2
LANE_UNKNOWN: Final = 1
LANE_CLASH: Final = 0


def lane_match(
    candidate: tuple[set[int], set[str]],
    lane: tuple[set[int], set[str]],
    *,
    decade_slack: int = 1,
) -> int:
    """How confidently a record belongs to a lane: match, unknown, or clash.

    ``in_lane`` answers yes or no and gives an unplaceable record the
    benefit of the doubt, which is right for deciding what may play. It
    is wrong for deciding what the next hour is built from, because a
    seed carries its era into every track that follows it. So this
    separates "known to fit" from "nothing known", and the reseed prefers
    the first.

    The effect is self-adjusting by genre, which is the point. Pop albums
    are decade-tagged, so on an 80s station the genuine 80s records rank
    MATCH and a record like "Locked Out of Heaven" ranks UNKNOWN and is
    passed over for seeding while still being allowed to play. Country
    albums are largely not decade-tagged, so nearly everything ranks
    UNKNOWN, the ordering flattens, and this stops having an opinion
    rather than starting to guess.
    """
    want_decades, want_genres = lane
    got_decades, got_genres = candidate
    if not in_lane(candidate, lane, decade_slack=decade_slack):
        return LANE_CLASH
    if not (want_decades and got_decades):
        return LANE_UNKNOWN
    if want_genres and not (got_genres & want_genres):
        return LANE_UNKNOWN
    return LANE_MATCH


_INFOBOX_DATE = re.compile(
    # Up to the next field, the end of the template, or the end of what
    # we were given: an infobox is usually followed by another field, but
    # a truncated article or a fragment ends without one.
    r"\|\s*(?:released|recorded)\s*=\s*(.+?)(?=\n\s*\||\n\s*\}\}|\Z)",
    re.I | re.S,
)
_YEAR_IN_TEXT = re.compile(r"\b(1[89]\d{2}|20[0-2]\d)\b")

# Nothing before this is a recording. Guards against a year picked out of
# a composer's birth date or a citation to a nineteenth-century source.
_FIRST_RECORDED_YEAR: Final = 1890


def earliest_year(wikitext: str) -> int | None:
    """The earliest Released or Recorded year in a Wikipedia infobox.

    Both fields, because they differ and the earlier one is the truth for
    an era: Big Thief's "Spud Infinity" was recorded 2020 and released
    2022, and Hank Williams' "Hey, Good Lookin'" was cut in March 1951
    and issued that June.

    The earliest of everything found, not the first match. An infobox
    lists later releases too, and taking the first gave 1983 for "Hello
    in There", which is a 1971 song reissued as a single.

    None where the article carries no date at all, which is a real case:
    a song can have an article and no infobox dates, and the caller must
    read that as "unknown" rather than as "undated therefore modern".
    """
    years: list[int] = []
    for field in _INFOBOX_DATE.findall(wikitext or ""):
        for found in _YEAR_IN_TEXT.findall(field):
            year = int(found)
            if year >= _FIRST_RECORDED_YEAR:
                years.append(year)
    return min(years) if years else None


# Longer than this is a sentence rather than a genre: a malformed field
# can swallow half an article.
_LONGEST_GENRE: Final = 40

# Longer than this is a sentence rather than a genre name: a malformed
# field can otherwise swallow half an article.
_LONGEST_GENRE: Final = 40

_INFOBOX_GENRE = re.compile(
    r"\|\s*genre\s*=\s*(.+?)(?=\n\s*\||\n\s*\}\}|\Z)", re.I | re.S
)
_WIKI_LINK = re.compile(r"\[\[(?:[^\]|]*\|)?([^\]|]+)\]\]")
_WIKI_TEMPLATE = re.compile(r"\{\{[^}]*?\}\}")
_WIKI_REF = re.compile(r"<ref[^>]*>.*?</ref>|<ref[^>]*/>", re.S)
# Inline citation templates, which carry author surnames and page numbers
# and must be dropped whole rather than unwrapped.
_CITATION = re.compile(
    r"\{\{\s*(?:sfn|sfnp|harv\w*|cite\w*|r|efn|refn|ref\w*)\b[^{}]*\}\}", re.I
)


def year_span(years: Iterable[int]) -> str:
    """The era a batch actually covers, as a person would write it.

    The one number that says whether the era rule is holding. A batch
    reading 1971-1989 is a station; the same batch reading 1951-2016 is
    the drift this was all built to stop.

    Deliberately the span of what is *known* rather than of the batch.
    Years are missing for plenty of records and a missing year has to
    mean unknown, so the count of how many are known is reported beside
    this and the two are read together: a tight span over three tracks
    says very little.
    """
    found = sorted({int(year) for year in years if year})
    if not found:
        return ""
    if found[0] == found[-1]:
        return str(found[0])
    return f"{found[0]}-{found[-1]}"


def infobox_genres(wikitext: str) -> set[str]:
    """What a song's own Wikipedia infobox calls it.

    Better evidence than an album's Last.fm tags for the same reason the
    year is: this describes the record, where album tags describe
    whichever compilation the track was filed under. "Hey, Good Lookin'"
    is country on its own article and untagged on the compilation Last.fm
    files it against.

    Markup is stripped rather than parsed. A genre field is written every
    way a wiki allows: "[[Country music|Country]]", a hlist template, a
    plain comma-separated line, any of them trailed by citations.
    """
    field = _INFOBOX_GENRE.search(wikitext or "")
    if not field:
        return set()
    text = _WIKI_REF.sub(" ", field.group(1))
    # Citations go before anything else unwraps them. A genre field is
    # often sourced inline, and keeping the contents turned the authors
    # of a Hank Williams biography into genres called "escott" and
    # "macewen".
    text = _CITATION.sub(" ", text)
    text = _WIKI_LINK.sub(r"\1", text)
    # Remaining templates wrap lists: drop the wrapper, keep the
    # pipe-separated contents it was holding.
    text = text.replace("{{", " ").replace("}}", " ")
    text = re.sub(r"\b(?:hlist|flatlist|plainlist|nowrap|ubl)\b", " ", text, flags=re.I)
    found = set()
    for part in re.split(r"[,|/\n]+", text):
        # Normalised exactly as ``lane_of`` normalises a Last.fm tag, and
        # no further. Folding punctuation here would turn "synth-pop"
        # into "synthpop" and it would then never match the Last.fm tag
        # of the same name, which is the whole point of collecting it.
        # A wiki list writes each entry as a bullet, which survives the
        # newline split as a leading marker.
        name = part.strip().lstrip("*#:;").strip().lower()
        if name and not name.isdigit() and len(name) <= _LONGEST_GENRE:
            found.add(name)
    return found


_INFOBOX_ARTIST = re.compile(
    r"\|\s*artist\s*=\s*(.+?)(?=\n\s*\||\n\s*\}\}|\Z)", re.I | re.S
)

# Longest credit worth keeping. A malformed field can run to the rest of
# the article, and nothing useful is decided past this.
_LONGEST_CREDIT: Final = 120

# Words that carry no identity when matching one credit against another.
# Without them "The Beatles" would not match "Beatles", and "Elton John"
# would not match "Elton John and Dua Lipa".
_CREDIT_NOISE: Final = frozenset(
    {"the", "a", "an", "and", "featuring", "feat", "ft", "with", "vs", "duet"}
)


def infobox_artist(wikitext: str) -> str:
    """Who the song's own Wikipedia infobox says recorded it.

    Read for one reason: to tell whether the article we found is about
    the recording we asked about or about the song somebody else wrote
    first. See ``performs``.
    """
    field = _INFOBOX_ARTIST.search(wikitext or "")
    if not field:
        return ""
    text = _WIKI_REF.sub(" ", field.group(1))
    text = _CITATION.sub(" ", text)
    text = _WIKI_LINK.sub(r"\1", text)
    text = text.replace("{{", " ").replace("}}", " ")
    return " ".join(text.split())[:_LONGEST_CREDIT]


def _credit_words(name: str) -> set[str]:
    """The words of a credit that carry identity."""
    return {
        word for word in _folded(name).split() if word and word not in _CREDIT_NOISE
    }


def performs(credited: str, performer: str) -> bool:
    """Whether an article's performer is who the provider credited.

    This is what tells a recording from the song, and without it the era
    data is quietly wrong on every cover. Searching "a little respect
    Wheatus" returns the article *A Little Respect*, which is about
    Erasure's 1988 record and mentions the cover in its body. The title
    matches exactly so it wins the search, and its infobox then dates a
    2000 recording to 1988. Observed in one real batch alongside
    Counting Crows' "Big Yellow Taxi", dated to Joni Mitchell's 1970
    original, which between them reported a 1990s indie hour as spanning
    1970 to 2006.

    Compared word by word rather than as strings, because a substring
    test says Ash performs Richard Ashcroft's records. Every word of the
    credit that carries identity has to appear on the other side, in
    either direction, so "The Beatles" matches "Beatles" and "Elton
    John" matches "Elton John and Dua Lipa".

    An article with no artist field cannot answer, and answers yes.
    Most of them have one, and refusing every article that does not
    would cost far more years than covers ever will.
    """
    if not performer:
        return True
    wanted = _credit_words(credited)
    found = _credit_words(performer)
    if not wanted or not found:
        return True
    return wanted <= found or found <= wanted


def best_article(results: Sequence[str], title: str, artist: str) -> str:
    """Which search result is the article for this recording.

    Searching is not optional. A direct title lookup for "Hey Good
    Lookin'" resolves to a real but different article carrying no dates,
    which is indistinguishable from a genuine gap and is how three
    separate attempts concluded the data did not exist. The search for
    the same phrase plus the artist puts "Hey, Good Lookin' (song)"
    first.

    Prefers a result whose name carries the song disambiguator, then one
    matching the title once punctuation is folded, then the top hit.
    Rejects a result that is merely the artist's own page, which is what
    comes back when a track has no article of its own.
    """
    if not results:
        return ""
    wanted = _folded(title)
    performer = _folded(artist)
    scored: list[tuple[int, str]] = []
    for name in results:
        folded = _folded(name)
        if folded == performer:
            continue  # the artist's page, not the song's
        rank = 0
        if wanted and wanted in folded:
            rank += 2
        if "song" in name.lower() or "single" in name.lower():
            rank += 1
        scored.append((rank, name))
    if not scored:
        return ""
    best = max(scored, key=lambda pair: pair[0])
    return best[1] if best[0] else scored[0][1]


def crowd_pool(
    crowd: Sequence[tuple[str, str, float]],
    seed_artist: str,
    limit: int,
) -> tuple[list[tuple[str, float]], dict[str, list[str]]]:
    """Turn a song's crowd into an artist pool and the records it wants.

    Returns the same ``(name, match)`` pairs the artist graph returns, so
    everything downstream is unchanged, plus the titles the crowd asked
    for from each artist. Those titles are what fixes the defect: the
    artist graph names a neighbour and then leaves the provider's
    relevance ranking to pick the song, which is how "Summer Madness"
    reached a Michael Jackson station instead of "Cherish".

    An artist keeps the match score of the first song of theirs the crowd
    offered, and their titles accumulate in crowd order, so Cyndi Lauper
    appearing twice arrives with two records to choose between rather
    than as two pool entries.

    The seed's own tracks are dropped. Every crowd is topped by them, and
    on a giant it is not only the seed: a "Man in the Mirror" crowd opens
    with two Michael Jackson records, then his brothers. The seed gets its
    share of the batch from the seed lean, not from the crowd.
    """
    ordered: list[tuple[str, float]] = []
    titles: dict[str, list[str]] = {}
    seen: dict[str, str] = {}
    for who, title, match in crowd:
        name = who.strip()
        if not name or not title.strip():
            continue
        if _same_artist(name, seed_artist):
            continue
        key = name.lower()
        if key not in seen:
            if len(ordered) >= limit > 0:
                continue
            seen[key] = name
            ordered.append((name, match))
            titles[name] = []
        wanted = titles[seen[key]]
        if title not in wanted:
            wanted.append(title)
    return ordered, titles


def prefer_titles(tracks: list[Any], wanted: Sequence[str]) -> list[Any]:
    """Move the records the crowd asked for to the front of an artist's list.

    A reordering rather than a filter, deliberately. The crowd names a
    record, and the provider may not carry it under that spelling or at
    all; dropping everything else would then leave the artist
    contributing nothing, which is the failure mode that made a silently
    empty pool so hard to see (0.25.1). Anything the crowd did not name
    keeps its provider order behind those it did.

    Matched on ``base_title`` so a remaster, a single version or a
    parenthesised subtitle still counts as the record asked for.
    """
    if not wanted:
        return tracks
    order = {base_title(title): index for index, title in enumerate(wanted)}
    if not order:
        return tracks
    return sorted(
        tracks,
        key=lambda track: order.get(base_title(getattr(track, "name", "")), len(order)),
    )


def usable_songs(
    known: Sequence[tuple[str, int]] | None, share: float
) -> int:
    """How many of an artist's songs a station can play before it is past
    their hits.

    Counts down their ranking while each song still reaches ``share`` of
    their biggest, so it is measured against the artist rather than
    against the station and genre cancels out. Hank Williams Jr's biggest
    song has 38,490 listeners and his curve is flat: 83%, 65%, 42%, 31%,
    18% at positions 2, 3, 5, 10 and 20, so he keeps his catalogue where
    an absolute threshold would erase it.

    Measured on real curves, 2026-09-15. At a 10% share the one-hit
    wonders collapse to exactly one song each, Dexys' second being 4% of
    their first, Norman Greenbaum's 1%, The Knack's 6%; while The Beatles
    hold seventy-five and Michael Jackson thirty-eight. That is what the
    caller wants it for: an act with one record retires after playing it,
    and an act with fifty can be returned to all evening.

    Run it loose. It only decides whether an artist has anything left,
    never which record plays, and a tight bar penalises an artist whose
    first song is enormous: a-ha's "Take on Me" has 2.9 million
    listeners, which leaves their genuinely well-known second at 11%.

    Zero when nothing is known, meaning "no opinion", not "nothing left".
    """
    if not known:
        return 0
    biggest = max((count for _, count in known), default=0)
    if biggest <= 0:
        return 0
    kept = 0
    for _, count in known:
        if count / biggest < share:
            break
        kept += 1
    return kept


def song_shares(
    title_by_uri: Mapping[str, str],
    known: Sequence[tuple[str, int]] | None,
) -> dict[str, float]:
    """Each song's listeners as a fraction of its artist's biggest song.

    The figure the tiering wants and used to guess at. Genre-neutral by
    construction, because the numerator and denominator are the same
    artist: Hank Williams Jr's biggest song has 38,490 listeners and his
    curve is as flat as a giant's, so measuring him against himself gives
    him his catalogue where any absolute threshold would erase it.

    Titles the two services spell differently are simply absent from the
    result, which leaves the caller on its geometric guess for those. The
    same base-title folding as ``too_deep``, so a remaster matches the
    record it is a remaster of.
    """
    if not known:
        return {}
    listeners: dict[str, int] = {}
    for title, count in known:
        key = base_title(title)
        if key:
            listeners[key] = max(count, listeners.get(key, 0))
    if not listeners:
        return {}
    biggest = max(listeners.values())
    if biggest <= 0:
        return {}
    shares: dict[str, float] = {}
    for uri, title in title_by_uri.items():
        count = listeners.get(base_title(title))
        if count:
            shares[uri] = count / biggest
    return shares


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
    cut: set[str] = set()
    for track in tracks:
        position = rank.get(track.uri)
        title = base_title(track.name)
        if position is None or title in biggest or listeners.get(title, 0) >= bar:
            continue
        if position < a_tracks and title not in listeners:
            # A title Last.fm has never seen, high in the provider's own
            # order, is usually the two services spelling one record
            # differently rather than a song nobody knows. Tidal writes
            # "Beethoven: Symphony No. 5 in C Minor, Op. 67: I. Allegro con
            # brio" where Last.fm drops the composer, and cutting on that
            # took the famous recordings. A title Last.fm does list, below
            # the bar, is judged on its listeners as everything else is.
            continue
        cut.add(track.uri)
    return cut
