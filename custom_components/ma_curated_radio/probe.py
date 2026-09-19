"""A fixed cross-genre sample, for comparing one popularity measure to another.

This is measurement scaffolding, not part of the station. Nothing in the
engine's normal path imports it.

The question it exists to answer: Last.fm's listener counts are known to
read low on some genres and high on others, by roughly ten to one between
country and rock. Share (a song's listeners over its artist's biggest)
was adopted because it cancels that out by construction. A provider's own
popularity score is a third measure, and before anything is built on it,
it is worth knowing whether it is a better instrument or the same one in
different units.

Answering that needs a sample chosen for a particular shape, not whatever
happened to play:

* **Six genres**, including the one Last.fm is known to mis-read, so a
  cross-genre level shift is visible at all.
* **Ten records each, spread across stature** rather than ten anthems.
  Three roughly everybody knows, four solid hits, three that are real
  records with real followings but no claim on a stranger. Without that
  spread there is nothing to correlate *within* a genre, and the
  within-genre correlation is the whole test: two measures that agree
  inside a genre and disagree across it are the same instrument with a
  per-genre offset, and averaging them would only halve the offset.
* **Era spread inside each genre**, so a measure that merely tracks
  streaming-era recency is caught looking like insight.

Several of these are here because Jeff has already judged them by ear,
which makes them the closest thing to ground truth available: the three
German records he named as records he would be upset to never hear,
Grant Lee Buffalo as an artist he called unfamiliar, Oasis-adjacent
90s alternative as one he called fine, and the two records he
favourited. A measure that ranks those the way he did is telling us
something; one that does not is not.

Titles are given as the records are commonly credited. Matching is done
by folded title downstream, so punctuation and parentheses here are for
the reader rather than for the lookup.
"""

from __future__ import annotations

from typing import Final, NamedTuple


class Sample(NamedTuple):
    """One record in the probe, with the genre it is being measured under."""

    genre: str
    artist: str
    title: str


# Ten per genre, ordered within each genre from the widest-known down to
# the most particular. The order is documentation rather than input: the
# probe reports what it measures, and a measure that reproduces this
# ordering is a measure worth having.
SAMPLE: Final[tuple[Sample, ...]] = (
    # Country: the genre Last.fm reads roughly ten times too low. If any
    # measure is going to disagree with share across genres, it is here.
    Sample("country", "Dolly Parton", "Jolene"),
    Sample("country", "Johnny Cash", "Ring of Fire"),
    Sample("country", "Garth Brooks", "Friends in Low Places"),
    Sample("country", "Willie Nelson", "On the Road Again"),
    Sample("country", "Kenny Rogers", "The Gambler"),
    Sample("country", "Alan Jackson", "Chattahoochee"),
    Sample("country", "George Strait", "Amarillo by Morning"),
    Sample("country", "Brooks & Dunn", "Boot Scootin' Boogie"),
    Sample("country", "Travis Tritt", "It's a Great Day to Be Alive"),
    Sample("country", "Vince Gill", "Go Rest High on That Mountain"),
    # Eighties pop and new wave: the lane Jeff has listened to hardest,
    # and the one whose calls he has already corrected twice.
    Sample("eighties", "a-ha", "Take On Me"),
    Sample("eighties", "Tears for Fears", "Everybody Wants to Rule the World"),
    Sample("eighties", "Soft Cell", "Tainted Love"),
    Sample("eighties", "Nena", "99 Luftballons"),
    Sample("eighties", "Falco", "Rock Me Amadeus"),
    Sample("eighties", "Peter Schilling", "Major Tom (Coming Home)"),
    Sample("eighties", "Talk Talk", "It's My Life"),
    Sample("eighties", "Thomas Dolby", "She Blinded Me with Science"),
    Sample("eighties", "Trio", "Da Da Da"),
    Sample("eighties", "Re-Flex", "The Politics of Dancing"),
    # Classic rock: the genre Last.fm reads most generously, and so the
    # other end of any cross-genre offset.
    Sample("classic-rock", "Queen", "Bohemian Rhapsody"),
    Sample("classic-rock", "Led Zeppelin", "Stairway to Heaven"),
    Sample("classic-rock", "Eagles", "Hotel California"),
    Sample("classic-rock", "Fleetwood Mac", "Go Your Own Way"),
    Sample("classic-rock", "Lynyrd Skynyrd", "Sweet Home Alabama"),
    Sample("classic-rock", "Boston", "More Than a Feeling"),
    Sample("classic-rock", "Steve Miller Band", "The Joker"),
    Sample("classic-rock", "Blue Oyster Cult", "Burnin' for You"),
    Sample("classic-rock", "Bad Company", "Feel Like Makin' Love"),
    Sample("classic-rock", "Grand Funk Railroad", "Some Kind of Wonderful"),
    # Soul and R&B: heavily covered and heavily compiled, which is the
    # case where a title match alone goes wrong most often.
    Sample("soul", "Marvin Gaye", "What's Going On"),
    Sample("soul", "Stevie Wonder", "Superstition"),
    Sample("soul", "Aretha Franklin", "Respect"),
    Sample("soul", "The Temptations", "My Girl"),
    Sample("soul", "Otis Redding", "(Sittin' On) The Dock of the Bay"),
    Sample("soul", "Al Green", "Let's Stay Together"),
    Sample("soul", "Bill Withers", "Ain't No Sunshine"),
    Sample("soul", "Earth, Wind & Fire", "September"),
    Sample("soul", "Teddy Pendergrass", "Close the Door"),
    Sample("soul", "The Chi-Lites", "Have You Seen Her"),
    # Hip-hop: the genre whose streaming numbers and whose radio stature
    # are furthest apart, in the opposite direction to country.
    Sample("hip-hop", "The Notorious B.I.G.", "Juicy"),
    Sample("hip-hop", "Dr. Dre", "Still D.R.E."),
    Sample("hip-hop", "OutKast", "Ms. Jackson"),
    Sample("hip-hop", "Snoop Dogg", "Gin and Juice"),
    Sample("hip-hop", "Wu-Tang Clan", "C.R.E.A.M."),
    Sample("hip-hop", "A Tribe Called Quest", "Can I Kick It?"),
    Sample("hip-hop", "Nas", "N.Y. State of Mind"),
    Sample("hip-hop", "Grandmaster Flash", "The Message"),
    Sample("hip-hop", "Digable Planets", "Rebirth of Slick (Cool Like Dat)"),
    Sample("hip-hop", "Black Sheep", "The Choice Is Yours"),
    # Alternative: holds both records Jeff favourited and the artist he
    # named as unfamiliar, which makes it the genre with the most
    # independent checks on whatever the numbers say.
    Sample("alternative", "Nirvana", "Smells Like Teen Spirit"),
    Sample("alternative", "Radiohead", "Creep"),
    Sample("alternative", "Oasis", "Wonderwall"),
    Sample("alternative", "Weezer", "Buddy Holly"),
    Sample("alternative", "Beck", "Loser"),
    Sample("alternative", "Pixies", "Where Is My Mind?"),
    Sample("alternative", "Mazzy Star", "Fade Into You"),
    Sample("alternative", "Pearl Jam", "Yellow Ledbetter"),
    Sample("alternative", "The Smiths", "There Is a Light That Never Goes Out"),
    Sample("alternative", "Grant Lee Buffalo", "Fuzzy"),
)

