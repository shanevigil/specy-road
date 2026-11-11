"""The end of a bundled command's ``main``: parse, run the chosen handler, exit with its status."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from pathlib import Path

from specy_road.git_workflow_config import resolve_integration_defaults


def run_cli(
    build_parser: Callable[[], argparse.ArgumentParser],
    argv: list[str] | None = None,
) -> None:
    """Parse ``argv`` (default ``sys.argv[1:]``) and exit with the chosen handler's status."""
    ns = build_parser().parse_args(list(sys.argv[1:] if argv is None else argv))
    raise SystemExit(ns.func(ns))


def run_handler(ns: argparse.Namespace) -> None:
    """Exit with ``ns``'s handler's status; a ``ValueError`` is one ``error:`` line and status 1."""
    try:
        raise SystemExit(ns.func(ns))
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        raise SystemExit(1) from e


def integration_defaults(root: Path, ns: argparse.Namespace) -> tuple[str, str]:
    """``--base`` and ``--remote``, else the configured defaults, with any warning on stderr."""
    base, remote, warnings = resolve_integration_defaults(
        root, explicit_base=ns.base, explicit_remote=ns.remote
    )
    for w in warnings:
        print(f"warning: {w}", file=sys.stderr)
    return base, remote
