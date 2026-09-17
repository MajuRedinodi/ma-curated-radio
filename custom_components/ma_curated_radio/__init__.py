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
from homeassistant.exceptions import (
    ConfigEntryError,
    ConfigEntryNotReady,
    ServiceValidationError,
)
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
    CONF_MA_CONFIG_ENTRY_ID,
    CONF_PLAYER,
    CONF_PLAYER_REGISTRY_ID,
    CONF_SEED_LEAN,
    DEFAULT_PLAYLIST_LENGTH,
    DEFAULT_PLAYLIST_NAME,
    DEFAULT_SEARCH_RESULTS,
    DOMAIN,
    FACTS_SAVE_DELAY,
    FACTS_STORAGE_KEY,
    FACTS_STORAGE_VERSION,
    LEGACY_SEED_LEANS,
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
from .facts import FactBook
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
    """Set up one player from a config entry.

    Music Assistant is checked before the player is resolved, because
    only one of these two is worth retrying and the retryable one has to
    get its answer in first.
    """
    _retire_legacy_style(hass, entry)

    ma_entry = hass.config_entries.async_get_entry(
        entry.data.get(CONF_MA_CONFIG_ENTRY_ID, "")
    )
    if ma_entry is None:
        # Not the same thing as "not loaded yet", and retrying will never
        # fix it. Music Assistant was removed and re-added, which gives it
        # a new entry id, and this one points at an entry that no longer
        # exists. Retried as NotReady it sat there saying it was waiting
        # for Music Assistant to load, forever, while Music Assistant was
        # loaded the whole time.
        raise ConfigEntryError(
            "The Music Assistant entry this player was set up against no "
            "longer exists. Remove this player and add it again."
        )
    if ma_entry.state is not ConfigEntryState.LOADED:
        raise ConfigEntryNotReady("Music Assistant is not loaded yet")

    _keep_player_current(hass, entry)
    settings = Settings.from_entry(entry)

    skips = SkipMemory(
        hass,
        entry.entry_id,
        track_days=settings.track_suppress_days,
        artist_days=settings.artist_mute_days,
        strike_limit=settings.artist_strike_limit,
    )
    await skips.async_load()

    engine = CuratedRadioEngine(
        hass,
        settings,
        async_get_clientsession(hass),
        skips,
        entry.entry_id,
        await _async_facts(hass),
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

    Every store batches its writes, and a delayed write outlives the
    objects that scheduled it. Flushing here keeps a skip recorded moments
    before a reload, and stops a write landing after a deleted entry's
    files have been removed and recreating them.
    """
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    runtime = getattr(entry, "runtime_data", None)
    if runtime is not None:
        await runtime.skips.async_flush()
        await runtime.engine.async_flush()
    await _async_flush_facts(hass)
    return unloaded


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Forget what a removed player remembered.

    Both stores listed here are keyed by entry id, so nothing else can
    ever read them again, and leaving them behind means a player deleted
    and re-added inherits nothing while the files stay in .storage for
    good.

    What is known about records is deliberately not in that list. It is
    one file for every player, so deleting a player must not take it: the
    release year of a record is not something the living room owns, and
    removing one of two players would otherwise throw away everything
    both of them had learned.
    """
    stores = (
        (f"{DOMAIN}.{entry.entry_id}", SKIP_STORAGE_VERSION),
        (f"{DOMAIN}.{entry.entry_id}.station", STATION_STORAGE_VERSION),
    )
    for key, version in stores:
        await Store(hass, version, key).async_remove()


class _FactsStore(Store[dict[str, Any]]):
    """The store for what is known about records, and its migration."""

    async def _async_migrate_func(
        self,
        old_major_version: int,
        old_minor_version: int,
        old_data: dict[str, Any],
    ) -> dict[str, Any]:
        """Bring an older file up to the current schema.

        Adding a field never comes through here, because every read
        defaults and a record written before a field existed reads as not
        knowing it. This is for the other kind of change, where what a
        field means has moved under it.

        Version 1 stored a release year without checking that the article
        it came from was about the recording we asked for. A cover shares
        its title with the original, whose article wins the search, so
        Wheatus' "A Little Respect" was filed as 1988 off Erasure's page
        and Counting Crows' "Big Yellow Taxi" as 1970 off Joni
        Mitchell's. Those look exactly like good years, a hit never
        expires so they cannot age out, and there is no way after the
        fact to tell which of a few hundred records they are.

        So the file goes. A cache is rebuildable: losing it costs lookups
        and not correctness, and refilling it is what the per-batch
        lookup budget is for.
        """
        _LOGGER.info(
            "Forgetting what was known about records: schema %s predates the "
            "check that a year belongs to the recording rather than to the "
            "song somebody else made first",
            old_major_version,
        )
        return {"records": {}}


async def _async_facts(hass: HomeAssistant) -> FactBook:
    """What is known about records, loaded once however many players exist.

    Held in hass.data rather than on a config entry, because it outlives
    any one of them. The second player to set up gets the book the first
    one loaded, so a year learned in the living room is already known on
    the phone.

    Writes are scheduled rather than immediate. Store rewrites the whole
    file on every save and one batch learns about twenty records in a
    burst, so the delay is what turns those into a single write.
    """
    domain_data = hass.data.setdefault(DOMAIN, {})
    if (known := domain_data.get("facts")) is not None:
        return known
    store: Store[dict[str, Any]] = _FactsStore(
        hass, FACTS_STORAGE_VERSION, FACTS_STORAGE_KEY
    )
    try:
        data = await store.async_load()
    except Exception as err:  # noqa: BLE001 - a bad cache must not block setup
        # Losing it costs lookups, not correctness, so setup carries on
        # with an empty book and fills it again.
        _LOGGER.warning("Could not read what is known about records: %s", err)
        data = None
    known = FactBook.from_dict(data)
    known.bind(lambda: store.async_delay_save(known.as_dict, FACTS_SAVE_DELAY))
    domain_data["facts"] = known
    domain_data["facts_store"] = store
    _LOGGER.debug("Know something about %s records", len(known))
    return known


async def _async_flush_facts(hass: HomeAssistant) -> None:
    """Write out what was learned, rather than in thirty seconds.

    A delayed write outlives whatever scheduled it, so a player unloading
    seconds after a batch would otherwise drop what that batch learned.
    """
    domain_data = hass.data.get(DOMAIN) or {}
    store = domain_data.get("facts_store")
    known = domain_data.get("facts")
    if store is not None and known is not None:
        await store.async_save(known.as_dict())


@callback
def _retire_legacy_style(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Rewrite an old station style to its current name, once.

    Settings normalises the old name on the way past, so the engine has
    always run the right style. Nothing else did: the dropdown fell back
    to Balanced, the per-style numbers under it showed one style's values
    while another was in force, and the options dialog seeded its own
    selector with a value that selector rejects, so opening Configure and
    pressing Submit failed on a form the user had not touched.

    One normalisation is better than four, so the stored value is brought
    up to date here and everything downstream reads something current.
    """
    style = entry.options.get(CONF_SEED_LEAN)
    if style not in LEGACY_SEED_LEANS:
        return
    current = LEGACY_SEED_LEANS[style]
    _LOGGER.info("Station style %s is now called %s", style, current)
    hass.config_entries.async_update_entry(
        entry, options={**entry.options, CONF_SEED_LEAN: current}
    )


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
        # Nothing in the registry answers to that name. A warning in the
        # log was not enough: the entry still went green, brought up all
        # its entities, showed its switch on, and would never queue
        # anything. Failing is the only version of this a person sees.
        raise ConfigEntryError(
            f"No player called {player} exists any more. Remove this "
            "entry and add the player again."
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
        # Same three cases the button distinguishes. Folding the first
        # into the catch-all told somebody whose build was already
        # running to check that something was playing, which is both
        # wrong and unactionable.
        if result.error == "already_running":
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="playlist_running"
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
