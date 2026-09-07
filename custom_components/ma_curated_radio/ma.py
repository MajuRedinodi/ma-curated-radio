"""Music Assistant access layer.

Two paths, in order of preference:

* **Service calls** (``music_assistant.get_queue`` / ``search`` /
  ``play_media``) are the stable, documented surface and the only one this
  integration requires. Called from Python they return the real objects, so
  none of the Jinja Enum-stringification that shaped the YAML version
  applies here.
* **The native client**, reached through the Music Assistant config entry's
  runtime data, offers things the service surface does not: genuine artist
  top-tracks rather than relevance-ranked search, and the literal contents
  of the current queue. That is another integration's internals, so every
  call is capability-probed and falls back silently.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from homeassistant.core import HomeAssistant

from .const import MA_DOMAIN

_LOGGER = logging.getLogger(__name__)


def field_of(obj: Any, key: str, default: Any = None) -> Any:
    """Read ``key`` off a mapping or an object, tolerating either shape.

    Music Assistant hands back dicts through the service surface and
    dataclasses through the native client; callers should not have to care.
    """
    if obj is None:
        return default
    if isinstance(obj, Mapping):
        value = obj.get(key, default)
    else:
        value = getattr(obj, key, default)
    return default if value is None else value


def text_of(obj: Any, key: str) -> str:
    """Read ``key`` as a stripped string, or an empty string."""
    return str(field_of(obj, key, "") or "").strip()


@dataclass(slots=True)
class TrackInfo:
    """The subset of a Music Assistant track this integration reasons about."""

    uri: str
    name: str
    version: str
    album: str

    @classmethod
    def from_item(cls, item: Any) -> TrackInfo:
        """Build a TrackInfo from a service-response dict or a client object."""
        return cls(
            uri=text_of(item, "uri"),
            name=text_of(item, "name"),
            version=text_of(item, "version"),
            album=text_of(field_of(item, "album"), "name"),
        )


@dataclass(slots=True)
class QueueSnapshot:
    """A point-in-time read of a player's Music Assistant queue."""

    queue_id: str = ""
    current_uri: str = ""
    next_uri: str = ""
    seed_artist: str = ""
    items: int = 0
    current_index: int = 0
    artists: list[str] = field(default_factory=list)

    @property
    def remaining(self) -> int:
        """Tracks still queued after the one playing."""
        return max(self.items - self.current_index - 1, 0)


def _media_item(queue_item: Any) -> Any:
    """Unwrap the media_item off a queue item."""
    return field_of(queue_item, "media_item")


def _artist_names(media_item: Any) -> list[str]:
    """Artist names credited on a media item, in order."""
    names = []
    for artist in field_of(media_item, "artists", []) or []:
        name = text_of(artist, "name")
        if name:
            names.append(name)
    return names


async def async_get_queue(hass: HomeAssistant, player: str) -> QueueSnapshot | None:
    """Read the player's queue, or None if it has none."""
    try:
        response = await hass.services.async_call(
            MA_DOMAIN,
            "get_queue",
            {"entity_id": player},
            blocking=True,
            return_response=True,
        )
    except Exception as err:  # noqa: BLE001 - a bad read must not kill the listener
        _LOGGER.debug("get_queue failed for %s: %s", player, err)
        return None

    if not response:
        return None
    queue_id = next(iter(response), "")
    queue = response[queue_id]

    current = _media_item(field_of(queue, "current_item"))
    artists = _artist_names(current)
    return QueueSnapshot(
        queue_id=str(queue_id),
        current_uri=text_of(current, "uri"),
        next_uri=text_of(_media_item(field_of(queue, "next_item")), "uri"),
        seed_artist=artists[0] if artists else "",
        items=int(field_of(queue, "items", 0) or 0),
        current_index=int(field_of(queue, "current_index", 0) or 0),
        artists=artists,
    )


async def async_search_tracks(
    hass: HomeAssistant, ma_entry_id: str, artist: str
) -> list[TrackInfo]:
    """Search for an artist's tracks, relevance-ranked by the provider.

    Both ``name`` and ``artist`` are set to the same string on purpose:
    ``name`` alone does fuzzy title matching instead of returning that
    artist's own catalogue.
    """
    try:
        response = await hass.services.async_call(
            MA_DOMAIN,
            "search",
            {
                "config_entry_id": ma_entry_id,
                "media_type": ["track"],
                "name": artist,
                "artist": artist,
            },
            blocking=True,
            return_response=True,
        )
    except Exception as err:  # noqa: BLE001 - one artist must not kill the batch
        _LOGGER.debug("Track search failed for %s: %s", artist, err)
        return []

    tracks = field_of(response, "tracks", []) or []
    return [TrackInfo.from_item(item) for item in tracks]


