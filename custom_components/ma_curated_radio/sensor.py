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
        muted = self.runtime.skips.muted_display
        return {
            "artists": sorted(muted),
            "muted_until": muted,
            "suppressed_tracks": self.runtime.skips.suppressed_count,
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
            "artists": result.artists,
            "tracks_queued": result.queued,
            "skipped_reason": result.skipped_reason or None,
        }


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
