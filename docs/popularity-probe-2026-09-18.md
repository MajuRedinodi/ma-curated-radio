# Last.fm listener counts against Tidal popularity

Run 2026-09-18 on the Family Room Stereo entry, integration 0.63.0, via
`ma_curated_radio.compare_popularity`. Sixty records, six genres, ten
each, one record per artist. Fifty-nine resolved on Tidal.

## The short version

Tidal's popularity score is **much less genre-skewed** than Last.fm's
listener counts, and it matches Jeff's ear on the one case where we have
his ear on record. But it fails in a way Last.fm does not: it scores a
*pressing*, not a record, so a record can come back with a number that is
simply wrong.

So: do not average them. Use each where it is sound, and use the
disagreement between them as a bug detector.

## Finding 1: the cross-genre spread, which is what we came for

These are records of comparable stature by construction, so a spread
between genres is the measure's, not the music's.

| Genre | Median Last.fm listeners | Median Tidal popularity |
|---|---:|---:|
| country | 331,924 | 81 |
| eighties | 477,619 | 73 |
| hip-hop | 830,123 | 88 |
| soul | 1,329,922 | 86 |
| classic-rock | 1,479,842 | 85 |
| alternative | 2,293,617 | 88 |

Last.fm spreads these six genres over **6.9x**. Tidal spreads them over
**1.2x**, fifteen points on a hundred-point scale.

That is the genre skew, measured. Country sits at the bottom of the
Last.fm column and in the middle of the Tidal one.

## Finding 2: the three records Jeff named

The strongest evidence here, because it is checked against a human rather
than against another number. Jeff said he would be upset if these never
came up, and that all three were huge.

| Record | Last.fm listeners | Tidal popularity |
|---|---:|---:|
| Nena, 99 Luftballons | 1,038,219 | 70 |
| Falco, Rock Me Amadeus | 477,619 | 70 |
| Peter Schilling, Major Tom (Coming Home) | 215,127 | 73 |

Last.fm spreads them **4.8x** and ranks Major Tom last by a wide margin.
Tidal puts all three inside three points and ranks Major Tom **first**.

Jeff's judgement was that all three are big records. Tidal agrees with
him. Last.fm does not.

The same check in the other direction: Grant Lee Buffalo's *Fuzzy*, which
he called unfamiliar, is the smallest record in alternative on both
measures (99,782 listeners, popularity 57, both the genre's lowest). And
Oasis's *Wonderwall*, which he called fine, is large on both. Where his
ear has spoken, both measures agree with him except on the German three,
where only Tidal does.

## Finding 3: Tidal scores pressings, not records

This is the catch, and it is serious.

| Record | Last.fm listeners | Tidal popularity |
|---|---:|---:|
| Queen, Bohemian Rhapsody | 2,312,998 | **43** |
| Wu-Tang Clan, C.R.E.A.M. | 740,372 | **31** |
| Travis Tritt, It's a Great Day to Be Alive | 254,392 | **42** |

Bohemian Rhapsody has the second-highest listener count in the entire
sample and scores 43. That is not a judgement about the record. Last.fm
aggregates scrobbles across every version of a song; Tidal scores each
release separately, so a compilation cut, a remaster or a live take
carries its own low number. Whichever pressing the search happened to
return is the number we got.

The Trio miss makes the same point from the other side. *Da Da Da* came
back unmatched, but the record is on Tidal in at least five pressings, at
201, 204, 279, 392 and 397 seconds, under two different titles (the full
German one and the English one). It was not missing, it was spread across
five entries, and our exact folded-title match found none of them.

So Tidal popularity is **unstable per lookup** in a way listener counts
are not. Left unguarded it would silently demote a Power record to
nothing depending on which URI came back that day.

## Finding 4: within a genre, the two mostly agree

Rank agreement between Last.fm listeners and Tidal popularity, per genre:

| Genre | Agreement |
|---|---:|
| soul | 0.83 |
| eighties | 0.78 |
| alternative | 0.72 |
| country | 0.68 |
| hip-hop | 0.66 |
| classic-rock | 0.20 |

Five of six land between 0.66 and 0.83: the same ordering, broadly. Classic
rock's 0.20 is almost entirely the Bohemian Rhapsody pressing, which drags
the top record of the genre to the bottom of one column.

Read together with Finding 1, this is the useful shape: **the two measures
carry the same information inside a lane, and only one of them carries a
per-genre offset.** Tidal is not a second opinion about which record is
bigger. It is the same opinion without the country penalty.

## What this means for averaging

Jeff's suggestion was to weigh Tidal against other scores and average them.
The data argues against it, for a specific reason: an average of two
measures that already agree within a lane adds nothing inside the lane,
and an average of one skewed measure with one flat one reintroduces the
skew at half strength across lanes. It would make the country problem
half as bad instead of gone, and cost the flat measure's advantage.

## What to do instead

1. **Do not average.** They are not independent opinions.

2. **Leave the tiering alone.** `tier_of` already runs on share, which is
   genre-neutral by construction, and this probe found nothing against it.

3. **Replace the absolute listener bar.** `depth_bar` and `too_deep`
   threshold on raw listener counts, and that is exactly where the 6.9x
   offset bites: a country lane's depth bar is being set from
   country-sized numbers against a constant tuned on rock-sized ones.
   This is the concrete win, and it is narrow enough to be safe.

4. **Build the disagreement check.** High listeners plus low popularity
   means we resolved the wrong pressing, not that the record is weak.
   Bohemian Rhapsody at 2.3M and 43 is a URI bug announcing itself. That
   check is worth having on its own, independent of any scoring change,
   and it came out of this measurement rather than out of theory.

5. **Match titles more loosely against the provider.** Trio was findable
   and we missed it. A prefix or containment match against the credited
   artist's catalogue would have caught all five pressings.

## What this probe could not measure, and why

**The share column is dead in this run.** Median share is 1.00 in all six
genres, because the sample picks each artist's signature record and that
is nearly always their Last.fm number one. Forty-eight of sixty sit at
exactly 1.0. So the `share_vs_popularity` figures (-0.17, 0.41, null,
0.65, -0.64, 0.41) are computed over a handful of leftovers and mean
nothing. Ignore them.

That is a sample design error, mine. One record per artist was chosen so
that two rows never share an artist total, and it does prevent that, but
it also guarantees the one record chosen is the artist's biggest. To
measure share the sample needs two or three records per artist at
different depths, accepting the shared denominator, and reporting share
within artist rather than pooling it.

The cross-genre finding does not depend on the share column, so it stands.
