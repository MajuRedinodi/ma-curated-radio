"""Filter parity tests.

These mirror the Jinja expressions in the blueprint this integration
replaces, so a behaviour change here is a deliberate one.
"""

import random
from datetime import UTC, datetime, timedelta

import pytest
from filters import (
    TIER_POWER,
    base_title,
    clean_similar_artists,
    close_to_home,
    credits_artist,
    depth_bar,
    drop_outliers,
    freshness,
    hotness,
    is_holiday,
    is_live,
    is_non_song,
    is_too_short,
    keep_one_act,
    lead_among_credits,
    lean_toward_strength,
    matches_provider,
    move_on,
    neighbourhood_strength,
    reach_of,
    sequence_tiered,
    strong_artists,
    tier_of,
    too_deep,
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
        # A backing band is the same act. This asserted False until a live
        # batch showed what that costs: Last.fm asked for "Tom Petty and
        # The Heartbreakers", Tidal credits plain "Tom Petty", and the
        # artist contributed nothing at all to the batch.
        (["Bob Seger & The Silver Bullet Band"], "Bob Seger", True),
        ([], "Madonna", False),
        (["Anyone"], "", True),
    ],
)
def test_credits_artist(credited, wanted, expected):
    assert credits_artist(credited, wanted) is expected



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


def test_reach_is_absolute_so_batches_compare_across_pools():
    """Tiers are relative to their own pool and say nothing across pools.

    An observed rock batch ran near 900,000 and a singer-songwriter batch
    at identical settings near 240,000, which is the difference between
    depth being free and depth being too much.
    """
    big = [("Boston", ["b1", "b2"], 1800000)]
    small = [("Shelby Lynne", ["s1", "s2"], 150000)]
    assert reach_of(big, 0.7)["b1"] > reach_of(small, 0.7)["s1"]
    # Position within an artist decays it.
    assert reach_of(big, 0.7)["b2"] < reach_of(big, 0.7)["b1"]


def test_reach_uses_the_pool_median_for_an_unknown_artist():
    pool = [
        ("A", ["a1"], 400000),
        ("B", ["b1"], 500000),
        ("C", ["c1"], 600000),
        ("Unknown", ["u1"], 0),
    ]
    reach = reach_of(pool, 0.7)
    assert reach["u1"] == 500000


def test_a_backing_band_may_be_present_or_absent():
    """Last.fm and a provider disagree about writing the band in.

    Observed live: Last.fm returned "Tom Petty and The Heartbreakers",
    Tidal credits plain "Tom Petty", and the exact comparison rejected
    every track so the artist contributed nothing at all to a batch.
    """
    assert credits_artist(["Tom Petty"], "Tom Petty and The Heartbreakers")
    assert credits_artist(["Tom Petty and The Heartbreakers"], "Tom Petty")
    assert credits_artist(["Stevie Nicks", "Tom Petty"], "Tom Petty & The Heartbreakers")


def test_two_acts_sharing_a_prefix_are_still_different_acts():
    """Prefix matching would be the obvious generalisation and is wrong."""
    assert not credits_artist(["The Band Perry"], "The Band")
    assert not credits_artist(["The Band"], "The Band Perry")


def test_the_wrong_record_with_the_right_words_is_still_rejected():
    """Searching Madonna returned "Madonna Madonna" by Rosanna Rocci."""
    assert not credits_artist(["Rosanna Rocci"], "Madonna")


def test_a_concert_recording_is_a_live_recording():
    """The Band's "Helpless (Concert Version)", from The Last Waltz,
    reached a queue with live filtering switched on."""
    assert is_live("Helpless (Concert Version)", "")
    assert is_live("Helpless", "Concert Version")
    assert is_live("Layla", "Unplugged")


def test_a_song_that_merely_sounds_live_is_not_filtered():
    assert not is_live("Alive", "")
    assert not is_live("Living on a Prayer", "")
    assert not is_live("Concrete and Clay", "")


def test_a_classical_piece_is_the_same_piece_with_a_tempo_marking():
    """Brahms' Hungarian Dance No 5 reached one queue twice.

    Classical releases append a movement or tempo to the title with a
    comma, and abbreviate "No." inconsistently.
    """
    assert base_title("Hungarian Dance No 5") == base_title(
        "Hungarian Dance No. 5, Allegro molto"
    )
    assert base_title("Symphony No. 7") == base_title("Symphony No 7, Allegretto")


def test_a_comma_in_a_pop_title_is_left_alone():
    """Splitting on the comma would collapse these onto each other."""
    assert base_title("Hello, Goodbye") != base_title("Hello")
    assert base_title("Rock Me, Baby") != base_title("Rock Me")


