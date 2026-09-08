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
3. It reads the artist off that track, asks Last.fm for a few similar
   artists, and pulls each artist's best-known tracks. Live versions,
   holiday content and anything played recently are filtered out. The
   artists are interleaved round-robin so nobody plays twice in a row.
4. As the batch plays down to its last couple of tracks, it **refills**
   without touching what is already queued, reseeding off whatever is
   playing at that moment. That is what lets an evening drift naturally
   instead of being locked to one batch decided at the start.

## Requirements

- Music Assistant, with at least one streaming provider.
- A free [Last.fm API key](https://www.last.fm/api/account/create). Only the
  API key is needed, not the shared secret; every lookup is anonymous and
  read-only.

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
button. Defaults in brackets.

| Option | What it does |
|---|---|
| Similar artists per batch [3] | How many Last.fm-similar artists join the seed artist. Zero keeps every batch to the seed artist alone. |
| Tracks per artist [3] | How many tracks to take from each artist. The seed may get more, depending on station style. |
| Station style [balanced] | **Artist radio** always builds from the artist you picked and never wanders. **Balanced** wanders but stays inside the degree fence below. **Discovery** wanders without limit, which is the point of it. |
| Degrees of separation [3] | How far a session may travel from the artist that started it. Ignored by Artist radio and Discovery. |
| Most in a row from one artist [2] | How many tracks by the same artist may play back to back. Two lets an artist station feel like an artist station without anyone monopolising the hour. |
| Skipped song stays away for [30 days] | Skip a song and it will not be queued again for this long. |
| Skips in a row before muting an artist [3] | Skip this many of one artist's tracks consecutively and they stop being suggested. |
| Muted artist stays away for [30 days] | How long a muted artist stays out of the similar-artist pool. |
| Refill threshold [2] | Top the queue up once this many tracks or fewer remain after the one playing. |
| Repeat memory [120 min] | How long a title stays excluded from new batches. Zero disables repeat memory. |
| Settle delay [3 s] | How long to wait after a manual pick before rewriting the queue. |
| Cooldown script or automation | If another routine also rebuilds this player's queue on a schedule (a morning genre-radio automation, say), point this at it so its rebuild is never mistaken for a manual pick. |
| Cooldown window [120 s] | How long after that routine runs to skip detection entirely. |
| Provider filter | Comma-separated provider prefixes to restrict tracks to, e.g. `tidal`. Empty allows every provider. |
| Skip live recordings [on] | Live versions rank high in popularity searches and rarely suit background listening. |
| Skip holiday tracks [on] | A popularity ranking will surface an artist's Christmas album in September. |
| Use catalogue order instead of search [off] | Leave it off. Music Assistant returns an artist's track catalogue rather than a popularity ranking, so turning this on fills batches with album tracks and misses the hits. |

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

`ma_curated_radio.unmute_artist` lets one muted artist back in immediately,
and `ma_curated_radio.forget_feedback` wipes every remembered skip and mute.

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

## Notes and limitations

- **The seed artist leads each batch.** That is the intent rather than an
  accident: picking a song should get you a station built around it. Set
  station style to format radio if you want it evened out.
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
