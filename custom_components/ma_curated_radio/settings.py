"""Resolved settings for one configured player."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry

from .const import (
    CONF_ARTIST_MUTE_DAYS,
    CONF_ARTIST_STRIKE_LIMIT,
    CONF_BATCH_LENGTH,
    CONF_BULK_TRACKS,
    CONF_COOLDOWN_ENTITY,
    CONF_COOLDOWN_SECONDS,
    CONF_DEGREES,
    CONF_ENABLED,
    CONF_EXPLICIT,
    CONF_FAMILIARITY,
    CONF_FILTER_HOLIDAY,
    CONF_FILTER_LIVE,
    CONF_FILTER_REMIX,
    CONF_HISTORY_MINUTES,
    CONF_LASTFM_API_KEY,
    CONF_MA_CONFIG_ENTRY_ID,
    CONF_MAX_ARTISTS,
    CONF_MAX_CONSECUTIVE,
    CONF_MIN_DURATION,
    CONF_PLAYER,
    CONF_POPULARITY_FLOOR,
    CONF_PROVIDER_FILTER,
    CONF_REFILL_THRESHOLD,
    CONF_SEED_FROM_SONG,
    CONF_SEED_LEAN,
    CONF_SETTLE_SECONDS,
    CONF_TRACK_SUPPRESS_DAYS,
    CONF_TRACKS_PER_ARTIST,
    DEFAULT_ARTIST_MUTE_DAYS,
    DEFAULT_ARTIST_STRIKE_LIMIT,
    DEFAULT_BULK_TRACKS,
    DEFAULT_COOLDOWN_SECONDS,
    DEFAULT_DEGREES,
    DEFAULT_ENABLED,
    DEFAULT_EXPLICIT,
    DEFAULT_FAMILIARITY,
    DEFAULT_FILTER_HOLIDAY,
    DEFAULT_FILTER_LIVE,
    DEFAULT_FILTER_REMIX,
    DEFAULT_HISTORY_MINUTES,
    DEFAULT_MAX_CONSECUTIVE,
    DEFAULT_MIN_DURATION,
    DEFAULT_POPULARITY_FLOOR,
    DEFAULT_PROVIDER_FILTER,
    DEFAULT_REFILL_THRESHOLD,
    DEFAULT_SEED_FROM_SONG,
    DEFAULT_SEED_LEAN,
    DEFAULT_SETTLE_SECONDS,
    DEFAULT_TRACK_SUPPRESS_DAYS,
    EXPLICIT_MODES,
    FAMILIARITIES,
    LEGACY_SEED_LEANS,
    SEED_LEANS,
    style_value,
)


@dataclass(slots=True)
class Settings:
    """Everything one configured player needs, flattened out of the entry."""

    player: str
    ma_config_entry_id: str
    enabled: bool
    lastfm_api_key: str
    max_artists: int
    batch_length: int
    popularity_floor: int
    tracks_per_artist: int
    refill_threshold: int
    bulk_tracks: int
    history_minutes: int
    settle_seconds: int
    cooldown_entity: str
    cooldown_seconds: int
    provider_filter: str
    filter_live: bool
    filter_remix: bool
    filter_holiday: bool
    seed_from_song: bool
    seed_lean: str
    familiarity: str
    explicit: str
    degrees: int
    min_duration: int
    max_consecutive: int
    track_suppress_days: int
    artist_mute_days: int
    artist_strike_limit: int

    @classmethod
    def from_entry(cls, entry: ConfigEntry) -> Settings:
        """Read the entry, letting options override the original setup data."""
        merged = {**entry.data, **entry.options}
        # Batch shape is per style, so the style has to be resolved before
        # anything that depends on it is read.
        style = seed_lean(merged.get(CONF_SEED_LEAN, DEFAULT_SEED_LEAN))
        return cls(
            player=str(merged.get(CONF_PLAYER, "")),
            enabled=bool(merged.get(CONF_ENABLED, DEFAULT_ENABLED)),
            ma_config_entry_id=str(merged.get(CONF_MA_CONFIG_ENTRY_ID, "")),
            lastfm_api_key=str(merged.get(CONF_LASTFM_API_KEY, "")),
            max_artists=style_value(merged, style, CONF_MAX_ARTISTS),
            batch_length=style_value(merged, style, CONF_BATCH_LENGTH),
            popularity_floor=int(
                merged.get(CONF_POPULARITY_FLOOR, DEFAULT_POPULARITY_FLOOR)
            ),
            tracks_per_artist=style_value(merged, style, CONF_TRACKS_PER_ARTIST),
            refill_threshold=int(
                merged.get(CONF_REFILL_THRESHOLD, DEFAULT_REFILL_THRESHOLD)
            ),
            bulk_tracks=int(merged.get(CONF_BULK_TRACKS, DEFAULT_BULK_TRACKS)),
            history_minutes=int(
                merged.get(CONF_HISTORY_MINUTES, DEFAULT_HISTORY_MINUTES)
            ),
            settle_seconds=int(merged.get(CONF_SETTLE_SECONDS, DEFAULT_SETTLE_SECONDS)),
            cooldown_entity=str(merged.get(CONF_COOLDOWN_ENTITY, "") or ""),
            cooldown_seconds=int(
                merged.get(CONF_COOLDOWN_SECONDS, DEFAULT_COOLDOWN_SECONDS)
            ),
            provider_filter=str(
                merged.get(CONF_PROVIDER_FILTER, DEFAULT_PROVIDER_FILTER) or ""
            ),
            filter_live=bool(merged.get(CONF_FILTER_LIVE, DEFAULT_FILTER_LIVE)),
            filter_remix=bool(merged.get(CONF_FILTER_REMIX, DEFAULT_FILTER_REMIX)),
            filter_holiday=bool(
                merged.get(CONF_FILTER_HOLIDAY, DEFAULT_FILTER_HOLIDAY)
            ),
            seed_from_song=bool(
                merged.get(CONF_SEED_FROM_SONG, DEFAULT_SEED_FROM_SONG)
            ),
            seed_lean=style,
            familiarity=_familiarity(merged.get(CONF_FAMILIARITY, DEFAULT_FAMILIARITY)),
            explicit=_explicit_mode(merged.get(CONF_EXPLICIT, DEFAULT_EXPLICIT)),
            degrees=int(merged.get(CONF_DEGREES, DEFAULT_DEGREES)),
            min_duration=int(merged.get(CONF_MIN_DURATION, DEFAULT_MIN_DURATION)),
            max_consecutive=int(
                merged.get(CONF_MAX_CONSECUTIVE, DEFAULT_MAX_CONSECUTIVE)
            ),
            track_suppress_days=int(
                merged.get(CONF_TRACK_SUPPRESS_DAYS, DEFAULT_TRACK_SUPPRESS_DAYS)
            ),
            artist_mute_days=int(
                merged.get(CONF_ARTIST_MUTE_DAYS, DEFAULT_ARTIST_MUTE_DAYS)
            ),
            artist_strike_limit=int(
                merged.get(CONF_ARTIST_STRIKE_LIMIT, DEFAULT_ARTIST_STRIKE_LIMIT)
            ),
        )


def seed_lean(value: object) -> str:
    """Normalise a station style, carrying old names forward.

    Public because more than one place has to answer this question, and
    when they answered it separately they disagreed: this one carried
    "format" forward to Discovery, while the entity and the options form
    each fell back to Balanced instead. The dropdown said Balanced, the
    numbers under it showed Discovery's, and the engine ran Discovery.
    """
    name = str(value or "")
    name = LEGACY_SEED_LEANS.get(name, name)
    return name if name in SEED_LEANS else DEFAULT_SEED_LEAN


def _familiarity(value: object) -> str:
    """Normalise the familiarity setting."""
    name = str(value or "")
    return name if name in FAMILIARITIES else DEFAULT_FAMILIARITY


def _explicit_mode(value: object) -> str:
    """Normalise the explicit-content setting."""
    name = str(value or "")
    return name if name in EXPLICIT_MODES else DEFAULT_EXPLICIT
