#!/usr/bin/env python3
"""Export the roadmap graph to roadmap.md (index) and roadmap/phases/*.md.

Canonical source is under roadmap/ (roadmap.yaml manifest and chunk files, or legacy inline nodes).
Markdown is a human-readable view.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from roadmap_load import load_roadmap

ROOT = Path(__file__).resolve().parent.parent
ROADMAP_YAML = ROOT / "roadmap" / "roadmap.yaml"
OUT_INDEX = ROOT / "roadmap.md"
OUT_PHASES = ROOT / "roadmap" / "phases"

BANNER = (
    "<!-- specy-road: generated from roadmap graph (roadmap.yaml + includes) "
    "— do not edit by hand -->\n"
)


def sort_key(nid: str) -> tuple[int, ...]:
    """Sort M0 < M0.1 < M0.1.1 < M1."""
    parts = nid[1:].split(".") if nid.startswith("M") else nid.split(".")
    return tuple(int(p) for p in parts if p.isdigit())


def gate_display(node: dict) -> str:
    sub = node.get("execution_subtask")
    if sub == "human-gate":
        return "Human gate"
    if sub == "agentic":
        return "Agentic"
    if sub == "human":
        return "Human"
    em = node.get("execution_milestone")
    if em:
        return str(em)
    return "—"


def children_of(parent_id: str | None, nodes: list[dict]) -> list[dict]:
    out = [n for n in nodes if n.get("parent_id") == parent_id]
    return sorted(out, key=lambda n: sort_key(n["id"]))


def collect_subtree(root_id: str, by_id: dict[str, dict]) -> list[dict]:
    out: list[dict] = []

    def walk(nid: str) -> None:
        n = by_id[nid]
        out.append(n)
        for c in children_of(nid, list(by_id.values())):
            walk(c["id"])

    walk(root_id)
    return out


def render_index(nodes: list[dict]) -> str:
    lines = [
        "# Roadmap index",
        "",
        BANNER.rstrip(),
        "",
        "Gate maps milestone/task execution: **Human-led** / **Agentic-led** / **Mixed**, or sub-task "
        "**Human** / **Agentic** / **Human gate** when `execution_subtask` is set.",
        "",
        "| ID | Title | Type | Gate | Status |",
        "|----|-------|------|------|--------|",
    ]
    for n in sorted(nodes, key=lambda x: sort_key(x["id"])):
        tid = n["id"].replace("|", "\\|")
        title = str(n.get("title", "")).replace("|", "\\|")
        typ = n.get("type", "")
        gate = gate_display(n).replace("|", "\\|")
        st = n.get("status", "")
        lines.append(f"| `{tid}` | {title} | {typ} | {gate} | {st} |")
    lines.append("")
    lines.append("Phase detail: [`roadmap/phases/`](roadmap/phases/).")
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


def render_phase_doc(phase_id: str, subtree: list[dict]) -> str:
    lines = [
        f"# Phase `{phase_id}`",
        "",
        BANNER.rstrip(),
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
        n for n in subtree
        if n.get("goal") or n.get("acceptance") or n.get("decision")
    ]
    if detailed:
        lines.extend(["## Details", ""])
        for n in detailed:
            lines.append(f"### `{n['id']}` — {n.get('title', '')}")
            lines.append("")
            _render_details(n, lines)
    return "\n".join(lines)


def export_markdown(nodes: list[dict]) -> tuple[str, dict[str, str]]:
    by_id = {n["id"]: n for n in nodes}
    phase_roots = [
        n for n in nodes if n.get("type") == "phase" and n.get("parent_id") is None
    ]
    phase_roots = sorted(phase_roots, key=lambda n: sort_key(n["id"]))

    index = render_index(nodes)
    phase_files: dict[str, str] = {}
    for pr in phase_roots:
        pid = pr["id"]
        subtree = collect_subtree(pid, by_id)
        phase_files[f"{pid}.md"] = render_phase_doc(pid, subtree)
    return index, phase_files


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit 1 if generated files differ from disk (CI drift check)",
    )
    args = parser.parse_args()

    if not ROADMAP_YAML.is_file():
        print(f"missing {ROADMAP_YAML}", file=sys.stderr)
        raise SystemExit(1)

    nodes = load_roadmap(ROOT)["nodes"]

    index, phase_files = export_markdown(nodes)

    if args.check:
        if OUT_INDEX.is_file():
            existing = OUT_INDEX.read_text(encoding="utf-8")
            if existing != index:
                print(f"drift: {OUT_INDEX}", file=sys.stderr)
                raise SystemExit(1)
        else:
            print(f"missing {OUT_INDEX}", file=sys.stderr)
            raise SystemExit(1)
        for name, content in sorted(phase_files.items()):
            path = OUT_PHASES / name
            if not path.is_file():
                print(f"missing {path}", file=sys.stderr)
                raise SystemExit(1)
            if path.read_text(encoding="utf-8") != content:
                print(f"drift: {path}", file=sys.stderr)
                raise SystemExit(1)
        print("OK: markdown export matches roadmap graph.")
        return

    OUT_INDEX.write_text(index, encoding="utf-8")
    OUT_PHASES.mkdir(parents=True, exist_ok=True)
    for name, content in phase_files.items():
        (OUT_PHASES / name).write_text(content, encoding="utf-8")
    print(f"Wrote {OUT_INDEX} and {len(phase_files)} file(s) under {OUT_PHASES}")


if __name__ == "__main__":
    main()
