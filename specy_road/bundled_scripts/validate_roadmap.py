#!/usr/bin/env python3
"""Validate merged roadmap graph (manifest + chunks) and registry.yaml."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import json

import yaml
from jsonschema import Draft202012Validator

from roadmap_chunk_utils import discover_manifest_path, load_manifest_mapping
from roadmap_edit_fields import title_to_codename
from roadmap_load import load_roadmap, validate_roadmap_line_limits
from planning_artifacts import collect_planning_artifact_errors
from specy_road.git_workflow_config import (
    integration_refs_present,
    is_git_worktree,
    load_git_workflow_config,
)
from specy_road.runtime_paths import default_user_repo_root

AGENTIC_KEYS = (
    "artifact_action",
    "contract_citation",
    "interface_contract",
    "constraints_note",
    "dependency_note",
)

# Known documentation path prefixes — project-agnostic.
CONTRACT_PATH_PREFIXES = ("shared/", "docs/", "specs/", "adr/")


def load_schema(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def validate_schema(instance: dict, schema: dict, label: str) -> None:
    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(instance), key=lambda e: e.path)
    if errors:
        for err in errors:
            loc = "/".join(str(p) for p in err.path) or "."
            print(f"{label}: {loc}: {err.message}", file=sys.stderr)
        raise SystemExit(1)


def validate_node_keys(nodes: list[dict]) -> None:
    keys = [n.get("node_key") for n in nodes]
    if any(k is None or k == "" for k in keys):
        print("roadmap: every node must have a non-empty node_key", file=sys.stderr)
        raise SystemExit(1)
    if len(keys) != len(set(keys)):
        from collections import Counter

        dup = [k for k, v in Counter(keys).items() if v > 1]
        print(f"roadmap: duplicate node_key values: {dup}", file=sys.stderr)
        raise SystemExit(1)


def validate_dependency_ids(nodes: list[dict]) -> None:
    keys = {n["node_key"] for n in nodes}
    for n in nodes:
        for dep in n.get("dependencies") or []:
            if dep not in keys:
                msg = (
                    f"roadmap: node {n['id']} depends on missing node_key {dep}"
                )
                print(msg, file=sys.stderr)
                raise SystemExit(1)


def cycle_check(nodes: list[dict]) -> None:
    """DFS cycle detection on dependency edges (dep node_key must precede node)."""
    by_key = {n["node_key"]: n for n in nodes}
    visited: set[str] = set()
    stack: set[str] = set()

    def visit(nk: str) -> None:
        if nk in stack:
            n = by_key.get(nk, {})
            msg = (
                f"roadmap: dependency cycle involving "
                f"{n.get('id', nk)}"
            )
            print(msg, file=sys.stderr)
            raise SystemExit(1)
        if nk in visited:
            return
        stack.add(nk)
        for dep in by_key[nk].get("dependencies") or []:
            if dep in by_key:
                visit(dep)
        stack.remove(nk)
        visited.add(nk)

    for nk in by_key:
        if nk not in visited:
            visit(nk)


def warn_phase_status_when_all_descendants_complete(
    nodes: list[dict], *, no_phase_status_warn: bool
) -> None:
    """Emit a warning when a phase's subtree is all Complete but the phase row is not."""
    if no_phase_status_warn:
        return
    by_id = {n["id"]: n for n in nodes}
    children: dict[str | None, list[str]] = {}
    for n in nodes:
        pid = n.get("parent_id")
        if pid in (None, ""):
            pkey: str | None = None
        else:
            pkey = str(pid)
        children.setdefault(pkey, []).append(n["id"])

    def gather_descendants(root: str) -> list[str]:
        out: list[str] = []
        stack = list(children.get(root, []))
        seen: set[str] = set()
        while stack:
            x = stack.pop()
            if x in seen:
                continue
            seen.add(x)
            out.append(x)
            stack.extend(children.get(x, []))
        return out

    for n in nodes:
        if n.get("type") != "phase":
            continue
        desc = gather_descendants(str(n["id"]))
        if not desc:
            continue
        all_complete = True
        for d in desc:
            st = by_id.get(d, {}).get("status")
            if st != "Complete":
                all_complete = False
                break
        if not all_complete:
            continue
        st_phase = n.get("status")
        if st_phase != "Complete":
            print(
                "warning: roadmap: phase "
                f"{n['id']!r} has status {st_phase!r} but every descendant "
                "node is Complete — update the phase status or rely on PM UI "
                "display rollup (subtree complete).",
                file=sys.stderr,
            )


def validate_parents(nodes: list[dict]) -> None:
    ids = {n["id"] for n in nodes}
    for n in nodes:
        pid = n.get("parent_id")
        if pid is not None and pid not in ids:
            print(
                f"roadmap: node {n['id']} has unknown parent_id {pid}",
                file=sys.stderr,
            )
            raise SystemExit(1)


