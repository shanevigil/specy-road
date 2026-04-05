#!/usr/bin/env python3
"""Emit a bounded brief for a roadmap node (ancestors, deps, touch zones)."""

from __future__ import annotations

import argparse
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
ROADMAP = ROOT / "roadmap" / "roadmap.yaml"
SHARED = ROOT / "shared"


def load_nodes() -> list[dict]:
    with ROADMAP.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data["nodes"]


def index(nodes: list[dict]) -> dict[str, dict]:
    return {n["id"]: n for n in nodes}


def ancestors(nid: str, by_id: dict[str, dict]) -> list[dict]:
    out: list[dict] = []
    cur = by_id.get(nid)
    if not cur:
        return out
    pid = cur.get("parent_id")
    while pid:
        p = by_id.get(pid)
        if not p:
            break
        out.append(p)
        pid = p.get("parent_id")
    return list(reversed(out))


def _brief_deps_and_contracts(n: dict, deps: list, by_id: dict[str, dict]) -> list[str]:
    lines: list[str] = [
        "",
        "## Dependencies (must complete first)",
        "",
    ]
    if deps:
        for d in deps:
            dn = by_id.get(d, {})
            lines.append(f"- **{d}** — {dn.get('title', '(missing node)')}")
    else:
        lines.append("- _none_")
    lines.extend(
        [
            "",
            "## Contracts (read selectively)",
            "",
            "Load only what you need from `shared/` (see `shared/README.md`).",
            "",
        ]
    )
    if SHARED.is_dir():
        for f in sorted(SHARED.glob("*.md")):
            lines.append(f"- `{f.relative_to(ROOT)}`")
    else:
        lines.append("- _(no shared/*.md yet)_")
    return lines


def render_brief(node_id: str, by_id: dict[str, dict]) -> str:
    n = by_id[node_id]
    chain = ancestors(node_id, by_id) + [n]
    deps = n.get("dependencies") or []

    head = [
        f"# Brief: `{node_id}` — {n.get('title', '')}",
        "",
        "## Ancestor chain",
        "",
    ]
    for item in chain:
        tid = item["id"]
        typ = item.get("type")
        ttl = item.get("title", "")
        head.append(f"- **{tid}** ({typ}) — {ttl}")
    head.extend(
        [
            "",
            "## This node",
            "",
            f"- **Status:** {n.get('status')}",
            f"- **Execution (milestone):** {n.get('execution_milestone')}",
            f"- **Execution (sub-task):** {n.get('execution_subtask')}",
            f"- **Codename:** {n.get('codename')}",
            (
                "- **Touch zones:** "
                f"{', '.join(n.get('touch_zones') or []) or '—'}"
            ),
        ]
    )
    ac = n.get("agentic_checklist")
    if isinstance(ac, dict):
        head.extend(["", "## Agentic checklist", ""])
        for key in (
            "artifact_action",
            "spec_citation",
            "interface_contract",
            "constraints_note",
            "dependency_note",
        ):
            head.append(f"- **{key}:** {ac.get(key, '—')}")
    tail = _brief_deps_and_contracts(n, deps, by_id)
    return "\n".join(head + tail) + "\n"


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("node_id", help="Roadmap node id, e.g. M1.1")
    p.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Write markdown to this file (default: stdout)",
    )
    args = p.parse_args()

    nodes = load_nodes()
    by_id = index(nodes)
    if args.node_id not in by_id:
        raise SystemExit(f"unknown node id: {args.node_id}")

    text = render_brief(args.node_id, by_id)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
        print(f"Wrote {args.output}")
    else:
        print(text, end="")


if __name__ == "__main__":
    main()
