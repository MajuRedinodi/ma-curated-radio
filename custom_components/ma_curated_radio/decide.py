"""What to do when the playing track changes.

Split out of the coordinator so it can be tested without Home Assistant.
Every detection bug this integration has had lived in these few rules
rather than in the wiring around them: a manual pick read as a refill, a
playlist load read as a pick, a pick read as neither. They are worth
pinning down.

Nothing here does any I/O. It takes a description of the queue and
returns a decision; the caller does the reading and the acting.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Decision(Enum):
    """What a track change turned out to mean."""

    PICKED = "picked"
    """Somebody jumped playback. Replace the stale tail."""

    REFILL = "refill"
    """Normal progression and the queue is nearly out. Top it up."""

    NOTHING = "nothing"
    """Normal progression with plenty left, or a routine that owns the
    queue is still settling. Leave it alone."""


@dataclass(frozen=True, slots=True)
class QueueFacts:
    """The parts of a queue reading that a decision depends on."""

    current_uri: str = ""
    next_uri: str = ""
    items: int = 0
    remaining: int = 0


def is_bulk_load(
    queue: QueueFacts,
    *,
    previous_items: int | None,
    threshold: int,
    next_is_ours: bool,
) -> bool:
    """True if the queue itself was replaced, rather than jumped within.

    A manual pick is one track. A playlist or album is many, and choosing
    to play a playlist is a decision to hear it rather than an invitation
    to replace it.

    Two measurements, because either alone gets a case wrong.

    SIZE, because loading a playlist usually REPLACES the queue rather
    than adding to it: swapping a 170-track queue for a 40-track playlist
    is a change of minus 130, which a growth test sails past.

    CHANGE, because size alone cannot see a pick made *during* a
    playlist. Music Assistant inserts a picked track and jumps to it,
    leaving the rest queued behind, so the queue still looks big and
    still looks foreign. What gives it away is that it barely moved:
    inserting one track shifts the count by one, while loading a playlist
    shifts it by hundreds.

    Without a previous count, immediately after a restart, size has to
    stand alone. Leaving a large unfamiliar queue alone is the safer way
    to be wrong.
    """
    if threshold <= 0 or queue.items < threshold:
        return False
    if next_is_ours:
        return False
    if previous_items is None:
        # Nothing to compare against, which is the state immediately
        # after a restart. Leaving a large unfamiliar queue alone is the
        # safer way to be wrong.
        return True
    # A queue that barely moved is the same queue, one track deep, so
    # somebody jumped within it rather than loading something new.
    return abs(queue.items - previous_items) >= threshold


def decide(
    queue: QueueFacts,
    *,
    expected_uri: str,
    current_is_ours: bool,
    next_is_ours: bool,
    previous_items: int | None,
    bulk_threshold: int,
    refill_threshold: int,
    in_cooldown: bool = False,
) -> Decision:
    """Work out what a track change means.

    ``current_is_ours`` is the important one. A track this integration
    queued is never a manual pick, even when it fails the expected-next
    comparison. That comparison goes wrong for innocent reasons (a rapid
    Previous, a track that would not play, a queue rewrite landing mid
    change), and every false positive used to re-anchor the drift fence
    to wherever the music had already got to, which is how a Lady Gaga
    session ended up playing UK house.

    ``expected_uri`` is empty before anything has been observed, which is
    the state immediately after a restart. Nothing can be called a pick
    then, because there is no expectation to have been broken.
    """
    if in_cooldown:
        return Decision.NOTHING

    picked = (
        bool(expected_uri)
        and queue.current_uri != expected_uri
        and not current_is_ours
        and not is_bulk_load(
            queue,
            previous_items=previous_items,
            threshold=bulk_threshold,
            next_is_ours=next_is_ours,
        )
    )
    if picked:
        return Decision.PICKED
    if queue.remaining <= refill_threshold:
        return Decision.REFILL
    return Decision.NOTHING
