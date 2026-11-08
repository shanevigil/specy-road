#!/usr/bin/env python3
"""Replay recorded review packets through roster reviewers at two effort levels (M10.6).

Usage:
    python scripts/review_effort_study.py --model grok-4.7-high --levels high medium M3.16 M9.1 M3.13

For each packet ``work/reviews/<ID>/PACKET.md``, each ``--model`` (a roster reviewer) and
each level, the roster entry's ``channels.cli`` runs once and ``results.csv`` (under
``-o``, default ``work/effort-study``) gets one row with the verdict and block reasons.
Only that command runs, never a model API, so the reviewer is billed and sandboxed as the
roster has it. A level reaches the command the way M10.5 passes effort:

* a harness with an effort flag (``claude-code``, ``codex``): the command must name
  ``{effort}``, which becomes the flag for the level;
* a harness without one (``cursor``): the model id carries the effort, so the roster id
  must end in ``-<level>`` and appear in the command, and is swapped for ``<stem>-<level>``.

The replay files nothing: the reviewer gets a study preamble and the packet, runs in its
own directory under ``-o`` (prompt and output are kept there), and ends with a YAML block
the script reads. Every check runs before the first reviewer, and a study larger than
``--max-runs`` (the maintainer's budget, default 12) is refused whole.

``policy-evidence`` (M16.1.6) runs no reviewer and no network: it reads the review history under
``work/reviews`` and git, and counts per optional review policy how many review rounds it changed::

    python scripts/review_effort_study.py policy-evidence [NODE_ID ...] [-o DIR]

A case is one review round: node_key, commit and every record filed at that commit, from ``history/``
and each live ``REVIEW-*.md`` no history copy duplicates; a record's filing time is its history stamp,
else the end of its ``date`` day (:func:`filed_at`). It is
replayable when its records validate and its commit, node and ``roadmap/orchestration.yaml`` (the
integration branch's last commit before the round's latest filing time) all come back from git; the
policy's public evaluator then runs on the case with the policy as configured and with only that policy
disabled (:data:`POLICIES`). A case that is not replayable is cited-only when a record field or problem
sentence names the policy, else unknown. ``cases.csv`` under ``-o`` lists each case's provenance.
"""

from __future__ import annotations

import argparse
import copy
import csv
import functools
import json
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable

import yaml

from specy_road.git_subprocess import git_text
from specy_road.git_workflow_config import GIT_WORKFLOW_REL, resolve_integration_defaults
from specy_road.orchestration_config import (DEFAULT_CONFIG, DEFAULT_POLICY, family_of,
                                            load_orchestration_config)
from specy_road.orchestration_pinned import pinned_config
from specy_road.review_deferral import deferral_in_effect, load_markers
from specy_road.review_files import (PACKET_NAME, ReviewFile, latest_ready, list_rcas,
                                     list_review_history, list_reviews, reviews_dir, reviews_root)
from specy_road.review_gate import delta_problem
from specy_road.review_policy_ref import committed_yaml
from specy_road.review_pre_existing import PRE_EXISTING_NAME, gate_problems
from specy_road.review_rca import Round, escalation, review_rounds
from specy_road.review_resumed_delta import fresh_session_problem
from specy_road.review_strong import applicable_items
from specy_road.review_target import full_sha, node_at, same_commit
from specy_road.roadmap_json import nodes_from_chunk_doc
from specy_road.runtime_paths import project_prefix
from specy_road.runtime_paths import add_repo_root_arg, resolve_repo_root
from specy_road.worker_adapters import ADAPTERS, placeholder_problem, substitute_prompt

#: Cursor's effort suffixes on a model id (`agent --list-models`, 2026-11-02).
ID_LEVELS = ("none", "low", "medium", "high", "xhigh", "max")
COLUMNS = ("node_id", "commit", "model", "family", "level", "verdict", "block_reasons", "exit_code", "seconds")
PREAMBLE = """# Review replay: `{node}` (effort study)

You are one reviewer in a measurement of reviewer effort. Review the packet below as you
would for the gate: judge the commit it names against the brief's acceptance criteria.
Judge from the packet alone. Do not run commands, do not edit files, and do not run
`specy-road review record`: this replay files nothing.

End your reply with exactly one fenced block in this form, and nothing after it:

```yaml
verdict: approve        # or block
block_reasons: []       # when you block: one short line per reason, e.g. ["A2 fails: ..."]
```

---

"""


