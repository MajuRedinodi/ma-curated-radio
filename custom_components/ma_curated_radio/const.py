"""Constants for the Music Assistant Curated Radio integration."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

DOMAIN: Final = "ma_curated_radio"
MA_DOMAIN: Final = "music_assistant"

# --- Config entry keys -------------------------------------------------------

CONF_PLAYER: Final = "player"
# The player's entity registry id, which a rename does not change. The
# entity_id above is what everything targets, but it is not stable: renaming
# the Music Assistant player left this integration watching a name nothing
# would ever report again, with no error and no batch ever built.
CONF_PLAYER_REGISTRY_ID: Final = "player_registry_id"
CONF_MA_CONFIG_ENTRY_ID: Final = "ma_config_entry_id"
CONF_LASTFM_API_KEY: Final = "lastfm_api_key"

# --- Options keys ------------------------------------------------------------

CONF_MAX_ARTISTS: Final = "max_artists"
CONF_TRACKS_PER_ARTIST: Final = "tracks_per_artist"
CONF_REFILL_THRESHOLD: Final = "refill_threshold"
CONF_HISTORY_MINUTES: Final = "history_minutes"
CONF_SETTLE_SECONDS: Final = "settle_seconds"
CONF_COOLDOWN_ENTITY: Final = "cooldown_entity"
CONF_COOLDOWN_SECONDS: Final = "cooldown_seconds"
CONF_PROVIDER_FILTER: Final = "provider_filter"
CONF_FILTER_LIVE: Final = "filter_live"
CONF_FILTER_REMIX: Final = "filter_remix"
CONF_SEED_FROM_SONG: Final = "seed_from_song"
CONF_FILTER_HOLIDAY: Final = "filter_holiday"

# --- Defaults ----------------------------------------------------------------

DEFAULT_MAX_ARTISTS: Final = 3
DEFAULT_TRACKS_PER_ARTIST: Final = 3
DEFAULT_REFILL_THRESHOLD: Final = 2
DEFAULT_HISTORY_MINUTES: Final = 120
# How long a song counts as already heard today. Inside the repeat window
# above it cannot play at all; after that, only once its artist has nothing
# fresh left. A four-hour Don Henley morning replayed thirteen of its first
# hour's nineteen songs at 11:08, because the two-hour window had let them
# go and each returning artist started again from their biggest song.
HEARD_MINUTES: Final = 480
DEFAULT_SETTLE_SECONDS: Final = 3
DEFAULT_COOLDOWN_SECONDS: Final = 120
DEFAULT_PROVIDER_FILTER: Final = ""
DEFAULT_FILTER_LIVE: Final = True
# Off by default: a remix is sometimes the version people know, and the one
# that jarred (Elton John and Dua Lipa's "Cold Heart" in an hour of 70s rock)
# is the only version of that song there is.
DEFAULT_FILTER_REMIX: Final = False
DEFAULT_FILTER_HOLIDAY: Final = True

# Seed a station from the songs people play alongside the one picked,
# rather than from the artists people play alongside its artist. On by
# default: the artist graph names a neighbour and leaves the provider's
# relevance ranking to choose the record, which is how a Michael Jackson
# station came to play Kool & the Gang's "Summer Madness" rather than
# "Cherish". Turning it off restores the 0.39 behaviour exactly, which is
# a faster A/B than reinstalling and covers the case where a lane is too
# thin for a crowd to exist.
DEFAULT_SEED_FROM_SONG: Final = True

# How many of a song's neighbours to ask for. Last.fm serves well past
# 100 (237 measured on one track), but the far tail drifts off-lane and
# the filters are what keep the near tail usable, so this is the depth
# worth paying for rather than the depth available.
CROWD_SIZE: Final = 100

# How big one of an artist's songs has to be, against their own biggest,
# to count as a record they are still known for. Only ever decides
# whether an act has anything left to play tonight, never which record
# plays, so it runs loose: a tight bar punishes an artist whose first
# song is enormous, and a-ha's second lands at 11% behind a "Take on Me"
# with 2.9 million listeners. At this figure the one-hit wonders measured
# on 2026-09-15 keep exactly one song each, and The Beatles keep dozens.
USABLE_SHARE: Final = 0.05

# How many similar artists to ask Last.fm for, regardless of how many end
# up in a batch. Last.fm ranks by match score, and the goal is a station
# format rather than an artist's three nearest neighbours, so the shuffle
# should draw from the whole adjacent field. Tying this to the cap made
# repeated batches off one seed converge on the same few faces.
LASTFM_POOL_SIZE: Final = 25

# How many tracks to ask the provider for per artist.
#
# Music Assistant's search action takes no limit and returns five, which
# for a whole session was the real constraint on every batch: the seed
# contributed its entire catalogue in one go and then vanished from every
# refill, because a title that just played is excluded and there was
# nothing behind it. Artist radio drifted off its own seed by the second
# batch, and the seed-lean multiplier could never bite because five tracks
# minus the filters rarely reached the cap it was multiplying.
#
# This deliberately does not change what a first batch plays. Selection
# still takes the top few in the provider's own relevance order, so the
# extra depth is only ever reached by a later batch that has already used
# the obvious hits. That is exactly where an artist station needs somewhere
# left to go.
SEARCH_LIMIT: Final = 25

# How many credited artists make a track worth re-joining before asking
# Last.fm about it. Two names is a duo the provider may have split; three
# or more is a collaboration or a supergroup, where the first credit is
# already the act and joining the rest would invent a name nobody uses.
SPLIT_DUO_CREDITS: Final = 2

# How much of the first credit's audience the pair must hold before the
# pair is treated as the act. Measured cases sit nowhere near the line:
# Sonny & Cher draw 2.9 times "Sonny" alone, while Lady Gaga & Beyonce
# draw 0.006 of Lady Gaga alone. Parity is simply the midpoint of a gap
# three orders of magnitude wide, not a tuned figure.
PAIR_LISTENER_RATIO: Final = 1.0

# --- Programming the hour ------------------------------------------------

# How much of an artist's size a track keeps per position down that
# artist's own ordering. Between 0.6 and 0.8 the tier estimate barely
# changes, so this is not a tuned constant; it only has to fall.
TIER_DECAY: Final = 0.7

# How many of an artist's best-known songs to fetch from Last.fm for the
# depth limit. A provider search returns 25, and the Beatles' hundredth song
# on Last.fm is still well known, so a hundred covers every song a search
# can offer that could clear the bar.
DEPTH_TOP_TRACKS: Final = 100

# Drop a neighbour whose audience is below this share of the pool's own
# median. Christine McVie arrived at 2% of her pool's median and gave a
# Fleetwood Mac station three tracks nobody knew; across four observed
# pools the next lowest artist was 12%, so this sits in open space.
# Zero disables the floor entirely.
DEFAULT_POPULARITY_FLOOR: Final = 10
CONF_POPULARITY_FLOOR: Final = "popularity_floor"

# Placeholder option for the release dropdowns. A select entity with an
# empty option list cannot render, and "nothing to release" is a state
# worth showing rather than an empty control that looks broken.
NOTHING_REMEMBERED: Final = "Nothing to release"

# --- Batch modes -------------------------------------------------------------

MODE_REPLACE: Final = "replace"
MODE_REFILL: Final = "refill"
MODES: Final = [MODE_REPLACE, MODE_REFILL]

# --- Services ----------------------------------------------------------------

SERVICE_RUN_BATCH: Final = "run_batch"
ATTR_MODE: Final = "mode"
ATTR_CONFIG_ENTRY_ID: Final = "config_entry_id"

# Where users get the API key the config flow asks for. Linked from the
# setup form, since a key nobody can find is a key nobody enters.
LASTFM_SIGNUP_URL: Final = "https://www.last.fm/api/account/create"

# --- Listener feedback -------------------------------------------------------

CONF_SEED_LEAN: Final = "seed_lean"
CONF_MAX_CONSECUTIVE: Final = "max_consecutive"
CONF_TRACK_SUPPRESS_DAYS: Final = "track_suppress_days"
CONF_ARTIST_MUTE_DAYS: Final = "artist_mute_days"
CONF_ARTIST_STRIKE_LIMIT: Final = "artist_strike_limit"

# Station style governs two things at once: how much of a batch the seed
# artist gets, and how far a session may wander from where it started.
# They are one control because a mode that differs on only one of them is
# not a different kind of station.
SEED_LEAN_ARTIST: Final = "artist"
SEED_LEAN_BALANCED: Final = "balanced"
SEED_LEAN_DISCOVERY: Final = "discovery"
SEED_LEANS: Final = [SEED_LEAN_ARTIST, SEED_LEAN_BALANCED, SEED_LEAN_DISCOVERY]
SEED_LEAN_MULTIPLIER: Final = {
    SEED_LEAN_ARTIST: 2.0,
    SEED_LEAN_BALANCED: 1.5,
    SEED_LEAN_DISCOVERY: 1.0,
}

# "format" was the old name for what is now discovery: even seed share,
# no limit on wandering. Same behaviour, so old entries carry over.
LEGACY_SEED_LEANS: Final = {"format": SEED_LEAN_DISCOVERY}

DEFAULT_SEED_LEAN: Final = SEED_LEAN_BALANCED

# Batch shape, per station style, because the two want opposite things.
# Artist radio is a showcase: few neighbours, several tracks each, and a
# seed lean that doubles the seed's share on top. Balanced is a station:
# many neighbours, two tracks each, so no single act dominates and one
# weak neighbour is diluted rather than becoming a run of duds. Measured
# in use, moving Balanced from 3/3 to 8/2 dropped the seed from 36% of an
# hour to 18% and was the single biggest improvement to how it sounds.
#
# A value set on the dashboard is written against the style that is
# selected at the time, so tuning one style cannot quietly wreck another.
CONF_STYLE_SETTINGS: Final = "style_settings"

# How many tracks a batch actually plays, as opposed to how many it drew
# to choose from. Zero plays everything drawn, which is what the
# integration did before this existed.
#
# Nineteen is about ninety minutes, which is a comfortable chunk before
# the station reseeds and moves on.
#
# Separating the two is what lets depth be tuned without lengthening the
# hour. Tracks per artist used to do both jobs at once, so reaching an
# artist's third track also took a batch from 19 tracks to 29, and a
# longer batch reseeds less often. Drawing three each and playing 19
# gives the same hour with the deeper tracks landing in the slots that
# want them.
CONF_BATCH_LENGTH: Final = "batch_length"
STYLE_DEFAULTS: Final = {
    SEED_LEAN_ARTIST: {
        CONF_MAX_ARTISTS: 3,
        CONF_TRACKS_PER_ARTIST: 3,
        CONF_BATCH_LENGTH: 0,
    },
    # Twelve artists at two tracks each, rather than eight at three.
    # Power comes from breadth and not from depth: a record is Power when
    # it is one of the ones its artist is known for, which is mostly
    # their first and sometimes their second, so twelve Powers in an hour
    # needs about twelve artists and no pattern can conjure a thirteenth
    # out of eight. Drawing 24 to play 20 is the same search volume as
    # eight at three, spent on breadth instead. The same move from three
    # artists to eight was the single biggest improvement to how this
    # sounded, measured by ear on 2026-09-10.
    SEED_LEAN_BALANCED: {
        CONF_MAX_ARTISTS: 12,
        CONF_TRACKS_PER_ARTIST: 2,
        CONF_BATCH_LENGTH: 20,
    },
    SEED_LEAN_DISCOVERY: {
        CONF_MAX_ARTISTS: 8,
        CONF_TRACKS_PER_ARTIST: 3,
        CONF_BATCH_LENGTH: 20,
    },
}

# The music clock each station style is built to, one letter per slot,
# repeating. The letters are filters.TIER_* and a test holds them to it;
# they are spelled out here because this is where per-style settings
# live and filters.py deliberately imports nothing.
#
# Three rules out of commercial radio practice, which all three clocks
# keep:
#
#   1. Every block opens on a Power. Radio does this because ratings were
#      credited in quarter hours, so the strongest record went right
#      after :00, :15, :30 and :45. The habit outlived the reason: an
#      hour that opens strongly and softens in the middle holds up.
#   2. No two unfamiliar records are ever adjacent. A Deep or a Gold has
#      a Power either side of it. Two in a row is how a listener leaves.
#   3. The hour closes on a Power. Terciles used to put the remainder in
#      Deep, so a batch ended on its weakest material.
#
# Balanced is 12 Power, 5 Secondary, 2 Deep and 1 Gold across 20 slots,
# which is 60/25/10/5. Everything except the Deeps is a record somebody
# would recognise, so the hour is 90% familiar, which is the target this
# whole project has been aimed at.
#
# Because tiers are now absolute rather than terciles, a clock is a
# ceiling and not a quota: asking for Deep in a pool of nothing but hits
# falls back to Secondary rather than demoting a hit to fill the slot.
# That is why Discovery can ask for a third and get less.
STYLE_CLOCK: Final = {
    # A showcase, so depth is the point rather than a cost. One Deep
    # every six, still Power-led.
    SEED_LEAN_ARTIST: ["P", "S", "P", "D", "S", "P"],
    SEED_LEAN_BALANCED: [
        "P", "S", "P", "P", "D",
        "P", "S", "P", "P", "S",
        "P", "S", "P", "P", "G",
        "P", "S", "P", "D", "P",
    ],
    # Asks for as much depth as the pool can honestly supply, which on a
    # pool of hits is none: a clock is a ceiling now, not a quota.
    SEED_LEAN_DISCOVERY: ["P", "S", "D", "P", "S", "D", "S", "P"],
}
DEFAULT_MAX_CONSECUTIVE: Final = 2
DEFAULT_TRACK_SUPPRESS_DAYS: Final = 30
DEFAULT_ARTIST_MUTE_DAYS: Final = 30
DEFAULT_ARTIST_STRIKE_LIMIT: Final = 3

# A track abandoned with more than this long left was skipped, not finished.
# Generous enough that a fade-out or trailing silence does not read as a
# skip, tight enough that bailing out of the last chorus does.
SKIP_GRACE_SECONDS: Final = 15.0

# There was a figure here for telling a run of skips apart from a verdict,
# because two skips at 1am from a house full of kids had suppressed two
# songs for a month. It is gone along with everything else that read a
# skip as a judgement: a skip is now only a skip, and the judgement is a
# button somebody has to mean to press.

# How far the elapsed time has to jump backwards before the song counts as
# having started again rather than drifted. Small, because the figure is
# worked out from the position and its timestamp and is accurate to well
# under a second; it only has to clear the case of a song re-picked in its
# own opening moments, where there is nothing to tell a restart from noise.
RESTART_TOLERANCE_SECONDS: Final = 3.0

# --- Entities ----------------------------------------------------------------

CONF_ENABLED: Final = "enabled"
DEFAULT_ENABLED: Final = True

SERVICE_UNMUTE_ARTIST: Final = "unmute_artist"
SERVICE_ALLOW_TRACK: Final = "allow_track"
SERVICE_SEARCH: Final = "search"
SERVICE_FORGET_FEEDBACK: Final = "forget_feedback"
ATTR_ARTIST: Final = "artist"
ATTR_TRACK: Final = "track"
ATTR_QUERY: Final = "query"
ATTR_LIMIT: Final = "limit"

# How many results a free-text search returns by default. The action
# Music Assistant exposes returns five with no way to ask for more, which
# is too few to find a particular recording of a well-covered song.
DEFAULT_SEARCH_RESULTS: Final = 20


def signal_update(entry_id: str) -> str:
    """Dispatcher signal telling this entry's entities to re-read state."""
    return f"{DOMAIN}_update_{entry_id}"

