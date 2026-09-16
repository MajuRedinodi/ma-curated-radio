"""Filtering rules.

Each test is pinned to a real song: one that reached somebody's evening
and should not have, or one that was kept out and should not have been.
The names in these tests are the specification.
"""

import random

import pytest
from filters import (
    TIER_DEEP,
    TIER_POWER,
    base_title,
    clean_similar_artists,
    close_to_home,
    credits_artist,
    depth_bar,
    drop_outliers,
    is_demo,
    is_holiday,
    is_live,
    is_non_song,
    is_remix,
    is_too_short,
    keep_one_act,
    lead_among_credits,
    lean_toward_strength,
    matches_provider,
    move_on,
    neighbourhood_strength,
    reach_of,
    sequence_tiered,
    song_shares,
    strong_artists,
    tier_of,
    too_deep,
    weighted_sample,
    without_backing_band,
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
        # Songs that are simply called what they are called. Judging the
        # whole title condemned all of these while live filtering was on
        # by default.
        ("Live and Let Die", "", False),
        ("Live Wire", "", False),
        ("Live to Tell", "", False),
        ("Live Forever", "", False),
        ("Alive", "", False),
        ("Living on a Prayer", "", False),
        ("(Forever) Live And Die", "", False),
        ("Song", "Remastered", False),
        # A venue that opens a title is a concert only when the song's
        # own name follows it. Requiring nothing after it read ordinary
        # titles as recordings, and Portugal. The Man's second biggest
        # song could not be queued at all.
        (
            "Live at the Olympia - Paris, France (October 10, 1969) - Dazed",
            "",
            True,
        ),
        ("Live at Tomorrowland 2026 (Freedom Stage) - Some Song", "", True),
        ("Live in the Moment", "", False),
        ("Live On Forever", "", False),
        ("Live in the Sky", "", False),
        ("Live From Space", "", False),
        # Live in the languages the catalogue is not in English.
        ("Cancion (En Vivo)", "", True),
        ("Musica - Ao Vivo", "", True),
        ("Cancion", "En Directo", True),
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
        # Records that sit near the top of an artist's provider results
        # and say nothing about the season. All four opened a station in
        # September.
        ("Fairytale of New York", "", "If I Should Fall from Grace", True),
        ("Underneath the Tree", "", "Wrapped In Red", True),
        ("It's the Most Wonderful Time of the Year", "", "Andy Williams", True),
        ("Happy Holiday / The Holiday Season", "", "Andy Williams", True),
        ("Little Saint Nick", "", "", True),
        ("Mele Kalikimaka", "", "", True),
        ("Grandma Got Run Over by a Reindeer", "", "", True),
        ("Stille Nacht", "", "Weihnachten", True),
        ("O Tannenbaum", "", "Weihnachten", True),
        ("Mary's Boy Child / Oh My Lord", "", "Boney M.", True),
        ("Angels We Have Heard on High", "", "Carols", True),
        ("Do You Hear What I Hear?", "", "Carols", True),
        # But not Scott Walker, which is why the token is not "boy child".
        ("Boy Child", "", "Scott 4", False),
        # Punctuation the two services spell differently. Each of these
        # was caught only when the album name happened to say Christmas.
        ("Baby, It's Cold Outside", "", "The Merriest Time Of The Year", True),
        ("Hark! The Herald Angels Sing", "", "Sinatra", True),
        ("O Come, All Ye Faithful", "", "Carols", True),
        ("The First Noël", "", "Carols", True),
        # Says Christmas, is not Christmas. Sakamoto's is the piece he is
        # best known for and it was suppressed in every month of the year.
        ("Merry Christmas Mr. Lawrence", "", "1996", False),
        ("Merry Christmas Mr. Lawrence", "", "Merry Christmas Mr. Lawrence", False),
        ("Merry Christmas Mr. Lawrence - Remastered", "", "1996", False),
        ("Christmas", "", "Tommy", False),
        ("Christmas in February", "", "New York", False),
        # A carol that really is called Christmas, on a Christmas record.
        ("Christmas", "", "A Christmas Album", True),
        # Noel is a first name before it is a carol.
        ("AKA... What a Life!", "", "Noel Gallagher's High Flying Birds", False),
        ("If I Had a Gun...", "", "Noel Gallagher", False),
        # Santa in Spanish is an adjective, and it is not about him.
        ("Santa Monica", "", "Sparkle and Fade", False),
        ("Santa Fe", "", "", False),
        ("Santa María", "", "", False),
        ("Santa Lucía", "", "", False),
        ("Semana Santa", "", "", False),
        ("Tierra Santa", "", "", False),
        ("Oye Como Va", "", "Santana", False),
        # Santa where it is about him, including the possessive, which
        # loses its apostrophe to the folding.
        ("Santa's Coming for Us", "", "", True),
        ("Back Door Santa", "", "", True),
        ("Must Be Santa", "", "", True),
    ],
)
def test_is_holiday_ignores_season(name, version, album, expected):
    assert is_holiday(name, version, album) is expected


