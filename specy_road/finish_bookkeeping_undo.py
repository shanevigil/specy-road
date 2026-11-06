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

Before its first write (M21.28), finish runs :func:`bookkeeping_guard`: it
runs ``validate`` and refuses an invalid configuration with nothing changed,
then :func:`snapshot_pre_commit` records the worktree
state and index entries of every path finish may write up to its bookkeeping
commit (:func:`pre_commit_paths`), and :func:`restore_pre_commit` puts them
back, never from HEAD, so a user's staged and unstaged edits survive.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

from specy_road.bundled_scripts.roadmap_chunk_utils import build_node_chunk_map
from specy_road.finish_work_artifacts import cleanup_paths
from specy_road.generated_files import GENERATED_COMMITTED
from specy_road.git_subprocess import git_code, git_ok
from specy_road.git_workflow_config import WORKER_LOGS_REL
from specy_road.registry_yaml import REGISTRY_REL


def one_line(text: str) -> str:
    """``text`` on one line: its non-blank lines, trimmed, joined with `` / ``."""
    return " / ".join(line.strip() for line in text.splitlines() if line.strip())


@dataclass
class BookkeepingSnapshot:
    """The branch tip before the bookkeeping commit, and each path's content.

    An entry is ``("link", target)`` for a symlink, ``("file", bytes)`` for a
    file, and ``("absent", b"")`` for a cleanup path that did not exist.
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
    rels = _cleanup_and_log_paths(root, node_id, sess_path)
    entries: dict[str, tuple[str, str | bytes]] = {}
    for rel in rels:
        state = _path_state(root / rel)
        if state is not None:
            entries[rel] = state
    return BookkeepingSnapshot(branch=branch, pre_sha=sha, entries=entries)


def _cleanup_and_log_paths(root: Path, node_id: str, sess_path: Path | None) -> list[str]:
    """What cleanup deletes or moves, plus this leaf's worker logs (staged, and deleted again by a reset)."""
    rels = cleanup_paths(root, node_id, sess_path)
    logs = root / WORKER_LOGS_REL / node_id
    if logs.is_dir():
        rels.extend(p.relative_to(root).as_posix() for p in sorted(logs.rglob("*")))
    return rels


def merge_undo_snapshot(repo: Path, branch: str, ctx: dict) -> BookkeepingSnapshot | None:
    """The snapshot finish takes in merge mode (not a milestone rollup); ``None`` otherwise.

    ``ctx`` is finish's resolved context (``on_mode``, ``rollup``, ``node_id``,
    ``sess_path``). auto and pr keep their bookkeeping commit: the PR needs it.
    """
    if ctx["on_mode"] != "merge" or ctx["rollup"]:
        return None
    return snapshot_bookkeeping(repo, branch=branch, node_id=ctx["node_id"], sess_path=ctx["sess_path"])


def _path_state(path: Path) -> tuple[str, str | bytes] | None:
    """``path`` as a snapshot entry, never following a link; ``None`` for a directory or other kind."""
    if path.is_symlink():
        return ("link", os.readlink(path))
    if not os.path.lexists(path):
        return ("absent", b"")
    if path.is_file():
        return ("file", path.read_bytes())
    return None


def _restore(root: Path, rel: str, entry: tuple[str, str | bytes]) -> None:
    """Make ``rel`` exactly ``entry``: unchanged when it already is, else remove what is there and recreate it.

    One rule for every kind: a link with another target, a file with other
    bytes, the wrong kind, or something that was not there before is unlinked
    (never followed) and the snapshot state written. A directory in the way
    raises, so nothing is removed recursively.
    """
    path = root / rel
    if _path_state(path) == entry:
        return
    if os.path.lexists(path):
        if not path.is_symlink() and path.is_dir():
            raise IsADirectoryError(f"{rel} is a directory")
        path.unlink()
    kind, value = entry
    if kind != "absent":
        path.parent.mkdir(parents=True, exist_ok=True)
    if kind == "link":
        os.symlink(value, path)
    elif kind == "file":
        path.write_bytes(value)


