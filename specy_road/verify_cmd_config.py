"""``verify_cmd`` in ``roadmap/git-workflow.yaml``: how executors and reviewers run a leaf's tests.

Several workers on one machine, each running the full suite with one test worker per core, oversubscribe
the CPU: the suite slows for everyone and a reviewer's run can outlast its harness's background-task limit.
``verify_cmd`` (e.g. ``python -m pytest -n 4 -p no:cacheprovider``) names a bounded command that executor
briefs and reviewer prompts give for the leaf's tests, with the test paths appended; ``land_check_cmd``
stays the full gate at landing. It lives here, not in :mod:`specy_road.git_workflow_config`, which is at
its line cap.
"""

from __future__ import annotations

from pathlib import Path

from specy_road.git_workflow_config import GIT_WORKFLOW_REL, load_git_workflow_config


def resolve_verify_cmd(repo_root: Path) -> str | None:
    """``verify_cmd`` from ``roadmap/git-workflow.yaml``; ``None`` when unset, blank or unreadable."""
    data, err = load_git_workflow_config(repo_root)
    cmd = (data or {}).get("verify_cmd") if not err else None
    return (cmd or "").strip() or None


def verify_cmd_lines(repo_root: Path) -> list[str]:
    """The one sentence an executor brief and a reviewer prompt carry about running the leaf's tests."""
    cmd = resolve_verify_cmd(repo_root)
    if cmd:
        line = (f"**Running tests:** run this leaf's tests with `{cmd}` followed by the test paths "
                f"(`verify_cmd` in `{GIT_WORKFLOW_REL.as_posix()}`); other workers may share this machine, "
                "and the full suite runs at landing.")
    else:
        line = ("**Running tests:** when other workers share this machine, cap parallel test workers (for "
                "example `pytest -n 4`, not `-n auto`): each full parallel suite starts one worker per core. "
                f"A project can name the command as `verify_cmd` in `{GIT_WORKFLOW_REL.as_posix()}`.")
    return [line, ""]