# One real record per entry in the holiday list. A mutation sweep found
# that most of the list could be deleted without a single test failing,
# which is the wrong way round for a list whose entire purpose is to be
# long: a token nobody has pinned is a token somebody tidies away.
@pytest.mark.parametrize(
    ("name", "album"),
    [
        ("White Christmas", ""),
        ("Merry Xmas Everybody", ""),
        ("Feliz Navidad", ""),
        ("Winter Wonderland", ""),
        ("Let It Snow! Let It Snow! Let It Snow!", ""),
        ("Sleigh Ride", ""),
        ("Jingle Bell Rock", ""),
        ("Silver Bells", ""),
        ("Frosty the Snowman", ""),
        ("Rudolph the Red-Nosed Reindeer", ""),
        ("A Holly Jolly Christmas", ""),
        ("Mistletoe", ""),
        ("Auld Lang Syne", ""),
        ("Baby, It's Cold Outside", ""),
        ("Little Saint Nick", ""),
        ("Mele Kalikimaka", ""),
        ("Wintersong", ""),
        ("It's the Most Wonderful Time of the Year", ""),
        ("Happy Holiday", ""),
        ("The Holiday Season", ""),
        ("Fairytale of New York", ""),
        ("Underneath the Tree", ""),
        ("Silent Night", ""),
        ("O Holy Night", ""),
        ("Stille Nacht", ""),
        ("O Tannenbaum", ""),
        ("Deck the Halls", ""),
        ("The Little Drummer Boy", ""),
        ("Away in a Manger", ""),
        ("O Come, All Ye Faithful", ""),
        ("Hark! The Herald Angels Sing", ""),
        ("God Rest Ye Merry, Gentlemen", ""),
        ("God Rest You Merry, Gentlemen", ""),
        ("Good King Wenceslas", ""),
        ("Carol of the Bells", ""),
        ("What Child Is This", ""),
        ("Ding Dong Merrily on High", ""),
        ("The Twelve Days of Christmas", ""),
        ("We Three Kings", ""),
        ("O Christmas Tree", ""),
        ("Greensleeves", ""),
        ("Mary's Boy Child", ""),
        ("Angels We Have Heard on High", ""),
        ("Do You Hear What I Hear?", ""),
        ("The First Noël", ""),
        ("Must Be Santa", ""),
        # Two the list carries for the album rather than the title.
        ("Some Song", "Yuletide Favourites"),
        ("Some Song", "Sleigh Bells and Carols"),
    ],
)
def test_every_holiday_token_catches_a_real_record(name, album):
    assert is_holiday(name, "", album)


@pytest.mark.parametrize(
    "version",
    ["Club Mix", "Dance Mix", "Extended Mix", "Dub Mix", "House Mix", '12" Mix'],
)
def test_every_club_reworking_counts_as_a_remix(version):
    """Only "club mix" was pinned, so the other five could go quietly."""
    assert is_remix("Blue Monday", version)


