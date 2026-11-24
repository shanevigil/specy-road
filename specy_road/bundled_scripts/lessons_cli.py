#!/usr/bin/env python3
"""``specy-road lessons add|list``: deprecated alias of ``decisions add|list --kind lesson``.

Each prints one deprecation line, then runs the ``decisions`` code on the same
``constraints/review-lessons.md``: ``--rule`` is ``--summary`` there and ``--from`` is its ``NODE``.
"""

from __future__ import annotations

import argparse

from specy_road.bundled_scripts.decisions_cli import add_lesson_entry, list_lessons
from specy_road.cli import ALIASES_REMOVED_IN, warn_deprecated
from specy_road.cli_entry import run_cli
from specy_road.runtime_paths import add_repo_root_arg, resolve_repo_root


def cmd_add(ns: argparse.Namespace) -> int:
    warn_deprecated("lessons add", "decisions add --kind lesson")
    return add_lesson_entry(resolve_repo_root(ns), rule=ns.rule, example=ns.example, from_node=ns.from_node)


def cmd_list(ns: argparse.Namespace) -> int:
    warn_deprecated("lessons list", "decisions list --kind lesson")
    return list_lessons(resolve_repo_root(ns))


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="specy-road")
    sub = p.add_subparsers(dest="cmd", required=True)
    les = sub.add_parser("lessons", help=f"Deprecated: use decisions add|list --kind lesson (removed in "
                                         f"{ALIASES_REMOVED_IN})")
    lsub = les.add_subparsers(dest="lessons_cmd", required=True)

    add = lsub.add_parser("add", help="Deprecated: use decisions add --kind lesson. Append a defect class that "
                                      "escaped review")
    add.add_argument("--rule", required=True, help="The defect class as a one-line rule for reviewers")
    add.add_argument("--example", help="One line showing the defect, such as where it escaped")
    add.add_argument("--from", dest="from_node", metavar="NODE_ID", help="The leaf the defect escaped from")
    add_repo_root_arg(add)
    add.set_defaults(func=cmd_add)

    lst = lsub.add_parser("list", help="Deprecated: use decisions list --kind lesson. Print every lesson, in "
                                       "file order")
    add_repo_root_arg(lst)
    lst.set_defaults(func=cmd_list)
    return p


def main(argv: list[str] | None = None) -> None:
    run_cli(build_parser, argv)


if __name__ == "__main__":
    main()
