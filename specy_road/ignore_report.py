"""The note on files a ``.gitignore`` update reaches: observed in a real run, estimated in a dry run.

**Real run: observed, not predicted.** Git lists, in the checkout itself, the
untracked files it shows (:func:`observe`), once before the write and once
after: *now hidden* is a file shown before and not after. *Still tracked under
a new rule* is not a before/after difference either: a tracked file is listed
when git ignores it after the write (every input counted, so a negation keeps
it out) and a line the update added to the top-level ``.gitignore`` (a line
not already in the file) matches it on its own, in a scratch ``.gitignore``
holding only those lines. An older rule that also matches it, whichever rule
git lets decide, does not hide the notice. Whatever git reads (rule order,
nested and self-ignored ``.gitignore`` files, ``info/exclude``,
``core.ignorecase``, the global excludes file) is therefore accounted for by
git, not reproduced here.

**Dry run: an estimate, labelled as one.** Nothing may be written, so
:func:`estimate` copies the current top-level ``.gitignore``, the ``.gitignore``
in every ancestor directory of every candidate path (ignored ones included;
a symlinked one stays a symlink, which git does not read), and ``info/exclude``
into a throwaway ``git init`` directory, applies the update there and asks git
before and after (the same two definitions), with the checkout's
``core.ignorecase`` and ``core.excludesFile``. Known limits: it reproduces
only those inputs, so it can differ from the real run when git reads anything
else (another config setting, an ignore file this list misses) or when files
change between the dry run and the real one; the real run reports exactly
what changed.

Either way the note is advisory: any failure becomes one
``ignore check skipped: <reason>`` line (see :func:`attempt`), and the writes
it describes go ahead unchanged.
"""

from __future__ import annotations

import os
import shlex
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
UNTRACK_LABEL = "  to stop tracking them, run from the git root (specy-road never runs it):"
#: What to do about a tracked file a new rule matches: printed after the command, which is never run for you.
UNTRACK_HINT = ("  keep tracking a file meant to be shared (the rule only hides new files); "
                "untrack one that is session scratch")
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


def _shown(git_root: Path) -> list[str]:
    """The untracked files git shows in ``git_root`` now."""
    return _paths(_git(["ls-files", "-o", "--exclude-standard", "-z"], git_root))


def _top_ignore(root: Path) -> bytes:
    """The top-level ``.gitignore``'s bytes, empty when there is none (a symlink is read through)."""
    path = root / GITIGNORE
    return path.read_bytes() if path.is_file() else b""


def observe(git_root: Path) -> tuple[list[str], bytes]:
    """``(untracked files git shows, top-level .gitignore bytes)`` in the checkout, before the write."""
    return _shown(git_root), _top_ignore(git_root)


def observed(git_root: Path, before: tuple[list[str], bytes]) -> list[Match]:
    """What the write just changed, from :func:`observe` before it and git now (see the module docstring)."""
    now_shown = set(_shown(git_root))
    hidden = [p for p in before[0] if p not in now_shown]
    tracked = _paths(_git(["ls-files", "-c", "-z"], git_root))
    rules = _ignored(git_root, hidden, [])
    return (_tracked_under_new_rules(git_root, tracked, before[1], _ignore_config(git_root)[0])
            + [(p, rules.get(p, "?"), HIDDEN_NOTE) for p in hidden])


def _deciding(cwd: Path, paths: list[str], config: list[str]) -> list[tuple[bytes, bytes, bytes, str]]:
    """``(source, line number, rule, path)`` for each path git ignores in ``cwd`` (index not consulted)."""
    if not paths:
        return []
    fields = _git([*config, "check-ignore", "--no-index", "-v", "-z", "--stdin"], cwd,
                  stdin=_stdin(paths), ok=(0, 1)).split(b"\0")
    return [(src, line, rule, os.fsdecode(path)) for src, line, rule, path in zip(*[iter(fields)] * 4)
            if not rule.startswith(b"!")]


