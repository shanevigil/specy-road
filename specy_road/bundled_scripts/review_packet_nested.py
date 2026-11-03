"""``## Nested repositories`` in the review packet: the leaf's diff in each ``nested_repos`` repository.

Split from :mod:`specy_road.bundled_scripts.review_packet` for the file limit.
A leaf whose work lives in a separately versioned repository under the project
root has its branch there under the same name; the main repository's diff
cannot show it, so reviewers had to be handed it by hand. Each configured
repository gets its changed paths, judged against the touch zones as the main
repository's are, and its diff from the merge base with its integration branch.
"""

from __future__ import annotations

from pathlib import Path

from specy_road.finish_implementation_check import in_zones
from specy_road.git_changed_paths import diff_paths
from specy_road.git_subprocess import git_stdout
from specy_road.nested_repos import NestedRepo, branch_diff_range, nested_repos
from specy_road.review_files import reviews_dir
from specy_road.review_target import ReviewTarget
from specy_road.runtime_paths import project_prefix

NOTE = ("_Computed by review-packet from each nested repository's git (`nested_repos` in "
        "`roadmap/git-workflow.yaml`): the leaf's branch there, from its merge base with that repository's "
        "integration branch. Paths are project-relative._")


def _patch_name(nr: NestedRepo) -> str:
    return "DIFF-nested-" + nr.path.replace("/", "-") + ".patch"


def _repo_lines(root: Path, t: ReviewTarget, nr: NestedRepo, branch: str, zones: list[str],
                max_diff_lines: int) -> list[str]:
    """One repository's subsection: changed paths with outside-zone marks, then its diff (or where it was written)."""
    from specy_road.bundled_scripts.review_packet import _fence   # noqa: PLC0415 — review_packet imports this module

    out = [f"### `{nr.path}`", ""]
    patch = reviews_dir(root, t.node_id) / _patch_name(nr)
    patch.unlink(missing_ok=True)   # only a capped section names one
    rng = branch_diff_range(root, nr, branch)
    if rng is None:
        return out + [f"_No `{branch}` branch in this repository: the leaf did not change it._", ""]
    repo, prefix = root / nr.path, project_prefix(root)
    paths = diff_paths(repo, rng) or []
    out += [f"_`{rng}` in `{nr.path}`._", ""]
    for p in paths:
        inside = not zones or in_zones(zones, f"{prefix}{nr.path}/{p}", prefix)
        out.append(f"- `{nr.path}/{p}`" + ("" if inside else "  **← outside touch zones**"))
    if not paths:
        return out + ["- _none_", ""]
    diff = git_stdout(["diff", rng], repo) or ""
    if max_diff_lines and diff.count("\n") > max_diff_lines:
        patch.parent.mkdir(parents=True, exist_ok=True)
        patch.write_text(diff, encoding="utf-8")
        return out + ["", f"**Diff capped at {max_diff_lines} lines** ({diff.count(chr(10))} lines): "
                      f"the full diff is at `{patch}`.", ""]
    return out + [""] + _fence(diff, "diff")


def nested_diff_section(root: Path, t: ReviewTarget, max_diff_lines: int) -> list[str]:
    """The section, or nothing when no nested repository is configured."""
    repos = nested_repos(root)
    if not repos:
        return []
    branch = (t.entry or {}).get("branch") or t.ref
    zones = [z.strip().strip("/") for z in t.review_zones if isinstance(z, str) and z.strip()]
    out = ["## Nested repositories", "", NOTE, ""]
    for nr in repos:
        out += _repo_lines(root, t, nr, branch, zones, max_diff_lines)
    return out
