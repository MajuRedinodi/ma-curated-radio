# Replacing the Yamaha RX-V1900 — decision, 2026-09-22

Verified against manufacturer pages, live stock status and independent
reviews on 2026-09-22. Every "best of 2026" listicle was ignored: two of
them were caught stating specs that were flatly wrong (a sub out that
does not exist, a phono input that does not exist).

## What it has to do, in Jeff's words

> Replace the Yamaha, play my records, connect to my Klipsch speakers,
> connect to Music Assistant, and sound as good as what I have now, if
> not better. I don't mind a bit of a wait for a much cheaper price.

What that resolves to:

1. A **true phono stage** (MM at minimum; MC keeps a future cartridge
   upgrade unconstrained)
2. A **line-level subwoofer output** for the Klipsch R-120SWi (run wired
   over LFE)
3. **Bass management** — a high-pass on the R-60M bookshelves. This is
   not optional under "at least as good as now": **the RX-V1900 does it
   today.** An amp without it sends the bookshelves full-range and
   blends the sub by its knob, which is a step backward from the current
   system, not a neutral choice.
4. Power is **not** a requirement in watts. Anything here will sound at
   least as good as a 2008 mass-market AVR; the Klipsch are efficient and
   the sub does the heavy lifting. Honest ratings are still preferred
   over marketing ones.
5. **Lowest cost that meets the above.** A wait is acceptable.
6. Only two sources are used: WiiM Pro (RCA) and the turntable. Music
   Assistant connectivity is already solved by the WiiM.

## The pick — buyable today

### Emotiva BasX TA1 — $499 (list $599), or $424 Factory Renewed

**Availability note:** an automated fetch of emotiva.com on 2026-09-22
read "Temporarily unavailable," but Jeff viewing the page live the same
evening saw **Add to Cart**. Trust the live page. Check the Factory
Renewed listing first: same unit, same three-year warranty, $75 less.

| | |
|---|---|
| Power | **60W × 2, both channels driven, 20Hz–20kHz, <0.02% THD** |
| Phono | **MM and MC** |
| Bass management | **Fixed 90Hz Linkwitz-Riley high-pass on the mains, 90Hz LR low-pass on the sub.** Fixed rather than variable, but 90Hz is a sound point for R-60M bookshelves |
| Also | DAC, FM tuner, line inputs, three-year warranty (same on Factory Renewed) |
| Availability | **Add to Cart on emotiva.com** (confirmed live by Jeff, 2026-09-22). Direct only: no new stock at any US retailer. No successor announced |
| Price | **$499 sale / $424 Renewed** — about half the buy-today alternative |

Why it wins under this brief: it meets every requirement, including the
one most amps fail (bass management), at half the price of anything else
that does. The 60W is not a compromise into efficient Klipsch with a sub
doing the bass. Independent reviews (Hi-Fi News, SoundStage, Andrew
Robinson, Steve Huff) are consistently positive.

**Action:** buy it from emotiva.com. Check the Factory Renewed listing
first ($424, same warranty); otherwise the new unit at the $499 sale
price.

Connect the WiiM Pro by RCA into a line input, bypassing the amp's DAC.

## The buy-today alternate

### Parasound NewClassic 200 Integrated — $1,000, in stock

| | |
|---|---|
| Power | **110W × 2, both channels driven, 20Hz–20kHz, 0.05% THD** (125W at 1%) |
| Phono | **MM (40dB / 47kΩ) and MC (50dB / 100Ω)** |
| Bass management | **Analogue, variable 20–140Hz high-pass on the mains**, plus an 80Hz low-passed sub out |
| Sub control | Level and on/off **on the remote** |
| Also | Burr-Brown PCM1798 DAC, home-theatre bypass, headphone amp, tone controls |
| Availability | **Add to Cart live on parasound.com**, with a 30-day "Reserve" price lock |
| Price | **$1,000 direct** — reviewed retail was $1,195, so already discounted |

The better amplifier, by a clear margin: nearly twice the power, a
variable crossover, a proper DAC, sub level on the remote. Independent
review (The Audio Beatnik) on its phono stage: "deep black backgrounds
and a refined purity in the tonality of instruments and voices." Choose
it if you want the box this week, or if Emotiva's hold drags on.

