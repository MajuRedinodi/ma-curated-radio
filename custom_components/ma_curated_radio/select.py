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
    NOTHING_REMEMBERED,
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
        [
            StationStyleSelect(entry),
            FamiliaritySelect(entry),
            ExplicitSelect(entry),
            MutedArtistSelect(entry),
            SuppressedTrackSelect(entry),
        ]
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


class _ReleaseSelect(CuratedRadioEntity, SelectEntity):
    """Base for the dropdowns that point at one remembered entry.

    A dashboard cannot put a button next to each row of a templated list,
    because card actions cannot be templated. A dropdown of what is
    currently remembered, paired with a button that acts on the choice, is
    the native way to release one thing at a time.

    The options are rebuilt from the skip memory on every read, so an
    entry released elsewhere disappears here without anything to keep in
    sync. When nothing is remembered the list is a single placeholder,
    since a select with no options cannot render.
    """

    _attr_entity_category = EntityCategory.CONFIG

    @property
    def _choices(self) -> list[str]:
        """Whatever is currently remembered, most recent expiry last."""
        raise NotImplementedError

    @property
    def _chosen(self) -> str:
        """The stored cursor for this dropdown."""
        raise NotImplementedError

    def _store(self, value: str) -> None:
        """Move the cursor."""
        raise NotImplementedError

    @property
    def options(self) -> list[str]:
        """Current entries, or a placeholder when there are none."""
        return self._choices or [NOTHING_REMEMBERED]

    @property
    def current_option(self) -> str:
        """The chosen entry, falling back to the first still present.

        A cursor left pointing at something already released would make
        the entity invalid, so it lands on whatever is at the top instead.
        """
        options = self.options
        return self._chosen if self._chosen in options else options[0]

    async def async_select_option(self, option: str) -> None:
        """Point at a different entry."""
        self._store(option)
        self.async_write_ha_state()


class MutedArtistSelect(_ReleaseSelect):
    """Which muted artist the unmute button will release."""

    _attr_translation_key = "muted_artist"
    _attr_icon = "mdi:account-cancel"

    def __init__(self, entry: MaCuratedRadioConfigEntry) -> None:
        """Bind to the skip memory."""
        super().__init__(entry, "muted_artist")

    @property
    def _choices(self) -> list[str]:
        """Artists currently muted."""
        return self.runtime.skips.muted_labels

    @property
    def _chosen(self) -> str:
        """Cursor into the muted list."""
        return self.runtime.picked.artist

    def _store(self, value: str) -> None:
        """Move the muted-artist cursor."""
        self.runtime.picked.artist = value


class SuppressedTrackSelect(_ReleaseSelect):
    """Which held-off track the allow button will release."""

    _attr_translation_key = "suppressed_track"
    _attr_icon = "mdi:music-note-off"

    def __init__(self, entry: MaCuratedRadioConfigEntry) -> None:
        """Bind to the skip memory."""
        super().__init__(entry, "suppressed_track")

    @property
    def _choices(self) -> list[str]:
        """Tracks currently held off after being skipped."""
        return self.runtime.skips.suppressed_labels

    @property
    def _chosen(self) -> str:
        """Cursor into the held-off list."""
        return self.runtime.picked.track

    def _store(self, value: str) -> None:
        """Move the held-off-track cursor."""
        self.runtime.picked.track = value
