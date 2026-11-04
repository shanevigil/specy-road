"""Verified pre-existing claims: ``specy-road review check-pre-existing <NODE_ID>``.

An approving reviewer may name a failing READY verifier in
``verify_pre_existing``: it already fails on the integration branch, so the leaf
did not break it. On the reviewer's word alone that is an LLM judgement deciding
a gate. This module makes the claim a reproduced fact: each claimed command runs
twice through the shell, at the project root of a detached temporary worktree
of the integration tip, and the exits are written to
``work/reviews/<NODE_ID>/PRE-EXISTING.md``::

    ---
    integration_commit: <full sha of the tip the commands ran on>
    commands:
      - {cmd: pytest -q tests/x.py, exits: [1, 1]}
      - {cmd: pytest -q tests/new.py, exits: [], unverified: "names tests/new.py, which <sha> does not have"}
    ---

The gate (:func:`review_files.verifier_gate_problems`) honours a claim only when
that file lists the command with two non-zero exits and its
``integration_commit`` is still the integration tip. Two exits that say the
command could not run what it named (:data:`NO_EVIDENCE`) are no evidence, and a
command naming a path the leaf has but the tip lacks is not run at all: it fails
on the tip only because the leaf adds that file.
"""

from __future__ import annotations

import argparse
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from specy_road.bundled_scripts.brief_acceptance import acceptance_ids
from specy_road.finish_implementation_check import base_ref
from specy_road.git_subprocess import git_code, git_text
from specy_road.git_workflow_config import resolve_integration_defaults
from specy_road.review_files import (
    ReviewFile,
    _read,
    failing_verifier_entries,
    latest_ready,
    pre_existing_cmds_from_approvals,
    render_front_matter,
    reviews_dir,
)
from specy_road.review_gate import evaluate_gate
from specy_road.review_target import ReviewTargetError, resolve_target
from specy_road.runtime_paths import project_prefix, resolve_repo_root

PRE_EXISTING_NAME = "PRE-EXISTING.md"
RUNS = 2
#: Exits that say the command could not run what it named, not that a check failed.
NO_EVIDENCE = {126: "not executable", 127: "command not found", 4: "pytest usage error or no such file",
               5: "pytest collected no tests"}


def integration_tip(repo_root: Path) -> str | None:
    """Full SHA of the integration branch tip, resolved as ``trial_merge_or_exit`` resolves it."""
    ib, remote, _warnings = resolve_integration_defaults(repo_root, explicit_base=None, explicit_remote=None)
    ref = base_ref(repo_root, remote, ib)
    return git_text(["rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"], repo_root) if ref else None


def _rows(record: dict[str, Any] | None) -> dict[str, tuple[list[int], str | None]]:
    """``cmd -> (exits, recorded reason it is no evidence)`` for each well-formed entry; anything else is
    no evidence, so its claim stays unverified."""
    commands = (record or {}).get("commands")
    out: dict[str, tuple[list[int], str | None]] = {}
    for r in commands if isinstance(commands, list) else []:
        if not (isinstance(r, dict) and isinstance(r.get("cmd"), str)):
            continue
        exits, why = r.get("exits"), r.get("unverified") if isinstance(r.get("unverified"), str) else None
        ok = isinstance(exits, list) and len(exits) == RUNS and all(type(e) is int for e in exits)
        if ok or why:
            out[r["cmd"]] = (exits if ok else [], why)
    return out


def _exit_problem(exits: list[int]) -> str | None:
    bad = next((e for e in exits if e in NO_EVIDENCE), None)
    return None if bad is None else f"exit {bad} ({NO_EVIDENCE[bad]}) is no evidence"


def absent_paths(repo_root: Path, leaf: str | None, tip: str, cmd: str) -> list[str]:
    """Paths ``cmd`` names that the leaf commit has and ``tip`` lacks (a test file the leaf adds).

    A word is a repository path when it exists at ``leaf`` (pytest's ``path::test`` counts as ``path``).
    """
    try:
        words = shlex.split(cmd)
    except ValueError:
        words = cmd.split()
    prefix, out = project_prefix(repo_root), []
    for w in dict.fromkeys(words):
        rel = w.split("::", 1)[0].removeprefix("./").rstrip("/")
        if not leaf or not rel or rel.startswith(("-", "/")) or ".." in rel.split("/"):
            continue
        exists = [git_code(["cat-file", "-e", f"{sha}:{prefix}{rel}"], repo_root)[0] == 0 for sha in (leaf, tip)]
        if exists == [True, False]:
            out.append(rel)
    return out


