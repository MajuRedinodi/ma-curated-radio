"""The Music Assistant Curated Radio integration."""

from __future__ import annotations

import logging
from dataclasses import dataclass

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import ConfigEntryNotReady, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.typing import ConfigType

from .const import (
    ATTR_ARTIST,
    ATTR_CONFIG_ENTRY_ID,
    ATTR_MODE,
    DOMAIN,
    MODE_REPLACE,
    MODES,
    SERVICE_FORGET_FEEDBACK,
    SERVICE_RUN_BATCH,
    SERVICE_UNMUTE_ARTIST,
    signal_update,
)
from .coordinator import CuratedRadioDetector
from .engine import CuratedRadioEngine
from .feedback import SkipMemory
from .settings import Settings

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

PLATFORMS: list[Platform] = [
    Platform.BUTTON,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
]

_ENTRY_FIELD = {vol.Optional(ATTR_CONFIG_ENTRY_ID): cv.string}

RUN_BATCH_SCHEMA = vol.Schema(
    {**_ENTRY_FIELD, vol.Optional(ATTR_MODE, default=MODE_REPLACE): vol.In(MODES)}
)
UNMUTE_ARTIST_SCHEMA = vol.Schema({**_ENTRY_FIELD, vol.Required(ATTR_ARTIST): cv.string})
FORGET_FEEDBACK_SCHEMA = vol.Schema(_ENTRY_FIELD)


@dataclass(slots=True)
class RuntimeData:
    """Live objects for one configured player."""

    settings: Settings
    engine: CuratedRadioEngine
    detector: CuratedRadioDetector
    skips: SkipMemory

    def apply(self, settings: Settings) -> None:
        """Adopt changed settings in place.

        Deliberately not a reload. The settings are reachable as entities
        now, so a reload would tear down the entity handling the change
        while it is still handling it.
        """
        self.settings = settings
        self.engine.apply_settings(settings)
        self.detector.apply_settings(settings)


type MaCuratedRadioConfigEntry = ConfigEntry[RuntimeData]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the integration-wide actions."""
    hass.services.async_register(
        DOMAIN, SERVICE_RUN_BATCH, _make_run_batch(hass), schema=RUN_BATCH_SCHEMA
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_UNMUTE_ARTIST,
        _make_unmute_artist(hass),
        schema=UNMUTE_ARTIST_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_FORGET_FEEDBACK,
        _make_forget_feedback(hass),
        schema=FORGET_FEEDBACK_SCHEMA,
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

    skips = SkipMemory(
        hass,
        entry.entry_id,
        track_days=settings.track_suppress_days,
        artist_days=settings.artist_mute_days,
        strike_limit=settings.artist_strike_limit,
    )
    await skips.async_load()

    engine = CuratedRadioEngine(
        hass, settings, async_get_clientsession(hass), skips, entry.entry_id
    )
    detector = CuratedRadioDetector(hass, settings, engine, skips)
    entry.runtime_data = RuntimeData(
        settings=settings, engine=engine, detector=detector, skips=skips
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(detector.async_start())
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))

    _LOGGER.debug("Watching %s for manual picks", settings.player)
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: MaCuratedRadioConfigEntry
) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_options_updated(
    hass: HomeAssistant, entry: MaCuratedRadioConfigEntry
) -> None:
    """Push changed options into the running objects."""
    entry.runtime_data.apply(Settings.from_entry(entry))
    async_dispatcher_send(hass, signal_update(entry.entry_id))


@callback
def _resolve(hass: HomeAssistant, entry_id: str | None) -> MaCuratedRadioConfigEntry:
    """Find the entry an action should act on."""
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
        return entry
    if len(loaded) == 1:
        return loaded[0]
    raise ServiceValidationError(
        translation_domain=DOMAIN, translation_key="entry_required"
    )


def _make_run_batch(hass: HomeAssistant):
    """Build the run_batch action handler."""

    async def _run_batch(call: ServiceCall) -> None:
        """Build one batch on demand, for a dashboard button or voice."""
        entry = _resolve(hass, call.data.get(ATTR_CONFIG_ENTRY_ID))
        await entry.runtime_data.engine.async_run(call.data[ATTR_MODE])

    return _run_batch


def _make_unmute_artist(hass: HomeAssistant):
    """Build the unmute_artist action handler."""

    async def _unmute_artist(call: ServiceCall) -> None:
        """Give one muted artist another chance."""
        entry = _resolve(hass, call.data.get(ATTR_CONFIG_ENTRY_ID))
        artist = call.data[ATTR_ARTIST]
        if not await entry.runtime_data.skips.async_unmute(artist):
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="not_muted",
                translation_placeholders={"artist": artist},
            )
        async_dispatcher_send(hass, signal_update(entry.entry_id))

    return _unmute_artist


def _make_forget_feedback(hass: HomeAssistant):
    """Build the forget_feedback action handler."""

    async def _forget_feedback(call: ServiceCall) -> None:
        """Wipe every remembered skip and mute."""
        entry = _resolve(hass, call.data.get(ATTR_CONFIG_ENTRY_ID))
        await entry.runtime_data.skips.async_clear()
        async_dispatcher_send(hass, signal_update(entry.entry_id))

    return _forget_feedback
