"""Filter parity tests.

These mirror the Jinja expressions in the blueprint this integration
replaces, so a behaviour change here is a deliberate one.
"""

import pytest
from filters import (
    base_title,
    clean_similar_artists,
    is_holiday,
    is_live,
    matches_provider,
    sequence,
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
        "Lady Gaga",
        "Bruno Mars",
        "Lady Gaga, Bruno Mars",
        "Simon & Garfunkel",
        "",
        "Bruno Mars",
    ]
    assert clean_similar_artists(names, "Lady Gaga") == ["Bruno Mars"]


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
