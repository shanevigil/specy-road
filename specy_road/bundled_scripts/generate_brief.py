#!/usr/bin/env python3
"""Emit a bounded brief for a roadmap node (ancestors, deps, touch zones)."""

from __future__ import annotations

import argparse
from pathlib import Path

from roadmap_load import load_roadmap
from planning_artifacts import (
    ancestor_planning_paths,
    normalize_planning_dir,
    planning_artifact_paths,
)
from roadmap_node_keys import build_key_to_node

from specy_road.runtime_paths import default_user_repo_root


def load_nodes(root: Path | None = None) -> list[dict]:
    return load_roadmap(root or default_user_repo_root())["nodes"]


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


def _brief_deps_and_contracts(
    _n: dict, deps: list, root: Path, by_id: dict[str, dict]
) -> list[str]:
    # dependencies[] stores node_key UUIDs, not display ids — resolve via key map
    by_key = build_key_to_node(list(by_id.values()))
    lines: list[str] = [
        "",
        "## Dependencies (must complete first)",
        "",
    ]
    if deps:
        for d in deps:
            if not isinstance(d, str):
                continue
            dep_node = by_key.get(d)
            if dep_node:
                did = dep_node.get("id", d)
                ttl = dep_node.get("title", "(no title)")
                lines.append(f"- **{did}** — {ttl}")
            else:
                lines.append(f"- **{d}** — (missing node for node_key)")
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
    shared = root / "shared"
    if shared.is_dir():
        for f in sorted(shared.glob("*.md")):
            lines.append(f"- `{f.relative_to(root)}`")
    else:
        lines.append("- _(no shared/*.md yet)_")
    return lines


def _agentic_checklist_lines(n: dict) -> list[str]:
    ac = n.get("agentic_checklist")
    if not isinstance(ac, dict):
        return []
    lines = ["", "## Agentic checklist", ""]
    for key in (
        "artifact_action",
        "contract_citation",
        "interface_contract",
        "constraints_note",
        "dependency_note",
    ):
        lines.append(f"- **{key}:** {ac.get(key, '—')}")
    return lines


def _planning_dir_artifact_lines(
    n: dict, root: Path, by_id: dict[str, dict]
) -> list[str]:
    nid = n["id"]
    lines: list[str] = ["", "## Planning feature sheets", ""]
    anc = ancestor_planning_paths(nid, by_id, root)
    if anc:
        lines.append("Read **ancestor** sheets first (program → phase → milestone), then this node.")
        lines.append("")
        for rel, p in anc:
            state = "present" if p.is_file() else "missing"
            lines.append(f"- **Ancestor:** `{rel}` ({state})")
        lines.append("")
    pd = n.get("planning_dir")
    if not isinstance(pd, str) or not pd.strip():
        if not anc:
            lines.append("- _(no planning_dir on this node)_")
        return lines
    try:
        norm = normalize_planning_dir(pd.strip())
        paths = planning_artifact_paths(root, norm)
        p = paths["sheet"]
        rel = p.relative_to(root)
        state = "present" if p.is_file() else "missing"
        lines.append(f"- **This node:** `{rel}` ({state})")
    except ValueError as e:
        lines.append(f"- _(invalid planning_dir: {e})_")
    return lines


def render_brief(
    node_id: str, by_id: dict[str, dict], *, repo_root: Path | None = None
) -> str:
    root = repo_root or default_user_repo_root()
    n = by_id[node_id]
    chain = ancestors(node_id, by_id) + [n]
    deps = n.get("dependencies") or []

    head = [
        f"# Brief: `{node_id}` — {n.get('title', '')}",
        "",
        "## Execution Target",
        "",
        f"- **Leaf node:** `{node_id}`",
        f"- **Codename:** {n.get('codename')}",
        f"- **Title:** {n.get('title', '')}",
        "",
        "## Ancestor Context Chain",
        "",
    ]
    for item in chain[:-1]:
        tid = item["id"]
        typ = item.get("type")
        ttl = item.get("title", "")
        status = item.get("status")
        head.append(
            f"- **{tid}** ({typ}) — {ttl} "
            f"_(objective context; status: {status})_"
        )
    head.extend(
        [
            "",
            "## Leaf Action Details",
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
    head.extend(
        [
            "",
            "## Derived Rollup Semantics",
            "",
            (
                "- Ancestors are context containers and are not execution "
                "pickup targets."
            ),
            (
                "- Ancestor in-progress state is derived from active "
                "descendant claims."
            ),
            (
                "- Complete ancestor status rolls up from descendant "
                "completion semantics."
            ),
        ]
    )
    head.extend(_agentic_checklist_lines(n))
    head.extend(_planning_dir_artifact_lines(n, root, by_id))
    tail = _brief_deps_and_contracts(n, deps, root, by_id)
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
    p.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        metavar="DIR",
        help="Repository root (default: git root or cwd)",
    )
    args = p.parse_args()
    root = (args.repo_root or default_user_repo_root()).resolve()

    nodes = load_nodes(root)
    by_id = index(nodes)
    if args.node_id not in by_id:
        raise SystemExit(f"unknown node id: {args.node_id}")

    text = render_brief(args.node_id, by_id, repo_root=root)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
        print(f"Wrote {args.output}")
    else:
        print(text, end="")


if __name__ == "__main__":
    main()