@pytest.mark.parametrize(
    "name",
    [
        "Free Fallin' (Karaoke Version)",
        "Free Fallin' (Made Popular By Tom Petty)",
        "Free Fallin' (In the Style of Tom Petty)",
        "Free Fallin' (Originally Performed By Tom Petty)",
        "Free Fallin' (A Tribute to Tom Petty)",
        "Free Fallin' (Backing Track)",
    ],
)
def test_every_imitation_marker_is_caught(name):
    """These are credited to the artist they imitate, so the title marker
    is the only thing that can reject them."""
    assert is_non_song(name, "")


@pytest.mark.parametrize(
    "name",
    [
        "Track by Track: Song One",
        "Commentary on the Album",
        "Interlude",
        "Skit",
        "Voice Memo",
        "Spoken Word",
    ],
)
def test_every_non_song_marker_is_caught(name):
    assert is_non_song(name, "")


def test_clean_similar_artists_drops_collabs_and_seed():
    names = [
        ("Lady Gaga", 0.9),
        ("Bruno Mars", 0.8),
        ("Lady Gaga, Bruno Mars", 0.7),
        ("Simon & Garfunkel", 0.6),
        ("", 0.5),
        ("Bruno Mars", 0.4),
    ]
    # Simon & Garfunkel stays. The ampersand is not what marks a
    # collaboration credit; being made of artists the list already knows
    # separately is, and this list knows neither Simon nor Garfunkel.
    assert [name for name, _ in clean_similar_artists(names, "Lady Gaga")] == [
        "Bruno Mars",
        "Simon & Garfunkel",
    ]


@pytest.mark.parametrize(
    "act",
    [
        "Simon & Garfunkel",
        "Crosby, Stills & Nash",
        "Peter, Paul and Mary",
        "Hall & Oates",
        "Earth, Wind & Fire",
        "Kool & The Gang",
        "Bob Seger & The Silver Bullet Band",
        "Angus & Julia Stone",
        "Iron & Wine",
        "Big & Rich",
    ],
)
def test_clean_similar_artists_keeps_real_acts(act):
    """Punctuation in a name is not evidence of anything.

    Dropping on it cost a James Taylor seed most of its obvious
    neighbours and a Huey Lewis seed most of its own, which showed up as
    a station that would never play the duos everybody expects.
    """
    names = [(act, 0.9), ("Fleetwood Mac", 0.8)]
    assert act in [name for name, _ in clean_similar_artists(names, "James Taylor")]


def test_clean_similar_artists_drops_the_seeds_own_band():
    names = [("Bruce Springsteen & The E Street Band", 0.9), ("Tom Petty", 0.8)]
    assert [
        name for name, _ in clean_similar_artists(names, "Bruce Springsteen")
    ] == ["Tom Petty"]


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


def test_floor_still_applies_to_the_artist_styles_three_neighbours():
    """The Artist seed style draws exactly three, and a minimum of four
    switched the floor off for the whole style, which brought back the
    one defect the rule was written for."""
    pool = [("Fleetwood Mac", 2103659), ("Stevie Nicks", 715395), ("Christine McVie", 28061)]
    keep, dropped = drop_outliers(pool, 10)
    assert keep == ["Fleetwood Mac", "Stevie Nicks"]
    assert dropped == [("Christine McVie", 28061)]


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


def test_the_second_slot_takes_the_deep_track_the_pattern_asks_for():
    """The test above cannot fail, and that took a while to notice.

    Opening on Power is what the fullest-pool rule does anyway, so
    asserting it proves nothing about the pattern: ignoring tiers
    entirely, or never advancing past the first one, both pass it. What
    the pattern is for is the shape of the whole hour, so this asks for
    the slot the pattern alone can fill, and that the hour does not open
    with every big record in a row.
    """
    lists = [["aP", "aD", "aS"], ["bP", "bD", "bS"], ["cP", "cD", "cS"]]
    tiers = {uri: uri[1] for pool in lists for uri in pool}
    out = sequence_tiered(lists, tiers, ["P", "D", "S"])
    assert tiers[out[1]] == "D"
    assert [tiers[u] for u in out[:3]] != ["P", "P", "P"]


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