## Also considered

### Emotiva BasX TA2+ — $1,299, temporarily unavailable

135W × 2 honest, MM/MC, variable 40–200Hz high-pass, XLR, HDMI ARC,
USB-C. Revised May 2026 with a quieter phono stage and a metal remote,
which fixes the two complaints reviews raised. Its cooling fans become
audible when pushed hard. Everything it adds over the TA1 is
connectivity you would not use, at $800 more. Same availability hold as
the TA1.

## Home Assistant control — a nice-to-have, not a requirement

Music Assistant playback is already in HA through the WiiM Pro; this is
about controlling the **amp itself** (power, volume, input) from HA.

| | Native network | Trigger in | IR in | Serial | Practical HA path |
|---|---|---|---|---|---|
| **Emotiva TA1** | no | **no** (trigger *out* only) | no | no | Smart plug on the rear power rocker, or an **IR blaster** (Broadlink-type) learning the supplied remote — gives power, volume and input from a dashboard for ~$40 |
| **Parasound NC 200 Int** | no (Control4 driver) | no (trigger *out* only) | **yes, rear IR input** | **2-way RS-232 with exact volume control and feedback** | Wired IR from a blaster, or RS-232 via a USB-serial / serial-to-IP adapter for full two-way control with volume state |
| **Yamaha R-N600A** | **yes, MusicCast** — HA has a first-party integration | — | — | — | Plug-and-play: power, volume, input, presets. **But** verified 80W, MM only, no crossover, no YPAO: its sub out is plain full-range, so it drops bass management and is a step back from the RX-V1900 |

The WiiM Pro's 12V trigger output (220mA, rises on playback, drops on
standby) would have made auto-power free, but neither finalist has a
trigger *input*, so it is unused here.

Verdict: the TA1's IR-blaster path is cheap and adequate for a
nice-to-have. The Parasound is the more controllable box, but $500 more
for a feature that is not required is the wrong trade. The R-N600A is
the only one that is truly native and it loses the thing that actually
affects sound.

## Eliminated, and why

| Candidate | Reason |
|---|---|
| Outlaw RR2160MkII | Out of stock, not found elsewhere |
| Emotiva BasX TA2 (original) | Sold out new ($999) and Factory Renewed ($849); discontinued for the TA2+ |
| NAD C 3050 | $1,899, sold out, MM only, and its bass management is undocumented on the base unit (appears to live in the optional BluOS-D module) |
| Denon DRA-900H | Honest 100W and MM phono, two sub outs — but the manual confirms **fronts fixed full-range, low-pass on the sub only, no high-pass**. No bass management. $799 |
| Marantz Stereo 70s | Same platform as the Denon, same limitation, 75W |
| Cambridge Audio AXR100 | 100W, MM/high-output-MC phono, low-passed sub out — **no high-pass on the mains**. ~$550 |
| Yamaha A-S501 | 85W, MM phono, full-range sub out, **no bass management**. ~$600. The buy-today cost-down if bass management is given up, which is a step back from the RX-V1900 |
| Yamaha A-S301 | 60W, MM phono, full-range sub out, no bass management. ~$350 |
| Yamaha R-N600A / R-N800A | 80/100W, MM, sub out, streaming you already own via the WiiM, no high-pass. $650 / $1,000 |
| Sony STR-DH190 | **No subwoofer output at all** — roundups claiming otherwise were wrong |
| WiiM Amp / Amp Pro / Ultra | No phono stage on any of them |

## Before buying anything

Test the sub with any spare RCA cable from a drawer. Everything that
happened on the night of 2026-09-22 — the swelling, the dropouts, every
apparent fix that did not hold, the final silence after the cable was
pulled and re-run — is consistent with one broken interconnect. If that
is what it was, this document is a plan for whenever the Yamaha actually
dies, not a purchase for this week.

## Cartridge note

The AT-LP120XBT-USB ships with an AT-VM95E, moving magnet. The best-value
upgrade is the **AT-VM95ML stylus (~$170)**: a stylus-only swap on the
same body, no realignment. Both finalists handle any VM95 stylus, any MM
cartridge, and MC as well.
