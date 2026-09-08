"""Drift fence tests.

The rule these check is the one that keeps a station recognisable: an
observed build ran Taylor Swift, Maisie Peters, Lorde, Katy Perry, Ke$ha,
Selena Gomez, Anitta in twenty-four tracks.
"""

from session import ListeningSession


def test_origin_is_degree_zero():
    s = ListeningSession.start("Taylor Swift")
    assert s.degree_of("taylor swift") == 0
    assert s.active


def test_admits_within_the_cap_and_records_degrees():
    s = ListeningSession.start("Taylor Swift")
    assert s.eligible("Taylor Swift", ["Maisie Peters"], 3) == ["Maisie Peters"]
    assert s.degree_of("Maisie Peters") == 1
    assert s.eligible("Maisie Peters", ["Lorde"], 3) == ["Lorde"]
    assert s.degree_of("Lorde") == 2


def test_stops_the_walk_at_the_cap():
    s = ListeningSession.start("Taylor Swift")
    chain = ["Maisie Peters", "Lorde", "Katy Perry"]
    parent = "Taylor Swift"
    for name in chain:
        assert s.eligible(parent, [name], 3) == [name]
        parent = name
    # Katy Perry sits at 3, so Ke$ha would be 4 and never gets in.
    assert s.eligible("Katy Perry", ["Ke$ha"], 3) == []
    assert s.degree_of("Ke$ha") is None


def test_edge_still_admits_artists_already_inside():
    """At the fence the eligible set becomes an intersection, not nothing."""
    s = ListeningSession.start("Taylor Swift")
    s.admit("Lorde", 2)
    s.admit("Katy Perry", 3)
    # From the frontier, a degree-4 newcomer is refused but Lorde is not.
    assert s.eligible("Katy Perry", ["Ke$ha", "Lorde"], 3) == ["Lorde"]


def test_keeps_the_shortest_path():
    s = ListeningSession.start("Taylor Swift")
    s.admit("Lorde", 3)
    s.admit("Lorde", 1)
    assert s.degree_of("Lorde") == 1


def test_discovery_has_no_fence():
    s = ListeningSession.start("Vivaldi")
    parent = "Vivaldi"
    for name in ["A", "B", "C", "D", "E", "Metallica"]:
        assert s.eligible(parent, [name], None) == [name]
        parent = name


def test_unknown_parent_is_treated_as_the_frontier():
    """Somewhere the session never sanctioned cannot become free ground."""
    s = ListeningSession.start("Taylor Swift")
    assert s.eligible("Some Stranger", ["Metallica"], 3) == []
