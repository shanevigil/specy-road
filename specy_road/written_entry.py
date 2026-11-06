"""One line of a refresh/init report, carried as data: the path and what happened to it.

The report used to be a list of display strings (``"<path> (<outcome>)"``) that
the printer split back apart with ``partition(" (")``, which truncated any path
containing `` (``. :class:`Written` keeps the path and the outcome separately and
formats the display string once, so every existing caller that compares, joins
or prints the entries as strings still works, and a printer that needs the
path reads :attr:`Written.path` instead of parsing.
"""

from __future__ import annotations


class Written(str):
    """``"<path>"`` or ``"<path> (<outcome>)"``, with ``path`` and ``outcome`` kept as fields."""

    path: str
    outcome: str

    def __new__(cls, path: str, outcome: str = "") -> "Written":
        self = super().__new__(cls, f"{path} ({outcome})" if outcome else path)
        self.path = path
        self.outcome = outcome
        return self