class StudyError(Exception):
    pass


def level_command(entry: dict, level: str) -> tuple[str, list[str]]:
    """``(cli, effort_args)`` for one level of the roster ``entry``: what :func:`substitute_prompt` takes."""
    cli, rid = (entry.get("channels") or {}).get("cli"), str(entry.get("id"))
    why = placeholder_problem(cli)
    if why:
        raise StudyError(f"{rid}: roster channels.cli: {why}")
    adapter = ADAPTERS.get(entry.get("harness") or "generic", ADAPTERS["generic"])
    if adapter.effort_flag(level):
        if "{effort}" not in cli:   # placeholder_problem has refused one inside a larger word
            raise StudyError(f"{rid}: channels.cli names no {{effort}}, so both levels would run the same: {cli}")
        return cli, adapter.effort_flag(level)
    stem, _, suffix = rid.rpartition("-")
    word = re.compile(rf"(?<![\w.-]){re.escape(rid)}(?![\w.-])")
    if suffix not in ID_LEVELS or not word.search(cli):
        raise StudyError(f"{rid}: {adapter.harness} carries effort in the model id, so the roster id must end in "
                         f"-<{'|'.join(ID_LEVELS)}> and appear in channels.cli: {cli}")
    if level not in ID_LEVELS:   # it is spliced into a shell command unquoted
        raise StudyError(f"{rid}: level {level!r} is not a {adapter.harness} effort suffix ({', '.join(ID_LEVELS)})")
    return word.sub(f"{stem}-{level}", cli), []


def packet_commit(text: str) -> str:
    m = re.search(r"\*\*Commit under review:\*\* `([0-9a-f]{7,40})`", text)
    return m.group(1) if m else ""


def parse_verdict(output: str) -> tuple[str, list[str]]:
    """The last fenced YAML block naming a verdict; ``unparsed`` when there is none."""
    for block in reversed(re.findall(r"```ya?ml\s*\n(.*?)```", output, re.S)):
        try:
            data = yaml.safe_load(block)
        except yaml.YAMLError:
            continue
        if isinstance(data, dict) and data.get("verdict") in ("approve", "block"):
            reasons = data.get("block_reasons") or []
            return data["verdict"], [str(r) for r in (reasons if isinstance(reasons, list) else [reasons])]
    return "unparsed", []


def plan(root: Path, models: list[str], levels: list[str], nodes: list[str], max_runs: int) -> list[tuple]:
    """Every run as ``(node, packet text, entry, level, cli, effort_args)``; raises before anything runs."""
    if len(set(levels)) != len(levels):
        raise StudyError(f"--levels {' '.join(levels)}: the levels must differ, or one level runs twice and "
                         "reads as a two-level study; nothing was run")
    total = len(nodes) * len(models) * len(levels)
    if total > max_runs:
        raise StudyError(f"{len(nodes)} packet(s) x {len(models)} model(s) x {len(levels)} level(s) = {total} "
                         f"reviewer runs, over the budget of {max_runs}; nothing was run")
    config, err = pinned_config(root)
    if err:
        raise StudyError(f"orchestration config: {err}")
    entries = {e.get("id"): e for e in config.get("roster") or []}
    runs = []
    for node in nodes:
        packet = reviews_dir(root, node) / PACKET_NAME
        if not packet.is_file():
            raise StudyError(f"no recorded packet at {packet}")
        text = packet.read_text(encoding="utf-8")
        for rid in models:
            entry = entries.get(rid)
            if entry is None or "reviewer" not in (entry.get("roles") or []):
                raise StudyError(f"{rid!r} is not a reviewer in the roster (roadmap/orchestration.yaml)")
            runs += [(node, text, entry, lv, *level_command(entry, lv)) for lv in levels]
    return runs


