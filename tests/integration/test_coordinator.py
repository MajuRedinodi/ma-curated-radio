"""The wiring between the player, the queue and the engine.

``decide()`` has been tested since the day it was split out. The code that
feeds it never was: the elapsed-time clock, the state listener, the queue
read and the hand-off to the engine. F1 in docs/pick-seam-review-2026-09-29.md
lived entirely in that half, and a two-line test of the clock would have
shown it. These drive the real listener with real state changes and a fake
queue, and watch what reaches the engine.
"""

import pytest

pytest.importorskip("pytest_homeassistant_custom_component")

from datetime import timedelta  # noqa: E402

from homeassistant.core import State, SupportsResponse  # noqa: E402
from homeassistant.util import dt as dt_util  # noqa: E402

from custom_components.ma_curated_radio.const import (  # noqa: E402
    CONF_SETTLE_SECONDS,
    MA_DOMAIN,
    MODE_REPLACE,
)
from custom_components.ma_curated_radio.coordinator import _elapsed  # noqa: E402

PLAYER = "media_player.family_room_stereo"
PICK = "tidal://track/pick"
OURS = "tidal://track/ours"


def _attrs(position, updated_at, track=PICK):
    return {
        "media_content_id": track,
        "media_position": position,
        "media_position_updated_at": updated_at,
        "media_duration": 300,
    }


def test_the_clock_stops_while_the_player_is_paused():
    """A paused player does not advance, and its stored position does not
    move either, so adding wall time read a ten-minute pause as ten
    minutes of playback. On resume the real position was ten minutes
    less, which is what a song starting again looks like."""
    ten_minutes_ago = dt_util.utcnow() - timedelta(minutes=10)
    paused = State(PLAYER, "paused", _attrs(100, ten_minutes_ago))
    playing = State(PLAYER, "playing", _attrs(100, ten_minutes_ago))

    assert _elapsed(paused) == pytest.approx(100, abs=1)
    assert _elapsed(playing) == pytest.approx(700, abs=1)


@pytest.fixture
def queue(hass):
    """A fake Music Assistant queue: the picked song playing, twenty of
    ours behind it. Mutate the dict to change what the next read says."""
    facts = {"items": 21, "current_index": 0}

    async def get_queue(call):
        return {
            PLAYER: {
                "queue_id": "queue-1",
                "current_item": {
                    "media_item": {
                        "uri": PICK,
                        "name": "The Pick",
                        "artists": [{"name": "Somebody", "uri": "artist/1"}],
                    }
                },
                "next_item": {"media_item": {"uri": OURS, "name": "Ours"}},
                "items": facts["items"],
                "current_index": facts["current_index"],
            }
        }

    hass.services.async_register(
        MA_DOMAIN, "get_queue", get_queue, supports_response=SupportsResponse.ONLY
    )
    return facts


@pytest.fixture
async def listening(hass, entry, queue):
    """The integration set up on a player that is playing the pick, with
    the engine replaced by a recorder so a build is a fact, not a side
    effect. Settle time is zero so a decision lands within the test."""
    hass.config_entries.async_update_entry(entry, options={CONF_SETTLE_SECONDS: 0})
    hass.states.async_set(PLAYER, "playing", _attrs(200, dt_util.utcnow()))
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    runs: list[str] = []

    async def record(mode, *, continuing=True):
        runs.append(mode)

    entry.runtime_data.engine.async_run = record
    return runs


async def test_resuming_the_picked_song_after_a_pause_builds_nothing(
    hass, listening
):
    """Cell 21, end to end: the phone rang, the pick was paused, and
    pressing play again rebuilt the station around the same song."""
    ten_minutes_ago = dt_util.utcnow() - timedelta(minutes=10)
    hass.states.async_set(PLAYER, "paused", _attrs(100, ten_minutes_ago))
    await hass.async_block_till_done()
    hass.states.async_set(PLAYER, "playing", _attrs(100, dt_util.utcnow()))
    await hass.async_block_till_done()

    assert listening == []


async def test_re_picking_the_song_playing_still_builds(hass, listening, queue):
    """The 15 September case, through the wiring: the dashboard re-plays
    the song that is on, the queue collapses to it, the song starts over.
    That is a pick, and the rule above must not have cost it."""
    queue["items"] = 1
    hass.states.async_set(PLAYER, "playing", _attrs(0, dt_util.utcnow()))
    await hass.async_block_till_done()

    assert listening == [MODE_REPLACE]
