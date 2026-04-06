#!/usr/bin/env python3
"""Close the current roadmap feature branch: update status, deregister, validate, commit."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import yaml
from roadmap_load import load_roadmap

ROOT = Path(__file__).resolve().parent.parent
REGISTRY_PATH = ROOT / "roadmap" / "registry.yaml"


# ---------------------------------------------------------------------------
# Git helpers
# ---------------------------------------------------------------------------


def _current_branch() -> str:
    r = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        capture_output=True,
        text=True,
        cwd=ROOT,
        check=True,
    )
    return r.stdout.strip()


def _git(*args: str) -> None:
    subprocess.check_call(["git", *args], cwd=ROOT)


# ---------------------------------------------------------------------------
# Registry helpers
# ---------------------------------------------------------------------------


def _load_registry() -> dict:
    with REGISTRY_PATH.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {"version": 1, "entries": []}


def _save_registry(doc: dict) -> None:
    with REGISTRY_PATH.open("w", encoding="utf-8") as f:
        yaml.dump(doc, f, default_flow_style=False, allow_unicode=True, sort_keys=False)


# ---------------------------------------------------------------------------
# YAML chunk status update (in-place, preserves formatting)
# ---------------------------------------------------------------------------


def _find_chunk(node_id: str) -> Path | None:
    """Return the chunk file (or roadmap.yaml) that contains node_id."""
    manifest = ROOT / "roadmap" / "roadmap.yaml"
    with manifest.open(encoding="utf-8") as f:
        doc = yaml.safe_load(f)
    includes = doc.get("includes")
    if not includes:
        return manifest
    base = ROOT / "roadmap"
    for rel in includes:
        chunk = base / rel
        with chunk.open(encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if any(n.get("id") == node_id for n in (data.get("nodes") or [])):
            return chunk
    return None


def _patch_status(content: str, node_id: str, new_status: str) -> tuple[str, bool]:
    """
    Update the top-level ``status:`` field for node_id in YAML text without
    reformatting the file.  Returns (new_content, was_updated).

    Strategy: scan line-by-line tracking which node we are inside, then
    replace the first ``status:`` key at exactly node_indent+2 spaces.
    """
    lines = content.splitlines(keepends=True)
    in_target = False
    node_indent = -1
    updated = False

    for i, line in enumerate(lines):
        stripped = line.strip()
        leading = len(line) - len(line.lstrip())

        if stripped.startswith("- id:"):
            raw_id = stripped[len("- id:"):].strip().strip("\"'")
            if raw_id == node_id:
                in_target = True
                node_indent = leading
            elif in_target and leading <= node_indent:
                # Entered a different node at the same list depth — give up.
                break
            continue

        if in_target:
            # ``- foo:`` at the same list depth as the node marker means a new
            # list item (different structure) — exit.
            if stripped.startswith("- ") and leading <= node_indent:
                break
            # Match ``status:`` at exactly field depth (node_indent + 2).
            if leading == node_indent + 2 and stripped.startswith("status:"):
                lines[i] = " " * leading + f"status: {new_status}\n"
                updated = True
                break

    return "".join(lines), updated


# ---------------------------------------------------------------------------
# Main (split into focused helpers to stay within line limits)
# ---------------------------------------------------------------------------


def _resolve_context(branch: str) -> tuple[str, dict, dict, list[dict]]:
    """Return (codename, registry_doc, entry, nodes) or raise SystemExit."""
    codename = branch[len("feature/rm-"):]
    reg = _load_registry()
    entries = reg.get("entries") or []
    entry = next((e for e in entries if e.get("codename") == codename), None)
    if not entry:
        print(f"error: no registry entry for codename '{codename}'.", file=sys.stderr)
        print("  Is roadmap/registry.yaml up to date?", file=sys.stderr)
        raise SystemExit(1)
    node_id = entry["node_id"]
    nodes = load_roadmap(ROOT)["nodes"]
    if not any(n["id"] == node_id for n in nodes):
        print(f"error: node '{node_id}' not found in roadmap.", file=sys.stderr)
        raise SystemExit(1)
    return codename, reg, entry, nodes


def _update_chunk_status(node_id: str) -> list[str]:
    """Patch status in chunk file; return list of changed file paths."""
    chunk = _find_chunk(node_id)
    if not chunk:
        print(f"[warn] chunk file not found for {node_id} — set status manually.")
        return []
    content = chunk.read_text(encoding="utf-8")
    new_content, patched = _patch_status(content, node_id, "Complete")
    if patched:
        chunk.write_text(new_content, encoding="utf-8")
        print(f"[ok] status -> Complete  ({chunk.relative_to(ROOT)})")
        return [str(chunk.relative_to(ROOT))]
    print(f"[warn] status field not found for {node_id} in {chunk.relative_to(ROOT)}")
    print("       Set it manually:  status: Complete")
    return []


def _validate_and_export() -> None:
    subprocess.check_call(
        [sys.executable, "-m", "specy_road.cli", "validate"], cwd=ROOT
    )
    subprocess.check_call(
        [sys.executable, "-m", "specy_road.cli", "export"], cwd=ROOT
    )


def main() -> None:
    branch = _current_branch()
    if not branch.startswith("feature/rm-"):
        print(
            f"error: current branch '{branch}' is not a roadmap feature branch "
            "(expected feature/rm-<codename>).",
            file=sys.stderr,
        )
        raise SystemExit(1)

    codename, reg, entry, nodes = _resolve_context(branch)
    node_id = entry["node_id"]
    node = next(n for n in nodes if n["id"] == node_id)

    print(f"Finishing [{node_id}] {node.get('title', '')}")
    print(f"Branch:   {branch}\n")

    changed_files = _update_chunk_status(node_id)
    changed_files.append(str(REGISTRY_PATH.relative_to(ROOT)))

    reg["entries"] = [e for e in reg.get("entries", []) if e.get("codename") != codename]
    _save_registry(reg)
    print(f"[ok] removed registry entry for '{codename}'\n")

    print("-> specy-road validate")
    print("-> specy-road export")
    _validate_and_export()

    changed_files.append("roadmap.md")
    _git("add", *changed_files)
    _git("commit", "-m", f"chore(rm-{codename}): complete, deregister")
    print("\n[ok] bookkeeping committed")

    title = f"[{node_id}] {node.get('title', '')}"
    print()
    print("-" * 60)
    print("Branch ready. Push and open a PR:")
    print(f"  git push -u origin {branch}")
    print(f'  gh pr create --base main --head {branch} --title "{title}"')
    print("-" * 60)


if __name__ == "__main__":
    main()
