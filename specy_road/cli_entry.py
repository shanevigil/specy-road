"""Entry point for a bundled CLI that ``specy-road`` forwards a subcommand to.

``specy-road digest``, ``history`` and ``search`` each re-send their own name to
the script that implements them, so each script stripped it back off before
parsing. The three ``main`` functions were identical apart from that name.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable


def run_forwarded_cli(
    build_parser: Callable[[], argparse.ArgumentParser],
    command: str,
    argv: list[str] | None = None,
) -> None:
    """Parse ``argv`` (minus a leading ``command``) and run the chosen handler."""
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] == command:
        args = args[1:]
    ns = build_parser().parse_args(args)
    try:
        raise SystemExit(ns.func(ns))
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        raise SystemExit(1) from e
