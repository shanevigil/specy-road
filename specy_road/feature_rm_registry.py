"""Match ``feature/rm-<codename>`` to ``roadmap/registry.yaml`` and roadmap nodes."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from specy_road.bundled_scripts.roadmap_load import load_roadmap
from specy_road.registry_yaml import read_registry, registry_path

_Context = tuple[str, dict[str, Any], dict[str, Any], list[dict[str, Any]]]


def resolve_feature_rm_registry_context(repo_root: Path, branch: str) -> _Context:
    """Return (codename, registry_doc, entry, nodes) or raise SystemExit."""
    codename = branch[len("feature/rm-"):]
    reg = read_registry(registry_path(repo_root))
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


def _node_for_codename(nodes: list[dict], codename: str) -> dict | None:
    return next(
        (n for n in nodes if n.get("codename") == codename and n.get("id")),
        None,
    )


def finish_already_done_on_branch(repo_root: Path, branch: str) -> dict | None:
    """Return the leaf when finish already ran here: no registry row, status Complete."""
    if not branch.startswith("feature/rm-"):
        return None
    codename = branch[len("feature/rm-") :]
    reg = read_registry(registry_path(repo_root))
    if any(e.get("codename") == codename for e in reg.get("entries") or []):
        return None
    node = _node_for_codename(load_roadmap(repo_root)["nodes"], codename)
    if node is None:
        return None
    if (node.get("status") or "").lower() != "complete":
        return None
    return node


def report_finish_already_done_on_branch(repo_root: Path, branch: str) -> None:
    """Explain a repeat ``finish-this-task`` after bookkeeping already committed."""
    from specy_road.finish_modes import print_pr_gated_state
    from specy_road.git_workflow_config import resolve_integration_defaults

    node = finish_already_done_on_branch(repo_root, branch)
    if node is None:
        return
    node_id = node["id"]
    ib, _, _ = resolve_integration_defaults(
        repo_root, explicit_base=None, explicit_remote=None
    )
    print(
        f"[info] {node_id} is already Complete on {branch}; "
        "finish-this-task ran on this branch and released the registry row here."
    )
    print(
        "  Do not run finish again — open or merge the PR to close the node on "
        f"{ib}."
    )
    print_pr_gated_state(node_id=node_id, branch=branch, integration_branch=ib)
    raise SystemExit(0)


def resolve_feature_rm_registry_context_for_finish(
    repo_root: Path, branch: str
) -> _Context:
    """Like :func:`resolve_feature_rm_registry_context`, with a repeat-finish hint."""
    if branch.startswith("feature/rm-"):
        codename = branch[len("feature/rm-") :]
        entries = read_registry(registry_path(repo_root)).get("entries") or []
        if codename and not any(e.get("codename") == codename for e in entries):
            if finish_already_done_on_branch(repo_root, branch):
                report_finish_already_done_on_branch(repo_root, branch)
    return resolve_feature_rm_registry_context(repo_root, branch)
