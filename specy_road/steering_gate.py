"""Steering files at finish and at launch (M21.7): the two uses of :mod:`specy_road.steering_paths` outside a
worker turn.

- :func:`zones_or_exit`: finish's implementation check, then :func:`steering_or_exit`, which refuses a branch
  that changes an in-tree steering path no touch zone names exactly.
- :func:`claude_denies`: per-file ``--disallowedTools`` rules for a Claude Code executor's launch and resume.

Split from :mod:`specy_road.steering_paths` for the file limit.
"""

from __future__ import annotations

import sys
from pathlib import Path

from specy_road.finish_implementation_check import _clean, base_ref, changed_paths, implementation_or_exit
from specy_road.review_target import ReviewTargetError, resolve_target
from specy_road.runtime_paths import prefix_within, rebase_to_project
from specy_road.steering_paths import (CLAUDE_ALWAYS_DENIED, FINISH_CLASSES, HARNESS_DIRS, POLICY_FILES, SHELL_FILES,
                                      in_tree_class, tree_files)
from specy_road.worktree_env import git_top

# --- finish -----------------------------------------------------------------------------------------------


def steering_hits(paths: list[str], prefix: str, zones: list[str]) -> list[tuple[str, str]]:
    """``(path, class)`` per git-root-relative changed path that is an in-tree steering path finish refuses
    (:data:`FINISH_CLASSES`) and that no touch zone names exactly (a directory or glob zone does not count)."""
    exact = {z for z in (_clean(z) for z in zones) if z}
    out = []
    for p in paths:
        rel = rebase_to_project(p, prefix)
        cls = (in_tree_class(rel) if rel is not None else None) or in_tree_class(p, project=False)
        if cls in FINISH_CLASSES and p not in exact and rel not in exact:
            out.append((rel if rel is not None else p, cls))
    return out


def zones_or_exit(repo_root: Path, *, node: dict, entry: dict, node_id: str, remote: str,
                  integration_branch: str, allow_empty: bool) -> None:
    """Finish's two checks of what the branch changed against its zones, both before any bookkeeping: the
    implementation check (finish_implementation_check), then the steering files (:func:`steering_or_exit`)."""
    implementation_or_exit(repo_root, node=node, entry=entry, node_id=node_id, remote=remote,
                           integration_branch=integration_branch, allow_empty=allow_empty)
    steering_or_exit(repo_root, node=node, entry=entry, remote=remote, integration_branch=integration_branch)


def steering_or_exit(repo_root: Path, *, node: dict, entry: dict, remote: str, integration_branch: str) -> None:
    """Refuse, before finish's bookkeeping commit, a branch whose diff against the merge base changes an
    in-tree steering path no touch zone names exactly."""
    ref = base_ref(repo_root, remote, integration_branch)
    paths = changed_paths(repo_root, ref) if ref else None
    top = git_top(repo_root)
    zones = entry.get("touch_zones") or node.get("touch_zones") or []
    hits = steering_hits(paths or [], prefix_within(top, Path(repo_root)), zones)
    if not hits:
        return
    print(f"error: this branch changes {len(hits)} steering file(s) that trusted code outside the executor "
          "reads or runs (docs/orchestration-steering-files.md):", file=sys.stderr)
    for path, cls in hits:
        print(f"  {path} ({cls})", file=sys.stderr)
    print("  Next step, per path: if the change is intended, add that exact path to the leaf's touch zones and "
          "get it reviewed:\n"
          f"    specy-road edit-node {node['id']} --set touch_zones=<current zones>,<path>\n"
          f"  otherwise revert it on this branch (git checkout {ref} -- <path>) and commit.", file=sys.stderr)
    raise SystemExit(1)


# --- Claude Code launch ---------------------------------------------------------------------------------


def claude_denies(worktree: Path, repo_root: Path | None, node_id: str | None) -> list[str]:
    """``--disallowedTools`` with ``Edit(./<rel>)`` and ``Write(./<rel>)`` for each in-tree steering file present
    in ``worktree`` (the harness's cwd) plus :data:`CLAUDE_ALWAYS_DENIED` and the policy files, skipping each
    path a touch zone names exactly. One rule per file, no parent glob: no rule can match an exempt path."""
    top = Path(worktree)
    prefix = prefix_within(git_top(repo_root), Path(repo_root)) if repo_root else ""
    zones: list[str] = []
    if repo_root and node_id:
        try:
            zones = resolve_target(repo_root, node_id).touch_zones
        except ReviewTargetError:
            zones = []
    exact = {z for z in (_clean(z) for z in zones) if z}
    rels = set(CLAUDE_ALWAYS_DENIED) | {prefix + p for p in POLICY_FILES}
    for base, project, lead in ((top, prefix == "", ""), (top / prefix, True, prefix)):
        for name in (*SHELL_FILES, *(POLICY_FILES if project else ())):
            if (base / name).exists() or (base / name).is_symlink():
                rels.add(lead + name)
        for d in HARNESS_DIRS:
            for p in tree_files(base / d) if (base / d).is_dir() else []:
                if in_tree_class(rel := p.relative_to(base).as_posix(), project=project):
                    rels.add(lead + rel)
    keep = sorted(r for r in rels if r not in exact and rebase_to_project(r, prefix) not in exact)
    rules = [rule for r in keep for rule in (f"Edit(./{r})", f"Write(./{r})")]
    return ["--disallowedTools", *rules] if rules else []