# --- Playlist building -------------------------------------------------------

SERVICE_BUILD_PLAYLIST: Final = "build_playlist"
ATTR_NAME: Final = "name"
ATTR_SEED_ARTIST: Final = "seed_artist"
ATTR_LENGTH: Final = "length"
ATTR_PROVIDER: Final = "provider"

DEFAULT_PLAYLIST_NAME: Final = "Curated Radio"
DEFAULT_PLAYLIST_LENGTH: Final = 50

# Tracks are appended in chunks rather than one call, since a long build
# would otherwise be a single very large request.
PLAYLIST_CHUNK: Final = 25

# Ceiling on reseed rounds, so an artist whose neighbours all come back
# empty cannot spin forever chasing a length it will never reach.
PLAYLIST_MAX_ROUNDS: Final = 25

# --- Drift rails -------------------------------------------------------------

CONF_DEGREES: Final = "degrees"

# Degrees of separation from the artist that started the session, in the
# Six Degrees of Kevin Bacon sense. Observed drift on a real build ran
# Taylor Swift, Maisie Peters, Lorde, Katy Perry, Ke$ha, Selena Gomez,
# Anitta. Three stops it at Katy Perry, which is still a station that
# plays Taylor Swift. Six is Brazilian funk.
DEFAULT_DEGREES: Final = 3

