"""Setting up, unloading and removing one configured player.

None of this was covered before: every bug in it (a renamed player
silently watched forever, storage files left behind, a delayed write
recreating them) was found by reading rather than by testing.
"""

import pytest

pytest.importorskip("pytest_homeassistant_custom_component")

from homeassistant.config_entries import ConfigEntryState  # noqa: E402
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN  # noqa: E402
from homeassistant.helpers import entity_registry as er  # noqa: E402

from custom_components.ma_curated_radio.const import (  # noqa: E402
    CONF_MA_CONFIG_ENTRY_ID,
    CONF_PLAYER,
    CONF_PLAYER_REGISTRY_ID,
    CONF_SEED_LEAN,
    DOMAIN,
    SEED_LEAN_DISCOVERY,
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


async def test_every_platform_brings_an_entity(hass, entry, entity_registry):
    """The test above promises buttons in its docstring and checks a
    switch and two sensors, so three of the five platforms could stop
    loading entirely without a failure. The dashboard in the README
    renders an error card for every entity that does not arrive."""
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    domains = {
        e.domain
        for e in er.async_entries_for_config_entry(entity_registry, entry.entry_id)
    }
    assert {"button", "number", "select", "sensor", "switch"} <= domains


async def test_setup_retries_until_music_assistant_is_loaded(
    hass, entry, music_assistant
):
    """The restart race, which sets up dead if it is not retried.

    Both integrations come back at once and there is no ordering between
    them. Refusing without asking to be retried leaves an entry that
    loaded, shows its entities, and will never build anything until
    somebody reloads it by hand.
    """
    music_assistant.mock_state(hass, ConfigEntryState.NOT_LOADED)

    assert not await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.SETUP_RETRY


async def test_a_skip_recorded_moments_before_unload_still_lands(
    hass, entry, hass_storage
):
    """Writes are batched over ten seconds, and unloading does not wait.

    So the last skip before a reload was lost, and the same delayed write
    landing after a removal recreated the storage file that removal had
    just tidied away.
    """
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    await entry.runtime_data.skips.async_record_skip("some song", "Some Artist")
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    stored = hass_storage[f"{DOMAIN}.{entry.entry_id}"]["data"]
    assert "some song" in stored["tracks"]


async def test_a_retired_style_name_is_brought_up_to_date(hass, entry):
    """One style had two names, and four places disagreed about which.

    Settings carried the old name forward, so the engine ran the right
    style. Nothing else did: the dropdown fell back to Balanced, the
    per-style numbers under it showed the values of a style that was not
    in force, and the options form seeded its own selector with a value
    that selector rejects, so pressing Submit failed on an untouched
    field. Rewriting the stored value once leaves one answer.
    """
    hass.config_entries.async_update_entry(entry, options={CONF_SEED_LEAN: "format"})

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.options[CONF_SEED_LEAN] == SEED_LEAN_DISCOVERY
    assert entry.runtime_data.settings.seed_lean == SEED_LEAN_DISCOVERY
    style = hass.states.get("select.family_room_stereo_station_style")
    assert style.state == SEED_LEAN_DISCOVERY


async def test_a_player_that_no_longer_exists_fails_instead_of_pretending(
    hass, entry, player, entity_registry
):
    """Green and dead was the worst of both.

    A warning in the log was the only sign: the entry loaded, brought up
    every entity, showed its switch on, and would never queue anything.
    """
    entity_registry.async_remove(player.entity_id)

    assert not await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.SETUP_ERROR


async def test_a_music_assistant_entry_that_is_gone_is_not_worth_retrying(
    hass, entry
):
    """Removed and re-added, Music Assistant gets a new entry id, and the
    one recorded here names an entry that no longer exists.

    Treated as "not loaded yet" this retried for ever, reporting that it
    was waiting for Music Assistant, while Music Assistant sat there
    loaded the whole time. Retrying cannot fix a stale id.
    """
    hass.config_entries.async_update_entry(
        entry, data={**entry.data, CONF_MA_CONFIG_ENTRY_ID: "no-such-entry"}
    )

    assert not await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.SETUP_ERROR


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