def test_the_run_cap_can_be_tightened_to_one():
    """Ported from the round-robin sequencer this replaced."""
    pools = [["s1", "s2", "s3"], ["a1", "a2", "a3"]]
    tiers = dict.fromkeys(("s1", "s2", "s3", "a1", "a2", "a3"), "P")
    ordered = sequence_tiered(pools, tiers, ["P"], max_consecutive=1)
    assert all(ordered[i] != ordered[i + 1] for i in range(len(ordered) - 1))
    assert sorted(ordered) == ["a1", "a2", "a3", "s1", "s2", "s3"]


def test_the_cap_gives_way_rather_than_dropping_tracks():
    """When only the blocked artist has anything left, it plays.

    The cap is a preference, not a guarantee: playing three in a row
    beats ending an hour early.
    """
    pools = [["s1", "s2", "s3", "s4"], ["a1"]]
    tiers = dict.fromkeys(("s1", "s2", "s3", "s4", "a1"), "P")
    ordered = sequence_tiered(pools, tiers, ["P"], max_consecutive=2)
    assert len(ordered) == 5


def test_an_empty_pool_orders_nothing():
    assert sequence_tiered([], {}, ["P"]) == []
    assert sequence_tiered([[], []], {}, ["P"]) == []


def test_reseeding_uses_the_stronger_half_of_a_batch():
    """A refill must not ratchet a station into obscurity.

    Observed: a Carole King batch at 759,000 median reach reseeded to
    Janis Ian at 338,000, whose own pool was Eva Cassidy and Steve
    Forbert. A big artist's neighbours are mostly smaller than it, so
    reseeding off whichever happens to be playing steps down more often
    than up.
    """
    batch = [
        ("Carole King", 900000),
        ("Paul Simon", 1200000),
        ("Carly Simon", 700000),
        ("Janis Ian", 338000),
        ("Judy Collins", 200000),
    ]
    strong = strong_artists(batch)
    assert "Paul Simon" in strong
    assert "Janis Ian" not in strong
    assert "Judy Collins" not in strong


def test_reseeding_keeps_more_than_one_candidate():
    """Always taking the biggest would pin a station to one artist."""
    batch = [("A", 900000), ("B", 800000), ("C", 700000), ("D", 100000)]
    assert len(strong_artists(batch)) > 1


def test_an_artist_of_unknown_size_stays_a_candidate():
    batch = [("A", 900000), ("B", 100000), ("Unknown", 0)]
    assert "Unknown" in strong_artists(batch)


def test_reseeding_from_nothing_returns_nothing():
    assert strong_artists([]) == []


@pytest.mark.parametrize(
    ("name", "album"),
    [
        # Reached a September queue past the original token list, which
        # only knew the word "Christmas". Neither the title nor the album
        # contains it.
        ("Winter Wonderland", "The Best Man Holiday: Original Motion Picture"),
        ("Let It Snow! Let It Snow! Let It Snow!", "A Jolly Collection"),
        ("Sleigh Ride", "Seasonal Favourites"),
        ("The Little Drummer Boy", "Carols"),
        ("Auld Lang Syne", "New Year"),
        ("Silent Night", "Hymns"),
        ("Rockin' Around the Christmas Tree", "Greatest Hits"),
    ],
)
def test_holiday_standards_are_caught_without_the_word_christmas(name, album):
    assert is_holiday(name, "", album)


@pytest.mark.parametrize(
    ("name", "album"),
    [
        # The single words that would catch the songs above are exactly
        # the words ordinary songs use.
        ("Winter", "Boys for Pele"),
        ("A Hazy Shade of Winter", "Bookends"),
        ("Chasing Cars", "Eyes Open"),
        ("Holiday", "American Idiot"),
        ("Holiday Road", "National Lampoon's Vacation"),
        ("Hell's Bells", "Back in Black"),
        ("Ring My Bell", "Anita Ward"),
    ],
)
def test_ordinary_songs_are_not_mistaken_for_holiday_music(name, album):
    assert not is_holiday(name, "", album)


# --- Where a refill reseeds from -----------------------------------------

DEGREES = {
    "sam smith": 0,
    "adele": 1,
    "calum scott": 1,
    "christina aguilera": 2,
    "jessie j": 3,
}


def test_a_refill_prefers_the_strong_artists_nearest_home():
    """A Sam Smith station reseeded from Christina Aguilera.

    She was big enough for the stronger half and sits at its 2000s-pop
    edge, and the next hour was Jessie J, JoJo, Lindsay Lohan and Ashley
    Tisdale.
    """
    strong = ["Christina Aguilera", "Adele", "Calum Scott"]
    chosen = close_to_home(strong, lambda a: DEGREES.get(a.lower()), fenced=True)
    assert set(chosen) == {"Adele", "Calum Scott"}


