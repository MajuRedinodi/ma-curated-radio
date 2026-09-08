"""Batch builder: turn the currently playing track into more of the same.

One run reads the seed artist off whatever is playing, asks Last.fm for a
few similar artists, pulls each artist's best-known tracks, filters them,
orders them so no artist monopolises a run, and enqueues the result.
"""

from __future__ import annotations

import asyncio
import logging
import random
from collections import deque
from dataclasses import dataclass, field

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.util import dt as dt_util

from .const import (
    DEFAULT_PLAYLIST_LENGTH,
    EXPLICIT_CLEAN,
    EXPLICIT_PREFER,
    FAMILIARITY_EXPONENT,
    LASTFM_POOL_SIZE,
    MODE_REFILL,
    PLAYLIST_CHUNK,
    PLAYLIST_MAX_ROUNDS,
    QUEUED_MEMORY,
    SEED_LEAN_ARTIST,
    SEED_LEAN_DISCOVERY,
    SEED_LEAN_MULTIPLIER,
    SESSION_EXPIRY_HOURS,
    signal_update,
)
from .feedback import SkipMemory
from .filters import (
    base_title,
    clean_similar_artists,
    hotness,
    is_holiday,
    is_live,
    is_non_song,
    is_too_short,
    matches_provider,
    sequence,
    weighted_sample,
)
from .history import TitleHistory
from .lastfm import async_get_similar_artists
from .ma import (
    NativeClient,
    PlaylistUnsupportedError,
    TrackInfo,
    async_get_queue,
    async_play_media,
    async_search_tracks,
)
from .session import ListeningSession
from .settings import Settings

_LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class PlaylistResult:
    """What one playlist build actually did."""

    name: str
    seed_artist: str = ""
    artists: list[str] = field(default_factory=list)
    tracks: int = 0
    replaced: int = 0
    error: str = ""


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
        skips: SkipMemory,
        entry_id: str,
    ) -> None:
        """Set up the engine and its per-player memory."""
        self._hass = hass
        self._entry_id = entry_id
        self._settings = settings
        self._session = session
        self._skips = skips
        self._history = TitleHistory(settings.history_minutes)
        self._native = NativeClient(hass, settings.ma_config_entry_id)
        self._lock = asyncio.Lock()
        # Deliberately a separate lock. Sharing the batch lock would let a
        # long playlist build starve the live queue, since async_run skips
        # rather than waits when the batch lock is held.
        self._playlist_lock = asyncio.Lock()
        self._last_batch: BatchResult | None = None
        self._listening = ListeningSession()
        # Everything this integration has put in the queue recently. A
        # track we chose is never a manual pick, whatever the expected-next
        # comparison says, and that is what stops our own music from
        # re-anchoring the session and resetting the drift fence.
        self._queued: deque[str] = deque(maxlen=QUEUED_MEMORY)

    @property
    def history(self) -> TitleHistory:
        """The rolling title history, exposed for diagnostics and tests."""
        return self._history

    def was_queued(self, uri: str) -> bool:
        """True if this integration put that track in the queue."""
        return bool(uri) and uri in self._queued

    @property
    def last_batch(self) -> BatchResult | None:
        """What the most recent run did, for the status sensor."""
        return self._last_batch

    def apply_settings(self, settings: Settings) -> None:
        """Adopt changed settings without rebuilding the engine."""
        self._settings = settings
        self._history.set_window(settings.history_minutes)

    async def async_run(self, mode: str) -> BatchResult:
        """Build and enqueue one batch.

        Overlapping runs are skipped rather than queued, matching the
        ``mode: single`` behaviour of the script this replaces.
        """
        if self._lock.locked():
            _LOGGER.debug("A batch is already building; skipping %s request", mode)
            return BatchResult(mode=mode, skipped_reason="already_running")
        async with self._lock:
            result = await self._async_build(mode)
        self._last_batch = result
        async_dispatcher_send(self._hass, signal_update(self._entry_id))
        return result

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
        # A manual pick is a new station, so it re-anchors the session; a
        # refill continues the one already running.
        self._anchor(seed, restart=mode != MODE_REFILL)
        artists = [seed, *await self._async_similar_artists(self._pool_seed(seed))]

        # On a refill the tail of the queue is still populated, so avoid
        # re-adding anything already sitting there. Native-only; an empty
        # set just means this extra filter is unavailable.
        already_queued = (
            await self._native.async_queued_uris(queue.queue_id)
            if mode == MODE_REFILL
            else set()
        )
        # Recently played titles age out in hours; skipped ones are held off
        # for weeks. Both are just titles the batch must not contain.
        recent_titles = self._history.current() | self._skips.suppressed_titles

        per_artist: list[list[str]] = []
        title_by_uri: dict[str, str] = {}
        for index, artist in enumerate(artists):
            tracks = await self._async_tracks_for(artist)
            uris, titles = self._select(
                tracks,
                current_uri=queue.current_uri,
                excluded_titles=recent_titles | set(title_by_uri.values()),
                excluded_uris=already_queued,
                limit=self._track_cap(is_seed=index == 0),
            )
            if uris:
                per_artist.append(uris)
                title_by_uri.update(zip(uris, titles, strict=True))

        if not per_artist:
            _LOGGER.debug("No usable tracks for %s or any similar artist", seed)
            return BatchResult(
                mode=mode, seed_artist=seed, artists=artists, skipped_reason="no_tracks"
            )

        ordered = sequence(per_artist, self._settings.max_consecutive)
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

    async def _async_similar_artists(
        self,
        seed: str,
        cache: dict[str, list[tuple[str, float]]] | None = None,
        session: ListeningSession | None = None,
    ) -> list[str]:
        """Pick a capped set of Last.fm-similar artists.

        The pool is deliberately much larger than the cap, because the goal
        is what a station playing the seed artist would also play rather
        than that artist's three nearest neighbours. Selection from it is
        weighted by match score, not flat: a deep pool sampled uniformly is
        how batches ended up full of defensible artists nobody knew.
        """
        settings = self._settings
        if settings.max_artists <= 0 or not settings.lastfm_api_key:
            return []
        if cache is not None and seed in cache:
            names = cache[seed]
        else:
            names = await async_get_similar_artists(
                self._session, settings.lastfm_api_key, seed, LASTFM_POOL_SIZE
            )
            if cache is not None:
                cache[seed] = names
        candidates = clean_similar_artists(names, seed)
        muted = self._skips.muted_artists
        candidates = [pair for pair in candidates if pair[0].lower() not in muted]

        active = session or self._listening
        cap = self._degree_cap
        allowed = set(active.eligible(seed, [name for name, _ in candidates], cap))
        if not allowed and active.origin and seed != active.origin:
            # At the edge of the fence with nothing eligible nearby. Pull
            # back toward the origin rather than stalling out there.
            _LOGGER.debug("Nothing within %s degrees of %s; falling back", cap, seed)
            return await self._async_similar_artists(active.origin, cache, active)

        # Weighted by Last.fm's match score rather than shuffled flat, so a
        # batch is mostly artists a listener would actually recognise.
        return weighted_sample(
            [pair for pair in candidates if pair[0] in allowed],
            settings.max_artists,
            FAMILIARITY_EXPONENT.get(settings.familiarity, 1.0),
        )

    def _track_cap(self, *, is_seed: bool) -> int:
        """How many tracks this artist contributes to the batch.

        Only the seed is affected. Artist radio should mostly play the
        artist you picked; a format station treats it as one act among
        several. Muting never applies to the seed, since it is playing
        because you chose it.
        """
        cap = self._settings.tracks_per_artist
        if not is_seed:
            return cap
        multiplier = SEED_LEAN_MULTIPLIER.get(self._settings.seed_lean, 1.0)
        return max(1, round(cap * multiplier))

    async def _async_tracks_for(
        self, artist: str, cache: dict[str, list[TrackInfo]] | None = None
    ) -> list[TrackInfo]:
        """Get an artist's best-known tracks, natively if possible.

        The optional cache is per playlist build. The same few artists
        recur in every round, and without it each recurrence costs a fresh
        search plus a track fetch.
        """
        if cache is not None and artist in cache:
            return cache[artist]
        tracks: list[TrackInfo] = []
        if self._settings.use_native_top_tracks:
            native = await self._native.async_top_tracks(artist)
            tracks = native or []
        if not tracks:
            tracks = await async_search_tracks(
                self._hass, self._settings.ma_config_entry_id, artist
            )
        if cache is not None:
            cache[artist] = tracks
        return tracks

    def _ordered_for_selection(self, tracks: list[TrackInfo]) -> list[TrackInfo]:
        """Apply every ordering preference before the batch is cut.

        Explicit preference is a sort rather than a filter because a clean
        edit is usually a separate release with its own title, so nothing
        marks it as a version of the original. Putting the explicit tracks
        first pushes the edit outside the per-artist cut instead.
        """
        ordered = self._by_hotness(tracks)
        if self._settings.explicit == EXPLICIT_PREFER:
            ordered = sorted(ordered, key=lambda track: not track.explicit)
        return ordered

    def _by_hotness(self, tracks: list[TrackInfo]) -> list[TrackInfo]:
        """Reorder an artist's tracks so a hot new release can get in.

        Providers rank by cumulative plays, which buries anything recent.
        Tracks scoring zero, meaning old, unpopular, or without the
        metadata to tell, keep the provider's ordering exactly: the sort is
        stable, so this is a no-op wherever the data is absent.
        """
        window = self._settings.fresh_days
        if window <= 0:
            return tracks
        now = dt_util.utcnow()
        scored = sorted(
            tracks,
            key=lambda t: hotness(t.released, t.popularity, window, now),
            reverse=True,
        )
        if scored and scored[0] is not tracks[0]:
            _LOGGER.debug("Promoted %s as a hot new release", scored[0].name)
        return scored

    def _select(
        self,
        tracks: list[TrackInfo],
        *,
        current_uri: str,
        excluded_titles: set[str],
        excluded_uris: set[str],
        limit: int,
    ) -> tuple[list[str], list[str]]:
        """Filter one artist's tracks down to this batch's picks.

        Returns the chosen URIs and their normalised titles, in order.
        """
        settings = self._settings
        uris: list[str] = []
        titles: list[str] = []
        for track in self._ordered_for_selection(tracks):
            if len(uris) >= limit:
                break
            if not track.uri or track.uri == current_uri or track.uri in excluded_uris:
                continue
            if not matches_provider(track.uri, settings.provider_filter):
                continue
            # Commentary, interludes and skits chart alongside the songs,
            # so a genuine top-tracks ranking hands them straight over.
            if is_too_short(track.duration, settings.min_duration):
                continue
            if settings.explicit == EXPLICIT_CLEAN and track.explicit:
                continue
            if is_non_song(track.name, track.version):
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

        self._queued.append(uris[0])
        enqueued = [uris[0]]
        for uri in uris[1:]:
            try:
                await async_play_media(self._hass, self._settings.player, uri, "add")
            except Exception as err:  # noqa: BLE001 - one bad track, keep going
                _LOGGER.debug("Could not enqueue %s: %s", uri, err)
                continue
            self._queued.append(uri)
            enqueued.append(uri)
        return enqueued

    async def async_build_playlist(
        self,
        *,
        name: str,
        seed_artist: str = "",
        length: int = DEFAULT_PLAYLIST_LENGTH,
        provider: str = "",
    ) -> PlaylistResult:
        """Fill a provider playlist with the same music this queues.

        A playlist is for somewhere Home Assistant cannot reach, most
        obviously a car, so it is built long and in one go rather than
        refilled as it plays. Each round reseeds off one of the artists it
        just used, which reproduces over 60 tracks the drift an evening of
        refills produces live.

        Nothing is enqueued and playback is untouched. The skip memory is
        read so rejected songs and muted artists stay out, but the rolling
        repeat history is deliberately not written: a 60-track build would
        flood a two-hour window and starve the live queue.
        """
        if self._playlist_lock.locked():
            _LOGGER.debug("A playlist build is already running; skipping")
            return PlaylistResult(name=name, error="already_running")
        async with self._playlist_lock:
            return await self._async_build_playlist(
                name=name, seed_artist=seed_artist, length=length, provider=provider
            )

    async def _async_build_playlist(
        self,
        *,
        name: str,
        seed_artist: str,
        length: int,
        provider: str,
    ) -> PlaylistResult:
        """Do the work of one playlist build."""
        settings = self._settings

        if not seed_artist:
            queue = await async_get_queue(self._hass, settings.player)
            seed_artist = queue.seed_artist if queue else ""
        if not seed_artist:
            return PlaylistResult(name=name, error="no_seed_artist")

        # A build gets its own session rather than borrowing the live one.
        # Sharing meant a manual pick mid-build re-anchored the fence
        # underneath it, so a long playlist could end up half anchored to
        # one artist and half to another with nothing to show for it.
        build_session = ListeningSession.start(seed_artist)
        _LOGGER.debug("Playlist session anchored to %s", seed_artist)

        ordered: list[str] = []
        seen_titles = self._history.current() | self._skips.suppressed_titles
        artists_used: list[str] = []
        current_seed = seed_artist

        # Scoped to this build. The same artists recur every round, and
        # re-fetching them was most of the time a long build took.
        similar_cache: dict[str, list[tuple[str, float]]] = {}
        track_cache: dict[str, list[TrackInfo]] = {}

        for _ in range(PLAYLIST_MAX_ROUNDS):
            if len(ordered) >= length:
                break
            round_artists = [
                current_seed,
                *await self._async_similar_artists(
                    self._pool_seed(current_seed, build_session),
                    similar_cache,
                    build_session,
                ),
            ]
            per_artist: list[list[str]] = []
            for index, artist in enumerate(round_artists):
                tracks = await self._async_tracks_for(artist, track_cache)
                uris, titles = self._select(
                    tracks,
                    current_uri="",
                    excluded_titles=seen_titles,
                    excluded_uris=set(ordered),
                    limit=self._track_cap(is_seed=index == 0),
                )
                if provider:
                    uris = [u for u in uris if matches_provider(u, provider)]
                    titles = titles[: len(uris)]
                if uris:
                    per_artist.append(uris)
                    seen_titles.update(titles)
                    if artist not in artists_used:
                        artists_used.append(artist)
            if not per_artist:
                break
            ordered.extend(sequence(per_artist, settings.max_consecutive))

            # Reseed off a similar artist from this round, the same way a
            # refill reseeds off whatever happens to be playing.
            candidates = round_artists[1:]
            current_seed = random.choice(candidates) if candidates else current_seed

        ordered = ordered[:length]
        if not ordered:
            return PlaylistResult(name=name, seed_artist=seed_artist, error="no_tracks")

        try:
            written, replaced = await self._async_write_playlist(name, provider, ordered)
        except PlaylistUnsupportedError as err:
            _LOGGER.warning("Cannot manage playlists: %s", err)
            return PlaylistResult(
                name=name, seed_artist=seed_artist, error="playlists_unsupported"
            )

        _LOGGER.debug(
            "Wrote %s track(s) to playlist %s, seeded from %s via %s",
            written,
            name,
            seed_artist,
            ", ".join(artists_used),
        )
        return PlaylistResult(
            name=name,
            seed_artist=seed_artist,
            artists=artists_used,
            tracks=written,
            replaced=replaced,
        )

    async def _async_write_playlist(
        self, name: str, provider: str, uris: list[str]
    ) -> tuple[int, int]:
        """Create or refresh the named playlist. Returns (written, removed).

        Refreshed in place rather than recreated so the link stays stable
        for anything pointing at it, a car stereo included.
        """
        playlist = await self._native.async_find_playlist(name)
        replaced = 0
        if playlist is None:
            playlist = await self._native.async_create_playlist(name, provider)
        else:
            replaced = await self._native.async_clear_playlist(playlist)

        for start in range(0, len(uris), PLAYLIST_CHUNK):
            await self._native.async_add_playlist_tracks(
                playlist, uris[start : start + PLAYLIST_CHUNK]
            )
        return len(uris), replaced

    # --- Drift rails ---------------------------------------------------

    @property
    def listening(self) -> ListeningSession:
        """The current listening session, exposed for diagnostics."""
        return self._listening

    @property
    def _degree_cap(self) -> int | None:
        """How far this station style lets a session wander, or None."""
        if self._settings.seed_lean == SEED_LEAN_DISCOVERY:
            return None
        return max(0, self._settings.degrees)

    def _anchor(self, artist: str, *, restart: bool) -> None:
        """Establish or continue the live session anchored to an artist.

        A manual pick restarts it: you chose something else, so that is a
        new station. A session also restarts once it has gone stale, so
        tonight is not still anchored to yesterday morning.
        """
        if (
            restart
            or not self._listening.active
            or self._listening.is_stale(SESSION_EXPIRY_HOURS)
        ):
            self._listening = ListeningSession.start(artist)
            _LOGGER.debug("Queue session anchored to %s", artist)
        else:
            self._listening.touch()

    def _pool_seed(
        self, current_artist: str, session: ListeningSession | None = None
    ) -> str:
        """Which artist the similar-artist pool is drawn from.

        Artist radio always draws from the artist you picked, however far
        into the evening it is. Everything else draws from what is playing
        and relies on the degree fence to stay in the neighbourhood.
        """
        active = session or self._listening
        if self._settings.seed_lean == SEED_LEAN_ARTIST and active.origin:
            return active.origin
        return current_artist
