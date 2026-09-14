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

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


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


def is_transitional(queue: QueueFacts) -> bool:
    """True while a queue is between tracks and says nothing yet.

    A queue being replaced reports no current track for a moment. Read as
    a track change, that blank looked like a pick: nothing played was ours
    and nothing matched the expectation. The run it started found no
    artist to build from and gave up, and the real pick arriving a moment
    later was then compared against an expectation taken from the blank,
    so it was never recognised either. Observed on a phone player: a
    second pick, "Walk This Way", was left as a queue of one song.

    Such a reading is not a decision at all. The caller should ignore it
    entirely and keep the expectation it already had.
    """
    return not queue.current_uri


def track_started(state: str, track: str | None, last_playing: str | None) -> bool:
    """True when a player is playing a different track from the last one heard.

    Compared against the last track seen *playing*, not against whatever
    the previous update said. The phone player reports a pick in two
    steps: the new track arrives on an update that still says idle, and
    playing follows on a second update with the track unchanged. Compared
    update to update, the first was not playing and the second changed
    nothing, so a pick of "Rock You Like a Hurricane" from the car built
    no station at all. A pause and resume of the same song is still no
    change.
    """
    return state == "playing" and track != last_playing


def starts_station(*, refilling: bool, continuing: bool) -> bool:
    """True when this batch begins a station rather than continuing one.

    A pick always does. So does a refill onto music that is not ours:
    somebody put an album on, and topping it up should follow the album
    rather than resume the station that happened to play before it.

    What follows from it: the session re-anchors, the previous batch is
    not reseeded from, the credit is resolved afresh, and the song playing
    goes into repeat memory.
    """
    return not refilling or not continuing


@dataclass(slots=True)
class PlaybackSnapshot:
    """Enough of a media_player state to judge whether a track was skipped."""

    uri: str = ""
    title: str = ""
    artist: str = ""
    # The credits as the provider lists them. Home Assistant joins them
    # into one string for display, and that string is not an artist: a
    # skipped duet keyed on "Dan Seals/Marie Osmond" matched no Last.fm
    # name, so muting never fired, and it counted as a different artist
    # from Dan Seals, which reset the run of skips that muting counts.
    credits: list[str] = field(default_factory=list)
    duration: float = 0.0
    elapsed: float = 0.0

    @property
    def credited(self) -> str:
        """The artist to judge, which is the first credit.

        Falls back to the string Home Assistant displays where the credits
        are unknown, which is any player whose queue could not be read.
        Splitting that string instead would be wrong for AC/DC.
        """
        return self.credits[0] if self.credits else self.artist

    def was_skipped(self, grace_seconds: float) -> bool:
        """True if the track was cut short rather than allowed to finish.

        Without a duration there is nothing to compare against, so the
        benefit of the doubt goes to "played".
        """
        if self.duration <= 0:
            return False
        return self.elapsed < self.duration - grace_seconds


@dataclass(slots=True)
class SkipLedger:
    """Which skips are verdicts on a song, and which are somebody hunting.

    A skip means "not this one", but a run of them seconds apart means
    somebody is looking for something, and says nothing about anything
    passed over on the way. So a skip is held until the listener's next
    verdict: another skip close behind throws both away, a later one
    confirms it, and a song played through confirms it too.

    Holding them is what makes muting an artist reachable. Committing a
    skip only when a song later played through, and resetting the run at
    the same moment, left the run permanently at one.
    """

    pending: Any = None
    last_at: float | None = None

    def played(self) -> list[Any]:
        """A song was allowed to play. Returns skips to record now."""
        return self._take()

    def skipped(self, outgoing: Any, now: float, window: float) -> list[Any]:
        """A song was skipped. Returns skips to record now.

        ``window`` is how close together two skips have to be to count as
        hunting rather than judging.
        """
        hunting = is_hunting(
            None if self.last_at is None else now - self.last_at, window
        )
        self.last_at = now
        if hunting:
            self.pending = None
            return []
        confirmed = self._take()
        self.pending = outgoing
        return confirmed

    def _take(self) -> list[Any]:
        """Hand over whatever was waiting, and stop waiting for it."""
        pending, self.pending = self.pending, None
        return [pending] if pending is not None else []


def is_hunting(since_last_skip: float | None, window: float) -> bool:
    """True when a skip is part of a run rather than a verdict on one song.

    Somebody holding the next button skips songs they never heard. Two of
    those at one in the morning, from a house full of kids, suppressed two
    songs for a month each. ``None`` means no skip has been seen yet, which
    cannot be a run.
    """
    return since_last_skip is not None and since_last_skip < window


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
    if in_cooldown or is_transitional(queue):
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


def leading_pool(
    pool_artists: list[str],
    playing_artists: list[str],
    *,
    lands_next: bool,
) -> int | None:
    """Which pool, if any, has effectively played once already.

    A batch is sequenced in isolation and cannot see the track it will be
    played after, so without this a pick and the two tracks following it
    are three in a row by one artist, each step of which looks legal.
    Returns the index the sequencer should count as having just played,
    or None when the batch does not join onto the current track.

    ``lands_next`` is a statement about where the batch goes rather than
    how it was triggered. A replace always lands immediately after the
    current track. A refill usually does not, since it joins the end of a
    populated queue, but it does when the queue has run dry, which is
    both the natural end of a batch and what the first pick after a
    restart looks like.

    Matched against every name the current track credits, not just the
    first. The first credit is what seeds a batch, but a pool can be led
    by any of them, and this comparison failing silently costs the whole
    guard rather than failing loudly.
    """
    if not lands_next:
        return None
    playing = {name.strip().lower() for name in playing_artists if name}
    if not playing:
        return None
    for position, name in enumerate(pool_artists):
        if name.strip().lower() in playing:
            return position
    return None