def run_one(out: Path, node: str, text: str, entry: dict, level: str, cli: str, effort: list[str],
            timeout: int) -> dict:
    run_dir = out / "runs" / node / f"{entry['id']}-{level}"
    run_dir.mkdir(parents=True, exist_ok=True)
    prompt = run_dir / "prompt.md"
    prompt.write_text(PREAMBLE.format(node=node) + text, encoding="utf-8")
    started = time.monotonic()
    try:
        done = subprocess.run(substitute_prompt(cli, prompt, effort=effort), shell=True, cwd=run_dir,
                              capture_output=True, text=True, timeout=timeout, check=False)
        output, code = done.stdout + done.stderr, done.returncode
    except subprocess.TimeoutExpired as e:
        output, code = f"{e.stdout or ''}{e.stderr or ''}\n(timed out after {timeout}s)", "timeout"
    (run_dir / "output.txt").write_text(str(output), encoding="utf-8")
    verdict, reasons = parse_verdict(str(output))
    return {"node_id": node, "commit": packet_commit(text), "model": entry["id"], "family": entry.get("family", ""),
            "level": level, "verdict": verdict, "block_reasons": " | ".join(reasons), "exit_code": code,
            "seconds": round(time.monotonic() - started)}


# --- policy-evidence (M16.1.6): which optional review policy changed a gate outcome ---------------------

OFF = 10**9   # an escalation threshold no review loop reaches: RCA escalation disabled
STAMP = re.compile(r"^(\d{4})(\d\d)(\d\d)T(\d\d)(\d\d)(\d\d)\d*Z-")   # history/<UTC stamp>-<model>.md
EVIDENCE_OUT = ("node_id", "node_key", "commit", "round", "records", "provenance")


class Missing(Exception):
    """The case lacks an input the policy's evaluator needs, so it cannot be replayed for that policy."""


class Case:
    """One review round of one node, with what git gives back for it at the round's filing time.

    A plain class, not a dataclass: the tests load this script without registering it in ``sys.modules``.
    """

    def __init__(self, root: Path, node_id: str, commit: str, round_no: int, rounds: list[Round],
                 records: list[ReviewFile]) -> None:
        self.root, self.node_id, self.commit = root, node_id, commit
        # 1-based, in filing order (review_rca.review_rounds); 0: a commit only a live REVIEW-*.md names
        self.round, self.rounds = round_no, rounds
        self.records = records    # every record at this commit (history, then live), not only the latest
        self.node: dict[str, Any] | None = None
        self.config: dict[str, Any] = {}
        self.workflow: dict[str, Any] = {}
        self.has_orchestration = False   # whether roadmap/orchestration.yaml existed then, not only defaults
        self.provenance = ""
        self.problem = ""         # why the case is not replayable; empty when it is

    def approvals(self) -> list[ReviewFile]:
        latest = {r.data["model"]: r for r in self.records}   # filing order: the last record wins
        return [r for r in latest.values() if r.data["verdict"] == "approve"]


def _delta(c: Case, policy: dict[str, Any]) -> Any:
    """Which delta approvals count: :func:`review_gate.delta_problem` (outcome: an approval counted)."""
    return tuple(delta_problem(c.root, c.node, r.data["delta_from"], c.commit, policy) is None
                 for r in c.approvals() if r.data.get("delta_from"))


def _resumed(c: Case, policy: dict[str, Any]) -> Any:
    """Which approvals pass the fresh-session rule: :func:`review_resumed_delta.fresh_session_problem`."""
    return tuple(fresh_session_problem(policy, r.data, None) is None for r in c.approvals())


def _red_green(c: Case, policy: dict[str, Any]) -> Any:
    """Off: no problem. On: the replay needs RED-GREEN.md and planned_test_changes as they were then."""
    if policy.get("red_green"):
        raise Missing("red_green was on; RED-GREEN.md and planned_test_changes are not reconstructed")
    return ()


def _pre_existing(c: Case, policy: dict[str, Any]) -> Any:
    """Failing READY verifiers left as gate problems: :func:`review_pre_existing.gate_problems`."""
    claims = {str(x) for r in c.approvals() for x in r.data.get("verify_pre_existing") or []}
    if not claims:
        return ()
    ready = latest_ready(c.root, c.node_id)
    if ready is None or not same_commit(c.root, ready.data["commit"], c.commit) or \
            not (ready.path.parent / PRE_EXISTING_NAME).is_file():
        raise Missing("a pre-existing claim, but no READY and PRE-EXISTING.md at this commit")
    failing = [v for v in ready.data.get("verify") or [] if v.get("exit") != 0]
    return tuple(gate_problems(ready, failing, claims if policy.get("pre_existing", True) else set()))


def _deferral(c: Case, policy: dict[str, Any]) -> Any:
    """Blocks of this round a DEFERRAL marker in effect resolves (:func:`review_deferral.deferral_in_effect`)."""
    if not policy.get("deferral", True):
        return ()
    blocks = [r for r in c.records if r.data["verdict"] == "block"]
    return tuple(m.name for m in load_markers(c.root, c.node_id)[0]
                 if any(x["reviewer"] == b.data["model"] and same_commit(c.root, x["commit"], c.commit)
                        for x in m.items for b in blocks) and not deferral_in_effect(c.root, c.node_id, m))


