"""The note on files a ``.gitignore`` update reaches: observed in a real run, estimated in a dry run.

**Real run: observed, not predicted.** Git lists, in the checkout itself, the
untracked files it shows and the tracked files it ignores (:func:`observe`),
once before the write and once after. *Now hidden* is a file shown before and
not after; *still tracked under a new rule* is a tracked file ignored after and
not before. Whatever git reads (rule order, nested and self-ignored
``.gitignore`` files, ``info/exclude``, ``core.ignorecase``, the global
excludes file) is therefore accounted for by git, not reproduced here.

**Dry run: an estimate, labelled as one.** Nothing may be written, so
:func:`estimate` copies the current top-level ``.gitignore``, the ``.gitignore``
in every ancestor directory of every candidate path (ignored ones included;
a symlinked one stays a symlink, which git does not read), and ``info/exclude``
into a throwaway ``git init`` directory, applies the update there and asks git
before and after, with the checkout's ``core.ignorecase``
and ``core.excludesFile``. Known limits: it reproduces only those inputs, so
it can differ from the real run when git reads anything else (another config
setting, an ignore file this list misses) or when files change between the dry
run and the real one; the real run reports exactly what changed.

Either way the note is advisory: any failure becomes one
``ignore check skipped: <reason>`` line (see :func:`attempt`), and the writes
it describes go ahead unchanged.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from collections.abc import Callable
from pathlib import Path, PurePosixPath
from typing import TypeVar

GITIGNORE = ".gitignore"
#: How many matching paths the note lists before it gives a count.
MATCH_LIMIT = 20
TRACKED_NOTE = "still tracked; git keeps tracking it"
HIDDEN_NOTE = "untracked; now hidden from git status"
REAL_HEADER = ".gitignore: new rules match files already in the tree (nothing was untracked):"
ESTIMATE_HEADER = ("estimated (dry run): .gitignore's new rules would match files already in the tree "
                   "(nothing is untracked); the real run reports exactly what changed:")
UNTRACK_HINT = "  to stop tracking one of the files above: git rm --cached <path>"
#: Variables that would point a git call in a scratch repository back at the checkout (set inside git hooks).
_REPO_ENV = ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR", "GIT_OBJECT_DIRECTORY")

Match = tuple[str, str, str]   # (path, rule, note)
T = TypeVar("T")


class IgnoreCheckSkipped(Exception):
    """A git call the note depends on failed; the note is skipped, never guessed."""


def attempt(fn: Callable[[], T]) -> T | str:
    """``fn()``, or the reason it failed as a string: the note never stops the command."""
    try:
        return fn()
    except (OSError, ValueError, subprocess.SubprocessError, IgnoreCheckSkipped) as e:
        return str(e) or type(e).__name__


def _git(args: list[str], cwd: Path, *, stdin: bytes | None = None, ok: tuple[int, ...] = (0,)) -> bytes:
    """Raw stdout bytes of ``git <args>``; :class:`IgnoreCheckSkipped` on any other exit."""
    env = {k: v for k, v in os.environ.items() if k not in _REPO_ENV}
    r = subprocess.run(["git", *args], cwd=cwd, input=stdin, capture_output=True, check=False, timeout=60, env=env)
    if r.returncode not in ok:
        lines = os.fsdecode(r.stderr).strip().splitlines()
        command = next(a for i, a in enumerate(args) if not a.startswith("-") and (i == 0 or args[i - 1] != "-c"))
        raise IgnoreCheckSkipped(f"git {command}: {lines[-1] if lines else f'exit {r.returncode}'}")
    return r.stdout


def _paths(raw: bytes) -> list[str]:
    """NUL-separated git output as paths (undecodable bytes kept via ``os.fsdecode``)."""
    return [os.fsdecode(p) for p in raw.split(b"\0") if p]


def _stdin(paths: list[str]) -> bytes:
    return b"".join(os.fsencode(p) + b"\0" for p in paths)


def observe(git_root: Path) -> tuple[list[str], list[str]]:
    """``(untracked files git shows, tracked files git ignores)`` in the checkout, as git reports them now."""
    shown = _paths(_git(["ls-files", "-o", "--exclude-standard", "-z"], git_root))
    tracked_ignored = _paths(_git(["ls-files", "-c", "-i", "--exclude-standard", "-z"], git_root))
    return shown, tracked_ignored


def observed(git_root: Path, before: tuple[list[str], list[str]]) -> list[Match]:
    """What the write just changed, from :func:`observe` before it and now; rules named by ``check-ignore``."""
    shown, tracked_ignored = observe(git_root)
    was_ignored, now_shown = set(before[1]), set(shown)
    newly_tracked = [p for p in tracked_ignored if p not in was_ignored]
    hidden = [p for p in before[0] if p not in now_shown]
    rules = _ignored(git_root, newly_tracked + hidden, [])
    return ([(p, rules.get(p, "?"), TRACKED_NOTE) for p in newly_tracked]
            + [(p, rules.get(p, "?"), HIDDEN_NOTE) for p in hidden])


def _ignored(cwd: Path, paths: list[str], config: list[str]) -> dict[str, str]:
    """``{path: rule}`` for each path git ignores when run in ``cwd`` (index not consulted)."""
    if not paths:
        return {}
    fields = _git([*config, "check-ignore", "--no-index", "-v", "-z", "--stdin"], cwd,
                  stdin=_stdin(paths), ok=(0, 1)).split(b"\0")
    return {os.fsdecode(path): os.fsdecode(rule) for _src, _line, rule, path in zip(*[iter(fields)] * 4)
            if not rule.startswith(b"!")}


def _ignore_config(git_root: Path) -> tuple[list[str], Path | None]:
    """The checkout's ``core.ignorecase`` and ``core.excludesFile`` as ``-c`` flags, and its ``info/exclude``."""
    ignorecase = _git(["config", "--bool", "--get", "core.ignorecase"], git_root, ok=(0, 1)).decode().strip()
    config = ["-c", f"core.ignorecase={ignorecase or 'false'}"]
    excludes = os.fsdecode(_git(["config", "--path", "--get", "core.excludesFile"], git_root, ok=(0, 1))).strip()
    if excludes:
        config += ["-c", f"core.excludesFile={git_root / excludes}"]   # an absolute path stays absolute
    exclude = git_root / os.fsdecode(_git(["rev-parse", "--git-path", "info/exclude"], git_root)).strip()
    return config, exclude if exclude.is_file() else None


