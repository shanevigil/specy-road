"""Remote registry overlay merge and fingerprint helpers."""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

import yaml

from specy_road.git_subprocess import git_ok
from specy_road.git_workflow_config import (
    is_git_worktree,
    load_git_workflow_config,
    resolve_integration_defaults,
)
from specy_road.pm_integration_registry import (
    remote_registry_overlay_fingerprint_addendum as remote_feature_refs_fingerprint_addendum,
)

REGISTRY_REL = Path("roadmap") / "registry.yaml"
DEFAULT_MAX_REFS = 48
DEFAULT_TOTAL_BUDGET_S = 5.0
PER_SHOW_TIMEOUT_S = 4.0


def _max_refs() -> int:
    raw = os.environ.get("SPECY_ROAD_GUI_REGISTRY_REMOTE_OVERLAY_MAX_REFS", "").strip()
    if not raw:
        return DEFAULT_MAX_REFS
    try:
        n = int(raw, 10)
        return max(1, min(n, 256))
    except ValueError:
        return DEFAULT_MAX_REFS


def _total_budget_s() -> float:
    raw = os.environ.get(
        "SPECY_ROAD_GUI_REGISTRY_REMOTE_OVERLAY_BUDGET_S",
        "",
    ).strip()
    if not raw:
        return DEFAULT_TOTAL_BUDGET_S
    try:
        return max(0.5, min(float(raw), 60.0))
    except ValueError:
        return DEFAULT_TOTAL_BUDGET_S


def resolve_git_remote(repo_root: Path) -> str:
    data, _ = load_git_workflow_config(repo_root)
    if isinstance(data, dict):
        rm = data.get("remote")
        if isinstance(rm, str) and rm.strip():
            return rm.strip()
    return "origin"


def list_remote_feature_rm_refs(repo_root: Path, remote: str) -> list[str]:
    rm = (remote or "").strip()
    if not rm or not is_git_worktree(repo_root):
        return []
    pattern = f"refs/remotes/{rm}/feature/rm-*"
    ok, out = git_ok(
        ["for-each-ref", "--format=%(refname)", pattern],
        repo_root,
        60.0,
    )
    if not ok:
        return []
    return sorted({ln.strip() for ln in out.splitlines() if ln.strip()})


def read_registry_at_ref(
    repo_root: Path,
    ref: str,
    timeout: float,
) -> dict[str, Any] | None:
    spec = f"{ref}:{REGISTRY_REL.as_posix()}"
    ok, blob = git_ok(["show", spec], repo_root, timeout)
    if not ok or not blob.strip():
        return None
    try:
        raw = yaml.safe_load(blob)
    except yaml.YAMLError:
        return None
    if not isinstance(raw, dict):
        return None
    return raw


def _normalize_entries(doc: dict[str, Any]) -> list[dict[str, Any]]:
    entries = doc.get("entries")
    if not isinstance(entries, list):
        return []
    out: list[dict[str, Any]] = []
    for e in entries:
        if isinstance(e, dict) and e.get("node_id"):
            out.append(e)
    return out


def _append_remote_registry_entries(
    doc: dict[str, Any] | None,
    head_ids: set[str],
    merged_entries: list[dict[str, Any]],
    seen_remote_nodes: set[str],
) -> int:
    if doc is None:
        return 0
    n = 0
    for e in _normalize_entries(doc):
        nid = str(e["node_id"])
        if nid in head_ids or nid in seen_remote_nodes:
            continue
        seen_remote_nodes.add(nid)
        merged_entries.append(dict(e))
        n += 1
    return n


def merge_registry_with_remote_overlay(
    head_reg: dict[str, Any],
    repo_root: Path,
    remote: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    rm = (remote or resolve_git_remote(repo_root)).strip() or "origin"
    base, _remote_def, _warns = resolve_integration_defaults(
        repo_root,
        explicit_base=None,
        explicit_remote=None,
    )
    meta: dict[str, Any] = {
        "enabled": True,
        "remote": rm,
        "remote_refs_scanned": 0,
        "merged_remote_entries": 0,
        "merged_integration_branch_entries": 0,
        "skipped_refs": 0,
        "integration_branch_ref": None,
    }
    head_entries = list(_normalize_entries(head_reg))
    head_ids = {str(e["node_id"]) for e in head_entries}
    merged_entries: list[dict[str, Any]] = [dict(e) for e in head_entries]
    seen_remote_nodes: set[str] = set()
    budget = _total_budget_s()
    t0 = time.monotonic()
    ib_ref = f"refs/remotes/{rm}/{base}"
    ok_ib, _ = git_ok(["show-ref", "--verify", ib_ref], repo_root, min(5.0, budget))
    if ok_ib:
        meta["integration_branch_ref"] = ib_ref
        remain = budget - (time.monotonic() - t0)
        if remain > 0:
            timeout = min(PER_SHOW_TIMEOUT_S, max(0.5, remain))
            doc = read_registry_at_ref(repo_root, ib_ref, timeout)
            meta["merged_integration_branch_entries"] += _append_remote_registry_entries(
                doc,
                head_ids,
                merged_entries,
                seen_remote_nodes,
            )
    refs = list_remote_feature_rm_refs(repo_root, rm)[: _max_refs()]
    for ref in refs:
        if time.monotonic() - t0 > budget:
            break
        remain = budget - (time.monotonic() - t0)
        timeout = min(PER_SHOW_TIMEOUT_S, max(0.5, remain))
        doc = read_registry_at_ref(repo_root, ref, timeout)
        meta["remote_refs_scanned"] += 1
        if doc is None:
            meta["skipped_refs"] += 1
            continue
        meta["merged_remote_entries"] += _append_remote_registry_entries(
            doc,
            head_ids,
            merged_entries,
            seen_remote_nodes,
        )
    return {"version": 1, "entries": merged_entries}, meta


def roadmap_fingerprint_with_remote_refs(repo_root: Path, base_fp: int) -> int:
    return base_fp + remote_feature_refs_fingerprint_addendum(repo_root)