@pytest.mark.parametrize(
    ("one", "other"),
    [
        ("Bill Haley and His Comets", "Bill Haley & His Comets"),
        ("Crosby, Stills and Nash", "Crosby, Stills & Nash"),
        ("Earth Wind & Fire", "Earth, Wind & Fire"),
        ("Mike + The Mechanics", "Mike & The Mechanics"),
        ("Bruce Springsteen & The E Street Band", "Bruce Springsteen"),
    ],
)
def test_spelling_disagreements_are_the_same_act(one, other):
    """An ampersand against "and" is not a question worth an answer."""
    assert credits_artist([one], other)
    assert credits_artist([other], one)


@pytest.mark.parametrize(
    ("full", "short"),
    [
        ("Tom Petty and The Heartbreakers", "Tom Petty"),
        ("Bill Haley and His Comets", "Bill Haley"),
        ("Bruce Springsteen & The E Street Band", "Bruce Springsteen"),
        ("Katrina and the Waves", "Katrina"),
    ],
)
def test_a_backing_band_can_be_stripped_for_a_second_search(full, short):
    """The retry that searches under the short name has to actually fire.

    It did not. The pattern was case sensitive and required a lowercase
    "the", which no service writes, so the fallback was dead for every
    real name and a Tom Petty station kept searching Tidal under the long
    one, where the results are four Stevie Nicks collaborations and a
    karaoke record.
    """
    assert without_backing_band(full) == short


def test_nothing_to_strip_reports_nothing_to_strip():
    assert without_backing_band("Fleetwood Mac") == ""


def test_an_album_called_rough_mix_is_not_a_rough_mix():
    """Townshend and Lane's 1977 record is called Rough Mix, and every
    track on it was being thrown away as an unfinished recording."""
    assert not is_demo("Let My Love Open the Door", "", "Rough Mix")
    assert is_demo("Song", "Rough Mix", "Album")
    assert is_demo("F2D", "", "Demo 2")
    assert not is_demo("Demolition Man", "", "Ghost in the Machine")


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
    """Ported from the round-robin sequencer this replaced.

    Compares the pool each track came from, not the track. Comparing the
    tracks asserted that adjacent URIs differ, which is true of any
    ordering of distinct tracks whatever the cap does, so the cap could
    be ignored outright and this still passed.
    """
    pools = [["s1", "s2", "s3"], ["a1", "a2", "a3"]]
    tiers = dict.fromkeys(("s1", "s2", "s3", "a1", "a2", "a3"), "P")
    ordered = sequence_tiered(pools, tiers, ["P"], max_consecutive=1)
    whose = [uri[0] for uri in ordered]
    assert all(whose[i] != whose[i + 1] for i in range(len(whose) - 1))
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


# --- Real per-song counts, where the position guess was wrong -------------


def test_the_guess_inverts_a_giants_deep_hit_against_a_one_hit_wonder():
    """The measured case, and the reason share exists.

    Both figures are real, from 2026-09-15. The Beatles' twentieth song
    is 54% of their biggest; Dexys Midnight Runners' second is 4% of
    theirs. Guessing the fraction as 0.7 ** position says the opposite,
    and by a wide margin, so the clock spent Power slots on the dud and
    filed the Beatles record as Deep.
    """
    pool = [
        ("The Beatles", ["beatles-20th"], 1_600_000),
        ("Dexys Midnight Runners", ["dexys-2nd"], 1_300_000),
    ]
    rank = {"beatles-20th": 19, "dexys-2nd": 1}

    guessed = reach_of(pool, 0.7, rank)
    assert guessed["dexys-2nd"] > guessed["beatles-20th"]

    share = {"beatles-20th": 0.54, "dexys-2nd": 0.04}
    honest = reach_of(pool, 0.7, rank, share)
    assert honest["beatles-20th"] > honest["dexys-2nd"]


def test_tiers_follow_the_real_share_not_the_position():
    """The same inversion where it actually costs something: the hour."""
    pool = [
        ("The Beatles", ["beatles-20th"], 1_600_000),
        ("Dexys Midnight Runners", ["dexys-2nd"], 1_300_000),
        ("Filler", ["filler"], 100_000),
    ]
    rank = {"beatles-20th": 19, "dexys-2nd": 1, "filler": 0}
    share = {"beatles-20th": 0.54, "dexys-2nd": 0.04, "filler": 1.0}
    tiers = tier_of(pool, 0.7, rank, share)
    assert tiers["beatles-20th"] == TIER_POWER
    assert tiers["dexys-2nd"] == TIER_DEEP


