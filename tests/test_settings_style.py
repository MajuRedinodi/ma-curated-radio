"""Per-style batch shape.

Artist radio and Balanced want opposite shapes, and they used to share
one pair of numbers, so tuning Balanced silently retuned Artist radio.
"""

from const import (
    CONF_BATCH_LENGTH,
    CONF_MAX_ARTISTS,
    CONF_STYLE_SETTINGS,
    CONF_TRACKS_PER_ARTIST,
    LANE_LOOKUPS_PER_BATCH,
    PLAYED_LOOKUPS_PER_BATCH,
    SEED_LEAN_ARTIST,
    SEED_LEAN_BALANCED,
    STYLE_DEFAULTS,
    style_value,
    with_style_value,
)


def test_each_style_has_its_own_default():
    assert style_value({}, SEED_LEAN_ARTIST, CONF_MAX_ARTISTS) == 3
    assert style_value({}, SEED_LEAN_BALANCED, CONF_MAX_ARTISTS) == 8
    assert style_value({}, SEED_LEAN_ARTIST, CONF_TRACKS_PER_ARTIST) == 3
    assert style_value({}, SEED_LEAN_BALANCED, CONF_TRACKS_PER_ARTIST) == 3


def test_a_value_from_before_styles_applies_to_every_style():
    """An existing install must keep behaving exactly as it did."""
    legacy = {CONF_MAX_ARTISTS: 8, CONF_TRACKS_PER_ARTIST: 2}
    for style in (SEED_LEAN_ARTIST, SEED_LEAN_BALANCED):
        assert style_value(legacy, style, CONF_MAX_ARTISTS) == 8
        assert style_value(legacy, style, CONF_TRACKS_PER_ARTIST) == 2


def test_setting_one_style_leaves_the_others_alone():
    options = {CONF_MAX_ARTISTS: 8}
    updated = with_style_value(options, SEED_LEAN_ARTIST, CONF_MAX_ARTISTS, 3)
    assert style_value(updated, SEED_LEAN_ARTIST, CONF_MAX_ARTISTS) == 3
    # Balanced still falls back to the pre-style value, not to its default.
    assert style_value(updated, SEED_LEAN_BALANCED, CONF_MAX_ARTISTS) == 8


def test_writing_a_style_does_not_mutate_the_options_passed_in():
    options = {CONF_STYLE_SETTINGS: {SEED_LEAN_ARTIST: {CONF_MAX_ARTISTS: 3}}}
    with_style_value(options, SEED_LEAN_BALANCED, CONF_MAX_ARTISTS, 8)
    assert options[CONF_STYLE_SETTINGS] == {SEED_LEAN_ARTIST: {CONF_MAX_ARTISTS: 3}}


def test_writing_a_style_that_is_already_there_does_not_mutate_it_either():
    """The case above writes a style the options do not yet hold, which a
    shallow copy survives. Overwriting one that is already there is what
    actually reaches into the caller's dictionary."""
    options = {CONF_STYLE_SETTINGS: {SEED_LEAN_ARTIST: {CONF_MAX_ARTISTS: 3}}}
    with_style_value(options, SEED_LEAN_ARTIST, CONF_MAX_ARTISTS, 5)
    assert options[CONF_STYLE_SETTINGS] == {SEED_LEAN_ARTIST: {CONF_MAX_ARTISTS: 3}}


def test_both_styles_can_be_set_independently():
    options: dict = {}
    options = with_style_value(options, SEED_LEAN_ARTIST, CONF_TRACKS_PER_ARTIST, 3)
    options = with_style_value(options, SEED_LEAN_BALANCED, CONF_TRACKS_PER_ARTIST, 2)
    assert style_value(options, SEED_LEAN_ARTIST, CONF_TRACKS_PER_ARTIST) == 3
    assert style_value(options, SEED_LEAN_BALANCED, CONF_TRACKS_PER_ARTIST) == 2


# --- What a batch can afford to look up ---------------------------------


def test_a_full_batch_of_records_fits_its_lookup_budget():
    """The two undated tracks of 16 Sep, pinned.

    A Smiths refill came back with twelve of fourteen dated, missing
    "Only You" and "Just Can't Get Enough", which Wikipedia covers
    exhaustively. Selection and the batch shared one allowance and
    selection spent it first, on candidates it went on to reject. The
    records that play now have their own, and it has to stay big enough
    for the longest batch any style can build or the same hole reopens
    quietly.
    """
    longest = max(
        values[CONF_BATCH_LENGTH]
        or values[CONF_MAX_ARTISTS] * values[CONF_TRACKS_PER_ARTIST]
        for values in STYLE_DEFAULTS.values()
    )
    assert longest <= PLAYED_LOOKUPS_PER_BATCH


def test_selection_cannot_spend_what_the_batch_needs():
    """Two budgets, not one pool with two claimants."""
    assert LANE_LOOKUPS_PER_BATCH > 0
    assert PLAYED_LOOKUPS_PER_BATCH > 0
