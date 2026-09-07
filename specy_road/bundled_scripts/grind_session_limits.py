"""Where grind-session's implement bounds come from.

CLI flag > ``roadmap/git-workflow.yaml`` > the module defaults. Kept apart from
the loop itself so the loop file stays inside its line budget, and so the
precedence is testable without building an argparse namespace.
"""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from specy_road.bundled_scripts.grind_session_implement import ImplementLimits
from specy_road.git_workflow_config import load_git_workflow_config


#: ``git-workflow.yaml`` key -> :class:`ImplementLimits` field.
_YAML_LIMIT_KEYS = {
    "grind_session_max_limit_waits": "max_resumes",
    "grind_session_max_limit_wait_hours": "max_wait_seconds",
    "grind_session_limit_wait_grace_seconds": "grace_seconds",
    "grind_session_max_empty_retries": "max_empty_retries",
}


def _limits_from_git_workflow(repo_root: Path) -> dict[str, int]:
    """Bounds set in ``roadmap/git-workflow.yaml``, if any.

    An unreadable or schema-invalid file yields nothing, exactly as the
    boolean settings behave. grind-session cannot reach this step with a broken
    file anyway: ``on_complete`` resolution reads the same file first and
    refuses to start the loop.
    """
    data, err = load_git_workflow_config(repo_root)
    if err or not data:
        return {}
    out: dict[str, int] = {}
    for key, field in _YAML_LIMIT_KEYS.items():
        value = data.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        out[field] = int(value * 3600) if field == "max_wait_seconds" else int(value)
    return out


def resolve_implement_limits(
    repo_root: Path,
    *,
    max_limit_waits: int | None = None,
    max_limit_wait_hours: float | None = None,
    limit_wait_grace_seconds: int | None = None,
    max_empty_retries: int | None = None,
) -> ImplementLimits:
    """Bounds for the implement step: CLI flag > git-workflow.yaml > default.

    Hours in, seconds out. A person quotes a reset in hours and so does the
    loop's own refusal message, while every comparison inside the loop is in
    seconds.
    """
    values: dict[str, int] = asdict(ImplementLimits.defaults())
    values.update(_limits_from_git_workflow(repo_root))
    cli = {
        "max_resumes": max_limit_waits,
        "max_wait_seconds": (
            None if max_limit_wait_hours is None else int(max_limit_wait_hours * 3600)
        ),
        "grace_seconds": limit_wait_grace_seconds,
        "max_empty_retries": max_empty_retries,
    }
    values.update({k: v for k, v in cli.items() if v is not None})
    return ImplementLimits(**{k: max(0, int(v)) for k, v in values.items()})
