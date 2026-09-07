"""Resolved settings for one configured player."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry

from .const import (
    CONF_COOLDOWN_ENTITY,
    CONF_COOLDOWN_SECONDS,
    CONF_FILTER_HOLIDAY,
    CONF_FILTER_LIVE,
    CONF_HISTORY_MINUTES,
    CONF_LASTFM_API_KEY,
    CONF_MA_CONFIG_ENTRY_ID,
    CONF_MAX_ARTISTS,
    CONF_PLAYER,
    CONF_PROVIDER_FILTER,
    CONF_REFILL_THRESHOLD,
    CONF_SETTLE_SECONDS,
    CONF_TRACKS_PER_ARTIST,
    CONF_USE_NATIVE_TOP_TRACKS,
    DEFAULT_COOLDOWN_SECONDS,
    DEFAULT_FILTER_HOLIDAY,
    DEFAULT_FILTER_LIVE,
    DEFAULT_HISTORY_MINUTES,
    DEFAULT_MAX_ARTISTS,
    DEFAULT_PROVIDER_FILTER,
    DEFAULT_REFILL_THRESHOLD,
    DEFAULT_SETTLE_SECONDS,
    DEFAULT_TRACKS_PER_ARTIST,
    DEFAULT_USE_NATIVE_TOP_TRACKS,
)


@dataclass(slots=True)
class Settings:
    """Everything one configured player needs, flattened out of the entry."""

    player: str
    ma_config_entry_id: str
    lastfm_api_key: str
    max_artists: int
    tracks_per_artist: int
    refill_threshold: int
    history_minutes: int
    settle_seconds: int
    cooldown_entity: str
    cooldown_seconds: int
    provider_filter: str
    filter_live: bool
    filter_holiday: bool
    use_native_top_tracks: bool

    @classmethod
    def from_entry(cls, entry: ConfigEntry) -> Settings:
        """Read the entry, letting options override the original setup data."""
        merged = {**entry.data, **entry.options}
        return cls(
            player=str(merged.get(CONF_PLAYER, "")),
            ma_config_entry_id=str(merged.get(CONF_MA_CONFIG_ENTRY_ID, "")),
            lastfm_api_key=str(merged.get(CONF_LASTFM_API_KEY, "")),
            max_artists=int(merged.get(CONF_MAX_ARTISTS, DEFAULT_MAX_ARTISTS)),
            tracks_per_artist=int(
                merged.get(CONF_TRACKS_PER_ARTIST, DEFAULT_TRACKS_PER_ARTIST)
            ),
            refill_threshold=int(
                merged.get(CONF_REFILL_THRESHOLD, DEFAULT_REFILL_THRESHOLD)
            ),
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
            filter_holiday=bool(
                merged.get(CONF_FILTER_HOLIDAY, DEFAULT_FILTER_HOLIDAY)
            ),
            use_native_top_tracks=bool(
                merged.get(CONF_USE_NATIVE_TOP_TRACKS, DEFAULT_USE_NATIVE_TOP_TRACKS)
            ),
        )
