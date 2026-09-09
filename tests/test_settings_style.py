"""Per-style batch shape.

Artist radio and Balanced want opposite shapes, and they used to share
one pair of numbers, so tuning Balanced silently retuned Artist radio.
"""

from const import (
    CONF_MAX_ARTISTS,
    CONF_STYLE_SETTINGS,
    CONF_TRACKS_PER_ARTIST,
    SEED_LEAN_ARTIST,
    SEED_LEAN_BALANCED,
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


def test_both_styles_can_be_set_independently():
    options: dict = {}
    options = with_style_value(options, SEED_LEAN_ARTIST, CONF_TRACKS_PER_ARTIST, 3)
    options = with_style_value(options, SEED_LEAN_BALANCED, CONF_TRACKS_PER_ARTIST, 2)
    assert style_value(options, SEED_LEAN_ARTIST, CONF_TRACKS_PER_ARTIST) == 3
    assert style_value(options, SEED_LEAN_BALANCED, CONF_TRACKS_PER_ARTIST) == 2
