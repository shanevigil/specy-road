"""Load and validate ``roadmap/orchestration.yaml``: roster, review policy, substitutions.

Orchestration is part of the core contract, but the file is optional: a repo
without one gets :data:`DEFAULT_CONFIG` — one reviewer, any family, a roster of
one human — so upgrading does not strand a solo maintainer.
"""

from __future__ import annotations

import copy
import json
from datetime import date, datetime
from functools import cache
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator

from specy_road.git_subprocess import git_stdout
from specy_road.schema_revision import accepted_at_revision

_PACKAGE_DIR = Path(__file__).resolve().parent
_ORCHESTRATION_SCHEMA = _PACKAGE_DIR / "templates" / "project" / "schemas" / "orchestration.schema.json"
ORCHESTRATION_REL = Path("roadmap") / "orchestration.yaml"
ORCHESTRATION_LOCAL_REL = Path("roadmap") / "orchestration.local.yaml"
AVAILABILITY_OVERLAY_KEYS = frozenset({"available", "paused_until", "unavailable_until"})

DEFAULT_POLICY: dict[str, Any] = {
    "reviewers_required": 1,
    "reviewers_distinct_families": False,
    "reviewer_fresh_session": True,
    "signed_reviews": False,
    "reviewer_reruns_required": False,
    "max_workers": 2,
    "escalate_same_acceptance_blocks": 3,
    "escalate_review_rounds": 5,
    "stall_after_seconds": 600,
    "milestone_full_review": True,
    "delta_review": True,
    "reviewer_resumed_delta": False,
}
DEFAULT_CONFIG: dict[str, Any] = {
    "version": 1,
    "roster": [{"id": "human", "family": "human", "roles": ["coordinator", "reviewer"]}],
    "policy": dict(DEFAULT_POLICY),
    "substitutions": [],
}


def orchestration_yaml_path(repo_root: Path) -> Path:
    return (repo_root / ORCHESTRATION_REL).resolve()


def orchestration_local_path(repo_root: Path) -> Path:
    return (repo_root / ORCHESTRATION_LOCAL_REL).resolve()


@cache
def _schema_validator() -> Draft202012Validator:
    """Compiled once per process; the schema ships inside the wheel."""
    schema = json.loads(_ORCHESTRATION_SCHEMA.read_text(encoding="utf-8"))
    return Draft202012Validator(schema)


def validate_orchestration_dict(data: dict[str, Any], repo_root: Path | None = None,
                                rev: str | None = None) -> str | None:
    """Return error message if invalid, else None.

    With ``repo_root``, the file was read at ``rev`` (the working tree when
    ``None``), and the schema as a specy-road checkout has it there counts too:
    a leaf that adds a policy key is valid against its own schema.
    """
    errs = sorted(_schema_validator().iter_errors(data), key=lambda e: list(e.path))
    sub = _ORCHESTRATION_SCHEMA.relative_to(_PACKAGE_DIR).as_posix()
    if not errs or repo_root is not None and accepted_at_revision(data, sub, repo_root, rev):
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
        if not isinstance(entry, dict):
            continue
        for key in ("unavailable_until", "paused_until"):
            if isinstance(entry.get(key), date):
                entry[key] = entry[key].isoformat()
            elif isinstance(entry.get(key), datetime):
                entry[key] = entry[key].replace(microsecond=0).isoformat()


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
    return _date_error(raw)


def _paused_until_error(loc: str, val: Any) -> str | None:
    if val is None:
        return None
    s = str(val)
    if len(s) == 10:
        try:
            date.fromisoformat(s)
        except ValueError:
            return f"{loc}: {val!r} is not a calendar date (YYYY-MM-DD)"
        return None
    try:
        datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return f"{loc}: {val!r} is not a date or datetime"
    return None


def _date_error(raw: dict[str, Any]) -> str | None:
    """The schema's ``\\d{4}-\\d{2}-\\d{2}`` admits ``2026-00-00``; these fields are compared as dates."""
    fields = [(f"roster/{i}/unavailable_until", e.get("unavailable_until"))
              for i, e in enumerate(raw.get("roster") or []) if isinstance(e, dict)]
    fields += [(f"roster/{i}/paused_until", e.get("paused_until"))
               for i, e in enumerate(raw.get("roster") or []) if isinstance(e, dict)]
    fields += [(f"substitutions/{i}/{k}", s.get(k))
               for i, s in enumerate(raw.get("substitutions") or []) if isinstance(s, dict)
               for k in ("decided", "expires")]
    for loc, val in fields:
        if loc.endswith("paused_until"):
            if err := _paused_until_error(loc, val):
                return err
            continue
        if val is None:
            continue
        try:
            date.fromisoformat(str(val))
        except ValueError:
            return f"{loc}: {val!r} is not a calendar date (YYYY-MM-DD)"
    return None