def _rca(c: Case, policy: dict[str, Any]) -> Any:
    """The escalation rule :func:`review_rca.escalation` starts at this round; an RCA filed for the round
    that the configured policy does not reproduce makes the case unreplayable."""
    if c.round == 0:   # the RCA rule reads history alone, so it never counted this commit
        return None
    triggers = [r.data["trigger"] for r in list_rcas(c.root, c.node_id) if r.ok]
    resolved = max((int(t["round"]) for t in triggers if int(t["round"]) < c.round), default=0)
    fam: Callable[[str], str] = lambda m: family_of(c.config, m) or m
    filed = any(int(t["round"]) == c.round and t["rule"] != "forced" for t in triggers)
    if filed and escalation(c.rounds[:c.round], c.config["policy"], resolved, fam) is None:
        raise Missing("an RCA was filed at this round, but the configured policy does not escalate")
    now = escalation(c.rounds[:c.round], policy, resolved, fam)
    before = escalation(c.rounds[:c.round - 1], policy, resolved, fam) if c.round - 1 > resolved else None
    return now.rule if now and not before else None


def _strong(c: Case, policy: dict[str, Any]) -> Any:
    """Applicable ``strong_review`` items no approval of the round meets (:mod:`review_strong`)."""
    models = {r.data["model"] for r in c.approvals()}
    items = applicable_items(policy, (c.node or {}).get("touch_zones"), project_prefix(c.root))
    return tuple(i for i, item in items if not models & set(item.get("require_one_of") or []))


def _agreement(c: Case, policy: dict[str, Any]) -> Any:
    """review_gate_agreement's rule at the round's time: reviewers asked for while finish skips the gate."""
    finish_gate = bool(c.workflow.get("require_implementation_review_before_finish"))   # absent: off
    asks = c.has_orchestration and int(policy["reviewers_required"]) >= 1   # absent file: asks for none
    return policy.get("agreement", True) and asks and not finish_gate


#: policy -> (evaluator, the policy with only it disabled, citation pattern, outcome counted when it changes).
POLICIES: dict[str, tuple[Callable[[Case, dict[str, Any]], Any], dict[str, Any], str, str]] = {
    "delta": (_delta, {"delta_review": False}, r"delta_from|delta_review|delta review",
              "a delta approval counted that is refused without it"),
    "resumed delta": (_resumed, {"reviewer_resumed_delta": False},
                      r"reviewer_resumed_delta|resumed delta|fresh_session: false",
                      "a resumed approval counted that is refused without it"),
    "red-green": (_red_green, {"red_green": False}, r"red_green|red-green", "a gate block it caused"),
    "pre-existing": (_pre_existing, {"pre_existing": False}, r"verify_pre_existing|pre-existing",
                     "a failing verifier it cleared"),
    "deferral": (_deferral, {"deferral": False}, r"deferral|defer_findings|review defer",
                 "a deferral it forced (a block resolved)"),
    "RCA escalation": (_rca, {"escalate_same_acceptance_blocks": OFF, "escalate_review_rounds": OFF},
                       r"\bRCA\b|escalat", "an RCA escalation it forced"),
    "strong review": (_strong, {"strong_review": []}, r"strong_review|strong review",
                      "a gate block it caused"),
    "agreement": (_agreement, {"agreement": False},
                  r"require_implementation_review_before_finish|review_gate_agreement",
                  "a validate/doctor error it raised"),
}


@functools.cache
def node_then(root: Path, node_id: str, commit: str) -> dict[str, Any] | None:
    """``node_id`` as ``commit`` records it: :func:`review_target.node_at`, else (a node archived or moved
    since) the chunk ``roadmap/manifest.json`` at ``commit`` lists that holds it."""
    found = node_at(root, node_id, commit)
    try:
        includes = json.loads(git_text(["show", f"{commit}:./roadmap/manifest.json"], root) or "{}")["includes"]
    except (ValueError, KeyError, TypeError):
        includes = []
    for rel in includes if found is None else []:
        try:
            nodes = nodes_from_chunk_doc(json.loads(git_text(["show", f"{commit}:./roadmap/{rel}"], root) or "null"))
        except ValueError:
            continue
        found = next((n for n in nodes or [] if n.get("id") == node_id), None)
        if found is not None:
            break
    return found


