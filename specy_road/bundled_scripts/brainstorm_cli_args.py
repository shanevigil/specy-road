"""Argparse surface for ``specy-road brainstorm``: every subcommand's flags, bound by name.

The handlers live in ``brainstorm_cli``. This module also turns flags into the
records they stand for: the sources ``add-evidence`` and ``add-idea --quote``
build, the ``frame`` answers, and the ``--from-file`` records parsed as the
single command's own flags.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any

import yaml

from specy_road.cli_args import add_json_arg
from specy_road.brainstorm_promote import (
    DEFAULT_PROMOTE_TYPE,
    INHERIT_EXECUTION_MILESTONE,
    PROMOTABLE_TYPES,
)
from specy_road.bundled_scripts.brainstorm_fields import (
    NO_RESULT,
    REPO,
    STANCES,
    no_result_locator,
    repo_locator,
    source_record,
)
from specy_road.bundled_scripts.brainstorm_lenses import PROFILES
from specy_road.bundled_scripts.brainstorm_verify import repo_commit
from specy_road.brainstorm_session import (
    IDEA_KINDS,
    BrainstormError,
    IDEA_STATUSES,
    RECOMMENDATIONS,
)
from specy_road.bundled_scripts.roadmap_edit_fields import EXEC_MILESTONES
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
    p.add_argument("--rounds", type=int, default=2, metavar="R",
                   help="Diverge rounds planned (default: 2). Round 1 plans and generates "
                        "without the roadmap list or research; `next-round` opens the rest.")
    p.add_argument("--profile", default=None, choices=sorted(PROFILES),
                   help="Lens set: product (default) or technical (failure modes, "
                        "operability, migration, debt, dependency risk, platform).")
    p.add_argument("--panel", type=int, default=None, metavar="N",
                   help="Also write N independent shard prompts "
                        "(work/brainstorm-<slug>-r1-sN-prompt.md) "
                        "for sub-agents or other harnesses to run without seeing each other; "
                        "`frame` rewrites them with the frame and each shard's "
                        "`sN:` allocation cell.")
    _add_slug(p)


def _add_add_idea(sub) -> None:
    p = sub.add_parser("add-idea", help="record one idea, or a file of them (the agent calls this)")
    p.add_argument("--title", default=None, metavar="TEXT", help="Required unless --from-file.")
    p.add_argument("--rationale", default=None, metavar="TEXT")
    p.add_argument(
        "--kind",
        default=None,  # None, not feature, so an explicit --kind beside --from-file can be refused
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
    p.add_argument("--quote", action="append", default=None, metavar="TEXT",
                   help="Verbatim text (≤300 chars) from the --evidence URL in the same position; "
                        "records a source `verify` checks. Repeatable.")
    p.add_argument("--origin", default=None, metavar="H/M/LENS/ROUND[/SHARD]",
                   help="Where the idea came from: harness/model/lens/round[/shard].")
    p.add_argument("--hypothesis", default=None, metavar="TEXT",
                   help="If we do this, <metric> moves because <reason>.")
    p.add_argument("--assumption", action="append", default=None, metavar="TEXT",
                   help="Something that must be true for the idea to matter. Repeatable.")
    p.add_argument("--from-gap", action="store_true",
                   help="Mark the idea as raised in the converge pass (a gap); "
                        "recommend lists it for a verdict.")
    _add_from_file(p, "ideas")
    _add_slug(p)


def _add_list(sub) -> None:
    p = sub.add_parser("list", help="show the ideas in a session")
    p.add_argument(
        "--status",
        default=None,
        choices=IDEA_STATUSES,
        help="Show only ideas in this state.",
    )
    add_json_arg(p)
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

    c = sub.add_parser("close", help="move a finished session to work/brainstorm-closed/ "
                                     "so it stops counting as open")
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

    p = sub.add_parser("revise",
                       help="edit an idea, or record a recommendation (or a file of them)")
    p.add_argument("idea_id", nargs="?", default=None, metavar="IDEA_ID",
                   help="Required unless --from-file.")
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
                   help="Set verdict_why (the stored verdict reasoning; cite a clause, source, or "
                        "overlap). "
                        "Unlike --rationale it does not edit the idea or mark it revised.")
    p.add_argument("--append-why", default=None, metavar="TEXT",
                   help="Append to verdict_why instead of replacing it.")
    p.add_argument("--cluster", default=None, metavar="CID",
                   help="Cluster id from the converge pass.")
    p.add_argument("--target-parent", default=None, metavar="NODE_ID",
                   help="Display id promote lands this idea under instead of the anchor "
                        "('' clears it).")
    p.add_argument("--overlap", action="append", default=None, metavar="NODE_ID:RELATION",
                   help="Existing node this overlaps and how (repeatable).")
    p.add_argument("--critic", action="append", default=None, metavar="ROLE: TEXT",
                   help="A critic's strongest objection, e.g. 'feasibility: ...' (repeatable).")
    _add_from_file(p, "verdicts")
    _add_slug(p)


def _add_from_file(p: argparse.ArgumentParser, key: str) -> None:
    p.add_argument("--from-file", default=None, metavar="PATH",
                   help=f"Apply every record in a YAML list (or a mapping with a `{key}:` list), "
                        "or JSONL "
                        "(one object per line; `-` reads stdin), as one write: all or none. "
                        "Keys are this "
                        "command's flag names without the dashes; repeatable flags take a list.")


def frame_answers(ns: argparse.Namespace) -> list[tuple[str, str]]:
    """``--answer KEY=TEXT`` pairs, or ``--amend KEY`` with its one ``--answer TEXT``."""
    if ns.amend is None:
        pairs = [(key.strip(), text.strip())
                 for key, _sep, text in (a.partition("=") for a in ns.answer)]
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
    """The checked ``--quote``: required on a page or a file, absent on a search that
    found nothing."""
    given = [f for f, v in (("--url", ns.url), ("--path", ns.path), ("--query", ns.query))
             if v is not None]
    if len(given) != 1:
        raise BrainstormError("add-evidence takes one of --url URL, --path FILE[:LINE], "
                              "or --query TEXT --no-result"
                              + (f"; got {', '.join(given)}" if given else ""))
    if (ns.query is not None) != ns.no_result:
        raise BrainstormError("--query and --no-result go together: "
                              "they record a search that found nothing")
    quote = (ns.quote or "").strip()
    if ns.no_result:
        if quote:
            raise BrainstormError("--no-result takes no --quote: the search found nothing to quote")
        return quote
    if not quote:
        raise BrainstormError("--quote is required: a URL with no quote is not evidence "
                              "(verify checks the quote)")
    if len(quote) > 300:
        raise BrainstormError("--quote must be 300 characters or fewer: quote, do not paraphrase")
    return quote


def evidence_record(ns: argparse.Namespace, root: Path) -> dict[str, Any]:
    """The source ``add-evidence`` records: a page (``--url``), a file in this repository at
    ``HEAD``
    (``--path FILE[:LINE]``), or a search that found nothing (``--query TEXT --no-result``)."""
    common = dict(quote=_evidence_quote(ns), supports=ns.supports, stance=ns.stance, tool=ns.tool,
                  retrieved_at=ns.retrieved_at or date.today().isoformat())
    source_type = ns.source_type.strip()
    if ns.path is not None:
        if source_type not in ("", REPO):
            raise BrainstormError(f"--path cites a file in this repository: "
                                  f"--source-type {REPO}, or leave it out")
        path = ns.path.strip()
        commit = repo_commit(root, path)
        return source_record(repo_locator(path, commit), source_type=REPO, path=path,
                             commit=commit, **common)
    if source_type == REPO:
        raise BrainstormError(f"--source-type {REPO} needs --path FILE[:LINE]")
    if ns.no_result:
        if not ns.query.strip():
            raise BrainstormError("--query is empty: record the search that found nothing")
        return source_record(no_result_locator(ns.query.strip()), source_type=source_type,
                             query=ns.query,
                             result=NO_RESULT, **common)
    return source_record(ns.url, source_type=source_type, **common)


def quoted_sources(ns: argparse.Namespace) -> list[dict]:
    """``--quote`` N backs ``--evidence`` N: a source ``verify`` can check, for an idea
    research produced."""
    quotes, urls = list(ns.quote or []), list(ns.evidence or [])
    if len(quotes) > len(urls):
        raise BrainstormError(f"{len(quotes)} --quote for {len(urls)} --evidence: "
                              f"each quote backs the URL "
                              "in the same position")
    for q in quotes:
        if not q.strip() or len(q) > 300:
            raise BrainstormError("each --quote needs verbatim text of 300 characters or fewer")
    return [source_record(u, quote=q, retrieved_at=date.today().isoformat())
            for u, q in zip(urls, quotes)]


def _add_add_evidence(sub) -> None:
    p = sub.add_parser("add-evidence", help="record one source on an idea (the agent calls this)")
    p.add_argument("idea_id", metavar="IDEA_ID")
    p.add_argument("--url", default=None, help="The page. One of --url, --path or --query.")
    p.add_argument("--path", default=None, metavar="FILE[:LINE]",
                   help=f"A file in this repository (source type {REPO}); records the HEAD commit, "
                        "and "
                        "verify checks the quote against the file at that commit, locally.")
    p.add_argument("--query", default=None, metavar="TEXT",
                   help="With --no-result: a search, e.g. a disconfirming one, that found nothing.")
    p.add_argument("--no-result", action="store_true",
                   help="Record --query as a search with no hit; it takes no --quote and "
                        "verify skips it.")
    p.add_argument("--quote", default="", metavar="TEXT",
                   help="Verbatim text from the page or file (≤300 chars); "
                   "required unless --no-result — a URL alone is not evidence.")
    p.add_argument("--supports", default="", metavar="TEXT", help="The claim this source bears on.")
    p.add_argument("--stance", default="for", choices=STANCES)
    p.add_argument("--tool", default="", metavar="TEXT",
                   help="How it was retrieved, e.g. 'claude WebFetch'.")
    p.add_argument("--source-type", default="", metavar="TYPE",
                   help=f"official-doc, regulation, paper, customer-report, news, competitor; "
                        f"{REPO} with --path.")
    p.add_argument("--retrieved-at", default=None, metavar="DATE", help="Default: today.")
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
    p.add_argument("--by-cluster", action="store_true",
                   help="One node per cluster lead (strongest verdict, then accept order); "
                        "the cluster's other accepted ideas are listed on it as alternatives.")
    p.add_argument("--min-recommendation", default=None, choices=RECOMMENDATIONS,
                   help="Promote only ideas with at least this verdict; weaker ones stay accepted.")
    p.add_argument("--plan", default=None, metavar="PLAN.yaml",
                   help="Create the tree a plan file describes (parent, type, title, acceptance, "
                        "dependencies, ideas by id) instead of one node per accepted idea.")
    _add_slug(p)


def _add_rounds(sub) -> None:
    """``next-round`` and ``frame``: the diverge rounds and the frame they run under."""
    p = sub.add_parser("next-round",
                       help="open the next diverge round: regenerate against the pool")
    p.add_argument("--count", type=int, default=None, metavar="N",
                   help="Minimum new ideas to ask for (default: 20).")
    _add_slug(p)

    p = sub.add_parser("frame", help="record the agreed frame or the allocation grid")
    p.add_argument("--answer", action="append", default=[], metavar="KEY=TEXT",
                   help="One agreed answer, e.g. outcome=... (repeatable). "
                        "A different answer for a "
                        "recorded key replaces it and keeps the old one in frame_history.")
    p.add_argument("--amend", default=None, metavar="KEY",
                   help="Change one recorded answer: give the new text as the one --answer TEXT; "
                        "the previous answer is kept in frame_history.")
    state = p.add_mutually_exclusive_group()
    state.add_argument("--provisional", action="store_true",
                       help="Mark the frame provisional: later prompts treat it as "
                            "working assumptions.")
    state.add_argument("--confirm", action="store_true",
                       help="Mark the frame confirmed by the PM; later prompts say so.")
    p.add_argument("--allocation", default=None, metavar="TEXT",
                   help="The allocation grid as text. With --panel, a line `sN: <cell>` "
                        "gives shard N its cell.")
    _add_slug(p)


def _add_evidence(sub) -> None:
    """``evidence``, ``add-evidence`` and ``verify``: sourcing the shortlist and checking
    its quotes."""
    p = sub.add_parser("evidence", help="write the evidence prompt for shortlisted ideas")
    p.add_argument("idea_id", nargs="*", metavar="IDEA_ID",
                   help="Ideas to source (default: those recommended strong). More than 15 warns.")
    _add_slug(p)

    _add_add_evidence(sub)

    p = sub.add_parser("verify", help="check that each recorded quote appears on its page "
                                      "(asks before fetching)")
    p.add_argument("idea_id", nargs="*", metavar="IDEA_ID",
                   help="Default: every idea with unverified sources.")
    p.add_argument("--yes", action="store_true", help="Allow the fetch without asking (scripts).")
    _add_slug(p)


def _add_settle(sub) -> None:
    """``park``, ``decide``, ``merge`` and ``cluster``: the triage outcomes besides
    accept and reject."""
    p = sub.add_parser("park",
                       help="set ideas aside with a reason and, optionally, a revisit condition")
    p.add_argument("idea_id", nargs="+", metavar="IDEA_ID")
    p.add_argument("--reason", required=True, metavar="TEXT",
                   help="Required; recorded as the decision reason.")
    p.add_argument("--revisit-when", default="", metavar="TEXT",
                   help="Optional: what would make the idea worth another look.")
    _add_slug(p)

    p = sub.add_parser("decide", help="record the decision or policy an idea settled: "
                                      "status decided; "
                                      "promote writes it into the anchor's sheet instead of a node")
    p.add_argument("idea_id", metavar="IDEA_ID")
    p.add_argument("--decision", required=True, metavar="TEXT",
                   help="The decision, as it should read under the anchor sheet's "
                        "`## Decided policies`.")
    _add_slug(p)

    p = sub.add_parser("merge",
                       help="fold a duplicate idea into others: status merged, linked both ways")
    p.add_argument("idea_id", metavar="IDEA_ID")
    p.add_argument("--into", nargs="+", required=True, metavar="IDEA_ID",
                   help="The idea(s) it duplicates; each records the merged id in merged_from.")
    _add_slug(p)

    p = sub.add_parser("cluster",
                       help="record a converge cluster: its name, best statement and critics")
    p.add_argument("cluster_id", metavar="CID")
    p.add_argument("--name", default=None, metavar="TEXT",
                   help="What the cluster's ideas share ('' clears it).")
    p.add_argument("--best", default=None, metavar="IDEA_ID",
                   help="The member that states the bet best; it must already carry this "
                        "cluster id ('' clears it).")
    p.add_argument("--critic", action="append", default=None, metavar="ROLE: TEXT",
                   help="A critic's strongest objection to the cluster "
                        "(repeatable; same role replaces).")
    _add_slug(p)


def execution_milestone_from_promote_sets(pairs: list[str] | None) -> object:
    """Parse ``promote --set`` pairs; return :data:`INHERIT_EXECUTION_MILESTONE` when absent."""
    if not pairs:
        return INHERIT_EXECUTION_MILESTONE
    value: str | None = None
    for raw in pairs:
        if "=" not in raw:
            raise BrainstormError(
                f"promote --set expects KEY=VALUE (got {raw!r})"
            )
        key, _, raw_val = raw.partition("=")
        if key.strip() != "execution_milestone":
            raise BrainstormError(
                "promote --set only supports execution_milestone "
                f"(got {key.strip()!r})"
            )
        if raw_val.lower() in ("null", "~", ""):
            value = None
        elif raw_val not in EXEC_MILESTONES:
            raise BrainstormError(
                "execution_milestone must be one of "
                f"{sorted(EXEC_MILESTONES)} (got {raw_val!r})"
            )
        else:
            value = raw_val
    return value


def bound_parser(handlers: dict[str, Callable]) -> argparse.ArgumentParser:
    """The whole ``brainstorm`` parser, bound to ``handlers`` by name."""
    p = argparse.ArgumentParser(prog="specy-road brainstorm", description=_DESCRIPTION)
    sub = p.add_subparsers(dest="brainstorm_cmd", required=True)
    _add_start(sub)
    _add_add_idea(sub)
    _add_list(sub)
    _add_triage(sub)
    _add_converge(sub)
    _add_rounds(sub)
    _add_evidence(sub)
    _add_settle(sub)
    for name, fn in handlers.items():
        sub.choices[name].set_defaults(func=fn)
    return p


#: Subcommands a ``--from-file`` record stands for, and the builder that adds each one's flags.
_RECORD_BUILDERS = {"add-idea": _add_add_idea, "revise": _add_triage}


def record_parser(command: str) -> argparse.ArgumentParser:
    """``command``'s own parser, for one ``--from-file`` record: exact flag names only,
    errors raised."""
    sub = argparse.ArgumentParser().add_subparsers()
    _RECORD_BUILDERS[command](sub)
    p = sub.choices[command]
    p.allow_abbrev = False  # a record key must be a whole flag name

    def error(message: str):
        raise BrainstormError(message)

    p.error = error  # type: ignore[method-assign]
    return p


#: Keys a record may not carry: the session and the input are the command line's.
_NOT_RECORD_KEYS = ("slug", "repo-root", "from-file", "help")
#: The list key a YAML mapping holds its records under, per command.
_FILE_LIST_KEY = {"add-idea": "ideas", "revise": "verdicts"}


def _read_records(path: str, command: str) -> list:
    where = "stdin" if path == "-" else path
    try:
        text = sys.stdin.read() if path == "-" else Path(path).read_text(encoding="utf-8")
        lines = [ln for ln in text.splitlines() if ln.strip()]
        if lines and all(ln.lstrip().startswith("{") for ln in lines):
            return [json.loads(ln) for ln in lines]   # JSONL: one object per line
        raw = yaml.safe_load(text)
    except (OSError, ValueError, yaml.YAMLError) as e:
        raise BrainstormError(f"cannot read {where}: {e}") from e
    key = _FILE_LIST_KEY[command]
    records = raw.get(key) if isinstance(raw, dict) else raw
    if not isinstance(records, list) or not records:
        raise BrainstormError(f"{where}: expected a non-empty YAML list, a mapping with a "
                              f"`{key}:` list, "
                              "or JSONL with one object per line")
    return records


def _record_argv(record: dict, command: str) -> list[str]:
    """``{flag: value}`` -> the argv the single command would take; ``id`` is revise's IDEA_ID.

    Every value stays data: flags are ``--flag=value``, and the id follows ``--``, so an id or a
    value such as ``--help`` can never be read as an option."""
    argv, ident = [], []
    for key, value in record.items():
        flag = str(key).replace("_", "-")
        if flag in _NOT_RECORD_KEYS or (flag == "id" and command == "add-idea"):
            raise BrainstormError(f"key {key!r} is not allowed in a record")
        if flag == "id":
            ident = ["--", str(value)]
            continue
        values = value if isinstance(value, list) else [value]
        for v in values:
            if isinstance(v, dict):
                raise BrainstormError(f"key {key!r}: expected a string, number, boolean or list")
            if v is True:
                argv.append(f"--{flag}")
            elif v is not None and v is not False:
                argv.append(f"--{flag}={v}")
    return argv + ident


def file_namespaces(ns: argparse.Namespace, command: str) -> list[argparse.Namespace]:
    """Every record in ``--from-file`` parsed as ``command``'s own flags; the first bad
    one raises."""
    out = []
    for n, record in enumerate(_read_records(ns.from_file, command), 1):
        try:
            if not isinstance(record, dict) or not record:
                raise BrainstormError("expected a mapping of flag names to values")
            rec_ns = record_parser(command).parse_args(_record_argv(record, command))
            # false/null values add no argv, so check every key here
            for key, value in record.items():
                dest = str(key).replace("-", "_")
                if dest == "id":
                    continue
                if dest == "idea_id" or not hasattr(rec_ns, dest):
                    raise BrainstormError(f"unknown key {key!r}: not a {command} flag")
                if isinstance(value, list) and not isinstance(getattr(rec_ns, dest), list):
                    raise BrainstormError(f"key {key!r} takes one value, not a list")
            if command == "revise" and not rec_ns.idea_id:
                raise BrainstormError("needs `id`: the idea the verdict is for")
        except BrainstormError as e:
            raise BrainstormError(f"{ns.from_file} record {n}: {e} — nothing was written") from e
        out.append(rec_ns)
    return out
