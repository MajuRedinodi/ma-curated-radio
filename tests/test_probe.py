"""The popularity probe's sample and its rank agreement."""

from probe import GENRES, SAMPLE, rank_agreement, sample_for


def test_the_sample_covers_six_genres_evenly():
    """An uneven sample would make the per-genre medians incomparable,
    which is the one comparison the probe exists to make.
    """
    assert len(GENRES) == 6
    for genre in GENRES:
        assert len([s for s in SAMPLE if s.genre == genre]) == 10


def test_no_record_appears_twice():
    keys = [(s.artist.lower(), s.title.lower()) for s in SAMPLE]
    assert len(set(keys)) == len(keys)


def test_no_artist_carries_two_records():
    """Two records by one artist share an artist total, so their shares
    are not independent and a genre's median would count that artist
    twice.
    """
    artists = [s.artist.lower() for s in SAMPLE]
    assert len(set(artists)) == len(artists)


def test_narrowing_to_a_genre_returns_only_that_genre():
    picked = sample_for(["country"])
    assert len(picked) == 10
    assert {s.genre for s in picked} == {"country"}


def test_narrowing_to_two_genres_returns_both():
    assert len(sample_for(["country", "soul"])) == 20


def test_an_unknown_genre_narrows_to_nothing():
    """Deliberately not "everything". A probe that quietly measures the
    wrong sample is worse than one that comes back empty.
    """
    assert sample_for(["polka"]) == ()


def test_no_genre_given_is_the_whole_sample():
    assert sample_for([]) == SAMPLE
    assert sample_for(None) == SAMPLE


def test_two_measures_that_order_alike_agree():
    pairs = [(1.0, 10.0), (2.0, 20.0), (3.0, 30.0), (4.0, 40.0)]
    assert rank_agreement(pairs) == 1.0


def test_two_measures_that_order_oppositely_disagree():
    pairs = [(1.0, 40.0), (2.0, 30.0), (3.0, 20.0), (4.0, 10.0)]
    assert rank_agreement(pairs) == -1.0


def test_agreement_is_about_order_not_scale():
    """The whole reason this ranks rather than correlates the values. One
    measure runs to millions and the other to a hundred, and a constant
    offset between genres must not read as disagreement within one.
    """
    listeners = [(900_000.0, 80.0), (500_000.0, 60.0), (100_000.0, 40.0)]
    shifted = [(a / 10, b) for a, b in listeners]
    assert rank_agreement(listeners) == rank_agreement(shifted) == 1.0


def test_a_measure_with_nothing_to_say_gives_no_number():
    """A provider that scores every record the same has not agreed with
    anything; reporting a correlation would invent an ordering it never
    supplied.
    """
    assert rank_agreement([(1.0, 50.0), (2.0, 50.0), (3.0, 50.0)]) is None


def test_two_records_are_not_a_correlation():
    assert rank_agreement([(1.0, 10.0), (2.0, 20.0)]) is None
    assert rank_agreement([]) is None


def test_ties_do_not_break_the_ordering():
    pairs = [(1.0, 10.0), (2.0, 20.0), (2.0, 20.0), (3.0, 30.0)]
    assert rank_agreement(pairs) == 1.0


def test_partial_agreement_lands_between():
    pairs = [(1.0, 10.0), (2.0, 30.0), (3.0, 20.0), (4.0, 40.0)]
    score = rank_agreement(pairs)
    assert score is not None
    assert 0.5 < score < 1.0
