"""The master on/off switch, plus the two content filters."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import (
    CONF_ENABLED,
    CONF_FILTER_HOLIDAY,
    CONF_FILTER_LIVE,
    CONF_FILTER_REMIX,
    DEFAULT_ENABLED,
    DEFAULT_FILTER_HOLIDAY,
    DEFAULT_FILTER_LIVE,
    DEFAULT_FILTER_REMIX,
)
from .entity import CuratedRadioEntity

if TYPE_CHECKING:
    from . import MaCuratedRadioConfigEntry


@dataclass(frozen=True, kw_only=True)
class CuratedRadioSwitchDescription(SwitchEntityDescription):
    """A switch backed by one boolean option."""

    option_key: str
    default: bool


SWITCHES: tuple[CuratedRadioSwitchDescription, ...] = (
    CuratedRadioSwitchDescription(
        key="enabled",
        translation_key="enabled",
        icon="mdi:radio",
        option_key=CONF_ENABLED,
        default=DEFAULT_ENABLED,
    ),
    CuratedRadioSwitchDescription(
        key="filter_live",
        translation_key="filter_live",
        entity_category=EntityCategory.CONFIG,
        option_key=CONF_FILTER_LIVE,
        default=DEFAULT_FILTER_LIVE,
    ),
    CuratedRadioSwitchDescription(
        key="filter_remix",
        translation_key="filter_remix",
        entity_category=EntityCategory.CONFIG,
        option_key=CONF_FILTER_REMIX,
        default=DEFAULT_FILTER_REMIX,
    ),
    CuratedRadioSwitchDescription(
        key="filter_holiday",
        translation_key="filter_holiday",
        entity_category=EntityCategory.CONFIG,
        option_key=CONF_FILTER_HOLIDAY,
        default=DEFAULT_FILTER_HOLIDAY,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MaCuratedRadioConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the switches."""
    async_add_entities(
        CuratedRadioSwitch(entry, description) for description in SWITCHES
    )


class CuratedRadioSwitch(CuratedRadioEntity, SwitchEntity):
    """A boolean option, exposed so a dashboard can reach it."""

    entity_description: CuratedRadioSwitchDescription

    def __init__(
        self,
        entry: MaCuratedRadioConfigEntry,
        description: CuratedRadioSwitchDescription,
    ) -> None:
        """Bind the switch to its option."""
        super().__init__(entry, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool:
        """Current value of the option."""
        return bool(
            self._option(
                self.entity_description.option_key, self.entity_description.default
            )
        )

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable the option."""
        self._write_option(self.entity_description.option_key, True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable the option."""
        self._write_option(self.entity_description.option_key, False)
