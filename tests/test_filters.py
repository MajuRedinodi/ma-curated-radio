"""Filter parity tests.

These mirror the Jinja expressions in the blueprint this integration
replaces, so a behaviour change here is a deliberate one.
"""

import random
from datetime import UTC, datetime, timedelta

import pytest
from filters import (
    base_title,
    clean_similar_artists,
    credits_artist,
    drop_outliers,
    freshness,
    hotness,
    is_holiday,
    is_live,
    is_non_song,
    is_too_short,
    matches_provider,
    sequence,
    sequence_tiered,
    tier_of,
    weighted_sample,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Poker Face", "poker face"),
        ("Poker Face - Remastered 2011", "poker face"),
        ("Poker Face (Radio Edit)", "poker face"),
        ("Poker Face - Live (Bonus)", "poker face"),
        ("  Spaced Out  ", "spaced out"),
    ],
)
def test_base_title_collapses_variants(raw, expected):
    assert base_title(raw) == expected


@pytest.mark.parametrize(
    ("name", "version", "expected"),
    [
        ("Song", "Live at Wembley", True),
        ("Song (Live)", "", True),
        ("Song - Live", "", True),
        # Known false positive, inherited from the YAML: the word is the
        # title. Filtering it costs one song; matching loosely would let
        # every live recording through.
        ("Live and Let Die", "", True),
        ("Alive", "", False),
        ("Living on a Prayer", "", False),
        ("Song", "Remastered", False),
    ],
)
def test_is_live(name, version, expected):
    assert is_live(name, version) is expected


@pytest.mark.parametrize(
    ("name", "version", "album", "expected"),
    [
        ("Santa Baby", "", "", True),
        ("Song", "", "Kylie Christmas", True),
        ("Song", "Xmas Mix", "", True),
        ("The First Noel", "", "", True),
        ("Jingle Bell Rock", "", "", True),
        ("Ordinary Song", "", "Ordinary Album", False),
    ],
)
def test_is_holiday_ignores_season(name, version, album, expected):
    assert is_holiday(name, version, album) is expected


def test_clean_similar_artists_drops_collabs_and_seed():
    names = [
        ("Lady Gaga", 0.9),
        ("Bruno Mars", 0.8),
        ("Lady Gaga, Bruno Mars", 0.7),
        ("Simon & Garfunkel", 0.6),
        ("", 0.5),
        ("Bruno Mars", 0.4),
    ]
    assert [name for name, _ in clean_similar_artists(names, "Lady Gaga")] == [
        "Bruno Mars"
    ]


@pytest.mark.parametrize(
    ("uri", "filt", "expected"),
    [
        ("tidal://track/123", "", True),
        ("tidal://track/123", "tidal", True),
        ("qobuz://track/123", "tidal", False),
        ("qobuz://track/123", "tidal, qobuz", True),
        ("library://track/9", "tidal", False),
    ],
)
def test_matches_provider(uri, filt, expected):
    assert matches_provider(uri, filt) is expected


def test_sequence_round_robins_when_artists_are_even():
    assert sequence([["s1", "s2"], ["a1", "a2"], ["b1", "b2"]]) == [
        "s1",
        "a1",
        "b1",
        "s2",
        "a2",
        "b2",
    ]


def test_sequence_caps_consecutive_from_one_artist():
    # A seed-heavy batch: the surplus is spread, never three in a row.
    ordered = sequence([["s1", "s2", "s3", "s4"], ["a1", "a2"]], max_consecutive=2)
    assert ordered == ["s1", "s2", "a1", "s3", "s4", "a2"]
    assert _longest_run(ordered) == 2


def test_sequence_plays_the_tail_rather_than_dropping_it():
    # Only the blocked artist is left; playing them beats losing tracks.
    ordered = sequence([["s1", "s2", "s3", "s4"], ["a1"]], max_consecutive=2)
    assert sorted(ordered) == ["a1", "s1", "s2", "s3", "s4"]


def test_sequence_honours_a_stricter_cap():
    ordered = sequence([["s1", "s2", "s3"], ["a1", "a2", "a3"]], max_consecutive=1)
    assert _longest_run(ordered) == 1


def test_sequence_handles_nothing():
    assert sequence([]) == []
    assert sequence([[], []]) == []


