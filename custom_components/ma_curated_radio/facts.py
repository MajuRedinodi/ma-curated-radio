"""What is known about a record, kept between restarts.

Everything the engine learns about a song arrives from somewhere slow.
A record's era and genres cost two Last.fm lookups, its release year
costs two Wikipedia requests, and none of it survived a restart, so the
first batch after one re-learned what the batch before it already knew.

One collection for every player rather than one per config entry, because
a release year is a fact about a record and not about a room. The living
room and the phone would otherwise each pay to learn it.

Nothing here imports Home Assistant, or anything else in this
integration, on the same grounds as session.py and decide.py: the file is
written by the caller, so what a record holds and when it is worth asking
again can both be tested without the framework. That is also why the
titles arrive already folded rather than being folded here, since the
folding lives in filters with the rest of the title rules.

Size is worth writing down, since a cache that grows forever invites the
question. A full record is about 150 bytes and lookups are dictionary
gets that do not care how many there are, so nothing degrades with use.
A few thousand records a year settling lower puts five years at roughly
4 MB, which parses in well under a tenth of a second, once, at startup.
The only cost that grows is the write, because the whole file is rewritten
on every save, which is why the caller batches writes behind a delay.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Any, Final

SECONDS_PER_DAY: Final = 86400

# How long a failed lookup stays believed. A hit never expires, since a
# 1951 recording will still be a 1951 recording, but an article can be
# written or an infobox filled in, so a miss is only worth trusting for
# so long.
MISS_EXPIRY_DAYS: Final = 30

# Why a lookup came back without a year. Worth recording separately
# because the two want different fixes: no article means the search query
# needs help or the record wants a hand-picked article, while an article
# with no date is the right page and a thin infobox. Kept apart so the
# misses are a work list already sorted by the kind of work.
MISS_NO_ARTICLE: Final = "no_article"
MISS_NO_DATE: Final = "no_date"

# No reason was recorded, which is what a record that answered looks like.
MISS_NONE: Final = ""

MISS_KINDS: Final = (MISS_NO_ARTICLE, MISS_NO_DATE)


def _today() -> int:
    """Today as a count of days.

    A day number rather than a timestamp or an ISO date. It compares as an
    integer, it is a third the size written out, and nothing here wants an
    accuracy finer than a day.
    """
    return int(datetime.now(UTC).timestamp() // SECONDS_PER_DAY)


def fact_key(artist: str, base: str) -> str:
    """How one record is filed, from an artist and an already-folded title.

    By artist and title rather than by provider URI or by article name.
    The URI is per-provider and would not survive moving off Tidal, and
    the article name is an answer rather than a question: a lookup starts
    from what the provider credited, which is the only thing the engine
    has in hand.

    ``base`` is expected to have been through ``filters.base_title``,
    which is what makes a remaster, a single edit and an album cut share
    one record. The folding is deliberately the caller's: it lives in
    filters with the rest of the title rules and the tests that pin them,
    and the engine already folds exactly this way for its in-memory lane
    cache, so the two agree by construction rather than by coincidence.
    """
    return f"{artist.strip().lower()}|{base.strip().lower()}"


def _genres(raw: Iterable[Any]) -> tuple[str, ...]:
    """Genres as the lane check compares them.

    Normalised exactly as lane_of does, and no further. Folding out the
    punctuation as well would read better and would mean a stored
    "synth-pop" could never match the album tag "synth-pop" it is
    supposed to reinforce.
    """
    seen: list[str] = []
    for item in raw:
        genre = str(item).strip().lower()
        if genre and genre not in seen:
            seen.append(genre)
    return tuple(seen)


@dataclass(frozen=True)
class Fact:
    """Everything known about one record.

    Every field has a default, which is the property that lets the schema
    grow without a migration: a record written before a field existed
    reads as not knowing it, and "not known" is a case the engine already
    has to handle everywhere.
    """

    # The earliest year the record was released or recorded. None means
    # nobody has told us, never that the record is modern: treating a
    # missing year as recent throws out most of a country batch.
    year: int | None = None
    genres: tuple[str, ...] = ()
    # Which Wikipedia article answered, so a wrong match is visible later
    # rather than being an inexplicable year.
    article: str = ""
    # Why there is no year, when there is no year. One of MISS_KINDS.
    miss: str = MISS_NONE
    # Set when a person entered this by hand. Nothing automatic may
    # overwrite it, which is what makes a correction stick: without it,
    # the next harvest quietly replaces a year that was fixed on purpose.
    fixed: bool = False
    # The day this was last useful, for a prune that does not yet exist.
    # It has to be written from the first record or a future cleanup can
    # only delete blindly.
    seen: int = 0

    @property
    def known(self) -> bool:
        """Whether this record answers anything at all."""
        return self.year is not None or bool(self.genres)

    @property
    def decade(self) -> int | None:
        """The decade this record belongs to, if its year is known."""
        return None if self.year is None else self.year // 10 * 10

    def stale(self, *, today: int | None = None) -> bool:
        """Whether a failed lookup is old enough to be worth retrying.

        A hit never goes stale, because a 1951 recording will still be a
        1951 recording. A miss does: an article can be written, or an
        infobox filled in, in the time since we last asked.
        """
        if self.fixed or not self.miss:
            return False
        now = _today() if today is None else today
        return now - self.seen >= MISS_EXPIRY_DAYS

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Fact:
        """Read one record, defaulting anything an older file lacks."""
        year = data.get("year")
        miss = str(data.get("miss") or MISS_NONE)
        return cls(
            year=int(year) if year is not None else None,
            genres=_genres(data.get("genres") or ()),
            article=str(data.get("article") or ""),
            miss=miss if miss in MISS_KINDS else MISS_NONE,
            fixed=bool(data.get("fixed")),
            seen=int(data.get("seen") or 0),
        )

    def as_dict(self) -> dict[str, Any]:
        """The record as the file holds it, defaults left out.

        Omitting defaults is most of why a record averages 150 bytes
        rather than twice that. A song we know only the year of writes as
        two fields, and a field added later costs nothing on the records
        that do not have it.
        """
        data: dict[str, Any] = {"seen": self.seen}
        if self.year is not None:
            data["year"] = self.year
        if self.genres:
            data["genres"] = list(self.genres)
        if self.article:
            data["article"] = self.article
        if self.miss:
            data["miss"] = self.miss
        if self.fixed:
            data["fixed"] = True
        return data


class FactBook:
    """Every record the engine has learned something about.

    Reads are a dictionary get. Writes mark the book dirty and call the
    caller's hook, which is expected to schedule a delayed save rather
    than write immediately: one batch asks about twenty records in a
    burst and the whole file is rewritten on every save.
    """

    def __init__(
        self,
        records: Mapping[str, Fact] | None = None,
        *,
        on_change: Callable[[], None] | None = None,
    ) -> None:
        """Hold the records given, reporting changes to on_change."""
        self._records: dict[str, Fact] = dict(records or {})
        self._on_change = on_change

    def bind(self, on_change: Callable[[], None]) -> None:
        """Set the hook called whenever a record changes.

        Separate from construction because the hook usually needs the
        book it is saving, so the two cannot be built in one expression.
        """
        self._on_change = on_change

    def __len__(self) -> int:
        """How many records are held."""
        return len(self._records)

    def _changed(self) -> None:
        """Tell the caller something is worth writing."""
        if self._on_change is not None:
            self._on_change()

    def get(self, artist: str, base: str) -> Fact | None:
        """What is known about one record, or None if nothing is."""
        return self._records.get(fact_key(artist, base))

    def needs_lookup(self, artist: str, base: str) -> bool:
        """Whether this record is worth asking about.

        True when nothing is held, or when what is held is a failed
        lookup old enough to retry.
        """
        fact = self.get(artist, base)
        return fact is None or fact.stale()

    def remember(
        self,
        artist: str,
        base: str,
        *,
        year: int | None = None,
        genres: Iterable[str] = (),
        article: str = "",
        miss: str = MISS_NONE,
        fixed: bool = False,
    ) -> Fact:
        """Record what a lookup found, and return what is now held.

        A record set by hand is never overwritten by anything automatic,
        only by another hand-set write. That is the whole point of the
        flag: a year corrected on purpose has to survive the next harvest
        that disagrees with it.
        """
        key = fact_key(artist, base)
        held = self._records.get(key)
        if held is not None and held.fixed and not fixed:
            return self.touch(artist, base) or held
        fact = Fact(
            year=int(year) if year is not None else None,
            genres=_genres(genres),
            article=str(article or ""),
            miss=miss if miss in MISS_KINDS else MISS_NONE,
            fixed=fixed,
            seen=_today(),
        )
        self._records[key] = fact
        self._changed()
        return fact

    def touch(self, artist: str, base: str) -> Fact | None:
        """Note that a record was useful today.

        At most one write per record per day: a lane check consults the
        same records over and over inside one batch, and marking the book
        dirty on every read would rewrite the file for no new knowledge.
        """
        key = fact_key(artist, base)
        fact = self._records.get(key)
        if fact is None:
            return None
        today = _today()
        if fact.seen == today:
            return fact
        fact = replace(fact, seen=today)
        self._records[key] = fact
        self._changed()
        return fact

    def misses(self, kind: str = "") -> list[str]:
        """The records we failed to date, as the keys they are filed under.

        This is the work list for anything built to go and find the
        missing data, and it comes already sorted by the kind of work.
        A key with no article needs its search query helped or an article
        named by hand; a key whose article carried no date is the right
        page with a thin infobox.
        """
        return sorted(
            key
            for key, fact in self._records.items()
            if fact.miss and (not kind or fact.miss == kind)
        )

    def prune(self, days: int) -> int:
        """Drop records not useful in this many days, returning how many.

        Nothing calls this yet and at the measured growth rate nothing
        needs to. It exists because it is only possible at all thanks to
        the day stamp on every record, and a cleanup that has to be
        designed later under pressure is a worse cleanup.
        """
        if days <= 0:
            return 0
        cutoff = _today() - days
        keep = {
            key: fact
            for key, fact in self._records.items()
            if fact.fixed or fact.seen > cutoff
        }
        dropped = len(self._records) - len(keep)
        if dropped:
            self._records = keep
            self._changed()
        return dropped

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> FactBook:
        """Read a whole file, tolerating one that is absent or nonsense.

        A cache is rebuildable, so a record that will not parse is
        dropped rather than raised over. Losing one costs a lookup.
        """
        records: dict[str, Fact] = {}
        for key, raw in ((data or {}).get("records") or {}).items():
            if isinstance(raw, Mapping):
                records[str(key)] = Fact.from_dict(raw)
        return cls(records)

    def as_dict(self) -> dict[str, Any]:
        """The whole book as the file holds it."""
        return {"records": {key: fact.as_dict() for key, fact in self._records.items()}}
