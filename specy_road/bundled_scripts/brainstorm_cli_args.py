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
    execution_milestone_from_promote_sets,
)
from specy_road.bundled_scripts.brainstorm_cli_args_v2 import (
    add_start_v2_options,
    add_v2_subcommands,
)
from specy_road.bundled_scripts.brainstorm_session import (
    IDEA_KINDS,
    IDEA_STATUSES,
    RECOMMENDATIONS,
)
from specy_road.runtime_paths import add_repo_root_arg

_DESCRIPTION = (
    "Brainstorm roadmap ideas with an agent, then promote the ones you keep. "
    "Two modes: `start` diverges (Socratic questioning, then quantity; no "
    "research in round 1, `next-round` opens it) and `recommend` converges "
    "(clustering and ranking). Both write a prompt "
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
    add_start_v2_options(p)
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
    p.add_argument("--origin", default=None, metavar="H/M/LENS/ROUND[/SHARD]",
                   help="Where the idea came from: harness/model/lens/round[/shard].")
    p.add_argument("--hypothesis", default=None, metavar="TEXT",
                   help="If we do this, <metric> moves because <reason>.")
    p.add_argument("--assumption", action="append", default=None, metavar="TEXT",
                   help="Something that must be true for the idea to matter. Repeatable.")
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
    p.add_argument("--summary", action="store_true",
                   help="Print per-status and per-recommendation counts instead of a row listing.")
    p.add_argument("--by", default=None, choices=("cluster",),
                   help="Group the listing (cluster-first triage).")
    p.add_argument("--show-verdicts", action="store_true",
                   help="Show the agent's recommendation column, its reasoning and the critics' "
                        "objections (hidden by default so they do not steer the triage).")
    _add_slug(p)

    s = sub.add_parser("sessions", help="list every open brainstorm session")
    add_repo_root_arg(s)

    c = sub.add_parser("close", help="move a finished session to work/brainstorm-closed/ so it stops counting as open")
    _add_slug(c)


def _add_triage(sub) -> None:
    p = sub.add_parser("accept", help="keep one or more ideas")
    p.add_argument("idea_id", nargs="+", metavar="IDEA_ID")
    p.add_argument("--reason", default=None, metavar="TEXT",
                   help="Optional; when given, recorded as the decision reason.")
    _add_slug(p)

    p = sub.add_parser("reject", help="discard one or more ideas")
    p.add_argument("idea_id", nargs="+", metavar="IDEA_ID")
    p.add_argument("--reason", required=True, metavar="TEXT",
                   help="Required; recorded as the decision reason.")
    _add_slug(p)

    p = sub.add_parser(
        "realize",
        help="link an idea to a roadmap node you created outside promote",
    )
    p.add_argument("idea_id", metavar="IDEA_ID")
    p.add_argument("--node", required=True, metavar="NODE_ID",
                   help="Display id of an existing node in the merged roadmap.")
    _add_slug(p)

    p = sub.add_parser("revise", help="edit an idea, or record a recommendation")
    p.add_argument("idea_id", metavar="IDEA_ID")
    p.add_argument("--title", default=None, metavar="TEXT")
    p.add_argument("--rationale", default=None, metavar="TEXT")
    p.add_argument("--kind", default=None, choices=IDEA_KINDS)
    p.add_argument("--effort", default=None, metavar="SIZE")
    p.add_argument(
        "--codename",
        default=None,
        metavar="SLUG",
        help="Kebab-case branch slug for promote (overrides title-derived codename).",
    )
    p.add_argument(
        "--recommendation",
        default=None,
        choices=RECOMMENDATIONS,
        help="The agent's verdict. Passing only this leaves the idea's "
        "triage status alone, so accept/reject stays the PM's call.",
    )
    p.add_argument("--why", default=None, metavar="TEXT",
                   help="Set verdict_why (the stored verdict reasoning; cite a clause, source, or overlap). "
                        "Unlike --rationale it does not edit the idea or mark it revised.")
    p.add_argument("--append-why", default=None, metavar="TEXT",
                   help="Append to verdict_why instead of replacing it.")
    p.add_argument("--cluster", default=None, metavar="CID", help="Cluster id from the converge pass.")
    p.add_argument("--overlap", action="append", default=None, metavar="NODE_ID:RELATION",
                   help="Existing node this overlaps and how (repeatable).")
    p.add_argument("--critic", action="append", default=None, metavar="ROLE: TEXT",
                   help="A critic's strongest objection, e.g. 'feasibility: ...' (repeatable).")
    _add_slug(p)


def _add_converge(sub) -> None:
    p = sub.add_parser(
        "recommend",
        help="switch to roadmap mode and write the convergent prompt",
    )
    p.add_argument("--check", action="store_true",
                   help="Write nothing; exit 1 listing every idea without a cluster or a "
                        "recommendation (run after the agent's converge pass).")
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
    p.add_argument(
        "--set",
        dest="set",
        action="append",
        metavar="KEY=VALUE",
        help=(
            "Override a field on every promoted node. Only execution_milestone "
            "is supported (e.g. --set execution_milestone=Human-led); otherwise "
            "the anchor's execution_milestone is copied."
        ),
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
    add_v2_subcommands(sub)
    for name, fn in handlers.items():
        sub.choices[name].set_defaults(func=fn)
    return p
