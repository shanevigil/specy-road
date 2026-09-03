"""The one git subprocess primitive for the toolkit.

Every git invocation in this package goes through :func:`run`. Before this
module was the single door, fourteen modules each had their own wrapper in four
different return shapes and five timeout policies — including three
(``archive_git``, ``history_git``, ``node_activity``) that passed no timeout at
all and could hang a CLI or a GUI request forever against an unresponsive
remote.

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


def run(args: list[str], cwd: Path, *, timeout: float = DEFAULT_TIMEOUT) -> GitResult:
    """Run ``git <args>`` in ``cwd``. Never raises."""
    try:
        r = subprocess.run(
            ["git", *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as e:
        return GitResult(-1, "", str(e), "timeout")
    except OSError as e:
        return GitResult(-1, "", str(e), "os_error")
    except (ValueError, subprocess.SubprocessError) as e:
        return GitResult(-1, "", str(e), "error")
    return GitResult(r.returncode, r.stdout or "", r.stderr or "")


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


def is_git_worktree(repo_root: Path) -> bool:
    """Whether ``repo_root`` is inside a git worktree."""
    return (git_text(["rev-parse", "--is-inside-work-tree"], repo_root) or "").lower() == "true"


def current_branch_name(repo_root: Path) -> str | None:
    """Current branch, or ``None`` outside a worktree / on a detached HEAD."""
    if not is_git_worktree(repo_root):
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
