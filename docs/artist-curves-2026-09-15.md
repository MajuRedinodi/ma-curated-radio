# How far down an artist is still a hit

Measured 15 September 2026, to answer a question the integration had been
guessing at: **how many of an artist's songs can a station play before it
is into material nobody knows?**

The answer has to work at both extremes at once. A one-hit wonder should
contribute one song. A giant's top twenty should all stay eligible. And
it cannot use raw listener counts, because Last.fm undercounts whole
genres: Hank Williams Jr's biggest song has 38,490 listeners, fewer than
Christine McVie's solo catalogue in places, and every one of his is known.

## The rule that came out of it

**Compare a track to its own artist's biggest song, not to anything
else.** Genre cancels, because the numerator and denominator are the same
artist. Scale cancels too, which is the point and also the limitation.

## Files

| File | What it is |
|---|---|
| `artist-curves-2026-09-15.json` | Raw `artist.getTopTracks` for 49 artists, up to 100 titles each with listener counts. Keep it: re-fetching costs 49 API calls. |
| `artist-curves-2026-09-15.txt` | The analysis run: per-artist curve shape, songs kept at each threshold, and the pinned verdicts. |

Cohorts were chosen so a rule could be **scored** rather than admired:
known one-hit wonders, giants, mid acts, thin neighbours, side projects,
country and classical, and three records already ruled on by ear.

## What it found

**The three pinned verdicts all land correctly at a 10 to 12% bar**, with
much wider margins than estimated:

| Record | Position | Share of its artist's #1 | Wanted |
|---|---|---|---|
| Mr. Mister, "Kyrie" | #2 | 39.0% | keep ✓ |
| Glenn Frey, "You Belong to the City" | #2 | 70.8% | keep ✓ |
| Sugar, "Candy from Strangers" | #27 | 10.0% | cut ✓ |

Real junk sits at 1 to 10%. Real second hits sit at 24 to 71%. The gap is
wide, not the narrow window that was feared.

**One-hit wonders collapse to exactly one song.** Dexys Midnight Runners'
#2 is 4% of their #1, Norman Greenbaum's 1%, The Knack's 6%, Soft Cell's
6%, Chumbawamba's 6%. At a 10% bar each keeps one track.

**Giants keep their depth.** The Beatles hold 75 songs above 25% of their
#1; their #20 is still 54%. Michael Jackson keeps 30 above 12%,
Metallica's #20 is 30%, Queen's 25%.

**Genre neutrality is demonstrated, not argued.** Hank Williams Jr's #1
has 38,490 listeners and he keeps 35 songs, because his curve is flat:
83%, 65%, 42%, 31%, 18% at positions 2, 3, 5, 10 and 20. George Strait
92/86/72, Luke Combs 79/66/55. Any absolute threshold would erase country
outright.

## Two limits worth knowing

**An outsized #1 compresses everything behind it.** a-ha's "Take on Me"
is 2,941,370 listeners, so "The Sun Always Shines on T.V." lands at 11%
and a 12% bar would cut a genuine hit. The fix is not a cleverer bar: use
a loose one (about 5%) and let track-level selection decide *which* record
plays, so the bar only ever answers "has this artist anything left".

**Scale-free rules are blind to scale, by definition.** Dave Gahan keeps
23 songs at a 10% bar, because his solo curve is flat (81%, 59%, 51%).
His #1 is 114,395 against Depeche Mode's 2,192,172, which is 5.2%, so a
popularity floor measured against the seed catches him where the
within-artist rule never can. The two rules answer different questions and
neither replaces the other.

## A rule that was tried and does not work

Detecting the "cliff" where a catalogue falls away, by looking for the
steepest drop between adjacent positions, fails in both directions. On
real curves it fires after position 1 for a-ha, Thompson Twins, Loverboy,
Don Henley, Shawn Colvin, Semisonic, Blind Melon, Nena and Harvey Danger,
every one of which has a real second track; and it never fires at all for
a catalogue that declines smoothly, which is how genuinely obscure
material survives it. A single-step measure is hostage to where the step
falls. The cumulative ratio is the stable way to ask the same question.
