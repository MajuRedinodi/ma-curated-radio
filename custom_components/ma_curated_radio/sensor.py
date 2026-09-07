"""Status readouts: what the last batch did, and who is muted."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .entity import CuratedRadioEntity

if TYPE_CHECKING:
    from . import MaCuratedRadioConfigEntry


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MaCuratedRadioConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the status sensors."""
    async_add_entities([MutedArtistsSensor(entry), LastBatchSensor(entry)])


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
