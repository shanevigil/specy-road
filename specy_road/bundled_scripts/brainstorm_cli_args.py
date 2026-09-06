"""Argparse surface for ``specy-road brainstorm``.

Split from ``brainstorm_cli.py`` for the same reason as
``do_next_task_args.py``: nine subcommands of option wiring would otherwise
push the command module past the file cap and bury the handlers.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable

from specy_road.bundled_scripts.brainstorm_promote import (
    DEFAULT_PROMOTE_TYPE,
    PROMOTABLE_TYPES,
)
from specy_road.bundled_scripts.brainstorm_session import (
    IDEA_KINDS,
    IDEA_STATUSES,
    RECOMMENDATIONS,
)
from specy_road.runtime_paths import add_repo_root_arg

_DESCRIPTION = (
    "Brainstorm roadmap ideas with an agent, then promote the ones you keep. "
    "Two modes: `start` diverges (quantity, Socratic questioning, research) "
    "and `recommend` converges (clustering and ranking). Both write a prompt "
    "under work/ for your agent to run; ideas land in "
    "work/brainstorm-<slug>.yaml, which is tracked."
)

_SLUG_HELP = (
    "Session name (default: the only open session; required when several are)."
)


def _add_slug(p: argparse.ArgumentParser) -> None:
    p.add_argument("--slug", default=None, metavar="SLUG", help=_SLUG_HELP)
    add_repo_root_arg(p)


def _add_start(sub) -> None:
    p = sub.add_parser(
        "start",
        help="open (or reopen) a session and write the divergent prompt",
    )
    p.add_argument(
        "--topic",
        default=None,
        metavar="TEXT",
        help="The question to brainstorm. Also seeds --slug when omitted.",
    )
    p.add_argument(
        "--under",
        default=None,
        metavar="NODE_ID",
        help="Anchor node that accepted ideas become children of "
        "(default: the roadmap root).",
    )
    p.add_argument(
        "--count",
        type=int,
        default=20,
        metavar="N",
        help="Minimum ideas to ask for (default: 20). Raise it to push the "
        "agent past its first, safest set.",
    )
    _add_slug(p)


def _add_add_idea(sub) -> None:
    p = sub.add_parser("add-idea", help="record one idea (the agent calls this)")
    p.add_argument("--title", required=True, metavar="TEXT")
    p.add_argument("--rationale", default=None, metavar="TEXT")
    p.add_argument(
        "--kind",
        default="feature",
        choices=IDEA_KINDS,
        help="Default: feature.",
    )
    p.add_argument(
        "--effort",
        default=None,
        metavar="SIZE",
        help="Free-form t-shirt size, e.g. S / M / L.",
    )
    p.add_argument(
        "--evidence",
        action="append",
        default=None,
        metavar="URL",
        help="Source that produced the idea. Repeatable.",
    )
    _add_slug(p)


def _add_list(sub) -> None:
    p = sub.add_parser("list", help="show the ideas in a session")
    p.add_argument(
        "--status",
        default=None,
        choices=IDEA_STATUSES,
        help="Show only ideas in this state.",
    )
    p.add_argument("--json", action="store_true", help="Machine-readable output.")
    _add_slug(p)

    s = sub.add_parser("sessions", help="list every open brainstorm session")
    add_repo_root_arg(s)


def _add_triage(sub) -> None:
    for name, verb in (("accept", "keep"), ("reject", "discard")):
        p = sub.add_parser(name, help=f"{verb} one or more ideas")
        p.add_argument("idea_id", nargs="+", metavar="IDEA_ID")
        _add_slug(p)

    p = sub.add_parser("revise", help="edit an idea, or record a recommendation")
    p.add_argument("idea_id", metavar="IDEA_ID")
    p.add_argument("--title", default=None, metavar="TEXT")
    p.add_argument("--rationale", default=None, metavar="TEXT")
    p.add_argument("--kind", default=None, choices=IDEA_KINDS)
    p.add_argument("--effort", default=None, metavar="SIZE")
    p.add_argument(
        "--recommendation",
        default=None,
        choices=RECOMMENDATIONS,
        help="The agent's verdict. Passing only this leaves the idea's "
        "triage status alone, so accept/reject stays the PM's call.",
    )
    _add_slug(p)


def _add_converge(sub) -> None:
    p = sub.add_parser(
        "recommend",
        help="switch to roadmap mode and write the convergent prompt",
    )
    _add_slug(p)

    p = sub.add_parser("promote", help="turn accepted ideas into roadmap nodes")
    p.add_argument(
        "--under",
        default=None,
        metavar="NODE_ID",
        help="Override the session's anchor for this promotion.",
    )
    p.add_argument(
        "--type",
        default=DEFAULT_PROMOTE_TYPE,
        choices=PROMOTABLE_TYPES,
        help=f"Node type to create (default: {DEFAULT_PROMOTE_TYPE}).",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Show the ids that would be created, write nothing.",
    )
    _add_slug(p)


def build_parser(handlers: dict[str, Callable]) -> argparse.ArgumentParser:
    """The whole ``brainstorm`` parser, bound to ``handlers`` by name."""
    p = argparse.ArgumentParser(prog="specy-road brainstorm", description=_DESCRIPTION)
    sub = p.add_subparsers(dest="brainstorm_cmd", required=True)
    _add_start(sub)
    _add_add_idea(sub)
    _add_list(sub)
    _add_triage(sub)
    _add_converge(sub)
    for name, fn in handlers.items():
        sub.choices[name].set_defaults(func=fn)
    return p
