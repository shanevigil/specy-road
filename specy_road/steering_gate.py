"""Steering files at finish: the in-tree steering list and the merge-point refusal that uses it (M22.31).

Some files a leaf's branch can change are later read or run by trusted code outside the executor: the
coordinator's harness (its config and hooks), the coordinator's shell (root startup files) and the toolkit's own
gate (the three roadmap policy files). Finish is the merge point on every platform, sandboxed or not, so a
reviewed touch zone that names the exact path is the only way such a change reaches the integration branch
(docs/orchestration-steering-files.md).

- :func:`in_tree_class`: the steering class of one path, or ``None``.
- :func:`zones_or_exit`: finish's implementation check, then :func:`steering_or_exit`, which refuses, before any
  bookkeeping, a branch whose diff against the merge base changes a steering path no touch zone names exactly,
  and refuses as well when the integration ref, the merge base or the changed paths cannot be read.
"""

from __future__ import annotations

import fnmatch
import sys
from pathlib import Path

from specy_road.finish_implementation_check import _clean, base_ref, implementation_or_exit
from specy_road.git_changed_paths import diff_paths
from specy_road.git_subprocess import git_text
from specy_road.runtime_paths import project_prefix, rebase_to_project

#: The toolkit's policy files, project-relative.
POLICY_FILES = ("roadmap/orchestration.yaml", "roadmap/orchestration.local.yaml", "roadmap/git-workflow.yaml")
#: Shell startup files at the git root and the project root.
SHELL_FILES = (".bashrc", ".bash_profile", ".profile", ".zshrc", ".zshenv", ".envrc")


def in_tree_class(rel: str, *, project: bool = True) -> str | None:
    """The class of an in-tree steering path (``harness``, ``policy_tree``, ``shell_startup``), or ``None``.

    ``rel`` is relative to the project root (``project``) or to the git root, where only harness config and shell
    startup files count. ``roadmap/registry.yaml`` is never a steering path here."""
    parts = rel.split("/")
    if project and rel in POLICY_FILES:
        return "policy_tree"
    if rel in SHELL_FILES:
        return "shell_startup"
    head, n = parts[0], len(parts)
    if head == ".codex" and n > 1:
        return "harness"
    if head == ".claude" and ((n == 2 and fnmatch.fnmatch(parts[1], "settings*.json")) or (n > 2 and parts[1] == "hooks")):
        return "harness"
    if head == ".cursor" and ((n == 2 and parts[1].endswith(".json")) or (n > 2 and parts[1] == "hooks")):
        return "harness"
    return None


def steering_hits(paths: list[str], prefix: str, zones: list[str]) -> list[tuple[str, str]]:
    """``(path, class)`` per git-root-relative changed path that is an in-tree steering path and that no touch
    zone names exactly (a directory or glob zone does not count)."""
    exact = {z for z in (_clean(z) for z in zones) if z}
    out = []
    for p in paths:
        rel = rebase_to_project(p, prefix)
        cls = (in_tree_class(rel) if rel is not None else None) or in_tree_class(p, project=False)
        if cls and p not in exact and rel not in exact:
            out.append((rel if rel is not None else p, cls))
    return out


def zones_or_exit(repo_root: Path, *, node: dict, entry: dict, node_id: str, remote: str,
                  integration_branch: str, allow_empty: bool) -> None:
    """Finish's two checks of what the branch changed against its zones, both before any bookkeeping: the
    implementation check (finish_implementation_check), then the steering files (:func:`steering_or_exit`)."""
    implementation_or_exit(repo_root, node=node, entry=entry, node_id=node_id, remote=remote,
                           integration_branch=integration_branch, allow_empty=allow_empty)
    steering_or_exit(repo_root, node=node, entry=entry, remote=remote, integration_branch=integration_branch)


def _unreadable(what: str) -> None:
    print(f"error: finish cannot check this branch for steering files (docs/orchestration-steering-files.md): "
          f"{what} could not be read. Nothing was changed; fix that and run finish again.", file=sys.stderr)
    raise SystemExit(1)


def steering_or_exit(repo_root: Path, *, node: dict, entry: dict, remote: str, integration_branch: str) -> None:
    """Refuse, before finish's bookkeeping commit, a branch whose diff against the merge base changes an
    in-tree steering path no touch zone names exactly, or whose diff cannot be read."""
    ref = base_ref(repo_root, remote, integration_branch)
    if ref is None:
        _unreadable(f"the integration ref ({remote}/{integration_branch} or {integration_branch})")
    merge_base = git_text(["merge-base", ref, "HEAD"], repo_root)
    if not merge_base:
        _unreadable(f"the merge base of HEAD and {ref}")
    paths = diff_paths(repo_root, merge_base, "HEAD")
    if paths is None:
        _unreadable(f"the paths changed since the merge base {merge_base[:12]}")
    zones = entry.get("touch_zones") or node.get("touch_zones") or []
    hits = steering_hits(paths, project_prefix(repo_root), zones)
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
