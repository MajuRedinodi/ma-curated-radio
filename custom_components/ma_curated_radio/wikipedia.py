"""When a record was made, from Wikipedia.

Four sources were measured against records the era rule kept misplacing,
and this one won outright. Hank Williams' "Hey, Good Lookin'" is a 1951
recording: Last.fm dates it to an undated compilation, MusicBrainz to a
1970 reissue, Wikidata has no date property for it at all, and Wikipedia
carries both "Released 22 June 1951" and "Recorded 16 March 1951", cited
to the 78rpm issue. Across ten records Wikipedia scored eight within two
years where Wikidata scored five.

It is also the cheapest. Fifty articles come back in one request, there
is no rate limit worth the name, and no equivalent of MusicBrainz's
intermittent 503s.

Nothing here raises: a missing year has to mean "unknown", never "modern",
because the alternative throws out most of a country batch.
"""

from __future__ import annotations

import logging
from http import HTTPStatus
from typing import Any, NamedTuple

import aiohttp

from .filters import best_article, earliest_year, infobox_artist, infobox_genres

_LOGGER = logging.getLogger(__name__)

API_URL = "https://en.wikipedia.org/w/api.php"
TIMEOUT = aiohttp.ClientTimeout(total=20)

# Wikipedia asks that a client identify itself and says so in its own
# API etiquette; an anonymous agent is the one thing that gets throttled.
USER_AGENT = (
    "ma-curated-radio/0.54 "
    "( https://github.com/MajuRedinodi/ma-curated-radio )"
)

# How many articles one fetch may ask for. The API's own ceiling is 50.
ARTICLES_PER_FETCH = 50

# How far down the search results to look for the right article.
SEARCH_RESULTS = 3


async def _call(
    session: aiohttp.ClientSession, params: dict[str, str], subject: str
) -> dict[str, Any] | None:
    """One API request, None on anything that went wrong."""
    query = {**params, "format": "json", "formatversion": "2"}
    try:
        async with session.get(
            API_URL,
            params=query,
            timeout=TIMEOUT,
            headers={"User-Agent": USER_AGENT},
        ) as response:
            if response.status != HTTPStatus.OK:
                _LOGGER.debug(
                    "Wikipedia returned HTTP %s for %s", response.status, subject
                )
                return None
            payload = await response.json(content_type=None)
    except (aiohttp.ClientError, TimeoutError, ValueError) as err:
        _LOGGER.debug("Wikipedia lookup failed for %s: %s", subject, err)
        return None
    return payload if isinstance(payload, dict) else None


async def async_find_article(
    session: aiohttp.ClientSession, artist: str, title: str
) -> str:
    """The article for one recording, or "" if there is not one.

    Searched rather than looked up directly, which is the whole trick.
    Asking for the title alone resolves "Hey Good Lookin'" to a real but
    unrelated article with no dates in it, and an empty answer from the
    wrong page is indistinguishable from a song Wikipedia has never heard
    of.
    """
    if not artist or not title:
        return ""
    payload = await _call(
        session,
        {
            "action": "query",
            "list": "search",
            "srsearch": f"{title} {artist}",
            "srlimit": str(SEARCH_RESULTS),
        },
        f"{title} by {artist}",
    )
    if not payload:
        return ""
    hits = [
        str(hit.get("title") or "")
        for hit in (payload.get("query") or {}).get("search") or []
        if hit.get("title")
    ]
    return best_article(hits, title, artist)


class ArticleFacts(NamedTuple):
    """What one article says about the record it describes."""

    year: int | None = None
    genres: tuple[str, ...] = ()
    # Who the infobox credits, so the caller can tell whether this is the
    # recording it asked about or the song as somebody else first made
    # it. Empty where the article has no artist field.
    performer: str = ""


async def async_get_facts(
    session: aiohttp.ClientSession, articles: list[str]
) -> dict[str, ArticleFacts]:
    """What each article says about its record, by article name.

    Fifty at a time, which is the API's own ceiling and means a whole
    batch usually costs one request. Every field comes out of the same
    infobox, so asking for them together is free and asking separately
    would multiply the traffic for nothing.

    An article that answered nothing is still present in the result, with
    everything empty. That is the distinction the caller needs: an
    article with a thin infobox is the right page and wants a different
    field, while an article that was never found wants a better search.
    """
    found: dict[str, ArticleFacts] = {}
    wanted = [name for name in articles if name]
    for start in range(0, len(wanted), ARTICLES_PER_FETCH):
        chunk = wanted[start : start + ARTICLES_PER_FETCH]
        payload = await _call(
            session,
            {
                "action": "query",
                "prop": "revisions",
                "rvprop": "content",
                "rvslots": "main",
                "titles": "|".join(chunk),
                "redirects": "1",
            },
            f"{len(chunk)} articles",
        )
        if not payload:
            continue
        query = payload.get("query") or {}
        # A redirect means the article answered under another name; map it
        # back so the caller can find what it asked for.
        renamed: dict[str, str] = {}
        for entry in (query.get("normalized") or []) + (query.get("redirects") or []):
            if entry.get("from") and entry.get("to"):
                renamed[str(entry["to"])] = str(entry["from"])
        for page in query.get("pages") or []:
            revisions = page.get("revisions") or []
            if not revisions:
                continue
            text = ((revisions[0].get("slots") or {}).get("main") or {}).get("content")
            wikitext = str(text or "")
            detail = ArticleFacts(
                year=earliest_year(wikitext),
                genres=tuple(sorted(infobox_genres(wikitext))),
                performer=infobox_artist(wikitext),
            )
            name = str(page.get("title") or "")
            found[name] = detail
            if name in renamed:
                found[renamed[name]] = detail
    return found
