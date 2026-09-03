"""Load and validate ``roadmap/git-workflow.yaml``; git compliance for CLI and PM GUI."""

from __future__ import annotations

import json
import os
from functools import cache
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator

from specy_road.git_subprocess import current_branch_name, git_ok, is_git_worktree

_PACKAGE_DIR = Path(__file__).resolve().parent
_GIT_WORKFLOW_SCHEMA = _PACKAGE_DIR / "templates" / "project" / "schemas" / "git-workflow.schema.json"
GIT_WORKFLOW_REL = Path("roadmap") / "git-workflow.yaml"

# finish-this-task / do-next: how to land completed work (PR/MR vs local merge).
ON_COMPLETE_MODES = frozenset({"auto", "merge", "pr"})
DEFAULT_ON_COMPLETE = "pr"


def git_workflow_yaml_path(repo_root: Path) -> Path:
    return (repo_root / GIT_WORKFLOW_REL).resolve()


@cache
def _schema_validator() -> Draft202012Validator:
    """The compiled git-workflow validator.

    Cached because it was rebuilt -- schema file read, JSON parsed, validator
    compiled -- on *every* ``load_git_workflow_config``, which finish-this-task
    and do-next-available-task each call five times per run. The schema ships
    inside the wheel, so it cannot change while the process is alive.
    """
    schema = json.loads(_GIT_WORKFLOW_SCHEMA.read_text(encoding="utf-8"))
    return Draft202012Validator(schema)


def validate_git_workflow_dict(data: dict[str, Any]) -> str | None:
    """Return error message if invalid, else None."""
    v = _schema_validator()
    errs = sorted(v.iter_errors(data), key=lambda e: e.path)
    if not errs:
        return None
    e = errs[0]
    loc = "/".join(str(x) for x in e.path) if e.path else "(root)"
    return f"{loc}: {e.message}"


def load_git_workflow_config(repo_root: Path) -> tuple[dict[str, Any] | None, str | None]:
    """Load YAML from ``roadmap/git-workflow.yaml``. Returns (data, parse_or_schema_error)."""
    path = git_workflow_yaml_path(repo_root)
    if not path.is_file():
        return None, None
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        return None, f"YAML error in {GIT_WORKFLOW_REL}: {e}"
    if not isinstance(raw, dict):
        return None, f"{GIT_WORKFLOW_REL}: must be a mapping"
    err = validate_git_workflow_dict(raw)
    if err:
        return None, f"{GIT_WORKFLOW_REL}: {err}"
    return raw, None


def resolve_integration_defaults(
    repo_root: Path,
    *,
    explicit_base: str | None,
    explicit_remote: str | None,
) -> tuple[str, str, list[str]]:
    """Resolve integration branch and remote. Returns (base, remote, warnings)."""
    warnings: list[str] = []
    env_base = os.environ.get("SPECY_ROAD_INTEGRATION_BRANCH", "").strip()
    env_remote = os.environ.get("SPECY_ROAD_REMOTE", "").strip()
    base = explicit_base or env_base or None
    remote = explicit_remote or env_remote or None
    if base is None or remote is None:
        data, err = load_git_workflow_config(repo_root)
        if err:
            warnings.append(
                f"Could not load {GIT_WORKFLOW_REL}: {err}; using CLI defaults.",
            )
            data = None
        if base is None:
            base = (data or {}).get("integration_branch") if data else None
        if remote is None:
            remote = (data or {}).get("remote") if data else None
    if base is None:
        base = "main"
        if not git_workflow_yaml_path(repo_root).is_file():
            warnings.append(
                f"No {GIT_WORKFLOW_REL}; using integration branch {base!r}. "
                "Add the file (see specy-road init project template) to record your trunk.",
            )
    if remote is None:
        remote = "origin"
    return base, remote, warnings


