"""Track-change detection.

Every case here is one that happened. The rules are three lines long and
have been wrong four separate ways, so each is pinned to the symptom it
produced rather than to an abstraction of it.
"""

import pytest
from decide import Decision, QueueFacts, decide, is_bulk_load

# A pick lands on a track the integration did not queue, breaking the
# expectation set by the previous reading.
PICK = QueueFacts(current_uri="track/new", next_uri="", items=1, remaining=0)


def call(queue=PICK, **kwargs):
    """Decide, with the settings that ship by default."""
    options = {
        "expected_uri": "track/expected",
        "current_is_ours": False,
        "next_is_ours": False,
        "previous_items": 20,
        "bulk_threshold": 3,
        "refill_threshold": 2,
    }
    return decide(queue, **{**options, **kwargs})


def test_a_track_we_did_not_queue_breaking_the_expectation_is_a_pick():
    assert call() is Decision.PICKED


def test_our_own_track_is_never_a_pick():
    """The Lady Gaga session that ended up playing UK house.

    The expectation breaks for innocent reasons: a rapid Previous, a
    track that would not play, a queue rewrite landing mid change. Each
    false positive re-anchored the drift fence to wherever the music had
    already reached, so the fence only ever constrained one hop.
    """
    assert call(current_is_ours=True) is not Decision.PICKED


def test_nothing_is_a_pick_before_anything_has_been_observed():
    """Immediately after a restart there is no expectation to break."""
    assert call(expected_uri="") is not Decision.PICKED


def test_playing_the_expected_track_is_not_a_pick():
    queue = QueueFacts(current_uri="track/expected", items=20, remaining=9)
    assert call(queue) is Decision.NOTHING


def test_a_loaded_playlist_is_left_alone():
    """Choosing to play a playlist is a decision to hear it.

    The morning routine loads one, and rewriting it would be the rudest
    thing this integration could do.
    """
    playlist = QueueFacts(current_uri="track/new", items=300, remaining=299)
    assert call(playlist, previous_items=20) is not Decision.PICKED


def test_a_pick_made_during_a_playlist_is_still_a_pick():
    """Size alone traps the listener inside whatever is playing.

    Music Assistant inserts a picked track and jumps to it, leaving the
    rest of the playlist queued behind, so the queue still looks big and
    still looks foreign. What gives it away is that it barely moved.
    """
    inside = QueueFacts(current_uri="track/new", items=301, remaining=299)
    assert call(inside, previous_items=300) is Decision.PICKED


def test_a_playlist_that_shrinks_the_queue_is_still_a_bulk_load():
    """Loading a playlist usually replaces the queue rather than adding.

    Swapping a 170-track queue for a 40-track playlist is a change of
    minus 130, which a growth test sails straight past.
    """
    smaller = QueueFacts(current_uri="track/new", items=40, remaining=39)
    assert call(smaller, previous_items=170) is not Decision.PICKED


def test_a_big_queue_of_our_own_is_not_a_bulk_load():
    """Our own long batch must not read as somebody else's playlist."""
    ours = QueueFacts(current_uri="track/new", next_uri="track/ours", items=30)
    assert not is_bulk_load(
        ours, previous_items=None, threshold=3, next_is_ours=True
    )


def test_bulk_detection_can_be_turned_off():
    big = QueueFacts(current_uri="track/new", items=300, remaining=299)
    assert call(big, bulk_threshold=0, previous_items=20) is Decision.PICKED


def test_a_nearly_empty_queue_refills():
    queue = QueueFacts(current_uri="track/expected", items=10, remaining=2)
    assert call(queue) is Decision.REFILL


def test_a_full_queue_is_left_alone():
    queue = QueueFacts(current_uri="track/expected", items=20, remaining=3)
    assert call(queue) is Decision.NOTHING


def test_a_pick_wins_over_a_refill():
    """Both conditions hold on a pick, since the new queue is one track."""
    assert call() is Decision.PICKED


@pytest.mark.parametrize(
    "queue",
    [
        PICK,
        QueueFacts(current_uri="track/expected", items=10, remaining=0),
    ],
)
def test_a_routine_that_owns_the_queue_suppresses_everything(queue):
    """A scheduled rebuild would otherwise look exactly like a pick."""
    assert call(queue, in_cooldown=True) is Decision.NOTHING
