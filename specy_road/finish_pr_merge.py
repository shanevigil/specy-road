"""Under ``on_complete: pr``, merge the integration tip into the finish commit before anything is pushed.

The finish commit removes this leaf's registry row, while the integration
branch still holds it and, in a busy lane, has gained other claims since
pickup. git then conflicts on ``roadmap/registry.yaml`` and the two generated
files, and the PR opens conflicted. Those three paths are never ambiguous (see
:mod:`specy_road.finish_land_deterministic`): the integration branch's registry
minus this leaf's row, with ``roadmap.md`` and ``roadmap-context.md`` rendered
again. A conflict on any other path is work for a person, so it is named and
nothing is pushed.

The direction is the reverse of merge mode's landing: here ``HEAD`` is the
feature branch and the integration tip is the other side, so the registry is
read from that ref rather than from ``HEAD``.
"""

from __future__ import annotations

import sys
from pathlib import Path

from specy_road.finish_implementation_check import base_ref
from specy_road.finish_land_deterministic import (
    DETERMINISTIC_PATHS,
    DeterministicResolveError,
    _regenerate_generated_files,
    codename_from_branch,
    merge_in_progress,
    reconcile_or_rollback,
    unmerged_paths,
)
from specy_road.git_subprocess import git_code, git_ok, git_text
from specy_road.registry_remote_overlay_merge import read_registry_at_ref
from specy_road.registry_yaml import REGISTRY_REL, registry_path, write_registry
from specy_road.review_gate_ready import trial_merge
from specy_road.runtime_paths import project_prefix

#: Reading one blob out of a ref; short, because a hung git must not hang a finish.
_REF_READ_TIMEOUT = 4.0


def _registry_from(repo: Path, ref: str, codename: str | None) -> str:
    """Write ``ref``'s registry minus ``codename``'s row; return its project-relative path.

    With no row to drop, ``ref``'s blob is checked out byte for byte, as merge
    mode does, so its comments survive; with no registry on ``ref``, this
    branch's own copy stays.
    """
    rel = REGISTRY_REL.as_posix()
    doc = read_registry_at_ref(repo, ref, _REF_READ_TIMEOUT)
    entries = [e for e in ((doc or {}).get("entries") or []) if isinstance(e, dict)]
    if doc is not None and codename is not None and any(e.get("codename") == codename for e in entries):
        doc["entries"] = [e for e in entries if e.get("codename") != codename]
        write_registry(registry_path(repo), doc)
    else:
        git_code(["checkout", ref if doc is not None else "HEAD", "--", rel], repo)
    return rel


def _abort(repo: Path, detail: str) -> str:
    git_code(["merge", "--abort"], repo)
    return detail


def merge_integration_resolving_bookkeeping(repo: Path, *, ref: str, ib: str, branch: str) -> str | None:
    """Merge ``ref`` into the checked-out ``branch``, resolving the three bookkeeping paths.

    ``None`` once the merge commit exists; otherwise why it could not, with the
    merge aborted and ``branch`` where it was.
    """
    codename = codename_from_branch(branch)
    pre_sha = git_text(["rev-parse", "HEAD"], repo)
    if not pre_sha:
        return f"could not read {branch} HEAD before merging"
    code, out = git_code(["merge", "--no-commit", "--no-ff", ref], repo)
    prefix = project_prefix(repo)   # git names conflicted paths from the repository root
    stray = [p for p in unmerged_paths(repo) if p not in [prefix + d for d in DETERMINISTIC_PATHS]]
    if stray:
        return _abort(repo, f"the merge conflicts on {', '.join(stray)}")
    if not merge_in_progress(repo):
        return _abort(repo, out) if code != 0 else None
    try:
        staged = [_registry_from(repo, ref, codename), *_regenerate_generated_files(repo)]
    except DeterministicResolveError as exc:
        return _abort(repo, str(exc))
    code, out = git_code(["add", "--", *staged], repo)
    if code != 0:
        return _abort(repo, f"staging {', '.join(staged)} failed: {out}")
    minus = f" minus rm-{codename}" if codename else ""
    body = (f"roadmap/registry.yaml resolved to {ib}{minus}; roadmap.md and roadmap-context.md "
            "regenerated from the merged graph, so the PR merges without a bookkeeping conflict.")
    code, out = git_code(["commit", "-m", f"Merge {ib} into {branch}", "-m", body], repo)
    if code != 0:
        return _abort(repo, f"commit: {out}")
    return reconcile_or_rollback(repo, pre_sha)


def pr_merge_integration_or_exit(repo: Path, *, branch: str, ib: str, remote: str) -> None:
    """Exit 1, having pushed nothing, when the PR from ``branch`` would conflict on more than bookkeeping.

    Fetches ``ib`` first: the PR merges into the remote tip, which may have
    moved since pickup. A failed fetch keeps the last tip seen, and when git
    cannot answer at all there is nothing to say, as in the review packet.
    """
    git_ok(["fetch", "-q", remote, ib], repo)
    ref = base_ref(repo, remote, ib)
    tm = trial_merge(repo, "HEAD", ref)
    if ref is None or tm is None or not tm.conflicts:
        return
    other = [p for p in tm.conflicts if p not in DETERMINISTIC_PATHS]
    problem = (f"merging {ref} into {branch} conflicts on {', '.join(other)}" if other
               else merge_integration_resolving_bookkeeping(repo, ref=ref, ib=ib, branch=branch))
    if problem is None:
        print(f"[ok] merged {ref} into {branch}: resolved {', '.join(tm.conflicts)} "
              f"to {ib}'s registry minus this leaf's row, generated files rendered again")
        return
    print(f"\nerror: the PR into {ib} would conflict: {problem}. Nothing was pushed.", file=sys.stderr)
    print(f"  The bookkeeping commit is on {branch}. Run `git merge {ref}`, resolve, commit, have the "
          f"result reviewed, then `git push -u {remote} {branch}` and open the PR.", file=sys.stderr)
    raise SystemExit(1)