def _flag(repo_root: Path, key: str, *, default: bool) -> bool:
    """A boolean from ``roadmap/git-workflow.yaml``, or ``default``.

    An unreadable config yields the default, so a repo without one behaves as
    if every flag were unset.
    """
    data, err = load_git_workflow_config(repo_root)
    if err or not data:
        return default
    v = data.get(key)
    return default if v is None else bool(v)


def merge_request_requires_manual_approval(repo_root: Path) -> bool:
    """True when ``roadmap/git-workflow.yaml`` opts into manual MR approval."""
    return _flag(repo_root, "merge_request_requires_manual_approval", default=False)


def require_implementation_review_before_finish(repo_root: Path) -> bool:
    """True when finishing a task requires an implementation review first."""
    return _flag(repo_root, "require_implementation_review_before_finish", default=False)


def cleanup_work_artifacts_on_finish(repo_root: Path) -> bool:
    """True unless ``cleanup_work_artifacts_on_finish`` is explicitly false."""
    return _flag(repo_root, "cleanup_work_artifacts_on_finish", default=True)


def should_cleanup_work_artifacts_on_finish(
    repo_root: Path,
    *,
    no_cleanup_work_cli: bool,
) -> bool:
    """Respect ``--no-cleanup-work`` over ``roadmap/git-workflow.yaml``."""
    if no_cleanup_work_cli:
        return False
    return cleanup_work_artifacts_on_finish(repo_root)


def on_complete_from_git_workflow(repo_root: Path) -> str:
    """``on_complete`` from ``roadmap/git-workflow.yaml``; default ``pr`` if missing or invalid."""
    data, err = load_git_workflow_config(repo_root)
    if err or not data:
        return DEFAULT_ON_COMPLETE
    v = data.get("on_complete")
    if isinstance(v, str) and v in ON_COMPLETE_MODES:
        return v
    return DEFAULT_ON_COMPLETE


def resolve_on_complete(
    repo_root: Path,
    *,
    cli: str | None,
    session: str | None,
) -> str:
    """
    Effective mode for ``finish-this-task``.

    Precedence: CLI ``--on-complete`` > session file > ``SPECY_ROAD_ON_COMPLETE`` >
    ``roadmap/git-workflow.yaml`` > ``pr``.
    """
    if cli and cli in ON_COMPLETE_MODES:
        return cli
    if session and session in ON_COMPLETE_MODES:
        return session
    env = os.environ.get("SPECY_ROAD_ON_COMPLETE", "").strip()
    if env in ON_COMPLETE_MODES:
        return env
    return on_complete_from_git_workflow(repo_root)


def current_head_short_sha(repo_root: Path) -> str | None:
    if not is_git_worktree(repo_root):
        return None
    ok, sha = git_ok(["rev-parse", "--short", "HEAD"], repo_root)
    return sha if ok else None


def git_config_user_name(repo_root: Path) -> str | None:
    """Local ``git config user.name`` for this repo (developer identity on this clone)."""
    if not is_git_worktree(repo_root):
        return None
    ok, out = git_ok(["config", "--get", "user.name"], repo_root)
    if not ok or not (out or "").strip():
        return None
    return (out or "").strip()


def _tip_author(repo_root: Path, ref: str) -> str | None:
    """Author (``%an``) of the tip of ``ref``, when that ref exists."""
    if not is_git_worktree(repo_root):
        return None
    ok, _ = git_ok(["show-ref", "--verify", ref], repo_root)
    if not ok:
        return None
    ok2, line = git_ok(["log", "-1", "--format=%an", ref], repo_root)
    return (line or "").strip() or None if ok2 else None


def git_remote_tip_author(repo_root: Path, remote: str, branch: str) -> str | None:
    """Author name (``%an``) of the latest commit on ``refs/remotes/<remote>/<branch>``."""
    rm = (remote or "").strip()
    br = (branch or "").strip()
    if not rm or not br:
        return None
    return _tip_author(repo_root, f"refs/remotes/{rm}/{br}")


