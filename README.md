# Music Assistant Curated Radio

A replacement for radio mode in [Music Assistant](https://music-assistant.io/).

Pick one song, and instead of a provider's recommendation engine wandering
off into deep cuts nobody in the room has heard of, this keeps playback in
familiar, recognisable songs in the same lane, pulled in small batches and
topped up automatically as the queue runs down.

Install it through HACS, point it at a player, and there is nothing else to
set up. No helpers, no `rest_command`, no YAML.

> This is not Music Assistant's built-in radio mode, and it does not modify
> it. Music Assistant's own radio mode is left switched off on everything
> this queues; the two are alternatives, not layers.

## How it works

1. Someone picks a song on the Music Assistant player, outside whatever
   automation normally queues music.
2. The integration notices the newly playing track is not the one the queue
   predicted, which means playback was jumped by hand. It **replaces** the
   stale queue tail, starting fresh from the new pick.
3. It reads the artist off that track and asks Last.fm for similar artists,
   weighted so the batch is mostly names you would recognise. Anyone whose
   audience is far below the rest of that pool is dropped, because a
   neighbour whose whole catalogue is obscure gives a station nothing but
   tracks nobody knows.
4. Each artist contributes its best-known tracks. Live versions, holiday
   content, karaoke, commentary and anything played recently are filtered
   out.
5. Those candidates are then **programmed** rather than shuffled. Each is
   scored by how large its artist is and how far down that artist's own
   ordering it sits, and the batch is filled to a Power, Deep, Secondary
   rotation. Plain round-robin plays everyone's biggest track and then
   everyone's second, so an hour front-loads its hits and fades; rotating
   spends the big records across the whole hour instead. No artist plays
   more than twice in a row.
6. As the batch plays down to its last couple of tracks, it **refills**
   without touching what is already queued, reseeding off whatever is
   playing at that moment. That is what lets an evening drift naturally
   instead of being locked to one batch decided at the start.

## Requirements

- **Music Assistant, set up as a Home Assistant integration.** The add-on
  alone is not enough: this uses Music Assistant's config entry, its
  actions, and its client.
- **A streaming provider with a large catalogue.** This is a real
  prerequisite rather than a nicety. Every batch works by searching a
  catalogue of millions and taking the best-known results, so a Music
  Assistant running over a local file library will disappoint: Last.fm
  suggests artists you do not own, searches return only what is on your
  disk, and "that artist's biggest songs" becomes "whichever of their
  albums I happened to rip". Developed and tested against Tidal.
- **A free [Last.fm API key](https://www.last.fm/api/account/create).** Only
  the API key is needed, not the shared secret; every lookup is anonymous
  and read-only. Without one there are no similar artists at all and every
  batch is the seed artist alone.

Nothing else. No MCP server, no external service beyond Last.fm, and
`requirements` in the manifest is empty: every import is either the
standard library or Home Assistant itself.

## Installation

### HACS

1. HACS → three-dot menu → **Custom repositories**.
2. Add this repository's URL with category **Integration**.
3. Install **Music Assistant Curated Radio**, then restart Home Assistant.
4. Settings → Devices & Services → **Add Integration** → *Music Assistant
   Curated Radio*.

### Manual

Copy `custom_components/ma_curated_radio` into your Home Assistant
`config/custom_components/` directory and restart.

## Setup

The config flow asks for two things:

| Field | Notes |
|---|---|
| Player | The **Music Assistant** `media_player` entity, not the underlying device entity. If your speaker appears twice, you want the one Music Assistant provides. |
| Last.fm API key | Validated during setup, and stored in the config entry rather than `secrets.yaml`. |

The Music Assistant instance is read off the player from the entity
registry, so there is nothing to pick and no way to pair a player with the
wrong instance.

Add the integration once per player you want this behaviour on.

## Options

Everything below is tunable afterwards from the integration's **Configure**
button, and most of it is reachable from a dashboard as well. Defaults in
brackets.

The three that shape a batch are held **per station style**, because the
styles want opposite things: Artist radio is a showcase built around one
name, Balanced is a station. The same dashboard controls follow
whichever style is selected, so tuning one cannot quietly retune another.

| Option | What it does |
|---|---|
| Similar artists per batch | How many Last.fm-similar artists join the seed artist. Zero keeps every batch to the seed artist alone. Per station style: 3 for Artist radio, 8 for the others. |
| Tracks per artist | How many tracks to draw from each artist. The seed draws more, by the station style's multiplier. Per station style: 3 everywhere. |
| Tracks per batch | How many of the drawn tracks actually play, which is what lets a batch reach deeper without getting longer. Zero plays everything drawn. Per station style: 19 for Balanced and Discovery, 0 for Artist radio. |
| Drop artists below [10%] | Drop a similar artist whose audience is below this share of the pool's own median. Catches a neighbour whose whole catalogue is obscure without penalising a genre Last.fm undercounts. Zero disables it. |
| Station style [balanced] | **Artist radio** always builds from the artist you picked and never wanders. **Balanced** wanders but stays inside the degree fence below. **Discovery** wanders without limit, which is the point of it. |
| Degrees of separation [3] | How far a session may travel from the artist that started it. Ignored by Artist radio and Discovery. |
| Most in a row from one artist [2] | How many tracks by the same artist may play back to back. Two lets an artist station feel like an artist station without anyone monopolising the hour. |
| Skipped song stays away for [30 days] | Skip a song and it will not be queued again for this long. |
| Skips in a row before muting an artist [3] | Skip this many of one artist's tracks consecutively and they stop being suggested. |
| Muted artist stays away for [30 days] | How long a muted artist stays out of the similar-artist pool. |
| Refill threshold [2] | Top the queue up once this many tracks or fewer remain after the one playing. |
| Bulk load size [3 tracks] | A manual pick is one track; a playlist or album is many. If the queue holds at least this many tracks we did not choose, and nothing after them is ours either, it is left alone. Judged on queue size rather than growth, because loading a playlist usually replaces the queue rather than adding to it. |
| Repeat memory [120 min] | How long a title stays excluded from new batches. Zero disables repeat memory. |
| Settle delay [3 s] | How long to wait after a manual pick before rewriting the queue. |
| Cooldown script or automation | Mostly unnecessary now that bulk loads are detected on their own. Point it at another routine that rebuilds this player's queue if you want belt and braces. |
| Cooldown window [120 s] | How long after that routine runs to skip detection entirely. |
| Provider filter | Comma-separated provider prefixes to restrict tracks to, e.g. `tidal`. Empty allows every provider. |
| Explicit content [no preference] | **Clean only** drops anything flagged explicit, for when younger ears are in the room. **Prefer explicit** puts the original ahead of the radio edit. |
| Skip live recordings [on] | Live versions rank high in popularity searches and rarely suit background listening. |
| Skip holiday tracks [on] | A popularity ranking will surface an artist's Christmas album in September. |
| Use catalogue order instead of search [off] | Leave it off. Music Assistant returns an artist's track catalogue rather than a popularity ranking, so turning this on fills batches with album tracks and misses the hits. |

## A dashboard to paste in

Every setting above is reachable from any dashboard, but building one by
hand is a chore. This is the one actually in use, kept in step with the
integration.

Entities are named after the config entry title, so a player set up as
"Family Room Stereo" gets `switch.family_room_stereo_curated_radio` and so
on. **Find and replace `family_room_stereo` with your own slug**, and point
the `media_player` entity near the top at your player.

To use it: **Settings → Dashboards → Add dashboard → New dashboard from
scratch**, open it, then the pencil → three-dot menu → **Raw configuration
editor**, and paste over what is there.

<details>
<summary>Dashboard YAML</summary>

```yaml
views:
  - title: Curated Radio
    path: station
    type: sections
    icon: mdi:radio
    max_columns: 3
    badges:
      - type: entity
        entity: switch.family_room_stereo_curated_radio
        name: Curated radio
        show_name: true
        show_state: true
        tap_action: {action: toggle}
      - type: entity
        entity: sensor.family_room_stereo_version
        show_name: true
        show_state: true
      - type: entity
        entity: sensor.family_room_stereo_last_manual_pick
        show_name: true
        show_state: true
        state_content: [state]

    sections:
      - type: grid
        background: {color: purple, opacity: 8}
        cards:
          - type: heading
            heading: Now playing
            icon: mdi:speaker
          - type: media-control
            entity: media_player.family_room_stereo_2
            grid_options: {columns: full, rows: 6}
          - type: tile
            entity: media_player.family_room_stereo_2
            name: Volume
            icon: mdi:volume-high
            color: purple
            hide_state: true
            features_position: inline
            features:
              - type: media-player-volume-slider
                show_mute_button: true
            grid_options: {columns: full}

      - type: grid
        background: {color: blue, opacity: 8}
        cards:
          - type: heading
            heading: Station
            icon: mdi:tune-variant
          - type: tile
            entity: button.family_room_stereo_build_a_batch_now
            name: Build a batch
            color: purple
            hide_state: true
            grid_options: {columns: 6}
          - type: tile
            entity: button.family_room_stereo_build_a_playlist
            name: Build a playlist
            color: purple
            hide_state: true
            grid_options: {columns: 6}
            tap_action:
              action: perform-action
              perform_action: button.press
              target:
                entity_id: button.family_room_stereo_build_a_playlist
              confirmation:
                text: >-
                  Rebuild the Curated Radio playlist, seeded from what is
                  playing now? It takes a few minutes and replaces the
                  playlist's current contents. Playback is untouched.
          - type: tile
            entity: sensor.family_room_stereo_last_batch_seed
            name: Last batch seed
            color: purple
            state_content: [state, last_changed]
            grid_options: {columns: full}

          - type: heading
            heading: Tuning · per station style
            heading_style: subtitle
          - type: tile
            entity: select.family_room_stereo_station_style
            name: Station style
            color: blue
            hide_state: true
            features:
              - type: select-options
            grid_options: {columns: full}
          - type: tile
            entity: number.family_room_stereo_degrees_of_separation
            name: Degrees of separation
            icon: mdi:vector-polyline
            color: blue
            features:
              - type: numeric-input
                style: buttons
            grid_options: {columns: full}
            visibility:
              - condition: state
                entity: select.family_room_stereo_station_style
                state: balanced
          - type: tile
            entity: number.family_room_stereo_similar_artists_per_batch
            name: Similar artists
            features:
              - type: numeric-input
                style: buttons
            grid_options: {columns: 6}
          - type: tile
            entity: number.family_room_stereo_tracks_per_artist
            name: Tracks per artist
            features:
              - type: numeric-input
                style: buttons
            grid_options: {columns: 6}
          - type: tile
            entity: number.family_room_stereo_tracks_per_batch
            name: Tracks per batch
            color: blue
            features:
              - type: numeric-input
                style: buttons
            grid_options: {columns: 6}
          - type: tile
            entity: number.family_room_stereo_drop_artists_below
            name: Drop artists below
            color: blue
            features:
              - type: numeric-input
                style: buttons
            grid_options: {columns: 6}
          - type: tile
            entity: number.family_room_stereo_most_in_a_row_from_one_artist
            name: Most in a row
            features:
              - type: numeric-input
                style: buttons
            grid_options: {columns: 6}
          - type: tile
            entity: number.family_room_stereo_refill_threshold
            name: Refill threshold
            features:
              - type: numeric-input
                style: buttons
            grid_options: {columns: 6}

          - type: heading
            heading: Filters
            heading_style: subtitle
          - type: tile
            entity: switch.family_room_stereo_skip_live_recordings
            name: Skip live
            color: blue
            grid_options: {columns: 6}
          - type: tile
            entity: switch.family_room_stereo_skip_holiday_tracks
            name: Skip holiday
            color: blue
            grid_options: {columns: 6}

      - type: grid
        background: {color: amber, opacity: 8}
        cards:
          - type: heading
            heading: What it has learned
            icon: mdi:school
            badges:
              - type: entity
                entity: sensor.family_room_stereo_muted_artists
                icon: mdi:account-cancel
                show_state: true
                show_name: false
              - type: entity
                entity: sensor.family_room_stereo_muted_artists
                icon: mdi:music-note-off
                show_state: true
                show_name: false
                state_content: [suppressed_tracks]

          - type: heading
            heading: Let one back in
            heading_style: subtitle
            visibility:
              - condition: or
                conditions:
                  - condition: state
                    entity: select.family_room_stereo_muted_artist_to_release
                    state_not: Nothing to release
                  - condition: state
                    entity: select.family_room_stereo_song_to_release
                    state_not: Nothing to release
          - type: tile
            entity: select.family_room_stereo_muted_artist_to_release
            name: Muted artists
            color: amber
            hide_state: true
            features:
              - type: select-options
            grid_options: {columns: full}
            visibility:
              - condition: state
                entity: select.family_room_stereo_muted_artist_to_release
                state_not: Nothing to release
          - type: tile
            entity: button.family_room_stereo_unmute_selected_artist
            name: Unmute this artist
            color: amber
            hide_state: true
            grid_options: {columns: full}
            visibility:
              - condition: state
                entity: select.family_room_stereo_muted_artist_to_release
                state_not: Nothing to release
          - type: tile
            entity: select.family_room_stereo_song_to_release
            name: Songs held back
            color: amber
            hide_state: true
            features:
              - type: select-options
            grid_options: {columns: full}
            visibility:
              - condition: state
                entity: select.family_room_stereo_song_to_release
                state_not: Nothing to release
          - type: tile
            entity: button.family_room_stereo_allow_selected_song
            name: Allow this song again
            color: amber
            hide_state: true
            grid_options: {columns: full}
            visibility:
              - condition: state
                entity: select.family_room_stereo_song_to_release
                state_not: Nothing to release

          - type: heading
            heading: Settings
            heading_style: subtitle
          - type: tile
            entity: number.family_room_stereo_skips_before_muting_an_artist
            name: Skips before muting
            color: amber
            features:
              - type: numeric-input
                style: buttons
            grid_options: {columns: full}
          - type: tile
            entity: button.family_room_stereo_unmute_all_artists
            name: Unmute all artists
            color: amber
            hide_state: true
            grid_options: {columns: full}
            visibility:
              - condition: state
                entity: select.family_room_stereo_muted_artist_to_release
                state_not: Nothing to release
```

</details>

The release dropdowns and the unmute buttons hide themselves when there is
nothing to release, so a fresh install shows a shorter third section than
the one above until it has learned something. Degrees of separation hides
unless station style is Balanced, since nothing else uses it. The car
section assumes Tidal, so change `provider` or drop the section.

## Action

`ma_curated_radio.run_batch` builds a batch immediately, seeded from
whatever is playing. Useful on a dashboard button or as a voice intent for
"play more like this".

```yaml
action: ma_curated_radio.run_batch
data:
  mode: replace   # or refill
```

`config_entry_id` is optional when only one player is configured.

`ma_curated_radio.unmute_artist` lets one muted artist back in immediately
and `ma_curated_radio.allow_track` releases one held-back song, either by
the name shown on the dashboard or by its stored key.
`ma_curated_radio.forget_feedback` wipes every remembered skip and mute.

## Taking it with you

Home Assistant cannot reach a car stereo, and Android Auto only runs apps
that implement Android's own media API, so this integration can never
appear there. What it can do is put the same music somewhere that already
has a car app.

```yaml
action: ma_curated_radio.build_playlist
data:
  name: Curated Radio
  seed_artist: Taylor Swift   # optional; defaults to what is playing
  length: 60
  provider: tidal             # optional; a provider playlist holds only its own tracks
```

That writes a playlist on your music provider using the same similar-artist
pool, the same filters and the same skip memory. Open it in that provider's
own app and you get the selection this builds at home, in the car, without
subscribing to anything new.

It reseeds as it goes, so a 60-track playlist drifts the way an evening of
refills does rather than being one batch repeated. The playlist is
refreshed in place if it already exists, so the name stays stable for
anything pointing at it.

Two honest limits:

- **Nothing comes back.** Home Assistant cannot see what you skip in
  another app, so driving teaches this nothing. The playlist benefits from
  what it has already learned; it does not learn while you use it.
- **This is the one feature that cannot degrade gracefully.** Playlist
  management is only available through Music Assistant's client, with no
  equivalent on the Home Assistant service surface. Where that is
  unavailable the action raises a clear error rather than failing quietly.
  Everything else in this integration keeps working regardless.

Playback is untouched throughout. Nothing is enqueued, nothing is
reseeded, and the rolling repeat history is deliberately not written to, so
a long playlist build cannot starve the live queue.

## How far it is allowed to wander

Reseeding off whatever is playing is what makes an evening feel alive
rather than being one batch on repeat. Unbounded, it compounds. A real
24-track build went:

```
Taylor Swift → Maisie Peters → Lorde → Katy Perry → Ke$ha → Selena Gomez → Anitta
```

Every hop is defensible and the destination is not. Worse, the drift has a
direction: each step is toward something more mainstream, because
similarity plus popularity has gravity. Left alone, anything eventually
converges on the same few global pop stars regardless of where it started.

The fence is degrees of separation from the artist that began the session,
in the Six Degrees of Kevin Bacon sense. That artist is zero, their similar
artists are one, their similars are two. Past the limit an artist is only
eligible if a shorter path already put it inside. On the path above, a
limit of three stops at Katy Perry, which is still recognisably a station
that plays Taylor Swift.

The interesting part is the behaviour at the edge. When the current artist
sits at the limit, every newcomer would be one step too far, so the
eligible set collapses to exactly those artists similar to what is playing
that are *also* still within the limit of the origin. An intersection that
falls out of the rule rather than being imposed on top of it. If even that
is empty, it reseeds back toward the origin and sets off again in another
direction, which is what a station does.

A session starts on a manual pick and expires after six hours idle, so
tonight is never still anchored to yesterday morning.

## What it learns from skips

Skipping is the only feedback nobody has to be asked for, so it is the only
feedback this collects. A track abandoned with more than fifteen seconds
left counts as a skip; one that runs out counts as played.

Two consequences, deliberately different in weight:

- **The song goes away.** Skipped tracks are not queued again for a month
  by default. Being wrong about one song out of an artist's catalogue is
  cheap.
- **Three skips in a row mutes the artist.** Consecutive is the whole
  point. Three unlucky picks spread across an evening mean nothing; three
  in a row means that artist is wrong for this room. A single track played
  through resets the run.

Two things it deliberately does not treat as a skip. Jumping to a different
song by hand is a choice about where to go, not a verdict on what was
playing. And the artist you pick yourself is never muted, however much of
theirs you skip, because you asked for them.

This is the one piece of state that survives a restart, since feedback that
evaporates is not feedback.

## Reading a batch

Every batch reports its own shape, so a station can be judged before it
plays rather than at track ten. It appears on the debug log line and as
attributes on the **Last batch seed** sensor.

```
Queued 19 track(s) in replace mode, seeded from Jackson Browne via
Jackson Browne, Little River Band, Dan Fogelberg, The Band, Van Morrison,
Steve Winwood, Joe Walsh, Dave Mason; median reach 580,807,
weakest 106,212, tiers {'P': 7, 'D': 6, 'S': 6}
```

**Median reach** is the useful one. Each track scores its artist's audience
decayed by how far down that artist's own ordering it sits, and the median
of those is an absolute number, so batches compare with each other. As a
rough guide, from observed stations:

| Median reach | What it means |
|---|---|
| under 400,000 | a pool of mid-sized or cult artists; reduce tracks per artist or it finds genuinely obscure material fast. Observed: a Pantera station at 211,000 reached Nailbomb and Exhorder and was called too deep at three tracks an artist. |
| 400,000 to 800,000 | comfortable; three tracks an artist reaches interesting places without leaving the map. Observed: Jackson Browne at 581,000. |
| over 800,000 | a pool of giants; a third or fourth track is still a hit, so depth is nearly free. Observed: Fleetwood Mac at 900,000 and Metallica at 1,900,000. |

**Weakest** is the lowest-scoring track that made it in, which is the one
most likely to be the dud.

**Tiers** is the split the hour was programmed to. Even thirds mean the
rotation had enough of each to work with; a lopsided split means the pool
could not supply one of them and the pattern gave way, which is by design.

## Reporting a problem

Most problems here are about *what got played* rather than about an
error, so there is usually nothing to paste from a crash. The debug log
line for a batch carries almost everything needed instead: the artists it
drew from, how well known they are, and what it decided the track change
meant.

Turn debug logging on from **Settings → Devices & Services → Music
Assistant Curated Radio → ⋮ → Enable debug logging**, reproduce, then
download the log from the same menu. The setting is deliberately not kept
across a restart, since Home Assistant treats it as a debugging session
rather than a preference.

Search the log for `ma_curated_radio` and include the whole run, not only
the last line:

```
Manual pick: tidal--xxxx://track/123456
Antonio Vivaldi & The Czech Philharmonic is a collaboration (6 listeners
against 2028979 for Antonio Vivaldi alone); asking Last.fm about Antonio Vivaldi
Queue session anchored to Antonio Vivaldi
Too small for this pool, dropped: Christine McVie (78,730)
Batch follows Antonio Vivaldi; primed Antonio Vivaldi
Queued 19 track(s) in replace mode, seeded from Antonio Vivaldi via ...;
median reach 1,048,914, weakest 186,916, tiers {'P': 7, 'D': 6, 'S': 6}
```

Two things that are easy to get wrong and cost a round trip:

- **Give the version from the Version sensor, not from HACS.** An update
  only takes effect after a restart, so the two disagree exactly when it
  matters.
- **Give the settings for the station style that was selected**, since
  the three that shape a batch are held per style and the dashboard shows
  whichever is current.

Worth knowing before reporting a batch that felt too obscure: how deep a
batch reaches safely is a property of the pool rather than of the
settings, and the reported reach tells the two apart. See
[Reading a batch](#reading-a-batch).

## Notes and limitations

- **The seed artist leads each batch.** That is the intent rather than an
  accident: picking a song should get you a station built around it. Set
  station style to Discovery if you want it evened out.
- **Rapid Previous-Previous can read as a manual pick.** Rare, and the
  result is still on-genre.
- **Similar-artist results occasionally include collaboration credits**
  ("Artist A, Artist B" as its own Last.fm artist). Names containing a comma
  or ` & ` are filtered out, which catches most of them.
- **Never enqueue an artist by URI** if you build something similar
  yourself. `media_type: artist` plays the entire catalogue in album order.
  This integration searches `media_type: track` filtered by artist instead,
  which returns the provider's relevance ranking.
- **Music Assistant's `get_artist_tracks` is not a top-tracks call**, whatever
  the name suggests. It returns an artist's catalogue, so selecting from the
  front of it gives album tracks and commentary rather than hits. Relevance-ranked
  search is the better source, and is what this uses by default.
- **Search matches loosely**, so asking for Madonna can return "Madonna Madonna"
  by someone else entirely. Results are checked against the credited artists.
- **Refill only knows what is literally queued when the Music Assistant
  client exposes queue contents.** The service surface reports a queue
  length, not its contents. Where the client is reachable, already-queued
  tracks are excluded too; where it is not, the repeat-memory window does
  the work on its own.
- **Only Tidal has been tested.** `explicit`, `popularity` and `release_date`
  are optional fields that providers populate inconsistently, and the
  provider filter assumes URI schemes. On another provider the explicit
  filter and the new-release promotion may be more or less reliable than
  they are here. None of that is load-bearing: each one degrades to doing
  nothing rather than doing something wrong.
- **Playlist building reaches into Music Assistant's internals**, because
  playlist management has no equivalent on the Home Assistant action
  surface. It is the one feature that could break when the Music Assistant
  integration refactors, and the one that raises an error rather than
  degrading quietly.
- **Last.fm's audience is not evenly spread across genres**, and two
  features lean on it. Country is undercounted by roughly ten times: Hank
  Williams Jr's "Family Tradition" has fewer listeners than an obscure 1973
  duo's best track. That is why the artist floor is measured against the
  pool's own median rather than an absolute number, and why the tiering is
  relative to the batch in front of it. Both work within a genre; neither
  can compare across one.
- **Reach measures how well known the artist is, not the song.** A Haydn
  string quartet scores highly because Haydn is famous, and a country
  station scores low while playing songs you know by heart. It is a good
  guide to how deep a batch can safely reach and a poor guide to how
  familiar it will feel.
- **How deep a batch can reach depends on the pool, not on taste.** Four
  tracks an artist costs nothing on a pool of giants, where a third track
  is still Walk of Life or Magic Man, and goes well past comfortable on a
  pool of mid-sized artists. The reach reported with each batch is there to
  tell the two apart before it plays: roughly, above 800,000 depth is free
  and below 400,000 it bites.
- **Some live recordings carry no marker at all.** The filters read the
  title, the version and the album, and a Hall of Fame induction recording
  of "Master Of Puppets" announces itself in none of them. Only the running
  time gives it away, and not reliably enough to filter on.
- **Skip memory cannot tell two versions of a song apart.** It matches on
  the normalised title, which is what stops a remaster and a radio edit
  both landing in one batch, so skipping a live recording also suppresses
  the studio one. Release it from the dashboard if that happens.
- **There is no era filtering, and it is not an oversight.** Mixing an
  artist's 2006 material with their 2022 material is a real weakness, and
  the data to fix it is not there. Track search returns no year at all.
  Fetching the album gets one, but it is the release year of *that
  edition*: Den Harrow's "The Legend" reports 2008 for songs recorded
  between 1984 and 1987, and a re-recorded single carries the year of the
  re-recording. Current music usually sits on its original album so the
  year is right; older music mostly arrives via compilations and remasters
  so the year is wrong, and wrong in one direction. **Old songs look new.**
  An era filter built on this would misjudge precisely the catalogue you
  were trying to reach. Music Assistant's metadata has a single
  `release_date` and no concept of an original release, so a correct
  version needs an outside source such as MusicBrainz.

## Relationship to the blueprint version

This started life as a Home Assistant script plus automation, then as a pair
of blueprints. Those still work and are published separately. The
integration exists because the YAML version had to fight Home Assistant's
template engine: Music Assistant's service responses carry `Enum` fields
nested inside their dicts, and Home Assistant's Jinja renderer silently
stringifies the entire result of a templated `variables:` expression when
the object graph contains one anywhere, even many levels deep. No error, no
warning, and every subsequent lookup on the result returns nothing.

The blueprint works around it by never storing an intermediate Music
Assistant dict as a script variable, drilling from the response straight to
plain string leaves in a single expression. Python has no such problem: a
service call from an integration returns the real objects.

## License

MIT. See [LICENSE](LICENSE).
