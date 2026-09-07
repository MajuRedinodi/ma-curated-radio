"""Station style, as a dropdown you can put on a dashboard."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.select import SelectEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import CONF_SEED_LEAN, DEFAULT_SEED_LEAN, SEED_LEANS
from .entity import CuratedRadioEntity

if TYPE_CHECKING:
    from . import MaCuratedRadioConfigEntry


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MaCuratedRadioConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the station-style select."""
    async_add_entities([StationStyleSelect(entry)])


class StationStyleSelect(CuratedRadioEntity, SelectEntity):
    """How much of a batch belongs to the artist you picked."""

    _attr_translation_key = "seed_lean"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:tune-variant"
    _attr_options = SEED_LEANS

    def __init__(self, entry: MaCuratedRadioConfigEntry) -> None:
        """Bind to the seed-lean option."""
        super().__init__(entry, "seed_lean")

    @property
    def current_option(self) -> str:
        """Configured station style."""
        value = str(self._option(CONF_SEED_LEAN, DEFAULT_SEED_LEAN))
        return value if value in SEED_LEANS else DEFAULT_SEED_LEAN

    async def async_select_option(self, option: str) -> None:
        """Change the station style."""
        self._write_option(CONF_SEED_LEAN, option)
