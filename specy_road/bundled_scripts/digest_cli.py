#!/usr/bin/env python3
"""CLI for the current-state digest: `specy-road digest`.

Writes one generated, git-tracked document summarising where the roadmap
actually stands. It is meant to be committed and indexed by the IDE *instead of*
the much larger duplicated corpus under `planning/`, `work/` and
`roadmap/archive/`.

`--check` is the CI drift gate, matching `specy-road export --check`: a digest
that has drifted from the graph is worse than no digest, because an agent will
believe it.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from specy_road.digest import DEFAULT_OUTPUT, render_digest
from specy_road.runtime_paths import add_repo_root_arg, resolve_repo_root


def cmd_digest(ns: argparse.Namespace) -> int:
    root = resolve_repo_root(ns)
    body = render_digest(root)

    if ns.output == "-":
        print(body, end="")
        return 0

    out = root / ns.output if not Path(ns.output).is_absolute() else Path(ns.output)
    if ns.check:
        if not out.is_file():
            print(
                f"missing {out} — run: specy-road digest",
                file=sys.stderr,
            )
            return 1
        if out.read_text(encoding="utf-8") != body:
            print(
                f"drift: {out} no longer matches the roadmap. "
                "Run: specy-road digest",
                file=sys.stderr,
            )
            return 1
        print(f"OK: {ns.output} matches the roadmap.")
        return 0

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(body, encoding="utf-8")
    print(f"Wrote {out} ({len(body.encode('utf-8'))} bytes)")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="specy-road digest",
        description=(
            "Generate a compact current-state summary of the roadmap for agents "
            "to read instead of crawling planning/ and work/."
        ),
    )
    p.add_argument(
        "-o",
        "--output",
        default=DEFAULT_OUTPUT,
        metavar="FILE",
        help=f"Where to write it, repo-relative (default: {DEFAULT_OUTPUT}). "
        "Use - for stdout.",
    )
    p.add_argument(
        "--check",
        action="store_true",
        help="Exit 1 if the file on disk has drifted from the graph (CI gate).",
    )
    add_repo_root_arg(p)
    p.set_defaults(func=cmd_digest)
    return p


def main(argv: list[str] | None = None) -> None:
    argv = list(sys.argv[1:] if argv is None else argv)
    # `specy-road digest …` forwards its own name; argparse defines it here.
    if argv and argv[0] == "digest":
        argv = argv[1:]
    ns = build_parser().parse_args(argv)
    try:
        raise SystemExit(ns.func(ns))
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        raise SystemExit(1) from e


if __name__ == "__main__":
    main()
