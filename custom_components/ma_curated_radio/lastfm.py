"""Minimal async Last.fm client for similar-artist lookups.

The YAML version needed a hand-configured ``rest_command`` in
``configuration.yaml`` because templates cannot make HTTP calls. Here the
key lives in the config entry and the request is made directly.
"""

from __future__ import annotations

import logging
from http import HTTPStatus

import aiohttp

_LOGGER = logging.getLogger(__name__)

API_URL = "https://ws.audioscrobbler.com/2.0/"
TIMEOUT = aiohttp.ClientTimeout(total=10)


async def async_get_similar_artists(
    session: aiohttp.ClientSession,
    api_key: str,
    artist: str,
    limit: int,
) -> list[str]:
    """Return names of artists Last.fm considers similar to ``artist``.

    Never raises: a Last.fm outage should cost variety, not the whole batch.
    """
    params = {
        "method": "artist.getsimilar",
        "artist": artist,
        "api_key": api_key,
        "format": "json",
        "autocorrect": "1",
        "limit": str(limit),
    }
    try:
        async with session.get(API_URL, params=params, timeout=TIMEOUT) as response:
            if response.status != HTTPStatus.OK:
                _LOGGER.debug(
                    "Last.fm returned HTTP %s for artist %s", response.status, artist
                )
                return []
            # Last.fm serves JSON as text/plain on some error paths.
            payload = await response.json(content_type=None)
    except (aiohttp.ClientError, TimeoutError, ValueError) as err:
        _LOGGER.debug("Last.fm lookup failed for %s: %s", artist, err)
        return []

    if not isinstance(payload, dict):
        return []
    if "error" in payload:
        # Last.fm reports API-level errors with HTTP 200.
        _LOGGER.debug(
            "Last.fm error %s for %s: %s",
            payload.get("error"),
            artist,
            payload.get("message"),
        )
        return []

    similar = payload.get("similarartists") or {}
    entries = similar.get("artist") or []
    if isinstance(entries, dict):
        # A single result is returned unwrapped rather than as a list.
        entries = [entries]
    return [str(entry.get("name") or "") for entry in entries if isinstance(entry, dict)]


async def async_validate_api_key(
    session: aiohttp.ClientSession, api_key: str
) -> bool:
    """Return True if the key is accepted by Last.fm.

    Uses a well-known artist so a legitimate key cannot fail on an unknown
    name. An empty result for Cher means the key was rejected.
    """
    return bool(await async_get_similar_artists(session, api_key, "Cher", 1))
