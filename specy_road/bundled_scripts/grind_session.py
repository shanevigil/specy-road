#!/usr/bin/env python3
"""``specy-road grind-session`` — orchestrate the task loop over many leaves.

The command entry: :func:`build_parser` and the argument rules live in ``grind_session_args``; the
loop, its steps and its plan live in :mod:`specy_road.orchestration.grind`.
"""

from __future__ import annotations

from specy_road.bundled_scripts.grind_session_args import build_parser, parse_grind_session_args
from specy_road.orchestration import run_session

__all__ = ["build_parser", "main"]


def main(argv: list[str] | None = None) -> None:
    """Parse ``argv`` and exit with the session's exit code."""
    args = parse_grind_session_args(argv)
    raise SystemExit(run_session(args))


if __name__ == "__main__":
    main()
