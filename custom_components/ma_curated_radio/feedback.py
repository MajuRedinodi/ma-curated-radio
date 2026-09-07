"""What the listener rejected, remembered across restarts.

A skip is the strongest signal available without asking anyone to rate
anything, and it is worthless if it evaporates on restart, so this is the
one piece of state that gets persisted.

Two rules, deliberately different in weight:

* A skipped **track** is pushed off for a long window. Cheap to be wrong
  about: one song out of an artist's catalogue.
* An artist skipped several times **in a row** is muted. Consecutive is
  the point. Three unlucky picks spread over an evening say nothing; three
  in a row says the artist is wrong for the room right now.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

_LOGGER = logging.getLogger(__name__)

STORAGE_VERSION = 1
SECONDS_PER_DAY = 86400


@dataclass(slots=True)
class _Streak:
    """The run of consecutive skips currently in progress."""

    artist: str = ""
    count: int = 0

    def register(self, artist: str) -> int:
        """Record a skip and return the new run length for that artist."""
        key = artist.lower()
        if key == self.artist:
            self.count += 1
        else:
            self.artist = key
            self.count = 1
        return self.count

    def reset(self) -> None:
        """Forget the run. Called whenever a track plays to the end."""
        self.artist = ""
        self.count = 0


class SkipMemory:
    """Persisted record of skipped tracks and muted artists."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry_id: str,
        *,
        track_days: int,
        artist_days: int,
        strike_limit: int,
    ) -> None:
        """Set up storage for one configured player."""
        self._store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, f"ma_curated_radio.{entry_id}"
        )
        self._track_days = track_days
        self._artist_days = artist_days
        self._strike_limit = strike_limit
        self._tracks: dict[str, float] = {}
        self._artists: dict[str, float] = {}
        self._streak = _Streak()

    async def async_load(self) -> None:
        """Read persisted state, tolerating an absent or unreadable store."""
        try:
            data = await self._store.async_load()
        except Exception as err:  # noqa: BLE001 - bad store must not block setup
            _LOGGER.warning("Could not read skip history: %s", err)
            return
        if not data:
            return
        self._tracks = dict(data.get("tracks") or {})
        self._artists = dict(data.get("artists") or {})
        self._prune()

    async def _async_save(self) -> None:
        """Persist current state."""
        self._store.async_delay_save(
            lambda: {"tracks": self._tracks, "artists": self._artists}, 10
        )

    def _prune(self) -> None:
        """Drop entries whose suppression window has passed."""
        now = dt_util.utcnow().timestamp()
        self._tracks = {k: v for k, v in self._tracks.items() if v > now}
        self._artists = {k: v for k, v in self._artists.items() if v > now}

    @property
    def suppressed_titles(self) -> set[str]:
        """Normalised titles that should not be queued right now."""
        self._prune()
        return set(self._tracks)

    @property
    def muted_artists(self) -> set[str]:
        """Lowercased artist names currently muted."""
        self._prune()
        return set(self._artists)

    @property
    def muted_display(self) -> dict[str, str]:
        """Muted artists mapped to when the mute lifts, for display."""
        self._prune()
        return {
            name: dt_util.utc_from_timestamp(until).isoformat()
            for name, until in sorted(self._artists.items(), key=lambda kv: kv[1])
        }

    @property
    def suppressed_count(self) -> int:
        """How many individual tracks are currently held off."""
        self._prune()
        return len(self._tracks)

    async def async_unmute(self, artist: str) -> bool:
        """Lift the mute on one artist. Returns False if it was not muted."""
        self._prune()
        if self._artists.pop(artist.lower(), None) is None:
            return False
        if self._streak.artist == artist.lower():
            self._streak.reset()
        await self._async_save()
        _LOGGER.info("Unmuted %s", artist)
        return True

    async def async_unmute_all(self) -> int:
        """Lift every artist mute. Returns how many were lifted."""
        self._prune()
        count = len(self._artists)
        if count:
            self._artists.clear()
            self._streak.reset()
            await self._async_save()
            _LOGGER.info("Unmuted %s artist(s)", count)
        return count

    async def async_record_played(self) -> None:
        """Note that a track finished, which breaks any skip run."""
        self._streak.reset()

    async def async_record_skip(self, title: str, artist: str) -> str | None:
        """Record a skip. Returns an artist name if this muted one.

        The title is pushed off immediately. The artist is muted only once
        the run of consecutive skips reaches the strike limit.
        """
        now = dt_util.utcnow().timestamp()
        if title:
            self._tracks[title] = now + self._track_days * SECONDS_PER_DAY

        muted: str | None = None
        if artist and self._streak.register(artist) >= self._strike_limit:
            self._artists[artist.lower()] = now + self._artist_days * SECONDS_PER_DAY
            self._streak.reset()
            muted = artist
            _LOGGER.info(
                "Muting %s for %s days after %s skips in a row",
                artist,
                self._artist_days,
                self._strike_limit,
            )

        await self._async_save()
        return muted

    async def async_clear(self) -> None:
        """Forget everything. Not wired to the UI yet; useful in testing."""
        self._tracks.clear()
        self._artists.clear()
        self._streak.reset()
        await self._async_save()


@dataclass(slots=True)
class PlaybackSnapshot:
    """Enough of a media_player state to judge whether a track was skipped."""

    uri: str = ""
    title: str = ""
    artist: str = ""
    duration: float = 0.0
    elapsed: float = 0.0
    extras: dict[str, Any] = field(default_factory=dict)

    def was_skipped(self, grace_seconds: float) -> bool:
        """True if the track was cut short rather than allowed to finish.

        Without a duration there is nothing to compare against, so the
        benefit of the doubt goes to "played".
        """
        if self.duration <= 0:
            return False
        return self.elapsed < self.duration - grace_seconds
