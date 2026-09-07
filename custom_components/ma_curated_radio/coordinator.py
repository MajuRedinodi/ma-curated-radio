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
    callback,
)
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.util import dt as dt_util

from .const import MODE_REFILL, MODE_REPLACE
from .engine import CuratedRadioEngine
from .ma import async_get_queue
from .settings import Settings

_LOGGER = logging.getLogger(__name__)


class CuratedRadioDetector:
    """Turns track changes on one player into engine runs."""

    def __init__(
        self,
        hass: HomeAssistant,
        settings: Settings,
        engine: CuratedRadioEngine,
    ) -> None:
        """Start with no expectation, so the first track change bootstraps."""
        self._hass = hass
        self._settings = settings
        self._engine = engine
        self._expected_next = ""
        self._task: asyncio.Task[None] | None = None

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

        # Restart semantics: a rapid skip supersedes the decision in flight
        # rather than stacking a second one behind it.
        if self._task is not None and not self._task.done():
            self._task.cancel()
        self._task = self._hass.async_create_task(self._async_decide())

    async def _async_decide(self) -> None:
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
                elif queue.remaining <= self._settings.refill_threshold:
                    await self._engine.async_run(MODE_REFILL)

            # The engine may have rewritten the queue, so re-read rather
            # than trusting the snapshot taken above.
            post = await async_get_queue(self._hass, self._settings.player)
            self._expected_next = post.next_uri if post else ""
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - the listener has to survive anything
            _LOGGER.exception("Curated radio batch failed while handling a track change")

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
