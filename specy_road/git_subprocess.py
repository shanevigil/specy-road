"""The one git subprocess primitive for the toolkit.

Every git invocation that just runs a command and reads its output goes
through :func:`run`. Before this module was the single door, fourteen modules
each had their own wrapper in four different return shapes and five timeout
policies — including three (``archive_git``, ``history_git``,
``node_activity``) that passed no timeout at all and could hang a CLI or a GUI
request forever against an unresponsive remote.

Output that must stay bytes — paths git prints, which may hold a newline, an
edge space or bytes that are not UTF-8 — goes through :func:`run_bytes` and the
views on it (:func:`git_out`, :func:`git_path`, :func:`git_root`). Interactive
sequences whose progress the user watches go through :func:`git_run`, which
passes output through. ``file_limits_engine`` still spawns git itself, because
it pipes a NUL-separated path list into ``check-ignore --stdin`` under its own
failure rule; it is the one exception.

The shapes callers actually need are all views on one result, so :class:`GitResult`
carries the raw fields and names each view:

* :attr:`GitResult.text` — stripped stdout, or ``None`` on failure. The common case.
* :attr:`GitResult.out` — **raw** stdout. Log and ``cat-file`` parsing needs the
  bytes as git wrote them; stripping corrupts a trailing-newline-sensitive walk.
* :attr:`GitResult.message` — stderr falling back to stdout, for error text.

Nothing here raises. A missing git binary, a directory that is not a worktree,
and a timeout all arrive as a non-zero :attr:`GitResult.code`, because every
caller in this toolkit is best-effort about git and none wants a traceback.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

#: Ceiling for a single git invocation. Generous for local plumbing, but finite
#: so a wedged remote cannot hang a CLI run or a GUI request.
DEFAULT_TIMEOUT = 60.0

#: A history walk over a large repository legitimately outruns the default.
HISTORY_TIMEOUT = 600.0

@dataclass(frozen=True)
class GitResult:
    """Outcome of one git invocation. ``code == -1`` means git never ran.

    :attr:`failure` says *why* git did not report an exit status, because a
    caller that records a status (the registry auto-fetch overlay) must tell a
    timeout apart from a missing binary apart from a real non-zero exit.
    """

    code: int
    out: str
    err: str
    failure: str | None = None

    @property
    def ok(self) -> bool:
        return self.code == 0

    @property
    def text(self) -> str | None:
        """Stripped stdout on success, ``None`` on any failure."""
        return self.out.strip() if self.ok else None

    @property
    def message(self) -> str:
        """stderr, falling back to stdout — the text to show on failure."""
        return (self.err or self.out).strip()


def run(
    args: list[str], cwd: Path, *, timeout: float = DEFAULT_TIMEOUT, env: dict[str, str] | None = None
) -> GitResult:
    """Run ``git <args>`` in ``cwd``, in ``env`` (``None`` inherits this process's). Never raises."""
    try:
        r = subprocess.run(
            ["git", *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            env=env,
        )
    except subprocess.TimeoutExpired as e:
        return GitResult(-1, "", str(e), "timeout")
    except OSError as e:
        return GitResult(-1, "", str(e), "os_error")
    except (ValueError, subprocess.SubprocessError) as e:
        return GitResult(-1, "", str(e), "error")
    return GitResult(r.returncode, r.stdout or "", r.stderr or "")


@dataclass(frozen=True)
class GitBytes:
    """Outcome of one git invocation read as bytes.

    ``code == -1`` means git never ran; ``err`` then says why.
    """

    code: int
    out: bytes
    err: bytes

    @property
    def ok(self) -> bool:
        """Whether git ran and exited 0."""
        return self.code == 0

    @property
    def message(self) -> str:
        """stderr, falling back to stdout, decoded for display."""
        return os.fsdecode(self.err or self.out).strip()

    def checked(self, args: list[str], ok: tuple[int, ...] = (0,)) -> bytes:
        """stdout when the exit code is in ``ok``.

        Otherwise :class:`GitError`, naming the subcommand of ``args`` (the first
        word that is neither an option nor a ``-c`` value) and stderr's last line.
        """
        if self.code in ok:
            return self.out
        lines = os.fsdecode(self.err).strip().splitlines()
        command = next(a for i, a in enumerate(args)
                       if not a.startswith("-") and (i == 0 or args[i - 1] != "-c"))
        raise GitError(f"git {command}: {lines[-1] if lines else f'exit {self.code}'}")


class GitError(Exception):
    """A git call whose exit code the caller does not accept (:meth:`GitBytes.checked`)."""


def run_bytes(
    args: list[str], cwd: Path, *, timeout: float = DEFAULT_TIMEOUT,
    env: dict[str, str] | None = None, stdin: bytes | None = None,
) -> GitBytes:
    """Run ``git <args>`` in ``cwd`` and keep stdout and stderr as bytes. Never raises.

    For output text mode would corrupt: universal newlines turn a ``\\r`` in a path
    into ``\\n``, stripping drops an edge space, and strict decoding of one
    non-UTF-8 name hides every other line.
    """
    try:
        r = subprocess.run(["git", *args], cwd=cwd, input=stdin, capture_output=True,
                           timeout=timeout, check=False, env=env)
    except (OSError, ValueError, subprocess.SubprocessError) as e:
        return GitBytes(-1, b"", os.fsencode(str(e)))
    return GitBytes(r.returncode, r.stdout or b"", r.stderr or b"")


def git_bytes(args: list[str], cwd: Path) -> bytes:
    """``git <args>``'s raw stdout, empty on failure.

    For callers that decode each name or file on its own, so one non-UTF-8
    entry cannot hide the rest.
    """
    r = run_bytes(args, cwd)
    return r.out if r.ok else b""


def git_out(args: list[str], cwd: Path) -> str | None:
    """``git <args>``'s stdout less its final newline, or ``None`` on failure.

    Decoded with :func:`os.fsdecode`. Unlike :func:`git_text` nothing else is
    stripped, and any byte round-trips.
    """
    r = run_bytes(args, cwd)
    return os.fsdecode(r.out.removesuffix(b"\n")) if r.ok else None


def git_path(args: list[str], cwd: Path) -> Path | None:
    """The one path ``git <args>`` prints in ``cwd``, resolved; ``None`` on failure or none printed.

    Each query asks for exactly one value: a path may hold a newline, so a
    multi-value output could not be split back into paths.
    """
    out = git_out(args, cwd)
    return Path(out).resolve() if out else None


def git_root(start: Path | None = None) -> Path | None:
    """The enclosing git worktree root of ``start`` (default: the working directory).

    ``None`` outside one. Read as bytes (:func:`git_path`), so any directory name
    round-trips.
    """
    return git_path(["rev-parse", "--show-toplevel"], start or Path.cwd())


def is_worktree_root(path: Path, branch: str | None = None) -> bool:
    """Whether ``path`` is the top of a git worktree, not a directory inside one.

    With ``branch``, also whether that branch is checked out there.
    """
    if not path.is_dir() or git_root(path) != path.resolve():
        return False
    return branch is None or current_branch_name(path, is_worktree=True) == branch


def git_run(repo_root: Path, *args: str) -> None:
    """Run ``git <args>`` in ``repo_root``, output passed through. Raises ``CalledProcessError``.

    Not captured on purpose: ``git fetch`` and ``git push`` write progress to the
    terminal, and the task-lifecycle commands that use this are the ones a user
    is watching.
    """
    subprocess.check_call(["git", *args], cwd=repo_root)


def git_capture(repo_root: Path, *args: str) -> str:
    """Raw stdout of ``git <args>`` in ``repo_root``. Raises ``CalledProcessError`` on failure.

    Unlike :func:`git_checked` it keeps leading spaces: ``status --porcelain``
    lines start with one.
    """
    return subprocess.run(["git", *args], cwd=repo_root, capture_output=True, text=True,
                          check=True).stdout


def git_text(
    args: list[str], cwd: Path, *, timeout: float = DEFAULT_TIMEOUT
) -> str | None:
    """Stripped stdout, or ``None`` on any failure."""
    return run(args, cwd, timeout=timeout).text


def git_stdout(
    args: list[str], cwd: Path, *, timeout: float = DEFAULT_TIMEOUT
) -> str | None:
    """**Raw** stdout, or ``None`` on any failure.

    Distinct from :func:`git_text` on purpose: ``log --raw`` and ``cat-file``
    output is parsed line-by-line and must not be stripped.
    """
    r = run(args, cwd, timeout=timeout)
    return r.out if r.ok else None


def git_ok(
    args: list[str], cwd: Path, timeout: float = DEFAULT_TIMEOUT
) -> tuple[bool, str]:
    """``(ok, output_or_error)``.

    When git never ran at all — timeout, missing binary — the second element is
    empty rather than the exception text. Callers of this shape branch on the
    boolean and surface the string to users; :func:`run` carries the reason for
    the callers that record it.
    """
    r = run(args, cwd, timeout=timeout)
    if r.ok:
        return True, r.out.strip()
    return False, ("" if r.failure else r.message)


def git_code(
    args: list[str], cwd: Path, *, timeout: float = DEFAULT_TIMEOUT
) -> tuple[int, str]:
    """``(exit code, message)`` — for step-by-step sequences that branch on
    the code and report the message, such as a merge-and-push rollup."""
    r = run(args, cwd, timeout=timeout)
    return r.code, r.message


def git_checked(
    args: list[str], cwd: Path, *, timeout: float = DEFAULT_TIMEOUT
) -> str:
    """Stripped stdout, raising :class:`subprocess.CalledProcessError` on failure.

    The exception to this module's never-raises rule, for the few callers whose
    return type is a plain ``str`` and whose caller would otherwise carry an
    empty string into a later git command.
    """
    r = run(args, cwd, timeout=timeout)
    if not r.ok:
        raise subprocess.CalledProcessError(r.code, ["git", *args], r.out, r.err)
    return r.out.strip()


def local_branch_exists(repo_root: Path, branch: str) -> bool:
    """Whether ``branch`` is present in this clone as a local ref."""
    r = run(["rev-parse", "--verify", "--quiet", f"refs/heads/{branch}"], repo_root)
    return r.ok


def commits_behind(repo_root: Path, branch: str, base: str) -> int | None:
    """How many commits ``base`` has that ``branch`` does not, or ``None``.

    ``None`` means the question could not be answered — no such ref, not a
    worktree — which callers treat as "say nothing" rather than "zero".
    """
    out = git_text(["rev-list", "--count", f"{branch}..{base}"], repo_root)
    try:
        return int(out) if out else None
    except ValueError:
        return None


def merge_conflicts(repo_root: Path, ours: str, theirs: str) -> list[str] | None:
    """Paths a merge of ``theirs`` into ``ours`` would leave conflicted, or ``None``.

    ``git merge-tree --write-tree`` merges in memory — no checkout, index or
    working-tree change — so a coordinator can ask about any branch. ``[]`` is
    a clean merge. ``None`` means git could not answer (an unknown ref, or a git
    older than 2.38), which callers treat as "say nothing". Paths are named
    from the repository root.
    """
    # merge-tree names paths relative to the working directory, so run it at the top level.
    top = git_root(repo_root) or repo_root   # not a repo: merge-tree fails below
    r = run(["merge-tree", "--write-tree", "--name-only", "--no-messages", "-z", ours, theirs], top)
    # Both outcomes print the merged tree id first; an unknown ref also exits 1, with nothing on stdout.
    fields = r.out.split("\0")
    if r.code not in (0, 1) or not fields[0].strip():
        return None
    return sorted({f for f in fields[1:] if f})


def is_git_worktree(repo_root: Path) -> bool:
    """Whether ``repo_root`` is inside a git worktree."""
    return (git_text(["rev-parse", "--is-inside-work-tree"], repo_root) or "").lower() == "true"


def current_branch_name(
    repo_root: Path, *, is_worktree: bool | None = None
) -> str | None:
    """Current branch, or ``None`` outside a worktree / on a detached HEAD.

    ``is_worktree`` lets a caller that has already probed pass the answer in;
    building the PM GUI's git status otherwise runs the same
    ``rev-parse --is-inside-work-tree`` five times per request.
    """
    if not (is_git_worktree(repo_root) if is_worktree is None else is_worktree):
        return None
    return git_text(["branch", "--show-current"], repo_root) or None


def head_sha(repo_root: Path) -> str | None:
    """Full SHA of ``HEAD``, or ``None``."""
    return git_text(["rev-parse", "HEAD"], repo_root) or None


def working_tree_clean(repo_root: Path) -> bool:
    """Whether the working tree has no staged, unstaged or untracked changes."""
    if not is_git_worktree(repo_root):
        return False
    r = run(["status", "--porcelain"], repo_root)
    return r.ok and r.out.strip() == ""
