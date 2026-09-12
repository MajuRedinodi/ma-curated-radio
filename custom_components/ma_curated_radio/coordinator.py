"""Detection: decide when a batch is warranted.

Watches the player's ``media_content_id``. If the newly playing track is
not the one the queue predicted, somebody jumped playback by hand and the
stale tail should be replaced. If it is the predicted track and the queue
has nearly run out, top it up. Otherwise do nothing.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from homeassistant.core import (
    CALLBACK_TYPE,
    Event,
    EventStateChangedData,
    HomeAssistant,
    State,
    callback,
)
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.util import dt as dt_util

from .const import (
    MODE_REFILL,
    MODE_REPLACE,
    SKIP_BURST_SECONDS,
    SKIP_GRACE_SECONDS,
)
from .decide import (
    Decision,
    QueueFacts,
    decide,
    is_hunting,
    is_transitional,
    track_started,
)
from .engine import CuratedRadioEngine
from .feedback import PlaybackSnapshot, SkipMemory
from .filters import base_title
from .ma import async_get_queue
from .settings import Settings

_LOGGER = logging.getLogger(__name__)


def _snapshot(state: State | None) -> PlaybackSnapshot | None:
    """Capture what was playing, and how far into it we got.

    ``media_position`` only updates on seek and track change, so the real
    elapsed time is that value plus however long it has been reporting it.
    """
    if state is None or state.state != "playing":
        return None
    attrs = state.attributes
    duration = float(attrs.get("media_duration") or 0)
    position = float(attrs.get("media_position") or 0)
    updated_at = attrs.get("media_position_updated_at")
    elapsed = position
    if isinstance(updated_at, datetime):
        elapsed += max(0.0, (dt_util.utcnow() - updated_at).total_seconds())
    return PlaybackSnapshot(
        uri=str(attrs.get("media_content_id") or ""),
        title=str(attrs.get("media_title") or ""),
        artist=str(attrs.get("media_artist") or ""),
        duration=duration,
        elapsed=min(elapsed, duration) if duration else elapsed,
    )


class CuratedRadioDetector:
    """Turns track changes on one player into engine runs."""

    def __init__(
        self,
        hass: HomeAssistant,
        settings: Settings,
        engine: CuratedRadioEngine,
        skips: SkipMemory,
    ) -> None:
        """Start with no expectation, so the first track change bootstraps."""
        self._hass = hass
        self._settings = settings
        self._engine = engine
        self._skips = skips
        self._expected_next = ""
        self._last_manual_pick: datetime | None = None
        self._queue_items: int | None = None
        self._task: asyncio.Task[None] | None = None
        # The track last heard playing. Track changes are judged against
        # this rather than against the update before, because some players
        # change the track and start playing it in two separate updates.
        self._playing_track: str | None = None
        # A skip waiting to be confirmed by the next song playing through,
        # and when the last one arrived, so a run of them can be told from
        # a verdict on one song.
        self._pending_skip: PlaybackSnapshot | None = None
        self._last_skip_at: datetime | None = None

    def apply_settings(self, settings: Settings) -> None:
        """Adopt changed settings without rebuilding the detector."""
        self._settings = settings

    @property
    def expected_next(self) -> str:
        """URI the queue is expected to play after the current track."""
        return self._expected_next

    @property
    def last_manual_pick(self) -> datetime | None:
        """When somebody last jumped playback by hand.

        Home Assistant only marks a state change as user-driven when it
        originated inside Home Assistant, so a pick made in the Music
        Assistant or provider app carries no user context and looks exactly
        like an automation. This detection does not depend on that: the
        queue predicted one track and a different one started, whoever
        caused it and from wherever.
        """
        return self._last_manual_pick

    def restore_last_manual_pick(self, when: datetime) -> None:
        """Seed the timestamp from a restored sensor state after a restart."""
        if self._last_manual_pick is None:
            self._last_manual_pick = when

    def async_start(self) -> CALLBACK_TYPE:
        """Begin watching the player. Returns the unsubscribe callback."""
        # Whatever the player holds now, paused or not, is not a change.
        # Otherwise resuming after a restart would read as a pick.
        if (current := self._hass.states.get(self._settings.player)) is not None:
            self._playing_track = current.attributes.get("media_content_id")
        unsub = async_track_state_change_event(
            self._hass, [self._settings.player], self._handle_state_event
        )

        @callback
        def _stop() -> None:
            unsub()
            if self._task is not None and not self._task.done():
                self._task.cancel()

        return _stop

    @callback
    def _handle_state_event(self, event: Event[EventStateChangedData]) -> None:
        """Queue up a decision when the playing track actually changes."""
        new_state = event.data["new_state"]
        old_state = event.data["old_state"]
        if new_state is None:
            return
        new_track = new_state.attributes.get("media_content_id")
        if not track_started(new_state.state, new_track, self._playing_track):
            return
        self._playing_track = new_track
        if not self._settings.enabled:
            # Switched off. Still worth following the queue so that turning
            # it back on does not read the next track as a manual pick.
            self._expected_next = ""
            return

        outgoing = _snapshot(old_state)

        # Restart semantics: a rapid skip supersedes the decision in flight
        # rather than stacking a second one behind it.
        if self._task is not None and not self._task.done():
            self._task.cancel()
        self._task = self._hass.async_create_task(self._async_decide(outgoing))

    async def _async_decide(self, outgoing: PlaybackSnapshot | None) -> None:
        """Read the queue, act on the decision, record the new expectation."""
        try:
            queue = await async_get_queue(self._hass, self._settings.player)
            if queue is None:
                return
            facts = QueueFacts(
                current_uri=queue.current_uri,
                next_uri=queue.next_uri,
                items=queue.items,
                remaining=queue.remaining,
            )
            if is_transitional(facts):
                # Between tracks. Ignored outright, expectation included, so
                # the real track arriving next is judged against what was
                # expected before the blank rather than against the blank.
                return

            cooling = self._in_cooldown()
            verdict = decide(
                facts,
                expected_uri=self._expected_next,
                current_is_ours=self._engine.was_queued(queue.current_uri),
                next_is_ours=self._engine.was_queued(queue.next_uri),
                previous_items=self._queue_items,
                bulk_threshold=self._settings.bulk_tracks,
                refill_threshold=self._settings.refill_threshold,
                in_cooldown=cooling,
            )

            if verdict is Decision.PICKED:
                # Someone jumped playback. Let the player settle before
                # rewriting the queue underneath it.
                _LOGGER.debug("Manual pick: %s", queue.current_uri)
                self._last_manual_pick = dt_util.utcnow()
                await asyncio.sleep(self._settings.settle_seconds)
                await self._engine.async_run(MODE_REPLACE)
            elif verdict is Decision.REFILL:
                # Normal progression, so the outgoing track either ran out
                # or was skipped. A manual pick is deliberately not counted
                # as a skip: jumping somewhere else is a choice about where
                # to go, not a verdict on what was playing.
                await self._async_record_feedback(outgoing)
                await self._engine.async_run(MODE_REFILL)
            elif not cooling:
                # Nothing to do about the queue, but the track that just
                # ended was still either played through or skipped.
                await self._async_record_feedback(outgoing)

            # The engine may have rewritten the queue, so re-read rather
            # than trusting the snapshot taken above.
            post = await async_get_queue(self._hass, self._settings.player)
            self._expected_next = post.next_uri if post else ""
            self._queue_items = post.items if post else queue.items
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - the listener has to survive anything
            _LOGGER.exception("Curated radio batch failed while handling a track change")

    async def _async_record_feedback(self, outgoing: PlaybackSnapshot | None) -> None:
        """Record whether the track that just ended was skipped.

        A skip is a verdict on one song, but somebody hunting through the
        queue produces a run of them that says nothing about any of the
        songs passed over. Observed at one in the morning with a house full
        of kids: two songs were suppressed for a month by somebody holding
        the next button. So a skip is held back until a song is allowed to
        play, and a second skip arriving first throws both away.
        """
        if outgoing is None:
            return
        if not outgoing.was_skipped(SKIP_GRACE_SECONDS):
            await self._async_commit_skip()
            await self._skips.async_record_played()
            return

        now = dt_util.utcnow()
        since = (
            None
            if self._last_skip_at is None
            else (now - self._last_skip_at).total_seconds()
        )
        self._last_skip_at = now
        if is_hunting(since, SKIP_BURST_SECONDS):
            _LOGGER.debug(
                "Ignoring %s: skipped seconds after the last skip, so somebody "
                "is hunting rather than judging",
                outgoing.title,
            )
            self._pending_skip = None
            return
        self._pending_skip = outgoing

    async def _async_commit_skip(self) -> None:
        """Record the skip that has been waiting to be confirmed."""
        outgoing, self._pending_skip = self._pending_skip, None
        if outgoing is None:
            return

        _LOGGER.debug(
            "Skipped %s by %s at %.0fs of %.0fs",
            outgoing.title,
            outgoing.artist,
            outgoing.elapsed,
            outgoing.duration,
        )
        muted = await self._skips.async_record_skip(
            base_title(outgoing.title),
            outgoing.artist,
            label=" by ".join(p for p in (outgoing.title, outgoing.artist) if p),
        )
        if muted:
            _LOGGER.info(
                "%s will not be suggested for a while: %s skips in a row",
                muted,
                self._settings.artist_strike_limit,
            )

    def _in_cooldown(self) -> bool:
        """True while a separate queue-rewriting routine is still settling.

        A scheduled automation that rebuilds the whole queue would otherwise
        look exactly like a manual pick, and its huge queue would never
        need a refill.
        """
        entity_id = self._settings.cooldown_entity
        if not entity_id:
            return False
        state = self._hass.states.get(entity_id)
        if state is None:
            return False
        last_triggered = state.attributes.get("last_triggered")
        if not isinstance(last_triggered, datetime):
            return False
        elapsed = (dt_util.utcnow() - last_triggered).total_seconds()
        return elapsed < self._settings.cooldown_seconds
