"""Match ``feature/rm-<codename>`` to ``roadmap/registry.yaml`` and roadmap nodes."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import yaml
from roadmap_load import load_roadmap

_Context = tuple[str, dict[str, Any], dict[str, Any], list[dict[str, Any]]]


def resolve_feature_rm_registry_context(repo_root: Path, branch: str) -> _Context:
    """Return (codename, registry_doc, entry, nodes) or raise SystemExit."""
    codename = branch[len("feature/rm-"):]
    reg_path = repo_root / "roadmap" / "registry.yaml"
    with reg_path.open(encoding="utf-8") as f:
        reg = yaml.safe_load(f) or {"version": 1, "entries": []}
    entries = reg.get("entries") or []
    entry = next((e for e in entries if e.get("codename") == codename), None)
    if not entry:
        print(
            f"error: no registry entry for codename '{codename}'.",
            file=sys.stderr,
        )
        print("  Is roadmap/registry.yaml up to date?", file=sys.stderr)
        raise SystemExit(1)
    node_id = entry["node_id"]
    nodes = load_roadmap(repo_root)["nodes"]
    if not any(n["id"] == node_id for n in nodes):
        print(
            f"error: node '{node_id}' not found in roadmap.",
            file=sys.stderr,
        )
        raise SystemExit(1)
    if any(
        isinstance(n.get("parent_id"), str) and n.get("parent_id") == node_id
        for n in nodes
    ):
        print(
            f"error: registry entry for '{node_id}' is not a leaf claim.",
            file=sys.stderr,
        )
        print(
            "  Roadmap feature commands only support leaf-scoped claims "
            "(feature/rm-<leaf-codename>).",
            file=sys.stderr,
        )
        raise SystemExit(1)
    reg_branch = entry.get("branch")
    if not reg_branch:
        print(
            "error: registry entry is missing 'branch' — "
            "fix roadmap/registry.yaml.",
            file=sys.stderr,
        )
        raise SystemExit(1)
    if reg_branch != branch:
        print(
            f"error: registry says branch {reg_branch!r} "
            f"but HEAD is {branch!r}.",
            file=sys.stderr,
        )
        print(
            "  Check out the feature branch that matches the registry, "
            "or fix the entry.",
            file=sys.stderr,
        )
        raise SystemExit(1)
    return codename, reg, entry, nodes
