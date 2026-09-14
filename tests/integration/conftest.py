"""Fixtures for the tests that run against a real Home Assistant.

Skipped entirely where the framework is not installed, so the fast suite
still runs on a machine with nothing set up: see requirements_test.txt.
"""

import pytest

pytest.importorskip("pytest_homeassistant_custom_component")

from homeassistant.config_entries import ConfigEntryState  # noqa: E402
from pytest_homeassistant_custom_component.common import (  # noqa: E402
    MockConfigEntry,
)

from custom_components.ma_curated_radio.const import (  # noqa: E402
    CONF_LASTFM_API_KEY,
    CONF_MA_CONFIG_ENTRY_ID,
    CONF_PLAYER,
    DOMAIN,
    MA_DOMAIN,
)

PLAYER = "media_player.family_room_stereo"


@pytest.fixture(autouse=True)
def enable_custom_integrations(enable_custom_integrations):
    """Let Home Assistant load this integration from the repository."""
    return enable_custom_integrations


@pytest.fixture
def music_assistant(hass):
    """A loaded Music Assistant entry, which setup refuses to run without."""
    entry = MockConfigEntry(domain=MA_DOMAIN, title="Music Assistant", data={})
    entry.add_to_hass(hass)
    entry.mock_state(hass, ConfigEntryState.LOADED)
    yield entry
    # Home Assistant unloads every loaded entry when the test ends, and
    # unloading this stub would import the real Music Assistant
    # integration, which needs a client library that is not installed.
    entry.mock_state(hass, ConfigEntryState.NOT_LOADED)


@pytest.fixture
def player(hass, entity_registry, music_assistant):
    """A Music Assistant player in the registry, as the flow requires."""
    return entity_registry.async_get_or_create(
        "media_player",
        MA_DOMAIN,
        "family-room-unique-id",
        suggested_object_id="family_room_stereo",
        config_entry=music_assistant,
    )


@pytest.fixture
def entry(hass, music_assistant, player):
    """This integration's own entry, pointed at that player."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Family Room Stereo",
        unique_id=player.entity_id,
        data={
            CONF_PLAYER: player.entity_id,
            CONF_MA_CONFIG_ENTRY_ID: music_assistant.entry_id,
            CONF_LASTFM_API_KEY: "not-a-real-key",
        },
    )
    entry.add_to_hass(hass)
    return entry


# There was a verify_cleanup override here that skipped the framework's
# lingering task, timer and thread check. It was added when that check
# failed on Home Assistant's own import executor for every test in this
# directory. It no longer does, on the pinned version, so the override
# has been removed: shadowing it cost the one thing that would notice a
# task or timer this integration leaves behind on unload, which is
# exactly the class of bug these tests exist to find.
