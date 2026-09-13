"""The Music Assistant Curated Radio integration."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.const import Platform
from homeassistant.core import (
    CALLBACK_TYPE,
    Event,
    HomeAssistant,
    ServiceCall,
    SupportsResponse,
    callback,
)
from homeassistant.exceptions import ConfigEntryNotReady, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_track_entity_registry_updated_event
from homeassistant.helpers.storage import Store
from homeassistant.helpers.typing import ConfigType

from .const import (
    ATTR_ARTIST,
    ATTR_CONFIG_ENTRY_ID,
    ATTR_LENGTH,
    ATTR_LIMIT,
    ATTR_MODE,
    ATTR_NAME,
    ATTR_PROVIDER,
    ATTR_QUERY,
    ATTR_SEED_ARTIST,
    ATTR_TRACK,
    CONF_PLAYER,
    CONF_PLAYER_REGISTRY_ID,
    DEFAULT_PLAYLIST_LENGTH,
    DEFAULT_PLAYLIST_NAME,
    DEFAULT_SEARCH_RESULTS,
    DOMAIN,
    MODE_REPLACE,
    MODES,
    SERVICE_ALLOW_TRACK,
    SERVICE_BUILD_PLAYLIST,
    SERVICE_FORGET_FEEDBACK,
    SERVICE_RUN_BATCH,
    SERVICE_SEARCH,
    SERVICE_UNMUTE_ARTIST,
    STATION_STORAGE_VERSION,
    signal_update,
)
from .coordinator import CuratedRadioDetector
from .engine import CuratedRadioEngine
from .entry_data import resolve_player
from .feedback import STORAGE_VERSION as SKIP_STORAGE_VERSION
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
ALLOW_TRACK_SCHEMA = vol.Schema({**_ENTRY_FIELD, vol.Required(ATTR_TRACK): cv.string})
SEARCH_SCHEMA = vol.Schema(
    {
        **_ENTRY_FIELD,
        vol.Optional(ATTR_QUERY, default=""): cv.string,
        vol.Optional(ATTR_ARTIST, default=""): cv.string,
        vol.Optional(ATTR_LIMIT, default=DEFAULT_SEARCH_RESULTS): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=100)
        ),
    }
)
BUILD_PLAYLIST_SCHEMA = vol.Schema(
    {
        **_ENTRY_FIELD,
        vol.Optional(ATTR_NAME, default=DEFAULT_PLAYLIST_NAME): cv.string,
        vol.Optional(ATTR_SEED_ARTIST, default=""): cv.string,
        vol.Optional(ATTR_LENGTH, default=DEFAULT_PLAYLIST_LENGTH): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=500)
        ),
        vol.Optional(ATTR_PROVIDER, default=""): cv.string,
    }
)
FORGET_FEEDBACK_SCHEMA = vol.Schema(_ENTRY_FIELD)


@dataclass(slots=True)
class Picked:
    """Which remembered entry the release dropdowns are pointing at.

    Deliberately not persisted. It is a cursor into a list, not a
    setting, and the list it points into is rebuilt on every restart.
    """

    artist: str = ""
    track: str = ""


@dataclass(slots=True)
class RuntimeData:
    """Live objects for one configured player."""

    settings: Settings
    engine: CuratedRadioEngine
    detector: CuratedRadioDetector
    skips: SkipMemory
    # Which artist and track the release dropdowns are pointing at. Held
    # here rather than on the select entities so the buttons that act on
    # them do not have to reach across the entity registry to find out.
    picked: Picked = field(default_factory=Picked)

    def apply(self, settings: Settings) -> None:
        """Adopt changed settings in place.

        Deliberately not a reload. The settings are reachable as entities
        now, so a reload would tear down the entity handling the change
        while it is still handling it.
        """
        self.settings = settings
        self.engine.apply_settings(settings)
        self.detector.apply_settings(settings)
        self.skips.apply_settings(settings)


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
        SERVICE_SEARCH,
        _make_search(hass),
        schema=SEARCH_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_ALLOW_TRACK,
        _make_allow_track(hass),
        schema=ALLOW_TRACK_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_FORGET_FEEDBACK,
        _make_forget_feedback(hass),
        schema=FORGET_FEEDBACK_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_BUILD_PLAYLIST,
        _make_build_playlist(hass),
        schema=BUILD_PLAYLIST_SCHEMA,
    )
    return True


async def async_setup_entry(
    hass: HomeAssistant, entry: MaCuratedRadioConfigEntry
) -> bool:
    """Set up one player from a config entry."""
    _keep_player_current(hass, entry)
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
    await engine.async_load()
    detector = CuratedRadioDetector(hass, settings, engine, skips)
    entry.runtime_data = RuntimeData(
        settings=settings, engine=engine, detector=detector, skips=skips
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(detector.async_start())
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    entry.async_on_unload(_watch_for_rename(hass, entry))

    _LOGGER.debug("Watching %s for manual picks", settings.player)
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: MaCuratedRadioConfigEntry
) -> bool:
    """Unload a config entry, writing out anything still pending.

    Both stores batch their writes over ten seconds, and a delayed write
    outlives the objects that scheduled it. Flushing here keeps a skip
    recorded moments before a reload, and stops a write landing after a
    deleted entry's files have been removed and recreating them.
    """
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    runtime = getattr(entry, "runtime_data", None)
    if runtime is not None:
        await runtime.skips.async_flush()
        await runtime.engine.async_flush()
    return unloaded


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Forget what a removed player remembered.

    Both stores are keyed by entry id, so nothing else can ever read them
    again, and leaving them behind means a player deleted and re-added
    inherits nothing while the files stay in .storage for good.
    """
    stores = (
        (f"{DOMAIN}.{entry.entry_id}", SKIP_STORAGE_VERSION),
        (f"{DOMAIN}.{entry.entry_id}.station", STATION_STORAGE_VERSION),
    )
    for key, version in stores:
        await Store(hass, version, key).async_remove()


