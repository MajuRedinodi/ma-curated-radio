# Wikipedia chart peaks: measured, and not usable as a filter

Measured 17 September 2026, to answer a question Jeff raised while
listening: some records in a batch were unfamiliar, and was that the
station's fault or his own gaps?

**The rule this was testing does not work. Do not build it.** The detail
is below so nobody spends another evening on it.

## The question

Tiering a record by its share of its own artist's biggest song is
scale-blind on purpose, which is what makes it work across genres. It is
also blind to whether anyone has heard of the artist. Grant Lee Buffalo's
"Fuzzy" really is their biggest record and is correctly filed Power, and
almost nobody knows it.

Chart peak looked like the missing signal, because it measures whether a
record was a hit rather than how its artist's audience is shaped. We
already fetch each article's full wikitext for the release year, so it
would have cost nothing extra.

## What the data says

`chart-probe.py` pulls peaks for a list of records, using the same search
and the same parsers the engine uses.

**Where a peak exists it is correct.** Spot-checked against known values:
All Star US 4, Chasing Cars US 5, Semi-Charmed Life US 4, Shiny Happy
People US 10. 46 of 54 records from two real batches returned something.

**Where a peak is absent, absence means nothing.** Run against sixteen
records nobody would call obscure, only five returned any peak at all:

| Record | US | Rock | UK | What it actually was |
|---|---|---|---|---|
| Elvis Presley, Heartbreak Hotel | - | - | - | a number one |
| Chuck Berry, Johnny B. Goode | - | - | - | US #8 |
| Hank Williams, Kaw-Liga | - | - | - | country #1, 13 weeks |
| Merle Haggard, Mama Tried | - | - | - | country #1 |
| Billie Holiday, Strange Fruit | - | - | - | pre-chart |
| Glenn Miller, In the Mood | - | - | - | pre-chart |

So "no chart found means it was never a hit" demotes Heartbreak Hotel and
Johnny B. Goode. That is the end of the idea.

Two structural causes, neither of them a parser bug worth fixing. The
Billboard Hot 100 began in August 1958 and the UK singles chart in 1952,
so a large part of the catalogue predates the charts entirely. And older
articles report chart placings in prose rather than in a chart template,
which no reasonable regex recovers.

The failure is biased by era and genre in exactly the direction this
project keeps getting burned by: **older and country material falls out
first**, the same way an absolute listener threshold erases country.

## The conclusion that does generalise

A chart peak **may confirm and must never demote**, which is the same
asymmetry already load-bearing in `in_lane`, `too_deep`, `drop_outliers`
and the year lookup: missing data means unknown, never bad.

That makes charts useless for the problem they were fetched for, because
Grant Lee Buffalo's signal *is* an absence.

**The actual fix for that problem is artist fame relative to the pool,
which already exists**: `popularity_floor`, sitting at its loose 10%
default, plus `familiarity` and `degrees`. No new data source needed.

## What the probe did earn

Five confirmations of the cover check added in 0.54, all of them real
records that had been getting a wrong year:

| Record | Article found | Wrong year it gave |
|---|---|---|
| Wheatus, A Little Respect | Erasure | 1988 |
| Counting Crows, Big Yellow Taxi | Joni Mitchell | 1970 |
| Faith No More, Easy | Commodores | 1977 |
| Frank Sinatra, Fly Me to the Moon | Kaye Ballard | 1954 |
| George Strait, Amarillo by Morning | Terry Stafford | 1973 |

And one live bug in shipped code, fixed in 0.55.1. Oasis' "Don't Look
Back in Anger" was resolving to the 2026 documentary *Oasis: Don't Look
Back in Anger*, whose name contains the title **and** the artist, so it
scored exactly what the song's own article scored and won on search order
alone. The cover check could not catch it, because a film has no song
infobox and therefore no artist field to disagree with. A 1996 record was
being placed in the 2020s.

Also worth knowing: `performs()` rejects "Matchbox Twenty" against an
article crediting "Matchbox 20", because it compares words and `twenty`
is not `20`. It fails safe, costing a year rather than giving a wrong
one, but it is a known false positive.
