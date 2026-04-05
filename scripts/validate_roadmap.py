#!/usr/bin/env python3
"""Validate roadmap.yaml and registry.yaml (schema, DAG, ids, codenames)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import json

import yaml
from jsonschema import Draft202012Validator

from roadmap_load import load_roadmap, validate_roadmap_yaml_line_limits

ROOT = Path(__file__).resolve().parent.parent
REGISTRY_PATH = ROOT / "roadmap" / "registry.yaml"
SCHEMA_ROADMAP = ROOT / "schemas" / "roadmap.schema.json"
SCHEMA_REGISTRY = ROOT / "schemas" / "registry.schema.json"

AGENTIC_KEYS = (
    "artifact_action",
    "spec_citation",
    "interface_contract",
    "constraints_note",
    "dependency_note",
)

# Known documentation path prefixes — project-agnostic.
# A spec_citation that starts with one of these is considered traceable.
SPEC_PATH_PREFIXES = ("shared/", "docs/", "specs/", "adr/")


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


def validate_spec_citations(nodes: list[dict]) -> None:
    """Warn when an agentic node's spec_citation lacks a known doc-path prefix."""
    for n in nodes:
        if n.get("execution_subtask") != "agentic":
            continue
        ac = n.get("agentic_checklist") or {}
        citation = ac.get("spec_citation", "")
        if not any(citation.startswith(p) for p in SPEC_PATH_PREFIXES):
            print(
                f"roadmap: warning — node {n['id']} spec_citation does not "
                f"reference a known doc path "
                f"({', '.join(SPEC_PATH_PREFIXES)}): \"{citation}\"",
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


def run_validation(roadmap: dict, registry: dict, no_overlap_warn: bool) -> None:
    validate_schema(roadmap, load_schema(SCHEMA_ROADMAP), "roadmap.schema")
    validate_schema(registry, load_schema(SCHEMA_REGISTRY), "registry.schema")

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
    validate_spec_citations(nodes)
    validate_codenames(nodes)

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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--no-overlap-warn",
        action="store_true",
        help="suppress touch-zone overlap warnings",
    )
    args = parser.parse_args()

    if not REGISTRY_PATH.is_file():
        print(f"missing {REGISTRY_PATH}", file=sys.stderr)
        raise SystemExit(1)

    validate_roadmap_yaml_line_limits(ROOT)
    roadmap = load_roadmap(ROOT)
    with REGISTRY_PATH.open(encoding="utf-8") as f:
        registry = yaml.safe_load(f)

    run_validation(roadmap, registry, args.no_overlap_warn)


if __name__ == "__main__":
    main()
