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

from .const import MODE_REFILL, MODE_REPLACE, SKIP_GRACE_SECONDS
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
        self._task: asyncio.Task[None] | None = None

    def apply_settings(self, settings: Settings) -> None:
        """Adopt changed settings without rebuilding the detector."""
        self._settings = settings

    @property
    def expected_next(self) -> str:
        """URI the queue is expected to play after the current track."""
        return self._expected_next

    def async_start(self) -> CALLBACK_TYPE:
        """Begin watching the player. Returns the unsubscribe callback."""
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
        if new_state is None or new_state.state != "playing":
            return
        new_track = new_state.attributes.get("media_content_id")
        old_track = old_state.attributes.get("media_content_id") if old_state else None
        if new_track == old_track:
            return
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
        """Read the queue, pick a branch, then record the new expectation."""
        try:
            queue = await async_get_queue(self._hass, self._settings.player)
            if queue is None:
                return

            if self._expected_next and not self._in_cooldown():
                if queue.current_uri != self._expected_next:
                    # Someone jumped playback. Let the player settle before
                    # rewriting the queue underneath it.
                    await asyncio.sleep(self._settings.settle_seconds)
                    await self._engine.async_run(MODE_REPLACE)
                else:
                    # Normal progression, so the outgoing track either ran
                    # out or was skipped. A manual pick is deliberately not
                    # counted as a skip: jumping somewhere else is a choice
                    # about where to go, not a verdict on what was playing.
                    await self._async_record_feedback(outgoing)
                    if queue.remaining <= self._settings.refill_threshold:
                        await self._engine.async_run(MODE_REFILL)

            # The engine may have rewritten the queue, so re-read rather
            # than trusting the snapshot taken above.
            post = await async_get_queue(self._hass, self._settings.player)
            self._expected_next = post.next_uri if post else ""
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - the listener has to survive anything
            _LOGGER.exception("Curated radio batch failed while handling a track change")

    async def _async_record_feedback(self, outgoing: PlaybackSnapshot | None) -> None:
        """Record whether the track that just ended was skipped."""
        if outgoing is None:
            return
        if not outgoing.was_skipped(SKIP_GRACE_SECONDS):
            await self._skips.async_record_played()
            return

        _LOGGER.debug(
            "Skipped %s by %s at %.0fs of %.0fs",
            outgoing.title,
            outgoing.artist,
            outgoing.elapsed,
            outgoing.duration,
        )
        muted = await self._skips.async_record_skip(
            base_title(outgoing.title), outgoing.artist
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
