#!/usr/bin/env python3
"""Export the merged roadmap graph to ``roadmap.md`` (read-only index).

Canonical nodes live in **JSON** chunk files listed by ``roadmap/manifest.json``.
This script writes only the generated root ``roadmap.md`` index — it does not overwrite chunk files.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from roadmap_chunk_utils import discover_manifest_path
from roadmap_layout import natural_id_sort_key
from roadmap_load import load_roadmap

from specy_road.runtime_paths import default_user_repo_root

BANNER = (
    "<!-- specy-road: generated index from merged roadmap (manifest.json + chunk files) "
    "— do not edit by hand -->\n"
)


def gate_display(node: dict) -> str:
    em = node.get("execution_milestone")
    if em:
        return str(em)
    return "—"


def _status_display(node: dict) -> str:
    """Prefer rollup_status (computed from descendants) over raw status."""
    rs = node.get("rollup_status")
    if isinstance(rs, str) and rs:
        return rs
    return str(node.get("status", ""))


def render_index(nodes: list[dict]) -> str:
    lines = [
        "# Roadmap index",
        "",
        BANNER.rstrip(),
        "",
        "Gate maps milestone execution: **Human-led** / **Agentic-led** / **Mixed**. "
        "All leaf tasks are agentic by design.",
        "",
        "Status shown is the **computed rollup status**: for leaves, the node's own status; "
        "for non-leaves, the roll-up over leaf descendants (Complete when every leaf descendant "
        "is Complete; otherwise the most-pressing non-complete status).",
        "",
        "| ID | Title | Type | Gate | Status |",
        "|----|-------|------|------|--------|",
    ]
    for n in sorted(nodes, key=lambda x: natural_id_sort_key(x["id"])):
        tid = n["id"].replace("|", "\\|")
        title = str(n.get("title", "")).replace("|", "\\|")
        typ = n.get("type", "")
        gate = gate_display(n).replace("|", "\\|")
        st = _status_display(n)
        lines.append(f"| `{tid}` | {title} | {typ} | {gate} | {st} |")
    lines.append("")
    lines.append(
        "Chunk files (authoritative definitions): see [`roadmap/manifest.json`](roadmap/manifest.json) "
        "`includes` (e.g. [`roadmap/phases/`](roadmap/phases/))."
    )
    lines.append("")
    return "\n".join(lines)


def _render_details(n: dict, lines: list[str]) -> None:
    """Append goal, decision, and acceptance sections for a node."""
    goal = n.get("goal")
    if goal:
        lines.append(f"**Goal:** {goal}")
        lines.append("")
    decision = n.get("decision")
    if decision:
        if decision.get("status") == "decided":
            date = decision.get("decided_date", "")
            adr = decision.get("adr_ref", "")
            ref = f" — {adr}" if adr else ""
            lines.append(f"> Decided ({date}){ref}")
        else:
            lines.append("> Decision pending")
        lines.append("")
    acceptance = n.get("acceptance")
    if acceptance:
        lines.append("**Acceptance criteria:**")
        for item in acceptance:
            lines.append(f"- {item}")
        lines.append("")
    planning_dir = n.get("planning_dir")
    if planning_dir:
        lines.append(f"**Planning feature sheet:** `{planning_dir}`")
        lines.append("")


def render_phase_doc(phase_id: str, subtree: list[dict]) -> str:
    """Render a phase subtree as a human-readable doc (used by tests / optional tooling)."""
    lines = [
        f"# Phase `{phase_id}`",
        "",
        "| ID | Title | Type | Gate | Status |",
        "|----|-------|------|------|--------|",
    ]
    for n in subtree:
        tid = n["id"].replace("|", "\\|")
        title = str(n.get("title", "")).replace("|", "\\|")
        typ = n.get("type", "")
        gate = gate_display(n).replace("|", "\\|")
        st = n.get("status", "")
        lines.append(f"| `{tid}` | {title} | {typ} | {gate} | {st} |")
    notes = [n for n in subtree if n.get("notes")]
    if notes:
        lines.extend(["", "## Notes", ""])
        for n in notes:
            lines.append(f"- **{n['id']}:** {n['notes']}")
        lines.append("")
    detailed = [
        n
        for n in subtree
        if n.get("goal")
        or n.get("acceptance")
        or n.get("decision")
        or n.get("planning_dir")
    ]
    if detailed:
        lines.extend(["## Details", ""])
        for n in detailed:
            lines.append(f"### `{n['id']}` — {n.get('title', '')}")
            lines.append("")
            _render_details(n, lines)
    return "\n".join(lines)


def export_markdown(nodes: list[dict]) -> str:
    """Return ``roadmap.md`` body (merged graph index only)."""
    return render_index(nodes)


def _write_export(
    root: Path,
    index: str,
    *,
    check: bool,
) -> None:
    out_index = root / "roadmap.md"
    if check:
        if out_index.is_file():
            existing = out_index.read_text(encoding="utf-8")
            if existing != index:
                print(f"drift: {out_index}", file=sys.stderr)
                raise SystemExit(1)
        else:
            print(f"missing {out_index}", file=sys.stderr)
            raise SystemExit(1)
        print("OK: roadmap.md matches merged roadmap graph.")
        return
    out_index.write_text(index, encoding="utf-8")
    print(f"Wrote {out_index}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit 1 if generated files differ from disk (CI drift check)",
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
    try:
        discover_manifest_path(root)
    except FileNotFoundError as e:
        print(str(e), file=sys.stderr)
        raise SystemExit(1) from e
    nodes = load_roadmap(root)["nodes"]
    index = export_markdown(nodes)
    _write_export(root, index, check=args.check)


if __name__ == "__main__":
    main()
