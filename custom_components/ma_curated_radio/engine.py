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
    PAIR_LISTENER_RATIO,
    PLAYLIST_CHUNK,
    PLAYLIST_MAX_ROUNDS,
    QUEUED_MEMORY,
    SEARCH_LIMIT,
    SEED_LEAN_ARTIST,
    SEED_LEAN_DISCOVERY,
    SEED_LEAN_MULTIPLIER,
    SESSION_EXPIRY_HOURS,
    SPLIT_DUO_CREDITS,
    TIER_DECAY,
    signal_update,
)
from .decide import leading_pool
from .feedback import SkipMemory
from .filters import (
    TIER_PATTERN,
    SelectionRules,
    base_title,
    clean_similar_artists,
    drop_outliers,
    matches_provider,
    reach_of,
    select_tracks,
    sequence,
    sequence_tiered,
    tier_of,
    weighted_sample,
    without_backing_band,
)
from .history import TitleHistory
from .lastfm import async_get_artist_listeners, async_get_similar_artists
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
    # How well known this batch is likely to be, so a shape can be judged
    # before it plays rather than at track ten. Reach is an artist's
    # audience decayed by how far down their own ordering a track sits,
    # which is the same score the tiering uses. Absolute, so it compares
    # across pools: an observed rock batch ran near 900,000 and a
    # singer-songwriter batch at the same settings near 240,000, which is
    # the difference between depth being free and depth being too much.
    reach_median: int = 0
    reach_low: int = 0
    tiers: dict[str, int] = field(default_factory=dict)

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
        # The name to ask Last.fm about, for seeds whose credit needed
        # resolving. Decided once when a station starts, because settling
        # it costs two lookups and the answer cannot change while the
        # same song is the reason the station exists.
        self._alias: dict[str, str] = {}
        # Artist audience sizes, kept for the life of the entry. Neighbours
        # recur heavily between batches, so this usually saves the lookups
        # entirely rather than merely spreading them out.
        self._sizes: dict[str, int] = {}

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
        # Settle which name Last.fm should be asked about, once, on the
        # pick that starts the station. A duet that merely comes up later
        # must not redefine it.
        if mode != MODE_REFILL:
            await self._async_resolve_alias(seed, queue.artists)
            # Put the picked song into repeat memory. Nothing else does:
            # the history records what this integration queues, and a pick
            # is not ours, so the one song guaranteed to have just played
            # was the only one with no protection at all. Matching on the
            # URI is not enough, because a provider carries several copies
            # of a hit and a remaster is a different URI for the same
            # song. Replaying it later is fine and radio-like; replaying
            # it three tracks later is not, and until now which one you
            # got was luck.
            if queue.current_title:
                self._history.add([base_title(queue.current_title)])
        # A manual pick is a new station, so it re-anchors the session; a
        # refill continues the one already running.
        self._anchor(seed, restart=mode != MODE_REFILL)
        # The artist the batch is actually built around, which in artist
        # radio is the one you picked rather than whoever is playing now.
        lead = self._lead_artist(seed)
        artists = [
            lead,
            *await self._async_similar_artists(self._pool_seed(seed)),
        ]

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
        # Artists already given a pool. Anything crediting one of them is
        # theirs, so a later pool cannot smuggle the same act back in.
        covered: set[str] = set()
        pool_artists: list[str] = []
        for index, artist in enumerate(artists):
            tracks = await self._async_tracks_for(artist)
            uris, titles = self._select(
                tracks,
                current_uri=queue.current_uri,
                excluded_titles=recent_titles | set(title_by_uri.values()),
                excluded_uris=already_queued,
                excluded_artists=covered,
                limit=self._track_cap(is_seed=index == 0),
            )
            covered.add(artist.strip().lower())
            if uris:
                pool_artists.append(artist)
                per_artist.append(uris)
                title_by_uri.update(zip(uris, titles, strict=True))

        if not per_artist:
            _LOGGER.debug("No usable tracks for %s or any similar artist", lead)
            return BatchResult(
                mode=mode, seed_artist=lead, artists=artists, skipped_reason="no_tracks"
            )

        leading = leading_pool(
            pool_artists,
            queue.artists,
            lands_next=mode != MODE_REFILL or queue.remaining == 0,
        )
        _LOGGER.debug(
            "Batch follows %s; %s",
            ", ".join(queue.artists) or "nothing",
            f"primed {pool_artists[leading]}"
            if leading is not None
            else "no pool primed",
        )
        # Round-robin plays every artist's biggest track, then every
        # artist's second, so an hour front-loads its hits and decays. A
        # measured batch closed on a third averaging 105k listeners
        # against 768k for its first third. Rotating tiers instead spends
        # the big records across the whole hour.
        sizes = await self._async_sizes(pool_artists)
        sized = [
            (artist, uris, sizes.get(artist, 0))
            for artist, uris in zip(pool_artists, per_artist, strict=True)
        ]
        tiers = tier_of(sized, TIER_DECAY)
        ordered = sequence_tiered(
            per_artist,
            tiers,
            TIER_PATTERN,
            max_consecutive=self._settings.max_consecutive,
            leading=leading,
            length=self._settings.batch_length,
        )
        enqueued = await self._async_enqueue(ordered, mode)
        if enqueued:
            self._history.add([title_by_uri[uri] for uri in enqueued])

        reach_median, reach_low, counts = self._summarise(enqueued, sized, tiers)

        _LOGGER.debug(
            "Queued %s track(s) in %s mode, seeded from %s via %s; "
            "median reach %s, weakest %s, tiers %s",
            len(enqueued),
            mode,
            lead,
            ", ".join(artists),
            f"{reach_median:,}",
            f"{reach_low:,}",
            counts or "none",
        )
        return BatchResult(
            mode=mode,
            seed_artist=lead,
            artists=artists,
            queued=len(enqueued),
            reach_median=reach_median,
            reach_low=reach_low,
            tiers=counts,
        )

    def _summarise(
        self,
        enqueued: list[str],
        sized: list[tuple[str, list[str], int]],
        tiers: dict[str, str],
    ) -> tuple[int, int, dict[str, int]]:
        """Median reach, weakest reach, and the tier split of a batch.

        Judging a batch on the way out means its shape is visible before
        it plays rather than at track ten. Reach is absolute so batches
        compare across stations; the tier counts are relative to their
        own pool and only describe the texture within one.
        """
        reach = reach_of(sized, TIER_DECAY)
        played = sorted(reach.get(uri, 0) for uri in enqueued)
        counts: dict[str, int] = {}
        for uri in enqueued:
            label = tiers.get(uri, "")
            if label:
                counts[label] = counts.get(label, 0) + 1
        if not played:
            return 0, 0, counts
        return played[len(played) // 2], played[0], counts

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
            names = await self._async_lookup_similar(seed)
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
        chosen = weighted_sample(
            [pair for pair in candidates if pair[0] in allowed],
            settings.max_artists,
            FAMILIARITY_EXPONENT.get(settings.familiarity, 1.0),
        )

        # Match score says how similar, not how known. Christine McVie
        # matches Fleetwood Mac almost perfectly and has 2% of that pool's
        # audience, which is how a Fleetwood Mac station ended up playing
        # three tracks nobody recognised.
        sizes = await self._async_sizes(chosen)
        keep, dropped = drop_outliers(
            [(name, sizes.get(name, 0)) for name in chosen],
            settings.popularity_floor,
        )
        if dropped:
            _LOGGER.debug(
                "Too small for this pool, dropped: %s",
                ", ".join(f"{name} ({size:,})" for name, size in dropped),
            )
        return keep

    async def _async_search(self, artist: str) -> list[TrackInfo]:
        """Search one artist's tracks, natively if the client allows it."""
        found = await self._native.async_search_tracks(artist, SEARCH_LIMIT)
        if found is None:
            found = await async_search_tracks(
                self._hass, self._settings.ma_config_entry_id, artist
            )
        return found

    async def _async_sizes(self, artists: list[str]) -> dict[str, int]:
        """Audience size per artist, cached for the life of the session.

        Used for two things that both need to know how big an artist is
        rather than how similar: dropping a neighbour far below its own
        pool, and tiering its tracks. Neighbours recur heavily between
        batches, so the cache means a refill usually costs no lookups at
        all.

        A failed lookup caches nothing and returns zero, which every
        caller reads as "unknown" rather than "tiny".
        """
        key = self._settings.lastfm_api_key
        if not key:
            return {}
        wanted = [a for a in artists if a.lower() not in self._sizes]
        if wanted:
            found = await asyncio.gather(
                *(
                    async_get_artist_listeners(self._session, key, artist)
                    for artist in wanted
                )
            )
            for artist, size in zip(wanted, found, strict=True):
                if size:
                    self._sizes[artist.lower()] = size
        return {a: self._sizes.get(a.lower(), 0) for a in artists}

    async def _async_resolve_alias(self, seed: str, credited: list[str]) -> None:
        """Decide whether a two-name credit is a duo or a collaboration.

        Providers credit both the same way, as two artists on one track,
        and both exist on Last.fm as an act in their own right, so the
        names alone cannot separate them. Getting it wrong is expensive in
        both directions:

        * Treating a duo as two soloists asks about half an act. "The Beat
          Goes On" is credited to Sonny and to Cher, and Last.fm's "Sonny"
          is Skrillex, whose given name is Sonny Moore, so a 1967 record
          seeded a dubstep station.
        * Treating a collaboration as a duo asks about a footnote.
          "Telephone" is credited to Lady Gaga and to Beyonce, and the
          pair is its own Last.fm act whose neighbours are Gaga's pre-fame
          bar band rather than her actual neighbours.

        The audience tells them apart. A duo is how its members are known,
        so the pair outdraws either name alone: Sonny & Cher have 528k
        listeners against 181k for "Sonny". A duet is a footnote beside
        either artist's own following: Lady Gaga & Beyonce have 34k
        against Lady Gaga's 5.9 million. Three orders of magnitude sit
        between those two cases, so the comparison needs no cleverness.
        """
        key = seed.lower()
        self._alias.pop(key, None)
        if len(credited) != SPLIT_DUO_CREDITS or not self._settings.lastfm_api_key:
            return
        joined = " & ".join(credited)
        if joined.lower() == key:
            return

        api_key = self._settings.lastfm_api_key
        pair, alone = await asyncio.gather(
            async_get_artist_listeners(self._session, api_key, joined),
            async_get_artist_listeners(self._session, api_key, seed),
        )
        if pair and pair >= alone * PAIR_LISTENER_RATIO:
            self._alias[key] = joined
            _LOGGER.debug(
                "%s is a duo (%s listeners against %s for %s alone); asking "
                "Last.fm about the pair",
                joined,
                pair,
                alone,
                seed,
            )
            return
        _LOGGER.debug(
            "%s is a collaboration (%s listeners against %s for %s alone); "
            "asking Last.fm about %s",
            joined,
            pair,
            alone,
            seed,
            seed,
        )

    async def _async_lookup_similar(self, seed: str) -> list[tuple[str, float]]:
        """Ask Last.fm about a seed, under its resolved name if it has one."""
        key = self._settings.lastfm_api_key
        asked = self._alias.get(seed.lower(), seed)
        names = await async_get_similar_artists(
            self._session, key, asked, LASTFM_POOL_SIZE
        )
        if names or asked == seed:
            return names
        # The pair looked like the act but Last.fm has no neighbours for
        # it. Half an answer beats none.
        return await async_get_similar_artists(
            self._session, key, seed, LASTFM_POOL_SIZE
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
            # Native search first, purely so a limit can be passed. The
            # service action returns five tracks and no more, which is less
            # than one batch uses, so an artist reached on a refill had
            # nothing left that had not just played.
            searched = await self._async_search(artist)
            if not searched and (plain := without_backing_band(artist)):
                # The name decides what comes back, not just what is
                # accepted. Last.fm writes a backing band in where a
                # provider often does not, and searching the long form
                # returns other people's records or nothing at all.
                _LOGGER.debug("Nothing for %s; trying %s", artist, plain)
                searched = await self._async_search(plain)
            tracks = searched
        if cache is not None:
            cache[artist] = tracks
        return tracks

    def _rules(self) -> SelectionRules:
        """This player's settings, as the selection understands them."""
        settings = self._settings
        return SelectionRules(
            provider=settings.provider_filter,
            min_duration=settings.min_duration,
            clean_only=settings.explicit == EXPLICIT_CLEAN,
            prefer_explicit=settings.explicit == EXPLICIT_PREFER,
            skip_live=settings.filter_live,
            skip_holiday=settings.filter_holiday,
            fresh_days=settings.fresh_days,
        )

    def _select(
        self,
        tracks: list[TrackInfo],
        *,
        current_uri: str,
        excluded_titles: set[str],
        excluded_uris: set[str],
        excluded_artists: set[str],
        limit: int,
    ) -> tuple[list[str], list[str]]:
        """Filter one artist's tracks down to this batch's picks."""
        return select_tracks(
            tracks,
            self._rules(),
            current_uri=current_uri,
            excluded_titles=excluded_titles,
            excluded_uris=excluded_uris,
            excluded_artists=excluded_artists,
            limit=limit,
            now=dt_util.utcnow(),
        )

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
                self._lead_artist(current_seed, build_session),
                *await self._async_similar_artists(
                    self._pool_seed(current_seed, build_session),
                    similar_cache,
                    build_session,
                ),
            ]
            per_artist: list[list[str]] = []
            covered: set[str] = set()
            for index, artist in enumerate(round_artists):
                tracks = await self._async_tracks_for(artist, track_cache)
                uris, titles = self._select(
                    tracks,
                    current_uri="",
                    excluded_titles=seen_titles,
                    excluded_uris=set(ordered),
                    excluded_artists=covered,
                    limit=self._track_cap(is_seed=index == 0),
                )
                covered.add(artist.strip().lower())
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

    def _lead_artist(
        self, current_artist: str, session: ListeningSession | None = None
    ) -> str:
        """Which artist leads the batch and takes the seed lean.

        Artist radio leads with the artist you picked, not with whoever
        happens to be playing when the queue runs down. Without this the
        origin was excluded from its own station's refills: the pool is
        drawn from the origin and a seed is always stripped from its own
        similar-artists list, so the one artist the station is named after
        was the one artist that could never appear in it again.
        """
        active = session or self._listening
        if self._settings.seed_lean == SEED_LEAN_ARTIST and active.origin:
            return active.origin
        return current_artist

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
