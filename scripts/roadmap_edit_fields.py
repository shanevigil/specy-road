"""Whitelisted roadmap node field patches (shared by CRUD CLI and Streamlit GUI)."""

from __future__ import annotations

import re
from typing import Any

from planning_artifacts import normalize_planning_dir

ID_PATTERN = re.compile(r"^M[0-9]+(\.[0-9]+)*$")
CODENAME_PATTERN = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


def title_to_codename(title: str) -> str:
    """
    Derive a valid kebab-case codename from a human title.
    Returns '' if the title yields nothing valid (caller may omit or clear codename).
    """
    s = re.sub(r"[^a-z0-9]+", "-", (title or "").lower().strip())
    s = re.sub(r"-+", "-", s).strip("-")
    if not s or not CODENAME_PATTERN.match(s):
        return ""
    return s


EDIT_WHITELIST = frozenset({
    "status",
    "title",
    "type",
    "parent_id",
    "codename",
    "execution_milestone",
    "execution_subtask",
    "parallel_tracks",
    "notes",
    "goal",
    "dependencies",
    "touch_zones",
    "acceptance",
    "risks",
    "decision.status",
    "decision.decided_date",
    "decision.adr_ref",
    "agentic_checklist.artifact_action",
    "agentic_checklist.contract_citation",
    "agentic_checklist.interface_contract",
    "agentic_checklist.constraints_note",
    "agentic_checklist.dependency_note",
    "agentic_checklist.success_signal",
    "agentic_checklist.forbidden_patterns",
    "planning_dir",
})

NODE_TYPES = frozenset({"vision", "phase", "milestone", "task"})
EXEC_MILESTONES = frozenset({"Human-led", "Agentic-led", "Mixed"})
EXEC_SUBTASKS = frozenset({"human", "agentic", "human-gate"})
DECISION_STATUS = frozenset({"pending", "decided"})


def _parse_dependency_tokens(raw: str, all_ids: set[str]) -> list[str]:
    parts = re.split(r"[\s,;]+", raw.strip())
    out: list[str] = []
    for p in parts:
        if not p:
            continue
        if not ID_PATTERN.match(p):
            raise ValueError(f"invalid dependency id {p!r}")
        if p not in all_ids:
            raise ValueError(f"dependency {p!r} is not an existing node id")
        out.append(p)
    return out


def _parse_touch_zone_lines(raw: str) -> list[str]:
    lines = [ln.strip() for ln in raw.replace(",", "\n").splitlines()]
    return [x for x in lines if x]


def _nonempty_lines(raw: str) -> list[str]:
    return [ln.strip() for ln in raw.splitlines() if ln.strip()]


def _set_type(node: dict, raw_val: str) -> None:
    if raw_val not in NODE_TYPES:
        raise ValueError(f"type must be one of: {sorted(NODE_TYPES)}")
    node["type"] = raw_val


def _set_parent_id(
    node: dict, raw_val: str, *, all_ids: set[str], self_id: str
) -> None:
    if raw_val.strip().lower() in ("", "null", "~"):
        node["parent_id"] = None
        return
    pid = raw_val.strip()
    if pid == self_id:
        raise ValueError("parent_id cannot equal the node's own id")
    if pid not in all_ids:
        raise ValueError(f"parent_id {pid!r} is not an existing node id")
    node["parent_id"] = pid


def _set_planning_dir(node: dict, raw_val: str) -> None:
    if raw_val.lower() in ("null", "~", ""):
        node.pop("planning_dir", None)
        return
    node["planning_dir"] = normalize_planning_dir(raw_val.strip())


def _set_codename(node: dict, raw_val: str) -> None:
    if raw_val.lower() in ("null", "~", ""):
        node["codename"] = None
    elif not CODENAME_PATTERN.match(raw_val.strip()):
        raise ValueError(f"invalid codename: {raw_val!r}")
    else:
        node["codename"] = raw_val.strip()