def _ignored(cwd: Path, paths: list[str], config: list[str]) -> dict[str, str]:
    """``{path: rule}`` for each path git ignores when run in ``cwd``."""
    return {path: os.fsdecode(rule) for _src, _line, rule, path in _deciding(cwd, paths, config)}


def _added_lines(old: bytes, new: bytes) -> list[bytes]:
    """The lines of ``new`` that are not a line of ``old`` (a trailing CR ignored), in order."""
    kept = {ln.rstrip(b"\r") for ln in old.split(b"\n")}
    return [ln.rstrip(b"\r") for ln in new.split(b"\n") if ln.strip() and ln.rstrip(b"\r") not in kept]


def _new_rule_matches(paths: list[str], added: list[bytes], config: list[str]) -> dict[str, str]:
    """``{path: new rule}`` for each path one of the ``added`` lines matches on its own, judged by git.

    The lines alone become a top-level ``.gitignore`` in a scratch repository, so
    no other rule can take the attribution; only matches from that file count.
    """
    if not paths or not added:
        return {}
    with tempfile.TemporaryDirectory() as tmp:
        scratch = Path(tmp)
        _git(["init", "-q", str(scratch)], scratch)
        (scratch / GITIGNORE).write_bytes(b"".join(ln + b"\n" for ln in added))
        return {path: os.fsdecode(rule) for src, _line, rule, path in _deciding(scratch, paths, config)
                if src == GITIGNORE.encode()}


def _tracked_under_new_rules(cwd: Path, tracked: list[str], old: bytes, config: list[str]) -> list[Match]:
    """Tracked paths git ignores now that a line the update added matches (``old`` → now), in ``tracked`` order.

    Two questions, both answered by git: is the path ignored after the update,
    with every input git reads (so a negation still keeps it out), and does an
    added line match it on its own (so an older rule that git lets decide,
    before or after the block or in a nested ``.gitignore``, does not hide it).
    """
    ignored = _ignored(cwd, tracked, config)
    rules = _new_rule_matches([p for p in tracked if p in ignored], _added_lines(old, _top_ignore(cwd)), config)
    return [(p, rules[p], TRACKED_NOTE) for p in tracked if p in rules]


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
        before, old = _ignored(scratch, shown, config), _top_ignore(scratch)
        apply(scratch, prefix, gitignore_seed=seed)
        after = _ignored(scratch, shown, config)
        tracked_matches = _tracked_under_new_rules(scratch, tracked, old, config)
    return tracked_matches + [(p, after[p], HIDDEN_NOTE) for p in shown if p in after and p not in before]


def print_matches(matches: list[Match] | str, *, estimated: bool) -> None:
    """The note: a skip line, or at most :data:`MATCH_LIMIT` paths then a count, and for tracked
    paths the ``git rm --cached`` command (printed, never run) with when to keep tracking instead."""
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
    tracked = [path for path, _, note in matches if note == TRACKED_NOTE]
    if tracked:
        for line in untrack_lines(tracked, [path for path, _, note in matches[:MATCH_LIMIT] if note == TRACKED_NOTE]):
            print(line)
        print(UNTRACK_HINT)


def command_line(argv: list[str]) -> str:
    """A line to copy and paste: ``argv`` shell-quoted, indented, and nothing else on it."""
    return "    " + shlex.join(argv)


def untrack_lines(tracked: list[str], listed: list[str]) -> list[str]:
    """The ``git rm --cached`` command for the ``listed`` tracked paths, each command on a line of its own.

    When ``tracked`` has more than were listed, a note line and the command that lists them follow.
    """
    lines = [UNTRACK_LABEL, command_line(["git", "rm", "--cached", "--", *listed])]
    if rest := len(tracked) - len(listed):
        lines += [f"  {rest} more tracked file(s) match a new rule; this lists every tracked file git ignores:",
                  command_line(["git", "ls-files", "-ci", "--exclude-standard"])]
    return lines
