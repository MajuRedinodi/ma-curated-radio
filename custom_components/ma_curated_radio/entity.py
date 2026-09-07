"""Shared base for this integration's control and status entities.

Every configured player gets one service device, and the entities on it are
the same settings the options flow exposes. Putting them on entities rather
than leaving them in the options dialog is what makes them reachable from a
dashboard, an automation or a voice command.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import Entity

from .const import DOMAIN, signal_update

if TYPE_CHECKING:
    from . import MaCuratedRadioConfigEntry, RuntimeData


class CuratedRadioEntity(Entity):
    """An entity backed by one config entry's live settings."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, entry: MaCuratedRadioConfigEntry, key: str) -> None:
        """Attach to the entry's service device."""
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="Music Assistant Curated Radio",
            model="Curated radio",
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def runtime(self) -> RuntimeData:
        """Live objects for this entry."""
        return self._entry.runtime_data

    async def async_added_to_hass(self) -> None:
        """Refresh whenever settings or batch state change."""
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                signal_update(self._entry.entry_id),
                self.async_write_ha_state,
            )
        )

    def _option(self, key: str, default: Any = None) -> Any:
        """Read an option, falling back to the original setup data."""
        return {**self._entry.data, **self._entry.options}.get(key, default)

    def _write_option(self, key: str, value: Any) -> None:
        """Persist one option.

        Updating the entry fires the update listener, which applies the new
        settings to the running objects in place. Deliberately not a reload:
        reloading would tear down the very entity handling the change.
        """
        self.hass.config_entries.async_update_entry(
            self._entry, options={**self._entry.options, key: value}
        )
