"""Load and validate ``roadmap/git-workflow.yaml``; git compliance for CLI and PM GUI."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator

_PACKAGE_DIR = Path(__file__).resolve().parent
_GIT_WORKFLOW_SCHEMA = _PACKAGE_DIR / "templates" / "project" / "schemas" / "git-workflow.schema.json"
GIT_WORKFLOW_REL = Path("roadmap") / "git-workflow.yaml"


def git_workflow_yaml_path(repo_root: Path) -> Path:
    return (repo_root / GIT_WORKFLOW_REL).resolve()


def _schema_validator() -> Draft202012Validator:
    raw = _GIT_WORKFLOW_SCHEMA.read_text(encoding="utf-8")
    schema = json.loads(raw)
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


def merge_request_requires_manual_approval(repo_root: Path) -> bool:
    """True when ``roadmap/git-workflow.yaml`` sets ``merge_request_requires_manual_approval``."""
    data, err = load_git_workflow_config(repo_root)
    if err or not data:
        return False
    v = data.get("merge_request_requires_manual_approval")
    return v is True


def require_implementation_review_before_finish(repo_root: Path) -> bool:
    """True when ``roadmap/git-workflow.yaml`` sets ``require_implementation_review_before_finish``."""
    data, err = load_git_workflow_config(repo_root)
    if err or not data:
        return False
    v = data.get("require_implementation_review_before_finish")
    return v is True


def cleanup_work_artifacts_on_finish(repo_root: Path) -> bool:
    """True unless ``cleanup_work_artifacts_on_finish`` is explicitly false in git-workflow.yaml."""
    data, err = load_git_workflow_config(repo_root)
    if err or not data:
        return True
    v = data.get("cleanup_work_artifacts_on_finish")
    if v is False:
        return False
    return True


def should_cleanup_work_artifacts_on_finish(
    repo_root: Path,
    *,
    no_cleanup_work_cli: bool,
) -> bool:
    """Respect ``--no-cleanup-work`` over ``roadmap/git-workflow.yaml``."""
    if no_cleanup_work_cli:
        return False
    return cleanup_work_artifacts_on_finish(repo_root)


def _git_ok(args: list[str], cwd: Path) -> tuple[bool, str]:
    try:
        r = subprocess.run(
            ["git", *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        if r.returncode != 0:
            return False, (r.stderr or r.stdout or "").strip()
        return True, r.stdout.strip()
    except (OSError, subprocess.TimeoutExpired) as e:
        return False, str(e)


def is_git_worktree(repo_root: Path) -> bool:
    ok, out = _git_ok(["rev-parse", "--is-inside-work-tree"], repo_root)
    return ok and out.lower() == "true"


def current_branch_name(repo_root: Path) -> str | None:
    """Named branch checked out, or None (detached HEAD / not git)."""
    if not is_git_worktree(repo_root):
        return None
    ok, out = _git_ok(["branch", "--show-current"], repo_root)
    if ok and out.strip():
        return out.strip()
    return None


def working_tree_clean(repo_root: Path) -> bool:
    """True when ``git status --porcelain`` is empty (no staged/unstaged/untracked noise)."""
    if not is_git_worktree(repo_root):
        return False
    ok, out = _git_ok(["status", "--porcelain"], repo_root)
    if not ok:
        return False
    return not (out or "").strip()


def current_head_short_sha(repo_root: Path) -> str | None:
    if not is_git_worktree(repo_root):
        return None
    ok, sha = _git_ok(["rev-parse", "--short", "HEAD"], repo_root)
    return sha if ok else None


def git_config_user_name(repo_root: Path) -> str | None:
    """Local ``git config user.name`` for this repo (developer identity on this clone)."""
    if not is_git_worktree(repo_root):
        return None
    ok, out = _git_ok(["config", "--get", "user.name"], repo_root)
    if not ok or not (out or "").strip():
        return None
    return (out or "").strip()


def git_remote_tip_author(repo_root: Path, remote: str, branch: str) -> str | None:
    """Author name (``%an``) of the latest commit on ``refs/remotes/<remote>/<branch>``."""
    if not is_git_worktree(repo_root):
        return None
    rm = (remote or "").strip()
    br = (branch or "").strip()
    if not rm or not br:
        return None
    ref = f"refs/remotes/{rm}/{br}"
    ok, _ = _git_ok(["show-ref", "--verify", ref], repo_root)
    if not ok:
        return None
    ok2, line = _git_ok(["log", "-1", "--format=%an", ref], repo_root)
    if not ok2 or not (line or "").strip():
        return None
    return (line or "").strip()


def integration_refs_present(
    repo_root: Path,
    remote: str,
    integration_branch: str,
) -> tuple[bool, str]:
    """True if local remote-tracking ref or local branch exists for integration trunk."""
    rr = f"refs/remotes/{remote}/{integration_branch}"
    ok, _ = _git_ok(["show-ref", "--verify", rr], repo_root)
    if ok:
        return True, rr
    hb = f"refs/heads/{integration_branch}"
    ok2, _ = _git_ok(["show-ref", "--verify", hb], repo_root)
    if ok2:
        return True, hb
    return False, ""


def _optional_git_workflow_config_fields(data: dict[str, Any]) -> dict[str, Any]:
    """Optional booleans exposed in status payload (subset of schema)."""
    out: dict[str, Any] = {}
    if "merge_request_requires_manual_approval" in data:
        out["merge_request_requires_manual_approval"] = bool(
            data["merge_request_requires_manual_approval"],
        )
    if "require_implementation_review_before_finish" in data:
        out["require_implementation_review_before_finish"] = bool(
            data["require_implementation_review_before_finish"],
        )
    if "cleanup_work_artifacts_on_finish" in data:
        out["cleanup_work_artifacts_on_finish"] = bool(
            data["cleanup_work_artifacts_on_finish"],
        )
    return out


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
