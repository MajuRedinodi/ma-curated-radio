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

The prediction on record before the first one: built around one of the
big names nearest Beyoncé (Rihanna, Janet Jackson or Destiny's Child) and
staying R&B. A Destiny's Child or Carters refill that circles back through
the same family would be the 0.31.0 narrowing cost showing up.

**Refill 1, 13:00. The prediction missed, in the worse direction.**

```
13:00  refill  led by Beyoncé, neighbours from Beyoncé
       median 1,660,464  weakest 388,201  tiers 7/6/6
       Destiny's Child, Summer Walker, Chloe x Halle, The Carters,
       Kelly Rowland, Janet Jackson, Chlöe, Doja Cat
```

```
20  Beyoncé              CUFF IT
21  Chloe x Halle        Do It
22  Summer Walker        Playing Games (w/ Bryson Tiller)
23  Destiny's Child      Cater 2 U
24  THE CARTERS          FRIENDS
25  Kelly Rowland        Motivation (w/ Lil Wayne)
26  Janet Jackson        All For You
27  Chlöe                Have Mercy
28  Summer Walker        Body
29  Doja Cat             Agora Hills
30  Chloe x Halle        Ungodly Hour
31  Kelly Rowland        Like This (w/ Eve)
32  Beyoncé              Halo
33  THE CARTERS          BOSS
34  Janet Jackson        Together Again
35  Destiny's Child      Jumpin', Jumpin'
36  Chlöe                Surprise
37  Destiny's Child      Soldier (w/ T.I., Lil Wayne)
38  Doja Cat             Say So
```

It reseeded from Beyoncé herself. 0.31.0 prefers stronger-half artists
closest to the origin, and the closest artist of all is the origin, so
she was always a candidate; the random pick landed on her and the refill
was her circle again. Thirteen of the nineteen are Beyoncé, her group, her
family or her label (Beyoncé 2, The Carters 2, Destiny's Child 3, Kelly
Rowland 2, Chloe x Halle 2, Chlöe 2); across both batches, 23 of 39.

Two more things it exposed. The dashboard tile read "2 hours ago" after
the refill, because it showed when the sensor's state last changed and a
refill led by the same artist does not change it. And the refill reported
exactly the median reach of the first batch, because reach counted each
song's position within its own batch, so the artists' deeper songs scored
like their hits.

All three fixed in 0.31.1: a refill never reseeds from the artist who led
the batch before, the tile uses last_updated, and reach and tiers use each
song's position in its artist's own ordering.