# A session is the run of listening since a manual pick. After this long
# without a batch, the next one starts fresh rather than staying anchored
# to whatever was playing yesterday.
SESSION_EXPIRY_HOURS: Final = 6

# --- Track quality -----------------------------------------------------------

CONF_MIN_DURATION: Final = "min_duration"

# Seconds. Under this, a track is almost certainly commentary, an
# interlude or a skit rather than a song. Search returns them alongside
# the real tracks, because they sit in the same catalogue.
DEFAULT_MIN_DURATION: Final = 90

# --- Familiarity -------------------------------------------------------------

CONF_FAMILIARITY: Final = "familiarity"

# Last.fm ranks similar artists by match score, which tracks how well known
# they are. Sampling that list uniformly, which is what a flat shuffle
# does, fills a batch with defensible neighbours nobody recognises. The
# exponent biases selection toward the top without making the tail
# unreachable.
FAMILIARITY_FAMILIAR: Final = "familiar"
FAMILIARITY_BALANCED: Final = "balanced"
FAMILIARITY_ADVENTUROUS: Final = "adventurous"
FAMILIARITIES: Final = [
    FAMILIARITY_FAMILIAR,
    FAMILIARITY_BALANCED,
    FAMILIARITY_ADVENTUROUS,
]
# Exponents are gentler than they look. Last.fm match scores fall away
# fast, so squaring already gives the closest artist roughly a hundred to
# one over the far tail. Going higher makes the tail unreachable, which
# would make the deep pool pointless.
FAMILIARITY_EXPONENT: Final = {
    FAMILIARITY_FAMILIAR: 2.0,
    FAMILIARITY_BALANCED: 1.0,
    FAMILIARITY_ADVENTUROUS: 0.0,
}