def _differs_from(root: Path, sha: str, rel: str, entry: tuple[str, str | bytes]) -> bool:
    """Whether ``entry`` is not what ``sha`` holds at ``rel`` (a link compares by its target)."""
    kind, value = entry
    if kind == "absent":
        return False
    data = value.encode() if isinstance(value, str) else value
    have = subprocess.run(["git", "hash-object", "--stdin"], cwd=root, input=data,
                          capture_output=True, check=False).stdout.decode().strip()
    return have != git_ok(["rev-parse", f"{sha}:./{rel}"], root)[1]


def _save_copy(node: str, rel: str, entry: tuple[str, str | bytes]) -> str:
    """Keep bytes that could not go back in place; return where, or why not."""
    kind, value = entry
    if kind == "link":
        return f"a symlink to {value}"
    if kind == "absent":
        return "absent before finish"
    try:
        dst = Path(tempfile.mkdtemp(prefix=f"specy-road-undo-{node}-")) / Path(rel).name
        dst.write_bytes(value)
    except OSError as e:
        return f"lost ({e})"
    return f"saved at {dst}"


def undo_bookkeeping(repo: Path, snap: BookkeepingSnapshot) -> UndoOutcome:
    """Reset ``snap.branch`` to ``pre_sha``, then put every captured path back as it was before finish.

    After a successful reset each path gets exactly its captured state, tracked
    or not (a locally modified tracked document gets its modified bytes, not
    the committed ones). When the checkout or reset failed, writing a tracked
    path would block the reset the report names, so only untracked paths are
    written and a tracked one whose bytes differ from ``pre_sha`` is saved.
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
    node = snap.branch.rsplit("/", 1)[-1]
    for rel, entry in snap.entries.items():
        if out.git_error is not None and git_ok(["cat-file", "-e", f"{snap.pre_sha}:./{rel}"], root)[0]:
            if _differs_from(root, snap.pre_sha, rel, entry):
                out.unrestored[rel] = f"tracked, so it waits for the reset; {_save_copy(node, rel, entry)}"
            continue
        try:
            _restore(root, rel, entry)
        except OSError as e:
            out.unrestored[rel] = f"{e}; {_save_copy(node, rel, entry)}"
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
    restored = (f"not restored: {one_line(lost)}" if out.unrestored else
                "its untracked work files are back; tracked ones come back with the reset")
    then = ", put each saved file named above back at its path," if out.unrestored else ","
    return (f"error: could not undo the bookkeeping commit: {one_line(out.git_error)} "
            f"(the commit is still on {snap.branch}; {restored})",
            f"run `{first}`{then} then `{again}` on this branch.")


@dataclass
class PreCommitSnapshot:
    """Each path's worktree state (as :func:`_path_state`) and its ``git ls-files -s`` index records."""

    prefix: str   # the repo root relative to the git top, "" or ending in "/"
    head: str     # HEAD when the snapshot was taken; once it moves, the commit happened
    files: dict[str, tuple[str, str | bytes]] = field(default_factory=dict)
    index: dict[str, list[str]] = field(default_factory=dict)


def pre_commit_paths(repo: Path, node_id: str, sess_path: Path | None) -> list[str]:
    """Every path finish may create, overwrite, move or remove before its bookkeeping commit.

    Every roadmap chunk (the leaf's and any rolled-up ancestor's), the registry,
    the generated files, the PR-body snapshot, and the cleanup and worker-log paths.
    """
    root = repo.resolve()
    chunks = sorted({p.relative_to(root).as_posix() for p in build_node_chunk_map(root).values()})
    rels = [*chunks, REGISTRY_REL.as_posix(), *GENERATED_COMMITTED, f"work/pr-body-{node_id}.md",
            *_cleanup_and_log_paths(root, node_id, sess_path)]
    return list(dict.fromkeys(rels))