def _longest_run(ordered: list[str]) -> int:
    """Longest run of items sharing a leading letter (their artist)."""
    longest = run = 0
    previous = None
    for item in ordered:
        run = run + 1 if item[0] == previous else 1
        previous = item[0]
        longest = max(longest, run)
    return longest


@pytest.mark.parametrize(
    ("duration", "minimum", "expected"),
    [
        (38, 90, True),
        (30, 90, True),
        (67, 90, True),
        (178, 90, False),
        (90, 90, False),
        # Zero means the provider did not say; assume it is a song.
        (0, 90, False),
        (30, 0, False),
    ],
)
def test_is_too_short(duration, minimum, expected):
    assert is_too_short(duration, minimum) is expected


@pytest.mark.parametrize(
    ("name", "version", "expected"),
    [
        ("Wi$h Li$t (Track by Track)", "", True),
        ("Wood", "Track by Track", True),
        ("Something", "Commentary", True),
        ("Interlude II", "", True),
        ("Cruel Summer", "", False),
        ("Shake It Off", "Remastered", False),
    ],
)
def test_is_non_song(name, version, expected):
    assert is_non_song(name, version) is expected


def test_weighted_sample_favours_the_best_match():
    """The whole point: a deep pool must not be sampled flat.

    Sampling uniformly from Last.fm's tail is what filled batches with
    defensible artists nobody recognised.
    """
    pool = [("Close", 1.0), ("Middling", 0.4), ("Distant", 0.05)]
    counts = {"Close": 0, "Middling": 0, "Distant": 0}
    random.seed(11)
    for _ in range(600):
        counts[weighted_sample(pool, 1, 2.0)[0]] += 1
    assert counts["Close"] > counts["Middling"] > counts["Distant"]
    assert counts["Close"] > 400


def test_weighted_sample_still_reaches_the_tail():
    """Biased, not deterministic. The far end has to stay possible.

    This is why the exponent is kept low. A steeper curve makes the tail
    unreachable rather than rare, which would make the deep pool pointless.
    """
    pool = [("Close", 1.0), ("Distant", 0.3)]
    random.seed(3)
    picks = {weighted_sample(pool, 1, 2.0)[0] for _ in range(400)}
    assert picks == {"Close", "Distant"}


def test_zero_exponent_is_a_flat_shuffle():
    pool = [("A", 1.0), ("B", 0.01)]
    random.seed(5)
    counts = {"A": 0, "B": 0}
    for _ in range(400):
        counts[weighted_sample(pool, 1, 0.0)[0]] += 1
    assert 150 < counts["A"] < 250


def test_weighted_sample_returns_distinct_artists():
    pool = [("A", 1.0), ("B", 0.9), ("C", 0.8), ("D", 0.7)]
    random.seed(7)
    picked = weighted_sample(pool, 3, 2.0)
    assert len(picked) == 3
    assert len(set(picked)) == 3


def test_weighted_sample_handles_empty_and_zero():
    assert weighted_sample([], 3, 2.0) == []
    assert weighted_sample([("A", 1.0)], 0, 2.0) == []
    # A zero match must not divide by zero.
    assert weighted_sample([("A", 0.0)], 1, 2.0) == ["A"]


def test_clean_similar_artists_keeps_match_scores():
    cleaned = clean_similar_artists(
        [("Bruno Mars", 0.8), ("Lady Gaga, Bruno Mars", 0.7), ("Lady Gaga", 0.9)],
        "Lady Gaga",
    )
    assert cleaned == [("Bruno Mars", 0.8)]


NOW = datetime(2026, 9, 7, tzinfo=UTC)


@pytest.mark.parametrize(
    ("age_days", "expected"),
    [(0, 1.0), (60, 0.5), (120, 0.0), (300, 0.0)],
)
def test_freshness_decays_across_the_window(age_days, expected):
    released = NOW - timedelta(days=age_days)
    assert freshness(released, 120, NOW) == pytest.approx(expected, abs=0.01)


def test_freshness_is_zero_without_a_release_date():
    """A provider that reports nothing must not trigger any promotion."""
    assert freshness(None, 120, NOW) == 0.0


def test_freshness_is_zero_when_disabled():
    assert freshness(NOW, 0, NOW) == 0.0


