"""Argparse surface for the brainstorm v2 subcommands.

``next-round``, ``frame``, ``evidence``, ``add-evidence``, ``verify``,
``park``, ``merge`` and ``cluster`` — kept apart from ``brainstorm_cli_args``
for the same file-cap reason that module exists — and the sources
``add-evidence`` and ``add-idea --quote`` build from their flags.
"""

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path
from typing import Any

from specy_road.bundled_scripts.brainstorm_fields import (
    NO_RESULT,
    REPO,
    STANCES,
    no_result_locator,
    repo_locator,
    source_record,
)
from specy_road.bundled_scripts.brainstorm_lenses import PROFILES
from specy_road.bundled_scripts.brainstorm_session import BrainstormError
from specy_road.bundled_scripts.brainstorm_verify import repo_commit
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


def add_from_file(p: argparse.ArgumentParser, key: str) -> None:
    p.add_argument("--from-file", default=None, metavar="PATH",
                   help=f"Apply every record in a YAML list (or a mapping with a `{key}:` list), or JSONL "
                        "(one object per line; `-` reads stdin), as one write: all or none. Keys are this "
                        "command's flag names without the dashes; repeatable flags take a list.")


def frame_answers(ns: argparse.Namespace) -> list[tuple[str, str]]:
    """``--answer KEY=TEXT`` pairs, or ``--amend KEY`` with its one ``--answer TEXT``."""
    if ns.amend is None:
        pairs = [(key.strip(), text.strip()) for key, _sep, text in (a.partition("=") for a in ns.answer)]
        for item, (key, text) in zip(ns.answer, pairs):
            if "=" not in item or not key or not text:
                raise BrainstormError(f"--answer {item!r}: expected KEY=TEXT")
        return pairs
    key = ns.amend.strip()
    if len(ns.answer) != 1:
        raise BrainstormError(f"--amend {key} takes exactly one --answer TEXT: the new answer")
    text = ns.answer[0].strip().removeprefix(f"{key}=").strip()   # KEY=TEXT is accepted too
    if not key or not text:
        raise BrainstormError("--amend needs a KEY and a non-empty --answer")
    return [(key, text)]


def _evidence_quote(ns: argparse.Namespace) -> str:
    """The checked ``--quote``: required on a page or a file, absent on a search that found nothing."""
    given = [f for f, v in (("--url", ns.url), ("--path", ns.path), ("--query", ns.query)) if v is not None]
    if len(given) != 1:
        raise BrainstormError("add-evidence takes one of --url URL, --path FILE[:LINE], "
                              "or --query TEXT --no-result" + (f"; got {', '.join(given)}" if given else ""))
    if (ns.query is not None) != ns.no_result:
        raise BrainstormError("--query and --no-result go together: they record a search that found nothing")
    quote = (ns.quote or "").strip()
    if ns.no_result:
        if quote:
            raise BrainstormError("--no-result takes no --quote: the search found nothing to quote")
        return quote
    if not quote:
        raise BrainstormError("--quote is required: a URL with no quote is not evidence (verify checks the quote)")
    if len(quote) > 300:
        raise BrainstormError("--quote must be 300 characters or fewer: quote, do not paraphrase")
    return quote


def evidence_record(ns: argparse.Namespace, root: Path) -> dict[str, Any]:
    """The source ``add-evidence`` records: a page (``--url``), a file in this repository at ``HEAD``
    (``--path FILE[:LINE]``), or a search that found nothing (``--query TEXT --no-result``)."""
    common = dict(quote=_evidence_quote(ns), supports=ns.supports, stance=ns.stance, tool=ns.tool,
                  retrieved_at=ns.retrieved_at or date.today().isoformat())
    source_type = ns.source_type.strip()
    if ns.path is not None:
        if source_type not in ("", REPO):
            raise BrainstormError(f"--path cites a file in this repository: --source-type {REPO}, or leave it out")
        path = ns.path.strip()
        commit = repo_commit(root, path)
        return source_record(repo_locator(path, commit), source_type=REPO, path=path, commit=commit, **common)
    if source_type == REPO:
        raise BrainstormError(f"--source-type {REPO} needs --path FILE[:LINE]")
    if ns.no_result:
        if not ns.query.strip():
            raise BrainstormError("--query is empty: record the search that found nothing")
        return source_record(no_result_locator(ns.query.strip()), source_type=source_type, query=ns.query,
                             result=NO_RESULT, **common)
    return source_record(ns.url, source_type=source_type, **common)


def quoted_sources(ns: argparse.Namespace) -> list[dict]:
    """``--quote`` N backs ``--evidence`` N: a source ``verify`` can check, for an idea research produced."""
    quotes, urls = list(ns.quote or []), list(ns.evidence or [])
    if len(quotes) > len(urls):
        raise BrainstormError(f"{len(quotes)} --quote for {len(urls)} --evidence: each quote backs the URL "
                              "in the same position")
    for q in quotes:
        if not q.strip() or len(q) > 300:
            raise BrainstormError("each --quote needs verbatim text of 300 characters or fewer")
    return [source_record(u, quote=q, retrieved_at=date.today().isoformat()) for u, q in zip(urls, quotes)]