def _set_exec_milestone(node: dict, raw_val: str) -> None:
    if raw_val.lower() in ("null", "~", ""):
        node["execution_milestone"] = None
    elif raw_val not in EXEC_MILESTONES:
        raise ValueError(
            f"execution_milestone must be one of {sorted(EXEC_MILESTONES)} or empty",
        )
    else:
        node["execution_milestone"] = raw_val


def _set_exec_subtask(node: dict, raw_val: str) -> None:
    if raw_val.lower() in ("null", "~", ""):
        node["execution_subtask"] = None
    elif raw_val not in EXEC_SUBTASKS:
        raise ValueError(
            f"execution_subtask must be one of {sorted(EXEC_SUBTASKS)} or empty",
        )
    else:
        node["execution_subtask"] = raw_val


def _apply_scalar_top_level(
    node: dict,
    key: str,
    raw_val: str,
    *,
    all_ids: set[str],
    self_id: str,
) -> None:
    if key == "type":
        _set_type(node, raw_val)
    elif key == "parent_id":
        _set_parent_id(node, raw_val, all_ids=all_ids, self_id=self_id)
    elif key == "dependencies":
        node["dependencies"] = _parse_dependency_tokens(raw_val, all_ids)
    elif key == "touch_zones":
        node["touch_zones"] = _parse_touch_zone_lines(raw_val)
    elif key == "acceptance":
        if not raw_val.strip():
            node.pop("acceptance", None)
        else:
            node["acceptance"] = _nonempty_lines(raw_val)
    elif key == "risks":
        if not raw_val.strip():
            node.pop("risks", None)
        else:
            node["risks"] = _nonempty_lines(raw_val)
    elif key == "parallel_tracks":
        try:
            node["parallel_tracks"] = int(raw_val)
        except ValueError as e:
            raise ValueError(
                f"parallel_tracks must be an integer, got {raw_val!r}",
            ) from e
    elif key == "planning_dir":
        _set_planning_dir(node, raw_val)
    elif key == "codename":
        _set_codename(node, raw_val)
    elif key == "execution_milestone":
        _set_exec_milestone(node, raw_val)
    elif key == "execution_subtask":
        _set_exec_subtask(node, raw_val)
    else:
        node[key] = raw_val


def _apply_decision(node: dict, sub: str, raw_val: str) -> None:
    dec = node.get("decision")
    if not isinstance(dec, dict):
        dec = {}
        node["decision"] = dec
    if sub == "status":
        if raw_val not in DECISION_STATUS:
            raise ValueError(
                f"decision.status must be one of {sorted(DECISION_STATUS)}",
            )
        dec["status"] = raw_val
    else:
        dec[sub] = raw_val


def _apply_agentic_sub(node: dict, sub: str, raw_val: str) -> None:
    ac = node.get("agentic_checklist")
    if not isinstance(ac, dict):
        ac = {}
        node["agentic_checklist"] = ac
    if sub in ("success_signal", "forbidden_patterns") and not raw_val.strip():
        ac.pop(sub, None)
    else:
        ac[sub] = raw_val


def apply_set(
    node: dict[str, Any],
    dotted_key: str,
    raw_val: str,
    *,
    all_ids: set[str],
    self_id: str,
) -> None:
    if dotted_key not in EDIT_WHITELIST:
        raise ValueError(f"key not allowed for --set: {dotted_key!r}")
    parts = dotted_key.split(".")
    if len(parts) == 1:
        _apply_scalar_top_level(
            node, parts[0], raw_val, all_ids=all_ids, self_id=self_id,
        )
        return
    if parts[0] == "decision" and len(parts) == 2:
        _apply_decision(node, parts[1], raw_val)
        return
    if parts[0] == "agentic_checklist" and len(parts) == 2:
        _apply_agentic_sub(node, parts[1], raw_val)
        return
    raise ValueError(f"unsupported nested key: {dotted_key!r}")
