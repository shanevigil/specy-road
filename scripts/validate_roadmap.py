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
from roadmap_load import load_roadmap, validate_roadmap_line_limits
from planning_artifacts import collect_planning_artifact_errors

ROOT = Path(__file__).resolve().parent.parent
REGISTRY_PATH = ROOT / "roadmap" / "registry.yaml"

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


def validate_dependency_ids(nodes: list[dict]) -> None:
    ids = {n["id"] for n in nodes}
    for n in nodes:
        for dep in n.get("dependencies") or []:
            if dep not in ids:
                msg = f"roadmap: node {n['id']} depends on missing id {dep}"
                print(msg, file=sys.stderr)
                raise SystemExit(1)


def cycle_check(nodes: list[dict]) -> None:
    """DFS cycle detection on dependency edges (dep must precede node)."""
    by_id = {n["id"]: n for n in nodes}
    visited: set[str] = set()
    stack: set[str] = set()

    def visit(nid: str) -> None:
        if nid in stack:
            msg = f"roadmap: dependency cycle involving {nid}"
            print(msg, file=sys.stderr)
            raise SystemExit(1)
        if nid in visited:
            return
        stack.add(nid)
        for dep in by_id[nid].get("dependencies") or []:
            visit(dep)
        stack.remove(nid)
        visited.add(nid)

    for nid in by_id:
        if nid not in visited:
            visit(nid)


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
) -> None:
    r = repo_root or ROOT
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

    validate_parents(nodes)
    validate_dependency_ids(nodes)
    cycle_check(nodes)
    validate_agentic_checklists(nodes)
    validate_contract_citations(nodes)
    validate_codenames(nodes)

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


def validate_at(
    root: Path, *, no_overlap_warn: bool = False, require_registry: bool = True
) -> None:
    """Validate roadmap + registry under ``root`` (repo root containing ``roadmap/``)."""
    reg_path = root / "roadmap" / "registry.yaml"
    if require_registry and not reg_path.is_file():
        print(f"missing {reg_path}", file=sys.stderr)
        raise SystemExit(1)

    validate_roadmap_line_limits(root)
    discover_manifest_path(root)
    mdoc = load_manifest_mapping(root)
    mschema = root / "schemas" / "manifest.schema.json"
    validate_schema(mdoc, load_schema(mschema), "manifest.schema")
    roadmap = load_roadmap(root)
    if reg_path.is_file():
        with reg_path.open(encoding="utf-8") as f:
            registry = yaml.safe_load(f)
    else:
        registry = {"version": 1, "entries": []}

    run_validation(roadmap, registry, no_overlap_warn, repo_root=root)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--no-overlap-warn",
        action="store_true",
        help="suppress touch-zone overlap warnings",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        metavar="DIR",
        help="Repository root (default: parent of scripts/).",
    )
    args = parser.parse_args()
    root = (args.repo_root or ROOT).resolve()
    validate_at(root, no_overlap_warn=args.no_overlap_warn, require_registry=True)


if __name__ == "__main__":
    main()
