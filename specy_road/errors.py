"""Command failures the CLI prints once and turns into an exit code."""

from __future__ import annotations

import sys


class SpecyError(Exception):
    """A command failure: the text, and the process status it exits with.

    ``SpecyError(message, exit_code)`` takes both. A command error that used to
    be a bare ``Exception``, ``ValueError`` or ``RuntimeError`` keeps that
    constructor: any positional arguments the old base accepted, and exit code 1
    (:func:`inherited_init`). ``ConstitutionExistsError`` keeps the arguments it
    already took.
    """

    def __init__(self, message, exit_code):
        super().__init__(message)
        self.exit_code = exit_code


def inherited_init(self, *args):
    """Positional arguments the previous base accepted, with exit code 1.

    No keyword arguments, matching ``Exception``. A subclass that is also a
    ``ValueError`` or ``RuntimeError`` still is. The command entry prints it
    with this exit code; it does not rewrite the code to 1.
    """
    super(SpecyError, self).__init__(*args)
    self.exit_code = 1


def exit_for(error: SpecyError) -> None:
    """Print ``error`` and stop with its code.

    This is the one place a command error is printed and turned into a status.
    It lives here so a command that only needs the type does not import the
    entry module and the git-workflow modules under it.
    """
    print(f"error: {error}", file=sys.stderr)
    raise SystemExit(error.exit_code) from None
