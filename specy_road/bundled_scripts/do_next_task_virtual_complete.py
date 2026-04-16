"""Virtual Complete-from-feature-tip for do-next dependency evaluation."""

from __future__ import annotations

from pathlib import Path

from roadmap_load_at_ref import load_roadmap_nodes_at_ref


def virtual_complete_from_registry(
    reg: dict,
    *,
    repo_root: Path,
    remote: str,
) -> tuple[set[str], list[str]]:
    """node_keys Complete on feature-branch tips but not yet on integration (dep eval only)."""
    virtual: set[str] = set()
    log_lines: list[str] = []
    entries = reg.get("entries") or []
    for e in entries:
        if not isinstance(e, dict):
            continue
        branch = e.get("branch")
        node_id = e.get("node_id")
        if not isinstance(branch, str) or not branch.strip():
            continue
        if not isinstance(node_id, str) or not node_id.strip():
            continue
        ref = f"{remote}/{branch.strip()}"
        nodes_at = load_roadmap_nodes_at_ref(repo_root, ref)
        if nodes_at is None:
            continue
        matched = next((n for n in nodes_at if n.get("id") == node_id), None)
        if matched is None:
            continue
        if (matched.get("status") or "").lower() != "complete":
            continue
        nk = matched.get("node_key")
        if not isinstance(nk, str) or not nk:
            continue
        virtual.add(nk)
        codename = e.get("codename", "") or ""
        log_lines.append(
            f"[info] Treating node {node_id} ({codename}) as Complete for dependency "
            f"evaluation — {ref} shows Complete; integration branch may not have merged "
            f"the PR yet."
        )
    return virtual, log_lines
