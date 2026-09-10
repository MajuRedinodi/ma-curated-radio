"""Track-change detection.

Every case here is one that happened. The rules are three lines long and
have been wrong four separate ways, so each is pinned to the symptom it
produced rather than to an abstraction of it.
"""

import pytest
from decide import (
    Decision,
    QueueFacts,
    decide,
    is_bulk_load,
    is_transitional,
    leading_pool,
)

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


# --- The seam between a batch and the track it follows -----------------

POOLS = ["Electric Light Orchestra", "Boston", "Styx"]


def test_the_artist_playing_now_is_counted_as_having_had_a_turn():
    """Picking Mr. Blue Sky opened a batch with two more ELO tracks.

    Every step was legal on its own, because a batch is sequenced in
    isolation and cannot see the track it will be played after.
    """
    assert leading_pool(POOLS, ["Electric Light Orchestra"], lands_next=True) == 0


def test_a_batch_landing_elsewhere_primes_nothing():
    """A refill joins the end of a populated queue, far from the join."""
    assert leading_pool(POOLS, ["Boston"], lands_next=False) is None


def test_every_credit_is_matched_not_only_the_first():
    """The first credit seeds a batch, but a pool can be led by any.

    Observed live: a batch following "Shawn Colvin, David Crosby".
    """
    assert leading_pool(POOLS, ["Tom Petty", "Styx"], lands_next=True) == 2


def test_an_artist_that_drew_no_tracks_primes_nothing():
    """Its pool was dropped, so there is no run for it to continue."""
    assert leading_pool(POOLS, ["Christine McVie"], lands_next=True) is None


def test_nothing_playing_primes_nothing():
    assert leading_pool(POOLS, [], lands_next=True) is None
    assert leading_pool(POOLS, [""], lands_next=True) is None


def test_matching_ignores_case_and_stray_spacing():
    assert leading_pool(POOLS, ["  boston "], lands_next=True) == 1


# --- Between tracks ------------------------------------------------------

BLANK = QueueFacts(current_uri="", next_uri="", items=1, remaining=0)


def test_a_queue_between_tracks_is_not_a_pick():
    """A second pick on a phone, "Walk This Way", was left as one song.

    While the queue was being replaced it reported no current track for a
    moment. That blank was read as a pick, the run it started had no
    artist to build from, and the real pick a moment later was then
    judged against an expectation taken from the blank.
    """
    assert call(BLANK) is Decision.NOTHING


def test_a_queue_between_tracks_does_not_refill_either():
    """An empty reading says nothing, including that the queue ran dry."""
    assert call(BLANK, expected_uri="") is Decision.NOTHING


def test_only_a_blank_reading_is_transitional():
    assert is_transitional(BLANK)
    assert not is_transitional(PICK)
