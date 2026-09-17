"""Why earliest_year read a 1996 record as 2026.

Oasis' "Don't Look Back in Anger" came back from the chart probe dated
2026, which is this year. A plausible-looking wrong year is the worst
kind, because nothing downstream can tell it from a good one, and the era
lane is about to start deciding things on these.

    python docs/year-bug-probe.py
"""

from __future__ import annotations

import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "custom_components" / "ma_curated_radio"))

from filters import (  # noqa: E402
    _FIRST_RECORDED_YEAR,
    _INFOBOX_DATE,
    _YEAR_IN_TEXT,
    best_article,
    earliest_year,
)

API = "https://en.wikipedia.org/w/api.php"
AGENT = "ma-curated-radio-probe/1.0 ( https://github.com/MajuRedinodi/ma-curated-radio )"

SUSPECTS = [
    "Don't Look Back in Anger",
    "Been Caught Stealing",
    "Everybody Hurts",
]


def body(title: str) -> tuple[str, str]:
    """The article's real name and wikitext."""
    query = {
        "action": "query",
        "prop": "revisions",
        "rvprop": "content",
        "rvslots": "main",
        "titles": title,
        "redirects": "1",
        "format": "json",
        "formatversion": "2",
    }
    request = urllib.request.Request(
        f"{API}?{urllib.parse.urlencode(query)}", headers={"User-Agent": AGENT}
    )
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
        payload = json.loads(response.read().decode("utf-8"))
    page = (payload.get("query") or {}).get("pages", [{}])[0]
    revisions = page.get("revisions") or []
    if not revisions:
        return str(page.get("title") or title), ""
    text = ((revisions[0].get("slots") or {}).get("main") or {}).get("content")
    return str(page.get("title") or title), str(text or "")


def main() -> None:
    """Show every date field and every year the rule considered."""
    for title in SUSPECTS:
        name, text = body(title)
        print(f"\n=== {name} ({len(text)} bytes) ===")
        if not text:
            print("  no article")
            continue
        print(f"  earliest_year -> {earliest_year(text)}")
        fields = _INFOBOX_DATE.findall(text)
        print(f"  {len(fields)} released/recorded field(s)")
        for index, field in enumerate(fields[:8]):
            flat = " ".join(str(field).split())[:150]
            years = [
                int(y)
                for y in _YEAR_IN_TEXT.findall(str(field))
                if int(y) >= _FIRST_RECORDED_YEAR
            ]
            print(f"    [{index}] years={years} from {flat!r}")



def which_article() -> None:
    """Which article the engine's own search actually picks.

    earliest_year turned out to be correct, so a wrong year has to mean
    a wrong article. This asks the same question async_find_article does.
    """

    for artist, title in [
        ("Oasis", "Don't Look Back in Anger"),
        ("Jane's Addiction", "Been Caught Stealing"),
    ]:
        query = {
            "action": "query",
            "list": "search",
            "srsearch": f"{title} {artist}",
            "srlimit": "3",
            "format": "json",
            "formatversion": "2",
        }
        request = urllib.request.Request(
            f"{API}?{urllib.parse.urlencode(query)}", headers={"User-Agent": AGENT}
        )
        with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
            payload = json.loads(response.read().decode("utf-8"))
        hits = [
            str(hit.get("title") or "")
            for hit in (payload.get("query") or {}).get("search") or []
            if hit.get("title")
        ]
        chosen = best_article(hits, title, artist)
        print(f"\n{title} by {artist}")
        print(f"  search returned: {hits}")
        print(f"  best_article chose: {chosen!r}")
        if chosen:
            name, text = body(chosen)
            print(f"  that article dates to: {earliest_year(text)}")


if __name__ == "__main__":
    main()
    which_article()