def validate_agentic_checklists(nodes: list[dict]) -> None:
    """Require full agentic_checklist when execution_subtask is agentic; forbid otherwise."""
    for n in nodes:
        nid = n["id"]
        sub = n.get("execution_subtask")
        ac = n.get("agentic_checklist")
        if sub == "agentic":
            if not isinstance(ac, dict):
                msg = (
                    f"roadmap: node {nid} has execution_subtask agentic "
                    "but missing agentic_checklist object"
                )
                print(msg, file=sys.stderr)
                raise SystemExit(1)
            for key in AGENTIC_KEYS:
                val = ac.get(key)
                if not val or not str(val).strip():
                    msg = (
                        f"roadmap: node {nid} agentic_checklist.{key} "
                        "must be a non-empty string"
                    )
                    print(msg, file=sys.stderr)
                    raise SystemExit(1)
        elif ac is not None:
            msg = (
                f"roadmap: node {nid} has agentic_checklist but "
                "execution_subtask is not agentic"
            )
            print(msg, file=sys.stderr)
            raise SystemExit(1)


def validate_unique_titles(nodes: list[dict]) -> None:
    """No two nodes may share the same non-empty title (after strip)."""
    seen: dict[str, str] = {}
    for n in nodes:
        t = (n.get("title") or "").strip()
        if not t:
            continue
        if t in seen:
            msg = (
                f"roadmap: duplicate title {t!r} on nodes {seen[t]} and {n['id']}"
            )
            print(msg, file=sys.stderr)
            raise SystemExit(1)
        seen[t] = n["id"]


def validate_unique_title_slugs(nodes: list[dict]) -> None:
    """
    Kebab-case slugs derived from titles (``title_to_codename``) must be unique.
    Matches the PM GUI codename slug and planning filename middle segment when codename tracks title.
    """
    seen: dict[str, str] = {}
    for n in nodes:
        slug = title_to_codename(str(n.get("title") or ""))
        if not slug:
            continue
        if slug in seen:
            msg = (
                f"roadmap: duplicate title-derived slug {slug!r} on nodes "
                f"{seen[slug]} and {n['id']} (titles differ but map to the same codename; "
                "add a number or qualifier to one title)"
            )
            print(msg, file=sys.stderr)
            raise SystemExit(1)
        seen[slug] = n["id"]


def validate_codenames(nodes: list[dict]) -> None:
    seen: dict[str, str] = {}
    for n in nodes:
        c = n.get("codename")
        if c:
            if c in seen:
                dup_msg = (
                    f"roadmap: duplicate codename '{c}' on {seen[c]} and {n['id']}"
                )
                print(dup_msg, file=sys.stderr)
                raise SystemExit(1)
            seen[c] = n["id"]


def validate_required_planning_dirs(nodes: list[dict]) -> None:
    """Vision, phase, milestone, and task nodes must set planning_dir (one .md file)."""
    for n in nodes:
        t = n.get("type")
        if t not in ("vision", "phase", "milestone", "task"):
            continue
        pd = n.get("planning_dir")
        if isinstance(pd, str) and pd.strip():
            continue
        nid = n.get("id", "?")
        msg = (
            f"roadmap: node {nid} (type {t}): must set planning_dir to a repo-relative "
            "path to a single feature sheet, e.g. planning/M1.1_slug_<node_key>.md"
        )
        print(msg, file=sys.stderr)
        raise SystemExit(1)


def validate_contract_citations(nodes: list[dict]) -> None:
    """Warn when an agentic node's contract_citation lacks a known doc-path prefix."""
    for n in nodes:
        if n.get("execution_subtask") != "agentic":
            continue
        ac = n.get("agentic_checklist") or {}
        citation = ac.get("contract_citation", "")
        if not any(citation.startswith(p) for p in CONTRACT_PATH_PREFIXES):
            print(
                f"roadmap: warning — node {n['id']} contract_citation does not "
                f"reference a known doc path "
                f"({', '.join(CONTRACT_PATH_PREFIXES)}): \"{citation}\"",
                file=sys.stderr,
            )


def touch_zone_overlap(entries: list[dict]) -> None:
    """Warn if entries share a touch zone path (heuristic)."""
    for i, a in enumerate(entries):
        za = sorted(a.get("touch_zones") or [])
        for j in range(i + 1, len(entries)):
            b = entries[j]
            zb = sorted(b.get("touch_zones") or [])
            for x in za:
                for y in zb:
                    y_base = y.rstrip("/")
                    x_base = x.rstrip("/")
                    nested = x.startswith(y_base + "/") or y.startswith(
                        x_base + "/"
                    )
                    if x == y or nested:
                        ac = a.get("codename")
                        bc = b.get("codename")
                        warn = (
                            f"registry: warning — possible overlap '{x}' vs "
                            f"'{y}' ({ac} vs {bc})"
                        )
                        print(warn, file=sys.stderr)


