"""Does a Wikipedia chart peak tell a record you know from one you do not?

The question behind it: tiering a record by its share of its own artist's
biggest is scale-blind on purpose, so it works across genres. It is also
blind to whether anybody has heard of the artist. Grant Lee Buffalo's
"Fuzzy" really is their biggest record and is filed Power correctly, and
almost nobody knows it.

Chart peak is the obvious candidate for the missing signal, because it
measures whether a record was a hit rather than how its artist's audience
is distributed. We already fetch each article's full wikitext for the
release year, so if this works it costs nothing extra.

Wikipedia only. No API key, no Last.fm, nothing that needs credentials.

    python docs/chart-probe.py
"""

from __future__ import annotations

import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "custom_components" / "ma_curated_radio"))

from filters import best_article, earliest_year, infobox_artist  # noqa: E402

API = "https://en.wikipedia.org/w/api.php"
AGENT = "ma-curated-radio-probe/1.0 ( https://github.com/MajuRedinodi/ma-curated-radio )"

# Every record from the two batches Jeff listened to on 2026-09-17. The
# only verdicts he has actually given are Oasis (fine) and Grant Lee
# Buffalo (unfamiliar); everything else is deliberately unlabelled here,
# because guessing his verdicts and then scoring against the guesses
# would prove nothing.
RECORDS = [
    ("Keane", "Somewhere Only We Know"),
    ("Oasis", "Supersonic"),
    ("Oasis", "Live Forever"),
    ("Oasis", "Don't Look Back in Anger"),
    ("Oasis", "Champagne Supernova"),
    ("Ocean Colour Scene", "The Riverboat Song"),
    ("Ocean Colour Scene", "Hundred Mile High City"),
    ("Ocean Colour Scene", "The Day We Caught the Train"),
    ("Richard Ashcroft", "A Song for the Lovers"),
    ("Richard Ashcroft", "Break the Night with Colour"),
    ("Wheatus", "Teenage Dirtbag"),
    ("Wheatus", "A Little Respect"),
    ("The Libertines", "Don't Look Back into the Sun"),
    ("The Libertines", "Can't Stand Me Now"),
    ("Blur", "Parklife"),
    ("Blur", "Beetlebum"),
    ("Garbage", "Only Happy When It Rains"),
    ("Garbage", "I Think I'm Paranoid"),
    ("Garbage", "Stupid Girl"),
    ("Smash Mouth", "All Star"),
    ("R.E.M.", "Shiny Happy People"),
    ("R.E.M.", "Everybody Hurts"),
    ("Republica", "Ready to Go"),
    ("Republica", "Drop Dead Gorgeous"),
    ("Counting Crows", "Big Yellow Taxi"),
    ("Keane", "Everybody's Changing"),
    ("Matchbox Twenty", "3AM"),
    ("Foo Fighters", "Everlong"),
    ("New Radicals", "You Get What You Give"),
    ("Snow Patrol", "Chasing Cars"),
    ("The Stone Roses", "I Wanna Be Adored"),
    ("Kula Shaker", "Hey Dude"),
    ("Third Eye Blind", "Semi-Charmed Life"),
    ("Third Eye Blind", "Never Let You Go"),
    ("Third Eye Blind", "Graduate"),
    ("Third Eye Blind", "Motorcycle Drive By"),
    ("Catatonia", "Road Rage"),
    ("Jeff Buckley", "Last Goodbye"),
    ("Kaiser Chiefs", "Ruby"),
    ("Cornershop", "Brimful of Asha"),
    ("Edwyn Collins", "A Girl Like You"),
    ("Edwyn Collins", "The Magic Piper"),
    ("Buffalo Tom", "Taillights Fade"),
    ("Buffalo Tom", "Late at Night"),
    ("Faith No More", "Easy"),
    ("Beck", "Devils Haircut"),
    ("Beck", "E-Pro"),
    ("Pulp", "Disco 2000"),
    ("Pulp", "Common People"),
    ("Grant Lee Buffalo", "Fuzzy"),
    ("Grant Lee Buffalo", "Mockingbirds"),
    ("The White Stripes", "Fell in Love with a Girl"),
    ("Soul Coughing", "Circles"),
    ("Jane's Addiction", "Been Caught Stealing"),
]

VERDICTS = {"Oasis": "known", "Grant Lee Buffalo": "unknown"}

# The cohort that decides whether a chart rule is safe to build at all.
# Every one of these is a record nobody would call obscure, and most of
# them predate the charts a rule would look them up in: the Billboard Hot
# 100 began in 1958 and the UK singles chart in 1952.
OLDER = [
    ("Hank Williams", "Hey, Good Lookin'"),
    ("Hank Williams", "Your Cheatin' Heart"),
    ("Hank Williams", "Kaw-Liga"),
    ("Johnny Cash", "Folsom Prison Blues"),
    ("Patsy Cline", "Crazy"),
    ("Elvis Presley", "Heartbreak Hotel"),
    ("Chuck Berry", "Johnny B. Goode"),
    ("Billie Holiday", "Strange Fruit"),
    ("Frank Sinatra", "Fly Me to the Moon"),
    ("Glenn Miller", "In the Mood"),
    ("Robert Johnson", "Cross Road Blues"),
    ("Woody Guthrie", "This Land Is Your Land"),
    ("Antonio Vivaldi", "The Four Seasons"),
    ("George Strait", "Amarillo by Morning"),
    ("Willie Nelson", "On the Road Again"),
    ("Merle Haggard", "Mama Tried"),
]

