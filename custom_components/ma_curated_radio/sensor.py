"""Status readouts: what the last batch did, and who is muted."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.loader import async_get_integration
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .entity import CuratedRadioEntity

if TYPE_CHECKING:
    from . import MaCuratedRadioConfigEntry


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MaCuratedRadioConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the status sensors."""
    integration = await async_get_integration(hass, DOMAIN)
    async_add_entities(
        [
            MutedArtistsSensor(entry),
            LastBatchSensor(entry),
            LastBatchBuiltSensor(entry),
            LastManualPickSensor(entry),
            VersionSensor(entry, str(integration.version)),
        ]
    )


class MutedArtistsSensor(CuratedRadioEntity, SensorEntity):
    """How many artists are currently muted, and who they are.

    A mute that lasts a month and cannot be inspected is a trap, so the
    names and their expiry are on the attributes where a dashboard can list
    them and the unmute action can be pointed at them.
    """

    _attr_translation_key = "muted_artists"
    _attr_icon = "mdi:account-cancel"
    _attr_native_unit_of_measurement = "artists"

    def __init__(self, entry: MaCuratedRadioConfigEntry) -> None:
        """Bind to the skip memory."""
        super().__init__(entry, "muted_artists")

    @property
    def native_value(self) -> int:
        """Number of muted artists."""
        return len(self.runtime.skips.muted_artists)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Muted artist names, when each mute lifts, and skip totals."""
        skips = self.runtime.skips
        muted = skips.muted_display
        suppressed = skips.suppressed_display
        return {
            "artists": sorted(muted),
            "muted_until": muted,
            "suppressed_tracks": skips.suppressed_count,
            # The titles as well as the count, so the list is inspectable
            # from a dashboard rather than being a number you cannot act on.
            "tracks": list(suppressed),
            "tracks_until": suppressed,
        }


class LastBatchSensor(CuratedRadioEntity, SensorEntity):
    """The artist the last batch was built from."""

    _attr_translation_key = "last_batch"
    _attr_icon = "mdi:playlist-music"

    def __init__(self, entry: MaCuratedRadioConfigEntry) -> None:
        """Bind to the engine's last result."""
        super().__init__(entry, "last_batch")

    @property
    def native_value(self) -> str | None:
        """Seed artist of the most recent batch."""
        result = self.runtime.engine.last_batch
        if result is None or not result.seed_artist:
            return None
        return result.seed_artist

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Mode, artists and track count of the most recent batch."""
        result = self.runtime.engine.last_batch
        if result is None:
            return {}
        return {
            "mode": result.mode,
            # The state is the batch's lead, which on a refill is simply
            # whoever was playing. This is where its artists came from.
            "neighbours_from": result.pool_from or None,
            "artists": result.artists,
            "tracks_queued": result.queued,
            "skipped_reason": result.skipped_reason or None,
            # How well known the batch is likely to be. Absolute, so it
            # compares across stations, which the tier counts do not.
            "reach_median": result.reach_median,
            "reach_low": result.reach_low,
            "tiers": result.tiers,
            # The real time the batch was built. The sensor's own
            # timestamps restart with Home Assistant; this does not.
            "built_at": result.built_at or None,
        }


class LastBatchBuiltSensor(CuratedRadioEntity, SensorEntity):
    """When the last batch was actually built.

    A dashboard showing the Last batch seed's own timestamp reported the
    last restart instead: Home Assistant resets every entity's last-updated
    time when it starts, so a batch built at 9:36 read as 10:03 after an
    update was installed. This comes from the batch itself, which is kept
    on disk, so it survives a restart.
    """

    _attr_translation_key = "last_batch_built"
    _attr_icon = "mdi:playlist-clock"
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, entry: MaCuratedRadioConfigEntry) -> None:
        """Bind to the engine's last result."""
        super().__init__(entry, "last_batch_built")

    @property
    def native_value(self) -> datetime | None:
        """Build time of the most recent batch that queued anything."""
        result = self.runtime.engine.last_batch
        if result is None or not result.built_at:
            return None
        return dt_util.parse_datetime(result.built_at)


class LastManualPickSensor(CuratedRadioEntity, RestoreEntity, SensorEntity):
    """When somebody last jumped playback by hand.

    Home Assistant marks a state change as user-driven only when it came
    from inside Home Assistant, so a song chosen in the Music Assistant or
    provider app is indistinguishable from an automation as far as
    ``context.user_id`` is concerned. This detection does not rely on that,
    which makes it a better "is a person actually listening" signal than
    anything Home Assistant can work out on its own. Useful for automations
    that should stand down while someone is clearly in the room.
    """

    _attr_translation_key = "last_manual_pick"
    _attr_icon = "mdi:gesture-tap"
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, entry: MaCuratedRadioConfigEntry) -> None:
        """Bind to the detector."""
        super().__init__(entry, "last_manual_pick")

    async def async_added_to_hass(self) -> None:
        """Carry the timestamp across restarts.

        A restart is not evidence that nobody is listening, so the value
        is restored rather than starting empty.
        """
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last is None or last.state in (STATE_UNKNOWN, STATE_UNAVAILABLE):
            return
        if (restored := dt_util.parse_datetime(last.state)) is not None:
            self.runtime.detector.restore_last_manual_pick(restored)

    @property
    def native_value(self) -> datetime | None:
        """Timestamp of the last detected manual pick."""
        return self.runtime.detector.last_manual_pick


class VersionSensor(CuratedRadioEntity, SensorEntity):
    """Which version of this integration is actually running.

    Python caches modules, so an update that has been downloaded is not
    the update that is running until Home Assistant restarts. Reading the
    version off a dashboard answers "did the restart take" without
    digging through the log for a behaviour that only shows up on the
    next pick.
    """

    _attr_translation_key = "version"
    _attr_icon = "mdi:tag-outline"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, entry: MaCuratedRadioConfigEntry, version: str) -> None:
        """Hold the version read from the loaded manifest."""
        super().__init__(entry, "version")
        self._version = version

    @property
    def native_value(self) -> str:
        """Version of the code currently loaded."""
        return self._version