def load_availability_overlay(repo_root: Path) -> tuple[dict[str, dict[str, Any]] | None, str | None]:
    """``roadmap/orchestration.local.yaml``: local roster availability overrides, not committed."""
    path = orchestration_local_path(repo_root)
    if not path.is_file():
        return None, None
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (yaml.YAMLError, ValueError) as e:
        return None, f"YAML error in {ORCHESTRATION_LOCAL_REL}: {e}"
    if raw is None:
        return {}, None
    if not isinstance(raw, dict):
        return None, f"{ORCHESTRATION_LOCAL_REL}: must be a mapping"
    roster = raw.get("roster")
    if roster is None:
        return {}, None
    if not isinstance(roster, list):
        return None, f"{ORCHESTRATION_LOCAL_REL}: roster must be a list"
    out: dict[str, dict[str, Any]] = {}
    for i, entry in enumerate(roster):
        if not isinstance(entry, dict):
            return None, f"{ORCHESTRATION_LOCAL_REL}: roster/{i} must be a mapping"
        rid = entry.get("id")
        if not rid:
            return None, f"{ORCHESTRATION_LOCAL_REL}: roster/{i}/id is required"
        patch = {k: entry[k] for k in AVAILABILITY_OVERLAY_KEYS if k in entry}
        if not patch:
            continue
        if "available" in patch and not isinstance(patch["available"], bool):
            return None, f"{ORCHESTRATION_LOCAL_REL}: roster/{i}/available must be true or false"
        _dates_to_iso({"roster": [patch]})
        for key in ("paused_until", "unavailable_until"):
            if err := _paused_until_error(f"{ORCHESTRATION_LOCAL_REL}/roster/{i}/{key}", patch.get(key)):
                return None, err
        out[str(rid)] = patch
    return out, None


def apply_availability_overlay(config: dict[str, Any], overlay: dict[str, dict[str, Any]] | None) -> None:
    """Merge overlay fields onto committed roster entries by ``id`` (in place)."""
    if not overlay:
        return
    by_id = {str(e.get("id")): e for e in config.get("roster") or [] if e.get("id")}
    for rid, patch in overlay.items():
        entry = by_id.get(rid)
        if entry is None:
            continue
        for key, val in patch.items():
            if val is None:
                entry.pop(key, None)
            else:
                entry[key] = val


def parse_orchestration_text(text: str, repo_root: Path | None = None,
                             rev: str | None = None) -> tuple[dict[str, Any] | None, str | None]:
    """Parse and validate the file's text, read at ``rev`` of ``repo_root`` when given
    (:func:`validate_orchestration_dict`). Returns (data, parse_or_schema_error)."""
    try:
        raw = yaml.safe_load(text)
    except (yaml.YAMLError, ValueError) as e:   # ValueError: an impossible date such as 2026-00-00
        return None, f"YAML error in {ORCHESTRATION_REL}: {e}"
    if not isinstance(raw, dict):
        return None, f"{ORCHESTRATION_REL}: must be a mapping"
    _dates_to_iso(raw)
    err = validate_orchestration_dict(raw, repo_root, rev) or _semantic_error(raw)
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
        text = git_stdout(["show", f"{ref}:./{ORCHESTRATION_REL.as_posix()}"], repo_root)   # ./ = project-root relative
        return (None, None) if text is None else parse_orchestration_text(text, repo_root, ref)
    path = orchestration_yaml_path(repo_root)
    if not path.is_file():
        return None, None
    return parse_orchestration_text(path.read_text(encoding="utf-8"), repo_root)


def effective_config(repo_root: Path, ref: str | None = None) -> tuple[dict[str, Any], str | None]:
    """The file's settings with defaults filled in, or :data:`DEFAULT_CONFIG` when absent.

    ``ref`` reads the file as committed there — the review gate passes the
    integration branch, so a feature branch cannot lower its own bar. On a parse
    or schema error the error is returned with the defaults, so a caller can
    refuse (the review gate does) instead of silently relaxing.
    """
    data, err = load_orchestration_config(repo_root, ref)
    if err:
        return copy.deepcopy(DEFAULT_CONFIG), err
    if data is None:
        out = copy.deepcopy(DEFAULT_CONFIG)
    else:
        out = copy.deepcopy(data)
        out["policy"] = {**DEFAULT_POLICY, **(data.get("policy") or {})}
        out.setdefault("roster", [])
        out.setdefault("substitutions", [])
    overlay, overlay_err = load_availability_overlay(repo_root)
    if overlay_err:
        return copy.deepcopy(DEFAULT_CONFIG), overlay_err
    apply_availability_overlay(out, overlay)
    return out, None


def roster_entry(config: dict[str, Any], model_id: str) -> dict[str, Any] | None:
    for entry in config.get("roster") or []:
        if entry.get("id") == model_id:
            return entry
    return None


def harness_model(entry: dict[str, Any], profile_api_id: str | None = None) -> str | None:
    """The model id a harness is told for roster ``entry``: its ``harness_model``, else the profile's ``api_id``,
    else the roster ``id``. ``None`` (a profile whose ``api_id`` is ``unknown``) means the harness's default."""
    if entry.get("harness_model"):
        return str(entry["harness_model"])
    if profile_api_id is not None:
        return None if profile_api_id.strip().lower() in ("", "unknown") else profile_api_id
    return str(entry["id"])


def harness_model_warnings(config: dict[str, Any]) -> list[str]:
    """Claude Code entries whose ``id`` has a dot and no ``harness_model``: ``claude --model`` ids use dashes."""
    return [f"roster entry {e.get('id')!r} runs on claude-code and its id has a dot; set harness_model to the id "
            "`claude --model` expects (e.g. claude-opus-5-5), or the default command may pass an unknown model"
            for e in config.get("roster") or []
            if e.get("harness") == "claude-code" and "." in str(e.get("id")) and not e.get("harness_model")]


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
