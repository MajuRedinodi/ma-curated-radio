"""One-shot actions: build a batch now, or lift every artist mute."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.button import ButtonEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import MODE_REPLACE, signal_update
from .entity import CuratedRadioEntity

if TYPE_CHECKING:
    from . import MaCuratedRadioConfigEntry


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MaCuratedRadioConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the buttons."""
    async_add_entities([BuildBatchButton(entry), UnmuteAllButton(entry)])


class BuildBatchButton(CuratedRadioEntity, ButtonEntity):
    """Build a batch now, seeded from whatever is playing."""

    _attr_translation_key = "build_batch"
    _attr_icon = "mdi:playlist-plus"

    def __init__(self, entry: MaCuratedRadioConfigEntry) -> None:
        """Bind to the engine."""
        super().__init__(entry, "build_batch")

    async def async_press(self) -> None:
        """Replace the queue tail with a fresh batch."""
        await self.runtime.engine.async_run(MODE_REPLACE)


class UnmuteAllButton(CuratedRadioEntity, ButtonEntity):
    """Give every muted artist another chance."""

    _attr_translation_key = "unmute_all"
    _attr_icon = "mdi:account-check"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, entry: MaCuratedRadioConfigEntry) -> None:
        """Bind to the skip memory."""
        super().__init__(entry, "unmute_all")

    async def async_press(self) -> None:
        """Lift every artist mute."""
        await self.runtime.skips.async_unmute_all()
        async_dispatcher_send(self.hass, signal_update(self._entry.entry_id))
