"""READY-adjacent gate helpers: the interactive human approval, the trial merge, and ``specy-road ready``."""

from __future__ import annotations

import argparse
import sys
import tempfile
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from specy_road.bundled_scripts.brief_acceptance import acceptance_ids
from specy_road.finish_implementation_check import base_ref
from specy_road.git_changed_paths import diff_paths
from specy_road.git_subprocess import commits_behind, git_text, merge_conflicts
from specy_road.git_workflow_config import resolve_integration_defaults
from specy_road.orchestration_config import effective_config, roster_entry
from specy_road.review_files import (
    HUMAN, READY_PREFIX, load_ready, render_front_matter, review_path, reviews_dir, write_review,
)
from specy_road.review_policy_ref import policy_source
from specy_road.review_signing import NOTES_KEY, SigningError, notes_digest, sign, verify
from specy_road.review_target import ReviewTargetError, full_sha, resolve_target
from specy_road.runtime_paths import add_repo_root_arg, project_prefix, rebase_to_project, resolve_repo_root


def write_human_approval(repo_root: Path, node: dict[str, Any], commit: str, sign_key: Path | None = None) -> Path:
    """File the interactive approval as ``REVIEW-human.md`` at ``commit``, signed when a key is given.

    A signature is verified against the roster's ``human`` ``public_key``
    before anything is written: a wrong key raises :class:`SigningError` and
    leaves no record behind, as ``review record --sign-key`` does.
    """
    body = "Approved interactively with `specy-road mark-implementation-reviewed`.\n"
    data = {
        "node_id": node["id"],
        "model": HUMAN,
        "family": HUMAN,
        "date": date.today().isoformat(),
        "verdict": "approve",
        "commit": commit,
        "acceptance": {aid: "pass" for aid in acceptance_ids(node)},
        "findings": {"correctness": [], "regression": [], "boundary": [], "test_integrity": []},
        "commands_rerun": [],
        "required_changes": [],
        "fresh_session": True,
        "authored_fix": False,
        # Whoever runs mark-implementation-reviewed is coordinating; say so.
        "is_coordinator": True,
        NOTES_KEY: notes_digest(body),
    }
    if sign_key is not None:
        data["signature"] = sign(data, sign_key)
        config, _err = effective_config(repo_root, policy_source(repo_root)[0])
        pub = (roster_entry(config, HUMAN) or {}).get("public_key")
        ok, why = verify(data, data["signature"], str(pub or ""), HUMAN)
        if not ok:
            raise SigningError(f"the signature does not verify against the roster public_key for "
                               f"{HUMAN!r} ({why}); wrong key?")
    path = review_path(repo_root, node["id"], HUMAN)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_front_matter(data, body), encoding="utf-8")
    return path


#: Project-relative bookkeeping, where a trial-merge conflict blocks nothing; ``x/`` covers below x, a file only itself.
TRIAL_MERGE_BOOKKEEPING = ("work/", "roadmap/", "planning/", "roadmap.md", "roadmap-context.md")


def is_trial_merge_bookkeeping(project_path: str) -> bool:
    return any(project_path.startswith(b) if b.endswith("/") else project_path == b for b in TRIAL_MERGE_BOOKKEEPING)


@dataclass(frozen=True)
class TrialMerge:
    """Merging the integration branch into a branch, done in memory; ``problem()`` says why review waits."""
    base_ref: str
    behind: int
    conflicts: list[str]        # project-relative; outside the project, ``../``-relative
    code_conflicts: list[str]   # the ones that block: not bookkeeping, or outside the project

    def problem(self) -> str | None:
        return (f"{self.base_ref} is {self.behind} commit(s) ahead and a trial merge conflicts on "
                f"{', '.join(self.code_conflicts)}: merge it into this branch and resolve before review"
                ) if self.code_conflicts else None


def trial_merge(repo_root: Path, ref: str, integration_ref: str | None) -> TrialMerge | None:
    """Trial-merge ``integration_ref`` into ``ref``, or ``None`` when git cannot answer."""
    behind = commits_behind(repo_root, ref, integration_ref) if integration_ref else None
    conflicts = merge_conflicts(repo_root, ref, integration_ref) if integration_ref and behind else []
    if integration_ref is None or behind is None or conflicts is None:
        return None
    prefix = project_prefix(repo_root)
    rebased = {p: rebase_to_project(p, prefix) for p in conflicts}   # None: outside the project
    named = {p: r if r is not None else "../" * prefix.count("/") + p for p, r in rebased.items()}
    code = [named[p] for p, r in rebased.items() if r is None or not is_trial_merge_bookkeeping(r)]
    return TrialMerge(integration_ref, behind, list(named.values()), code)


def trial_merge_or_exit(repo_root: Path) -> None:
    """Refuse before any bookkeeping commit while landing ``HEAD`` would conflict on code."""
    ib, remote, _warnings = resolve_integration_defaults(repo_root, explicit_base=None, explicit_remote=None)
    tm = trial_merge(repo_root, "HEAD", base_ref(repo_root, remote, ib))
    if tm is None or tm.problem() is None:
        return
    print(f"error: {tm.problem()}.", file=sys.stderr)
    print(f"  Run `git merge {tm.base_ref}`, resolve, commit, and have the result reviewed.", file=sys.stderr)
    raise SystemExit(1)


