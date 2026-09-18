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
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field, fields
from functools import partial
from typing import Any

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import (
    CROWD_SIZE,
    DEFAULT_PLAYLIST_LENGTH,
    DEPTH_TOP_TRACKS,
    EXPLICIT_CLEAN,
    EXPLICIT_PREFER,
    FAMILIARITY_EXPONENT,
    HEARD_MINUTES,
    LANE_LOOKUPS_PER_BATCH,
    LASTFM_POOL_SIZE,
    MODE_REFILL,
    MODE_REPLACE,
    PAIR_LISTENER_RATIO,
    PLAYED_LOOKUPS_PER_BATCH,
    PLAYLIST_CHUNK,
    PLAYLIST_MAX_ROUNDS,
    QUEUED_MEMORY,
    SEARCH_LIMIT,
    SEED_LEAN_ARTIST,
    SEED_LEAN_DISCOVERY,
    SEED_LEAN_MULTIPLIER,
    SESSION_EXPIRY_HOURS,
    SPLIT_DUO_CREDITS,
    STATION_SAVE_DELAY,
    STATION_STORAGE_VERSION,
    TIER_DECAY,
    USABLE_SHARE,
    signal_update,
)
from .decide import leading_pool, starts_station
from .facts import (
    MISS_NO_ARTICLE,
    MISS_NO_DATE,
    MISS_WRONG_ARTIST,
    Fact,
    FactBook,
)
from .feedback import SkipMemory
from .filters import (
    CANDIDATE_BANDS,
    FOOTNOTE_SHARE,
    LANE_CLASH,
    LANE_MATCH,
    LANE_UNKNOWN,
    NEIGHBOURHOOD_SIZE,
    TIER_GOLD,
    TIER_POWER,
    SelectionRules,
    base_title,
    clean_similar_artists,
    close_to_home,
    credits_artist,
    crowd_pool,
    depth_bar,
    drop_outliers,
    fallen_by,
    is_gold,
    keep_one_act,
    lane_match,
    lane_of,
    lead_among_credits,
    lean_toward_strength,
    matches_provider,
    median_of,
    move_on,
    neighbourhood_strength,
    performs,
    prefer_titles,
    reach_of,
    select_fresh_first,
    select_tracks,
    sequence_tiered,
    song_audience,
    song_shares,
    stratified_bands,
    strong_artists,
    tier_of,
    too_deep,
    usable_songs,
    weighted_sample,
    without_backing_band,
    year_span,
)
from .history import TitleHistory
from .lastfm import (
    async_get_album_of,
    async_get_album_tags,
    async_get_artist_listeners,
    async_get_similar_artists,
    async_get_similar_tracks,
    async_get_top_tracks,
)
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
from .wikipedia import ArticleFacts, async_find_article, async_get_facts

_LOGGER = logging.getLogger(__name__)


def _note(fact: Fact) -> tuple[str, ...]:
    """What to show beside a track in the batch listing.

    Its year, and where it charted if anything says so. Both are omitted
    rather than filled in when unknown: a record with no placing shown
    has not been shown to have missed the charts, only that Wikipedia
    does not say, and eleven of sixteen canonical records fall in that
    gap.
    """
    parts: list[str] = []
    if fact.year is not None:
        parts.append(str(fact.year))
    if (chart := fact.best_chart) is not None:
        parts.append(f"{chart[0]} {chart[1]}")
    return tuple(parts)


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
class _Pools:
    """Each artist's picks for one batch, before they are ordered."""

    artists: list[str] = field(default_factory=list)
    per_artist: list[list[str]] = field(default_factory=list)
    title_by_uri: dict[str, str] = field(default_factory=dict)
    rank: dict[str, int] = field(default_factory=dict)
    # Each song's listeners as a fraction of its artist's biggest, where
    # Last.fm has the song. The tiering used to guess this from position
    # and the guess inverted on deep positions; the numbers arrive here
    # anyway for the depth limit, so they are kept rather than discarded.
    share: dict[str, float] = field(default_factory=dict)
    # The same songs raw listener counts, which reach only reconstructs
    # and distorts. Kept for judging whether a station is degrading.
    audience: dict[str, int] = field(default_factory=dict)