# The premise is recognisable songs, so this leans that way by default.
DEFAULT_FAMILIARITY: Final = FAMILIARITY_FAMILIAR

# --- Explicit content --------------------------------------------------------

CONF_EXPLICIT: Final = "explicit"

# The two directions are not symmetrical. A clean edit is usually a
# separately titled release ("Forget You" for "Fuck You"), so nothing links
# it to the original as a version. Excluding explicit tracks therefore
# works as a hard filter, but preferring them can only be a sort: put the
# explicit ones first and the clean edit falls outside the per-artist cut.
EXPLICIT_ANY: Final = "any"
EXPLICIT_CLEAN: Final = "clean"
EXPLICIT_PREFER: Final = "prefer"
EXPLICIT_MODES: Final = [EXPLICIT_ANY, EXPLICIT_CLEAN, EXPLICIT_PREFER]

DEFAULT_EXPLICIT: Final = EXPLICIT_ANY

# How many recently enqueued track URIs to remember. Used to tell our own
# music apart from a genuine manual pick: a track we queued is never a
# pick, however the expected-next comparison lands. Comfortably more than
# any queue this builds.
QUEUED_MEMORY: Final = 500

# --- Bulk loads --------------------------------------------------------------

CONF_BULK_TRACKS: Final = "bulk_tracks"

