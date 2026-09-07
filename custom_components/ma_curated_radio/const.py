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
DEFAULT_USE_NATIVE_TOP_TRACKS: Final = True

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