GENRES: Final[tuple[str, ...]] = tuple(dict.fromkeys(item.genre for item in SAMPLE))


# Two records can only ever agree or disagree completely, which is not a
# correlation, it is a coin toss with two outcomes.
MIN_FOR_AGREEMENT: Final = 3


def _ranks(values: list[float]) -> list[float]:
    """Positions of ``values`` in ascending order, ties sharing a position."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    start = 0
    while start < len(order):
        stop = start
        while stop + 1 < len(order) and values[order[stop + 1]] == values[order[start]]:
            stop += 1
        shared = (start + stop) / 2
        for position in range(start, stop + 1):
            ranks[order[position]] = shared
        start = stop + 1
    return ranks


def rank_agreement(pairs: list[tuple[float, float]]) -> float | None:
    """How closely two measures order the same records. -1 to 1, or None.

    Rank correlation rather than correlation on the values, because the
    two measures are not on the same scale and never will be: one is a
    count of people running into the millions, the other a score out of a
    hundred. What matters is whether they put the same record on top.

    None when there are fewer than three records to compare, or when one
    measure gives every record the same value, in which case there is no
    ordering to agree with and a number would only invent one.

    Read it alongside the per-genre medians, not instead of them. High
    agreement within every genre plus a level shift between genres is the
    finding that would mean a composite is pointless: two instruments
    reading the same thing, one of them with a per-genre offset. High
    agreement within and no shift between would mean the second measure
    is simply better.
    """
    usable = [(a, b) for a, b in pairs if a is not None and b is not None]
    if len(usable) < MIN_FOR_AGREEMENT:
        return None
    left = _ranks([a for a, _ in usable])
    right = _ranks([b for _, b in usable])
    n = len(usable)
    mean_left, mean_right = sum(left) / n, sum(right) / n
    top = sum(
        (x - mean_left) * (y - mean_right)
        for x, y in zip(left, right, strict=True)
    )
    spread_left = sum((x - mean_left) ** 2 for x in left)
    spread_right = sum((y - mean_right) ** 2 for y in right)
    if spread_left <= 0 or spread_right <= 0:
        return None
    return round(top / (spread_left * spread_right) ** 0.5, 3)


def sample_for(genres: list[str] | None = None) -> tuple[Sample, ...]:
    """The probe sample, optionally narrowed to some genres.

    An unknown genre narrows to nothing rather than silently returning
    everything, because a probe that quietly measures the wrong sample is
    worse than one that comes back empty.
    """
    if not genres:
        return SAMPLE
    wanted = {name.strip().lower() for name in genres if name.strip()}
    return tuple(item for item in SAMPLE if item.genre in wanted)