def git_local_branch_tip_author(repo_root: Path, branch: str) -> str | None:
    """Latest commit author (%an) on ``refs/heads/<branch>`` when that ref exists."""
    br = (branch or "").strip()
    if not br:
        return None
    return _tip_author(repo_root, f"refs/heads/{br}")


def git_branch_tip_author(repo_root: Path, remote: str, branch: str) -> str | None:
    """Remote-tracking tip author, else local ``refs/heads/<branch>`` tip author."""
    a = git_remote_tip_author(repo_root, remote, branch)
    if a:
        return a
    return git_local_branch_tip_author(repo_root, branch)


def integration_refs_present(
    repo_root: Path,
    remote: str,
    integration_branch: str,
) -> tuple[bool, str]:
    """True if local remote-tracking ref or local branch exists for integration trunk."""
    rr = f"refs/remotes/{remote}/{integration_branch}"
    ok, _ = git_ok(["show-ref", "--verify", rr], repo_root)
    if ok:
        return True, rr
    hb = f"refs/heads/{integration_branch}"
    ok2, _ = git_ok(["show-ref", "--verify", hb], repo_root)
    if ok2:
        return True, hb
    return False, ""


#: Optional config fields echoed in the status payload, with how to coerce each.
_STATUS_FIELDS: tuple[tuple[str, type], ...] = (
    ("merge_request_requires_manual_approval", bool),
    ("require_implementation_review_before_finish", bool),
    ("cleanup_work_artifacts_on_finish", bool),
    ("on_complete", str),
)


def _optional_git_workflow_config_fields(data: dict[str, Any]) -> dict[str, Any]:
    """Optional fields exposed in the status payload (subset of schema)."""
    return {
        key: kind(data[key])
        for key, kind in _STATUS_FIELDS
        if key in data and (kind is not str or isinstance(data[key], str))
    }


def build_git_workflow_status(repo_root: Path) -> dict[str, Any]:
    """Payload for ``GET /api/git-workflow-status`` and CLI hints."""
    issues: list[dict[str, str]] = []
    config: dict[str, Any] | None = None
    path = git_workflow_yaml_path(repo_root)

    branch_current = current_branch_name(repo_root)
    head_short = current_head_short_sha(repo_root)
    git_user_name = git_config_user_name(repo_root)

    if not path.is_file():
        issues.append(
            {
                "code": "missing_config_file",
                "message": f"Missing {GIT_WORKFLOW_REL}",
                "detail": "Copy the template from specy-road init project or add version, integration_branch, and remote.",
            },
        )
    else:
        data, err = load_git_workflow_config(repo_root)
        if err:
            issues.append(
                {
                    "code": "invalid_config",
                    "message": "Invalid git workflow file",
                    "detail": err,
                },
            )
        else:
            assert data is not None
            config = {
                "version": data["version"],
                "integration_branch": data["integration_branch"],
                "remote": data["remote"],
                **_optional_git_workflow_config_fields(data),
            }

    if not is_git_worktree(repo_root):
        issues.append(
            {
                "code": "not_git_repo",
                "message": "Not a git repository",
                "detail": f"Directory {repo_root} is not a git worktree; branch status unavailable.",
            },
        )

    ib = config["integration_branch"] if config else "main"
    rm = config["remote"] if config else "origin"
    if is_git_worktree(repo_root) and config:
        ok_ref, _which = integration_refs_present(repo_root, rm, ib)
        if not ok_ref:
            issues.append(
                {
                    "code": "integration_ref_missing",
                    "message": f"No local ref for {rm}/{ib}",
                    "detail": f"Run: git fetch {rm}  — or create/checkout branch {ib!r} locally.",
                },
            )

    ok = len(issues) == 0

    return {
        "ok": ok,
        "config": config,
        "issues": issues,
        "resolved": {
            "integration_branch": ib,
            "remote": rm,
            "git_branch_current": branch_current,
            "git_head_short": head_short,
            "git_user_name": git_user_name,
        },
    }
