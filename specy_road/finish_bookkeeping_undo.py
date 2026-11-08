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

Before its first write (M21.28), finish runs :func:`bookkeeping_guard`. It
refuses a write destination that is not a regular file or absent
(:func:`refuse_irregular_destinations_or_exit`), runs ``validate`` and refuses
an invalid configuration with nothing changed, then :func:`snapshot_pre_commit`
records the worktree state of every path finish may write up to its
bookkeeping commit (:func:`pre_commit_paths`) and the whole index file, and
:func:`restore_pre_commit` puts both back, never from HEAD, so a user's staged
and unstaged edits survive.

Every restore writes a temporary file beside the path and renames it over the
path, with the regular file's recorded mode bits, so a failed write leaves
the previous bytes in place and names the temporary file (M22.20). One rule
for the index: when its staged entries changed since the snapshot (finish's
own staging, or a hook's or another process's), the index as it is now is
saved beside it and named before the snapshot's goes back, so no staging is
dropped unnamed; when that copy cannot be written the index stays as it is.
"""

from __future__ import annotations

import os
import secrets
import stat
import subprocess
import sys
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

from specy_road import safe_write
from specy_road.bundled_scripts.roadmap_chunk_utils import manifest_includes
from specy_road.finish_work_artifacts import archived_implementation_summary_rel, cleanup_paths
from specy_road.generated_files import GENERATED_COMMITTED
from specy_road.git_subprocess import git_code, git_ok
from specy_road.git_workflow_config import WORKER_LOGS_REL
from specy_road.registry_yaml import REGISTRY_REL
from specy_road.review_files import reviews_root


def one_line(text: str) -> str:
    """``text`` on one line: its non-blank lines, trimmed, joined with `` / ``."""
    return " / ".join(line.strip() for line in text.splitlines() if line.strip())


@dataclass
class BookkeepingSnapshot:
    """The branch tip before the bookkeeping commit, and each path's content.

    An entry is ``("link", target)`` for a symlink, ``("file", bytes)`` for a
    file, and ``("absent", b"")`` for a cleanup path that did not exist;
    ``modes`` holds each file's permission bits.
    """

    branch: str
    pre_sha: str
    entries: dict[str, tuple[str, str | bytes]] = field(default_factory=dict)
    modes: dict[str, int] = field(default_factory=dict)


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
    snap = BookkeepingSnapshot(branch=branch, pre_sha=sha)
    for rel in rels:
        _record(root, rel, snap.entries, snap.modes)
    return snap


def _record(root: Path, rel: str, entries: dict, modes: dict[str, int]) -> None:
    """Put ``rel``'s :func:`_path_state` in ``entries`` and a regular file's permission bits in ``modes``."""
    state = _path_state(root / rel)
    if state is None:
        return
    entries[rel] = state
    if state[0] == "file":
        modes[rel] = stat.S_IMODE((root / rel).lstat().st_mode)


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


def _restore(root: Path, rel: str, entry: tuple[str, str | bytes], mode: int | None = None) -> None:
    """Make ``rel`` exactly ``entry`` (a file with ``mode`` when given): unchanged when it already is.

    One rule for every kind: a link with another target, a file with other
    bytes or mode, or the wrong kind is replaced (never followed) by a
    temporary link or file written beside it and renamed over it, so what
    was there stays until the snapshot state is complete on disk; a failure
    names the temporary file it kept. A path absent before is unlinked. A
    directory in the way raises, so nothing is removed recursively.
    """
    path = root / rel
    kind, value = entry
    if _path_state(path) == entry and (kind != "file" or mode is None or stat.S_IMODE(path.lstat().st_mode) == mode):
        return
    if os.path.lexists(path) and not path.is_symlink() and path.is_dir():
        raise IsADirectoryError(f"{rel} is a directory")
    if kind == "absent":
        path.unlink()
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{secrets.token_hex(4)}.specy-road-restore")
    try:
        if kind == "link":
            os.symlink(value, tmp)
        else:
            with os.fdopen(os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb") as f:
                f.write(value)
            os.chmod(tmp, 0o644 if mode is None else mode)
        os.replace(tmp, path)
    except OSError as e:
        if os.path.lexists(tmp):
            raise OSError(f"{e}; the bytes from before finish are kept at {tmp}") from e
        raise


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
            _restore(root, rel, entry, snap.modes.get(rel))
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
    """Each path's worktree state (as :func:`_path_state`) and file mode, and the index file's bytes (``None``: absent).

    The whole index, not per-path entries: ``git add <dir>`` reaches every entry
    under a directory, including ones absent from disk, so no path list bounds it.
    ``index_entries`` is the staged entries (``git ls-files -s``, from the top),
    which :func:`restore_pre_commit` compares (M22.20).
    """

    head: str     # HEAD when the snapshot was taken; once it moves, the commit happened
    index_path: Path
    index_bytes: bytes | None
    files: dict[str, tuple[str, str | bytes]] = field(default_factory=dict)
    modes: dict[str, int] = field(default_factory=dict)
    index_entries: frozenset[str] | None = None


def pre_commit_paths(repo: Path, node_id: str, sess_path: Path | None) -> list[str]:
    """Every path finish may create, overwrite, move or remove before its bookkeeping commit.

    Its :func:`write_destinations`, then the cleanup and worker-log paths. The
    reviews-directory copy is the main checkout's, so from a linked worktree its
    path is relative with ``../`` and outside this worktree's index.
    """
    root = repo.resolve()
    dests = [Path(os.path.relpath(base / rel, root)).as_posix() for base, rel in write_destinations(root, node_id)]
    return list(dict.fromkeys([*dests, *_cleanup_and_log_paths(root, node_id, sess_path)]))


def snapshot_pre_commit(repo: Path, rels: list[str]) -> PreCommitSnapshot:
    """Record ``rels``' worktree bytes and modes (or absence; a directory is skipped) and the index."""
    root = repo.resolve()
    index_path = root / git_ok(["rev-parse", "--git-path", "index"], root)[1]
    snap = PreCommitSnapshot(head=git_ok(["rev-parse", "HEAD"], root)[1], index_path=index_path,
                             index_bytes=index_path.read_bytes() if index_path.is_file() else None,
                             index_entries=_index_entries(root))
    for rel in rels:
        _record(root, rel, snap.files, snap.modes)
    return snap


