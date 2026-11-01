"""What a ``session start`` / ``touch`` overlap warning says about the other copy.

:func:`specy_road.session_presence.warn_lines` names the other session and its
branch. An adopter found that warning was the useful signal that a later merge
would conflict, and then had to go and look for the rest: which worktree the
other session is in, and whether that copy has actually changed the
overlapping paths (rc1 feedback triage, M4.15). So the start/touch warning
adds, per overlapping session, its worktree and branch, whether it is yours
(the same ``$USER``, typically another worktree of your own), and the edit
state there: uncommitted edits to the overlap, commits touching it not yet
merged into the integration branch, or neither.

Session paths are written as their author typed them, git-root- or
project-relative, so a changed file counts when either form of its path falls
inside the overlap. Git cannot always answer (a removed worktree, no
integration branch); that piece is then reported as unknown, never as clean.
"""

from __future__ import annotations

from pathlib import Path

from specy_road.finish_implementation_check import base_ref, zone_matches
from specy_road.git_changed_paths import diff_paths
from specy_road.git_subprocess import git_stdout, git_text
from specy_road.git_workflow_config import resolve_integration_defaults
from specy_road.runtime_paths import project_prefix, rebase_to_project
from specy_road.session_presence import Session, current_user, warn_lines

_SHOWN = 4


def _in_overlap(path: str, hits: list[tuple[str, str]], prefix: str) -> bool:
    """Whether ``path`` (git-root-relative) lies inside both sides of some overlapping pair."""
    forms = {path, rebase_to_project(path, prefix) or path}
    return any(zone_matches(a, f) and zone_matches(b, f) for a, b in hits for f in forms)


def _uncommitted(top: Path) -> list[str] | None:
    """Tracked changes against ``HEAD`` (staged or not) plus untracked, non-ignored files."""
    changed = diff_paths(top, "HEAD")
    untracked = git_stdout(["ls-files", "--others", "--exclude-standard", "-z"], top)
    if changed is None or untracked is None:
        return None
    return sorted(set(changed) | {p for p in untracked.split("\0") if p})


def _few(paths: list[str]) -> str:
    more = f" (+{len(paths) - _SHOWN} more)" if len(paths) > _SHOWN else ""
    return ", ".join(paths[:_SHOWN]) + more


def edit_state(worktree: str | None, hits: list[tuple[str, str]], *, base: str, remote: str,
               prefix: str) -> str:
    """One line: the other worktree's uncommitted and unmerged edits inside the overlap."""
    wt = Path(worktree) if worktree else None
    top = git_text(["rev-parse", "--show-toplevel"], wt) if wt and wt.is_dir() else None
    if top is None:
        return f"edits there: unknown (no git checkout at {worktree or 'an unrecorded worktree'})"
    ref = base_ref(Path(top), remote, base)
    unmerged = diff_paths(Path(top), f"{ref}...HEAD") if ref else None
    found, unknown = [], []
    for label, files in (("uncommitted", _uncommitted(Path(top))),
                         (f"committed, not merged into {base}", unmerged)):
        if files is None:
            unknown.append(label)
            continue
        inside = [f for f in files if _in_overlap(f, hits, prefix)]
        if inside:
            found.append(f"{label}: {_few(inside)}")
    found += [f"{label}: unknown" for label in unknown]
    return "edits there: " + ("; ".join(found) if found else
                              f"neither uncommitted nor unmerged into {base} on the overlapping paths")


def _owner(s: Session) -> str:
    if s.user and s.user == current_user():
        return "yours"
    return f"user {s.user!r}" if s.user else "user not recorded"


def overlap_warning_lines(repo_root: Path, found: list[tuple[Session, list[tuple[str, str]]]], *,
                          what: str) -> list[str]:
    """:func:`warn_lines` for each overlapping session, each followed by where it is and what it changed."""
    if not found:
        return []
    base, remote, _ = resolve_integration_defaults(repo_root, explicit_base=None, explicit_remote=None)
    prefix = project_prefix(repo_root)
    lines: list[str] = []
    for s, hits in found:
        lines += warn_lines([(s, hits)], what=what)
        lines.append(f"  {_owner(s)}: worktree {s.worktree or '(not recorded)'}, "
                     f"branch {s.branch or '(none recorded)'}")
        lines.append("  " + edit_state(s.worktree, hits, base=base, remote=remote, prefix=prefix))
    return lines
