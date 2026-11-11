"""The end of a bundled command's ``main``: parse, run the chosen handler, exit with its status."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from pathlib import Path

from specy_road.errors import SpecyError
from specy_road.git_workflow_config import resolve_integration_defaults


def exit_for(error: SpecyError) -> None:
    """Print ``error`` and stop with its code.

    This is the one place a command error is printed and turned into a status.
    """
    print(f"error: {error}", file=sys.stderr)
    raise SystemExit(error.exit_code) from None


def run_reporting(func: Callable[[], None]) -> None:
    """Call ``func``. A :class:`SpecyError` is printed once and exits with its code."""
    try:
        func()
    except SpecyError as error:
        exit_for(error)


def run_cli(
    build_parser: Callable[[], argparse.ArgumentParser],
    argv: list[str] | None = None,
) -> None:
    """Parse ``argv`` (default ``sys.argv[1:]``) and exit with the chosen handler's status.

    A :class:`SpecyError` from the handler is printed once and exits with its code.
    """
    run_reporting(lambda: _parse_and_exit(build_parser, argv))


def _parse_and_exit(
    build_parser: Callable[[], argparse.ArgumentParser],
    argv: list[str] | None,
) -> None:
    ns = build_parser().parse_args(list(sys.argv[1:] if argv is None else argv))
    raise SystemExit(ns.func(ns))


def run_handler(ns: argparse.Namespace) -> None:
    """Exit with ``ns``'s handler's status.

    A :class:`SpecyError` is printed once with its own exit code, including one
    that is also a ``ValueError``. Any other ``ValueError`` is one ``error:``
    line and status 1.
    """
    try:
        run_reporting(lambda: _handler_status(ns))
    except ValueError as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(1) from error


def _handler_status(ns: argparse.Namespace) -> None:
    raise SystemExit(ns.func(ns))


def integration_defaults(root: Path, ns: argparse.Namespace) -> tuple[str, str]:
    """``--base`` and ``--remote``, else the configured defaults, with any warning on stderr."""
    base, remote, warnings = resolve_integration_defaults(
        root, explicit_base=ns.base, explicit_remote=ns.remote
    )
    for w in warnings:
        print(f"warning: {w}", file=sys.stderr)
    return base, remote
