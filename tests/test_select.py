"""Track selection.

The filter chain that decides what actually goes in a batch. Most of the
listening complaints this integration has had were about individual
tracks getting through it, so each rule is pinned to the track that
prompted it.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime

from filters import SelectionRules, select_fresh_first, select_tracks


@dataclass
class Track:
    """Enough of a Music Assistant track to be selected or rejected."""

    uri: str
    name: str
    version: str = ""
    album: str = ""
    duration: int = 240
    explicit: bool = False
    artists: list[str] = field(default_factory=list)
    popularity: int = 0
    released: datetime | None = None


def uris(tracks, rules=None, **kwargs):
    chosen, _ = select_tracks(tracks, rules or SelectionRules(), **kwargs)
    return chosen


def test_a_plain_track_is_selected():
    assert uris([Track("t1", "Renegade")]) == ["t1"]


def test_the_track_playing_now_is_never_re_queued():
    assert uris([Track("t1", "Renegade")], current_uri="t1") == []


def test_live_recordings_are_skipped():
    """They rank high in popularity searches and suit nobody's evening."""
    tracks = [Track("t1", "The Chain (Live at Wembley)"), Track("t2", "The Chain")]
    assert uris(tracks) == ["t2"]


def test_alive_is_not_a_live_recording():
    """Tokenising on non-alphanumerics, so Living on a Prayer survives."""
    assert uris([Track("t1", "Alive")]) == ["t1"]
    assert uris([Track("t1", "Living on a Prayer")]) == ["t1"]


def test_holiday_tracks_are_skipped_by_album_as_well_as_title():
    """A popularity ranking surfaces a Christmas album in September."""
    tracks = [Track("t1", "Silver Bells", album="A Very Merry Christmas")]
    assert uris(tracks) == []


def test_commentary_is_skipped_even_when_it_runs_long():
    """Taylor Swift's Track by Track entries chart alongside the songs."""
    tracks = [Track("t1", "Anti-Hero - Track by Track", duration=300)]
    assert uris(tracks) == []


def test_anything_too_brief_to_be_a_song_is_skipped():
    tracks = [Track("t1", "Interlude Two", duration=40)]
    assert uris(tracks, SelectionRules(min_duration=90)) == []


def test_an_unknown_duration_gets_the_benefit_of_the_doubt():
    tracks = [Track("t1", "Renegade", duration=0)]
    assert uris(tracks, SelectionRules(min_duration=90)) == ["t1"]


def test_the_same_song_is_not_queued_twice_under_two_titles():
    """A remaster and a radio edit collapse onto one title."""
    tracks = [
        Track("t1", "The Chain - 2001 Remaster"),
        Track("t2", "The Chain (Radio Edit)"),
    ]
    assert uris(tracks) == ["t1"]


def test_a_track_by_an_artist_already_in_the_batch_is_left_to_them():
    """Jeff Lynne and Electric Light Orchestra are the same act.

    A track credited to both is not a second artist for the run cap to
    space out, and treating it as one put three in a row.
    """
    tracks = [
        Track("t1", "When I Was a Boy", artists=["Jeff Lynne", "ELO"]),
        Track("t2", "She", artists=["Jeff Lynne"]),
    ]
    assert uris(tracks, excluded_artists={"elo"}) == ["t2"]


def test_clean_only_drops_explicit_tracks():
    tracks = [Track("t1", "Fuck You", explicit=True), Track("t2", "Forget You")]
    assert uris(tracks, SelectionRules(clean_only=True)) == ["t2"]


def test_preferring_explicit_reorders_rather_than_filters():
    """A clean edit is a separate release with its own title.

    Nothing marks it as a version of the original, so the explicit one is
    sorted ahead and the edit falls outside the cut instead.
    """
    tracks = [Track("t1", "Forget You"), Track("t2", "Fuck You", explicit=True)]
    assert uris(tracks, SelectionRules(prefer_explicit=True), limit=1) == ["t2"]


def test_the_provider_filter_keeps_a_batch_on_one_service():
    tracks = [Track("tidal://track/1", "A"), Track("qobuz://track/2", "B")]
    assert uris(tracks, SelectionRules(provider="tidal")) == ["tidal://track/1"]


