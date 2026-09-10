# Observed batches, 10 Sept 2026

Two stations, captured live as benchmarks for changes that were decided
but not yet heard.

1. **A modern country morning on 0.29.2**, the last run of the old refill
   rule (a refill led by whoever was playing, neighbours from a random
   artist in the stronger half). The baseline 0.31.0's refill rule has to
   match or beat.
2. **Texas Hold 'Em on 0.31.0**, the "before" for the 1.1 genre bridge,
   which is designed to send exactly this pick to country rather than to
   Beyoncé's own circle.

Same caveat as the 8 Sept file: Tidal availability and Last.fm's
neighbour lists drift, so this records what an hour sounded like, not
something to assert equality against.

## Settings

| | |
|---|---|
| Station style | balanced |
| Similar artists per batch | 8 |
| Tracks per artist | 3 |
| Tracks per batch | 19 |
| Drop artists below | 10% |
| Degrees of separation | 3 |

## 1. Country morning, 0.29.2

Picked: Dasha, "Austin (Boots Stop Workin')", first the Distant Matter
remix and then the original 37 seconds later. The second pick was
dropped because the first build was still running, which is what 0.30.1
fixed; both were Dasha, so the station came out the same.

```
08:28  replace  led by Dasha               median 153,509  weakest 44,506  tiers 7/6/6
09:22  refill   led by Russell Dickerson   median 135,210  weakest 29,696  x0.88
10:27  refill   led by Carter Faith        median 151,698  weakest 29,696  x1.12
```

Net x0.99 over two refills. The evening before, on the same rule before
0.28, a Carly Simon station went 994,825 -> 759,282 -> 337,793 (x0.34).

Artists, in order of appearance, 58 tracks, none repeated:

```
batch 1  Dasha, Alana Springsteen (w/ Chris Stapleton, Mitchell Tenpenny),
         Tucker Wetmore, Megan Moroney, Ingrid Andress, Russell Dickerson,
         Max McNown, Gabby Barrett, Lainey Wilson
refill 1 Russell Dickerson, Vincent Mason, Carly Pearce, Riley Green,
         Carter Faith, Ty Myers, Kelsea Ballerini, Cody Johnson,
         Parker McCollum
refill 2 Luke Combs, Carter Faith, Parker McCollum, HARDY, Corey Kent,
         Cody Johnson, Hudson Westbrook, Jason Aldean, Tucker Wetmore
```

Twenty-two different artists, all modern country, and heavy with radio
hits: Tennessee Orange, I Hope, 'Til You Can't, I Hope You're Happy Now,
Don't Mind If I Do, Fast Car, Beautiful Crazy, Dirt Road Anthem, TRUCK
BED. The reach figures read as deep only because Last.fm's audience
barely listens to current country.

**What this showed about the old rule.** "Led by" on a refill was
whoever was playing when the queue ran low, and the lead takes the lead
slots. Carter Faith, at 60,606 listeners the smallest artist in refill 1,
was playing when refill 2 fired, so she led it and brought three more of
her deepest songs; the weakest track in both refills was her third. The
neighbours for refill 2 (Luke Combs, HARDY, Aldean) came from someone
else in the stronger half. 0.31.0 makes the reseed artist lead as well.

## 2. Texas Hold 'Em, 0.31.0

Picked 11:52. Built in 16 seconds.

```
11:52  replace  led by Beyoncé, neighbours from Beyoncé
       median 1,660,464  weakest 271,813  tiers 7/6/6
       Destiny's Child, Janet Jackson, The Carters, Victoria Monét,
       Summer Walker, Tyla, Rihanna, Solange
```

```
 0  Beyoncé              TEXAS HOLD 'EM            (the pick)
 1  Beyoncé / JAŸ-Z      Crazy In Love
 2  THE CARTERS          APESHIT
 3  Summer Walker/Drake  Girls Need Love (Remix)
 4  Destiny's Child      Say My Name
 5  Victoria Monét       On My Mama
 6  Tyla                 Water
 7  Janet Jackson        That's The Way Love Goes
 8  THE CARTERS          SUMMER
 9  Solange              Cranes in the Sky
10  Rihanna              Don't Stop The Music
11  Victoria Monét       Alright
12  Janet Jackson        Any Time, Any Place
13  Beyoncé              FORMATION
14  Tyla                 CHANEL
15  Summer Walker/USHER  Come Thru
16  Destiny's Child      Lose My Breath
17  THE CARTERS          NICE
18  Solange              Almeda
19  Rihanna / JAŸ-Z      Umbrella
```

**The crossover problem, measured.** A country song produced an hour with
no country in it at all. The station follows the artist's circle, which
is what Last.fm's artist similarity describes.

**The band-members problem, measured.** Ten of the twenty tracks are
Beyoncé or her family: her own (3), The Carters (3), Destiny's Child (2)
and Solange (2). Artist similarity counts side projects and relatives;
the song-crowd seeding designed for 1.1 was simulated to drop exactly
this kind of leakage.

The hour itself is strong and hit-heavy (Crazy In Love, Say My Name,
Water, That's The Way Love Goes, Umbrella, FORMATION); the complaint is
only that it is not what the song asked for.

**What 1.1 should do with this pick**, from the simulations of 10 Sept:
the album (COWBOY CARTER) is tagged country while Beyoncé's own albums are
R&B, so the genre bridge fires; no country artist is near the song, and
of the genre's top artists Taylor Swift is rejected because her albums
now read as pop, leaving Kacey Musgraves, whose neighbours were 11 of 12
country (Maren Morris, Miranda Lambert, The Chicks, Carrie Underwood).

### Refills

To be added as they land. The prediction on record before the first one:
built around one of the big names nearest Beyoncé (Rihanna, Janet
Jackson or Destiny's Child) and staying R&B. A Destiny's Child or
Carters refill that circles back through the same family would be the
0.31.0 narrowing cost showing up.
