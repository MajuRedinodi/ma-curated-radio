"""Adding a player.

The setup flow is the one screen every user sees exactly once, and a
wrong answer here sends them off to fix the wrong thing.
"""

import pytest

pytest.importorskip("pytest_homeassistant_custom_component")

import aiohttp  # noqa: E402
from homeassistant.data_entry_flow import FlowResultType  # noqa: E402

from custom_components.ma_curated_radio.const import (  # noqa: E402
    CONF_LASTFM_API_KEY,
    CONF_PLAYER,
    DOMAIN,
)

LASTFM = "https://ws.audioscrobbler.com/2.0/"


async def _submit(hass, player):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    return await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_PLAYER: player.entity_id, CONF_LASTFM_API_KEY: "a-key"},
    )


async def test_a_key_last_fm_accepts_creates_the_entry(
    hass, player, aioclient_mock
):
    aioclient_mock.get(LASTFM, json={"artist": {"name": "Cher"}})

    result = await _submit(hass, player)

    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_a_key_last_fm_rejects_is_reported_against_the_key(
    hass, player, aioclient_mock
):
    aioclient_mock.get(LASTFM, json={"error": 10, "message": "Invalid API key"})

    result = await _submit(hass, player)

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_LASTFM_API_KEY: "invalid_api_key"}


async def test_last_fm_being_unreachable_is_not_reported_as_a_bad_key(
    hass, player, aioclient_mock
):
    """Every transport failure used to arrive as an empty result, which
    the flow read as a rejected key. Being told the key is wrong when the
    key is fine sends people off to generate another one that fails in
    exactly the same way."""
    aioclient_mock.get(LASTFM, exc=aiohttp.ClientConnectionError())

    result = await _submit(hass, player)

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_last_fm_having_a_bad_day_is_not_reported_as_a_bad_key(
    hass, player, aioclient_mock
):
    """An API-level error that is not about the key is Last.fm's problem."""
    aioclient_mock.get(LASTFM, json={"error": 8, "message": "Operation failed"})

    result = await _submit(hass, player)

    assert result["type"] is FlowResultType.CREATE_ENTRY
