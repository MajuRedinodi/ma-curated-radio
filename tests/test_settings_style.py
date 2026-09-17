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
    STYLE_CLOCK,
    STYLE_DEFAULTS,
    style_value,
    with_style_value,
)
from filters import TIER_DEEP, TIER_GOLD, TIER_POWER, TIER_SECONDARY


def test_each_style_has_its_own_default():
    assert style_value({}, SEED_LEAN_ARTIST, CONF_MAX_ARTISTS) == 3
    assert style_value({}, SEED_LEAN_BALANCED, CONF_MAX_ARTISTS) == 12
    assert style_value({}, SEED_LEAN_ARTIST, CONF_TRACKS_PER_ARTIST) == 3
    assert style_value({}, SEED_LEAN_BALANCED, CONF_TRACKS_PER_ARTIST) == 2


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


# --- The music clock ----------------------------------------------------


def test_every_clock_uses_real_tier_labels():
    """The letters are spelled out in const because filters imports
    nothing, so something has to hold the two spellings together."""
    labels = {TIER_POWER, TIER_SECONDARY, TIER_DEEP, TIER_GOLD}
    for style, clock in STYLE_CLOCK.items():
        assert clock, style
        assert set(clock) <= labels, style


def test_balanced_is_twelve_power_five_secondary_two_deep_one_gold():
    """Jeff's own numbers, listening to it: out of twenty, one gold,
    one or two deep, four to six secondary, the rest power.

    Everything except the Deeps is a record somebody would recognise, so
    the hour is 90% familiar, which is the target."""
    clock = STYLE_CLOCK[SEED_LEAN_BALANCED]
    assert len(clock) == 20
    assert clock.count(TIER_POWER) == 12
    assert clock.count(TIER_SECONDARY) == 5
    assert clock.count(TIER_DEEP) == 2
    assert clock.count(TIER_GOLD) == 1


def test_no_clock_ever_puts_two_unfamiliar_records_together():
    """Deep and Gold are protected by a Power either side. Two in a row
    is how a listener leaves, and the clock repeats, so the wrap has to
    hold too."""
    for style, clock in STYLE_CLOCK.items():
        doubled = clock + clock
        for first, second in zip(doubled, doubled[1:], strict=False):
            assert not (
                first in (TIER_DEEP, TIER_GOLD) and second in (TIER_DEEP, TIER_GOLD)
            ), f"{style}: {first} then {second}"


def test_every_clock_opens_and_closes_on_a_power():
    """Opens strongly because radio quarter-hours do. Closes strongly
    because terciles used to put the remainder in Deep, so a batch ended
    on its weakest material."""
    for style, clock in STYLE_CLOCK.items():
        assert clock[0] == TIER_POWER, style
        assert clock[-1] == TIER_POWER, style


def test_balanced_draws_enough_artists_to_supply_its_powers():
    """The ceiling no pattern can beat. A record is Power when it is one
    of the ones its artist is known for, which is mostly their first, so
    twelve Powers in an hour needs about twelve artists."""
    shape = STYLE_DEFAULTS[SEED_LEAN_BALANCED]
    powers = STYLE_CLOCK[SEED_LEAN_BALANCED].count(TIER_POWER)
    assert shape[CONF_MAX_ARTISTS] >= powers


def test_every_clock_can_fill_its_batch_from_what_the_style_draws():
    """A batch that plays more than it drew has holes in it."""
    for style, shape in STYLE_DEFAULTS.items():
        drawn = shape[CONF_MAX_ARTISTS] * shape[CONF_TRACKS_PER_ARTIST]
        assert shape[CONF_BATCH_LENGTH] <= drawn, style
