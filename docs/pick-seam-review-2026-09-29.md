# The pick-detection seam, cell by cell

**Date:** 29 September 2026, after v0.67.0.
**Scope:** `decide.py`, `coordinator.py` (`_handle_state_event`, `_async_decide`,
`_async_prime`, `_elapsed`), and the engine's `async_run` superseding rule.
**Method:** every event the coordinator can see, crossed with what is playing,
what the queue looks like and what the engine is doing. Each cell was walked
through the code as it stands after 0.67.0, not run. Cells marked **FAILS** are
ones I can make fail with a `decide()` call or by reading `_elapsed`; nothing
here has been changed yet.

Why this seam: five of the last six station defects lived here (the Bublé
afternoon, the 15 September re-pick, the Lady Gaga drift, the transitional
blank, and today's swallowed pick). The rules are short and every one of them
was found by use, so this is an attempt to find the rest by enumeration.

## What the coordinator can see

| Event | How it is recognised |
|---|---|
| **E1 Track started** | state `playing`, `media_content_id` differs from the last track heard playing |
| **E2 Track restarted** | state `playing`, same track, elapsed jumped back by more than 3 s |
| **E3 Anything else** | pause, volume, position updates on the same track: ignored before the queue is read |

E1 and E2 both read the queue and call `decide()`. E2 passes
`track_changed=False`.

## What the engine can be doing

**Idle** · **Building a pick** (replace) · **Building a refill** · **Cooldown**
(an external routine owns the queue) · **Disabled** · **Just restarted**
(expectation empty until `_async_prime` runs).

## The table

Queue shapes: **one** (collapsed to a single track), **intact** (our batch still
behind the current track), **+1** (one track inserted), **big foreign** (a
playlist or album, size changed by 3 or more).

| # | Event | Playing | Queue | Engine | Expected | Actual | Status |
|---|---|---|---|---|---|---|---|
| 1 | E1 | next track of our batch | intact | idle | nothing, or refill when 2 or fewer remain | same | ok, tested |
| 2 | E1 | foreign song | one | idle | pick | pick | ok, tested |
| 3 | E1 | song we queued earlier | one | idle | pick (dashboard re-pick) | pick | ok, tested (Bublé) |
| 4 | E1 | foreign song | +1, next is ours | idle | pick (MA app "play now") | pick | ok |
| 5 | E1 | song we queued earlier | +1, next is ours | idle | pick (MA app "play now" of a known song) | **nothing** | **FAILS, F2** |
| 6 | E1 | ours, two tracks ahead (double Next) | intact | idle | nothing | nothing | ok, tested (Lady Gaga) |
| 7 | E1 | ours, one back (Previous) | intact | idle | nothing | nothing | ok |
| 8 | E1 | foreign | big foreign | idle | nothing (leave the playlist alone) | nothing | ok, tested |
| 9 | E1 | foreign, inside a playlist | +1 | idle | pick | pick | ok, tested |
| 10 | E1 | last track of a foreign album | remaining 2 or fewer | idle | refill that starts a station from the album | same | ok |
| 11 | E1 | anything | blank (no current) | any | ignore, keep expectation | same | ok, tested |
| 12 | E1 | foreign song | one | building a pick | pick; build superseded | pick (0.67.0) | ok, tested |
| 13 | E1 | foreign song | one | building a refill | pick; refill superseded | pick (0.67.0) | ok |
| 14 | E1 | first track of ours, picked song ran out | intact | building | nothing | nothing | ok, tested |
| 15 | E1 | foreign song | one | cooldown | nothing (routine owns the queue) | nothing | ok, tested |
| 16 | E1 | foreign song | one | disabled | nothing, expectation cleared | same | ok |
| 17 | E1 | foreign song | one | just restarted, before prime | pick | refill with `continuing=False` | works by accident, F4 |
| 18 | E1 | foreign song | big foreign | just restarted | nothing | nothing | ok, tested |
| 19 | E2 | ours (dashboard re-pick of the song playing) | one | idle | pick | pick | ok (15 Sep) |
| 20 | E2 | ours, backward seek | intact | idle | nothing | nothing | ok |
| 21 | E2 | **the picked song, resumed after a pause over 3 s** | intact, next is ours | idle | nothing | **pick** | **FAILS, F1** |
| 22 | E2 | **the picked song, backward seek** | intact, next is ours | idle | nothing | **pick** | **FAILS, F1** |
| 23 | E2 | foreign album track, resumed after a pause | intact, next not ours | idle | nothing | nothing (bulk rule catches it) | ok by luck |
| 24 | E2 | ours, resumed after a pause | intact | any | nothing | nothing | ok, but a wasted queue read every resume |
| 25 | E1 | foreign song | one | building, then the rebuild lands | expectation follows the rebuild | expectation left empty until the next track | self-heals, F3 |
| 26 | E1/E2 | player came back from `unavailable` on a different track | any | idle | judged against a stale expectation | may read as a pick | rare, F7 |
| 27 | none | picked song ends before its build finishes | empty | building | batch lands and plays | batch lands; playback may not resume | unverified, F5 |

## Findings

### F1. Pausing the picked song rebuilds its station (high)

**Fixed in 0.68.0**, both halves, with the four tests below proven to fail
against 0.67.0 and pass after. Cells 21, 22 and 24 now read "nothing".

Two cells fail, 21 and 22, and they share a cause.

`_elapsed()` adds wall-clock time since `media_position_updated_at` whatever
the player's state is. A paused player does not advance, but its stored
position does not change either, so after a ten-minute pause the *old* state
reads as position plus ten minutes. On resume the new state reports the real
position, which is ten minutes less, and `track_restarted` fires: the song
"began again". That part is harmless on its own; it only means the queue gets
read.

The damage is in `decide()`. A restart-reading (`track_changed=False`) is
judged as a pick on `not current_is_ours` alone, and the picked song is never
ours: it is the one song in every station that somebody else put on. The
queue is intact and the next track is ours, so the bulk rule does not apply.
Verdict: PICKED. The engine then runs `replace_next`, drops the batch it just
built, and builds another around the same song. From the listener's chair
the station changes for no reason, the "last manual pick" sensor bumps, and
twenty lookups are spent.

A backward seek on the picked song (cell 22) is the same thing without the
pause.

`decide()` reproduces it with no Home Assistant:

```
call(QueueFacts(current_uri="track/pick", next_uri="track/ours", items=21, remaining=19),
     current_is_ours=False, next_is_ours=True, previous_items=21, track_changed=False)
# returns Decision.PICKED; should be NOTHING
```

**Proposed rule.** When nothing changed track, the only evidence of a pick is
the queue collapsing: a restart-reading is a pick only if `was_replaced`.
"Not ours" says nothing when the song was already playing before the reading.
That is the rule the 15 September fix meant and did not quite write.

**Also.** `_elapsed()` should add wall time only while the state is
`playing`. That stops every resume from reading the queue at all (cell 24),
and it makes `was_skipped` honest for a song that was paused a while before
the next one started.

Two lines each, two tests each. I would ship both.

### F2. Re-picking a known song from the MA app is invisible (medium)

Cell 5. The dashboard plays with `enqueue: replace`, so the queue collapses
and `was_replaced` outranks "we queued it". The Music Assistant app's "Play
now" inserts the track after the current one and jumps to it: the queue grows
by one and does not collapse. If the song is one this station queued in the
last five hundred tracks (about two days), `current_is_ours` is true, nothing
collapsed, and the reading is "normal progression". No station is built; the
old batch carries on behind the chosen song.

**Proposed rule.** A queue that grew by exactly one while the song playing is
not the expected one is an insertion, and an insertion that jumped playback is
a pick, ours or not. `inserted = previous_items is not None and items ==
previous_items + 1 and current_uri != expected_uri`. We never insert a single
track ourselves, so there is no false positive from our side.

I would ship it, but after confirming with one live "Play now" from the app
what MA actually reports for `items` and `next_item`; the rule is only as good
as that shape.

### F3. The expectation goes stale across a superseded build (low)

Cell 25. When a pick arrives mid-build, `engine.async_run` returns
"superseded" immediately and the coordinator re-reads the queue then, while
the rebuild is still running. It records a queue of one and no next track.
The rebuild lands a moment later and nothing refreshes the reading until the
next track change, which then heals it. During that one track a further pick
is judged with weaker evidence (`was_replaced` cannot fire from a previous
count of one), and the first batch track starting is judged against an empty
expectation.

**Proposed fix.** The engine already dispatches `signal_update` when a run
completes; the coordinator should re-read the queue on that signal. Small,
and it also covers the Family Room case where a cancelled decision never
reaches its own post-read.

### F4. A pick in the first second after a restart is mislabelled (low)

Cell 17. `_async_prime` runs as a task, so a track change that beats it finds
no expectation. The reading falls through to REFILL with `continuing=False`,
which `starts_station` turns into a fresh station anyway. Right station,
wrong word in the log, and it uses `add` rather than `replace_next`, which is
harmless because a queue of one has no tail. Leave it, or await prime before
subscribing; not worth a release on its own.

### F5. A song shorter than its build may leave silence (unverified)

Cell 27. A pick replaces the queue with one song. If a cold neighbourhood
takes longer to build than that song has left, the player reaches the end of
an empty queue and stops. `_async_enqueue` then writes twenty tracks with
`replace_next` and never presses play. Whether MA resumes on its own when
tracks arrive behind a stopped queue is a fact about MA that I have not
measured. Worth one deliberate test: pick a ninety-second song by an artist
nobody has asked about before and watch.

### F6. The coordinator has no tests (coverage)

**Started in 0.68.0:** `tests/integration/test_coordinator.py` drives the
real listener with real state changes, a fake `get_queue` service and the
engine replaced by a recorder. Cells 19, 21 and 24 run through it. Every
other cell in the table can be added the same way, one fixture tweak each.

`decide()` was well tested. `coordinator.py` was not tested at all:
`_elapsed`, `_snapshot`, `_handle_state_event`, `_async_decide`,
`_async_prime`. F1 lived in the untested half and was visible from a
two-line test of `_elapsed` on a paused state.

### F7. Player recovering from `unavailable` (rare)

Cell 26. Music Assistant restarting can bring the player back on a different
track from a different queue. The coordinator judges that against the
expectation from before the outage. Most outcomes are harmless; the worst is
a false pick that rebuilds a station somebody did not ask for. A cheap guard:
treat the first `playing` after `unavailable` the way startup does, adopting
the track without judging it.

## What I would do, in order

1. **F1 now.** Two rule changes, four tests, one release. It is the only
   finding that changes what plays, and it is reachable with the pause
   button.
2. **F6 alongside it**, because F1's `_elapsed` half needs a coordinator
   test to exist at all. Build the fake once; every later cell is cheap.
3. **F2 after one live measurement** of what "Play now" from the app looks
   like in `get_queue`.
4. **F3 and F7** together as one small hardening release; both are "re-read
   the queue when the world changed under you".
5. **F5** as a measurement, not a fix, until it is seen.

Cells 1 to 4, 6 to 16, 18 to 20 and 23 are sound as written and most are
already pinned by tests. The seam is not rotten; it has three real holes and
two soft spots, and the biggest hole is the pause button.
