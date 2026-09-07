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
| Tracks per artist [3] | How many tracks to take from each artist, seed included. Three artists at three tracks is a twelve-track batch. |
| Refill threshold [2] | Top the queue up once this many tracks or fewer remain after the one playing. |
| Repeat memory [120 min] | How long a title stays excluded from new batches. Zero disables repeat memory. |
| Settle delay [3 s] | How long to wait after a manual pick before rewriting the queue. |
| Cooldown script or automation | If another routine also rebuilds this player's queue on a schedule (a morning genre-radio automation, say), point this at it so its rebuild is never mistaken for a manual pick. |
| Cooldown window [120 s] | How long after that routine runs to skip detection entirely. |
| Provider filter | Comma-separated provider prefixes to restrict tracks to, e.g. `tidal`. Empty allows every provider. |
| Skip live recordings [on] | Live versions rank high in popularity searches and rarely suit background listening. |
| Skip holiday tracks [on] | A popularity ranking will surface an artist's Christmas album in September. |
| Prefer real top tracks [on] | Ask Music Assistant for genuine top tracks where its client exposes them, falling back to relevance-ranked search otherwise. |

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

## Notes and limitations

- **The seed artist plays first each batch.** It leads the round-robin, so
  one more track by the artist you just picked comes before the rotation
  starts.
- **Rapid Previous-Previous can read as a manual pick.** Rare, and the
  result is still on-genre.
- **Similar-artist results occasionally include collaboration credits**
  ("Artist A, Artist B" as its own Last.fm artist). Names containing a comma
  or ` & ` are filtered out, which catches most of them.
- **Never enqueue an artist by URI** if you build something similar
  yourself. `media_type: artist` plays the entire catalogue in album order.
  This integration searches `media_type: track` filtered by artist instead,
  which returns the provider's relevance ranking.
- **Refill only knows what is literally queued when the Music Assistant
  client exposes queue contents.** The service surface reports a queue
  length, not its contents. Where the client is reachable, already-queued
  tracks are excluded too; where it is not, the repeat-memory window does
  the work on its own.

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