async def async_play_media(
    hass: HomeAssistant, player: str, uri: str, enqueue: str
) -> None:
    """Enqueue one track URI on the player."""
    await hass.services.async_call(
        MA_DOMAIN,
        "play_media",
        {
            "entity_id": player,
            "media_id": uri,
            "media_type": "track",
            "enqueue": enqueue,
            "radio_mode": False,
        },
        blocking=True,
    )


class NativeClient:
    """Best-effort access to the Music Assistant client object.

    Everything here is optional. Each capability is probed once; if the
    installed Music Assistant integration or client library does not expose
    it, the capability is marked unavailable and the caller falls back to
    the service surface.
    """

    def __init__(self, hass: HomeAssistant, ma_entry_id: str) -> None:
        """Track which native capabilities are still worth trying."""
        self._hass = hass
        self._ma_entry_id = ma_entry_id
        self._top_tracks_available = True
        self._queue_items_available = True

    @property
    def top_tracks_available(self) -> bool:
        """False once a native top-tracks lookup has proven unusable."""
        return self._top_tracks_available

    def _mass(self) -> Any:
        """Return the Music Assistant client, or None."""
        entry = self._hass.config_entries.async_get_entry(self._ma_entry_id)
        if entry is None:
            return None
        runtime = getattr(entry, "runtime_data", None)
        mass = getattr(runtime, "mass", None)
        if mass is not None:
            return mass
        if isinstance(runtime, Mapping) and runtime.get("mass") is not None:
            return runtime["mass"]
        legacy = (self._hass.data.get(MA_DOMAIN) or {}).get(self._ma_entry_id)
        return getattr(legacy, "mass", None)

    async def async_top_tracks(self, artist: str) -> list[TrackInfo] | None:
        """Return an artist's real top tracks, or None if unavailable.

        Resolves the artist by name first, then asks the music controller
        for that artist's top tracks. None means "fall back to search",
        which is different from an empty list ("this artist has none").
        """
        if not self._top_tracks_available:
            return None
        mass = self._mass()
        if mass is None:
            self._top_tracks_available = False
            _LOGGER.debug("Native client unavailable; using search for top tracks")
            return None

        try:
            results = await mass.music.search(
                search_query=artist, media_types=["artist"], limit=1
            )
            matches = field_of(results, "artists", []) or []
            if not matches:
                return []
            match = matches[0]
            tracks = await mass.music.artists.get_artist_toptracks(
                text_of(match, "item_id"), text_of(match, "provider")
            )
        except (AttributeError, TypeError) as err:
            # The installed client does not expose this shape. Stop trying.
            self._top_tracks_available = False
            _LOGGER.info(
                "Music Assistant client has no usable top-tracks API (%s); "
                "falling back to relevance-ranked search for every artist",
                err,
            )
            return None
        except Exception as err:  # noqa: BLE001 - transient, keep the capability
            _LOGGER.debug("Native top-tracks lookup failed for %s: %s", artist, err)
            return None

        return [TrackInfo.from_item(track) for track in (tracks or [])]

    async def async_queued_uris(self, queue_id: str) -> set[str]:
        """Return URIs already sitting in the queue, or an empty set.

        Used so a refill does not re-add something the previous batch
        already queued. The service surface reports only a queue length, so
        this is native-only; an empty set simply means no extra filtering.
        """
        if not self._queue_items_available or not queue_id:
            return set()
        mass = self._mass()
        if mass is None:
            self._queue_items_available = False
            return set()

        try:
            items = await mass.player_queues.get_queue_items(queue_id, limit=500)
        except (AttributeError, TypeError) as err:
            self._queue_items_available = False
            _LOGGER.debug("Music Assistant client has no queue-items API: %s", err)
            return set()
        except Exception as err:  # noqa: BLE001 - transient failure
            _LOGGER.debug("Queue-items lookup failed for %s: %s", queue_id, err)
            return set()

        uris = set()
        for item in items or []:
            uri = text_of(_media_item(item) or item, "uri")
            if uri:
                uris.add(uri)
        return uris
