"""Merge ``roadmap/registry.yaml`` from remote-tracking ``feature/rm-*`` refs into the PM GUI payload.

Primary control: **Settings** → ``pm_gui.registry_remote_overlay`` in ``~/.specy-road/gui-settings.json``.
Optional env override: ``SPECY_ROAD_GUI_REGISTRY_REMOTE_OVERLAY=0`` forces off; ``=1`` forces on.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

import yaml

from specy_road.git_workflow_config import is_git_worktree, load_git_workflow_config

_LIB_DIR = Path(__file__).resolve().parent / "bundled_scripts"
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))
from roadmap_gui_settings import effective_settings_for_repo  # noqa: E402

REGISTRY_REL = Path("roadmap") / "registry.yaml"
DEFAULT_MAX_REFS = 48
DEFAULT_TOTAL_BUDGET_S = 5.0
PER_SHOW_TIMEOUT_S = 4.0
_FETCH_LOCK = threading.Lock()
_LAST_FETCH_MONO: dict[str, float] = {}


def registry_remote_overlay_enabled(repo_root: Path | None = None) -> bool:
    """True when overlay merge should run: env override, else settings + Test Git + repo/token."""
    v = os.environ.get("SPECY_ROAD_GUI_REGISTRY_REMOTE_OVERLAY", "").strip().lower()
    if v in ("0", "false", "no", "off"):
        return False
    if v in ("1", "true", "yes", "on"):
        return True
    if repo_root is None:
        return False
    eff = effective_settings_for_repo(repo_root)
    pm = eff.get("pm_gui") if isinstance(eff.get("pm_gui"), dict) else {}
    if not pm.get("registry_remote_overlay"):
        return False
    from pm_gui_git_remote_verify import get_git_remote_tested_ok

    if not get_git_remote_tested_ok(repo_root):
        return False
    gr = eff.get("git_remote") or {}
    return bool(str(gr.get("repo") or "").strip() and str(gr.get("token") or "").strip())


def maybe_auto_git_fetch(repo_root: Path, remote: str) -> None:
    """Best-effort ``git fetch`` for ``remote``; throttled by interval; errors ignored."""
    af = os.environ.get("SPECY_ROAD_GUI_REGISTRY_AUTO_FETCH", "").strip().lower()
    if af in ("0", "false", "no", "off"):
        return
    if not is_git_worktree(repo_root):
        return
    raw_iv = os.environ.get("SPECY_ROAD_GUI_REGISTRY_FETCH_INTERVAL_S", "").strip()
    try:
        interval = float(raw_iv) if raw_iv else 5.0
    except ValueError:
        interval = 5.0
    interval = max(1.0, min(interval, 3600.0))
    key = str(repo_root.resolve())
    now = time.monotonic()
    with _FETCH_LOCK:
        last = _LAST_FETCH_MONO.get(key, 0.0)
        if now - last < interval:
            return
        _LAST_FETCH_MONO[key] = now
    rname = (remote or "").strip() or "origin"
    try:
        subprocess.run(
            ["git", "fetch", "--quiet", rname],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=120.0,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        pass


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
        "SPECY_ROAD_GUI_REGISTRY_REMOTE_OVERLAY_BUDGET_S", ""
    ).strip()
    if not raw:
        return DEFAULT_TOTAL_BUDGET_S
    try:
        return max(0.5, min(float(raw), 60.0))
    except ValueError:
        return DEFAULT_TOTAL_BUDGET_S


def _git_ok(
    args: list[str], cwd: Path, timeout: float
) -> tuple[bool, str]:
    try:
        r = subprocess.run(
            ["git", *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False, ""
    if r.returncode != 0:
        return False, (r.stderr or r.stdout or "").strip()
    return True, (r.stdout or "").strip()


def resolve_git_remote(repo_root: Path) -> str:
    """Remote name from ``roadmap/git-workflow.yaml``, else ``origin``."""
    data, _ = load_git_workflow_config(repo_root)
    if isinstance(data, dict):
        rm = data.get("remote")
        if isinstance(rm, str) and rm.strip():
            return rm.strip()
    return "origin"


def list_remote_feature_rm_refs(repo_root: Path, remote: str) -> list[str]:
    """Sorted ``refs/remotes/<remote>/feature/rm-*`` ref names."""
    rm = (remote or "").strip()
    if not rm or not is_git_worktree(repo_root):
        return []
    pattern = f"refs/remotes/{rm}/feature/rm-*"
    ok, out = _git_ok(
        ["for-each-ref", "--format=%(refname)", pattern],
        repo_root,
        60.0,
    )
    if not ok:
        return []
    lines = sorted({ln.strip() for ln in out.splitlines() if ln.strip()})
    return lines


def read_registry_at_ref(
    repo_root: Path, ref: str, timeout: float
) -> dict[str, Any] | None:
    """Parse ``roadmap/registry.yaml`` at ``ref`` via ``git show``."""
    spec = f"{ref}:{REGISTRY_REL.as_posix()}"
    ok, blob = _git_ok(["show", spec], repo_root, timeout)
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


def merge_registry_with_remote_overlay(
    head_reg: dict[str, Any],
    repo_root: Path,
    remote: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """HEAD entries win on ``node_id``; remote refs fill gaps.

    Returns ``(merged_registry_doc, meta)``.
    """
    rm = (remote or resolve_git_remote(repo_root)).strip() or "origin"
    meta: dict[str, Any] = {
        "enabled": True,
        "remote": rm,
        "remote_refs_scanned": 0,
        "merged_remote_entries": 0,
        "skipped_refs": 0,
    }

    head_entries = list(_normalize_entries(head_reg))
    head_ids = {str(e["node_id"]) for e in head_entries}
    merged_entries: list[dict[str, Any]] = [dict(e) for e in head_entries]
    seen_remote_nodes: set[str] = set()

    refs = list_remote_feature_rm_refs(repo_root, rm)[: _max_refs()]
    budget = _total_budget_s()
    t0 = time.monotonic()

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
        for e in _normalize_entries(doc):
            nid = str(e["node_id"])
            if nid in head_ids:
                continue
            if nid in seen_remote_nodes:
                continue
            seen_remote_nodes.add(nid)
            merged_entries.append(dict(e))
            meta["merged_remote_entries"] += 1

    out_doc: dict[str, Any] = {
        "version": 1,
        "entries": merged_entries,
    }
    return out_doc, meta


def remote_feature_refs_fingerprint_addendum(repo_root: Path) -> int:
    """Stable int from remote ``feature/rm-*`` ref object names (when overlay enabled)."""
    if not registry_remote_overlay_enabled(repo_root) or not is_git_worktree(repo_root):
        return 0
    rm = resolve_git_remote(repo_root)
    pattern = f"refs/remotes/{rm}/feature/rm-*"
    ok, out = _git_ok(
        ["for-each-ref", "--format=%(objectname) %(refname)", pattern],
        repo_root,
        60.0,
    )
    if not ok or not out.strip():
        return 0
    h = hashlib.sha256(out.encode("utf-8")).digest()[:8]
    return int.from_bytes(h, "little")


def roadmap_fingerprint_with_remote_refs(repo_root: Path, base_fp: int) -> int:
    """Combine packaged roadmap fingerprint with remote-ref tip hash."""
    return base_fp + remote_feature_refs_fingerprint_addendum(repo_root)
