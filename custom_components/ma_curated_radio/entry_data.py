"""What a config entry's stored data means.

Two rules that decide what is written back to an entry, kept here rather
than in the flow and the setup that use them, because both have already
been wrong in ways nothing could catch: one silently reset every setting
it did not display, and the other left the integration watching a player
that no longer existed.

Nothing here imports Home Assistant, or anything else in this
integration, so both can be tested directly.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from typing import Any


def merge_options(
    stored: Mapping[str, Any],
    submitted: Mapping[str, Any],
    *,
    clearable: Iterable[str] = (),
) -> dict[str, Any]:
    """What an options form's result should replace the stored options with.

    Home Assistant replaces the whole options blob with whatever a flow
    returns, and a form never shows everything an entry holds: the master
    switch, the popularity floor and every per-style number are set from
    their own entities. Returning only the form's own fields silently
    reset all of them, so opening the dialog and pressing Submit turned a
    switched-off station back on and undid an evening of tuning.

    ``clearable`` are the optional fields. The frontend omits a field that
    has been emptied rather than sending an empty value, so those have to
    be dropped explicitly or a merge would put the old value back.
    """
    merged = {**stored, **submitted}
    for key in clearable:
        if key not in submitted:
            merged.pop(key, None)
    return merged


def resolve_player(
    stored_id: str | None,
    player: str,
    *,
    by_id: Callable[[str], str | None],
    by_name: Callable[[str], str | None],
) -> tuple[str, str | None]:
    """Which entity the configured player is now, and its registry id.

    A player is configured by entity_id, and everything targets that: the
    state subscription and every Music Assistant action. Entity ids are
    not stable. Renaming the player left this integration watching a name
    nothing would ever report again, with no events, no batches and no
    error. The registry id survives a rename, so it is recorded once and
    used to find the current name afterwards.

    ``by_id`` resolves a registry id to an entity_id; ``by_name`` returns
    the registry id for an entity_id. Both return None when the registry
    has no such entry, which is how a deleted player is told from a
    renamed one: a rename resolves, a deletion does not.
    """
    if stored_id and (current := by_id(stored_id)):
        return current, stored_id
    # Nothing recorded yet, or the player is gone rather than renamed.
    # Either way the configured name is the best there is.
    return player, by_name(player)
