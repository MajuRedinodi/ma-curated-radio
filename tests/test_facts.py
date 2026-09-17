"""What a record holds, and when it is worth asking again."""

from __future__ import annotations

import pytest
from facts import (
    MISS_EXPIRY_DAYS,
    MISS_NO_ARTICLE,
    MISS_NO_DATE,
    Fact,
    FactBook,
    fact_key,
)
from filters import base_title

# Titles arrive already folded, so the tests use them that way. What the
# folding itself does is pinned by the base_title tests in test_filters.
HANK = ("Hank Williams", "hey good lookin")


# --- How a record is filed ---------------------------------------------


def test_key_ignores_artist_case_and_padding() -> None:
    """The same record filed two ways is one record."""
    assert fact_key("Hank Williams", "kaw liga") == fact_key(
        "  hank williams  ", "kaw liga"
    )


def test_key_agrees_with_the_folding_the_engine_does() -> None:
    """The two caches have to land on one entry per record.

    The engine keys its in-memory lane cache on base_title and files
    records here under the same value, so a remaster and an album cut
    share what is known. This is the join between them.
    """
    plain = fact_key("a-ha", base_title("Take on Me"))
    assert fact_key("a-ha", base_title("Take on Me (2015 Remaster)")) == plain
    assert fact_key("a-ha", base_title("Take on Me - Remastered 2015")) == plain


def test_key_keeps_different_songs_apart() -> None:
    """Two songs by one artist are two records."""
    assert fact_key(*HANK) != fact_key("Hank Williams", "kaw liga")


# --- What a record holds -----------------------------------------------


def test_a_year_gives_a_decade() -> None:
    """The lane wants the decade, and the year is what is stored."""
    assert Fact(year=1951).decade == 1950
    assert Fact(year=1949).decade == 1940
    assert Fact(year=2000).decade == 2000


def test_no_year_means_no_decade() -> None:
    """Never a guess. A missing year has to read as unknown."""
    assert Fact().decade is None
    assert Fact(miss=MISS_NO_ARTICLE).decade is None


def test_known_is_true_for_either_half() -> None:
    """Genres alone are still something learned."""
    assert Fact(year=1951).known
    assert Fact(genres=("country",)).known
    assert not Fact().known
    assert not Fact(miss=MISS_NO_DATE).known


def test_genres_are_normalised_as_the_lane_compares_them() -> None:
    """Lower-cased and trimmed, and no further.

    Folding out the punctuation would mean a stored "synth-pop" could
    never match the album tag it is meant to reinforce.
    """
    fact = Fact.from_dict({"genres": [" Synth-Pop ", "COUNTRY", "synth-pop"]})
    assert fact.genres == ("synth-pop", "country")


# --- Reading and writing the file --------------------------------------


def test_a_record_round_trips() -> None:
    """Everything written comes back the same."""
    fact = Fact(
        year=1951,
        genres=("country", "honky-tonk"),
        article="Hey, Good Lookin'",
        fixed=True,
        seen=20_712,
    )
    assert Fact.from_dict(fact.as_dict()) == fact


def test_defaults_are_left_out_of_the_file() -> None:
    """Most of why a record averages 150 bytes rather than twice that."""
    assert Fact(year=1951, seen=20_712).as_dict() == {"year": 1951, "seen": 20_712}


def test_a_field_added_later_reads_as_unknown() -> None:
    """The property that lets the schema grow without a migration.

    A record written before a field existed has to read as not knowing
    it, which is a case the engine already handles everywhere.
    """
    fact = Fact.from_dict({"seen": 20_712})
    assert fact.year is None
    assert fact.genres == ()
    assert fact.article == ""
    assert fact.miss == ""
    assert not fact.fixed


def test_a_field_the_schema_dropped_is_ignored() -> None:
    """The other direction: an older file may hold more than we read."""
    fact = Fact.from_dict({"year": 1951, "chart_peak": 2, "seen": 1})
    assert fact == Fact(year=1951, seen=1)


def test_a_nonsense_miss_reason_reads_as_none() -> None:
    """Only the two recorded kinds mean anything to the work list."""
    assert Fact.from_dict({"miss": "banana"}).miss == ""


def test_a_junk_record_is_dropped_rather_than_raised_over() -> None:
    """A cache is rebuildable, so losing one record costs a lookup."""
    book = FactBook.from_dict(
        {"records": {"good|song": {"year": 1980}, "bad|song": "not a mapping"}}
    )
    assert len(book) == 1
    assert book.get("good", "song") is not None


def test_an_absent_file_gives_an_empty_book() -> None:
    """First run, and the case where the store would not read."""
    assert len(FactBook.from_dict(None)) == 0
    assert len(FactBook.from_dict({})) == 0