# {{Single chart|Billboardhot100|3}} and friends. The second positional
# parameter is the peak.
SINGLE_CHART = re.compile(
    r"\{\{\s*single chart\s*\|\s*([^|}]+?)\s*\|\s*(\d+)", re.I
)
# Plain table rows: "| US [[Billboard Hot 100]] || 3" or with scope=row.
TABLE_ROW = re.compile(
    r"\|\s*(?:scope=\"?row\"?\s*\|\s*)?([^|\n]*?(?:hot 100|billboard|uk singles|"
    r"modern rock|alternative airplay|mainstream rock)[^|\n]*?)\s*\|\|?\s*"
    r"(?:align=\"?center\"?\s*\|\s*)?(\d{1,3})\b",
    re.I,
)

# Past this a "peak" is a year, a catalogue number or a chart that does
# not exist.
HIGHEST_PEAK = 200

US_HOT = ("billboardhot100", "hot 100", "us hot 100")
US_ROCK = ("alternative", "modern rock", "mainstream rock", "billboardalternative")
UK = ("uk", "ukchartstats", "uk singles", "official charts")


def fetch(params: dict[str, str]) -> dict:
    """One Wikipedia API call."""
    query = {**params, "format": "json", "formatversion": "2"}
    url = f"{API}?{urllib.parse.urlencode(query)}"
    request = urllib.request.Request(url, headers={"User-Agent": AGENT})
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
        return json.loads(response.read().decode("utf-8"))


def find(artist: str, title: str) -> str:
    """The article for one record, by the same search the engine uses."""
    payload = fetch(
        {
            "action": "query",
            "list": "search",
            "srsearch": f"{title} {artist}",
            "srlimit": "3",
        }
    )
    hits = [
        str(hit.get("title") or "")
        for hit in (payload.get("query") or {}).get("search") or []
        if hit.get("title")
    ]
    return best_article(hits, title, artist)


def wikitext(articles: list[str]) -> dict[str, str]:
    """The raw wikitext of up to 50 articles in one call."""
    out: dict[str, str] = {}
    for start in range(0, len(articles), 50):
        chunk = articles[start : start + 50]
        payload = fetch(
            {
                "action": "query",
                "prop": "revisions",
                "rvprop": "content",
                "rvslots": "main",
                "titles": "|".join(chunk),
                "redirects": "1",
            }
        )
        query = payload.get("query") or {}
        renamed = {
            str(e["to"]): str(e["from"])
            for e in (query.get("normalized") or []) + (query.get("redirects") or [])
            if e.get("from") and e.get("to")
        }
        for page in query.get("pages") or []:
            revisions = page.get("revisions") or []
            if not revisions:
                continue
            body = ((revisions[0].get("slots") or {}).get("main") or {}).get("content")
            name = str(page.get("title") or "")
            out[name] = str(body or "")
            if name in renamed:
                out[renamed[name]] = str(body or "")
    return out


def peaks(text: str) -> dict[str, int]:
    """The best peak found for each chart family we care about."""
    found: list[tuple[str, int]] = []
    found += [(name.lower(), int(peak)) for name, peak in SINGLE_CHART.findall(text)]
    found += [(name.lower(), int(peak)) for name, peak in TABLE_ROW.findall(text)]
    best: dict[str, int] = {}
    for name, peak in found:
        if not 1 <= peak <= HIGHEST_PEAK:
            continue
        for family, keys in (("us", US_HOT), ("rock", US_ROCK), ("uk", UK)):
            if any(key in name for key in keys):
                best[family] = min(best.get(family, 999), peak)
                break
    return best


def main() -> None:
    """Probe every record and print the table."""
    chosen = OLDER if "older" in sys.argv else RECORDS
    print(f"probing {len(chosen)} records\n")
    articles: dict[tuple[str, str], str] = {}
    for artist, title in chosen:
        try:
            articles[(artist, title)] = find(artist, title)
        except Exception as err:  # noqa: BLE001 - a probe, not production
            print(f"  search failed for {title} by {artist}: {err}")
            articles[(artist, title)] = ""
        time.sleep(0.1)

    bodies = wikitext(sorted({name for name in articles.values() if name}))

    header = f"{'artist':<20} {'title':<32} {'US':>4} {'rock':>5} {'UK':>4} {'year':>5}  verdict"
    print(header)
    print("-" * len(header))
    rows = []
    for (artist, title), article in articles.items():
        text = bodies.get(article, "")
        chart = peaks(text)
        performer = infobox_artist(text)
        rows.append(
            (
                artist,
                title,
                chart.get("us"),
                chart.get("rock"),
                chart.get("uk"),
                earliest_year(text) if text else None,
                VERDICTS.get(artist, ""),
                performer,
            )
        )
    for artist, title, us, rock, uk, year, verdict, performer in rows:
        flag = verdict
        if performer and artist.lower() not in performer.lower():
            flag = f"{flag} [article: {performer}]".strip()
        print(
            f"{artist:<20} {title[:32]:<32} "
            f"{us if us else '-':>4} {rock if rock else '-':>5} "
            f"{uk if uk else '-':>4} {year if year else '-':>5}  {flag}"
        )

    dated = [r for r in rows if r[2] or r[3] or r[4]]
    print(f"\n{len(dated)} of {len(rows)} records had any chart peak at all")
    with_us = [r for r in rows if r[2]]
    print(f"{len(with_us)} had a US Hot 100 peak")


if __name__ == "__main__":
    main()
