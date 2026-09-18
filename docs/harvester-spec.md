# Wikipedia corpus harvester: specification

A standalone program that downloads every song article on English
Wikipedia into one local SQLite file. Nothing else.

It is deliberately separable from this integration and needs none of its
context. Anyone, or anything, can build it from this document alone.

## Why it exists

The integration reads release years, genres and chart placings out of
Wikipedia articles, one at a time, while a batch is being built. Every
improvement to those parsers so far has required re-fetching the same
articles to test against, and each measurement has therefore been scored
on a handful of records: 54 in one case, 16 in another.

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
- **Do not create a table of extracted facts.**
- **Do not call Last.fm, MusicBrainz, Discogs or anything else.**
  Wikipedia only.
- **Do not modify the `ma_curated_radio` integration.**

The parsers already exist in `custom_components/ma_curated_radio/
filters.py` and are pinned to real failures found in use: covers dated
to whoever recorded the song first, a documentary supplying a release
year, chart absence proving nothing. A second set written alongside them
would diverge, and reconciling two answers is worse than having one.
Extraction runs later, here, against the corpus this produces.

## Where it runs and what it writes

Runs on the mgmt box (Debian 13, Python 3.13 available, 405 GB free).

Writes a single file, `corpus.db`. It is created on first run. There is
nothing to provision: no server, no container, no credentials, no
network service.

Expect **on the order of 200,000 articles**, about 6 GB of wikitext
uncompressed. SQLite does not compress text, so store the wikitext
**zlib-compressed in a BLOB column**, which brings it to roughly 1.5 GB.

Enable WAL mode on the connection:

```sql
PRAGMA journal_mode=WAL;
```

Without it, readers block on the writer and the corpus cannot be
inspected until the whole run finishes, which is hours.

## Schema

```sql
CREATE TABLE IF NOT EXISTS seen (
    title      TEXT PRIMARY KEY,   -- as the category listed it
    category   TEXT NOT NULL,      -- e.g. 'Category:1985 songs'
    canonical  TEXT,               -- title the content returned under
    state      TEXT NOT NULL       -- 'pending' | 'fetched' | 'missing'
);
CREATE INDEX IF NOT EXISTS seen_state ON seen(state);

CREATE TABLE IF NOT EXISTS article (
    canonical   TEXT PRIMARY KEY,  -- after redirect resolution
    wikitext    BLOB NOT NULL,     -- zlib-compressed UTF-8
    bytes       INTEGER NOT NULL,  -- uncompressed length
    fetched_at  TEXT NOT NULL      -- ISO 8601, UTC
);

CREATE TABLE IF NOT EXISTS progress (
    category    TEXT PRIMARY KEY,
    cmcontinue  TEXT,              -- NULL when the category is exhausted
    done        INTEGER NOT NULL DEFAULT 0,
    updated_at  TEXT NOT NULL
);
```

`seen` is both the work queue and the provenance record. Two titles that
redirect to one article share a single row in `article`.

The `category` column is worth keeping beyond provenance: a year
category is an independent statement of the release year, so it
cross-checks whatever the infobox later says.

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

Iterate `Category:1900 songs` through `Category:<current year> songs`.
A category that does not exist returns an empty result, so the range can
be walked blindly without checking first.

Continue with the `continue.cmcontinue` token from each response, and
**write it to `progress` after every page**. That is what makes a restart
cheap.

A song with no year category is simply not harvested. That is acceptable:
the integration still resolves those live, as it does today.

## Fetching content

Fifty titles per request, which is the API's own anonymous ceiling:

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

Read the content from `query.pages[].revisions[0].slots.main.content`.

Map redirects back using `query.redirects` and `query.normalized`, both
of which carry `from` and `to`, so the `seen` row that asked for a title
records the `canonical` it actually landed on.

A page with no `revisions` is `missing`. Record it as such rather than
retrying it forever.

## Politeness, which is not optional

Wikimedia will throttle or block a client that ignores this.

- **One request at a time.** No concurrency, no thread pool. There is no
  deadline here.
- **`maxlag=5` on every request.** This is Wikimedia's own backpressure
  signal. On a `maxlag` error the API returns HTTP 503 with a
  `Retry-After` header. Honour it, sleep, retry the same request. Do not
  treat it as a failure.
- **A descriptive User-Agent with contact details**, per Wikimedia's API
  etiquette. An anonymous agent is the thing that gets throttled first:

  ```
  ma-curated-radio-harvester/1.0 (https://github.com/MajuRedinodi/ma-curated-radio)
  ```

- Retry a 5xx or a connection error with exponential backoff, a few
  times, then mark the batch pending again and move on.

At one request per second with 50 titles each, roughly 200,000 articles
is about 4,000 content requests plus enumeration: **two to three hours**.
That is fine. It runs once.

## Resuming

The program must be safe to kill and restart at any point.

On start: read `progress` for partly-walked categories, then select from
`seen` where `state = 'pending'`. Nothing already fetched is fetched
again. A restart should cost seconds, not hours.

Commit after each batch rather than at the end.

## Knowing it worked

- `SELECT count(*) FROM article` lands somewhere around 150,000 to
  250,000.
- `SELECT count(*) FROM seen WHERE state = 'pending'` is zero.
- `SELECT count(*) FROM seen WHERE state = 'missing'` is small, well
  under one percent.
- A spot check decompresses cleanly and contains what it should:

  ```sql
  SELECT canonical, bytes FROM article
  WHERE canonical LIKE '%Everlong%';
  ```

  and the decompressed text contains `{{Infobox song`.

- Progress should be printable while running: categories done, articles
  fetched, current category.

## What happens next, for context only

Extraction runs separately, in this repo, against `corpus.db`, reusing
`filters.py`. It produces a second, much smaller file, `facts.db`, of
roughly 80 MB, holding only years, genres, charts and credits. That is
the file that would eventually ship alongside the integration.

`corpus.db` itself never ships. It stays on mgmt so that the next parser
improvement is free to evaluate.

Note for later: per-song listener counts come from Last.fm, whose terms
do not permit redistributing them, so they can never be in a shipped
file. Nothing in this harvester touches Last.fm.
