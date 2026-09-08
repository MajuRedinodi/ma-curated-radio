"""Constants for the Music Assistant Curated Radio integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "ma_curated_radio"
MA_DOMAIN: Final = "music_assistant"

# --- Config entry keys -------------------------------------------------------

CONF_PLAYER: Final = "player"
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
CONF_FILTER_HOLIDAY: Final = "filter_holiday"
CONF_USE_NATIVE_TOP_TRACKS: Final = "use_native_top_tracks"

# --- Defaults ----------------------------------------------------------------

DEFAULT_MAX_ARTISTS: Final = 3
DEFAULT_TRACKS_PER_ARTIST: Final = 3
DEFAULT_REFILL_THRESHOLD: Final = 2
DEFAULT_HISTORY_MINUTES: Final = 120
DEFAULT_SETTLE_SECONDS: Final = 3
DEFAULT_COOLDOWN_SECONDS: Final = 120
DEFAULT_PROVIDER_FILTER: Final = ""
DEFAULT_FILTER_LIVE: Final = True
DEFAULT_FILTER_HOLIDAY: Final = True
# Off by default, and the name is a trap. Music Assistant's
# get_artist_tracks returns an artist's track CATALOGUE, not a popularity
# ranking, so enabling this fills batches with album tracks: Bob Seger
# without Night Moves, Jimmy Buffett without Margaritaville, and the
# commentary tracks off a deluxe edition. Relevance-ranked search is a
# worse-sounding idea and a better-sounding result.
DEFAULT_USE_NATIVE_TOP_TRACKS: Final = False

# How many similar artists to ask Last.fm for, regardless of how many end
# up in a batch. Last.fm ranks by match score, and the goal is a station
# format rather than an artist's three nearest neighbours, so the shuffle
# should draw from the whole adjacent field. Tying this to the cap made
# repeated batches off one seed converge on the same few faces.
LASTFM_POOL_SIZE: Final = 25

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
DEFAULT_MAX_CONSECUTIVE: Final = 2
DEFAULT_TRACK_SUPPRESS_DAYS: Final = 30
DEFAULT_ARTIST_MUTE_DAYS: Final = 30
DEFAULT_ARTIST_STRIKE_LIMIT: Final = 3

# A track abandoned with more than this long left was skipped, not finished.
# Generous enough that a fade-out or trailing silence does not read as a
# skip, tight enough that bailing out of the last chorus does.
SKIP_GRACE_SECONDS: Final = 15.0

# --- Entities ----------------------------------------------------------------

CONF_ENABLED: Final = "enabled"
DEFAULT_ENABLED: Final = True

SERVICE_UNMUTE_ARTIST: Final = "unmute_artist"
SERVICE_FORGET_FEEDBACK: Final = "forget_feedback"
ATTR_ARTIST: Final = "artist"


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
# interlude or a skit rather than a song. Genuine top-tracks rankings
# surface those; relevance-ranked search did not, which is why this only
# became necessary once the native lookup started working.
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

# --- New releases ------------------------------------------------------------

CONF_FRESH_DAYS: Final = "fresh_days"

# Provider top-track rankings are cumulative, so a song released last month
# ranks below years of catalogue no matter how big it is right now. Inside
# this window a track is promoted in proportion to how new AND how popular
# it is, so a hot new single surfaces while a new flop does not. Zero
# disables the promotion entirely.
DEFAULT_FRESH_DAYS: Final = 120

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