def filed_at(r: ReviewFile) -> tuple[str, bool]:
    """``(UTC time, from the date field)``: a record's filing time, the one rule for every record. A history
    copy's name carries it; a record without that stamp (a live ``REVIEW-*.md`` or a ``superseded-*`` copy)
    counts as filed at the end of its own ``date`` day, so the config found may be up to a day later than
    the review. ``("", False)`` when neither exists."""
    m = STAMP.match(r.path.name)
    if m:
        return "{}-{}-{}T{}:{}:{}Z".format(*m.groups()), False
    day = str(r.data.get("date") or "") if isinstance(r.data, dict) else ""
    return (f"{day}T23:59:59Z", True) if re.fullmatch(r"\d{4}-\d\d-\d\d", day) else ("", False)


def reconstruct(case: Case, branch: str) -> Case:
    """Fill ``case`` from git at the round's latest filing time; ``problem`` says what did not come back."""
    times = [filed_at(r) for r in case.records]
    commit = full_sha(case.root, case.commit)
    case.node = node_then(case.root, case.node_id, commit) if commit else None
    at = max((t for t, _ in times if t), default="")
    rev = git_text(["rev-list", "-1", "--first-parent", f"--before={at}", branch], case.root) if at else ""
    data, err = load_orchestration_config(case.root, rev) if rev else (None, None)
    case.problem = next((why for bad, why in (
        (not all(r.ok for r in case.records), "a record does not validate"),
        (not all(t for t, _ in times), "a record has no filing time"), (not commit, "the commit is not in git"),
        (case.node is None, "the node is not readable at the commit"),
        (not rev, f"no {branch} commit before {at}"), (bool(err), str(err))) if bad), "")
    if case.problem:
        return case
    case.commit = commit
    case.config = copy.deepcopy(data or DEFAULT_CONFIG)
    case.config["policy"] = {**DEFAULT_POLICY, **(case.config.get("policy") or {})}
    case.has_orchestration = data is not None
    case.workflow = committed_yaml(case.root, rev, GIT_WORKFLOW_REL.as_posix())
    dated = sum(by_date for _, by_date in times)
    case.provenance = (f"{len(case.records)} record(s) filed by {at}"
                       f"{f' ({dated} by their date field)' if dated else ''}; orchestration.yaml and "
                       f"git-workflow.yaml at {branch}@{rev[:12]}{'' if data else ' (absent: defaults)'}")
    return case


def node_cases(root: Path, node_id: str, branch: str) -> list[Case]:
    """Every reviewed commit of ``node_id`` with its full record set, reconstructed from git.

    The records are the history's and every live ``REVIEW-*.md`` no history record duplicates (same
    model, commit and verdict): one ``review record`` did not archive. Commits come in the history's round order, then the commits only a
    live record names. A record naming no commit (invalid) cannot join a case and is left out.
    """
    rounds, history = review_rounds(root, node_id), list_review_history(root, node_id)
    def vote(r: ReviewFile) -> tuple[Any, ...]:   # fields a live copy may add (independence) are ignored
        d = r.data if isinstance(r.data, dict) else {}
        return d.get("model"), full_sha(root, str(d.get("commit") or "")), d.get("verdict")
    archived = {vote(h) for h in history}
    live = [r for r in list_reviews(root, node_id) if vote(r) not in archived]
    order, by_commit = {rnd.commit: i for i, rnd in enumerate(rounds, 1)}, {rnd.commit: [] for rnd in rounds}
    for r in history + live:
        raw = str(r.data.get("commit") or "") if isinstance(r.data, dict) else ""
        if raw:
            by_commit.setdefault(full_sha(root, raw) or raw, []).append(r)
    return [reconstruct(Case(root, node_id, commit, order.get(commit, 0), rounds, records), branch)
            for commit, records in by_commit.items()]


def moves_others(case: Case, name: str) -> list[str]:
    """The other policies whose outcome moves when only ``name`` is disabled; a change is counted only
    when this is empty, so one policy's count never carries another's."""
    policy, off = case.config["policy"], POLICIES[name][1]
    moved = []
    for other, (evaluate, *_) in POLICIES.items():
        try:
            if other != name and evaluate(case, policy) != evaluate(case, {**policy, **off}):
                moved.append(other)
        except Missing:
            continue
    return moved