def test_an_artists_top_track_still_scores_their_whole_audience():
    """What keeps reach figures recorded before this comparable with after.

    A share of 1.0 is exactly what 0.7 ** 0 already gave, so a first
    batch, where almost every track sits at position 0, does not move.
    """
    pool = [("Erasure", ["top"], 575_377)]
    assert reach_of(pool, 0.7, {"top": 0}, {"top": 1.0}) == reach_of(
        pool, 0.7, {"top": 0}
    )


def test_a_song_lastfm_never_saw_falls_back_to_the_guess():
    """Tidal and Last.fm disagree on classical spellings especially, so a
    partial share must not drag the unmatched tracks to zero."""
    pool = [("Mixed", ["known", "unknown"], 800_000)]
    reach = reach_of(pool, 0.7, {"known": 1, "unknown": 1}, {"known": 0.5})
    assert reach["known"] == 400_000
    assert reach["unknown"] == int(800_000 * 0.7)


def test_shares_are_measured_against_the_artists_own_biggest():
    """Genre neutrality, using the real Hank Williams Jr figures.

    His biggest song has 38,490 listeners, a fraction of any rock act
    here, and his curve is as flat as a giant's. Measured against himself
    he keeps his catalogue; against any absolute number he loses it.
    """
    known = [("Family Tradition", 38_490), ("A Country Boy Can Survive", 31_947)]
    shares = song_shares({"a": "Family Tradition", "b": "A Country Boy Can Survive"},
                         known)
    assert shares["a"] == 1.0
    assert shares["b"] > 0.8


def test_a_remaster_matches_the_record_it_is_a_remaster_of():
    known = [("In the Air Tonight", 900_000)]
    shares = song_shares({"u": "In the Air Tonight (2015 Remaster)"}, known)
    assert shares["u"] == 1.0


def test_no_lastfm_data_means_no_shares_rather_than_zero_shares():
    """An outage must leave the tiering on its guess, not flatten it."""
    assert song_shares({"u": "Anything"}, None) == {}
    assert song_shares({"u": "Anything"}, []) == {}


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
    country = {"The Highwaymen": 380_679, "David Allan Coe": 136_180, "Johnny Paycheck": 128_366}
    assert depth_bar(rock) == 64_350
    # The point of the rule, which the fixed number above does not say:
    # country is not held to rock's figures.
    assert depth_bar(country) < depth_bar(rock)
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
    """A small act on a big station still gets its own two biggest songs."""
    small = [
        ("Family Tradition", 38_000),
        ("A Country Boy Can Survive", 32_000),
        ("Born to Boogie", 9_000),
    ]
    songs, rank = _ranked(["Born to Boogie", "A Country Boy Can Survive", "Family Tradition"])
    # Last.fm decides which two, not the provider, so its third song goes.
    assert too_deep(songs, rank, small, 100_000, 2) == {"t:0"}


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


def test_a_duet_where_the_artist_is_the_second_credit_is_kept():
    """Keying on the first credit whoever was asked for throws duets away.

    A Stevie Nicks and Tom Petty duet lists her first, so on a Tom Petty
    station it carries her artist id, looks like a different act under
    the same name, and is dropped as a namesake.
    """
    real = [_Song(f"r:{i}", f"Hit {i}", ["Tom Petty"], ["id:petty"]) for i in range(5)]
    duet = _Song(
        "d", "Stop Draggin' My Heart Around",
        ["Stevie Nicks", "Tom Petty"], ["id:nicks", "id:petty"],
    )
    assert keep_one_act([*real, duet], "Tom Petty") == [*real, duet]


