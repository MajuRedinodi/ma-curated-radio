"""What a config entry's stored data means.

Both rules here were wrong in ways nothing could catch: one reset every
setting it did not display, the other left the integration watching a
player that no longer existed.
"""

from entry_data import merge_options, resolve_player


def test_a_form_does_not_reset_what_it_never_showed():
    """Pressing Submit in Configure turned a switched-off station back on
    and reset every per-style number to its default."""
    stored = {"enabled": False, "style_settings": {"balanced": {"max_artists": 8}}}
    merged = merge_options(stored, {"degrees": 2})
    assert merged["enabled"] is False
    assert merged["style_settings"] == {"balanced": {"max_artists": 8}}
    assert merged["degrees"] == 2


def test_a_submitted_value_wins():
    assert merge_options({"degrees": 3}, {"degrees": 2})["degrees"] == 2


def test_clearing_an_optional_field_clears_it():
    """The frontend omits an emptied field rather than sending "", so a
    plain merge would put the old value back."""
    stored = {"cooldown_entity": "script.old", "degrees": 2}
    merged = merge_options(stored, {"degrees": 2}, clearable=("cooldown_entity",))
    assert "cooldown_entity" not in merged
    assert merged["degrees"] == 2


def test_an_optional_field_that_was_submitted_is_kept():
    merged = merge_options(
        {"cooldown_entity": "script.old"},
        {"cooldown_entity": "script.new"},
        clearable=("cooldown_entity",),
    )
    assert merged["cooldown_entity"] == "script.new"


def _registry(entries: dict[str, str]):
    """A fake registry: entity_id to registry id."""
    ids = {value: key for key, value in entries.items()}
    return ids.get, entries.get


def test_a_renamed_player_is_followed():
    """The failure this exists for: no events, no batches, no error."""
    by_id, by_name = _registry({"media_player.new_name": "abc123"})
    current, stored = resolve_player(
        "abc123", "media_player.old_name", by_id=by_id, by_name=by_name
    )
    assert (current, stored) == ("media_player.new_name", "abc123")


def test_the_registry_id_is_recorded_on_first_setup():
    by_id, by_name = _registry({"media_player.stereo": "abc123"})
    current, stored = resolve_player(
        None, "media_player.stereo", by_id=by_id, by_name=by_name
    )
    assert (current, stored) == ("media_player.stereo", "abc123")


def test_a_deleted_player_keeps_its_name_and_reports_no_id():
    """Told apart from a rename by the registry answering to neither."""
    by_id, by_name = _registry({})
    current, stored = resolve_player(
        "abc123", "media_player.gone", by_id=by_id, by_name=by_name
    )
    assert (current, stored) == ("media_player.gone", None)


def test_an_entry_from_before_ids_were_recorded_still_resolves():
    by_id, by_name = _registry({"media_player.stereo": "abc123"})
    current, stored = resolve_player(
        "", "media_player.stereo", by_id=by_id, by_name=by_name
    )
    assert (current, stored) == ("media_player.stereo", "abc123")
