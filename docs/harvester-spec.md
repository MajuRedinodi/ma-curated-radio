# Wikipedia corpus harvester: specification

A standalone program that downloads every song article on English
Wikipedia into a Postgres database. Nothing else.

It is deliberately separable from this integration and needs none of its
context. Anyone, or anything, can build it from this document alone.

**The database already exists and the schema is already applied.** The
harvester's only job is to fill it.

## Why it exists

The integration reads release years, genres and chart placings out of
Wikipedia articles, one at a time, while a batch is being built. Every
improvement to those parsers so far has required re-fetching the same
articles to test against, so each measurement has been scored on a
handful of records: 54 in one case, 16 in another.

With the corpus held locally, a parser change is re-runnable against the
whole thing offline, in seconds, and can be scored against thousands of
records instead of dozens. That is the entire point, and it is why the
**raw wikitext must be stored**, not just the fields extracted from it.

## Scope: harvest, do not extract

**In scope:** enumerate song articles, fetch their wikitext, store it
with provenance, resume cleanly.

**Out of scope, and important:**

- **Do not parse the wikitext.** No year extraction, no genre, no chart
  reading, no infobox handling of any kind.
- **Do not create tables of extracted facts.** Do not alter the schema.
- **Do not call Last.fm, MusicBrainz, Discogs or anything else.**
  Wikipedia only.
- **Do not modify the `ma_curated_radio` integration.**

The parsers already exist in `custom_components/ma_curated_radio/
filters.py` and are pinned to real failures found in use: covers dated
to whoever recorded the song first, a documentary supplying a release
year, chart absence proving nothing. A second set written alongside them
would diverge, and reconciling two answers is worse than having one.
Extraction runs later, in this repo, against the corpus this produces.

## Where it runs and where it writes

Runs on the mgmt box, `172.16.10.15` (Debian 13, Python 3.13, 405 GB
free).

Postgres 17 in Docker, already up:

| | |
|---|---|
| Compose file | `~/docker/music-db/compose.yaml` |
| Container | `music-db`, `restart: unless-stopped` |
| Volume | named volume `music_corpus` |
| Listening on | `127.0.0.1:5432` only |
| Database / user | `music` / `music` |
| Password | in `~/docker/music-db/.env`, mode 600 |

Bound to localhost because the harvester runs on the same box. Opening
it to the network is one line in the compose file and should come with a
FortiGate rule rather than without one.

Expect **on the order of 200,000 articles** and about 6 GB of wikitext.
Do not compress anything by hand: Postgres compresses large text columns
itself, which should land the database somewhere near 2 GB.

## Deliverable: one file, `harvest.py`

That is the whole deliverable. It runs in a container that is already
written, so it needs to know nothing about the host.

**Connect with `psycopg.connect()` and no arguments.** The standard libpq
environment variables (`PGHOST`, `PGPORT`, `PGDATABASE`, `PGUSER`,
`PGPASSWORD`) are already set by the runner, so psycopg finds the
database on its own. Do not hardcode a host, and do not read `.env`.

**The only dependency is `psycopg[binary]`**, which the runner installs.
Everything else must be standard library: use `urllib.request` rather
than `requests`, so there is nothing else to install.

**Write to stdout, unbuffered progress.** That is the log. Print which
category is being walked, counts as they climb, and any backoff.

**Exit 0 when `pending` reaches zero.** The container then stops on its
own and `docker ps -a` shows it finished cleanly.

Put the file at `~/docker/music-db/harvest.py` and start it with:

```
~/docker/music-db/run-harvest.sh     # detached, survives logout
docker logs -f music-harvest         # watch
docker stop music-harvest            # stop, safely, at any point
```

The runner is `~/docker/music-db/run-harvest.sh`, already in place. It
puts the harvester on the database's own Docker network, so the host is
`music-db`, not `localhost`.

## Schema, as applied

Defined in `~/docker/music-db/schema.sql`. Reproduced here so the shape
is visible; it is already created and does not need re-running.

```sql
CREATE TABLE seen (
    title       text PRIMARY KEY,     -- as the category listed it
    category    text NOT NULL,        -- e.g. 'Category:1985 songs'
    canonical   text,                 -- title content returned under
    state       text NOT NULL DEFAULT 'pending'
                CHECK (state IN ('pending', 'fetched', 'missing')),
    seen_at     timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX seen_pending_idx ON seen (title) WHERE state = 'pending';

CREATE TABLE article (
    canonical   text PRIMARY KEY,     -- after redirect resolution
    wikitext    text NOT NULL,
    bytes       integer NOT NULL,     -- length of the text as fetched
    fetched_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE progress (
    category    text PRIMARY KEY,
    cmcontinue  text,                 -- NULL when exhausted
    done        boolean NOT NULL DEFAULT false,
    updated_at  timestamptz NOT NULL DEFAULT now()
);
```

