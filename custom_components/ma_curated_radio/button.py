"""One-shot actions: build a batch, lift a mute, write out a playlist."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.button import ButtonEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import (
    DEFAULT_PLAYLIST_LENGTH,
    DEFAULT_PLAYLIST_NAME,
    DOMAIN,
    MODE_REPLACE,
    signal_update,
)
from .entity import CuratedRadioEntity

if TYPE_CHECKING:
    from . import MaCuratedRadioConfigEntry


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MaCuratedRadioConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the buttons."""
    async_add_entities(
        [
            BuildBatchButton(entry),
            UnmuteAllButton(entry),
            UnmuteSelectedButton(entry),
            AllowSelectedTrackButton(entry),
            BuildPlaylistButton(entry),
        ]
    )


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


class UnmuteSelectedButton(CuratedRadioEntity, ButtonEntity):
    """Release just the artist the dropdown is pointing at."""

    _attr_translation_key = "unmute_selected"
    _attr_icon = "mdi:account-arrow-left"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, entry: MaCuratedRadioConfigEntry) -> None:
        """Bind to the skip memory."""
        super().__init__(entry, "unmute_selected")

    async def async_press(self) -> None:
        """Lift the mute on the chosen artist.

        A cursor that has never been moved is empty, which is the common
        case when there is exactly one entry and nobody touched the
        dropdown, so fall back to the first thing on the list.
        """
        artists = self.runtime.skips.muted_labels
        chosen = self.runtime.picked.artist or (artists[0] if artists else "")
        if not chosen or chosen not in artists:
            return
        await self.runtime.skips.async_unmute(chosen)
        self.runtime.picked.artist = ""
        async_dispatcher_send(self.hass, signal_update(self._entry.entry_id))


class AllowSelectedTrackButton(CuratedRadioEntity, ButtonEntity):
    """Release just the track the dropdown is pointing at."""

    _attr_translation_key = "allow_selected_track"
    _attr_icon = "mdi:music-note-plus"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, entry: MaCuratedRadioConfigEntry) -> None:
        """Bind to the skip memory."""
        super().__init__(entry, "allow_selected_track")

    async def async_press(self) -> None:
        """Let the chosen track be queued again."""
        tracks = self.runtime.skips.suppressed_labels
        chosen = self.runtime.picked.track or (tracks[0] if tracks else "")
        if not chosen or chosen not in tracks:
            return
        await self.runtime.skips.async_allow_track(chosen)
        self.runtime.picked.track = ""
        async_dispatcher_send(self.hass, signal_update(self._entry.entry_id))


class BuildPlaylistButton(CuratedRadioEntity, ButtonEntity):
    """Write the current station out to a provider playlist.

    Exists as an entity rather than only as an action so a dashboard can
    reach it the same way it reaches everything else. It takes no
    arguments: the name is fixed so the link to it never changes, the
    length is the default, and the provider is the one the queue is
    already restricted to.

    The action remains the way to build anything else, a second playlist
    under another name or one seeded from an artist that is not playing.
    """

    _attr_translation_key = "build_playlist"
    _attr_icon = "mdi:playlist-music"

    def __init__(self, entry: MaCuratedRadioConfigEntry) -> None:
        """Bind to the engine."""
        super().__init__(entry, "build_playlist")

    async def async_press(self) -> None:
        """Refresh the playlist, leaving playback alone.

        Takes minutes rather than seconds, so it deliberately does not
        block: the result is reported by raising, which Home Assistant
        surfaces as a toast on the dashboard that pressed it.
        """
        result = await self.runtime.engine.async_build_playlist(
            name=DEFAULT_PLAYLIST_NAME,
            length=DEFAULT_PLAYLIST_LENGTH,
            provider=self.runtime.settings.provider_filter,
        )
        if result.error == "already_running":
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="playlist_running"
            )
        if result.error == "playlists_unsupported":
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="playlists_unsupported"
            )
        if result.error:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="playlist_empty",
                translation_placeholders={"name": result.name},
            )
