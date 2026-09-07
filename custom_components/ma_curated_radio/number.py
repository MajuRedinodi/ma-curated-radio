"""The batch-shape settings, as numbers a dashboard can adjust."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from homeassistant.components.number import (
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import (
    CONF_ARTIST_STRIKE_LIMIT,
    CONF_MAX_ARTISTS,
    CONF_MAX_CONSECUTIVE,
    CONF_REFILL_THRESHOLD,
    CONF_TRACKS_PER_ARTIST,
    DEFAULT_ARTIST_STRIKE_LIMIT,
    DEFAULT_MAX_ARTISTS,
    DEFAULT_MAX_CONSECUTIVE,
    DEFAULT_REFILL_THRESHOLD,
    DEFAULT_TRACKS_PER_ARTIST,
)
from .entity import CuratedRadioEntity

if TYPE_CHECKING:
    from . import MaCuratedRadioConfigEntry


@dataclass(frozen=True, kw_only=True)
class CuratedRadioNumberDescription(NumberEntityDescription):
    """A number backed by one integer option."""

    option_key: str
    default: int


NUMBERS: tuple[CuratedRadioNumberDescription, ...] = (
    CuratedRadioNumberDescription(
        key="max_artists",
        translation_key="max_artists",
        native_min_value=0,
        native_max_value=15,
        native_step=1,
        mode=NumberMode.BOX,
        option_key=CONF_MAX_ARTISTS,
        default=DEFAULT_MAX_ARTISTS,
    ),
    CuratedRadioNumberDescription(
        key="tracks_per_artist",
        translation_key="tracks_per_artist",
        native_min_value=1,
        native_max_value=10,
        native_step=1,
        mode=NumberMode.BOX,
        option_key=CONF_TRACKS_PER_ARTIST,
        default=DEFAULT_TRACKS_PER_ARTIST,
    ),
    CuratedRadioNumberDescription(
        key="max_consecutive",
        translation_key="max_consecutive",
        native_min_value=1,
        native_max_value=5,
        native_step=1,
        mode=NumberMode.BOX,
        option_key=CONF_MAX_CONSECUTIVE,
        default=DEFAULT_MAX_CONSECUTIVE,
    ),
    CuratedRadioNumberDescription(
        key="refill_threshold",
        translation_key="refill_threshold",
        native_min_value=0,
        native_max_value=10,
        native_step=1,
        mode=NumberMode.BOX,
        option_key=CONF_REFILL_THRESHOLD,
        default=DEFAULT_REFILL_THRESHOLD,
    ),
    CuratedRadioNumberDescription(
        key="artist_strike_limit",
        translation_key="artist_strike_limit",
        native_min_value=0,
        native_max_value=10,
        native_step=1,
        mode=NumberMode.BOX,
        option_key=CONF_ARTIST_STRIKE_LIMIT,
        default=DEFAULT_ARTIST_STRIKE_LIMIT,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MaCuratedRadioConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the number entities."""
    async_add_entities(
        CuratedRadioNumber(entry, description) for description in NUMBERS
    )


class CuratedRadioNumber(CuratedRadioEntity, NumberEntity):
    """An integer option, exposed so a dashboard can reach it."""

    entity_description: CuratedRadioNumberDescription
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self,
        entry: MaCuratedRadioConfigEntry,
        description: CuratedRadioNumberDescription,
    ) -> None:
        """Bind the number to its option."""
        super().__init__(entry, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> float:
        """Current value of the option."""
        return float(
            self._option(
                self.entity_description.option_key, self.entity_description.default
            )
        )

    async def async_set_native_value(self, value: float) -> None:
        """Store the new value as a whole number."""
        self._write_option(self.entity_description.option_key, int(value))