def claim_problem(record: dict[str, Any] | None, cmd: str, tip: str | None) -> str | None:
    """``None`` when ``record`` verifies the claim on ``cmd`` at ``tip``, else why not.

    ``unverified``: the command was never checked (or its entry is malformed);
    ``stale: <sha>``: it was checked on an earlier tip; ``rejected``: it did
    not fail both times; ``unverified: <why>``: its run is no evidence.
    """
    rows = _rows(record)
    if cmd not in rows:
        return "unverified"
    sha = str(record.get("integration_commit") or "")
    if tip is None or sha != tip:
        return f"stale: {sha[:12]}"
    exits, why = rows[cmd]
    if 0 in exits:
        return "rejected"
    why = why or _exit_problem(exits)
    return f"unverified: {why}" if why else None


def gate_problems(ready: ReviewFile, failing: list[dict[str, Any]], claimed: set[str]) -> list[str]:
    """One problem per failing verifier, unless a verified claim clears it; claimed ones say why not."""
    record = tip = None
    if any(str(v["cmd"]) in claimed for v in failing):
        data, _body, errs = _read(ready.path.parent / PRE_EXISTING_NAME)
        record = None if errs else data
        # READY lives at <project>/work/reviews/<ID>/, in the main worktree when asked from a linked one.
        tip = integration_tip(ready.path.parents[3])
    out = []
    for v in failing:
        why = claim_problem(record, str(v["cmd"]), tip) if str(v["cmd"]) in claimed else ""
        if why is not None:
            out.append(f"{ready.path.name} (executor-reported): verifier `{v['cmd']}` exited {v['exit']}"
                       + (f" ({why})" if why else ""))
    return out


def run_twice(repo_root: Path, sha: str, cmds: list[str], leaf: str | None = None) -> list[dict[str, Any]] | str:
    """Each command's two exits at the project root of a detached worktree of ``sha``, or an error.

    A command naming a path ``leaf`` has and ``sha`` lacks is not run; it and a run whose exits are no
    evidence are recorded ``unverified`` with the reason. Only this worktree is removed afterwards, so
    ``git worktree list`` ends as it began.
    """
    holder = Path(tempfile.mkdtemp(prefix="specy-road-pre-existing-"))
    worktree = holder / "tree"
    code, out = git_code(["worktree", "add", "--detach", str(worktree), sha], repo_root)
    if code != 0:
        shutil.rmtree(holder, ignore_errors=True)
        return f"could not create a worktree of {sha}: {out}"
    try:
        cwd = worktree / project_prefix(repo_root)
        rows = []
        for cmd in cmds:
            if absent := absent_paths(repo_root, leaf, sha, cmd):
                why = f"names {', '.join(absent)}, which {sha[:12]} does not have"
                print(f"check-pre-existing on {sha[:12]}: {cmd} → not run: {why}")
                rows.append({"cmd": cmd, "exits": [], "unverified": why})
                continue
            exits = [subprocess.run(cmd, shell=True, cwd=cwd).returncode for _ in range(RUNS)]
            print(f"check-pre-existing on {sha[:12]}: {cmd} → exits {exits}")
            why = None if 0 in exits else _exit_problem(exits)
            rows.append({"cmd": cmd, "exits": exits, **({"unverified": why} if why else {})})
        return rows
    finally:
        git_code(["worktree", "remove", "--force", str(worktree)], repo_root)
        shutil.rmtree(holder, ignore_errors=True)


def cmd_check_pre_existing(ns: argparse.Namespace) -> int:
    """Run every claimed failing READY verifier twice on the integration tip; record the exits."""
    root = resolve_repo_root(ns)
    try:
        t = resolve_target(root, ns.node_id, ns.ref)
    except ReviewTargetError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    branch = (t.entry or {}).get("branch")
    gate = evaluate_gate(root, t.node, t.commit, branch=branch)
    ready = latest_ready(root, ns.node_id, branch, acceptance_ids(t.node))
    claimed = pre_existing_cmds_from_approvals(gate.approvals)
    cmds = list(dict.fromkeys(str(v["cmd"]) for v in (failing_verifier_entries(ready) if ready else [])
                              if str(v["cmd"]) in claimed))
    if not cmds:
        print(f"{ns.node_id}: no failing READY verifier is claimed pre-existing by a counted approval.")
        return 0
    tip = integration_tip(root)
    rows = run_twice(root, tip, cmds, t.commit) if tip else "cannot resolve the integration branch tip"
    if isinstance(rows, str):
        print(f"error: {rows}", file=sys.stderr)
        return 1
    dest = reviews_dir(root, ns.node_id) / PRE_EXISTING_NAME
    dest.write_text(render_front_matter({"integration_commit": tip, "commands": rows}), encoding="utf-8")
    print(f"Wrote {dest}")
    rejected = [r["cmd"] for r in rows if 0 in r["exits"]]
    for cmd in rejected:
        print(f"claim-rejected: {cmd}")
    unverified = [r for r in rows if r.get("unverified")]
    for r in unverified:
        print(f"claim-unverified: {r['cmd']} ({r['unverified']})")
    return 1 if rejected or unverified else 0
