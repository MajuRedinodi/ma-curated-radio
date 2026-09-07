"""The Music Assistant Curated Radio integration."""

from __future__ import annotations

import logging
from dataclasses import dataclass

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryNotReady, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import ConfigType

from .const import (
    ATTR_CONFIG_ENTRY_ID,
    ATTR_MODE,
    DOMAIN,
    MODE_REPLACE,
    MODES,
    SERVICE_RUN_BATCH,
)
from .coordinator import CuratedRadioDetector
from .engine import CuratedRadioEngine
from .settings import Settings

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

RUN_BATCH_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_CONFIG_ENTRY_ID): cv.string,
        vol.Optional(ATTR_MODE, default=MODE_REPLACE): vol.In(MODES),
    }
)


@dataclass(slots=True)
class RuntimeData:
    """Live objects for one configured player."""

    settings: Settings
    engine: CuratedRadioEngine
    detector: CuratedRadioDetector


type MaCuratedRadioConfigEntry = ConfigEntry[RuntimeData]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the integration-wide service."""
    hass.services.async_register(
        DOMAIN, SERVICE_RUN_BATCH, _make_run_batch(hass), schema=RUN_BATCH_SCHEMA
    )
    return True


async def async_setup_entry(
    hass: HomeAssistant, entry: MaCuratedRadioConfigEntry
) -> bool:
    """Set up one player from a config entry."""
    settings = Settings.from_entry(entry)

    ma_entry = hass.config_entries.async_get_entry(settings.ma_config_entry_id)
    if ma_entry is None or ma_entry.state is not ConfigEntryState.LOADED:
        raise ConfigEntryNotReady("Music Assistant is not loaded yet")

    engine = CuratedRadioEngine(hass, settings, async_get_clientsession(hass))
    detector = CuratedRadioDetector(hass, settings, engine)
    entry.async_on_unload(detector.async_start())
    entry.runtime_data = RuntimeData(
        settings=settings, engine=engine, detector=detector
    )

    _LOGGER.debug("Watching %s for manual picks", settings.player)
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: MaCuratedRadioConfigEntry
) -> bool:
    """Unload a config entry. Listener teardown is registered on the entry."""
    return True


def _make_run_batch(hass: HomeAssistant):
    """Build the run_batch service handler."""

    async def _run_batch(call: ServiceCall) -> None:
        """Build one batch on demand, for a dashboard button or voice."""
        entry_id = call.data.get(ATTR_CONFIG_ENTRY_ID)
        loaded = [
            entry
            for entry in hass.config_entries.async_entries(DOMAIN)
            if entry.state is ConfigEntryState.LOADED
        ]
        if entry_id:
            entry = hass.config_entries.async_get_entry(entry_id)
            if entry is None or entry.domain != DOMAIN or entry not in loaded:
                raise ServiceValidationError(
                    translation_domain=DOMAIN,
                    translation_key="unknown_entry",
                    translation_placeholders={"entry_id": entry_id},
                )
        elif len(loaded) == 1:
            entry = loaded[0]
        else:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="entry_required",
            )

        await entry.runtime_data.engine.async_run(call.data[ATTR_MODE])

    return _run_batch
