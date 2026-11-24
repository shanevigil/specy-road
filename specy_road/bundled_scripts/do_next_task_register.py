"""Pickup's register step: the claim row plus the generated files it changes, in one commit.

The digest (``roadmap-context.md``) lists claims in flight, so a commit that
adds a registry row and nothing else leaves ``digest --check`` failing on the
integration branch and on every feature branch cut from it. The tracked
generated files are rendered again after the row is written; those that
changed ride in the same commit, and nothing else does.
"""

from __future__ import annotations

from pathlib import Path

from specy_road import safe_write
from specy_road.bundled_scripts.do_next_task_pickup_helpers import register_and_commit
from specy_road.bundled_scripts.export_roadmap_md import reexport_roadmap_md
from specy_road.digest import DEFAULT_OUTPUT, render_digest
from specy_road.finish_land_deterministic import _has_roadmap_graph
from specy_road.generated_files import GENERATED_COMMITTED
from specy_road.git_subprocess import git_code
from specy_road.registry_yaml import registry_path


def regenerated_tracked_paths(root: Path) -> list[str]:
    """Render the tracked ones of ``roadmap.md`` and the digest again; return those that changed.

    A file git does not track is neither rendered nor added: the claim commit
    does not start tracking a file the project chose not to, and pickup does
    not leave a new untracked file behind for the next clean-tree check.
    Each is written by the safe-write rule: a symlink at it raises ``SafeWriteError``.
    """
    if not _has_roadmap_graph(root):
        return []
    tracked = [n for n in GENERATED_COMMITTED
               if git_code(["ls-files", "--error-unmatch", "--", n], root)[0] == 0]
    if "roadmap.md" in tracked:
        reexport_roadmap_md(root)
    if DEFAULT_OUTPUT in tracked:
        safe_write.write(root, root / DEFAULT_OUTPUT, render_digest(root))
    return [n for n in tracked if git_code(["diff", "--quiet", "--", n], root)[0] == 1]


def register_claim(
    root: Path,
    node: dict,
    branch: str,
    reg: dict,
    commit_message: str,
    *,
    git_runner,
    impl_review_gate: bool,
    owner: str | None = None,
) -> None:
    """Append the claim row and commit it with the regenerated files on the integration branch.

    ``git_runner`` is the caller's (``do_next_task``'s ``git_run`` bound to the root),
    so the git calls stay patchable where they always were.
    """
    register_and_commit(
        registry_path=registry_path(root),
        git_runner=git_runner,
        node=node,
        branch=branch,
        reg=reg,
        commit_message=commit_message,
        impl_review_gate=impl_review_gate,
        owner=owner,
        generated=lambda: regenerated_tracked_paths(root),
    )