`seen` is both the work queue and the provenance record. Two titles that
redirect to one article share a single row in `article`.

The `category` column is worth keeping beyond provenance: a year
category is an independent statement of the release year, so it
cross-checks whatever the infobox later says.

There is also a `harvest_status` view, for printing progress.

## Enumerating the articles

Use the year categories, **not** search. They are complete, clean, and
free of the noise a search returns.

```
GET https://en.wikipedia.org/w/api.php
    ?action=query
    &list=categorymembers
    &cmtitle=Category:1985 songs
    &cmtype=page
    &cmlimit=500
    &format=json
    &formatversion=2
    &maxlag=5
```

Walk `Category:1900 songs` through `Category:<current year> songs`. A
category that does not exist returns an empty result, so the range can
be walked blindly without checking first.

Continue with the `continue.cmcontinue` token from each response, and
**write it to `progress` after every page**. That is what makes a restart
cheap.

A song with no year category is simply not harvested. That is
acceptable: the integration still resolves those live, as it does today.

## Fetching content

Fifty titles per request, the API's anonymous ceiling:

```
GET https://en.wikipedia.org/w/api.php
    ?action=query
    &prop=revisions
    &rvprop=content
    &rvslots=main
    &titles=A|B|C|...
    &redirects=1
    &format=json
    &formatversion=2
    &maxlag=5
```

Read content from `query.pages[].revisions[0].slots.main.content`.

Map redirects back using `query.redirects` and `query.normalized`, both
of which carry `from` and `to`, so the `seen` row that asked for a title
records the `canonical` it landed on.

A page with no `revisions` is `missing`. Record it as such rather than
retrying forever.

## Politeness, which is not optional

Wikimedia will throttle or block a client that ignores this.

- **One request at a time.** No concurrency, no thread pool. There is no
  deadline here.
- **`maxlag=5` on every request.** Wikimedia's own backpressure signal.
  On a maxlag error the API returns HTTP 503 with a `Retry-After`
  header. Honour it, sleep, retry the same request. It is not a failure.
- **A descriptive User-Agent with contact details**, per Wikimedia's API
  etiquette. An anonymous agent is throttled first:

  ```
  ma-curated-radio-harvester/1.0 (https://github.com/MajuRedinodi/ma-curated-radio)
  ```

- Retry a 5xx or connection error with exponential backoff a few times,
  then leave the batch `pending` and move on.

At one request per second with 50 titles each, 200,000 articles is about
4,000 content requests plus enumeration: **two to three hours**. That is
fine. It runs once.

## Resuming

The program must be safe to kill and restart at any point.

On start: read `progress` for partly-walked categories, then take work
from `seen` where `state = 'pending'`. Nothing already fetched is
fetched again. A restart should cost seconds, not hours.

Commit per batch, not at the end.

## Knowing it worked

```sql
SELECT * FROM harvest_status;
```

- `articles` lands somewhere around 150,000 to 250,000
- `pending` is zero
- `missing` is small, well under one percent of `titles_seen`
- `on_disk` is roughly 2 GB

And a spot check that the text is really there:

```sql
SELECT canonical, bytes,
       position('{{Infobox song' in wikitext) > 0 AS has_infobox
FROM article WHERE canonical LIKE '%Everlong%';
```

Progress should also be printable while running.

## Known loose end

The nightly backup on mgmt archives files, so it does **not** cover a
Postgres volume. `pg_dump` needs wiring into `backup.sh` or the corpus
is unprotected, and a silent backup gap on that box has bitten before.
Not the harvester's problem, but it should not be forgotten.

## What happens next, for context only

Extraction runs separately, in this repo, against this database, reusing
`filters.py`. It produces a much smaller **SQLite** file, `facts.db`, of
roughly 80 MB, holding only years, genres, charts and credits. That is
the file that would eventually ship alongside the integration, and it is
SQLite because a HACS integration cannot require a database server.

The corpus itself never ships. It stays on mgmt so the next parser
improvement is free to evaluate.

Note for later: per-song listener counts come from Last.fm, whose terms
do not permit redistributing them, so they can never be in a shipped
file. Nothing in this harvester touches Last.fm.
