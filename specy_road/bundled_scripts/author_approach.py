#!/usr/bin/env python3
"""``specy-road author-approach <ID> [<ID>...]``: the prompt that writes a leaf's ``## Approach``.

Pickup skips a leaf while its ``## Approach`` is still brainstorm promote's or
scaffold-planning's placeholder (M3.1). For each such leaf this prints the
node's title, acceptance, touch zones and ancestor Intent, then asks for the
Approach (constraints, steps, how to verify) and a commit of the sheet alone.
A leaf whose Approach is already written is reported and skipped. Read-only,
except that ``-o`` writes ``work/prompt-approach-<ID>.md`` instead of printing.
It never writes the Approach itself.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from specy_road.bundled_scripts.brief_dependency_context import extract_intent_block
from specy_road.bundled_scripts.planning_artifacts import normalize_planning_dir, resolve_planning_path
from specy_road.bundled_scripts.planning_sheet_bootstrap import _section_bodies, approach_is_placeholder
from specy_road.bundled_scripts.roadmap_load import load_roadmap
from specy_road.milestone_subtree import structural_leaf_ids
from specy_road.runtime_paths import add_repo_root_arg, resolve_repo_root


def _sheet(root: Path, node: dict) -> tuple[str, str] | None:
    """``(rel, text)`` of the node's planning sheet, or ``None`` when it has none on disk."""
    try:
        rel = normalize_planning_dir(str(node.get("planning_dir") or ""))
        return rel, resolve_planning_path(root, rel).read_text(encoding="utf-8")
    except (OSError, ValueError):
        return None


def _ancestor_intents(root: Path, node: dict, by_id: dict[str, dict]) -> list[str]:
    """``### <id> — <title>`` and its Intent for each ancestor with one, root first."""
    out: list[str] = []
    parent = by_id.get(node.get("parent_id") or "")
    while parent is not None:
        sheet = _sheet(root, parent)
        intent = extract_intent_block(sheet[1], parent.get("type")) if sheet else None
        if intent:
            out[:0] = [f"### {parent['id']} — {parent.get('title', '')}", "", intent.strip(), ""]
        parent = by_id.get(parent.get("parent_id") or "")
    return out


def render_prompt(root: Path, node: dict, by_id: dict[str, dict], rel: str) -> str:
    """The prompt that asks an agent to write ``node``'s ``## Approach`` in ``rel``."""
    nid = node["id"]
    acceptance = [a for a in node.get("acceptance") or [] if isinstance(a, str) and a.strip()]
    zones = node.get("touch_zones") or []
    lines = [
        f"# Write the ## Approach for `{nid}`", "",
        f"Pickup skips `{nid}` until its planning sheet `{rel}` has a written `## Approach`.", "",
        f"## Node: {node.get('title', '')}", "",
        "### Acceptance", "",
        *([f"- **A{i}:** {a.strip()}" for i, a in enumerate(acceptance, 1)] or ["_(none set)_"]), "",
        "### Touch zones", "",
        *([f"- `{z}`" for z in zones] or ["_(none set)_"]), "",
        "## Ancestor Intent", "",
        *(_ancestor_intents(root, node, by_id) or ["_(no ancestor Intent)_", ""]),
        "## Task", "",
        f"1. Read `{rel}` and the files the touch zones name.",
        "2. Replace the placeholder under `## Approach` with the constraints, the major steps, "
        "and how you will verify the acceptance above. Keep any constraints already listed there.",
        "3. Change no other section and no other file.",
        f"4. Commit only the sheet: `git commit --only {rel} -m \"planning({nid}): write Approach\"`.",
        "",
    ]
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="specy-road author-approach",
        description="Print the prompt that writes each leaf's ## Approach while it is still a placeholder.",
    )
    p.add_argument("node_ids", nargs="+", metavar="NODE_ID")
    p.add_argument("-o", "--output", action="store_true",
                   help="write work/prompt-approach-<ID>.md instead of printing")
    add_repo_root_arg(p)
    return p


def main(argv: list[str] | None = None) -> None:
    ns = build_parser().parse_args(argv)
    root = resolve_repo_root(ns)
    nodes = load_roadmap(root)["nodes"]
    by_id = {n["id"]: n for n in nodes}
    leaves = structural_leaf_ids(nodes)
    failed = False
    for nid in ns.node_ids:
        node = by_id.get(nid)
        if node is None or nid not in leaves:
            print(f"error: {nid} is not a leaf in the roadmap", file=sys.stderr)
            failed = True
            continue
        sheet = _sheet(root, node)
        if sheet is None:
            print(f"error: {nid} has no planning sheet (specy-road scaffold-planning {nid})", file=sys.stderr)
            failed = True
            continue
        rel, text = sheet
        if not approach_is_placeholder(_section_bodies(text)):
            print(f"{nid}: ## Approach in {rel} is already written; skipped.", file=sys.stderr)
            continue
        prompt = render_prompt(root, node, by_id, rel)
        if ns.output:
            dest = root / "work" / f"prompt-approach-{nid}.md"
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(prompt, encoding="utf-8")
            print(f"wrote {dest.relative_to(root).as_posix()}")
        else:
            print(prompt)
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
