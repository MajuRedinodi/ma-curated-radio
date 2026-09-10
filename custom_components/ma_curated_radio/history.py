"""Time-windowed memory of recently queued track titles.

The YAML implementation approximated this with three ``input_text`` helpers
shifted like a ring buffer, because a single helper caps at 255 characters.
Nothing here is stored in an entity, so a real time window replaces the
three-batch approximation: a title is excluded until it ages out.
"""

from __future__ import annotations

from collections import deque
from datetime import datetime, timedelta

from homeassistant.util import dt as dt_util


class TitleHistory:
    """Normalised track titles seen recently, pruned by age."""

    def __init__(self, window_minutes: int) -> None:
        """Set up an empty history with the given retention window."""
        self._window = timedelta(minutes=window_minutes)
        self._items: deque[tuple[str, datetime]] = deque()

    @property
    def window_minutes(self) -> int:
        """Retention window in whole minutes."""
        return int(self._window.total_seconds() // 60)

    def prune(self) -> None:
        """Drop everything older than the retention window."""
        cutoff = dt_util.utcnow() - self._window
        while self._items and self._items[0][1] < cutoff:
            self._items.popleft()

    def add(self, titles: list[str]) -> None:
        """Record a batch's titles as seen now."""
        now = dt_util.utcnow()
        self._items.extend((title, now) for title in titles)
        self.prune()

    def current(self) -> set[str]:
        """Return the set of titles still inside the window."""
        self.prune()
        return {title for title, _ in self._items}

    def __len__(self) -> int:
        """Number of remembered titles still inside the window."""
        self.prune()
        return len(self._items)

    def set_window(self, minutes: int) -> None:
        """Change the retention window, keeping what still fits."""
        self._window = timedelta(minutes=minutes)
        self.prune()

    def clear(self) -> None:
        """Forget everything."""
        self._items.clear()

    def as_list(self) -> list[list[str]]:
        """A form that survives a restart: pairs of title and ISO time."""
        self.prune()
        return [[title, when.isoformat()] for title, when in self._items]

    def restore(self, saved: list[list[str]] | None) -> None:
        """Put back what was saved, dropping anything malformed or aged out.

        Without this a restart forgot the last two hours, so the first
        batch afterwards could queue the songs that had just played.
        """
        items: list[tuple[str, datetime]] = []
        for entry in saved or []:
            try:
                title, when = entry
                items.append((str(title), datetime.fromisoformat(when)))
            except (TypeError, ValueError):
                continue
        items.sort(key=lambda pair: pair[1])
        self._items = deque(items)
        self.prune()
