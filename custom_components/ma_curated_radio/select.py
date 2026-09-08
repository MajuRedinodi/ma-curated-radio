"""Station style and familiarity, as dropdowns you can put on a dashboard."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.select import SelectEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import (
    CONF_EXPLICIT,
    CONF_FAMILIARITY,
    CONF_SEED_LEAN,
    DEFAULT_EXPLICIT,
    DEFAULT_FAMILIARITY,
    DEFAULT_SEED_LEAN,
    EXPLICIT_MODES,
    FAMILIARITIES,
    SEED_LEANS,
)
from .entity import CuratedRadioEntity

if TYPE_CHECKING:
    from . import MaCuratedRadioConfigEntry


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MaCuratedRadioConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the selects."""
    async_add_entities(
        [StationStyleSelect(entry), FamiliaritySelect(entry), ExplicitSelect(entry)]
    )


class ExplicitSelect(CuratedRadioEntity, SelectEntity):
    """Whether to allow, avoid or prefer explicit versions.

    Worth having on a dashboard rather than buried in options: which one
    you want depends on who is in the room, and that changes.
    """

    _attr_translation_key = "explicit"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:account-child-outline"
    _attr_options = EXPLICIT_MODES

    def __init__(self, entry: MaCuratedRadioConfigEntry) -> None:
        """Bind to the explicit-content option."""
        super().__init__(entry, "explicit")

    @property
    def current_option(self) -> str:
        """Configured explicit-content handling."""
        value = str(self._option(CONF_EXPLICIT, DEFAULT_EXPLICIT))
        return value if value in EXPLICIT_MODES else DEFAULT_EXPLICIT

    async def async_select_option(self, option: str) -> None:
        """Change how explicit versions are treated."""
        self._write_option(CONF_EXPLICIT, option)


class FamiliaritySelect(CuratedRadioEntity, SelectEntity):
    """How strongly artist choice leans toward the well known."""

    _attr_translation_key = "familiarity"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:account-star"
    _attr_options = FAMILIARITIES

    def __init__(self, entry: MaCuratedRadioConfigEntry) -> None:
        """Bind to the familiarity option."""
        super().__init__(entry, "familiarity")

    @property
    def current_option(self) -> str:
        """Configured familiarity."""
        value = str(self._option(CONF_FAMILIARITY, DEFAULT_FAMILIARITY))
        return value if value in FAMILIARITIES else DEFAULT_FAMILIARITY

    async def async_select_option(self, option: str) -> None:
        """Change how adventurous artist choice is."""
        self._write_option(CONF_FAMILIARITY, option)


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
