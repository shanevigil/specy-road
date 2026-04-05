#!/usr/bin/env python3
"""Validate roadmap.yaml and registry.yaml: schema, DAG, unique ids/codenames."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import json
import yaml
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parent.parent
ROADMAP_PATH = ROOT / "roadmap" / "roadmap.yaml"
REGISTRY_PATH = ROOT / "roadmap" / "registry.yaml"
SCHEMA_ROADMAP = ROOT / "schemas" / "roadmap.schema.json"
SCHEMA_REGISTRY = ROOT / "schemas" / "registry.schema.json"


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


def build_adjacency(nodes: list[dict]) -> dict[str, list[str]]:
    by_id: dict[str, dict] = {n["id"]: n for n in nodes}
    graph: dict[str, list[str]] = {nid: [] for nid in by_id}
    for n in nodes:
        nid = n["id"]
        for dep in n.get("dependencies") or []:
            if dep not in by_id:
                print(f"roadmap: node {nid} depends on missing id {dep}", file=sys.stderr)
                raise SystemExit(1)
            graph[nid].append(dep)
    return graph


def cycle_check(nodes: list[dict]) -> None:
    """DFS cycle detection on dependency edges (dep must precede node)."""
    by_id = {n["id"]: n for n in nodes}
    visited: set[str] = set()
    stack: set[str] = set()

    def visit(nid: str) -> None:
        if nid in stack:
            print(f"roadmap: dependency cycle involving {nid}", file=sys.stderr)
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


def validate_codenames(nodes: list[dict]) -> None:
    seen: dict[str, str] = {}
    for n in nodes:
        c = n.get("codename")
        if c:
            if c in seen:
                print(
                    f"roadmap: duplicate codename '{c}' on {seen[c]} and {n['id']}",
                    file=sys.stderr,
                )
                raise SystemExit(1)
            seen[c] = n["id"]


def touch_zone_overlap(entries: list[dict]) -> None:
    """Warn if two active entries share a touch zone path prefix (heuristic)."""
    for i, a in enumerate(entries):
        za = sorted(a.get("touch_zones") or [])
        for b in entries[i + 1 :]:
            zb = sorted(b.get("touch_zones") or [])
            for x in za:
                for y in zb:
                    if x == y or x.startswith(y.rstrip("/") + "/") or y.startswith(x.rstrip("/") + "/"):
                        print(
                            f"registry: warning — possible overlap '{x}' vs '{y}' "
                            f"({a.get('codename')} vs {b.get('codename')})",
                            file=sys.stderr,
                        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--no-overlap-warn",
        action="store_true",
        help="suppress touch-zone overlap warnings",
    )
    args = parser.parse_args()

    if not ROADMAP_PATH.is_file():
        print(f"missing {ROADMAP_PATH}", file=sys.stderr)
        raise SystemExit(1)
    if not REGISTRY_PATH.is_file():
        print(f"missing {REGISTRY_PATH}", file=sys.stderr)
        raise SystemExit(1)

    with ROADMAP_PATH.open(encoding="utf-8") as f:
        roadmap = yaml.safe_load(f)
    with REGISTRY_PATH.open(encoding="utf-8") as f:
        registry = yaml.safe_load(f)

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
    cycle_check(nodes)
    validate_codenames(nodes)

    for e in registry.get("entries") or []:
        nid = e.get("node_id")
        if nid and nid not in set(ids):
            print(
                f"registry: entry {e.get('codename')} references unknown node_id {nid}",
                file=sys.stderr,
            )
            raise SystemExit(1)

    if registry.get("entries") and not args.no_overlap_warn:
        touch_zone_overlap(registry["entries"])

    print("OK: roadmap and registry validate.")


if __name__ == "__main__":
    main()
