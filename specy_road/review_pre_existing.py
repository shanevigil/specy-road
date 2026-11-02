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
    ---

The gate (:func:`review_files.verifier_gate_problems`) honours a claim only when
that file lists the command with two non-zero exits and its
``integration_commit`` is still the integration tip.
"""

from __future__ import annotations

import argparse
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


def integration_tip(repo_root: Path) -> str | None:
    """Full SHA of the integration branch tip, resolved as ``trial_merge_or_exit`` resolves it."""
    ib, remote, _warnings = resolve_integration_defaults(repo_root, explicit_base=None, explicit_remote=None)
    ref = base_ref(repo_root, remote, ib)
    return git_text(["rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"], repo_root) if ref else None


def claim_problem(record: dict[str, Any] | None, cmd: str, tip: str | None) -> str | None:
    """``None`` when ``record`` verifies the claim on ``cmd`` at ``tip``, else why not.

    ``unverified``: the command was never checked; ``stale: <sha>``: it was
    checked on an earlier tip; ``rejected``: it did not fail both times.
    """
    rows = {str(r.get("cmd")): r.get("exits") for r in (record or {}).get("commands") or [] if isinstance(r, dict)}
    if cmd not in rows:
        return "unverified"
    sha = str(record.get("integration_commit") or "")
    if tip is None or sha != tip:
        return f"stale: {sha[:12]}"
    exits = rows[cmd]
    if not isinstance(exits, list) or len(exits) != RUNS or any(type(e) is not int or e == 0 for e in exits):
        return "rejected"
    return None


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


def run_twice(repo_root: Path, sha: str, cmds: list[str]) -> list[dict[str, Any]] | str:
    """Each command's two exits at the project root of a detached worktree of ``sha``, or an error.

    Only this worktree is removed afterwards, so ``git worktree list`` ends as it began.
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
            exits = [subprocess.run(cmd, shell=True, cwd=cwd).returncode for _ in range(RUNS)]
            print(f"check-pre-existing on {sha[:12]}: {cmd} → exits {exits}")
            rows.append({"cmd": cmd, "exits": exits})
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
    rows = run_twice(root, tip, cmds) if tip else "cannot resolve the integration branch tip"
    if isinstance(rows, str):
        print(f"error: {rows}", file=sys.stderr)
        return 1
    dest = reviews_dir(root, ns.node_id) / PRE_EXISTING_NAME
    dest.write_text(render_front_matter({"integration_commit": tip, "commands": rows}), encoding="utf-8")
    print(f"Wrote {dest}")
    rejected = [r["cmd"] for r in rows if 0 in r["exits"]]
    for cmd in rejected:
        print(f"claim-rejected: {cmd}")
    return 1 if rejected else 0
