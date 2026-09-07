"""Batch builder: turn the currently playing track into more of the same.

One run reads the seed artist off whatever is playing, asks Last.fm for a
few similar artists, pulls each artist's best-known tracks, filters them,
interleaves them round-robin so no artist plays twice in a row, and
enqueues the result.
"""

from __future__ import annotations

import asyncio
import logging
import random
from dataclasses import dataclass, field

import aiohttp
from homeassistant.core import HomeAssistant

from .const import LASTFM_OVERFETCH, MODE_REFILL
from .filters import (
    base_title,
    clean_similar_artists,
    interleave,
    is_holiday,
    is_live,
    matches_provider,
)
from .history import TitleHistory
from .lastfm import async_get_similar_artists
from .ma import (
    NativeClient,
    TrackInfo,
    async_get_queue,
    async_play_media,
    async_search_tracks,
)
from .settings import Settings

_LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class BatchResult:
    """What one engine run actually did."""

    mode: str
    seed_artist: str = ""
    artists: list[str] = field(default_factory=list)
    queued: int = 0
    skipped_reason: str = ""

    @property
    def ran(self) -> bool:
        """True if tracks were enqueued."""
        return self.queued > 0


class CuratedRadioEngine:
    """Builds one continuation batch at a time for a single player."""

    def __init__(
        self,
        hass: HomeAssistant,
        settings: Settings,
        session: aiohttp.ClientSession,
    ) -> None:
        """Set up the engine and its per-player memory."""
        self._hass = hass
        self._settings = settings
        self._session = session
        self._history = TitleHistory(settings.history_minutes)
        self._native = NativeClient(hass, settings.ma_config_entry_id)
        self._lock = asyncio.Lock()

    @property
    def history(self) -> TitleHistory:
        """The rolling title history, exposed for diagnostics and tests."""
        return self._history

    async def async_run(self, mode: str) -> BatchResult:
        """Build and enqueue one batch.

        Overlapping runs are skipped rather than queued, matching the
        ``mode: single`` behaviour of the script this replaces.
        """
        if self._lock.locked():
            _LOGGER.debug("Continuation already running; skipping %s request", mode)
            return BatchResult(mode=mode, skipped_reason="already_running")
        async with self._lock:
            return await self._async_build(mode)

    async def _async_build(self, mode: str) -> BatchResult:
        """Do the work of one batch."""
        settings = self._settings
        queue = await async_get_queue(self._hass, settings.player)
        if queue is None:
            return BatchResult(mode=mode, skipped_reason="no_queue")
        if not queue.seed_artist:
            _LOGGER.debug("No artist on the current track; nothing to seed from")
            return BatchResult(mode=mode, skipped_reason="no_seed_artist")

        seed = queue.seed_artist
        artists = [seed, *await self._async_similar_artists(seed)]

        # On a refill the tail of the queue is still populated, so avoid
        # re-adding anything already sitting there. Native-only; an empty
        # set just means this extra filter is unavailable.
        already_queued = (
            await self._native.async_queued_uris(queue.queue_id)
            if mode == MODE_REFILL
            else set()
        )
        recent_titles = self._history.current()

        per_artist: list[list[str]] = []
        title_by_uri: dict[str, str] = {}
        for artist in artists:
            tracks = await self._async_tracks_for(artist)
            uris, titles = self._select(
                tracks,
                current_uri=queue.current_uri,
                excluded_titles=recent_titles | set(title_by_uri.values()),
                excluded_uris=already_queued,
            )
            if uris:
                per_artist.append(uris)
                title_by_uri.update(zip(uris, titles, strict=True))

        if not per_artist:
            _LOGGER.debug("No usable tracks for %s or any similar artist", seed)
            return BatchResult(
                mode=mode, seed_artist=seed, artists=artists, skipped_reason="no_tracks"
            )

        ordered = interleave(per_artist)
        enqueued = await self._async_enqueue(ordered, mode)
        if enqueued:
            self._history.add([title_by_uri[uri] for uri in enqueued])

        _LOGGER.debug(
            "Queued %s track(s) in %s mode, seeded from %s via %s",
            len(enqueued),
            mode,
            seed,
            ", ".join(artists),
        )
        return BatchResult(
            mode=mode, seed_artist=seed, artists=artists, queued=len(enqueued)
        )

    async def _async_similar_artists(self, seed: str) -> list[str]:
        """Pick a shuffled, capped set of Last.fm-similar artists."""
        settings = self._settings
        if settings.max_artists <= 0 or not settings.lastfm_api_key:
            return []
        names = await async_get_similar_artists(
            self._session,
            settings.lastfm_api_key,
            seed,
            settings.max_artists + LASTFM_OVERFETCH,
        )
        candidates = clean_similar_artists(names, seed)
        random.shuffle(candidates)
        return candidates[: settings.max_artists]

    async def _async_tracks_for(self, artist: str) -> list[TrackInfo]:
        """Get an artist's best-known tracks, natively if possible."""
        if self._settings.use_native_top_tracks:
            tracks = await self._native.async_top_tracks(artist)
            if tracks:
                return tracks
        return await async_search_tracks(
            self._hass, self._settings.ma_config_entry_id, artist
        )

    def _select(
        self,
        tracks: list[TrackInfo],
        *,
        current_uri: str,
        excluded_titles: set[str],
        excluded_uris: set[str],
    ) -> tuple[list[str], list[str]]:
        """Filter one artist's tracks down to this batch's picks.

        Returns the chosen URIs and their normalised titles, in order.
        """
        settings = self._settings
        uris: list[str] = []
        titles: list[str] = []
        for track in tracks:
            if len(uris) >= settings.tracks_per_artist:
                break
            if not track.uri or track.uri == current_uri or track.uri in excluded_uris:
                continue
            if not matches_provider(track.uri, settings.provider_filter):
                continue
            if settings.filter_live and is_live(track.name, track.version):
                continue
            if settings.filter_holiday and is_holiday(
                track.name, track.version, track.album
            ):
                continue
            title = base_title(track.name)
            if not title or title in excluded_titles or title in titles:
                continue
            uris.append(track.uri)
            titles.append(title)
        return uris, titles

    async def _async_enqueue(self, uris: list[str], mode: str) -> list[str]:
        """Enqueue the ordered URIs, returning the ones that landed.

        ``replace_next`` on the first track drops everything queued after
        the one playing without interrupting it; ``add`` appends. If that
        first call fails in replace mode the stale tail is still there, so
        the run is abandoned rather than half-applied.
        """
        first_enqueue = "add" if mode == MODE_REFILL else "replace_next"
        try:
            await async_play_media(
                self._hass, self._settings.player, uris[0], first_enqueue
            )
        except Exception as err:  # noqa: BLE001 - surface it, do not half-apply
            _LOGGER.warning(
                "Could not start the %s batch on %s: %s",
                mode,
                self._settings.player,
                err,
            )
            return []

        enqueued = [uris[0]]
        for uri in uris[1:]:
            try:
                await async_play_media(self._hass, self._settings.player, uri, "add")
            except Exception as err:  # noqa: BLE001 - one bad track, keep going
                _LOGGER.debug("Could not enqueue %s: %s", uri, err)
                continue
            enqueued.append(uri)
        return enqueued
