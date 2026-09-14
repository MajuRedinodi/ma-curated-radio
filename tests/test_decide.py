"""Track-change detection.

Every case here is one that happened. The rules are three lines long and
have been wrong four separate ways, so each is pinned to the symptom it
produced rather than to an abstraction of it.
"""

import pytest
from decide import (
    Decision,
    PlaybackSnapshot,
    QueueFacts,
    SkipLedger,
    decide,
    is_bulk_load,
    is_hunting,
    is_transitional,
    leading_pool,
    starts_station,
    track_started,
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
    assert call(QueueFacts(current_uri="track/new", items=1, remaining=0)) is (
        Decision.PICKED
    )


def test_a_big_foreign_queue_right_after_a_restart_is_not_a_pick():
    """The central case of the bulk-load rule, and it was untested.

    No previous count is the state immediately after a restart, so size
    has to stand alone and a large unfamiliar queue is left alone. Read
    as a pick instead, somebody's three hundred track playlist is thrown
    away and replaced the moment Home Assistant comes back.
    """
    playlist = QueueFacts(current_uri="track/new", items=300, remaining=299)
    assert (
        decide(
            playlist,
            expected_uri="track/expected",
            current_is_ours=False,
            next_is_ours=False,
            previous_items=None,
            bulk_threshold=3,
            refill_threshold=2,
        )
        is Decision.NOTHING
    )


def test_a_new_track_while_paused_has_not_started():
    assert not track_started("paused", "track/new", "track/old")


def test_a_song_that_ran_into_its_fade_out_was_played_not_skipped():
    """Nothing referenced was_skipped at all, and it is the input to both
    feedback rules: a false skip pushes a song off for thirty days and
    three of them mute the artist."""
    assert not PlaybackSnapshot(duration=240.0, elapsed=230.0).was_skipped(15.0)
    assert PlaybackSnapshot(duration=240.0, elapsed=100.0).was_skipped(15.0)


def test_without_a_duration_the_benefit_of_the_doubt_goes_to_played():
    assert not PlaybackSnapshot(duration=0.0, elapsed=5.0).was_skipped(15.0)


def test_skips_a_little_under_the_window_apart_stay_a_run():
    """Each skip has to move the clock on, not just the first.

    Leaving the mark where the run began makes the third skip of a slow
    hunt look like a considered verdict, which is how a kid holding the
    button suppresses a song for a month.
    """
    ledger = SkipLedger()
    ledger.skipped("a", now=0.0, window=30.0)
    ledger.skipped("b", now=25.0, window=30.0)
    assert ledger.skipped("c", now=50.0, window=30.0) == []
    assert ledger.played() == []


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


def test_a_pick_reported_in_two_steps_is_still_a_pick():
    """The phone player: new track while idle, then playing, same track.

    Compared update to update, neither step looked like a change, and a pick
    of "Rock You Like a Hurricane" from the car built no station.
    """
    last_playing = "track/long-long-time"
    # Step one, idle with the new track: not playing, so nothing yet.
    assert not track_started("idle", "track/hurricane", last_playing)
    # Step two, playing with the same new track: judged against what was
    # last heard playing, so it is a change.
    assert track_started("playing", "track/hurricane", last_playing)


def test_pause_and_resume_is_not_a_change():
    assert not track_started("playing", "track/a", "track/a")


def test_a_player_flapping_between_idle_and_playing_is_not_a_change():
    """Seen as the phone connected to the car: same song, four state flips."""
    for state in ("playing", "idle", "playing", "idle", "playing"):
        assert not track_started(state, "track/a", "track/a")


def test_a_lone_skip_is_a_verdict():
    """Nothing skipped before it, and nothing else close behind."""
    assert not is_hunting(None, 30.0)
    assert not is_hunting(600.0, 30.0)


def test_skips_seconds_apart_are_somebody_hunting():
    """Kids at 1am, holding next: neither song was ever heard."""
    assert is_hunting(11.0, 30.0)
    assert is_hunting(0.5, 30.0)


def test_a_pick_always_starts_a_station():
    assert starts_station(refilling=False, continuing=True)
    assert starts_station(refilling=False, continuing=False)


def test_a_refill_of_our_own_music_continues_the_station():
    """The whole point of the station memory: an evening is one station."""
    assert not starts_station(refilling=True, continuing=True)


def test_a_refill_onto_somebody_elses_music_starts_a_station():
    """Put a jazz album on at nine and its last track used to be followed
    by neighbours of the station that played at eight."""
    assert starts_station(refilling=True, continuing=False)


def test_a_skip_waits_for_the_next_verdict():
    """A lone skip is not recorded until something confirms it."""
    ledger = SkipLedger()
    assert ledger.skipped("song a", now=0.0, window=30.0) == []
    assert ledger.played() == ["song a"]


def test_a_later_skip_confirms_the_one_before_it():
    """Three deliberate skips are three verdicts, which is what makes
    muting an artist reachable at all."""
    ledger = SkipLedger()
    assert ledger.skipped("a", now=0.0, window=30.0) == []
    assert ledger.skipped("b", now=300.0, window=30.0) == ["a"]
    assert ledger.skipped("c", now=600.0, window=30.0) == ["b"]
    assert ledger.played() == ["c"]


def test_skips_seconds_apart_are_both_thrown_away():
    """Kids at 1am, holding next. Neither song was ever heard."""
    ledger = SkipLedger()
    assert ledger.skipped("a", now=0.0, window=30.0) == []
    assert ledger.skipped("b", now=11.0, window=30.0) == []
    assert ledger.played() == []


def test_a_long_run_records_nothing_at_all():
    ledger = SkipLedger()
    for at in (0.0, 5.0, 10.0, 15.0, 20.0):
        assert ledger.skipped("song", now=at, window=30.0) == []
    assert ledger.played() == []


def test_a_skip_after_a_run_is_judged_on_its_own():
    """The run ends when the listener stops hunting."""
    ledger = SkipLedger()
    ledger.skipped("a", now=0.0, window=30.0)
    ledger.skipped("b", now=5.0, window=30.0)
    assert ledger.skipped("c", now=900.0, window=30.0) == []
    assert ledger.played() == ["c"]


def test_playing_through_twice_records_nothing_the_second_time():
    ledger = SkipLedger()
    ledger.skipped("a", now=0.0, window=30.0)
    assert ledger.played() == ["a"]
    assert ledger.played() == []


def test_a_duet_is_judged_on_its_first_credit():
    """Home Assistant shows one joined string for a multi-credit song.

    Keyed on that, a skipped duet matched no artist Last.fm ever returns,
    so muting could not fire, and it counted as a different artist from
    the same singer solo, which reset the run that muting counts.
    """
    duet = PlaybackSnapshot(
        title="Meet Me in Montana",
        artist="Dan Seals/Marie Osmond",
        credits=["Dan Seals", "Marie Osmond"],
    )
    assert duet.credited == "Dan Seals"


def test_an_artist_whose_name_contains_a_slash_is_left_alone():
    """Which is why this reads the credits rather than splitting the
    string Home Assistant displays."""
    solo = PlaybackSnapshot(title="Back in Black", artist="AC/DC", credits=["AC/DC"])
    assert solo.credited == "AC/DC"


def test_without_credits_the_displayed_artist_is_used():
    unknown = PlaybackSnapshot(title="Something", artist="Someone")
    assert unknown.credited == "Someone"