# A manual pick is one track. A playlist or album load is several at once,
# and is a deliberate choice to hear that playlist rather than an
# invitation to replace it.
#
# The threshold can sit this low because tracks we queued ourselves are
# already excluded before it is consulted, so the only distinction left to
# draw is one track against several. Picking a single track adds one, or
# replaces the queue and shrinks it. Three therefore protects even a very
# short playlist, which matters: not every playlist runs to hundreds.
# Zero disables the check.
DEFAULT_BULK_TRACKS: Final = 3


def style_value(options: Mapping[str, Any], style: str, key: str) -> int:
    """Read one batch-shape setting for a station style.

    Three places to look, in order: a value saved against this style, a
    value from before styles had their own (which applies to all of them,
    so an existing install keeps behaving as it did), then this style's
    default.
    """
    per_style = options.get(CONF_STYLE_SETTINGS) or {}
    saved = (per_style.get(style) or {}).get(key)
    if saved is not None:
        return int(saved)
    legacy = options.get(key)
    if legacy is not None:
        return int(legacy)
    return int(STYLE_DEFAULTS[style][key])


def with_style_value(
    options: Mapping[str, Any], style: str, key: str, value: int
) -> dict[str, Any]:
    """Return options with one setting saved against one style.

    The pre-style value is deliberately left in place. It is the fallback
    for every style that has not been set yet, so removing it here would
    silently move the others onto defaults.
    """
    per_style = {name: dict(values) for name, values in (options.get(CONF_STYLE_SETTINGS) or {}).items()}
    per_style.setdefault(style, {})[key] = int(value)
    return {**options, CONF_STYLE_SETTINGS: per_style}

