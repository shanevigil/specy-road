"""Pickup's register step: the claim row plus the generated files it changes, in one commit.

The digest (``roadmap-context.md``) lists claims in flight, so a commit that
adds a registry row and nothing else leaves ``digest --check`` failing on the
integration branch and on every feature branch cut from it. Both generated
files are rendered again after the row is written; the tracked ones that
changed ride in the same commit, and nothing else does.
"""

from __future__ import annotations

from pathlib import Path

from specy_road.bundled_scripts.do_next_task_pickup_helpers import register_and_commit
from specy_road.bundled_scripts.export_roadmap_md import reexport_roadmap_md
from specy_road.bundled_scripts.repo_ops import git_run
from specy_road.digest import DEFAULT_OUTPUT, render_digest
from specy_road.finish_land_deterministic import _has_roadmap_graph
from specy_road.generated_files import GENERATED_COMMITTED
from specy_road.git_subprocess import git_code
from specy_road.registry_yaml import registry_path


def regenerated_tracked_paths(root: Path) -> list[str]:
    """Render ``roadmap.md`` and the digest again; return the tracked ones that changed.

    An untracked or gitignored copy is rendered but never added: the claim
    commit does not start tracking a file the project chose not to.
    """
    if not _has_roadmap_graph(root):
        return []
    reexport_roadmap_md(root)
    (root / DEFAULT_OUTPUT).write_text(render_digest(root), encoding="utf-8")
    return [n for n in GENERATED_COMMITTED if git_code(["diff", "--quiet", "--", n], root)[0] == 1]


def register_claim(
    root: Path,
    node: dict,
    branch: str,
    reg: dict,
    commit_message: str,
    *,
    impl_review_gate: bool,
    owner: str | None = None,
) -> None:
    """Append the claim row and commit it with the regenerated files on the integration branch."""
    register_and_commit(
        registry_path=registry_path(root),
        git_runner=lambda *a: git_run(root, *a),
        node=node,
        branch=branch,
        reg=reg,
        commit_message=commit_message,
        impl_review_gate=impl_review_gate,
        owner=owner,
        generated=lambda: regenerated_tracked_paths(root),
    )
