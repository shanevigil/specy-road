#!/usr/bin/env python3
"""Add ``node_key`` and convert ``dependencies`` from display ids to node_key (UUID).

Run once from the repository root on roadmaps created before stable keys::

    python scripts/migrate_stable_node_keys.py --repo-root .

Idempotent: skips nodes that already have ``node_key``.
"""

from __future__ import annotations

import argparse
import uuid
from pathlib import Path

import yaml

from roadmap_chunk_utils import load_json_chunk, roadmap_dir, write_json_chunk
from roadmap_load import load_manifest_mapping, load_roadmap
from validate_roadmap import validate_at


NS = uuid.UUID("01234567-89ab-cdef-0123-456789abcdef")


def deterministic_key(display_id: str) -> str:
    return str(uuid.uuid5(NS, f"specy-road/migrate/{display_id}"))


def migrate_chunk(path: Path, id_to_key: dict[str, str]) -> bool:
    nodes = load_json_chunk(path)
    changed = False
    for n in nodes:
        if not isinstance(n, dict):
            continue
        nid = n.get("id")
        if not isinstance(nid, str):
            continue
        if not n.get("node_key"):
            n["node_key"] = id_to_key.get(nid) or deterministic_key(nid)
            changed = True
        nk = n["node_key"]
        id_to_key[nid] = nk
        deps = n.get("dependencies")
        if not isinstance(deps, list):
            continue
        new_deps: list[str] = []
        for d in deps:
            if not isinstance(d, str):
                continue
            if d in id_to_key:
                new_deps.append(id_to_key[d])
            elif len(d) == 36 and d.count("-") == 4:
                new_deps.append(d)
            else:
                new_deps.append(id_to_key.setdefault(d, deterministic_key(d)))
        if new_deps != deps:
            n["dependencies"] = new_deps
            changed = True
    if changed:
        write_json_chunk(path, nodes)
    return changed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path.cwd(),
        help="Repository root (default: cwd)",
    )
    args = parser.parse_args()
    root = args.repo_root.resolve()
    doc = load_roadmap(root)
    id_to_key: dict[str, str] = {}
    for n in doc["nodes"]:
        if isinstance(n.get("node_key"), str) and n["node_key"]:
            id_to_key[n["id"]] = n["node_key"]
    mdoc = load_manifest_mapping(root)
    base = roadmap_dir(root)
    touched = False
    for rel in mdoc.get("includes") or []:
        if not isinstance(rel, str):
            continue
        p = (base / rel).resolve()
        if p.suffix.lower() == ".json" and p.is_file():
            if migrate_chunk(p, id_to_key):
                touched = True
                print(f"migrated: {p.relative_to(root)}")
    reg = root / "roadmap" / "registry.yaml"
    if reg.is_file():
        data = yaml.safe_load(reg.read_text(encoding="utf-8"))
        entries = data.get("entries") if isinstance(data, dict) else None
        if isinstance(entries, list):
            for e in entries:
                if not isinstance(e, dict):
                    continue
                nid = e.get("node_id")
                if isinstance(nid, str) and nid in id_to_key:
                    e.setdefault("node_key", id_to_key[nid])
            reg.write_text(
                yaml.dump(data, default_flow_style=False, allow_unicode=True, sort_keys=False),
                encoding="utf-8",
            )
    if touched:
        validate_at(root, no_overlap_warn=True, require_registry=True)
        print("[ok] migration complete; validation passed.")
    else:
        print("[ok] nothing to migrate (already has node_key).")


if __name__ == "__main__":
    main()