# The station in progress, saved so a restart does not end it: where it
# started, the last batch's artists and lead, and recent titles. Written a
# few seconds after each batch, batched with any other change.
STATION_STORAGE_VERSION: Final = 1
STATION_SAVE_DELAY: Final = 10

# --- What is known about a record ---------------------------------------

# One store for every player, rather than one per config entry. A release
# year is a fact about a record, not about a room, so the living room and
# the phone would otherwise each pay to learn it. The consequence is that
# removing a player must not delete this file, which async_remove_entry
# has to know about.
FACTS_STORAGE_KEY: Final = f"{DOMAIN}.music_facts"

# The schema version, carried from the first write. Adding a field never
# needs it, because every read defaults and a record written before a
# field existed simply reads as not knowing it. It is here for the changes
# that do break old data: renaming the key format, changing what a field
# means, or dropping one something still reads. The skip memory shipped
# without one and its shape can therefore never change.
#
# Raised to 2 when the year gained a condition it did not have before:
# that the article it came from is about this recording and not about the
# song as somebody else first made it. Every version 1 year was written
# without that check, so the whole file is discarded rather than trusted.
# See _FactsStore in __init__.py.
FACTS_STORAGE_VERSION: Final = 2

# Longer than the station's ten seconds, because this file grows while
# the station's does not, and one write per batch is plenty. Store
# rewrites the whole file on every save, so the delay is what keeps a
# batch's twenty lookups down to a single write.
FACTS_SAVE_DELAY: Final = 30

# How long a failed lookup stays believed, and why one failed, both live
# in facts.py alongside the record they describe. That module imports
# nothing from this integration so the rules can be tested without Home
# Assistant, which is the same reason decide.py and session.py hold their
# own figures.

# How many records one batch may look up for the first time. Everything
# past a budget falls back to what album tags say, as it did before this
# existed, and is looked up by a later batch instead. A first batch on an
# empty store would otherwise want a lookup for every candidate it
# considers, including the ones it goes on to reject.
#
# Two budgets rather than one, and the split is the point. Shared, the
# work happened in the wrong order: selection checks the lane of every
# candidate first, including the ones it rejects, so it spent the whole
# allowance before the batch it had just chosen was dated at all. A
# Smiths refill on 16 Sep came back with twelve of fourteen tracks dated
# and the two missing were "Only You" and "Just Can't Get Enough", which
# Wikipedia covers exhaustively. They were not looked up because nothing
# was left to look them up with.
#
# So the records that will actually play get their own allowance, large
# enough that a full batch always fits, and selection gets a separate
# one it cannot overspend. Degrading is not symmetrical either: a lane
# check with no year still has album tags and still works, just less
# accurately, while a queued record with no year has nothing to show.
LANE_LOOKUPS_PER_BATCH: Final = 20
PLAYED_LOOKUPS_PER_BATCH: Final = 30

# --- Letting a station repeat itself -------------------------------------

# How far a station may fall below where it started before records it has
# already played are allowed back in, as a percentage.
#
# Jeff's figure, set by ear across one long session and deliberately a
# setting rather than a constant.
# because there is not yet the evidence to fix it. Two sessions have been
# watched. A Britpop evening fell 67% and sounded wrong; five hours of
# country fell 46% and sounded right, then recovered to *above* where it
# started. So the number is a starting point to be listened against, not
# a measurement.
#
# Measured against the session's own opening batch, which makes it
# genre-neutral: half of where this station started means the same thing
# in country as in rock, where absolute listener counts never do. And
# judged on the batch about to be queued rather than the one just played,
# or the correction arrives an hour after the hour it was meant to fix.
CONF_REPLAY_DROP: Final = "replay_drop"
DEFAULT_REPLAY_DROP: Final = 55

# How many already-played records one batch may bring back once a station
# has degraded past CONF_REPLAY_DROP. Three of twenty, in whatever slots
# the clock gives them, which is a seasoning rather than a rerun.
#
# The figure to be careful with. A four-hour Don Henley morning replayed
# thirteen of its first hour's nineteen songs at 11:08, which is what
# happens when repeats are allowed without a cap, and it is the single
# worst thing this has ever done to an evening.
REPLAYS_PER_BATCH: Final = 3
