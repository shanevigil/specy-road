"""Load and validate ``roadmap/orchestration.yaml``: roster, review policy, substitutions.

Orchestration is part of the core contract, but the file is optional: a repo
without one gets :data:`DEFAULT_CONFIG` — one reviewer, any family, a roster of
one human — so upgrading does not strand a solo maintainer.
"""

from __future__ import annotations

import copy
import json
from datetime import date
from functools import cache
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator

from specy_road.git_subprocess import git_stdout

_PACKAGE_DIR = Path(__file__).resolve().parent
_ORCHESTRATION_SCHEMA = _PACKAGE_DIR / "templates" / "project" / "schemas" / "orchestration.schema.json"
ORCHESTRATION_REL = Path("roadmap") / "orchestration.yaml"

DEFAULT_POLICY: dict[str, Any] = {
    "reviewers_required": 1,
    "reviewers_distinct_families": False,
    "reviewer_fresh_session": True,
    "signed_reviews": False,
}
DEFAULT_CONFIG: dict[str, Any] = {
    "version": 1,
    "roster": [{"id": "human", "family": "human", "roles": ["coordinator", "reviewer"]}],
    "policy": dict(DEFAULT_POLICY),
    "substitutions": [],
}


def orchestration_yaml_path(repo_root: Path) -> Path:
    return (repo_root / ORCHESTRATION_REL).resolve()


@cache
def _schema_validator() -> Draft202012Validator:
    """Compiled once per process; the schema ships inside the wheel."""
    schema = json.loads(_ORCHESTRATION_SCHEMA.read_text(encoding="utf-8"))
    return Draft202012Validator(schema)


def validate_orchestration_dict(data: dict[str, Any]) -> str | None:
    """Return error message if invalid, else None."""
    errs = sorted(_schema_validator().iter_errors(data), key=lambda e: list(e.path))
    if not errs:
        return None
    e = errs[0]
    loc = "/".join(str(x) for x in e.path) if e.path else "(root)"
    return f"{loc}: {e.message}"


def _dates_to_iso(raw: dict[str, Any]) -> None:
    """YAML reads an unquoted ``2026-01-15`` as a date; the schema wants the string."""
    for sub in raw.get("substitutions") or []:
        if not isinstance(sub, dict):
            continue
        for key in ("decided", "expires"):
            if isinstance(sub.get(key), date):
                sub[key] = sub[key].isoformat()
    for entry in raw.get("roster") or []:
        if isinstance(entry, dict) and isinstance(entry.get("unavailable_until"), date):
            entry["unavailable_until"] = entry["unavailable_until"].isoformat()


def _semantic_error(raw: dict[str, Any]) -> str | None:
    """Rules the schema cannot express."""
    ids = [e.get("id") for e in raw.get("roster") or []]
    dupes = sorted({i for i in ids if ids.count(i) > 1})
    if dupes:
        return f"roster: duplicate id(s) {', '.join(dupes)}"
    for i, sub in enumerate(raw.get("substitutions") or []):
        if sub.get("use") not in ids:
            return (
                f"substitutions/{i}/use: {sub.get('use')!r} must be a roster entry, "
                "so its family comes from the roster and not from the review file"
            )
    return None


def parse_orchestration_text(text: str) -> tuple[dict[str, Any] | None, str | None]:
    """Parse and validate the file's text. Returns (data, parse_or_schema_error)."""
    try:
        raw = yaml.safe_load(text)
    except yaml.YAMLError as e:
        return None, f"YAML error in {ORCHESTRATION_REL}: {e}"
    if not isinstance(raw, dict):
        return None, f"{ORCHESTRATION_REL}: must be a mapping"
    _dates_to_iso(raw)
    err = validate_orchestration_dict(raw) or _semantic_error(raw)
    if err:
        return None, f"{ORCHESTRATION_REL}: {err}"
    return raw, None


def load_orchestration_config(
    repo_root: Path, ref: str | None = None
) -> tuple[dict[str, Any] | None, str | None]:
    """Load ``roadmap/orchestration.yaml`` from the working tree, or from git ``ref``.

    ``(None, None)`` means the file is absent; callers that need settings use
    :func:`effective_config` instead.
    """
    if ref is not None:
        text = git_stdout(["show", f"{ref}:{ORCHESTRATION_REL.as_posix()}"], repo_root)
        return (None, None) if text is None else parse_orchestration_text(text)
    path = orchestration_yaml_path(repo_root)
    if not path.is_file():
        return None, None
    return parse_orchestration_text(path.read_text(encoding="utf-8"))


def effective_config(repo_root: Path, ref: str | None = None) -> tuple[dict[str, Any], str | None]:
    """The file's settings with defaults filled in, or :data:`DEFAULT_CONFIG` when absent.

    ``ref`` reads the file as committed there — the review gate passes the
    integration branch, so a feature branch cannot lower its own bar. On a parse
    or schema error the error is returned with the defaults, so a caller can
    refuse (the review gate does) instead of silently relaxing.
    """
    data, err = load_orchestration_config(repo_root, ref)
    if err or data is None:
        return copy.deepcopy(DEFAULT_CONFIG), err
    out = copy.deepcopy(data)
    out["policy"] = {**DEFAULT_POLICY, **(data.get("policy") or {})}
    out.setdefault("roster", [])
    out.setdefault("substitutions", [])
    return out, None


def roster_entry(config: dict[str, Any], model_id: str) -> dict[str, Any] | None:
    for entry in config.get("roster") or []:
        if entry.get("id") == model_id:
            return entry
    return None


def family_of(config: dict[str, Any], model_id: str) -> str | None:
    entry = roster_entry(config, model_id)
    return entry.get("family") if entry else None


def is_rostered_reviewer(config: dict[str, Any], model_id: str) -> bool:
    entry = roster_entry(config, model_id)
    return bool(entry) and "reviewer" in (entry.get("roles") or [])


def active_substitutions(
    config: dict[str, Any], node_id: str, today: date | None = None
) -> list[dict[str, Any]]:
    """Substitutions that cover ``node_id``, are already decided, and have not expired."""
    day = (today or date.today()).isoformat()
    out = []
    for sub in config.get("substitutions") or []:
        scope = sub.get("scope")
        if scope is not None and node_id not in scope:
            continue
        if str(sub.get("decided", "")) > day:
            continue
        expires = sub.get("expires")
        if expires and str(expires) < day:
            continue
        out.append(sub)
    return out


def substitute_for(
    config: dict[str, Any], node_id: str, model_id: str, today: date | None = None
) -> dict[str, Any] | None:
    """The active substitution that lets ``model_id`` review ``node_id``, if any."""
    for sub in active_substitutions(config, node_id, today):
        if sub.get("use") == model_id:
            return sub
    return None
