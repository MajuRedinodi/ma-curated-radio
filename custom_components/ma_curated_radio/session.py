"""How far a listening session has wandered from where it started.

Reseeding off whatever is playing is what lets an evening drift instead of
repeating one batch. Left unbounded it compounds: an observed build went
Taylor Swift, Maisie Peters, Lorde, Katy Perry, Ke$ha, Selena Gomez,
Anitta, in twenty-four tracks. Every hop defensible, the destination not.

The fence is degrees of separation from the artist that started the
session, in the Six Degrees of Kevin Bacon sense. Similar artists of the
origin are one degree out, their similars two, and so on. Past the cap, an
artist is only eligible if some shorter path already put it inside.

That last rule is what keeps the fence from strangling the station. At the
edge, the eligible set becomes "artists similar to what is playing that
are also still within the cap of the origin" — an intersection that falls
out of the rule rather than being imposed on top of it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta


def _now() -> datetime:
    """Current UTC time.

    Stdlib rather than homeassistant.util.dt on purpose: nothing else in
    this module needs Home Assistant, and keeping it out means the drift
    rules can be tested without it.
    """
    return datetime.now(UTC)


@dataclass(slots=True)
class ListeningSession:
    """The artists reachable from one origin, and how far out each is."""

    origin: str = ""
    degrees: dict[str, int] = field(default_factory=dict)
    last_active: datetime = field(default_factory=_now)

    @classmethod
    def start(cls, origin: str) -> ListeningSession:
        """Begin a session anchored to one artist."""
        return cls(origin=origin, degrees={origin.lower(): 0})

    @property
    def active(self) -> bool:
        """True once an origin has been established."""
        return bool(self.origin)

    def is_stale(self, expiry_hours: int) -> bool:
        """True if nothing has happened for long enough to start over."""
        return _now() - self.last_active > timedelta(hours=expiry_hours)

    def touch(self) -> None:
        """Mark the session as still in use."""
        self.last_active = _now()

    def degree_of(self, artist: str) -> int | None:
        """How far an artist is from the origin, or None if unknown."""
        return self.degrees.get(artist.lower())

    def admit(self, artist: str, degree: int) -> None:
        """Record an artist at a degree, keeping the shortest path found."""
        key = artist.lower()
        known = self.degrees.get(key)
        if known is None or degree < known:
            self.degrees[key] = degree

    def eligible(
        self, parent: str, candidates: list[str], cap: int | None
    ) -> list[str]:
        """Filter candidates to those still inside the fence.

        ``cap`` of None means no fence at all. Accepted candidates are
        recorded so a later round can recognise them as already inside,
        which is what lets the walk circulate near the edge rather than
        dead-ending there.
        """
        parent_degree = self.degree_of(parent)
        if parent_degree is None:
            # Reached somewhere the session never sanctioned, so treat it
            # as the frontier rather than as free ground.
            parent_degree = cap if cap is not None else 0
        next_degree = parent_degree + 1

        allowed: list[str] = []
        for name in candidates:
            known = self.degree_of(name)
            if known is not None and (cap is None or known <= cap):
                allowed.append(name)
                continue
            if cap is not None and next_degree > cap:
                continue
            self.admit(name, next_degree)
            allowed.append(name)
        return allowed