def policy_source_line(root: Path) -> str:
    """The packet's ``Policy source`` line: where the gate reads its policy from."""
    ref, err = policy_source(root)
    if err:
        return f"- **Policy source:** _{err}_ (the gate fails closed)"
    if ref is None:
        return "- **Policy source:** _the working tree (not a git checkout)_"
    return f"- **Policy source:** `{ref}` @ `{full_sha(root, ref) or '?'}`"


def trial_merge_lines(root: Path, ref: str | None, integration_ref: str | None) -> list[str]:
    """Whether the branch tip still merges into the integration branch; a code conflict stops review."""
    tm = trial_merge(root, ref, integration_ref)
    if tm is None:
        return ["- **Trial merge:** _git could not answer_"]
    ahead = f"`{tm.base_ref}` is {tm.behind} commit(s) ahead"
    if not tm.conflicts:
        return [f"- **Trial merge:** {ahead}; merges cleanly" if tm.behind else
                f"- **Trial merge:** up to date with `{tm.base_ref}`"]
    names = ", ".join(f"`{p}`" for p in tm.conflicts)
    if tm.problem() is None:
        return [f"- **Trial merge:** {ahead}; conflicts on bookkeeping only ({names}), which does not block"]
    return [f"- **Trial merge:** {ahead}; **conflicts on {names}**", "",
            f"**Stop: {tm.problem()}.** Reviewing this commit is wasted work: the merge makes it stale.", ""]


def parse_check(spec: str) -> tuple[str, int]:
    """``'<cmd>=<exit>'`` as ``(cmd, exit)``; the last ``=`` splits, so the command may contain one."""
    cmd, sep, code = spec.rpartition("=")
    try:
        if sep and cmd.strip():
            return cmd.strip(), int(code)
    except ValueError:
        pass
    raise ValueError(f"{spec!r}: expected '<cmd>=<exit>', e.g. 'pytest tests/test_x.py=0'")


def ready_body(red_green: list[tuple[str, int]], note: str | None) -> str:
    """Red-green evidence stays out of ``verify``: a non-zero exit there fails the gate."""
    out = []
    if red_green:
        out += ["## Red-green evidence", "",
                "Checks that fail without the fix, by design; listed here, not under `verify`, so they do not gate.",
                "", *(f"- `{cmd}` exited {code}" for cmd, code in red_green), ""]
    if note:
        out += [note.strip(), ""]
    return "\n".join(out)


def cmd_ready(ns: argparse.Namespace) -> int:
    """Write ``READY-<model>.md`` for ``HEAD``, validated by the loader ``handoff status`` uses; exit 1 on refusal."""
    root = resolve_repo_root(ns)
    try:
        verify = [parse_check(s) for s in ns.verify]
        red_green = [parse_check(s) for s in ns.red_green]
        t = resolve_target(root, ns.node_id, "HEAD")
    except (ValueError, ReviewTargetError) as e:
        return _refuse(str(e))
    failing = [f"`{cmd}` exited {code}" for cmd, code in verify if code != 0]
    if failing:
        return _refuse(f"failing verifier: {'; '.join(failing)}. Fix it, or, if it is a check meant to fail "
                       "without the fix, pass it as --red-green instead of --verify")
    branch = git_text(["branch", "--show-current"], root)
    if not branch or not t.base or not t.commit:
        return _refuse("needs a checked-out branch with a merge base on the integration branch")
    changed = diff_paths(root, f"{t.base}...{t.commit}")
    if changed is None:
        return _refuse(f"git cannot list the paths changed in {t.base[:12]}...{t.commit[:12]}")
    data = {"node_id": ns.node_id, "agent": ns.model, "branch": branch, "commit": t.commit, "base": t.base,
            "changed_paths": changed, "verify": [{"cmd": cmd, "exit": code} for cmd, code in verify]}
    text = render_front_matter(data, ready_body(red_green, ns.note))
    with tempfile.TemporaryDirectory() as td:   # the same checks handoff status makes, before anything is written
        (Path(td) / "READY.md").write_text(text, encoding="utf-8")
        errs = load_ready(Path(td) / "READY.md", ns.node_id, (t.entry or {}).get("branch"),
                          acceptance_ids(t.node)).errors
    if errs:
        return _refuse("; ".join(errs))
    dest = reviews_dir(root, ns.node_id) / f"{READY_PREFIX}{ns.model}.md"
    write_review(dest, text)
    print(f"Wrote {dest} at {t.commit[:12]}")
    return 0


def _refuse(msg: str) -> int:
    print(f"error: {msg}", file=sys.stderr)
    return 1


def add_ready_parser(sub: argparse._SubParsersAction) -> None:
    r = sub.add_parser("ready", help="Write the executor's READY hand-off for HEAD into work/reviews/<NODE_ID>/")
    r.add_argument("node_id")
    r.add_argument("--model", required=True, help="Your roster id; the file is READY-<model>.md")
    r.add_argument("--verify", action="append", default=[], metavar="CMD=EXIT",
                   help="A verifier or test you ran and its exit (repeatable); a non-zero exit is refused")
    r.add_argument("--red-green", action="append", default=[], metavar="CMD=EXIT",
                   help="A check that fails without the fix, by design (repeatable); goes in the notes, not verify")
    r.add_argument("--note", help="Notes for the coordinator: anything you could not finish, and why")
    add_repo_root_arg(r)
    r.set_defaults(func=cmd_ready)