def _ancestor_ignores(paths: list[str]) -> list[str]:
    """``.gitignore`` at the root and in every directory above each path: ignored or not, git reads them."""
    found = {GITIGNORE: None}
    for p in paths:
        parts = PurePosixPath(p).parts[:-1]
        for i in range(1, len(parts) + 1):
            found.setdefault(str(PurePosixPath(*parts[:i], GITIGNORE)), None)
    return list(found)


def _copy_ignore(src: Path, dst: Path, link_store: Path) -> None:
    """Copy ``src`` to ``dst``; a symlink stays a symlink, to a scratch copy of its target.

    Git does not read a ``.gitignore`` that is a symlink, so the scratch copy
    must be one too for git to judge it the same way; its target is copied
    inside the scratch repository so the update never writes through to the
    checkout's file.
    """
    dst.parent.mkdir(parents=True, exist_ok=True)
    if src.is_symlink():
        if src.exists():                 # a dangling link stays dangling: the update writes through it
            shutil.copyfile(src, link_store)
        dst.symlink_to(link_store)
    else:
        shutil.copyfile(src, dst)


def estimate(git_root: Path, prefix: str, seed: str, apply: Callable[..., object]) -> list[Match]:
    """The dry-run preview of :func:`observed`, judged in a scratch repository (see the module docstring)."""
    tracked = _paths(_git(["ls-files", "-c", "-z"], git_root))
    shown = _paths(_git(["ls-files", "-o", "--exclude-standard", "-z"], git_root))
    config, exclude = _ignore_config(git_root)
    with tempfile.TemporaryDirectory() as tmp:
        scratch = Path(tmp)
        _git(["init", "-q", str(scratch)], scratch)
        for n, rel in enumerate(r for r in _ancestor_ignores(tracked + shown) if (git_root / r).is_file() or (git_root / r).is_symlink()):
            _copy_ignore(git_root / rel, scratch / rel, scratch / ".git" / f"ignore-link-{n}")
        if exclude is not None:
            shutil.copyfile(exclude, scratch / ".git" / "info" / "exclude")
        before = _ignored(scratch, tracked + shown, config)
        apply(scratch, prefix, gitignore_seed=seed)
        after = _ignored(scratch, tracked + shown, config)
    newly = {p: rule for p, rule in after.items() if p not in before}
    return ([(p, newly[p], TRACKED_NOTE) for p in tracked if p in newly]
            + [(p, newly[p], HIDDEN_NOTE) for p in shown if p in newly])


def print_matches(matches: list[Match] | str, *, estimated: bool) -> None:
    """The note: a skip line, or at most :data:`MATCH_LIMIT` paths then a count, and the untrack hint."""
    if isinstance(matches, str):
        print(f"ignore check skipped: {matches}")
        return
    if not matches:
        return
    print(ESTIMATE_HEADER if estimated else REAL_HEADER)
    for path, rule, note in matches[:MATCH_LIMIT]:
        print(f"  {path} ({rule}): {note}")
    if len(matches) > MATCH_LIMIT:
        print(f"  … and {len(matches) - MATCH_LIMIT} more")
    if any(note == TRACKED_NOTE for _, _, note in matches):
        print(UNTRACK_HINT)
