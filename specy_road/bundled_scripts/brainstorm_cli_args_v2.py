"""Argparse surface for the brainstorm v2 subcommands.

``next-round``, ``frame``, ``evidence``, ``add-evidence``, ``verify`` and
``park`` — kept apart from ``brainstorm_cli_args`` for the same file-cap
reason that module exists.
"""

from __future__ import annotations

import argparse

from specy_road.bundled_scripts.brainstorm_fields import STANCES
from specy_road.bundled_scripts.brainstorm_lenses import PROFILES
from specy_road.runtime_paths import add_repo_root_arg

_SLUG_HELP = (
    "Session name (default: the only open session; required when several are)."
)


def _slug(p: argparse.ArgumentParser) -> None:
    p.add_argument("--slug", default=None, metavar="SLUG", help=_SLUG_HELP)
    add_repo_root_arg(p)


def add_start_v2_options(p: argparse.ArgumentParser) -> None:
    p.add_argument("--rounds", type=int, default=2, metavar="R",
                   help="Diverge rounds planned (default: 2). Round 1 plans and generates "
                        "without the roadmap list or research; `next-round` opens the rest.")
    p.add_argument("--profile", default=None, choices=sorted(PROFILES),
                   help="Lens set: product (default) or technical (failure modes, "
                        "operability, migration, debt, dependency risk, platform).")
    p.add_argument("--panel", type=int, default=None, metavar="N",
                   help="Also write N independent shard prompts (work/brainstorm-<slug>-r1-sN-prompt.md) "
                        "for sub-agents or other harnesses to run without seeing each other; "
                        "`frame` rewrites them with the frame and each shard's `sN:` allocation cell.")


def add_v2_subcommands(sub) -> None:
    p = sub.add_parser("next-round", help="open the next diverge round: regenerate against the pool")
    p.add_argument("--count", type=int, default=None, metavar="N",
                   help="Minimum new ideas to ask for (default: 20).")
    _slug(p)

    p = sub.add_parser("frame", help="record the agreed frame or the allocation grid")
    p.add_argument("--answer", action="append", default=[], metavar="KEY=TEXT",
                   help="One agreed answer, e.g. outcome=... (repeatable).")
    p.add_argument("--allocation", default=None, metavar="TEXT",
                   help="The allocation grid as text. With --panel, a line `sN: <cell>` gives shard N its cell.")
    _slug(p)

    p = sub.add_parser("evidence", help="write the evidence prompt for shortlisted ideas")
    p.add_argument("idea_id", nargs="*", metavar="IDEA_ID",
                   help="Ideas to source (default: those recommended strong or consider).")
    _slug(p)

    p = sub.add_parser("add-evidence", help="record one source on an idea (the agent calls this)")
    p.add_argument("idea_id", metavar="IDEA_ID")
    p.add_argument("--url", required=True)
    p.add_argument("--quote", default="", metavar="TEXT", help="Verbatim text from the page (≤300 chars); required — a URL alone is not evidence.")
    p.add_argument("--supports", default="", metavar="TEXT", help="The claim this source bears on.")
    p.add_argument("--stance", default="for", choices=STANCES)
    p.add_argument("--tool", default="", metavar="TEXT", help="How it was retrieved, e.g. 'claude WebFetch'.")
    p.add_argument("--source-type", default="", metavar="TYPE",
                   help="official-doc, regulation, paper, customer-report, news, competitor.")
    p.add_argument("--retrieved-at", default=None, metavar="DATE", help="Default: today.")
    _slug(p)

    p = sub.add_parser("verify", help="check that each recorded quote appears on its page (asks before fetching)")
    p.add_argument("idea_id", nargs="*", metavar="IDEA_ID", help="Default: every idea with unverified sources.")
    p.add_argument("--yes", action="store_true", help="Allow the fetch without asking (scripts).")
    _slug(p)

    p = sub.add_parser("park", help="set ideas aside with a reason and, optionally, a revisit condition")
    p.add_argument("idea_id", nargs="+", metavar="IDEA_ID")
    p.add_argument("--reason", required=True, metavar="TEXT")
    p.add_argument("--revisit-when", default="", metavar="TEXT",
                   help="Optional: what would make the idea worth another look.")
    _slug(p)
