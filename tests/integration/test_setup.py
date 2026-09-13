"""Setting up, unloading and removing one configured player.

None of this was covered before: every bug in it (a renamed player
silently watched forever, storage files left behind, a delayed write
recreating them) was found by reading rather than by testing.
"""

import pytest

pytest.importorskip("pytest_homeassistant_custom_component")

from homeassistant.config_entries import ConfigEntryState  # noqa: E402
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN  # noqa: E402

from custom_components.ma_curated_radio.const import (  # noqa: E402
    CONF_PLAYER,
    CONF_PLAYER_REGISTRY_ID,
    DOMAIN,
)


async def test_an_entry_sets_up_and_brings_its_entities(hass, entry):
    """The switch, the sensors and the buttons all arrive."""
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    assert hass.states.get("switch.family_room_stereo_curated_radio").state == "on"
    assert hass.states.get("sensor.family_room_stereo_last_batch_seed") is not None
    assert hass.states.get("sensor.family_room_stereo_version") is not None
    # Nothing has been built yet, so the batch sensors say so rather than
    # inventing a station.
    assert hass.states.get("sensor.family_room_stereo_last_batch_built").state == (
        STATE_UNKNOWN
    )


async def test_setup_records_the_players_registry_id(hass, entry, player):
    """It is what lets a rename be followed later."""
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.data[CONF_PLAYER_REGISTRY_ID] == player.id


async def test_a_renamed_player_is_followed(hass, entry, player, entity_registry):
    """The failure this exists for: no events, no batches, no error.

    Everything targets the entity_id, so a rename used to leave this
    watching a name nothing would ever report again.
    """
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    entity_registry.async_update_entity(
        player.entity_id, new_entity_id="media_player.family_room_speakers"
    )
    await hass.async_block_till_done()

    assert entry.data[CONF_PLAYER] == "media_player.family_room_speakers"
    assert entry.unique_id == "media_player.family_room_speakers"


async def test_unloading_leaves_nothing_behind(hass, entry):
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.NOT_LOADED
    # Home Assistant keeps the entity and marks it unavailable rather than
    # removing it, so that a reload does not orphan anything pointing at it.
    assert (
        hass.states.get("switch.family_room_stereo_curated_radio").state
        == STATE_UNAVAILABLE
    )


async def test_removing_an_entry_forgets_what_it_remembered(
    hass, entry, hass_storage
):
    """Both stores are keyed by entry id, so nothing could ever read them
    again, and they used to stay in .storage for good."""
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    # Pretend both stores had been written.
    for key in (f"{DOMAIN}.{entry.entry_id}", f"{DOMAIN}.{entry.entry_id}.station"):
        hass_storage[key] = {"version": 1, "data": {}}

    assert await hass.config_entries.async_remove(entry.entry_id)
    await hass.async_block_till_done()

    assert f"{DOMAIN}.{entry.entry_id}" not in hass_storage
    assert f"{DOMAIN}.{entry.entry_id}.station" not in hass_storage
