"""Project preferences in ``roadmap/git-workflow.yaml`` that the workflow respects (M15.22).

- ``pr_body_footer``: text finish-this-task appends to the PR body it writes.
- ``implementation_summary``: ``commit`` (default) or ``local``; whether
  executor prompts say to commit ``work/implementation-summary-<ID>.md`` or to
  leave it uncommitted for the review packet to read from the worktree. A
  ``.gitignore`` rule that ignores the summary wins over ``commit``: prompts never
  tell a worker to force-add an ignored path, and ``validate`` says so.
- ``land``: ``push`` (default) or ``local``; how merge mode lands the root
  repository (:mod:`specy_road.finish_land_local`).

Per-leaf settings (the summary rule, the PR body footer) are read from the
leaf's own checkout, found by :func:`leaf_root`, whichever checkout asks:
a linked leaf worktree can carry a committed setting its main checkout lacks.
``land`` is read by finish in the checkout that has the leaf's branch, which is
that same checkout.

See ``docs/git-workflow-preferences.md``. An unreadable config yields each
default, as :func:`specy_road.git_workflow_config._flag` does for booleans.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from specy_road.git_subprocess import git_code, git_text
from specy_road.git_workflow_config import GIT_WORKFLOW_REL, load_git_workflow_config
from specy_road.runtime_paths import project_prefix

SUMMARY_COMMIT, SUMMARY_LOCAL = "commit", "local"
LAND_PUSH, LAND_LOCAL = "push", "local"

def summary_rel(node_id: str) -> str:
    """The leaf's implementation summary, relative to the project root."""
    return f"work/implementation-summary-{node_id}.md"


def leaf_root(repo_root: Path, node_id: str) -> Path:
    """The project root of the checkout holding ``node_id``'s branch, else ``repo_root``.

    The one resolver for "this leaf's preferences": from the main checkout or
    any linked worktree, it names the worktree that has ``feature/rm-<codename>``
    checked out, where the leaf's commands run and its committed settings live.
    A leaf whose branch is checked out nowhere (or that has no codename) reads
    ``repo_root``.
    """
    from specy_road.bundled_scripts.roadmap_load import discover_manifest_path, load_roadmap   # noqa: PLC0415

    try:
        discover_manifest_path(repo_root)
    except FileNotFoundError:   # no roadmap here: nothing names the leaf's branch
        return repo_root
    node = next((n for n in load_roadmap(repo_root)["nodes"] if n.get("id") == node_id), None)
    if not node or not node.get("codename"):
        return repo_root
    want, holder = f"branch refs/heads/feature/rm-{node['codename']}", None
    for line in (git_text(["worktree", "list", "--porcelain"], repo_root) or "").splitlines():
        if line.startswith("worktree "):
            holder = Path(line[len("worktree "):])
        elif line == want and holder is not None:
            return holder / project_prefix(repo_root)
    return repo_root


def _value(repo_root: Path, key: str) -> Any:
    data, err = load_git_workflow_config(repo_root)
    return None if err or not data else data.get(key)


def pr_body_footer(repo_root: Path, node_id: str) -> str | None:
    """``node_id``'s ``pr_body_footer`` stripped, or ``None`` when unset; the schema refuses an empty or
    whitespace-only one."""
    text = _value(leaf_root(repo_root, node_id), "pr_body_footer")
    return text.strip() if text else None


def root_land(repo_root: Path) -> str:
    """``land`` for the root repository: ``push`` (default) or ``local``."""
    return _value(repo_root, "land") or LAND_PUSH


def summary_ignore_rules(repo_root: Path, node_ids: list[str]) -> dict[str, str]:
    """``{node_id: rule}`` for each leaf whose own summary path git ignores in ``repo_root``.

    One ``git check-ignore`` on the exact paths, so a rule naming some ids and
    not others is seen as written. ``rule`` is ``source:line:pattern``; a
    path whose deciding rule is a negation (``!pattern``) is not ignored.
    """
    paths = {summary_rel(i): i for i in node_ids}
    code, out = git_code(["check-ignore", "-v", "--no-index", *paths], repo_root) if paths else (1, "")
    found = {}
    for line in out.splitlines() if code == 0 else []:
        rule, _, path = line.partition("\t")
        if path in paths and not rule.split(":", 2)[-1].startswith("!"):
            found[paths[path]] = rule
    return found


def implementation_summary_rule(repo_root: Path, node_id: str) -> str:
    """What ``node_id``'s executor prompts say to do with its summary: ``commit`` or ``local``.

    Read in the leaf's checkout (:func:`leaf_root`). ``commit`` (configured or
    the default) becomes ``local`` when git ignores that leaf's summary path,
    so no prompt asks for a force-add.
    """
    root = leaf_root(repo_root, node_id)
    rule = _value(root, "implementation_summary") or SUMMARY_COMMIT
    if rule == SUMMARY_COMMIT and summary_ignore_rules(root, [node_id]):
        return SUMMARY_LOCAL
    return rule


def summary_rule_notice(repo_root: Path, node_ids: list[str]) -> str | None:
    """``validate``'s notice when ``implementation_summary: commit`` meets ``.gitignore`` rules ignoring the summary
    of any of ``node_ids`` (this checkout's leaves)."""
    if (_value(repo_root, "implementation_summary") or SUMMARY_COMMIT) != SUMMARY_COMMIT:
        return None
    found = summary_ignore_rules(repo_root, node_ids)
    if not found:
        return None
    named = "; ".join(f"{summary_rel(i)} ({rule})" for i, rule in sorted(found.items())[:3])
    more = f"; and {len(found) - 3} more" if len(found) > 3 else ""
    return (f"{GIT_WORKFLOW_REL.as_posix()} implementation_summary is commit (set or default), but .gitignore "
            f"ignores {len(found)} leaf summar{'y' if len(found) == 1 else 'ies'}: {named}{more}; the ignore rule "
            "wins for those leaves: their executor prompts say to leave the summary uncommitted for the review "
            "packet, never to force-add it. Set implementation_summary: local to say so, or drop the ignore rule "
            "to commit summaries.")


def warn_summary_rule(repo_root: Path, nodes: list[dict]) -> None:
    """Print :func:`summary_rule_notice` for the leaves of ``nodes`` as a stdout notice (``validate --strict``
    does not count it)."""
    parents = {n.get("parent_id") for n in nodes}
    if notice := summary_rule_notice(repo_root, [n["id"] for n in nodes if n["id"] not in parents]):
        print(f"notice: {notice}")


def summary_handling(rule: str) -> str:
    """The executor-prompt clause after "write the summary", per :func:`implementation_summary_rule`."""
    if rule == SUMMARY_LOCAL:
        return ("and leave it uncommitted (`implementation_summary: local`, or `.gitignore` ignores it): the review "
                "packet reads it from this worktree, so never force-add it. Reviewers judge it, and finish "
                "removes it from `work/`.")
    return ("and commit it on the feature branch by explicit path: reviewers judge it, and finish removes it "
            "from `work/`.")