def run_validation(
    roadmap: dict,
    registry: dict,
    no_overlap_warn: bool,
    *,
    repo_root: Path | None = None,
    no_phase_status_warn: bool = False,
) -> None:
    r = repo_root or default_user_repo_root()
    roadmap_schema = r / "schemas" / "roadmap.schema.json"
    registry_schema = r / "schemas" / "registry.schema.json"
    validate_schema(roadmap, load_schema(roadmap_schema), "roadmap.schema")
    validate_schema(registry, load_schema(registry_schema), "registry.schema")

    nodes = roadmap["nodes"]
    ids = [n["id"] for n in nodes]
    if len(ids) != len(set(ids)):
        from collections import Counter

        dup = [k for k, v in Counter(ids).items() if v > 1]
        print(f"roadmap: duplicate ids: {dup}", file=sys.stderr)
        raise SystemExit(1)

    validate_node_keys(nodes)
    validate_parents(nodes)
    validate_dependency_ids(nodes)
    cycle_check(nodes)
    validate_agentic_checklists(nodes)
    validate_contract_citations(nodes)
    validate_unique_titles(nodes)
    validate_unique_title_slugs(nodes)
    validate_codenames(nodes)
    validate_required_planning_dirs(nodes)

    warn_phase_status_when_all_descendants_complete(
        nodes, no_phase_status_warn=no_phase_status_warn
    )

    plan_errs = collect_planning_artifact_errors(r, nodes)
    if plan_errs:
        for msg in plan_errs:
            print(msg, file=sys.stderr)
        raise SystemExit(1)

    id_set = set(ids)
    for e in registry.get("entries") or []:
        nid = e.get("node_id")
        if nid and nid not in id_set:
            cn = e.get("codename")
            unk = f"registry: entry {cn} references unknown node_id {nid}"
            print(unk, file=sys.stderr)
            raise SystemExit(1)

    if registry.get("entries") and not no_overlap_warn:
        touch_zone_overlap(registry["entries"])

    print("OK: roadmap and registry validate.")


def validate_git_workflow_contract(root: Path) -> None:
    """Validate ``roadmap/git-workflow.yaml`` if present; warn on missing refs."""
    gw = root / "roadmap" / "git-workflow.yaml"
    if not gw.is_file():
        print(
            "warning: missing roadmap/git-workflow.yaml — add the template from "
            "`specy-road init project` so CLI and PM GUI share your integration branch.",
            file=sys.stderr,
        )
        return
    data, err = load_git_workflow_config(root)
    if err:
        print(err, file=sys.stderr)
        raise SystemExit(1)
    assert data is not None
    if is_git_worktree(root):
        ok, _ = integration_refs_present(
            root,
            str(data["remote"]),
            str(data["integration_branch"]),
        )
        if not ok:
            print(
                "warning: no local git ref for "
                f"{data['remote']}/{data['integration_branch']} — "
                f"run: git fetch {data['remote']}",
                file=sys.stderr,
            )


def validate_at(
    root: Path,
    *,
    no_overlap_warn: bool = False,
    require_registry: bool = True,
    no_phase_status_warn: bool = False,
) -> None:
    """Validate roadmap + registry under ``root`` (repo root containing ``roadmap/``)."""
    reg_path = root / "roadmap" / "registry.yaml"
    if require_registry and not reg_path.is_file():
        print(f"missing {reg_path}", file=sys.stderr)
        raise SystemExit(1)

    validate_roadmap_line_limits(root)
    discover_manifest_path(root)
    validate_git_workflow_contract(root)
    mdoc = load_manifest_mapping(root)
    mschema = root / "schemas" / "manifest.schema.json"
    validate_schema(mdoc, load_schema(mschema), "manifest.schema")
    roadmap = load_roadmap(root)
    if reg_path.is_file():
        with reg_path.open(encoding="utf-8") as f:
            registry = yaml.safe_load(f)
    else:
        registry = {"version": 1, "entries": []}

    run_validation(
        roadmap,
        registry,
        no_overlap_warn,
        repo_root=root,
        no_phase_status_warn=no_phase_status_warn,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--no-overlap-warn",
        action="store_true",
        help="suppress touch-zone overlap warnings",
    )
    parser.add_argument(
        "--no-phase-status-warn",
        action="store_true",
        help=(
            "suppress warning when a phase is not Complete but every descendant node is"
        ),
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        metavar="DIR",
        help="Repository root (default: git root or cwd).",
    )
    args = parser.parse_args()
    root = (args.repo_root or default_user_repo_root()).resolve()
    validate_at(
        root,
        no_overlap_warn=args.no_overlap_warn,
        require_registry=True,
        no_phase_status_warn=args.no_phase_status_warn,
    )


if __name__ == "__main__":
    main()