def classify(case: Case, name: str) -> str:
    """``changed``, ``unchanged``, ``cited-only`` or ``unknown`` for one policy on one case."""
    evaluate, off, pattern, _ = POLICIES[name]
    if not case.problem:
        try:
            on = evaluate(case, case.config["policy"])
            if on == evaluate(case, {**case.config["policy"], **off}):
                return "unchanged"
            if not moves_others(case, name):
                return "changed"
        except Missing:
            pass
    text = "\n".join(yaml.safe_dump(r.data) for r in case.records if isinstance(r.data, dict))
    return "cited-only" if re.search(pattern, text, re.I) else "unknown"


def evidence_main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="review_effort_study.py policy-evidence",
                                description="Count how often each optional review policy changed a gate "
                                            "outcome, from work/reviews history and git (M16.1.6).")
    p.add_argument("nodes", nargs="*", metavar="NODE_ID", help="Leaves to count (default: every leaf)")
    p.add_argument("-o", "--output", type=Path, help="Directory for cases.csv (default work/policy-evidence)")
    add_repo_root_arg(p)
    ns = p.parse_args(argv)
    root = resolve_repo_root(ns)
    branch = resolve_integration_defaults(root, explicit_base=None, explicit_remote=None)[0]
    top = reviews_root(root)
    nodes = ns.nodes or (sorted(d.name for d in top.iterdir() if d.is_dir() and not d.name.startswith("."))
                         if top.is_dir() else [])
    cases = [c for n in nodes for c in node_cases(root, n, branch)]
    nodes = sorted({c.node_id for c in cases})
    rows = [{"node_id": c.node_id, "node_key": (c.node or {}).get("node_key", ""), "commit": c.commit,
             "round": c.round or "live", "records": len(c.records), "provenance": c.provenance or c.problem,
             **{name: classify(c, name) for name in POLICIES}} for c in cases]
    out = (ns.output or root / "work" / "policy-evidence").resolve()
    out.mkdir(parents=True, exist_ok=True)
    with (out / "cases.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[*EVIDENCE_OUT, *POLICIES])
        writer.writeheader()
        writer.writerows(rows)
    print(f"{len(cases)} case(s) from {len(nodes)} node(s); "
          f"{sum(not c.problem for c in cases)} with full provenance; cases in {out / 'cases.csv'}\n")
    print("| Policy | Replayable | Changed | Cited-only | Unknown | Changed means |\n|---|---|---|---|---|---|")
    for name, (*_, means) in POLICIES.items():
        n = {k: sum(r[name] == k for r in rows) for k in ("changed", "unchanged", "cited-only", "unknown")}
        print(f"| {name} | {n['changed'] + n['unchanged']} | {n['changed']} | {n['cited-only']} | "
              f"{n['unknown']} | {means} |")
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["policy-evidence"]:
        return evidence_main(argv[1:])
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("nodes", nargs="+", metavar="NODE_ID", help="Leaves whose work/reviews/<ID>/PACKET.md to replay")
    p.add_argument("--model", action="append", required=True, help="Roster reviewer id (repeatable)")
    p.add_argument("--levels", nargs=2, required=True, metavar=("LEVEL", "LEVEL"),
                   help="The model's own effort levels, e.g. high medium")
    p.add_argument("--max-runs", type=int, default=12, help="Refuse a study with more reviewer runs (default 12)")
    p.add_argument("--timeout", type=int, default=1800, help="Seconds per reviewer run (default 1800)")
    p.add_argument("-o", "--output", type=Path, help="Study directory (default work/effort-study)")
    add_repo_root_arg(p)
    ns = p.parse_args(argv)
    root = resolve_repo_root(ns)
    out = (ns.output or root / "work" / "effort-study").resolve()   # each run's cwd is its own directory
    try:
        runs = plan(root, ns.model, ns.levels, ns.nodes, ns.max_runs)
    except StudyError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    out.mkdir(parents=True, exist_ok=True)
    with (out / "results.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        for i, run in enumerate(runs, 1):
            print(f"run {i}/{len(runs)}: {run[0]} {run[2]['id']} at {run[3]}", file=sys.stderr)
            writer.writerow(run_one(out, *run, timeout=ns.timeout))
            f.flush()
    print(f"{len(runs)} reviewer run(s); results in {out / 'results.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