def test_hot_new_track_outscores_an_old_one():
    """The Olivia Rodrigo case: new and big should beat old and big."""
    new_hit = hotness(NOW - timedelta(days=10), 90, 120, NOW)
    old_hit = hotness(NOW - timedelta(days=900), 100, 120, NOW)
    assert new_hit > old_hit == 0.0


def test_new_flop_is_not_promoted():
    """New alone is not enough; it has to be popular too."""
    assert hotness(NOW - timedelta(days=5), 0, 120, NOW) == 0.0


def test_hotness_needs_both_signals():
    assert hotness(None, 100, 120, NOW) == 0.0
    assert hotness(NOW, 0, 120, NOW) == 0.0
    assert hotness(NOW, 100, 120, NOW) == pytest.approx(1.0)


@pytest.mark.parametrize(
    ("credited", "wanted", "expected"),
    [
        (["Lady Gaga", "Colby O'Donis"], "Lady Gaga", True),
        (["Lady Gaga"], "lady gaga", True),
        # The real failure: right words, wrong record.
        (["Rosanna Rocci"], "Madonna", False),
        (["Bob Seger & The Silver Bullet Band"], "Bob Seger", False),
        ([], "Madonna", False),
        (["Anyone"], "", True),
    ],
)
def test_credits_artist(credited, wanted, expected):
    assert credits_artist(credited, wanted) is expected


def test_sequence_counts_the_track_it_follows():
    """A pick and the two after it must not be three by one artist.

    Observed: picking ELO's "Mr. Blue Sky" opened the batch with two more
    ELO tracks. Every step was legal on its own, because the batch could
    not see what it was being played after.
    """
    elo = {"elo1", "elo2", "elo3"}
    pools = [["elo1", "elo2", "elo3"], ["other1"], ["other2"]]

    # The pick counts as one, so exactly one more may follow it.
    seamed = sequence(pools, 2, leading=0)
    assert seamed[0] in elo
    assert seamed[1] not in elo

    # Standing alone, the same pool may open with two of its own.
    plain = sequence(pools, 2)
    assert plain[0] in elo
    assert plain[1] in elo


def test_sequence_leading_still_returns_everything():
    pools = [["a1", "a2", "a3"], ["b1"], ["c1"]]
    assert sorted(sequence(pools, 2, leading=0)) == ["a1", "a2", "a3", "b1", "c1"]


def test_floor_drops_an_artist_far_below_its_own_pool():
    """Christine McVie, the one real defect across four observed pools.

    Her biggest track is 2% of that pool's median. The next lowest
    artist in any observed pool was 12%, so 10% sits in open space.
    """
    pool = [
        ("Fleetwood Mac", 2103659),
        ("America", 1608474),
        ("Stevie Nicks", 715395),
        ("Christine McVie", 28061),
    ]
    keep, dropped = drop_outliers(pool, 10)
    assert keep == ["Fleetwood Mac", "America", "Stevie Nicks"]
    assert dropped == [("Christine McVie", 28061)]


def test_floor_keeps_a_small_artist_in_a_small_genre():
    """Hank Williams Jr. is tiny globally and normal for his pool.

    Last.fm undercounts country by about ten times, so an absolute floor
    would erase the genre. Measured against the pool's own median he sits
    at 28%, comfortably above a floor that drops Christine McVie at 2%.
    """
    pool = [
        ("The Highwaymen", 380679),
        ("David Allan Coe", 136180),
        ("Johnny Paycheck", 128366),
        ("Hank Williams Jr.", 38490),
    ]
    keep, dropped = drop_outliers(pool, 10)
    assert dropped == []
    assert len(keep) == 4


def test_floor_leaves_a_small_pool_alone():
    tiny = [("A", 100000), ("B", 500)]
    assert drop_outliers(tiny, 10) == (["A", "B"], [])


def test_floor_never_drops_an_artist_of_unknown_size():
    """A Last.fm miss should cost variety, not silently narrow the pool."""
    pool = [("A", 100000), ("B", 90000), ("C", 80000), ("Unknown", 0)]
    keep, dropped = drop_outliers(pool, 10)
    assert "Unknown" in keep
    assert dropped == []


