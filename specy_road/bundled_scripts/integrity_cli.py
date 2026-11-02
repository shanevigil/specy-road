#!/usr/bin/env python3
"""CLI for ``specy-road integrity``: test-integrity findings for a roadmap leaf."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from specy_road.integrity import compare_integrity, findings_to_json
from specy_road.review_target import resolve_target_or_exit
from specy_road.runtime_paths import add_repo_root_arg, default_user_repo_root


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(
        description="Report removed tests, new skips, lost asserts and pytest config edits "
        "between a leaf and its merge base (git objects only; no checkout).",
    )
    p.add_argument("node_id", help="Roadmap node id, e.g. M9.5")
    p.add_argument("--ref", help="Branch or commit (default: the node's registered branch)")
    p.add_argument("--json", action="store_true", help='Print {"findings": [...]} instead of lines')
    add_repo_root_arg(p)
    args = p.parse_args(argv)
    root = (args.repo_root or default_user_repo_root()).resolve()
    target = resolve_target_or_exit(root, args.node_id, args.ref)
    if not target.base or not target.commit:
        print("error: cannot resolve merge base or commit under review", file=sys.stderr)
        raise SystemExit(1)
    findings = compare_integrity(root, target.base, target.commit)
    if args.json:
        if findings:
            print(json.dumps(findings_to_json(findings), sort_keys=True))
    else:
        for f in findings:
            print(f.line())
    raise SystemExit(1 if findings else 0)


if __name__ == "__main__":
    main()