def test_the_providers_first_result_is_not_an_a_track():
    """A search for Sugar put a techno record by a different Sugar first.

    Last.fm lists it 27th for Sugar at 8,664 listeners against 86,542 for
    their biggest, so the bar catches it once the provider's order stops
    waving the first results through.
    """
    sugar = [
        ("If I Can't Change Your Mind", 86_542),
        ("A Good Idea", 61_183),
        ("Candy from Strangers", 8_664),
    ]
    songs, rank = _ranked(
        ["Candy from Strangers", "If I Can't Change Your Mind", "A Good Idea"]
    )
    assert too_deep(songs, rank, sugar, 15_000, 2) == {"t:0"}


def test_an_artist_last_fm_knows_under_another_name_is_left_alone():
    """Classical, where the two services share no song titles at all."""
    vivaldi = [("Spring", 400_000), ("Winter", 300_000)]
    songs, rank = _ranked(
        [
            "The Four Seasons, Violin Concerto in E Major, Allegro",
            "Concerto in G Minor",
        ]
    )
    assert too_deep(songs, rank, vivaldi, 100_000, 2) == set()


def test_an_artist_with_no_shared_titles_keeps_its_third_song_too():
    """The case above has two songs and allows two A-tracks, so the
    exemption covers both and the no-overlap guard is never load-bearing.
    A third song is what actually needs the guard."""
    vivaldi = [("Spring", 400_000), ("Winter", 300_000)]
    songs, rank = _ranked(["Concerto in E", "Concerto in G", "Concerto in F"])
    assert too_deep(songs, rank, vivaldi, 100_000, 2) == set()


def test_a_last_fm_title_with_different_punctuation_still_matches():
    """The two services disagree about curly quotes, and a title that
    fails to match reads as a song nobody has heard of."""
    known = [("A", 500_000), ("B", 400_000), ("Don't Stop Believin'", 300_000)]
    songs, rank = _ranked(["A", "B", "Don’t Stop Believin’"])
    assert too_deep(songs, rank, known, 100_000, 2) == set()


def test_an_a_track_last_fm_lists_as_a_remaster_is_still_an_a_track():
    small = [
        ("Family Tradition - Remastered", 38_000),
        ("Country Boy", 32_000),
        ("Born", 9_000),
    ]
    songs, rank = _ranked(["Family Tradition", "Country Boy", "Born"])
    assert too_deep(songs, rank, small, 100_000, 2) == {"t:2"}


def test_a_song_listed_twice_on_last_fm_is_judged_on_its_bigger_count():
    known = [("A", 500_000), ("B", 400_000), ("B - Remastered", 10_000)]
    songs, rank = _ranked(["A", "B"])
    assert too_deep(songs, rank, known, 100_000, 1) == set()


def test_the_depth_bar_ignores_artists_of_unknown_size():
    """A Last.fm miss counted as zero drags the median down, which lets
    deeper cuts through on any station where one lookup failed."""
    assert depth_bar({"A": 1_000_000, "B": 500_000, "Unknown": 0}) == 50_000


def test_a_tempo_after_an_opus_number_is_stripped():
    assert base_title("Symphony No. 9, Op. 125, Allegro") == base_title(
        "Symphony No. 9, Op. 125"
    )


def test_a_title_that_opens_with_a_parenthesis_survives():
    """Blue Oyster Cult could never be queued: the title normalised to "".

    A song with no base title is dropped as unusable, so "(Don't Fear) The
    Reaper", "(Sittin' On) The Dock of the Bay" and "(I Can't Get No)
    Satisfaction" were all unreachable.
    """
    assert base_title("(Don't Fear) The Reaper") == "dont fear the reaper"
    assert base_title("(Sittin' On) The Dock of the Bay") == "sittin on the dock of the bay"
    # And it matches the provider's other spelling of the same record.
    assert base_title("Don't Fear the Reaper") == "dont fear the reaper"


def test_a_trailing_parenthesis_is_still_a_note_about_the_recording():
    assert base_title("Song (Radio Edit)") == "song"
    assert base_title("Cold Heart (PNAU Remix)") == "cold heart"


def test_curly_and_straight_quotes_are_the_same_title():
    """The provider writes one, Last.fm writes the other, and a title that
    misses the Last.fm list is read as a song nobody knows."""
    assert base_title("Don’t Stop Believin’") == base_title("Don't Stop Believin'")