def snapshot_pre_commit(repo: Path, rels: list[str]) -> PreCommitSnapshot:
    """Record ``rels``' worktree bytes (or absence) and index entries; a directory is skipped."""
    root = repo.resolve()
    snap = PreCommitSnapshot(prefix=git_ok(["rev-parse", "--show-prefix"], root)[1],
                             head=git_ok(["rev-parse", "HEAD"], root)[1])
    for rel in rels:
        state = _path_state(root / rel)
        if state is not None:
            snap.files[rel] = state
            snap.index[rel] = []
    if snap.files:
        out = subprocess.run(["git", "--literal-pathspecs", "ls-files", "-s", "-z", "--full-name", "--", *snap.files],
                             cwd=root, capture_output=True, text=True, check=True).stdout
        for record in filter(None, out.split("\0")):
            rel = record.split("\t", 1)[1].removeprefix(snap.prefix)
            if rel in snap.index:
                snap.index[rel].append(record)
    return snap


def restore_pre_commit(repo: Path, snap: PreCommitSnapshot) -> dict[str, str]:
    """Put every snapshotted path's index entries and bytes back; return ``{path: why}`` for each that failed."""
    root = repo.resolve()
    failed: dict[str, str] = {}
    records = [f"0 {'0' * 40}\t{snap.prefix}{rel}" for rel in snap.files]
    records += [r for rels in snap.index.values() for r in rels]
    try:
        res = subprocess.run(["git", "update-index", "-z", "--index-info"], cwd=root, check=False,
                             input="".join(f"{r}\0" for r in records), capture_output=True, text=True)
        if res.returncode != 0:
            failed["the index"] = one_line(res.stderr or res.stdout) or f"git update-index exited {res.returncode}"
    except (OSError, subprocess.SubprocessError) as e:
        failed["the index"] = str(e)
    for rel, entry in snap.files.items():
        try:
            _restore(root, rel, entry)
        except OSError as e:
            failed[rel] = str(e)
    return failed


def preflight_validate_or_exit(repo: Path) -> None:
    """Run ``specy-road validate`` (output captured); on a refusal print it and exit 1 with nothing changed."""
    cmd = [sys.executable, "-m", "specy_road.cli", "validate", "--repo-root", str(repo)]
    try:
        r = subprocess.run(cmd, cwd=repo, capture_output=True, text=True, check=False)
    except (OSError, subprocess.SubprocessError) as e:
        print(f"error: could not run specy-road validate: {e}", file=sys.stderr)
    else:
        if r.returncode == 0:
            return
        sys.stdout.write(r.stdout)
        sys.stderr.write(r.stderr)
    print("finish-this-task: nothing was changed", file=sys.stderr)
    raise SystemExit(1)


def _failed_step(e: BaseException) -> str:
    """The failing command as the dev would type it, or the error with its path."""
    if not isinstance(e, subprocess.CalledProcessError):
        return f"{type(e).__name__}: {e}"
    argv = [str(a) for a in e.cmd] if isinstance(e.cmd, (list, tuple)) else [str(e.cmd)]
    if argv[1:3] == ["-m", "specy_road.cli"]:
        argv = ["specy-road", *argv[3:]]
    return f"`{' '.join(argv)}` exited {e.returncode}"


@contextmanager
def bookkeeping_guard(repo: Path, node_id: str, sess_path: Path | None) -> Iterator[None]:
    """Validate, snapshot :func:`pre_commit_paths`, and restore them when the body fails before the commit.

    An ``OSError`` or ``subprocess.SubprocessError`` (a refused validate, export
    or digest, a write, cleanup, ``git add`` or ``git commit``) while HEAD is
    still the snapshot's puts every path back and exits 1. Once HEAD moved the
    bookkeeping commit exists, so the error propagates as before.
    """
    preflight_validate_or_exit(repo)
    snap = snapshot_pre_commit(repo, pre_commit_paths(repo, node_id, sess_path))
    try:
        yield
    except (OSError, subprocess.SubprocessError) as e:
        if git_ok(["rev-parse", "HEAD"], repo.resolve())[1] != snap.head:
            raise
        print(f"error: finish-this-task: {_failed_step(e)}", file=sys.stderr)
        failed = restore_pre_commit(repo, snap)
        for rel, why in failed.items():
            print(f"error: could not restore {rel}: {why}", file=sys.stderr)
        if not failed:
            print("[ok] put back every file finish had changed", file=sys.stderr)
        print("nothing was committed; fix it and run finish-this-task again", file=sys.stderr)
        raise SystemExit(1) from None
