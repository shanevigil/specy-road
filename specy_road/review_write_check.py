"""The post-run write check of a reviewer run (M8.3), split from :mod:`specy_road.review_record_write` for the file
limit; callers reach these names through that module, whose docstring describes the outcomes.

:func:`snapshot` records, before and after the run, every file of the checkout the reviewer ran in, of its Git
directories (:func:`_walk_git`) and of the leaf's hand-off directory, each as ``(mode, size, mtime, content
digest)``, plus every ref and the Git index's entries; :func:`written` names what changed, but the run's own
:func:`runtime_files`.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from specy_road.git_subprocess import git_stdout, git_text
from specy_road.review_files import HISTORY_DIRNAME, REVIEW_PREFIX

OUTPUT_SCHEMA_NAME = "review-output.schema.json"
OUTPUT_PREFIX = "OUTPUT-"
LOCK_NAME = ".review-run.lock"


def runtime_files(reviews: Path, model: str) -> frozenset[str]:
    """The files a reviewer run may change: its notes and what the adapter writes during the run (the run
    record ``review_delegate.RUN_PREFIX`` names and its temporary copy, the raw log, Codex's ``-o`` file, the
    output schema and :data:`LOCK_NAME`). Prompts and packets are written before the run starts."""
    names = (f"notes-{model}.md", f"RUN-{model}.json", f"RUN-{model}.json.tmp", f"RUN-{model}.log",
             f"{OUTPUT_PREFIX}{model}.json", OUTPUT_SCHEMA_NAME, LOCK_NAME)
    return frozenset(str(reviews / n) for n in names)


def _own_records(reviews: Path, model: str) -> list[Path]:
    """This model's live record, in any case, and its ``history/`` copies."""
    live = [p for p in reviews.iterdir() if p.name.lower() == f"{REVIEW_PREFIX}{model}.md".lower()] \
        if reviews.is_dir() else []
    hist = reviews / HISTORY_DIRNAME
    return live + (sorted(hist.glob(f"*-{model}.md")) if hist.is_dir() else [])


def _content(path: str, is_link: bool) -> str:
    """SHA-256 of the file's bytes (a symlink's target text): a same-length rewrite with its mtime put back
    still differs. ``unreadable`` when it cannot be read (removed mid-walk, no permission)."""
    try:
        if is_link:
            return hashlib.sha256(os.readlink(path).encode()).hexdigest()
        with open(path, "rb") as f:
            return hashlib.file_digest(f, "sha256").hexdigest()
    except OSError:
        return "unreadable"


def _walk(base: Path, state: dict[str, Any], skip: frozenset[str] = frozenset()) -> None:
    """``(mode, size, mtime, content digest)`` of every file under ``base`` (a ``chmod`` alone is a write), ignored
    ones included; ``.git`` and nested
    checkouts (a directory holding ``.git``) are other repositories' and are skipped (the Git directories are
    walked on their own: :func:`_walk_git`), as is every path in ``skip``."""
    stack = [str(base)]
    while stack:
        try:
            entries = list(os.scandir(stack.pop()))
        except OSError:   # unreadable, or removed while walking
            continue
        for e in entries:
            try:
                if e.path in skip or e.name == ".git" or (e.is_dir(follow_symlinks=False)
                                                          and os.path.lexists(os.path.join(e.path, ".git"))):
                    continue
                if e.is_dir(follow_symlinks=False):
                    stack.append(e.path)
                    continue
                st = e.stat(follow_symlinks=False)
            except OSError:
                continue
            state[e.path] = (st.st_mode, st.st_size, st.st_mtime_ns, _content(e.path, e.is_symlink()))


def _walk_git(top: Path, state: dict[str, Any]) -> None:
    """The checkout's Git metadata: every file of its common Git directory (hooks, config, info, objects, refs,
    logs) and of its own worktree Git directory, and its ``.git`` pointer file in a linked worktree. Skipped: the
    other linked worktrees' directories under ``<common>/worktrees`` (other checkouts), and raw index bytes (this
    checkout's, which a read-only ``git status`` rewrites and :func:`snapshot` compares by its entries instead, and
    the main checkout's when this one is linked)."""
    def resolved(*args: str) -> Path | None:
        out = git_text(["rev-parse", "--path-format=absolute", *args], top)
        return Path(out).resolve() if out else None
    common, own, index = resolved("--git-common-dir"), resolved("--git-dir"), resolved("--git-path", "index")
    other = (common / "index", common / "worktrees") if common else ()   # the main checkout's index; other worktrees
    skip = frozenset(str(p) for p in (index, *other) if p)
    for d in dict.fromkeys(d for d in (common, own) if d):   # one directory when the checkout is the main one
        _walk(d, state, skip)
    pointer = top / ".git"
    if pointer.is_file():
        st = pointer.stat()
        state[str(pointer)] = (st.st_mode, st.st_size, st.st_mtime_ns, _content(str(pointer), False))


@dataclass
class Snapshot:
    """What a reviewer run could write; ``records`` keeps this model's own record bytes, ``exempt``
    :func:`runtime_files`, ``top`` the checkout walked."""
    state: dict[str, Any]
    records: dict[Path, bytes] = field(default_factory=dict)
    exempt: frozenset[str] = frozenset()
    top: Path = Path()

    def restore(self, reviews: Path, model: str) -> None:
        """Put this model's record files back as they were: a record the run filed itself never counts."""
        for p in _own_records(reviews, model):
            if p not in self.records:
                p.unlink(missing_ok=True)
        for p, data in self.records.items():
            p.write_bytes(data)


def snapshot(cwd: Path, reviews: Path, model: str) -> Snapshot:
    """Every file of the checkout at ``cwd``, of its Git directories (:func:`_walk_git`) and of the hand-off
    directory ``reviews``, plus every ref and the Git index. The index is compared by what it records (``ls-files --stage -v``:
    each entry's mode, blob, stage and assume-unchanged / skip-worktree flag), not its bytes, which a read-only
    ``git status`` rewrites when it refreshes the stat cache."""
    top = Path(git_text(["rev-parse", "--show-toplevel"], cwd) or cwd).resolve()
    reviews = reviews.resolve()
    index = git_stdout(["ls-files", "--stage", "-v", "-z"], top) or ""
    state: dict[str, Any] = {"git refs": (git_text(["rev-parse", "HEAD"], top) or "") + "\n"
                             + (git_text(["for-each-ref", "--format=%(refname) %(objectname)"], top) or ""),
                             "git index": hashlib.sha256(index.encode()).hexdigest()}
    _walk(top, state)
    _walk_git(top, state)
    if top not in reviews.parents:   # a reviewer in a linked worktree: the hand-off directory is the main checkout's
        _walk(reviews, state)
    return Snapshot(state, {p: p.read_bytes() for p in _own_records(reviews, model)}, runtime_files(reviews, model), top)


def written(before: Snapshot, after: Snapshot) -> list[str]:
    """Each path (or ``git refs``, ``git index``) added, removed or changed between the two snapshots, but the run's own
    :func:`runtime_files`; shown relative to the checkout when it is inside it."""
    keys = set(before.state) | set(after.state)
    changed = (k for k in keys if k not in before.exempt and before.state.get(k) != after.state.get(k))
    top = f"{before.top}{os.sep}"
    return sorted(k.removeprefix(top) for k in changed)
