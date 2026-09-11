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
) -> list[tuple[str, float]]:
    """Return artists Last.fm considers similar, with their match scores.

    The match score (0 to 1) is the whole point of returning pairs. It
    ranks by similarity, which correlates strongly with how well known an
    artist is, and discarding it was what made batches drift into names
    nobody recognises.

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
    results: list[tuple[str, float]] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("name") or "")
        if not name:
            continue
        try:
            match = float(entry.get("match") or 0.0)
        except (TypeError, ValueError):
            match = 0.0
        results.append((name, match))
    return results


async def async_validate_api_key(
    session: aiohttp.ClientSession, api_key: str
) -> bool:
    """Return True if the key is accepted by Last.fm.

    Uses a well-known artist so a legitimate key cannot fail on an unknown
    name. An empty result for Cher means the key was rejected.
    """
    return bool(await async_get_similar_artists(session, api_key, "Cher", 1))


async def async_get_artist_listeners(
    session: aiohttp.ClientSession, api_key: str, artist: str
) -> int:
    """How many people Last.fm has scrobbling an artist. Zero if unknown.

    Used to tell a duo apart from a collaboration. Both arrive from a
    provider as two credited names, and both exist on Last.fm as their own
    act, so the names alone cannot separate them. The audience can: a duo
    is how its members are known, while a one-off duet is a footnote
    beside either artist's own following.

    Never raises: this only ever decides which of two names to ask about.
    """
    params = {
        "method": "artist.getinfo",
        "artist": artist,
        "api_key": api_key,
        "format": "json",
        "autocorrect": "1",
    }
    try:
        async with session.get(API_URL, params=params, timeout=TIMEOUT) as response:
            if response.status != HTTPStatus.OK:
                return 0
            payload = await response.json(content_type=None)
    except (aiohttp.ClientError, TimeoutError, ValueError) as err:
        _LOGGER.debug("Last.fm artist lookup failed for %s: %s", artist, err)
        return 0

    if not isinstance(payload, dict) or "error" in payload:
        return 0
    stats = (payload.get("artist") or {}).get("stats") or {}
    try:
        return int(stats.get("listeners") or 0)
    except (TypeError, ValueError):
        return 0


async def async_get_top_tracks(
    session: aiohttp.ClientSession, api_key: str, artist: str, limit: int
) -> list[tuple[str, int]] | None:
    """An artist's best-known songs on Last.fm, with their listener counts.

    How well known an artist is says little about how well known their
    tenth song is. The Beatles' fiftieth still has more listeners than REO
    Speedwagon's first, while Mr. Mister fall from 224k to 40k between
    their second and third. Only the per-song numbers show that.

    None if the lookup failed, as distinct from an empty list, so a caller
    can hold back rather than read an outage as "no hits at all".
    """
    params = {
        "method": "artist.gettoptracks",
        "artist": artist,
        "api_key": api_key,
        "format": "json",
        "autocorrect": "1",
        "limit": str(limit),
    }
    try:
        async with session.get(API_URL, params=params, timeout=TIMEOUT) as response:
            if response.status != HTTPStatus.OK:
                return None
            payload = await response.json(content_type=None)
    except (aiohttp.ClientError, TimeoutError, ValueError) as err:
        _LOGGER.debug("Last.fm top tracks lookup failed for %s: %s", artist, err)
        return None

    if not isinstance(payload, dict) or "error" in payload:
        return None
    entries = (payload.get("toptracks") or {}).get("track") or []
    if isinstance(entries, dict):
        entries = [entries]
    results: list[tuple[str, int]] = []
    for entry in entries:
        if not isinstance(entry, dict) or not entry.get("name"):
            continue
        try:
            listeners = int(entry.get("listeners") or 0)
        except (TypeError, ValueError):
            listeners = 0
        results.append((str(entry["name"]), listeners))
    return results