def test_a_limit_cuts_the_list():
    tracks = [Track(f"t{i}", f"Song {i}") for i in range(5)]
    assert len(uris(tracks, limit=2)) == 2


def test_a_hot_new_release_is_promoted_when_the_data_exists():
    """Provider rankings are cumulative, so a new hit sits below years."""
    now = datetime(2026, 9, 9, tzinfo=UTC)
    tracks = [
        Track("old", "An Old Hit", popularity=90),
        Track(
            "new",
            "A New Hit",
            popularity=95,
            released=datetime(2026, 9, 1, tzinfo=UTC),
        ),
    ]
    assert uris(tracks, SelectionRules(fresh_days=120), limit=1, now=now) == ["new"]


def test_without_release_dates_the_provider_ordering_is_untouched():
    """Tidal reports neither popularity nor release date, so this is a
    no-op in practice and must stay one."""
    now = datetime(2026, 9, 9, tzinfo=UTC)
    tracks = [Track("t1", "First"), Track("t2", "Second")]
    assert uris(tracks, SelectionRules(fresh_days=120), now=now) == ["t1", "t2"]


def test_karaoke_is_not_music():
    """Tidal surfaces these. Searching for Tom Petty returned one."""
    tracks = [
        Track(
            "t1",
            "Mary Jane's Last Dance (Made Popular By Tom Petty)",
            artists=["Party Tyme Karaoke"],
        ),
        Track("t2", "Mary Jane's Last Dance", artists=["Tom Petty"]),
    ]
    assert uris(tracks) == ["t2"]


def test_a_karaoke_act_is_caught_by_its_own_name():
    tracks = [Track("t1", "Free Fallin'", artists=["The Karaoke Channel"])]
    assert uris(tracks) == []


def test_a_real_cover_is_still_welcome():
    """Shawn Colvin's Baker Street was the best thing in its batch."""
    tracks = [Track("t1", "Baker Street", artists=["Shawn Colvin", "David Crosby"])]
    assert uris(tracks) == ["t1"]


def test_a_demo_is_not_one_of_the_hits():
    """.38 Special's "F2D", from an album called "Demo 2", opened an hour."""
    tracks = [
        Track("t1", "F2D", album="Demo 2", artists=[".38 Special"]),
        Track("t2", "Hold On Loosely", artists=[".38 Special"]),
    ]
    assert uris(tracks) == ["t2"]


def test_words_that_merely_start_with_demo_are_left_alone():
    tracks = [
        Track("t1", "Demolition Man", artists=["The Police"]),
        Track("t2", "Democracy", artists=["Leonard Cohen"]),
    ]
    assert uris(tracks) == ["t1", "t2"]


def fresh(tracks, heard, **kwargs):
    chosen, _ = select_fresh_first(tracks, SelectionRules(), heard=heard, **kwargs)
    return chosen


_HENLEY = [
    Track("t1", "The Boys of Summer"),
    Track("t2", "Dirty Laundry"),
    Track("t3", "The End of the Innocence"),
    Track("t4", "All She Wants to Do Is Dance"),
]


def test_songs_heard_today_wait_while_the_artist_has_fresh_ones():
    """The 11:08 refill that replayed the first hour."""
    heard = {"the boys of summer", "dirty laundry"}
    assert fresh(_HENLEY, heard, limit=2) == ["t3", "t4"]


def test_heard_songs_fill_in_when_nothing_fresh_is_left():
    """Better a song from this morning than an artist with no pool."""
    heard = {"the boys of summer", "dirty laundry", "the end of the innocence"}
    assert fresh(_HENLEY, heard, limit=2) == ["t4", "t1"]


def test_the_repeat_window_still_wins_over_heard():
    """Inside the short window a song is not played at all."""
    heard = {"the boys of summer", "dirty laundry", "the end of the innocence"}
    chosen = fresh(_HENLEY, heard, limit=2, excluded_titles={"the boys of summer"})
    assert chosen == ["t4", "t2"]