@dataclass(slots=True)
class BatchResult:
    """What one engine run actually did."""

    mode: str
    seed_artist: str = ""
    # The artist the similar-artist pool was drawn from. The same as the
    # seed on a pick; on a refill, usually someone else.
    pool_from: str = ""
    artists: list[str] = field(default_factory=list)
    queued: int = 0
    # What it actually queued, as "Artist - Title", in playing order. The
    # count above says how many; this says which, which is the only way to
    # judge a batch without waiting an hour to hear it. The batch as
    # built, so it does not shrink as songs play and it knows nothing
    # about anything added by hand: the Music Assistant panel is still
    # where the live queue lives.
    tracks: list[str] = field(default_factory=list)
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
    # The era the batch actually covers, as "1971-1989", and how many of
    # its records that span is drawn from. Read together: a tight span
    # over three known years says very little, and the two apart are
    # misleading in opposite directions.
    year_span: str = ""
    years_known: int = 0
    # How far this batch has fallen from the one the session opened with,
    # as a percentage, by two different measures of the same thing.
    #
    # Instrumentation only. Nothing reads these yet, and that is the
    # point: the plan is to let replays back in once a station has
    # degraded, and there is no honest way to pick the threshold without
    # watching real sessions first. Two measures because they disagree,
    # and the disagreement is the finding. Across five hours of country
    # on 2026-09-18, reach fell 46% from the session's start while the
    # hour still sounded right to the listener, because reach follows the
    # size of the *artists* and the *records* stayed big.
    reach_drop: int = 0
    audience_drop: int = 0
    audience_median: int = 0
    # Power slots the clock asked for and the pool could not supply. The
    # hard end of the same question: a station that cannot fill its hour
    # has run out of material rather than merely drifted. Rarer than it
    # sounds, because Power is a share of an artist's own biggest, so any
    # artist's best record fills a slot however small the act.
    power_short: int = 0
    # When the batch was queued, as ISO time. Kept because the sensor's own
    # timestamps restart with Home Assistant, and a restored batch would
    # otherwise look as though it had just been built.
    built_at: str = ""

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
        facts: FactBook | None = None,
    ) -> None:
        """Set up the engine and its per-player memory."""
        self._hass = hass
        self._entry_id = entry_id
        self._settings = settings
        self._session = session
        self._skips = skips
        # What is known about records, shared with every other player
        # rather than learned again per room. Defaulted so a test can
        # build an engine without one, in which case nothing is
        # remembered past the session and the lane falls back to album
        # tags exactly as it did before any of this existed.
        self._facts = facts if facts is not None else FactBook()
        # How many candidates this batch may still look up while choosing
        # what to play. Reset per batch, since the point is to bound one
        # batch rather than the evening. The records it goes on to queue
        # are dated out of a separate allowance this cannot touch, so a
        # long selection can no longer leave the batch itself undated.
        self._lane_lookups_left = LANE_LOOKUPS_PER_BATCH
        self._history = TitleHistory(settings.history_minutes, HEARD_MINUTES)
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
        # A credited name that is only a footnote to its pair, mapped to the
        # credited artist who should lead instead. Settled alongside the
        # alias, on the pick that starts a station.
        self._lead_override: dict[str, str] = {}
        # Artist audience sizes, kept for the life of the entry. Neighbours
        # recur heavily between batches, so this usually saves the lookups
        # entirely rather than merely spreading them out.
        self._sizes: dict[str, int] = {}
        # Last.fm's similar-artist lists by lower-cased artist, for weighing
        # reseed candidates. Similarity barely moves within a session.
        self._similar: dict[str, list[tuple[str, float]]] = {}
        # Each artist's best-known songs on Last.fm with their listeners, for
        # the depth limit. Kept for the life of the entry, like sizes.
        self._top_tracks: dict[str, list[tuple[str, int]]] = {}
        # Each record's era and genres, from its album tags, keyed by
        # (artist, base title). Albums recur heavily inside a lane, so the
        # second batch of an evening pays almost nothing for this.
        self._lanes: dict[tuple[str, str], tuple[set[int], set[str]]] = {}
        # The lane of the song that started this station. Every reseed is
        # judged against it rather than against wherever the last hour
        # drifted to, so an off-era track can play without becoming the
        # seed that carries its era into the rest of the evening.
        self._origin_lane: tuple[set[int], set[str]] = (set(), set())
        # What the session opened with, so later batches can be compared
        # against where the listener started rather than against the last
        # batch. Batch to batch is too noisy to threshold on: one real
        # session ran 511k, 564k, 456k, 278k, rising once before falling.
        self._origin_reach = 0
        self._origin_audience = 0
        # Its own generator so reseed choices can be reproduced in tests.
        self._rng = random.Random()
        # Artists that actually contributed to the last batch. A refill
        # reseeds from the stronger half of these rather than from
        # whatever is playing, which stops a station sliding into
        # obscurity over an evening.
        self._last_pool: list[str] = []
        # Who led that batch. A refill never reseeds from them again, or a
        # station anchored close to home just rebuilds the same hour.
        self._last_lead = ""
        # The Power-tier records of the last batch, as (artist, title). A
        # refill reseeds its crowd from one of these, which is what keeps
        # an evening track-level instead of handing hour two back to the
        # artist graph.
        self._last_power: list[tuple[str, str]] = []
        # How many songs by each artist this station has played, so an act
        # with one record retires after playing it while an act with fifty
        # can be returned to all evening. Cleared with the session.
        self._played: dict[str, int] = {}
        # Set when a pick arrives while a batch is building. The build in
        # progress is then for a song the listener has already left.
        self._superseded = False
        # Everything above that describes the station in progress, kept on
        # disk so a restart does not end it. Separate from skip memory's
        # store because it is short-lived by nature and safe to lose.
        self._store: Store[dict[str, Any]] = Store(
            hass, STATION_STORAGE_VERSION, f"ma_curated_radio.{entry_id}.station"
        )

    async def async_load(self) -> None:
        """Pick the station up where it was before a restart.

        A session that has gone stale in the meantime is restored anyway
        and then replaced by the usual expiry check on the next batch, so
        last night's station does not carry into the morning.
        """
        try:
            data = await self._store.async_load()
        except Exception as err:  # noqa: BLE001 - a bad store must not block setup
            _LOGGER.warning("Could not read the saved station: %s", err)
            return
        if not data:
            return
        self._listening = ListeningSession.from_dict(data.get("session"))
        self._last_pool = [str(a) for a in data.get("last_pool") or []]
        self._last_lead = str(data.get("last_lead") or "")
        self._origin_reach = int(data.get("origin_reach") or 0)
        self._origin_audience = int(data.get("origin_audience") or 0)
        saved_lane = data.get("origin_lane") or [[], []]
        self._origin_lane = (
            {int(d) for d in saved_lane[0]},
            {str(g) for g in saved_lane[1]},
        )
        self._played = {
            str(who): int(count)
            for who, count in (data.get("played") or {}).items()
        }
        self._last_power = [
            (str(who), str(song))
            for who, song in (data.get("last_power") or [])
            if who and song
        ]
        self._alias = dict(data.get("alias") or {})
        self._lead_override = dict(data.get("lead_override") or {})
        # What this integration queued, which is how a refill knows the
        # music running out is its own. Without it every first refill after
        # a restart read as somebody else's music and re-anchored the
        # station to whichever neighbour happened to be playing, which is
        # the exact failure the rest of this store exists to prevent.
        self._queued = deque(
            (str(uri) for uri in data.get("queued") or []), maxlen=QUEUED_MEMORY
        )
        self._history.restore(data.get("history"))
        # The last batch too, so the dashboard shows the station that is
        # playing rather than "Unknown" until the next refill.
        saved_batch = data.get("last_batch")
        if isinstance(saved_batch, dict):
            known = {f.name for f in fields(BatchResult)}
            try:
                self._last_batch = BatchResult(
                    **{k: v for k, v in saved_batch.items() if k in known}
                )
            except TypeError:
                self._last_batch = None
        if self._listening.active:
            _LOGGER.debug(
                "Resumed the station anchored to %s, last led by %s",
                self._listening.origin,
                self._last_lead or "nobody yet",
            )

    def _station_dict(self) -> dict[str, Any]:
        """The station in progress, as the store holds it."""
        return {
            "session": self._listening.as_dict(),
            "last_pool": self._last_pool,
            "last_lead": self._last_lead,
            "last_power": [list(pair) for pair in self._last_power],
            "played": self._played,
            # Sets are not JSON, so the station lane travels as lists.
            "origin_reach": self._origin_reach,
            "origin_audience": self._origin_audience,
            "origin_lane": [
                sorted(self._origin_lane[0]),
                sorted(self._origin_lane[1]),
            ],
            "alias": self._alias,
            "lead_override": self._lead_override,
            "queued": list(self._queued),
            "history": self._history.as_list(),
            "last_batch": asdict(self._last_batch) if self._last_batch else None,
        }

    def _save_station(self) -> None:
        """Persist the station in progress, batched with other writes."""
        self._store.async_delay_save(self._station_dict, STATION_SAVE_DELAY)

    async def async_flush(self) -> None:
        """Write the station now rather than in ten seconds.

        Called when the entry unloads, so a batch built moments before a
        reload or a deletion is not still waiting in a timer that outlives
        the objects that scheduled it.
        """
        await self._store.async_save(self._station_dict())

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

    async def async_run(self, mode: str, *, continuing: bool = True) -> BatchResult:
        """Build and enqueue one batch.

        ``continuing`` says whether the music running out was this
        integration's own. A refill onto somebody else's queue is not a
        continuation of the station that happened to run earlier: load a
        jazz album at nine and the last track of it used to be topped up
        with neighbours of the Fleetwood Mac station from eight.

        An overlapping refill is skipped rather than queued, matching the
        ``mode: single`` behaviour of the script this replaces: a refill
        that waits a minute loses nothing.

        A replace is different, because it means somebody picked something,
        and the latest pick has to win. One arriving mid-build marks the
        build in progress as superseded, and the newest pick is built as
        soon as the lock frees. Dropping it instead let a station built
        from the first of two quick picks be written in behind the second:
        a remix swapped for the original forty seconds in, with a cold
        neighbourhood taking a minute to build, only came out right
        because both were by the same artist.
        """
        if self._lock.locked():
            if mode == MODE_REPLACE:
                self._superseded = True
                _LOGGER.debug("A newer pick arrived mid-build; building it next")
                return BatchResult(mode=mode, skipped_reason="superseded")
            _LOGGER.debug("A batch is already building; skipping %s request", mode)
            return BatchResult(mode=mode, skipped_reason="already_running")
        async with self._lock:
            self._superseded = False
            result = await self._async_build(mode, continuing=continuing)
            while self._superseded:
                self._superseded = False
                result = await self._async_build(MODE_REPLACE)
        # A run that queued nothing does not replace the record of the last
        # one that did. It used to, so a pointless run moments after a good
        # batch left the dashboard reporting no batch at all.
        if result.ran or self._last_batch is None:
            self._last_batch = result
        if result.ran:
            self._save_station()
        async_dispatcher_send(self._hass, signal_update(self._entry_id))
        return result

    async def _async_build(self, mode: str, *, continuing: bool = True) -> BatchResult:
        """Do the work of one batch."""
        self._lane_lookups_left = LANE_LOOKUPS_PER_BATCH
        settings = self._settings
        queue = await async_get_queue(self._hass, settings.player)
        if queue is None:
            return BatchResult(mode=mode, skipped_reason="no_queue")
        if not queue.seed_artist:
            _LOGGER.debug("No artist on the current track; nothing to seed from")
            return BatchResult(mode=mode, skipped_reason="no_seed_artist")

        seed = queue.seed_artist
        starting = starts_station(
            refilling=mode == MODE_REFILL, continuing=continuing
        )
        # Settle which name Last.fm should be asked about, once, on the
        # song that starts the station. A duet that merely comes up later
        # must not redefine it. A refill onto music that is not ours starts
        # a station too, so it needs this as much as a pick does: without
        # it, topping up a Sonny and Cher album asked Last.fm about "Sonny"
        # and got Skrillex.
        if starting:
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
        # refill continues the one already running, unless what ran out was
        # not ours, in which case that music is the station now.
        self._anchor(seed, restart=starting)
        # Where the neighbours come from. On a pick, the artist picked; on a
        # refill, an artist from the stronger half of the last batch,
        # preferring those nearest the origin.
        # Reseeding from the last batch is only right while this is the
        # same station. Topping up somebody else's album builds from what
        # they put on, the same way a pick does.
        refilling = not starting
        pool_from = await self._async_pool_seed(
            seed,
            previous=self._last_pool if refilling else None,
            last_lead=self._last_lead if refilling else "",
        )
        # The artist the batch is built around. On a refill that is the
        # reseed artist too, not whoever happened to be playing when the
        # queue ran low: the lead takes the lead slots, and handing them to
        # whoever was in the ear gave the smallest artist in a batch three
        # more of her deepest songs. Simulated, letting the reseed artist
        # lead kept a station's reach up by about a seventh over four
        # refills. In artist radio both are the origin either way.
        # And a credited name that is a footnote to its pair hands the lead
        # to the star, while the neighbours still come from the pair.
        lead = self._led_by(pool_from if refilling else self._lead_artist(seed))
        # Which records the pool wants from each artist, when the pool came
        # from the song's crowd rather than the artist's neighbours. Empty
        # otherwise, which leaves selection exactly as it was.
        wanted: dict[str, list[str]] = {}
        # A pick asks about the song picked. A refill asks about one of the
        # strong records of the batch just played, which is what keeps the
        # whole evening track-level rather than handing hour two back to
        # the artist graph.
        crowd_from, crowd_of = await self._async_crowd_seed(
            starting, seed, queue.current_title, lead
        )
        artists = [
            lead,
            *await self._async_similar_artists(
                pool_from,
                crowd_from=crowd_from,
                crowd_of=crowd_of,
                wanted=wanted,
            ),
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

        # How deep into each artist a batch may reach: their A-tracks
        # always, and past those only songs enough people actually know. A
        # tight fence refills from the same artists, and without this it
        # reached a little further down each of them every time round.
        gather = partial(
            self._async_pools,
            artists,
            current_uri=queue.current_uri,
            recent_titles=recent_titles,
            already_queued=already_queued,
            heard=self._history.heard(),
            wanted=wanted,
        )
        bar = depth_bar(await self._async_sizes(artists))
        pools = await gather(bar=bar)
        if not pools.per_artist and bar:
            # Better a deeper song than a station that stops.
            _LOGGER.debug("Nothing within reach for %s; lifting the depth limit", lead)
            pools = await gather(bar=0)
        pool_artists, per_artist = pools.artists, pools.per_artist
        title_by_uri, rank = pools.title_by_uri, pools.rank

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
        tiers = tier_of(sized, TIER_DECAY, rank, pools.share)
        # Before the clock rather than after, because the Gold slot is
        # decided on a release year and the clock has to know which
        # record is the throwback before it chooses where to put it. The
        # cost is looking up the few drawn records that will not be
        # played, which is four in a batch of twenty.
        known = await self._async_known(pool_artists, per_artist, title_by_uri)
        years = {uri: fact.year for uri, fact in known.items() if fact.year is not None}
        self._mark_gold(
            pool_artists, per_artist, title_by_uri, years, tiers, pools.share
        )
        ordered = sequence_tiered(
            per_artist,
            tiers,
            self._settings.clock,
            max_consecutive=self._settings.max_consecutive,
            leading=leading,
            length=self._settings.batch_length,
        )
        if self._superseded:
            # Somebody picked something else while this was being built.
            # Writing it now would put a station for a song they have
            # already moved on from behind the one they chose.
            _LOGGER.debug("Discarding the batch for %s; a newer pick arrived", lead)
            return BatchResult(
                mode=mode, seed_artist=lead, artists=artists, skipped_reason="superseded"
            )
        # Judged on what is about to be queued rather than on what was,
        # which is Jeff's point and the right one: a check that runs after
        # the enqueue tells you an hour has degraded while that hour is
        # already playing, and the correction arrives an hour late.
        # ``ordered`` is the batch the clock built; enqueue only ever
        # drops from it, so this is the same batch judged one step
        # earlier.
        audience_median = median_of(
            pools.audience[uri] for uri in ordered if uri in pools.audience
        )
        scored = reach_of(sized, TIER_DECAY, rank, pools.share)
        opening_reach = median_of(scored.get(uri, 0) for uri in ordered)
        # A station that starts fresh is its own baseline, so the first
        # batch of a session can never read as degraded.
        if starting or not self._origin_reach:
            self._origin_reach, self._origin_audience = opening_reach, audience_median
        reach_drop = fallen_by(opening_reach, self._origin_reach)
        audience_drop = fallen_by(audience_median, self._origin_audience)
        if reach_drop or audience_drop:
            _LOGGER.debug(
                "Station has fallen %s%% by reach and %s%% by audience since it "
                "started, before this batch plays",
                reach_drop,
                audience_drop,
            )
        enqueued = await self._async_enqueue(ordered, mode)
        if enqueued:
            self._history.add([title_by_uri[uri] for uri in enqueued])

        reach_median, reach_low, counts = self._summarise(
            enqueued, sized, tiers, rank, pools.share
        )
        wanted_power = sum(
            1
            for index in range(len(enqueued))
            if self._settings.clock[index % len(self._settings.clock)] == TIER_POWER
        )
        if enqueued:
            self._last_pool = list(pool_artists)
            self._last_lead = lead
            self._remember(enqueued, pool_artists, per_artist, title_by_uri, tiers)
        playing = set(enqueued)
        played_years = {uri: y for uri, y in years.items() if uri in playing}
        notes = {uri: _note(f) for uri, f in known.items() if uri in playing}

        _LOGGER.debug(
            "Queued %s track(s) in %s mode, led by %s, neighbours from %s, via %s; "
            "median reach %s, weakest %s, tiers %s",
            len(enqueued),
            mode,
            lead,
            pool_from,
            ", ".join(artists),
            f"{reach_median:,}",
            f"{reach_low:,}",
            counts or "none",
        )
        return BatchResult(
            mode=mode,
            seed_artist=lead,
            pool_from=pool_from,
            artists=artists,
            queued=len(enqueued),
            tracks=self._listed(
                enqueued, pool_artists, per_artist, title_by_uri, tiers, notes
            ),
            reach_median=reach_median,
            reach_low=reach_low,
            tiers=counts,
            year_span=year_span(played_years.values()),
            years_known=len(played_years),
            reach_drop=reach_drop,
            audience_drop=audience_drop,
            audience_median=audience_median,
            power_short=max(0, wanted_power - counts.get(TIER_POWER, 0)),
            built_at=dt_util.utcnow().isoformat() if enqueued else "",
        )

    async def _async_pools(
        self,
        artists: list[str],
        *,
        current_uri: str,
        recent_titles: set[str],
        already_queued: set[str],
        bar: int,
        cache: dict[str, list[TrackInfo]] | None = None,
        provider: str = "",
        heard: Mapping[str, float] | None = None,
        wanted: Mapping[str, list[str]] | None = None,
    ) -> _Pools:
        """Each artist's picks for one batch or playlist round, unordered.

        ``wanted`` names the records a song's crowd asked for from each
        artist. They go to the front of that artist's list before anything
        is chosen, so the crowd decides which record plays where the
        provider's relevance ranking used to. It is a reordering, not a
        filter: a record the provider does not carry must not leave the
        artist contributing nothing.

        ``bar`` is the depth limit's listener threshold; zero lifts it.
        ``provider``, if given, keeps only that provider's tracks.
        ``heard`` are titles played earlier today, used only as a fallback.
        """
        pools = _Pools()
        # Artists already given a pool. Anything crediting one of them is
        # theirs, so a later pool cannot smuggle the same act back in.
        covered: set[str] = set()
        known = await self._async_top_tracks(artists) if bar else {}
        for index, artist in enumerate(artists):
            if self._spent(artist, known.get(artist)):
                # Everything this act is known for has already played
                # tonight. Reaching further into them is how hour four
                # turns into album tracks; letting the slot go is how a
                # station narrows onto the artists who still have records
                # left, which is what a real one does.
                _LOGGER.debug("%s has nothing left tonight", artist)
                continue
            tracks = await self._async_tracks_for(artist, cache)
            if wanted:
                tracks = prefer_titles(tracks, wanted.get(artist, ()))
            artist_rank = self._rank(tracks, covered)
            pools.rank.update(artist_rank)
            cap = self._track_cap(is_seed=index == 0)
            uris, titles = self._select(
                tracks,
                current_uri=current_uri,
                excluded_titles=recent_titles | set(pools.title_by_uri.values()),
                heard=heard,
                excluded_uris=already_queued
                | too_deep(
                    tracks, artist_rank, known.get(artist), bar, cap, floor=USABLE_SHARE
                ),
                excluded_artists=covered,
                limit=cap,
            )
            covered.add(artist.strip().lower())
            if provider:
                kept = [
                    (uri, title)
                    for uri, title in zip(uris, titles, strict=True)
                    if matches_provider(uri, provider)
                ]
                uris, titles = [u for u, _ in kept], [t for _, t in kept]
            if uris:
                pools.artists.append(artist)
                pools.per_artist.append(uris)
                titled = dict(zip(uris, titles, strict=True))
                pools.title_by_uri.update(titled)
                pools.share.update(song_shares(titled, known.get(artist)))
                pools.audience.update(song_audience(titled, known.get(artist)))
        return pools

    async def _async_top_tracks(
        self, artists: list[str]
    ) -> dict[str, list[tuple[str, int]] | None]:
        """Each artist's best-known songs on Last.fm, cached like sizes.

        A failed lookup caches nothing and comes back as None, which the
        depth limit reads as "do not cut", so an outage costs nothing.
        """
        key = self._settings.lastfm_api_key
        if not key:
            return {}
        wanted = [a for a in artists if a.lower() not in self._top_tracks]
        if wanted:
            found = await asyncio.gather(
                *(
                    async_get_top_tracks(self._session, key, artist, DEPTH_TOP_TRACKS)
                    for artist in wanted
                )
            )
            for artist, songs in zip(wanted, found, strict=True):
                if songs is not None:
                    self._top_tracks[artist.lower()] = songs
        return {a: self._top_tracks.get(a.lower()) for a in artists}

    def _summarise(
        self,
        enqueued: list[str],
        sized: list[tuple[str, list[str], int]],
        tiers: dict[str, str],
        rank: dict[str, int],
        share: dict[str, float] | None = None,
    ) -> tuple[int, int, dict[str, int]]:
        """Median reach, weakest reach, and the tier split of a batch.

        Judging a batch on the way out means its shape is visible before
        it plays rather than at track ten. Reach is absolute so batches
        compare across stations; the tier counts are relative to their
        own pool and only describe the texture within one.
        """
        reach = reach_of(sized, TIER_DECAY, rank, share)
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
        *,
        crowd_from: str = "",
        crowd_of: str = "",
        wanted: dict[str, list[str]] | None = None,
    ) -> list[str]:
        """Pick a capped set of similar artists.

        ``crowd_from`` and ``crowd_of`` name the record to draw the pool
        from, when there is one and the setting allows it, in place of the
        seed's artist neighbours. On a pick that is the song picked; on a
        refill, a strong record of the batch just played. ``wanted`` is
        filled in with the records that crowd asked for from each artist,
        which is what selection later prefers.

        The pool is deliberately much larger than the cap, because the goal
        is what a station playing the seed artist would also play rather
        than that artist's three nearest neighbours. Selection from it is
        weighted by match score, not flat: a deep pool sampled uniformly is
        how batches ended up full of defensible artists nobody knew.
        """
        settings = self._settings
        if settings.max_artists <= 0 or not settings.lastfm_api_key:
            return []
        names: list[tuple[str, float]] = []
        from_crowd = False
        if crowd_of and crowd_from:
            # The song's own crowd, where there is one. Falls through to
            # the artist graph on an obscure record that has no crowd,
            # which is the case that would otherwise build nothing at all.
            names, titles = await self._async_song_crowd(crowd_from, crowd_of)
            if wanted is not None:
                wanted.update(titles)
            from_crowd = bool(names)
            if not names:
                _LOGGER.debug("No crowd for %s; using the artist graph", crowd_of)
        if not names:
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
        # Count the hop in the graph actually being walked. A crowd is
        # reached from a record already playing in this station, so its
        # artists are one step from THAT artist, not from whoever the pool
        # was seeded on. Measuring them against the artist graph counted a
        # hop nothing took, and since a crowd deliberately reaches names
        # artist similarity never would, they were routinely judged too
        # far and the whole station fell back to the artist graph.
        parent = crowd_from if from_crowd and crowd_from else seed
        allowed = set(active.eligible(parent, [name for name, _ in candidates], cap))
        if not allowed and active.origin and parent != active.origin:
            # At the edge of the fence with nothing eligible nearby. Pull
            # back toward the origin rather than stalling out there, on
            # the artist graph, because a crowd that has just been judged
            # entirely out of bounds is not the thing to try again.
            #
            # The crowd is deliberately NOT carried into this call. It
            # cannot be: the crowd's parent does not change, so the same
            # judgement would repeat and the recursion would never end.
            # Logged at info rather than debug because it switches the
            # whole of 0.40 off for a batch, and the one time it happened
            # silently it looked like the era filter was broken when it
            # had simply never run.
            self._log_fence_fallback(from_crowd, crowd_of or parent, cap, active.origin)
            return await self._async_similar_artists(active.origin, cache, active)

        eligible = [pair for pair in candidates if pair[0] in allowed]
        if from_crowd:
            # A crowd's tail is as strong as its head, so banding it beats
            # weighting it: weighting would crowd the draw onto the same
            # few names every day and never reach the forgotten hits.
            chosen = await self._async_draw_in_lane(
                eligible, settings.max_artists, crowd_from, crowd_of, wanted
            )
        else:
            # An artist pool's tail really is obscure, which is what
            # weighting was added for in 0.6.0 and why it stays here.
            chosen = weighted_sample(
                eligible,
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

    async def async_search(
        self, query: str, limit: int, artist: str = ""
    ) -> list[TrackInfo]:
        """Find tracks by title, by artist, or by both.

        Music Assistant's own search action takes no limit and returns
        five, which is too few to find a particular recording of a
        well-covered song: searching for "Stayin' Alive" returns three
        Bee Gees pressings and nothing else. The native client takes a
        limit, so this exists to make that reachable.

        Giving an artist as well does two things. It goes into the search
        text, since the provider ranks on the whole phrase, and it then
        filters the results down to tracks that artist is actually
        credited on. Without that second step a cover is unfindable: the
        original always outranks it.

        If that filter leaves nothing, the unfiltered results come back
        instead. An empty list cannot distinguish "no such recording"
        from "credited differently", and only one of those is worth
        showing somebody.
        """
        phrase = " ".join(part for part in (query, artist) if part).strip()
        found = await self._native.async_search_tracks(
            phrase, limit, credited_to=artist
        )
        if found is None:
            found = await async_search_tracks(
                self._hass, self._settings.ma_config_entry_id, phrase
            )
            if artist:
                found = [t for t in found if credits_artist(t.artists, artist)]
        if found or not artist:
            return found
        # Filtering by artist found nothing, which is not the same as the
        # recording being absent. Credits disagree with a name for plenty
        # of ordinary reasons: Last.fm asks for "Tom Petty and The
        # Heartbreakers" where Tidal credits plain "Tom Petty", and a
        # guest is sometimes left off entirely. Hand back the unfiltered
        # matches rather than nothing, since the person asking can see
        # which is which and an empty list tells them nothing at all.
        _LOGGER.debug(
            "Nothing credited to %s for %s; returning every match", artist, phrase
        )
        loose = await self._native.async_search_tracks(phrase, limit, credited_to="")
        if loose is None:
            loose = await async_search_tracks(
                self._hass, self._settings.ma_config_entry_id, phrase
            )
        return loose

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
        self._lead_override.pop(key, None)
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
            await self._async_choose_lead(seed, credited, alone, pair)
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

    async def _async_choose_lead(
        self, seed: str, credited: list[str], alone: int, pair: int
    ) -> None:
        """Hand the lead to the star when the first credit is a footnote.

        Only reached for a duo, and only costs a lookup when the first
        credited name draws a small share of the pair: see
        ``lead_among_credits``. The neighbours still come from the pair.
        """
        if alone >= pair * FOOTNOTE_SHARE:
            return
        others = [name for name in credited if name.lower() != seed.lower()]
        counts = await asyncio.gather(
            *(
                async_get_artist_listeners(
                    self._session, self._settings.lastfm_api_key, name
                )
                for name in others
            )
        )
        sizes = {seed: alone, **dict(zip(others, counts, strict=True))}
        lead = lead_among_credits(seed, sizes, pair)
        if lead != seed:
            self._lead_override[seed.lower()] = lead
            _LOGGER.debug(
                "%s is a footnote to %s (%s of %s listeners); %s leads",
                seed,
                " & ".join(credited),
                alone,
                pair,
                lead,
            )

    def _led_by(self, artist: str) -> str:
        """The artist a station built from this one is actually led by."""
        return self._lead_override.get(artist.lower(), artist)

    async def _async_song_crowd(
        self, artist: str, title: str
    ) -> tuple[list[tuple[str, float]], dict[str, list[str]]]:
        """The artists a song's own crowd suggests, and the records it wants.

        Asked about the song rather than its artist, which is the only way
        to learn *which* record by a neighbour belongs next to this one.
        The artist graph answers with a name and leaves the provider's
        relevance ranking to choose the song, and that ranking is what put
        "Summer Madness" on a Michael Jackson station instead of
        "Cherish".

        Empty on any failure, including an obscure pick that simply has no
        crowd, which the caller reads as "use the artist graph".
        """
        if not title:
            return [], {}
        crowd = await async_get_similar_tracks(
            self._session,
            self._settings.lastfm_api_key,
            self._alias.get(artist.lower(), artist),
            base_title(title),
            CROWD_SIZE,
        )
        if not crowd:
            return [], {}
        names, wanted = crowd_pool(crowd, artist, 0)
        _LOGGER.debug(
            "Song crowd for %s by %s: %d artists, %d records",
            title,
            artist,
            len(names),
            sum(len(titles) for titles in wanted.values()),
        )
        return names, wanted

    @staticmethod
    def _listed(
        enqueued: list[str],
        pool_artists: list[str],
        per_artist: list[list[str]],
        title_by_uri: dict[str, str],
        tiers: dict[str, str],
        notes: dict[str, tuple[str, ...]] | None = None,
    ) -> list[str]:
        """The batch as a person would read it, in playing order.

        Each line carries its tier, because the hour is laid out to a
        pattern and a track cannot be judged without knowing which slot
        it was filling: a record that would be a poor Power track is
        exactly what a Deep slot is for. Without it every line reads as
        a claim that this song is a hit.

        And its year where one is known, because the era rule is the
        thing hardest to judge by ear: a record that sounds wrong in an
        hour usually sounds wrong because of when it was made, and that
        is invisible until it is written down. A line with no year is a
        record nothing has told us about, never a modern one.

        The artist is the one whose pool the track came from rather than
        the credits on the record, which is deliberate: it says which
        slot of the batch each song filled, so a batch that has quietly
        become one act under three names is visible at a glance.
        """
        artist_of = {
            uri: artist
            for artist, uris in zip(pool_artists, per_artist, strict=True)
            for uri in uris
        }
        listed: list[str] = []
        for uri in enqueued:
            title = title_by_uri.get(uri, "")
            who = artist_of.get(uri)
            label = tiers.get(uri, "?")
            line = f"[{label}] {who} - {title}" if who else f"[{label}] {title}"
            # The year, and the chart placing where one was found. Shown
            # only where present, deliberately: a record with no placing
            # here has not been shown to have missed the charts, it has
            # been shown that Wikipedia does not say, and a blank is the
            # honest rendering of that.
            note = ", ".join(
                str(part) for part in (notes or {}).get(uri, ()) if part
            )
            if note:
                line = f"{line} ({note})"
            listed.append(line)
        return listed

    def _remember(
        self,
        enqueued: list[str],
        pool_artists: list[str],
        per_artist: list[list[str]],
        title_by_uri: dict[str, str],
        tiers: dict[str, str],
    ) -> None:
        """What the next batch needs to know about the one just queued.

        Its strongest records, as (artist, title), because the next batch
        reseeds its crowd from one of them and Last.fm is asked by name
        rather than by URI. And how many songs each artist has now had,
        which is what retires an act once its hits are spent.
        """
        artist_of = {
            uri: artist
            for artist, uris in zip(pool_artists, per_artist, strict=True)
            for uri in uris
        }
        for uri in enqueued:
            if who := artist_of.get(uri):
                key = who.strip().lower()
                self._played[key] = self._played.get(key, 0) + 1
        self._last_power = [
            (artist_of[uri], title_by_uri[uri])
            for uri in enqueued
            if tiers.get(uri) == TIER_POWER and uri in artist_of
        ]

    def _spent(self, artist: str, known: Sequence[tuple[str, int]] | None) -> bool:
        """Whether this artist has any record left worth playing tonight.

        A one-hit wonder has one, and once it has played, reaching further
        into them means their second song, which is 4% the size of their
        first. A giant has dozens, all of them real, so the same rule lets
        a station come back to Prince three times and to Rockwell once
        without either being told to.

        Only ever a veto on an artist, never on a record: which song plays
        is the crowd's decision. So the bar is deliberately loose, because
        a tight one penalises an artist whose first record is enormous.

        False when nothing is known, so a Last.fm outage costs variety
        rather than the batch.
        """
        if not self._settings.seed_from_song or not known:
            return False
        played = self._played.get(artist.strip().lower(), 0)
        return played >= usable_songs(known, USABLE_SHARE) > 0

    async def _async_crowd_seed(
        self, starting: bool, seed: str, playing: str, lead: str
    ) -> tuple[str, str]:
        """The record whose crowd this batch is drawn from, if any.

        A pick asks about the song picked, which is the whole statement of
        what somebody wanted. A refill asks about a strong record of the
        batch just played, which is what keeps an evening track-level
        rather than handing hour two back to the artist graph.

        Both empty when the setting is off, or when a refill has no Power
        tier behind it to draw on, and the artist graph takes over.
        """
        if not self._settings.seed_from_song:
            return "", ""
        if starting:
            # The station's own lane is settled here, on the song that
            # started it, and every later reseed is judged against it
            # rather than against whatever the last hour drifted to.
            self._origin_lane = await self._async_lane(seed, playing)
            return seed, playing
        return await self._async_reseed_song(lead)

    async def _async_reseed_song(self, lead: str) -> tuple[str, str]:
        """Which record of the last batch the next hour is built from.

        Sampled among the Power tier rather than taken from the top of it.
        Always choosing the strongest was tried at artist level in 0.32.0
        and failed on inspection: Fleetwood Mac alternated between the
        same two neighbourhoods all evening and Nancy Sinatra sat at one
        value for three refills. Deterministic reseeds oscillate.

        Records by the artist leading this batch are passed over, which is
        ``move_on`` at song level. Preferring what is closest to home made
        the origin the closest candidate of all in 0.31.0, and a Texas
        Hold 'Em station came back as Beyoncé's circle twice running, 23
        of 39 tracks.

        Empty when the last batch had no Power tier to draw on, which
        leaves the refill on the artist graph exactly as before.
        """
        candidates = [
            (who, song)
            for who, song in self._last_power
            if not credits_artist([who], lead)
        ] or self._last_power
        if not candidates:
            return "", ""
        if self._origin_lane != (set(), set()):
            # Permissive about what plays, strict about what seeds. A
            # record from the wrong era is one song; the same record as a
            # seed carries its era into every track of the next hour and
            # every hour after that. So a candidate that cannot be placed
            # is passed over while any that positively matches the
            # station's own lane is available.
            ranked: dict[int, list[tuple[str, str]]] = {}
            for who, song in candidates:
                rank = lane_match(await self._async_lane(who, song), self._origin_lane)
                ranked.setdefault(rank, []).append((who, song))
            best = ranked.get(LANE_MATCH) or ranked.get(LANE_UNKNOWN) or candidates
            if len(best) < len(candidates):
                _LOGGER.debug(
                    "Reseeding from %d of %d records that fit the station's lane",
                    len(best),
                    len(candidates),
                )
            candidates = best
        return self._rng.choice(candidates)

    @staticmethod
    def _log_fence_fallback(
        from_crowd: bool, subject: str, cap: int | None, origin: str
    ) -> None:
        """Say when the fence sent a batch back to artist similarity.

        Info rather than debug on the crowd path, because it turns the
        whole of the song-seeding work off for that batch. The one time
        it happened quietly it looked exactly like a broken era filter,
        when the filter had simply never been reached.
        """
        if from_crowd:
            _LOGGER.info(
                "Every artist %s suggests is outside %s degrees of %s; "
                "this batch falls back to artist similarity",
                subject,
                cap,
                origin,
            )
        else:
            _LOGGER.debug("Nothing within %s degrees of %s; falling back", cap, subject)

    async def _async_draw_in_lane(
        self,
        eligible: list[tuple[str, float]],
        count: int,
        artist: str,
        title: str,
        wanted: Mapping[str, list[str]] | None,
    ) -> list[str]:
        """Draw the batch's artists, dropping those from the wrong hour.

        A song's crowd is chosen by who listens, not by what a record
        sounds like, so a Michael Jackson pick returns his brothers' 1970
        Motown beside mid-80s pop, and a Hank Williams Jr. pick returns
        his father's 1949. Neither is obscure, which is why nothing else
        catches them: they are famous records from the wrong hour.

        Drawn first and checked second, which is the opposite of what
        this did at first and both cheaper and more correct. Filtering
        the crowd up front meant bounding the work to its head, because
        checking a hundred records to use sixteen is waste; but the
        banded draw then reached deliberately into the tail the bound had
        skipped. On a real Hank Williams Jr. batch twelve of sixteen
        artists came from past that bound and were never checked at all,
        including the 1949 record the rule exists for. Checking only what
        is drawn costs sixteen lookups rather than forty and leaves
        nothing unchecked.

        A rejected candidate is replaced **from its own band**, which is
        what keeps the hour the shape the clock asked for: refilling a
        failed Power slot out of the tail gives the right number of
        tracks and the wrong evening.
        """
        # The lane the STATION started in, not the lane of whichever record
        # seeded this hop. Taking it from the hop let the era walk: a
        # station begun on a 1992 record was judging candidates against
        # 1970 four refills later, because John Denver's record had seeded
        # that one, and it refused Alan Jackson for being two decades from
        # a lane the station had never been in. Each hop was then fencing
        # out the artists that belonged to the hour before it. Same reason
        # the degree fence counts from the origin rather than from
        # wherever the music has got to.
        lane = self._origin_lane
        if lane == (set(), set()):
            # No origin lane: a station restored from before this existed,
            # or a pick whose album Last.fm cannot place. Fall back to the
            # hop's own lane, which is what this used to do always.
            lane = await self._async_lane(artist, title)
        bands = stratified_bands(eligible, count, CANDIDATE_BANDS, self._rng)
        if lane == (set(), set()):
            _LOGGER.debug("No lane for %s; drawing without one", title)
            return [name for quota, order in bands for name in order[:quota]]

        chosen: list[str] = []
        dropped: list[str] = []
        for quota, order in bands:
            # Three grades, filled in order. A record known to fit is
            # best. Next best is an artist this station has already
            # played: in lane by construction, since it was accepted
            # earlier, and heard without being skipped. Only then an
            # artist nothing is known about.
            #
            # That ordering used to be the other way round, and on a real
            # batch only 3 of 59 candidates were placeable, so the filter
            # was replacing known-wrong with unknown. Past the repeat
            # window a proven track beats an unproven one, which is
            # Jeff's own rule: rather a repeat at three hours than an
            # hour of B cuts.
            fits: list[str] = []
            heard: list[str] = []
            unknown: list[str] = []
            for name in order:
                if len(fits) >= quota:
                    break
                rank = lane_match(
                    await self._async_lane(name, self._record(name, wanted)), lane
                )
                if rank == LANE_CLASH:
                    dropped.append(name)
                elif rank == LANE_MATCH:
                    fits.append(name)
                elif self._played.get(name.strip().lower(), 0):
                    heard.append(name)
                else:
                    unknown.append(name)
            chosen.extend((fits + heard + unknown)[:quota])
        if dropped:
            _LOGGER.debug(
                "Out of lane for %s (%s / %s): %s",
                title,
                sorted(lane[0]) or "any era",
                ", ".join(sorted(lane[1])[:3]) or "any genre",
                ", ".join(dropped[:8]),
            )
        return chosen

    @staticmethod
    def _record(artist: str, wanted: Mapping[str, list[str]] | None) -> str:
        """The record the crowd asked for from this artist, if it named one.

        The lane has to be read off the song the crowd offered rather than
        off whatever the artist is best known for, because those differ
        precisely where this matters: Hank Williams' own era is not the
        era of the compilation his biggest song now sits on.
        """
        titles = (wanted or {}).get(artist) or []
        return titles[0] if titles else ""

    async def _async_lane(self, artist: str, title: str) -> tuple[set[int], set[str]]:
        """The era and genres of one record, cached for the entry's life.

        Two sources, and they fail in opposite directions. Album tags are
        cheap and cover nearly everything, but the era they give is the
        era of whatever album a song sits on now, which is how Hank
        Williams' 1951 recording came to read as the undated compilation
        carrying it. A release year from Wikipedia is the record's own, so
        where it exists it wins outright.

        Neither source is asked twice. The in-memory cache covers a
        session and the fact book covers a restart, which is why the first
        batch after one no longer re-learns the evening before it.
        """
        key = (artist.lower(), base_title(title))
        if key in self._lanes:
            return self._lanes[key]
        decades, genres = await self._async_tag_lane(artist, title)
        if (fact := await self._async_fact(artist, title, key[1])) is not None:
            if fact.decade is not None:
                # One known decade in place of whatever the album claimed,
                # rather than both: the point is to correct the compilation,
                # and keeping its decade too would leave the record matching
                # the era it was reissued in.
                decades = {fact.decade}
            genres |= set(fact.genres)
        self._lanes[key] = (decades, genres)
        return self._lanes[key]

    async def _async_tag_lane(
        self, artist: str, title: str
    ) -> tuple[set[int], set[str]]:
        """What this record's album tags claim about it."""
        api_key = self._settings.lastfm_api_key
        album = await async_get_album_of(self._session, api_key, artist, title)
        tags = (
            await async_get_album_tags(self._session, api_key, artist, album)
            if album
            else []
        )
        return lane_of(tags, artist)

    async def _async_fact(self, artist: str, title: str, base: str) -> Fact | None:
        """What is known about one record, looking it up if nothing is.

        Both spellings of the title are needed and they are not
        interchangeable. ``base`` is what the record is filed under, so a
        remaster and an album cut share one entry. ``title`` is what goes
        to Wikipedia, because the folding strips the punctuation and
        "Hey, Good Lookin'" is a better search than "hey good lookin".

        Held to selection's own budget, which is separate from the one
        the chosen batch is dated out of and cannot be spent from it. A
        first batch against an empty book would otherwise want two
        Wikipedia requests for every candidate it considers, including
        the ones it goes on to reject, and those are the requests worth
        giving up first.
        """
        if not self._facts.needs_lookup(artist, base):
            return self._facts.touch(artist, base)
        if self._lane_lookups_left <= 0:
            # Deliberately records nothing, so the next batch tries again.
            # Album tags carry the lane in the meantime, which is the
            # whole reason this is the budget that runs out first.
            return self._facts.get(artist, base)
        self._lane_lookups_left -= 1
        return await self._async_learn(artist, title, base)

    def _write_fact(
        self,
        artist: str,
        base: str,
        article: str,
        detail: ArticleFacts | None,
    ) -> Fact:
        """File what one article said about one record.

        A failure is recorded as carefully as a success, because each kind
        wants a different fix and an undifferentiated pile of misses is no
        use as a work list. Reaching here at all means an article was
        found, so what is left is a thin infobox or the wrong recording.

        The wrong recording is the one worth watching for. A cover shares
        its title with the original, whose article usually wins the search
        outright, and taking its year silently dates the cover to whenever
        somebody else first made the record. Nothing about that looks like
        a failure downstream: it is a plausible year, from a real article,
        for the wrong decade.
        """
        found = detail or ArticleFacts()
        if found.year is not None and not found.song:
            # Not an article about a record, so whatever date it carries
            # is not a release date. This is the one the performer check
            # cannot catch: a film has no song infobox at all, so there
            # is no artist field to disagree with and the year would sail
            # through looking perfectly reasonable.
            _LOGGER.debug(
                "%s is not a song article, so %s is not a release year",
                article,
                found.year,
            )
            return self._facts.remember(
                artist, base, article=article, miss=MISS_NO_ARTICLE
            )
        if found.year is not None and not performs(artist, found.performer):
            _LOGGER.debug(
                "%s is a cover: %s is about %s, not %s, so its %s is not ours",
                base,
                article,
                found.performer,
                artist,
                found.year,
            )
            return self._facts.remember(
                artist, base, article=article, miss=MISS_WRONG_ARTIST
            )
        if found.year is not None:
            _LOGGER.debug(
                "%s by %s is a %s record, from %s", base, artist, found.year, article
            )
        return self._facts.remember(
            artist,
            base,
            year=found.year,
            genres=found.genres,
            charts=found.charts,
            article=article,
            miss="" if found.year is not None else MISS_NO_DATE,
        )

    async def _async_learn(self, artist: str, title: str, base: str) -> Fact:
        """Ask Wikipedia about one record and write down what it said."""
        article = await async_find_article(self._session, artist, title)
        if not article:
            return self._facts.remember(artist, base, miss=MISS_NO_ARTICLE)
        detail = (await async_get_facts(self._session, [article])).get(article)
        return self._write_fact(artist, base, article, detail)

    def _mark_gold(
        self,
        pool_artists: list[str],
        per_artist: list[list[str]],
        title_by_uri: dict[str, str],
        years: dict[str, int],
        tiers: dict[str, str],
        share: Mapping[str, float],
    ) -> str:
        """Promote at most one drawn record to Gold, and say which.

        One, not every record that qualifies. Jeff's spec is a single
        older record about every two hours, and labelling three of them
        would leave two competing for one slot and then ranking below
        Secondary everywhere else, which strands good records for no
        reason.

        The strongest qualifier wins, measured by the same share the
        tiers use, because the slot wants the throwback everybody knows
        rather than merely the oldest thing in the pool.

        Only a record already filed as Power is eligible. Gold is old and
        not obscure, and the tier is the familiarity test we already
        have, so this needs no second one.
        """
        lane = self._origin_lane
        if lane == (set(), set()):
            return ""
        artist_of = {
            uri: artist
            for artist, uris in zip(pool_artists, per_artist, strict=True)
            for uri in uris
        }
        best, top = "", -1.0
        for uri, artist in artist_of.items():
            if tiers.get(uri) != TIER_POWER:
                continue
            fact = self._facts.get(artist, base_title(title_by_uri.get(uri, "")))
            if fact is None or not is_gold(years.get(uri), fact.genres, lane):
                continue
            if (held := share.get(uri, 0.0)) > top:
                best, top = uri, held
        if best:
            tiers[best] = TIER_GOLD
            _LOGGER.debug(
                "%s is this batch's Gold: a %s record in a lane of %s",
                title_by_uri.get(best, best),
                years.get(best),
                ", ".join(str(decade) for decade in sorted(lane[0])) or "no decade",
            )
        return best

    async def _async_known(
        self,
        pool_artists: list[str],
        per_artist: list[list[str]],
        title_by_uri: dict[str, str],
    ) -> dict[str, int]:
        """When each drawn record was made, looking up what is not known.

        One search per record, then a single content fetch covering every
        article found, which is what the fifty-article ceiling is for.
        Asking per record instead would double the traffic for the same
        answers.

        Done after the batch is drawn but before the clock orders it, so
        the requests are spent on records that were actually chosen rather
        than on every candidate considered and dropped, while still
        landing in time for the Gold slot to be decided on a year.
        Selection itself only looks one record up per artist, which is
        enough to place that artist in a lane and nowhere near enough to
        date an hour.

        The few drawn records that do not go on to play are looked up too,
        four in a batch of twenty, and that is the price of knowing the
        year before the running order is settled rather than after.

        Records are filed under the artist whose pool the track came from,
        which is the same name the lane check used, so the two agree.
        Anything still unknown afterwards is simply absent rather than
        present with a guess.
        """
        drawn = [
            (artist, title_by_uri.get(uri, ""), uri)
            for artist, uris in zip(pool_artists, per_artist, strict=True)
            for uri in uris
        ]
        await self._async_learn_all(
            [(who, title) for who, title, _ in drawn], PLAYED_LOOKUPS_PER_BATCH
        )
        known: dict[str, Fact] = {}
        for who, title, uri in drawn:
            fact = self._facts.get(who, base_title(title))
            if fact is not None:
                known[uri] = fact
        return known

    async def _async_learn_all(
        self, pairs: list[tuple[str, str]], budget: int
    ) -> None:
        """Ask Wikipedia about several records in as few requests as it
        can be done in.

        The budget is passed rather than held, because it belongs to one
        batch and there is only ever one call per batch. A counter on the
        engine would be state that has to be remembered to reset.
        """
        wanted: list[tuple[str, str, str]] = []
        for artist, title in pairs:
            base = base_title(title)
            if not self._facts.needs_lookup(artist, base):
                self._facts.touch(artist, base)
                continue
            if budget <= 0:
                break
            budget -= 1
            wanted.append((artist, title, base))
        found: list[tuple[str, str, str]] = []
        for artist, title, base in wanted:
            article = await async_find_article(self._session, artist, title)
            if article:
                found.append((artist, base, article))
            else:
                self._facts.remember(artist, base, miss=MISS_NO_ARTICLE)
        if not found:
            return
        # Two records can resolve to one article, so the fetch is asked
        # for the distinct names and the answers are handed back out.
        details = await async_get_facts(
            self._session, sorted({article for _, _, article in found})
        )
        for artist, base, article in found:
            self._write_fact(artist, base, article, details.get(article))

    @property
    def facts_known(self) -> int:
        """How many records anything at all is known about."""
        return len(self._facts)

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
        """Get an artist's best-known tracks, by relevance-ranked search.

        The optional cache is per playlist build. The same few artists
        recur in every round, and without it each recurrence costs a fresh
        search plus a track fetch.
        """
        if cache is not None and artist in cache:
            return cache[artist]
        # Native search first, purely so a limit can be passed. The service
        # action returns five tracks and no more, which is less than one
        # batch uses, so an artist reached on a refill had nothing left
        # that had not just played.
        tracks = await self._async_search(artist)
        if not tracks and (plain := without_backing_band(artist)):
            # The name decides what comes back, not just what is accepted.
            # Last.fm writes a backing band in where a provider often does
            # not, and searching the long form returns other people's
            # records or nothing at all.
            _LOGGER.debug("Nothing for %s; trying %s", artist, plain)
            tracks = await self._async_search(plain)
        # One act per name: a namesake that the credit check cannot tell
        # apart is told apart by its provider ID instead.
        tracks = keep_one_act(tracks, artist)
        if cache is not None:
            cache[artist] = tracks
        return tracks

    async def _async_program(
        self,
        pool_artists: list[str],
        per_artist: list[list[str]],
        rank: dict[str, int],
        share: dict[str, float] | None = None,
    ) -> list[str]:
        """Order one playlist round the same way the live queue is.

        A round built by plain round-robin plays every artist's biggest
        track and then every artist's second, so a long playlist arrives
        as a sawtooth of strong and weak stretches rather than an even one.
        """
        sizes = await self._async_sizes(pool_artists)
        sized = [
            (artist, uris, sizes.get(artist, 0))
            for artist, uris in zip(pool_artists, per_artist, strict=True)
        ]
        return sequence_tiered(
            per_artist,
            tier_of(sized, TIER_DECAY, rank, share),
            self._settings.clock,
            max_consecutive=self._settings.max_consecutive,
        )

    def _rank(self, tracks: list[TrackInfo], covered: set[str]) -> dict[str, int]:
        """Each usable track's position in its artist's own ordering.

        The position the song would hold in a first batch: after the
        filters that decide whether a track is usable at all, and before
        anything that depends on what has already played. Raw provider
        order would not do, because it would penalise an artist whose
        search results are full of live versions and karaoke.
        """
        usable, _ = self._select(
            tracks,
            current_uri="",
            excluded_titles=set(),
            excluded_uris=set(),
            excluded_artists=covered,
            limit=0,
        )
        return {uri: position for position, uri in enumerate(usable)}

    def _rules(self) -> SelectionRules:
        """This player's settings, as the selection understands them."""
        settings = self._settings
        return SelectionRules(
            provider=settings.provider_filter,
            min_duration=settings.min_duration,
            clean_only=settings.explicit == EXPLICIT_CLEAN,
            prefer_explicit=settings.explicit == EXPLICIT_PREFER,
            skip_live=settings.filter_live,
            skip_remix=settings.filter_remix,
            skip_holiday=settings.filter_holiday,
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
        heard: Mapping[str, float] | None = None,
    ) -> tuple[list[str], list[str]]:
        """Filter one artist's tracks down to this batch's picks.

        ``heard``, if given, holds back songs played earlier today until the
        artist has nothing fresh left.
        """
        if heard:
            return select_fresh_first(
                tracks,
                self._rules(),
                heard=heard,
                current_uri=current_uri,
                excluded_titles=excluded_titles,
                excluded_uris=excluded_uris,
                excluded_artists=excluded_artists,
                limit=limit,
            )
        return select_tracks(
            tracks,
            self._rules(),
            current_uri=current_uri,
            excluded_titles=excluded_titles,
            excluded_uris=excluded_uris,
            excluded_artists=excluded_artists,
            limit=limit,
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
        previous_round: list[str] | None = None
        previous_lead = ""

        # Scoped to this build. The same artists recur every round, and
        # re-fetching them was most of the time a long build took.
        similar_cache: dict[str, list[tuple[str, float]]] = {}
        track_cache: dict[str, list[TrackInfo]] = {}

        for _ in range(PLAYLIST_MAX_ROUNDS):
            if len(ordered) >= length:
                break
            # Each round continues from the one before, the same way a
            # refill continues from the batch before it.
            pool_from = await self._async_pool_seed(
                current_seed,
                build_session,
                previous=previous_round,
                last_lead=previous_lead,
            )
            lead = (
                pool_from
                if previous_round
                else self._led_by(self._lead_artist(current_seed, build_session))
            )
            round_artists = [
                lead,
                *await self._async_similar_artists(
                    pool_from, similar_cache, build_session
                ),
            ]
            gather = partial(
                self._async_pools,
                round_artists,
                current_uri="",
                recent_titles=seen_titles,
                already_queued=set(ordered),
                cache=track_cache,
                provider=provider,
            )
            bar = depth_bar(await self._async_sizes(round_artists))
            pools = await gather(bar=bar)
            if not pools.per_artist and bar:
                pools = await gather(bar=0)
            if not pools.per_artist:
                break
            seen_titles.update(pools.title_by_uri.values())
            artists_used.extend(a for a in pools.artists if a not in artists_used)
            ordered.extend(
                await self._async_program(
                    pools.artists, pools.per_artist, pools.rank, pools.share
                )
            )
            previous_round = list(pools.artists)
            previous_lead = lead

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
        """How far this station style lets a session wander, or None.

        Artist radio has nothing to fence: it leads and reseeds from the
        origin every time, so every pool is the origin's own neighbours.
        Applying the cap anyway meant a setting of zero rejected all of
        them and left the station playing one artist and nobody else,
        which is not what "zero" should mean and not what the fence is
        for. Discovery is unfenced by design.
        """
        if self._settings.seed_lean in (SEED_LEAN_ARTIST, SEED_LEAN_DISCOVERY):
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
            if not restart:
                # A refill onto a session that had gone stale, typically the
                # first music of the morning after a station last night.
                # Last night's batch is not something to reseed from.
                self._last_pool = []
                self._last_lead = ""
                self._last_power = []
                self._origin_lane = (set(), set())
                # And last night's artists are available again. Retirement
                # is about not exhausting an act within one evening, not a
                # month-long ban; the skip memory is what does that.
                self._played = {}
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

    async def _async_pool_seed(
        self,
        current_artist: str,
        session: ListeningSession | None = None,
        *,
        previous: list[str] | None = None,
        last_lead: str = "",
    ) -> str:
        """Which artist the similar-artist pool is drawn from.

        Artist radio always draws from the artist you picked, however far
        into the evening it is.

        A manual pick always draws from the artist picked. That is the
        whole of what a pick means, and the batch before it is somebody
        else's station.

        A continuation (a refill, or a playlist's next round) draws from
        ``previous``, the artists of the batch or round before it, rather
        than from whatever happens to be in the ear at the moment it
        fires. A big artist's neighbours are mostly smaller than it, so
        reseeding off the current track steps down more often than up, and
        over an evening that is a one-way ratchet into obscurity. An
        observed evening fell from a median reach of 995,000 to 338,000
        across two reseeds that way.

        Drawing at random from the stronger half keeps the station moving,
        which is the point of a refill, while stopping the movement being
        consistently downward; preferring those closest to the origin
        stops it moving sideways; and leaning toward the candidates whose
        own neighbours are strongest stops a big artist with a small
        circle from taking the next hour down with it.

        ``previous`` is passed in rather than read from the live queue's
        state. Reading it here let a car playlist reseed every round from
        whatever the living room last played.
        """
        active = session or self._listening
        if self._settings.seed_lean == SEED_LEAN_ARTIST and active.origin:
            return active.origin
        if not previous:
            return current_artist
        strong = strong_artists(
            [(name, self._sizes.get(name.lower(), 0)) for name in previous]
        )
        strong = close_to_home(
            move_on(strong, last_lead),
            active.degree_of,
            fenced=self._degree_cap is not None,
        )
        if not strong:
            return current_artist
        strengths = {
            name: await self._async_neighbourhood(name) for name in strong
        } if len(strong) > 1 else {}
        chosen = lean_toward_strength(strong, strengths, self._rng)
        _LOGGER.debug(
            "Reseeding from %s rather than %s, which is playing; neighbourhoods %s",
            chosen,
            current_artist,
            ", ".join(f"{n} {s:,}" for n, s in strengths.items()) or "not compared",
        )
        return chosen

    async def _async_neighbourhood(self, artist: str) -> int:
        """Median audience of the neighbours this artist would bring.

        Both lookups are cached for the life of the entry, so weighing the
        same candidates again on later refills costs nothing.
        """
        key = artist.lower()
        if key not in self._similar:
            self._similar[key] = await self._async_lookup_similar(artist)
        neighbours = [
            name
            for name, _ in clean_similar_artists(self._similar[key], artist)
        ][:NEIGHBOURHOOD_SIZE]
        sizes = await self._async_sizes(neighbours)
        return neighbourhood_strength(neighbours, sizes)