def test_tiers_are_relative_so_a_small_genre_still_gets_power_tracks():
    """An all-country pool must not come out entirely Deep."""
    pool = [
        ("The Highwaymen", ["hw1", "hw2"], 380679),
        ("David Allan Coe", ["dac1", "dac2"], 136180),
        ("Johnny Paycheck", ["jp1", "jp2"], 128366),
        ("Hank Williams Jr.", ["hank1", "hank2"], 38490),
    ]
    tiers = tier_of(pool, 0.7)
    assert "P" in tiers.values()
    assert "D" in tiers.values()
    assert tiers["hw1"] == "P"


def test_tiered_order_spreads_the_big_tracks_across_the_hour():
    """Round-robin front-loads; the pattern should not."""
    lists = [["a1", "a2"], ["b1", "b2"], ["c1", "c2"], ["d1", "d2"]]
    tiers = {
        "a1": "P", "b1": "P", "c1": "S", "d1": "S",
        "a2": "S", "b2": "D", "c2": "D", "d2": "D",
    }
    out = sequence_tiered(lists, tiers, ["P", "D", "S"])
    assert len(out) == 8
    assert sorted(out) == sorted(sum(lists, []))
    # A Power track should not be stranded in the final third.
    assert tiers[out[0]] == "P"


def test_tiered_order_still_honours_the_seam_and_the_run_cap():
    lists = [["a1", "a2", "a3"], ["b1"], ["c1"]]
    tiers = dict.fromkeys(("a1", "a2", "a3", "b1", "c1"), "P")
    out = sequence_tiered(lists, tiers, ["P"], max_consecutive=2, leading=0)
    assert out[1] not in ("a1", "a2", "a3")


def test_unknown_artist_size_is_typical_not_worst():
    """A missed lookup must not file an artist as the weakest in the pool.

    The artist most likely to be missing is the one just picked, and the
    original scoring put every track of an unknown artist in the Deep
    tier, so the station would have treated what was asked for as its
    weakest material.
    """
    pool = [
        ("Big", ["big1", "big2"], 2000000),
        ("Mid", ["mid1", "mid2"], 500000),
        ("Small", ["small1", "small2"], 100000),
        ("Unknown", ["unk1", "unk2"], 0),
    ]
    tiers = tier_of(pool, 0.7)
    assert tiers["unk1"] != "D"
    assert tiers["big1"] == "P"


def test_tiering_survives_a_pool_with_no_sizes_at_all():
    """No Last.fm key, or a total outage: fall back to track position."""
    pool = [("A", ["a1", "a2"], 0), ("B", ["b1", "b2"], 0)]
    tiers = tier_of(pool, 0.7)
    assert len(tiers) == 4
    assert set(tiers.values()) <= {"P", "S", "D"}


def test_length_cap_separates_depth_from_how_long_the_hour_is():
    """Drawing deeper must not lengthen the batch.

    Tracks per artist used to do both jobs, so reaching an artist's third
    track also took a batch from 19 tracks to 29, and a longer batch
    reseeds less often.
    """
    lists = [["a1", "a2", "a3"], ["b1", "b2", "b3"], ["c1", "c2", "c3"]]
    tiers = {
        "a1": "P", "b1": "P", "c1": "P",
        "a2": "S", "b2": "S", "c2": "S",
        "a3": "D", "b3": "D", "c3": "D",
    }
    assert len(sequence_tiered(lists, tiers, ["P", "D", "S"], length=6)) == 6
    assert len(sequence_tiered(lists, tiers, ["P", "D", "S"])) == 9
    # A cap longer than the pool is not padding.
    assert len(sequence_tiered(lists, tiers, ["P", "D", "S"], length=99)) == 9


def test_a_capped_batch_spreads_across_artists_not_onto_the_biggest_pool():
    """The seed draws most, so favouring the fullest pool would feed it.

    Uncapped the fullest-pool rule stops tracks being stranded. Capped it
    only decides who gets the spare slots, and handing them to whoever
    drew most concentrates a batch on the seed.
    """
    lists = [["s1", "s2", "s3", "s4", "s5"], ["b1", "b2"], ["c1", "c2"]]
    tiers = dict.fromkeys(
        ("s1", "s2", "s3", "s4", "s5", "b1", "b2", "c1", "c2"), "P"
    )
    out = sequence_tiered(lists, tiers, ["P"], length=6)
    seed_share = sum(1 for uri in out if uri.startswith("s"))
    assert seed_share <= 3
