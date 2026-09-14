"""The options dialog, which used to reset what it does not show."""

import pytest

pytest.importorskip("pytest_homeassistant_custom_component")

from homeassistant.core import HomeAssistant  # noqa: E402

from custom_components.ma_curated_radio.const import (  # noqa: E402
    CONF_DEGREES,
    CONF_ENABLED,
    CONF_POPULARITY_FLOOR,
    CONF_STYLE_SETTINGS,
)


async def test_submitting_the_form_keeps_what_it_never_showed(
    hass: HomeAssistant, entry
) -> None:
    """Opening Configure and pressing Submit turned a switched-off station
    back on and undid every per-style number set from the dashboard."""
    hass.config_entries.async_update_entry(
        entry,
        options={
            CONF_ENABLED: False,
            CONF_POPULARITY_FLOOR: 25,
            CONF_STYLE_SETTINGS: {"balanced": {"max_artists": 8}},
        },
    )
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(entry.entry_id)
    # What the frontend submits: every field the form shows, with the
    # defaults it was given, and one of them changed.
    form = result["data_schema"]({CONF_DEGREES: 2})
    await hass.config_entries.options.async_configure(result["flow_id"], form)
    await hass.async_block_till_done()

    assert entry.options[CONF_ENABLED] is False
    assert entry.options[CONF_POPULARITY_FLOOR] == 25
    assert entry.options[CONF_STYLE_SETTINGS] == {"balanced": {"max_artists": 8}}
    assert entry.options[CONF_DEGREES] == 2
    # And as a whole number. The form hands back floats, "== 2" is happy
    # with 2.0, and a float reaching a range check reads as out of step.
    assert type(entry.options[CONF_DEGREES]) is int


async def test_a_saved_option_reaches_the_running_engine(
    hass: HomeAssistant, entry
) -> None:
    """Saving has to take effect now, not at the next restart.

    Nothing covered the path from Submit to the settings the next batch
    is built with, so the update listener could be dropped, or the new
    settings never handed to the running engine, and the only symptom
    would be a dialog that appears to save and changes nothing.
    """
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(entry.entry_id)
    form = result["data_schema"]({CONF_DEGREES: 2})
    await hass.config_entries.options.async_configure(result["flow_id"], form)
    await hass.async_block_till_done()

    assert entry.runtime_data.settings.degrees == 2
