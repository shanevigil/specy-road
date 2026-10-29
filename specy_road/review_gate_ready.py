"""READY-adjacent gate helpers: the interactive human approval and the trial merge."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from specy_road.bundled_scripts.brief_acceptance import acceptance_ids
from specy_road.finish_implementation_check import base_ref
from specy_road.git_subprocess import commits_behind, merge_conflicts
from specy_road.git_workflow_config import resolve_integration_defaults
from specy_road.orchestration_config import effective_config, roster_entry
from specy_road.review_files import HUMAN, render_front_matter, review_path
from specy_road.review_policy_ref import policy_source
from specy_road.review_signing import NOTES_KEY, SigningError, notes_digest, sign, verify
from specy_road.runtime_paths import project_prefix, rebase_to_project


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
