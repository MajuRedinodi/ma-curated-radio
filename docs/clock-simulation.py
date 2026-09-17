"""What the Balanced clock actually plays, against real Last.fm curves.

Run against docs/artist-curves-2026-09-15.json, which holds real
artist.getTopTracks for 49 artists. The point is to check the clock's
claimed composition survives contact with a pool that does not supply
tiers in the proportions the clock asks for.

    python docs/clock-simulation.py
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "custom_components" / "ma_curated_radio"))

from const import STYLE_CLOCK, STYLE_DEFAULTS  # noqa: E402
from filters import base_title, sequence_tiered, tier_of  # noqa: E402

CURVES = ROOT / "docs" / "artist-curves-2026-09-15.json"

# The artists a real Heaven 17 refill drew on 2026-09-16, restricted to
# the ones the curve file happens to hold.
EIGHTIES = [
    "Heaven 17", "Erasure", "Yazoo", "Ultravox", "Culture Club",
    "Orchestral Manoeuvres in the Dark", "Depeche Mode", "a-ha",
    "Thompson Twins", "Blancmange", "Information Society", "Camouflage",
]
# A pool of giants, where the clock should struggle to find any Deep.
GIANTS = [
    "The Beatles", "Michael Jackson", "Metallica", "Fleetwood Mac",
    "Madonna", "Elton John", "Queen", "Depeche Mode",
]
# Country, which Last.fm undercounts about tenfold.
COUNTRY = ["Hank Williams Jr.", "George Strait", "Luke Combs", "Bonnie Raitt"]
# One-hit wonders, where almost nothing should be Power past the firsts.
ONE_HITS = [
    "Dexys Midnight Runners", "Norman Greenbaum", "The Knack", "Soft Cell",
    "Chumbawamba", "Right Said Fred", "Semisonic", "Nena", "Harvey Danger",
    "Blind Melon", "Loverboy", "Men Without Hats",
]


def load() -> dict[str, list[tuple[str, int]]]:
    """Each artist's titles and listener counts, biggest first."""
    raw = json.loads(CURVES.read_text(encoding="utf-8"))
    curves: dict[str, list[tuple[str, int]]] = {}
    for artist, entry in raw.items():
        pairs = [
            (str(title), int(listeners))
            for title, listeners in (entry.get("tracks") or [])
            if title and listeners
        ]
        # The provider lists remasters as separate titles, which the
        # engine folds with base_title. Fold them here too or an
        # artist's "second record" is a remaster of their first.
        seen: set[str] = set()
        folded: list[tuple[str, int]] = []
        for title, listeners in pairs:
            key = base_title(title)
            if key and key not in seen:
                seen.add(key)
                folded.append((title, listeners))
        if folded:
            curves[artist] = folded
    return curves


def run(label: str, artists: list[str], curves: dict, style: str) -> None:
    """Draw one batch the way the engine would, and report its shape."""
    shape = STYLE_DEFAULTS[style]
    per_artist_cap = shape["tracks_per_artist"]
    length = shape["batch_length"]
    clock = STYLE_CLOCK[style]

    per_artist: list[list[str]] = []
    sized: list[tuple[str, list[str], int]] = []
    share: dict[str, float] = {}
    missing = []
    for artist in artists[: shape["max_artists"]]:
        curve = curves.get(artist)
        if not curve:
            missing.append(artist)
            continue
        biggest = curve[0][1]
        uris = []
        for title, listeners in curve[:per_artist_cap]:
            uri = f"{artist}::{title}"
            uris.append(uri)
            share[uri] = listeners / biggest
        per_artist.append(uris)
        sized.append((artist, uris, biggest))

    tiers = tier_of(sized, 0.7, None, share)
    supply = Counter(tiers.values())
    ordered = sequence_tiered(
        per_artist, tiers, clock, max_consecutive=2, length=length
    )
    played = Counter(tiers[uri] for uri in ordered)

    asked = Counter(clock[i % len(clock)] for i in range(len(ordered)))
    total = len(ordered) or 1
    familiar = 100 * (total - played["D"]) / total

    print(f"\n{label}  [{style}]")
    print(f"  drawn {len(share)} from {len(per_artist)} artists, played {len(ordered)}")
    if missing:
        print(f"  not in the curve file: {', '.join(missing)}")
    print(f"  clock asked for  P {asked['P']:2}  S {asked['S']:2}  "
          f"D {asked['D']:2}  G {asked['G']:2}")
    print(f"  pool supplied    P {supply['P']:2}  S {supply['S']:2}  "
          f"D {supply['D']:2}  G {supply['G']:2}")
    print(f"  actually played  P {played['P']:2}  S {played['S']:2}  "
          f"D {played['D']:2}  G {played['G']:2}")
    print(f"  recognisable: {familiar:.0f}%")
    runs = max_run(ordered, tiers)
    print(f"  longest run of unfamiliar records back to back: {runs}")
    print("  " + " ".join(tiers[uri] for uri in ordered))


def max_run(ordered: list[str], tiers: dict[str, str]) -> int:
    """The worst stretch of Deep tracks in a row that actually played."""
    worst = run = 0
    for uri in ordered:
        run = run + 1 if tiers[uri] == "D" else 0
        worst = max(worst, run)
    return worst


def main() -> None:
    """Every pool against every style worth checking."""
    curves = load()
    print(f"loaded curves for {len(curves)} artists")
    for style in ("balanced", "artist", "discovery"):
        run("80s synth-pop (a real refill)", EIGHTIES, curves, style)
    run("giants", GIANTS, curves, "balanced")
    run("country", COUNTRY, curves, "balanced")
    run("one-hit wonders", ONE_HITS, curves, "balanced")


if __name__ == "__main__":
    main()
