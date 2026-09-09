# Observed batches, 8 Sept 2026

Real output, captured live, kept as the benchmark any redesign has to
beat. The 8/2 batches are the control: Jeff ran them for an evening and
said "so far the eight two has been really good".

Not a test fixture yet. Track availability is Tidal-specific and the
Last.fm neighbour lists will drift, so this records *what a good hour
looked like*, not something to assert equality against.

## Settings

| | 3/3 batches | 8/2 batches |
|---|---|---|
| Similar artists per batch | 3 | 8 |
| Tracks per artist | 3 | 2 |
| Station style | artist, then balanced | balanced |
| Familiarity | familiar | familiar |
| Most in a row | 2 | 2 |
| Degrees of separation | 3 | 3 |
| Integration version | 0.17.0 / 0.18.0 | 0.18.1 |

Balanced multiplies the seed's quota by 1.5, so the seed took 5 of 14 at
3/3 and 3 of 17 at 8/2. The seed's share of the hour fell from 36% to
18%, which is probably as much of the improvement as the extra names.

## 3/3, for contrast

```
20:11  replace  seeded Electric Light Orchestra
       via ELO, Manfred Mann's Earth Band, Jeff Lynne, Boston
       15 tracks, 4 artists
```

Contains both bugs found that evening. Three ELO in a row at the start,
because the batch could not see the picked track it followed; and another
three later, because "Jeff Lynne/Electric Light Orchestra" came from the
Jeff Lynne pool and Jeff Lynne is ELO. Fixed in 0.18.0 and 0.18.1.

The same shape earlier, on Stevie Nicks, is why the hit rate dropped:

```
18:51  replace  seeded Stevie Nicks
       via Stevie Nicks, Buckingham Nicks, Fleetwood Mac, Christine McVie
```

Three of those four are the same act filed under different names, and two
of them have catalogues that are obscure end to end.

## 8/2, the control

```
21:23  replace  seeded Styx
       via Styx, Triumph, April Wine, Billy Squier, REO Speedwagon,
           Boston, The J. Geils Band, Asia, .38 Special
       17 tracks, 9 artists

  Styx            Babe · Blue Collar Man · Too Much Time On My Hands
  Triumph         Lay It On The Line · Magic Power
  April Wine      Just Between You And Me · Sign Of The Gypsy Queen
  Billy Squier    The Stroke · My Kinda Lover
  REO Speedwagon  Keep on Loving You · Take It On the Run
  Boston          More Than a Feeling · Peace of Mind
  J. Geils Band   Centerfold · Love Stinks
  Asia            Only Time Will Tell · Don't Cry
```

Not a weak entry in it. Every track is one a classic-rock station would
actually play, and no artist outstays its welcome.

```
22:26  refill   seeded Boston
       via Boston, .38 Special, Bad Company, Billy Squier, Foreigner,
           Eagles, Van Halen, Eddie Money, Kansas
       17 tracks, 9 artists

  Boston          Foreplay / Long Time · Rock & Roll Band · Smokin'
  Bad Company     Bad Company · Feel like Makin' Love
  Billy Squier    Everybody Wants You
  Foreigner       Cold as Ice
  Eagles          Hotel California
  Van Halen       Jump
  Eddie Money     Take Me Home Tonight
  Kansas          Carry on Wayward Son
```

## Two things to notice for the redesign

**The refill seam is still uncovered.** Track 29 is Boston and track 30,
the first of the next batch, is Boston again. Two in a row, so within the
cap, but only by luck: a refill is not primed with what it follows,
because it joins the end of a populated queue rather than the current
track. Had that batch opened with two Boston, it would have been three.

**Drift over two batches, unaided by the fence.** Styx to Boston is one
hop, and the neighbour list moved from Canadian AOR (Triumph, April Wine)
toward American arena rock (Eagles, Van Halen, Kansas). Still one lane,
and the degree fence never had to intervene. That is the behaviour the
clock design has to preserve, not just the track quality.