def _index_entries(root: Path) -> frozenset[str] | None:
    """Every staged entry (mode, object id, stage and top-relative path); ``None`` when git cannot list them.

    Entries, not the file's bytes: git rewrites the index when it only refreshes stat data (``git status``).
    """
    r = subprocess.run(["git", "ls-files", "-s", "-z", "--full-name", "--", ":/"], cwd=root, capture_output=True,
                       check=False)
    return frozenset(r.stdout.decode("utf-8", "surrogateescape").split("\0")) - {""} if r.returncode == 0 else None


def _save_changed_index(root: Path, snap: PreCommitSnapshot) -> None:
    """When the staged entries changed since the snapshot, copy the index beside it and say where and what changed.

    An index git cannot list counts as changed. A copy that cannot be written raises, so the caller keeps the index.
    """
    now = _index_entries(root)
    if now is not None and now == snap.index_entries:
        return
    changed = ("unlistable" if now is None or snap.index_entries is None
               else ", ".join(sorted({e.split("\t", 1)[-1] for e in now ^ snap.index_entries})))
    try:
        fd, name = tempfile.mkstemp(prefix=f"{snap.index_path.name}.left-by-finish.", dir=snap.index_path.parent)
        with os.fdopen(fd, "wb") as f:
            f.write(snap.index_path.read_bytes() if snap.index_path.is_file() else b"")
    except OSError as e:
        raise OSError(f"staging changed since finish started ({changed}) and the index could not be saved "
                      f"({e}), so it stays as it is at {snap.index_path}") from e
    print(f"note: put the index from before finish back at {snap.index_path}; the one it replaced (staging changed "
          f"since finish started: {changed}) is saved at {name}: move it back over the index to keep that staging",
          file=sys.stderr)


def restore_pre_commit(repo: Path, snap: PreCommitSnapshot) -> dict[str, str]:
    """Put the index file and every snapshotted path's bytes back; return ``{path: why}`` for each that failed.

    The index it replaces is saved and named first when its staged entries changed (:func:`_save_changed_index`).
    """
    root = repo.resolve()
    failed: dict[str, str] = {}
    try:
        _save_changed_index(root, snap)
        if snap.index_bytes is None:
            snap.index_path.unlink(missing_ok=True)
        else:   # written beside it and renamed, so git never reads half an index
            tmp = snap.index_path.with_name(snap.index_path.name + ".specy-road-restore")
            tmp.write_bytes(snap.index_bytes)
            os.replace(tmp, snap.index_path)
    except OSError as e:
        failed["the index"] = str(e)
    for rel, entry in snap.files.items():
        try:
            _restore(root, rel, entry, snap.modes.get(rel))
        except OSError as e:
            failed[rel] = str(e)
    return failed


