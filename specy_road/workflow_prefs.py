"""Project preferences in ``roadmap/git-workflow.yaml`` that the workflow respects (M15.22).

- ``pr_body_footer``: text finish-this-task appends to the PR body it writes.
- ``implementation_summary``: ``commit`` (default) or ``local``; whether
  executor prompts say to commit ``work/implementation-summary-<ID>.md`` or to
  leave it uncommitted for the review packet to read from the worktree. A
  ``.gitignore`` rule that ignores the summary wins over ``commit``: prompts never
  tell a worker to force-add an ignored path, and ``validate`` says so.
- ``land``: ``push`` (default) or ``local``; how merge mode lands the root
  repository (:mod:`specy_road.finish_land_local`).

See ``docs/git-workflow-preferences.md``. An unreadable config yields each
default, as :func:`specy_road.git_workflow_config._flag` does for booleans.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from specy_road.git_subprocess import git_code
from specy_road.git_workflow_config import GIT_WORKFLOW_REL, load_git_workflow_config

SUMMARY_COMMIT, SUMMARY_LOCAL = "commit", "local"
LAND_PUSH, LAND_LOCAL = "push", "local"
#: Stands for any leaf's summary when asking git whether summaries are ignored.
_SAMPLE_SUMMARY = "work/implementation-summary-M0.md"


def _value(repo_root: Path, key: str) -> Any:
    data, err = load_git_workflow_config(repo_root)
    return None if err or not data else data.get(key)


def pr_body_footer(repo_root: Path) -> str | None:
    """``pr_body_footer`` stripped, or ``None`` when unset; the schema refuses an empty or whitespace-only one."""
    text = _value(repo_root, "pr_body_footer")
    return text.strip() if text else None


def root_land(repo_root: Path) -> str:
    """``land`` for the root repository: ``push`` (default) or ``local``."""
    return _value(repo_root, "land") or LAND_PUSH


def summary_ignore_rule(repo_root: Path) -> str | None:
    """The ``.gitignore`` rule (``source:line:pattern``) that ignores implementation summaries, or ``None``."""
    code, out = git_code(["check-ignore", "-v", "--no-index", _SAMPLE_SUMMARY], repo_root)
    rule = out.split("\t", 1)[0].strip() if code == 0 else ""
    return rule if rule and not rule.split(":", 2)[-1].startswith("!") else None


def implementation_summary_rule(repo_root: Path) -> str:
    """What executor prompts say to do with the summary: ``commit`` or ``local``.

    ``commit`` (the configured value or the default) becomes ``local`` when git
    ignores the summary, so no prompt asks for a force-add.
    """
    rule = _value(repo_root, "implementation_summary") or SUMMARY_COMMIT
    if rule == SUMMARY_COMMIT and summary_ignore_rule(repo_root):
        return SUMMARY_LOCAL
    return rule


def summary_rule_notice(repo_root: Path) -> str | None:
    """``validate``'s notice when ``implementation_summary: commit`` meets a ``.gitignore`` that ignores summaries."""
    if (_value(repo_root, "implementation_summary") or SUMMARY_COMMIT) != SUMMARY_COMMIT:
        return None
    rule = summary_ignore_rule(repo_root)
    if rule is None:
        return None
    return (f"{GIT_WORKFLOW_REL.as_posix()} implementation_summary is commit (set or default), but .gitignore "
            f"ignores work/implementation-summary-*.md ({rule}); the ignore rule wins: executor prompts say to "
            "leave the summary uncommitted for the review packet, never to force-add it. Set "
            "implementation_summary: local to say so, or drop the ignore rule to commit summaries.")


def warn_summary_rule(repo_root: Path) -> None:
    """Print :func:`summary_rule_notice` as a stdout notice (``validate --strict`` does not count it)."""
    if notice := summary_rule_notice(repo_root):
        print(f"notice: {notice}")


def summary_handling(rule: str) -> str:
    """The executor-prompt clause after "write the summary", per :func:`implementation_summary_rule`."""
    if rule == SUMMARY_LOCAL:
        return ("and leave it uncommitted (`implementation_summary: local`, or `.gitignore` ignores it): the review "
                "packet reads it from this worktree, so never force-add it. Reviewers judge it, and finish "
                "removes it from `work/`.")
    return ("and commit it on the feature branch by explicit path: reviewers judge it, and finish removes it "
            "from `work/`.")
