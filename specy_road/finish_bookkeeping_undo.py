"""Undo finish-this-task's bookkeeping commit after a failed merge landing (M15.40).

In merge mode the bookkeeping commit ("complete, deregister") is made before
the landing. When the landing then fails, that commit would leave the branch
claiming nothing while nothing landed, which other tools read as an orphan
claim. :func:`snapshot_bookkeeping` records the branch tip and every path the
bookkeeping deletes or moves (:func:`~specy_road.finish_work_artifacts.cleanup_paths`)
or adds and a reset would delete again (this leaf's worker logs);
:func:`undo_bookkeeping` puts both back (``git reset --keep``, then rewrites the
paths ``pre_sha`` does not track), and :func:`undo_report` says what happened,
so a plain re-run of finish starts over.
"""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from specy_road.finish_work_artifacts import cleanup_paths
from specy_road.git_subprocess import git_code, git_ok
from specy_road.git_workflow_config import WORKER_LOGS_REL


def one_line(text: str) -> str:
    """``text`` on one line: its non-blank lines, trimmed, joined with `` / ``."""
    return " / ".join(line.strip() for line in text.splitlines() if line.strip())


@dataclass
class BookkeepingSnapshot:
    """The branch tip before the bookkeeping commit, and each path's content.

    An entry is ``("link", target)`` for a symlink, else ``("file", bytes)``.
    """

    branch: str
    pre_sha: str
    entries: dict[str, tuple[str, str | bytes]] = field(default_factory=dict)


@dataclass
class UndoOutcome:
    """What :func:`undo_bookkeeping` did; ``git_error`` means the commit is still on the branch."""

    snap: BookkeepingSnapshot
    git_error: str | None = None
    checked_out: bool = True
    unrestored: dict[str, str] = field(default_factory=dict)   # path -> saved copy or why not


def snapshot_bookkeeping(
    repo: Path, *, branch: str, node_id: str, sess_path: Path | None,
) -> BookkeepingSnapshot | None:
    """Record what :func:`undo_bookkeeping` restores; ``None`` when HEAD is unreadable."""
    ok, sha = git_ok(["rev-parse", "HEAD"], repo)
    if not ok or not sha:
        return None
    root = repo.resolve()
    rels = cleanup_paths(root, node_id, sess_path)
    logs = root / WORKER_LOGS_REL / node_id
    if logs.is_dir():
        rels.extend(p.relative_to(root).as_posix() for p in sorted(logs.rglob("*")))
    entries: dict[str, tuple[str, str | bytes]] = {}
    for rel in rels:
        path = root / rel
        if path.is_symlink():
            entries[rel] = ("link", os.readlink(path))
        elif path.is_file():
            entries[rel] = ("file", path.read_bytes())
    return BookkeepingSnapshot(branch=branch, pre_sha=sha, entries=entries)


def merge_undo_snapshot(repo: Path, branch: str, ctx: dict) -> BookkeepingSnapshot | None:
    """The snapshot finish takes in merge mode (not a milestone rollup); ``None`` otherwise.

    ``ctx`` is finish's resolved context (``on_mode``, ``rollup``, ``node_id``,
    ``sess_path``). auto and pr keep their bookkeeping commit: the PR needs it.
    """
    if ctx["on_mode"] != "merge" or ctx["rollup"]:
        return None
    return snapshot_bookkeeping(repo, branch=branch, node_id=ctx["node_id"], sess_path=ctx["sess_path"])


def _restore(root: Path, rel: str, entry: tuple[str, str | bytes]) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    kind, value = entry
    if kind == "link":
        if not os.path.lexists(path):
            os.symlink(value, path)
    else:
        path.write_bytes(value)


def _save_copy(node: str, rel: str, entry: tuple[str, str | bytes]) -> str:
    """Keep bytes that could not go back in place; return where, or why not."""
    kind, value = entry
    if kind == "link":
        return f"a symlink to {value}"
    try:
        dst = Path(tempfile.mkdtemp(prefix=f"specy-road-undo-{node}-")) / Path(rel).name
        dst.write_bytes(value)
    except OSError as e:
        return f"lost ({e})"
    return f"saved at {dst}"


def undo_bookkeeping(repo: Path, snap: BookkeepingSnapshot) -> UndoOutcome:
    """Reset ``snap.branch`` to ``pre_sha`` and rewrite the paths ``pre_sha`` does not track.

    Untracked paths are rewritten even when the checkout or reset failed, so
    their bytes are never lost; tracked ones come back with the reset.
    """
    root = repo.resolve()
    out = UndoOutcome(snap=snap)
    ok, current = git_ok(["symbolic-ref", "--short", "-q", "HEAD"], root)
    if not ok or current != snap.branch:
        code, msg = git_code(["checkout", snap.branch], root)
        if code != 0:
            out.git_error, out.checked_out = f"git checkout {snap.branch} failed: {msg}", False
    if out.git_error is None:
        code, msg = git_code(["reset", "--keep", snap.pre_sha], root)
        if code != 0:
            out.git_error = f"git reset --keep {snap.pre_sha} failed: {msg}"
    for rel, entry in snap.entries.items():
        if git_ok(["cat-file", "-e", f"{snap.pre_sha}:./{rel}"], root)[0]:
            continue
        try:
            _restore(root, rel, entry)
        except OSError as e:
            out.unrestored[rel] = f"{e}; {_save_copy(snap.branch.rsplit('/', 1)[-1], rel, entry)}"
    if out.git_error is None and not out.unrestored:
        print(f"[ok] undid the bookkeeping commit: {snap.branch} is back at {snap.pre_sha[:12]}, "
              "its registry claim and work files restored")
    return out


def undo_report(out: UndoOutcome, again: str) -> tuple[str | None, str]:
    """``(one-line error or None, what to do next)`` for :func:`merge_landing_failed`."""
    snap, sha = out.snap, out.snap.pre_sha
    lost = "; ".join(f"{rel}: {why}" for rel, why in out.unrestored.items())
    if out.git_error is None and not out.unrestored:
        return None, (f"run `{again}` again on this branch: this run undid its bookkeeping commit "
                      "(the branch, its registry claim and work files are as they were before "
                      "finish), so it runs the whole finish again.")
    if out.git_error is None:
        return (f"error: undid the bookkeeping commit ({snap.branch} is back at {sha[:12]}, its "
                f"registry claim restored) but could not restore {one_line(lost)}",
                f"put each file named above back at its path, then run `{again}` again on this branch.")
    first = f"git reset --keep {sha}" if out.checked_out else f"git checkout {snap.branch} && git reset --keep {sha}"
    restored = "its untracked work files are back" if not out.unrestored else f"not restored: {one_line(lost)}"
    return (f"error: could not undo the bookkeeping commit: {one_line(out.git_error)} "
            f"(the commit is still on {snap.branch}; {restored})",
            f"run `{first}`, then `{again}` on this branch.")