def write_destinations(repo: Path, node_id: str) -> list[tuple[Path, str]]:
    """``(base, relative path)`` for every path finish writes, moves or copies into before its commit.

    Under the repo root: every manifest chunk (leaf and rolled-up ancestors), the registry, ``roadmap.md``,
    ``roadmap-context.md``, the PR-body file and a tracked summary's ``work/done/`` archive. Under the
    main checkout's project root (this one, or the main one from a linked worktree): an untracked
    summary's copy, ``work/reviews/<node>/<summary>``, so ``work`` and ``work/reviews`` are walked too.
    """
    root = repo.resolve()
    chunks = [Path("roadmap", inc).as_posix() for inc in manifest_includes(root) if isinstance(inc, str)]
    rels = [*chunks, REGISTRY_REL.as_posix(), *GENERATED_COMMITTED, f"work/pr-body-{node_id}.md",
            archived_implementation_summary_rel(node_id)]
    summary = Path(archived_implementation_summary_rel(node_id)).name
    return [*((root, rel) for rel in rels if not os.path.normpath(rel).startswith("..")),
            (reviews_root(root).parents[1], f"work/reviews/{node_id}/{summary}")]


def irregular_destination(base: Path, rel: str) -> str | None:
    """``"<path> is <kind>, not <expected>"`` when ``rel`` under ``base`` cannot be written as a plain file.

    The :mod:`specy_road.safe_write` walk from ``base`` with ``lstat``: each
    component absent (finish creates it) or a real directory on the way and a
    regular file at the end. A symlink (to anywhere), a regular file where a
    directory belongs, a directory, FIFO, socket or device at the end, and a
    component ``lstat`` cannot read (its error is named) all refuse.
    """
    return safe_write.refused(base, rel)


def refuse_irregular_destinations_or_exit(repo: Path, node_id: str) -> None:
    """Exit 1 before anything is written when a :func:`write_destinations` path is not absent or a regular file.

    With that precondition the snapshot only ever holds a regular file or an
    absence for each destination, and no write can land behind a link.
    """
    found = [why for base, rel in write_destinations(repo, node_id) if (why := irregular_destination(base, rel))]
    if found:
        _nothing_changed([f"error: finish-this-task writes there, but {why}; fix or remove it" for why in found])


def _nothing_changed(errors: list[str]) -> None:
    """Print ``errors`` and the nothing-changed line on stderr, then exit 1: every refusal before a write."""
    for line in [*errors, "finish-this-task: nothing was changed"]:
        print(line, file=sys.stderr)
    raise SystemExit(1)


def preflight_validate_or_exit(repo: Path) -> None:
    """Run ``specy-road validate`` (output captured); on a refusal print it and exit 1 with nothing changed."""
    cmd = [sys.executable, "-m", "specy_road.cli", "validate", "--repo-root", str(repo)]
    try:
        r = subprocess.run(cmd, cwd=repo, capture_output=True, text=True, check=False)
    except (OSError, subprocess.SubprocessError) as e:
        _nothing_changed([f"error: could not run specy-road validate: {e}"])
    if r.returncode != 0:
        sys.stdout.write(r.stdout)
        _nothing_changed([r.stderr.rstrip("\n")] if r.stderr.strip() else [])


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
    """Refuse irregular destinations, validate, snapshot :func:`pre_commit_paths`, and restore them on failure.

    An ``OSError`` or ``subprocess.SubprocessError`` (a refused validate, export
    or digest, a write, cleanup, ``git add`` or ``git commit``) while HEAD is
    still the snapshot's puts every path back and exits 1. Once HEAD moved the
    bookkeeping commit exists, so the error propagates as before.
    """
    refuse_irregular_destinations_or_exit(repo, node_id)
    preflight_validate_or_exit(repo)
    try:
        snap = snapshot_pre_commit(repo, pre_commit_paths(repo, node_id, sess_path))
    except (OSError, subprocess.SubprocessError, RuntimeError) as e:   # RuntimeError: a symlink loop (Python < 3.13)
        _nothing_changed([f"error: finish-this-task could not record the tree before writing: {_failed_step(e)}"])
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