def test_a_whole_book_round_trips() -> None:
    """What the store writes is what the store reads back."""
    book = FactBook()
    book.remember(*HANK, year=1951, genres=["country"], article="Hey, Good Lookin'")
    book.remember("Bruno Mars", "24k magic", miss=MISS_NO_DATE, article="24K Magic")
    again = FactBook.from_dict(book.as_dict())
    assert again.as_dict() == book.as_dict()
    assert (fact := again.get(*HANK)) is not None
    assert fact.year == 1951


# --- When a lookup is worth repeating ----------------------------------


def test_a_hit_never_goes_stale() -> None:
    """A 1951 recording will still be a 1951 recording."""
    fact = Fact(year=1951, seen=0)
    assert not fact.stale(today=100_000)


def test_a_miss_goes_stale_on_the_expiry_day() -> None:
    """An article can be written, or an infobox filled in."""
    fact = Fact(miss=MISS_NO_ARTICLE, seen=1_000)
    assert not fact.stale(today=1_000 + MISS_EXPIRY_DAYS - 1)
    assert fact.stale(today=1_000 + MISS_EXPIRY_DAYS)


def test_a_hand_set_record_never_goes_stale() -> None:
    """Nothing automatic gets a second chance to overwrite a correction."""
    fact = Fact(miss=MISS_NO_DATE, fixed=True, seen=0)
    assert not fact.stale(today=100_000)


def test_nothing_known_needs_a_lookup() -> None:
    """The only case where the engine pays for Wikipedia."""
    book = FactBook()
    assert book.needs_lookup(*HANK)
    book.remember(*HANK, year=1951)
    assert not book.needs_lookup(*HANK)


def test_an_old_miss_needs_another_lookup() -> None:
    """Trusted for a month, not forever."""
    old = Fact(miss=MISS_NO_ARTICLE, seen=0)
    book = FactBook({fact_key(*HANK): old})
    assert book.needs_lookup(*HANK)


# --- Hand-set records --------------------------------------------------


def test_a_hand_set_year_survives_a_harvest_that_disagrees() -> None:
    """The mechanism that makes a correction stick."""
    book = FactBook()
    book.remember(*HANK, year=1951, fixed=True)
    book.remember(*HANK, year=1970, article="Some Compilation")
    assert (fact := book.get(*HANK)) is not None
    assert fact.year == 1951
    assert fact.fixed


def test_a_hand_set_record_yields_to_another_hand_set_write() -> None:
    """A correction can be corrected."""
    book = FactBook()
    book.remember(*HANK, year=1949, fixed=True)
    book.remember(*HANK, year=1951, fixed=True)
    assert (fact := book.get(*HANK)) is not None
    assert fact.year == 1951


# --- The day stamp -----------------------------------------------------


def test_a_useful_record_is_stamped_with_today() -> None:
    """What makes a future prune possible at all."""
    book = FactBook()
    written = book.remember(*HANK, year=1951)
    stale = Fact(year=1951, seen=written.seen - 10)
    book = FactBook({fact_key(*HANK): stale})
    assert (touched := book.touch(*HANK)) is not None
    assert touched.seen == written.seen


def test_touching_an_unknown_record_writes_nothing() -> None:
    """Reading about a record we know nothing of is not a change."""
    changes: list[int] = []
    book = FactBook(on_change=lambda: changes.append(1))
    assert book.touch(*HANK) is None
    assert changes == []


def test_a_second_touch_the_same_day_is_not_a_change() -> None:
    """One batch consults the same record repeatedly.

    Marking the book dirty on every read would rewrite the whole file for
    no new knowledge.
    """
    book = FactBook()
    book.remember(*HANK, year=1951)
    changes: list[int] = []
    book.bind(lambda: changes.append(1))
    book.touch(*HANK)
    book.touch(*HANK)
    assert changes == []


def test_a_write_reports_a_change() -> None:
    """Which is what schedules the delayed save."""
    changes: list[int] = []
    book = FactBook(on_change=lambda: changes.append(1))
    book.remember(*HANK, year=1951)
    assert changes == [1]


def test_a_read_reports_nothing() -> None:
    """Lookups are the common case and must not cost a write."""
    book = FactBook()
    book.remember(*HANK, year=1951)
    changes: list[int] = []
    book.bind(lambda: changes.append(1))
    book.get(*HANK)
    book.needs_lookup(*HANK)
    assert changes == []


# --- The work list -----------------------------------------------------