def _add_evidence_parser(sub) -> None:
    p = sub.add_parser("add-evidence", help="record one source on an idea (the agent calls this)")
    p.add_argument("idea_id", metavar="IDEA_ID")
    p.add_argument("--url", default=None, help="The page. One of --url, --path or --query.")
    p.add_argument("--path", default=None, metavar="FILE[:LINE]",
                   help=f"A file in this repository (source type {REPO}); records the HEAD commit, and "
                        "verify checks the quote against the file at that commit, locally.")
    p.add_argument("--query", default=None, metavar="TEXT",
                   help="With --no-result: a search, e.g. a disconfirming one, that found nothing.")
    p.add_argument("--no-result", action="store_true",
                   help="Record --query as a search with no hit; it takes no --quote and verify skips it.")
    p.add_argument("--quote", default="", metavar="TEXT", help="Verbatim text from the page or file (≤300 chars); "
                   "required unless --no-result — a URL alone is not evidence.")
    p.add_argument("--supports", default="", metavar="TEXT", help="The claim this source bears on.")
    p.add_argument("--stance", default="for", choices=STANCES)
    p.add_argument("--tool", default="", metavar="TEXT", help="How it was retrieved, e.g. 'claude WebFetch'.")
    p.add_argument("--source-type", default="", metavar="TYPE",
                   help=f"official-doc, regulation, paper, customer-report, news, competitor; {REPO} with --path.")
    p.add_argument("--retrieved-at", default=None, metavar="DATE", help="Default: today.")
    _slug(p)


def add_v2_subcommands(sub) -> None:
    p = sub.add_parser("next-round", help="open the next diverge round: regenerate against the pool")
    p.add_argument("--count", type=int, default=None, metavar="N",
                   help="Minimum new ideas to ask for (default: 20).")
    _slug(p)

    p = sub.add_parser("frame", help="record the agreed frame or the allocation grid")
    p.add_argument("--answer", action="append", default=[], metavar="KEY=TEXT",
                   help="One agreed answer, e.g. outcome=... (repeatable). A different answer for a "
                        "recorded key replaces it and keeps the old one in frame_history.")
    p.add_argument("--amend", default=None, metavar="KEY",
                   help="Change one recorded answer: give the new text as the one --answer TEXT; "
                        "the previous answer is kept in frame_history.")
    state = p.add_mutually_exclusive_group()
    state.add_argument("--provisional", action="store_true",
                       help="Mark the frame provisional: later prompts treat it as working assumptions.")
    state.add_argument("--confirm", action="store_true",
                       help="Mark the frame confirmed by the PM; later prompts say so.")
    p.add_argument("--allocation", default=None, metavar="TEXT",
                   help="The allocation grid as text. With --panel, a line `sN: <cell>` gives shard N its cell.")
    _slug(p)

    p = sub.add_parser("evidence", help="write the evidence prompt for shortlisted ideas")
    p.add_argument("idea_id", nargs="*", metavar="IDEA_ID",
                   help="Ideas to source (default: those recommended strong). More than 15 warns.")
    _slug(p)

    _add_evidence_parser(sub)

    p = sub.add_parser("verify", help="check that each recorded quote appears on its page (asks before fetching)")
    p.add_argument("idea_id", nargs="*", metavar="IDEA_ID", help="Default: every idea with unverified sources.")
    p.add_argument("--yes", action="store_true", help="Allow the fetch without asking (scripts).")
    _slug(p)

    p = sub.add_parser("park", help="set ideas aside with a reason and, optionally, a revisit condition")
    p.add_argument("idea_id", nargs="+", metavar="IDEA_ID")
    p.add_argument("--reason", required=True, metavar="TEXT",
                   help="Required; recorded as the decision reason.")
    p.add_argument("--revisit-when", default="", metavar="TEXT",
                   help="Optional: what would make the idea worth another look.")
    _slug(p)

    p = sub.add_parser("decide", help="record the decision or policy an idea settled: status decided; "
                                      "promote writes it into the anchor's sheet instead of a node")
    p.add_argument("idea_id", metavar="IDEA_ID")
    p.add_argument("--decision", required=True, metavar="TEXT",
                   help="The decision, as it should read under the anchor sheet's `## Decided policies`.")
    _slug(p)

    p = sub.add_parser("merge", help="fold a duplicate idea into others: status merged, linked both ways")
    p.add_argument("idea_id", metavar="IDEA_ID")
    p.add_argument("--into", nargs="+", required=True, metavar="IDEA_ID",
                   help="The idea(s) it duplicates; each records the merged id in merged_from.")
    _slug(p)

    p = sub.add_parser("cluster", help="record a converge cluster: its name, best statement and critics")
    p.add_argument("cluster_id", metavar="CID")
    p.add_argument("--name", default=None, metavar="TEXT", help="What the cluster's ideas share ('' clears it).")
    p.add_argument("--best", default=None, metavar="IDEA_ID",
                   help="The member that states the bet best; it must already carry this cluster id ('' clears it).")
    p.add_argument("--critic", action="append", default=None, metavar="ROLE: TEXT",
                   help="A critic's strongest objection to the cluster (repeatable; same role replaces).")
    _slug(p)
