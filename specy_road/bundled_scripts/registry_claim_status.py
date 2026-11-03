"""Annotate a leaf's registry claim for list-nodes and brief output."""

from __future__ import annotations


def leaf_claim_entry(
    node_id: str, *, leaf_ids: set[str], by_reg: dict[str, dict]
) -> dict | None:
    """Active registry row for a structural leaf with a non-empty branch."""
    if node_id not in leaf_ids:
        return None
    entry = by_reg.get(node_id)
    br = entry.get("branch") if entry else None
    return entry if isinstance(br, str) and br.strip() else None


def list_nodes_status_label(node: dict, claim: dict | None) -> str:
    raw = str(node.get("status", ""))
    return f"{raw} (claimed)" if claim else raw


def list_nodes_json_row(node: dict, chunk_rel: str | None, claim: dict | None) -> dict:
    row = {**node, "chunk": chunk_rel, "claimed": bool(claim)}
    if claim:
        row["branch"] = claim["branch"]
    return row


def brief_status_own_line(node: dict, claim: dict | None) -> str:
    status = node.get("status")
    if not claim:
        return str(status)
    line = f"{status} — claim `{claim.get('branch', '')}`"
    owner = claim.get("owner")
    if isinstance(owner, str) and owner.strip():
        line += f" (owner: {owner.strip()})"
    return line