def test_misses_come_back_sorted_by_kind() -> None:
    """Already a work list, because the two kinds want different fixes."""
    book = FactBook()
    book.remember("A", "one", miss=MISS_NO_ARTICLE)
    book.remember("B", "two", miss=MISS_NO_DATE, article="Two")
    book.remember("C", "three", year=1985)
    assert book.misses() == ["a|one", "b|two"]
    assert book.misses(MISS_NO_ARTICLE) == ["a|one"]
    assert book.misses(MISS_NO_DATE) == ["b|two"]


def test_a_record_that_answered_is_not_a_miss() -> None:
    """Including one whose article gave genres but no year."""
    book = FactBook()
    book.remember("A", "one", genres=["country"], miss=MISS_NO_DATE)
    assert book.misses() == ["a|one"]
    book.remember("A", "one", year=1951, genres=["country"])
    assert book.misses() == []


# --- Pruning -----------------------------------------------------------


@pytest.mark.parametrize("days", [0, -1])
def test_pruning_nothing_drops_nothing(days: int) -> None:
    """A guard, so a misconfigured cleanup cannot empty the book."""
    book = FactBook({fact_key(*HANK): Fact(year=1951, seen=0)})
    assert book.prune(days) == 0
    assert len(book) == 1


def test_pruning_drops_what_has_not_been_useful() -> None:
    """Possible only because every record carries the day stamp."""
    fresh = FactBook().remember("Fresh", "song", year=1985)
    book = FactBook(
        {
            "fresh|song": fresh,
            "old|song": Fact(year=1971, seen=fresh.seen - 900),
        }
    )
    assert book.prune(365) == 1
    assert book.get("fresh", "song") is not None
    assert book.get("old", "song") is None


def test_pruning_keeps_a_hand_set_record_however_old() -> None:
    """A correction is not a cache entry."""
    book = FactBook({"old|song": Fact(year=1971, fixed=True, seen=0)})
    assert book.prune(30) == 0
    assert len(book) == 1


def test_pruning_reports_a_change_only_when_it_dropped_something() -> None:
    """No write for a cleanup that found nothing to do."""
    changes: list[int] = []
    book = FactBook(
        {"old|song": Fact(year=1971, seen=0)}, on_change=lambda: changes.append(1)
    )
    assert book.prune(1_000_000) == 0
    assert changes == []
    assert book.prune(30) == 1
    assert changes == [1]


# --- Chart placings, collected and never filtered on --------------------


def test_the_best_placing_is_the_highest_one_anywhere():
    """Lowest number wins: a number one beats a number four."""
    fact = Fact(charts=(("UK", 4), ("US", 1)))
    assert fact.best_chart == ("US", 1)


def test_no_placing_found_is_not_a_claim_that_it_never_charted():
    """Eleven of sixteen canonical records have no peak on Wikipedia,
    "Heartbreak Hotel" among them, so absence has to read as silence."""
    assert Fact(year=1956).best_chart is None


def test_placings_round_trip_through_the_file():
    """JSON gives lists back where tuples went in."""
    fact = Fact(year=1998, charts=(("UK", 24), ("US", 4)), seen=1)
    assert Fact.from_dict(fact.as_dict()) == fact
    assert fact.as_dict()["charts"] == [["UK", 24], ["US", 4]]


def test_placings_are_put_in_a_canonical_order_on_the_way_in():
    """Both ways in sort them, so two records that know the same thing
    compare equal. Building a Fact directly does not, which is a test
    convenience rather than a path anything real takes: the engine goes
    through remember and the store through from_dict."""
    assert Fact.from_dict({"charts": [["US", 4], ["UK", 24]]}).charts == (
        ("UK", 24),
        ("US", 4),
    )
    book = FactBook()
    assert book.remember("a", "b", charts=[("US", 4), ("UK", 24)]).charts == (
        ("UK", 24),
        ("US", 4),
    )


def test_the_best_of_two_placings_on_one_chart_is_kept():
    """An article can list a re-entry at a worse position."""
    assert Fact.from_dict({"charts": [["US", 40], ["US", 4]]}).charts == (("US", 4),)


def test_a_record_with_no_placings_writes_no_charts_field():
    """Defaults stay out of the file, which is most of why a record is
    150 bytes rather than twice that."""
    assert "charts" not in Fact(year=1998, seen=1).as_dict()


def test_junk_placings_are_dropped_rather_than_raised_over():
    """A cache, so a lost placing costs nothing."""
    assert Fact.from_dict({"charts": ["nonsense", ["US"], ["US", "x"], 7]}).charts == ()


def test_placings_are_remembered_alongside_everything_else():
    book = FactBook()
    book.remember(*HANK, year=1951, charts=[("US", 63)])
    assert (fact := book.get(*HANK)) is not None
    assert fact.charts == (("US", 63),)
