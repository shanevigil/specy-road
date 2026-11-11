#!/usr/bin/env python3
"""Generate a comprehensive work-packet brief for a roadmap node."""

from __future__ import annotations

import argparse
from pathlib import Path

from specy_road.brief_acceptance import print_size_warning
from specy_road.brief_generation import (
    __doc__ as _BRIEF_DOC,
    index,
    load_nodes,
    render_brief,
)
from specy_road.runtime_paths import add_repo_root_arg, default_user_repo_root
from specy_road.verify_cmd_config import verify_cmd_lines

__all__ = [
    "_chain_sheet_paths",
    "ancestors",
    "index",
    "load_nodes",
    "render_brief",
    "verify_cmd_lines",
]

from specy_road.brief_generation import (  # noqa: E402 — re-export after __all__
    _chain_sheet_paths,
    ancestors,
)


def build_parser() -> argparse.ArgumentParser:
    """The ``specy-road brief`` parser."""
    p = argparse.ArgumentParser(description=_BRIEF_DOC.split("The CLI entry point", 1)[0].strip())
    p.add_argument("node_id", help="Roadmap node id, e.g. M1.1")
    p.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Write markdown to this file (default: stdout)",
    )
    add_repo_root_arg(p)
    p.add_argument(
        "--no-history",
        action="store_true",
        help="Omit the git-derived history section (## 9).",
    )
    p.add_argument(
        "--all-contracts",
        action="store_true",
        help=(
            "Inline every shared/**/*.md instead of only those cited in the "
            "planning chain's `## References`. Restores pre-0.2.1 behaviour."
        ),
    )
    return p


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    root = (args.repo_root or default_user_repo_root()).resolve()

    nodes = load_nodes(root)
    by_id = index(nodes)
    if args.node_id not in by_id:
        raise SystemExit(f"unknown node id: {args.node_id}")

    text = render_brief(
        args.node_id,
        by_id,
        repo_root=root,
        include_history=not args.no_history,
        all_contracts=args.all_contracts,
    )
    print_size_warning(text)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
        print(f"Wrote {args.output}")
    else:
        print(text, end="")


if __name__ == "__main__":
    main()
