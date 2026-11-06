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
import os
import sys
from pathlib import Path

from specy_road import safe_write
from specy_road.digest import DEFAULT_OUTPUT, render_digest
from specy_road.generated_files import gitignore_resolution_hint
from specy_road.runtime_paths import add_repo_root_arg, git_root, resolve_repo_root
from specy_road.cli_entry import run_forwarded_cli


def _print_gitignore_hint(root: Path, name: str) -> None:
    """Name the ignore rule when it is the reason ``--check`` cannot pass.

    Regenerating fixes drift only if the result can be committed. A gitignored
    and untracked digest fails this gate forever, and the message that says
    "run: specy-road digest" is the one thing that will not help.
    """
    hint = gitignore_resolution_hint(root, name)
    if hint:
        print(f"  {hint}", file=sys.stderr)


def _write_output(root: Path, output: str, out: Path, body: str) -> None:
    """Write the digest to ``out``: by the safe-write rule from the checkout, unless ``output`` is absolute and outside it.

    The default, a relative ``-o``, or an absolute one at or under the checkout
    (compared lexically with the resolved checkout, which includes the checkout
    itself) go through the rule as given, so a ``..`` above the checkout is
    refused. An explicit absolute path outside the checkout is the person's own.
    """
    checkout = git_root(root) or root   # both resolved
    if Path(output).is_absolute() and not Path(os.path.normpath(out)).is_relative_to(checkout):
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(body, encoding="utf-8")
        return
    safe_write.write(checkout, out, body)


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
            _print_gitignore_hint(root, ns.output)
            return 1
        if out.read_text(encoding="utf-8") != body:
            print(
                f"drift: {out} no longer matches the roadmap. "
                "Run: specy-road digest",
                file=sys.stderr,
            )
            _print_gitignore_hint(root, ns.output)
            return 1
        print(f"OK: {ns.output} matches the roadmap.")
        return 0

    with safe_write.exit_on_refusal():
        _write_output(root, ns.output, out, body)
    print(f"Wrote {out} ({len(body.encode('utf-8'))} bytes)")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="specy-road digest",
        description=(
            "Generate a compact current-state summary of the roadmap for agents "
            "to read instead of crawling planning/ and work/. "
            "roadmap-context.md is generated AND committed, exactly like "
            "roadmap.md: agents read it out of the tree they clone, so it must "
            "be tracked. Regenerate it whenever the graph changes and gate CI "
            "on --check, the way you gate on export --check."
        ),
    )
    p.add_argument(
        "-o",
        "--output",
        default=DEFAULT_OUTPUT,
        metavar="FILE",
        help=f"Where to write it, repo-relative (default: {DEFAULT_OUTPUT}). "
        "Use - for stdout. A relative path, or an absolute one at or under the checkout (compared "
        "lexically with the resolved checkout), refuses any symlink on the way; an absolute path outside the checkout "
        "is written as given.",
    )
    p.add_argument(
        "--check",
        action="store_true",
        help=(
            "Exit 1 if the committed file is missing or has drifted from the "
            "graph (CI gate; mirrors export --check)."
        ),
    )
    add_repo_root_arg(p)
    p.set_defaults(func=cmd_digest)
    return p


def main(argv: list[str] | None = None) -> None:
    run_forwarded_cli(build_parser, "digest", argv)


if __name__ == "__main__":
    main()