def test_two_steps_out_is_used_when_nobody_is_one_step_out():
    strong = ["Christina Aguilera", "Jessie J"]
    chosen = close_to_home(strong, lambda a: DEGREES.get(a.lower()), fenced=True)
    assert chosen == ["Christina Aguilera"]


def test_a_station_that_has_travelled_still_reseeds_from_somewhere():
    """A preference, not a filter: nobody close is not nobody at all."""
    strong = ["Jessie J", "Somebody Unmapped"]
    chosen = close_to_home(strong, lambda a: DEGREES.get(a.lower()), fenced=True)
    assert chosen == strong


def test_discovery_is_left_to_wander():
    strong = ["Christina Aguilera", "Adele"]
    chosen = close_to_home(strong, lambda a: DEGREES.get(a.lower()), fenced=False)
    assert chosen == strong


def test_the_origin_itself_counts_as_home():
    strong = ["Sam Smith", "Christina Aguilera"]
    chosen = close_to_home(strong, lambda a: DEGREES.get(a.lower()), fenced=True)
    assert chosen == ["Sam Smith"]


def test_a_refill_moves_on_from_the_artist_who_led_the_last_hour():
    """A Texas Hold 'Em station refilled from Beyoncé again.

    Preferring artists near the origin made the origin itself the nearest,
    and the refill was a near copy of the hour before: six of its nine
    artists were Beyoncé, her group, her family or her label.
    """
    strong = ["Beyoncé", "Rihanna", "Janet Jackson"]
    assert "Beyoncé" not in move_on(strong, "Beyoncé")


def test_the_last_lead_stays_when_nobody_else_is_left():
    """Repeating beats stopping."""
    assert move_on(["Beyoncé"], "Beyoncé") == ["Beyoncé"]


def test_nothing_is_dropped_on_the_first_refill_after_a_restart():
    assert move_on(["A", "B"], "") == ["A", "B"]


def test_a_deeper_song_reaches_less_even_when_it_leads_its_batch():
    """Songs already played are excluded before a batch is chosen.

    Counting positions within the batch scored an artist's fourth song as
    though it were their first, so a refill of the same artists' deeper
    songs reported exactly the median reach of the hits before it.
    """
    pool = [("Beyoncé", ["fourth", "fifth"], 1_000_000)]
    naive = reach_of(pool, 0.7)
    honest = reach_of(pool, 0.7, {"fourth": 3, "fifth": 4})
    assert naive["fourth"] == 1_000_000
    assert honest["fourth"] < naive["fourth"]
    assert honest["fifth"] < honest["fourth"]


def test_true_rank_also_decides_the_tiers():
    """A big artist's fifth song should not out-tier a small artist's hit."""
    pool = [
        ("Big", ["big-5th"], 1_000_000),
        ("Small", ["small-1st"], 200_000),
        ("Mid", ["mid-1st"], 500_000),
    ]
    tiers = tier_of(pool, 0.7, {"big-5th": 5, "small-1st": 0, "mid-1st": 0})
    assert tiers["mid-1st"] == TIER_POWER
    assert tiers["big-5th"] != TIER_POWER


# --- Which credited artist leads a pick ----------------------------------


def test_a_footnote_first_credit_hands_the_lead_to_the_star():
    """Different Drum, credited to Stone Poneys and Linda Ronstadt.

    Built around the first credit it gave three obscure 1967 album cuts at
    8,278 listeners and none of her hits.
    """
    sizes = {"Stone Poneys": 8_278, "Linda Ronstadt": 1_200_000}
    assert lead_among_credits("Stone Poneys", sizes, 697_141) == "Linda Ronstadt"


def test_a_duo_known_by_its_first_name_keeps_it():
    """The Beat Goes On: Cher is bigger, but Sonny is how the duo is known.

    Handing the lead to the biggest credit would put Believe into a 1967
    hour.
    """
    sizes = {"Sonny": 181_000, "Cher": 3_000_000}
    assert lead_among_credits("Sonny", sizes, 528_000) == "Sonny"


def test_without_a_pair_audience_the_first_credit_stands():
    assert lead_among_credits("A", {"A": 10, "B": 1_000_000}, 0) == "A"


# --- Leaning a reseed toward strong neighbourhoods -----------------------


def test_a_neighbourhood_is_measured_by_the_pool_it_would_bring():
    """Boney M. was big; its neighbours were Dschinghis Khan and Fancy."""
    sizes = {"Dschinghis Khan": 200_000, "Fancy": 90_000, "Ottawan": 150_000}
    assert neighbourhood_strength(["Dschinghis Khan", "Fancy", "Ottawan"], sizes) == 150_000


