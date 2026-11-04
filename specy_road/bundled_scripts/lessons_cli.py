#!/usr/bin/env python3
"""CLI for ``specy-road lessons add|list`` (M11.78): project review lessons."""

from __future__ import annotations

import argparse
import sys

from specy_road.review_lessons import LESSONS_REL, add_lesson, format_lesson, lessons_path, read_lessons
from specy_road.runtime_paths import add_repo_root_arg, resolve_repo_root


def cmd_add(ns: argparse.Namespace) -> int:
    root = resolve_repo_root(ns)
    try:
        add_lesson(root, rule=ns.rule, example=ns.example, from_node=ns.from_node)
    except (ValueError, OSError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    print(f"added lesson → {lessons_path(root)}")
    return 0


def cmd_list(ns: argparse.Namespace) -> int:
    root = resolve_repo_root(ns)
    path = lessons_path(root)
    try:
        entries = read_lessons(path)
    except OSError as e:
        print(f"error: could not read {LESSONS_REL.as_posix()}: {e}", file=sys.stderr)
        return 1
    if not path.is_file():
        print(f"No review lessons: {LESSONS_REL.as_posix()} does not exist; `specy-road lessons add` creates it.")
        return 0
    if not entries:
        print(f"No review lessons in {LESSONS_REL.as_posix()}.")
        return 0
    for e in entries:
        print(format_lesson(e))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="specy-road")
    sub = p.add_subparsers(dest="cmd", required=True)
    les = sub.add_parser("lessons", help="Defect classes every reviewer prompt checks (constraints/review-lessons.md)")
    lsub = les.add_subparsers(dest="lessons_cmd", required=True)

    add = lsub.add_parser("add", help="Append a defect class that escaped review")
    add.add_argument("--rule", required=True, help="The defect class as a one-line rule for reviewers")
    add.add_argument("--example", help="One line showing the defect, such as where it escaped")
    add.add_argument("--from", dest="from_node", metavar="NODE_ID", help="The leaf the defect escaped from")
    add_repo_root_arg(add)
    add.set_defaults(func=cmd_add)

    lst = lsub.add_parser("list", help="Print every lesson, in file order")
    add_repo_root_arg(lst)
    lst.set_defaults(func=cmd_list)
    return p


def main(argv: list[str] | None = None) -> None:
    argv = list(sys.argv[1:] if argv is None else argv)
    ns = build_parser().parse_args(argv)
    raise SystemExit(ns.func(ns))


if __name__ == "__main__":
    main()