@callback
def _keep_player_current(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Point the entry at wherever the configured player is now.

    A player is configured by entity_id, and everything targets that: the
    state subscription, every Music Assistant action. Entity ids are not
    stable, though, and renaming the player in Home Assistant left this
    integration watching a name nothing would ever report again. No events,
    no batches, no error, nothing unavailable, no log line. The registry id
    survives a rename, so it is recorded on first setup and used to find
    the player's current name on every setup afterwards.
    """
    registry = er.async_get(hass)
    player = entry.data[CONF_PLAYER]
    known = registry.async_get
    current, stored = resolve_player(
        entry.data.get(CONF_PLAYER_REGISTRY_ID),
        player,
        by_id=lambda uuid: er.async_resolve_entity_id(registry, uuid),
        by_name=lambda name: entry.id if (entry := known(name)) else None,
    )
    if stored is None:
        # Nothing in the registry answers to that name. Setting up anyway
        # is how this used to fail silently, so say so.
        _LOGGER.warning(
            "No player called %s exists any more, so nothing will be "
            "queued for it. Remove this entry and add the player again.",
            player,
        )
    if current == player and stored == entry.data.get(CONF_PLAYER_REGISTRY_ID):
        return
    if current != player:
        _LOGGER.info("The configured player is now %s, was %s", current, player)
    hass.config_entries.async_update_entry(
        entry,
        data={**entry.data, CONF_PLAYER: current, CONF_PLAYER_REGISTRY_ID: stored},
        # The unique id is the player's name, so it has to follow the
        # rename too. Left behind, it names an entity that no longer
        # exists, and adding the renamed player would be allowed to make a
        # second entry driving the same speaker.
        unique_id=current,
    )


@callback
def _watch_for_rename(hass: HomeAssistant, entry: ConfigEntry) -> CALLBACK_TYPE:
    """Reload the entry when the configured player is renamed.

    Setup re-resolves the name, so a reload is the whole repair.
    """

    @callback
    def _renamed(event: Event[er.EventEntityRegistryUpdatedData]) -> None:
        data = event.data
        if data["action"] != "update":
            return
        was = data.get("changes", {}).get("entity_id")
        if was and was == entry.data.get(CONF_PLAYER):
            hass.config_entries.async_schedule_reload(entry.entry_id)

    return async_track_entity_registry_updated_event(
        hass, entry.data[CONF_PLAYER], _renamed
    )


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


def _make_search(hass: HomeAssistant):
    """Build the search action handler."""

    async def _search(call: ServiceCall) -> dict[str, Any]:
        """Find tracks, returning more of them than the action surface does."""
        entry = _resolve(hass, call.data.get(ATTR_CONFIG_ENTRY_ID))
        found = await entry.runtime_data.engine.async_search(
            call.data[ATTR_QUERY],
            call.data[ATTR_LIMIT],
            call.data[ATTR_ARTIST],
        )
        return {
            "tracks": [
                {
                    "uri": track.uri,
                    "name": track.name,
                    "version": track.version,
                    "album": track.album,
                    "artists": track.artists,
                    "duration": track.duration,
                }
                for track in found
            ]
        }

    return _search


def _make_allow_track(hass: HomeAssistant):
    """Build the allow_track action handler."""

    async def _allow_track(call: ServiceCall) -> None:
        """Let one held-off track be queued again."""
        entry = _resolve(hass, call.data.get(ATTR_CONFIG_ENTRY_ID))
        track = call.data[ATTR_TRACK]
        if not await entry.runtime_data.skips.async_allow_track(track):
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="not_suppressed",
                translation_placeholders={"track": track},
            )
        async_dispatcher_send(hass, signal_update(entry.entry_id))

    return _allow_track


def _make_forget_feedback(hass: HomeAssistant):
    """Build the forget_feedback action handler."""

    async def _forget_feedback(call: ServiceCall) -> None:
        """Wipe every remembered skip and mute."""
        entry = _resolve(hass, call.data.get(ATTR_CONFIG_ENTRY_ID))
        await entry.runtime_data.skips.async_clear()
        async_dispatcher_send(hass, signal_update(entry.entry_id))

    return _forget_feedback


def _make_build_playlist(hass: HomeAssistant):
    """Build the build_playlist action handler."""

    async def _build_playlist(call: ServiceCall) -> None:
        """Fill a provider playlist without touching playback."""
        entry = _resolve(hass, call.data.get(ATTR_CONFIG_ENTRY_ID))
        result = await entry.runtime_data.engine.async_build_playlist(
            name=call.data[ATTR_NAME],
            seed_artist=call.data[ATTR_SEED_ARTIST],
            length=call.data[ATTR_LENGTH],
            provider=call.data[ATTR_PROVIDER],
        )
        if result.error == "playlists_unsupported":
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="playlists_unsupported"
            )
        if result.error:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="playlist_empty",
                translation_placeholders={"name": result.name},
            )

    return _build_playlist