def test_an_ampersand_is_the_word_and():
    assert base_title("Rock & Roll") == base_title("Rock and Roll")


def test_santana_is_not_a_christmas_album():
    """"santa" as a substring took every track on an album called Santana,
    plus Santa Monica and Santa Fe."""
    assert not is_holiday("Black Magic Woman", "", "Santana")
    assert not is_holiday("Evil Ways", "", "Santana III")
    assert not is_holiday("Santa Monica", "", "")
    assert not is_holiday("Santa Fe", "", "")
    assert is_holiday("Santa Claus Is Coming to Town", "", "")
    assert is_holiday("Santa Baby", "", "")


def test_an_unknown_first_credit_keeps_the_lead():
    """A lookup miss is not evidence of being small, here as everywhere.

    Keys are the names as credited, the way the engine passes them.
    """
    sizes = {"Sonny": 0, "Cher": 900_000}
    assert lead_among_credits("Sonny", sizes, 2_000_000) == "Sonny"




@pytest.mark.parametrize(
    ("title", "live"),
    [
        # Verbatim from Tidal. The marker comes before any separator.
        ("Live at the Olympia - Paris, France (October 10, 1969) - Dazed", True),
        ("Live at Tomorrowland 2026 (Freedom Stage) ID #002", True),
        ("Song [Live]", True),
        ("Song [Live at the Forum, 1980]", True),
        ("Song – Live", True),
        ("Song — Live", True),
        ("Helpless [Concert Version]", True),
        ("Layla [Unplugged]", True),
        # And the songs that are simply called what they are called.
        ("Live Wire", False),
        ("Live to Tell", False),
        ("Live and Let Die", False),
        ("(Forever) Live And Die", False),
        ("Livermore", False),
    ],
)
def test_live_markers_wherever_the_provider_puts_them(title, live):
    assert is_live(title, "") is live


@pytest.mark.parametrize(
    ("title", "remix"),
    [
        # Tidal writes these with no bracket, dash or version field.
        ("Savage Remix", True),
        ("Drunk in Love Remix", True),
        ("Song [PNAU Remix]", True),
        ("Song – PNAU Remix", True),
        ("Song [Club Mix]", True),
        ("Renegade", False),
        ("Remix Artist Collective", False),
    ],
)
def test_remix_markers_wherever_the_provider_puts_them(title, remix):
    assert is_remix(title, "") is remix


@pytest.mark.parametrize(
    ("title", "album", "holiday"),
    [
        # Christmas records that never say Christmas.
        ("Don't Shoot Me Santa", "Don't Waste Your Wishes", True),
        ("Back Door Santa", "Back Door Santa", True),
        ("Santa's Coming for Us", "", True),
        ("Must Be Santa", "", True),
        ("Santa Looked a Lot Like Daddy", "", True),
        # Places named after him, and the band.
        ("Santa Monica", "", False),
        ("Santa Fe", "", False),
        ("Black Magic Woman", "Santana", False),
        ("Evil Ways", "Santana III", False),
        ("Don't Let Me Be Misunderstood", "Santa Esmeralda", False),
    ],
)
def test_santa_without_the_places_named_after_him(title, album, holiday):
    assert is_holiday(title, "", album) is holiday


def test_a_spelling_last_fm_has_never_seen_is_not_a_deep_cut():
    """Tidal prefixes the composer; Last.fm does not, and the famous
    recordings were being cut for it."""
    known = [
        ("Symphony No. 5 in C Minor, Op. 67: I. Allegro con brio", 400_000),
        ("Fur Elise", 300_000),
    ]
    songs, rank = _ranked(
        [
            "Beethoven: Symphony No. 5 in C Minor, Op. 67: I. Allegro con brio",
            "Fur Elise",
            "Sonata No. 32, Arietta",
        ]
    )
    # The first is a top result whose spelling Last.fm does not carry, so
    # it stays. The third is past the A-tracks and unknown, so it goes.
    assert too_deep(songs, rank, known, 100_000, 2) == {"t:2"}


def test_extra_spaces_are_collapsed():
    """Stripping the brackets off a leading parenthetical leaves two."""
    assert base_title("Hello  World") == "hello world"
