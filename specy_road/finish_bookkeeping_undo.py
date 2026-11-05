"""Undo finish-this-task's bookkeeping commit after a failed merge landing (M15.40).

In merge mode the bookkeeping commit ("complete, deregister") is made before
the landing. When the landing then fails, that commit would leave the branch
claiming nothing while nothing landed, which other tools read as an orphan
claim. :func:`snapshot_bookkeeping` records the branch tip and the bytes of the
``work/`` files the bookkeeping removes or archives; :func:`undo_bookkeeping`
puts both back (``git reset --keep``, then rewrites the files), so a plain
re-run of finish starts over.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from specy_road.finish_work_artifacts import work_artifact_rel_paths
from specy_road.git_workflow_config import WORKER_LOGS_REL
from specy_road.git_subprocess import git_code, git_ok


@dataclass
class BookkeepingSnapshot:
    """The branch tip before the bookkeeping commit, and the work files' bytes."""

    branch: str
    pre_sha: str
    files: dict[str, bytes] = field(default_factory=dict)


def snapshot_bookkeeping(
    repo: Path, *, branch: str, node_id: str, sess_path: Path | None,
) -> BookkeepingSnapshot | None:
    """Record what :func:`undo_bookkeeping` restores; ``None`` when HEAD is unreadable.

    Taken before the bookkeeping phase touches anything: the session documents
    (``work/brief-``, ``prompt-``, ``implementation-summary-<ID>.md``), the
    on_complete sidecar and this leaf's worker logs.
    """
    ok, sha = git_ok(["rev-parse", "HEAD"], repo)
    if not ok or not sha:
        return None
    rels = list(work_artifact_rel_paths(node_id))
    if sess_path is not None:
        try:
            rels.append(sess_path.resolve().relative_to(repo.resolve()).as_posix())
        except ValueError:
            pass
    # The bookkeeping commit may add this leaf's untracked worker logs; the reset
    # would delete them again, so they are rewritten too.
    logs = repo / WORKER_LOGS_REL / node_id
    if logs.is_dir():
        rels.extend(p.relative_to(repo).as_posix() for p in sorted(logs.rglob("*")))
    files = {}
    for rel in rels:
        path = repo / rel
        if path.is_file() and not path.is_symlink():
            files[rel] = path.read_bytes()
    return BookkeepingSnapshot(branch=branch, pre_sha=sha, files=files)


def merge_undo_snapshot(repo: Path, branch: str, ctx: dict) -> BookkeepingSnapshot | None:
    """The snapshot finish takes in merge mode (not a milestone rollup); ``None`` otherwise.

    ``ctx`` is finish's resolved context (``on_mode``, ``rollup``, ``node_id``,
    ``sess_path``). auto and pr keep their bookkeeping commit: the PR needs it.
    """
    if ctx["on_mode"] != "merge" or ctx["rollup"]:
        return None
    return snapshot_bookkeeping(repo, branch=branch, node_id=ctx["node_id"], sess_path=ctx["sess_path"])


def undo_bookkeeping(repo: Path, snap: BookkeepingSnapshot) -> str | None:
    """Reset ``snap.branch`` to its pre-bookkeeping tip and rewrite the work files.

    Returns ``None`` on success, else why the undo failed.
    """
    ok, current = git_ok(["symbolic-ref", "--short", "-q", "HEAD"], repo)
    if not ok or current != snap.branch:
        code, out = git_code(["checkout", snap.branch], repo)
        if code != 0:
            return f"git checkout {snap.branch} failed: {out}"
    code, out = git_code(["reset", "--keep", snap.pre_sha], repo)
    if code != 0:
        return f"git reset --keep {snap.pre_sha} failed: {out}"
    for rel, data in snap.files.items():
        path = repo / rel
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        except OSError as e:
            return f"could not restore {rel}: {e}"
    print(f"[ok] undid the bookkeeping commit: {snap.branch} is back at {snap.pre_sha[:12]}, "
          "its registry claim and work files restored")
    return None
