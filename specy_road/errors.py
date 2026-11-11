"""Command failures the CLI prints once and turns into an exit code."""

from __future__ import annotations


class SpecyError(Exception):
    """A command failure: the text, and the process status it exits with.

    The command errors subclass this and keep the constructors they already
    had. ``exit_code`` is the status; those constructors do not take it.
    """

    def __init__(self, message, exit_code):
        super().__init__(message)
        self.exit_code = exit_code