def test_unknown_neighbours_are_left_out_not_counted_as_nothing():
    sizes = {"A": 1_000_000, "B": 0}
    assert neighbourhood_strength(["A", "B", "C"], sizes) == 1_000_000


def test_a_reseed_leans_toward_the_stronger_neighbourhood():
    """Weighted, so the strong one wins most of the time but not always."""
    strengths = {"Fleetwood Mac": 3_000_000, "Boney M.": 150_000}
    rng = random.Random(7)
    picks = [
        lean_toward_strength(["Fleetwood Mac", "Boney M."], strengths, rng)
        for _ in range(200)
    ]
    assert picks.count("Fleetwood Mac") > 150
    assert "Boney M." in picks


def test_a_single_candidate_is_simply_chosen():
    assert lean_toward_strength(["Only"], {}, random.Random(1)) == "Only"


class _Song:
    """Just enough of a track for the depth and namesake rules."""

    def __init__(self, uri, name, artists=(), artist_uris=()):
        self.uri = uri
        self.name = name
        self.artists = list(artists)
        self.artist_uris = list(artist_uris)


def test_the_depth_bar_follows_the_station():
    """A share of the typical artist, so country is not held to rock's numbers."""
    rock = {"REO Speedwagon": 1_287_000, "Pat Benatar": 1_488_000, "Loverboy": 703_000}
    assert depth_bar(rock) == 64_350
    assert depth_bar({"Unknown": 0}) == 0


# Shaped like the real Last.fm numbers: the Beatles' tail stays huge, Mr.
# Mister fall off a cliff after their second song.
_BEATLES = [
    ("Here Comes the Sun - Remastered 2009", 1_592_000),
    ("Let It Be", 1_423_000),
    ("Blackbird", 914_000),
    ("Eleanor Rigby", 816_000),
]
_MR_MISTER = [("Broken Wings", 576_000), ("Kyrie", 224_000), ("Third Song", 40_000)]


def _ranked(titles):
    songs = [_Song(f"t:{i}", title) for i, title in enumerate(titles)]
    return songs, {song.uri: i for i, song in enumerate(songs)}


def test_a_giant_keeps_its_deep_hits():
    songs, rank = _ranked(["Here Comes the Sun", "Let It Be", "Blackbird", "Eleanor Rigby"])
    assert too_deep(songs, rank, _BEATLES, 100_000, 2) == set()


def test_a_mid_sized_act_stops_at_its_hits():
    songs, rank = _ranked(["Broken Wings", "Kyrie", "Third Song", "Uncredited B-side"])
    assert too_deep(songs, rank, _MR_MISTER, 100_000, 2) == {"t:2", "t:3"}


def test_a_tracks_are_always_allowed_even_below_the_bar():
    """A small act on a big station still gets its own biggest songs."""
    small = [("Family Tradition", 38_000), ("A Country Boy Can Survive", 32_000)]
    songs, rank = _ranked(["Born to Boogie", "A Country Boy Can Survive", "Family Tradition"])
    # The first two by the provider's order, the third by Last.fm's.
    assert too_deep(songs, rank, small, 100_000, 2) == set()


def test_nothing_is_cut_without_numbers():
    """A Last.fm outage must not empty the station."""
    songs, rank = _ranked(["One", "Two", "Three"])
    assert too_deep(songs, rank, None, 100_000, 1) == set()
    assert too_deep(songs, rank, [], 100_000, 1) == set()
    assert too_deep(songs, rank, _MR_MISTER, 0, 1) == set()


def test_a_namesake_is_left_out():
    """The .38 Special search that returned a scream metal demo."""
    real = [
        _Song(f"r:{i}", f"Hit {i}", [".38 Special"], ["tidal://artist/1"])
        for i in range(6)
    ]
    other = _Song("o:1", "F2D", [".38 Special"], ["tidal://artist/99"])
    assert keep_one_act([*real, other], ".38 Special") == real


def test_an_even_split_is_left_alone():
    """No clear majority, so there is nothing to say which act was meant."""
    one = [_Song(f"a:{i}", "A", ["Name"], ["id:1"]) for i in range(3)]
    two = [_Song(f"b:{i}", "B", ["Name"], ["id:2"]) for i in range(3)]
    assert keep_one_act([*one, *two], "Name") == [*one, *two]


def test_tracks_without_ids_are_kept():
    songs = [_Song(f"r:{i}", "A", ["Act"], ["id:1"]) for i in range(4)]
    stray = _Song("s", "B", ["Act"], [])
    namesake = _Song("n", "C", ["Act"], ["id:2"])
    assert keep_one_act([*songs, stray, namesake], "Act") == [*songs, stray]
