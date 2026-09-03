#!/usr/bin/env python3
"""CLI for `specy-road search`: ranked text search over the roadmap corpus.

Read-only. The only file it touches is the gitignored index under
`.specyrd/cache/`, and that is best-effort.

Output is deliberately a *pointer plus a snippet*, not file contents. An agent
gets enough to judge relevance and a path to open if it wants more — the
progressive-disclosure pattern, rather than flooding a context window with
material that is mostly duplicated anyway.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from specy_road.runtime_paths import add_repo_root_arg, resolve_repo_root
from specy_road.search_corpus import (
    KIND_CONSTITUTION,
    KIND_NODE,
    KIND_PLANNING,
    KIND_SHARED,
    KIND_SUMMARY,
    SCOPE_ARCHIVED,
    SCOPE_LIVE,
)
from specy_road.search_index import corpus_stats, fts5_available, search

_KINDS = (KIND_PLANNING, KIND_SHARED, KIND_NODE, KIND_SUMMARY, KIND_CONSTITUTION)


def _scopes(value: str) -> set[str] | None:
    if value == "all":
        return None
    return {SCOPE_LIVE} if value == "live" else {SCOPE_ARCHIVED}


def _print_results(results: list[dict]) -> None:
    for item in results:
        marker = " [archived]" if item["scope"] == SCOPE_ARCHIVED else ""
        heading = f"  ## {item['heading']}" if item["heading"] else ""
        print(f"{item['doc_path']}{heading}{marker}")
        print(f"    {item['context']}")
        for line in item["snippet"].splitlines():
            if line.strip():
                print(f"    {line.strip()}")
        print()


def cmd_search(ns: argparse.Namespace) -> int:
    root = resolve_repo_root(ns)
    query = " ".join(ns.query).strip()

    if ns.stats:
        stats = corpus_stats(root)
        stats["fts5"] = fts5_available()
        print(json.dumps(stats, indent=2, sort_keys=True) if ns.json else stats)
        return 0

    if not query:
        print("error: nothing to search for.", file=sys.stderr)
        return 2

    results = search(
        root,
        query,
        scopes=_scopes(ns.scope),
        kinds=set(ns.kind) if ns.kind else None,
        node_id=ns.node,
        limit=ns.limit,
        rebuild=ns.rebuild,
    )

    if ns.json:
        print(
            json.dumps(
                {"query": query, "results": results}, indent=2, sort_keys=True
            )
        )
        return 0

    if not results:
        print(_empty_note(root, query))
        return 0
    _print_results(results)
    print(f"{len(results)} result(s). Open a path above for the full text.")
    return 0


def _empty_note(root: Path, query: str) -> str:
    stats = corpus_stats(root)
    if not stats["chunks"]:
        return (
            "nothing indexed: no planning sheets, shared contracts or roadmap "
            "nodes were found under this repo root. Is --repo-root correct?"
        )
    return (
        f"no matches for {query!r} across {stats['chunks']} indexed passages. "
        "Try fewer words, or --scope all to include archived work."
    )


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="specy-road search",
        description=(
            "Search planning sheets, shared contracts, roadmap nodes, "
            "implementation summaries and archived work. Ranked, deduplicated, "
            "and scoped so current decisions outrank superseded ones."
        ),
    )
    p.add_argument("query", nargs="*", metavar="QUERY")
    p.add_argument(
        "--scope",
        choices=("live", "archived", "all"),
        default="all",
        help="Restrict to live or archived material (default: all, live ranked first).",
    )
    p.add_argument(
        "--kind",
        action="append",
        choices=_KINDS,
        default=None,
        help="Restrict to a source kind. Repeatable.",
    )
    p.add_argument(
        "--node", metavar="NODE_ID", default=None, help="Only this node's material."
    )
    p.add_argument("--limit", type=int, default=10, metavar="N")
    p.add_argument("--json", action="store_true", help="Machine-readable output.")
    p.add_argument(
        "--stats", action="store_true", help="Report index size instead of searching."
    )
    p.add_argument(
        "--rebuild",
        action="store_true",
        help="Discard the index under .specyrd/cache/ and re-chunk everything.",
    )
    add_repo_root_arg(p)
    p.set_defaults(func=cmd_search)
    return p


def main(argv: list[str] | None = None) -> None:
    argv = list(sys.argv[1:] if argv is None else argv)
    # `specy-road search …` forwards its own name; argparse defines it here.
    if argv and argv[0] == "search":
        argv = argv[1:]
    ns = build_parser().parse_args(argv)
    try:
        raise SystemExit(ns.func(ns))
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        raise SystemExit(1) from e


if __name__ == "__main__":
    main()
