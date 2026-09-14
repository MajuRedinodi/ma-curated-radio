"""Track selection.

The filter chain that decides what actually goes in a batch. Most of the
listening complaints this integration has had were about individual
tracks getting through it, so each rule is pinned to the track that
prompted it.
"""

from dataclasses import dataclass, field

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


def test_karaoke_is_not_music():
    """Tidal surfaces these. Searching for Tom Petty returned one.

    The imitation act is credited to the artist it imitates, so only the
    title marker can reject it. Crediting the karaoke act as well let the
    artist check do the work and left the marker untested.
    """
    tracks = [
        Track(
            "t1",
            "Mary Jane's Last Dance (Made Popular By Tom Petty)",
            artists=["Tom Petty"],
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
    heard = {"the boys of summer": 100.0, "dirty laundry": 200.0}
    assert fresh(_HENLEY, heard, limit=2) == ["t3", "t4"]


def test_heard_songs_fill_in_when_nothing_fresh_is_left():
    """Better a song from this morning than an artist with no pool."""
    heard = {
        "the boys of summer": 100.0,
        "dirty laundry": 200.0,
        "the end of the innocence": 300.0,
    }
    assert fresh(_HENLEY, heard, limit=2) == ["t4", "t1"]


def test_the_repeat_window_still_wins_over_heard():
    """Inside the short window a song is not played at all."""
    heard = {
        "the boys of summer": 100.0,
        "dirty laundry": 200.0,
        "the end of the innocence": 300.0,
    }
    chosen = fresh(_HENLEY, heard, limit=2, excluded_titles={"the boys of summer"})
    assert chosen == ["t4", "t2"]


def test_repeats_start_with_whatever_was_heard_longest_ago():
    """Not with the biggest song, which played four times in one day."""
    heard = {
        "the boys of summer": 400.0,
        "dirty laundry": 100.0,
        "the end of the innocence": 200.0,
        "all she wants to do is dance": 300.0,
    }
    assert fresh(_HENLEY, heard, limit=2) == ["t2", "t3"]


def test_fill_ins_keep_the_providers_order_among_themselves():
    """Which repeats to use is one question, what order to play them another.

    Age picks them: the two heard longest ago are the third and second
    tracks, in that order. The provider's ranking then lays them out, so
    they come back second-then-third. The existing age test cannot see
    the difference, because there its two answers agree.
    """
    heard = {
        "the boys of summer": 300.0,
        "dirty laundry": 200.0,
        "the end of the innocence": 100.0,
        "all she wants to do is dance": 400.0,
    }
    assert fresh(_HENLEY, heard, limit=2) == ["t2", "t3"]


def test_the_fill_in_pass_does_not_repeat_a_fresh_title_under_another_uri():
    """A remaster is the same song, and it must not come back as a fill-in.

    The fresh pass takes the song; the fill-in pass, working on URIs,
    could then take the remaster of it and put the same record in one
    batch twice.
    """
    tracks = [
        Track("t1", "Song"),
        Track("t2", "Song - Remastered"),
        Track("t3", "Other"),
    ]
    assert fresh(tracks, {"other": 1.0}, limit=2) == ["t1", "t3"]


def test_a_medley_title_is_the_same_song():
    """Chicago's "Hard to Say I'm Sorry / Get Away", twice in one batch."""
    tracks = [
        Track("t1", "Hard to Say I'm Sorry / Get Away"),
        Track("t2", "Hard to Say I'm Sorry"),
    ]
    assert uris(tracks) == ["t1"]


def test_remixes_are_kept_unless_asked_otherwise():
    """A remix is sometimes the version people know."""
    tracks = [Track("t1", "Cold Heart", version="PNAU Remix")]
    assert uris(tracks) == ["t1"]


def test_remixes_are_skipped_when_the_switch_is_on():
    rules = SelectionRules(skip_remix=True)
    tracks = [
        Track("t1", "Cold Heart", version="PNAU Remix"),
        Track("t2", "Blue Monday (Club Mix)"),
        Track("t3", "Sacrifice"),
    ]
    assert uris(tracks, rules) == ["t3"]


def test_an_ordinary_mix_is_not_a_remix():
    """Half the catalogue is an album or single mix of the known record."""
    rules = SelectionRules(skip_remix=True)
    tracks = [Track("t1", "Renegade", version="Album Mix")]
    assert uris(tracks, rules) == ["t1"]
