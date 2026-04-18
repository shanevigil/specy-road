#!/usr/bin/env python3
"""Generate a comprehensive work-packet brief for a roadmap node.

F-004: ``specy-road brief`` is a deterministic agent-handoff document that
inlines all the context an implementer needs (no separate file-opening):

* node metadata (id, codename, title, status, rollup, touch zones)
* ancestor context chain (program -> phase -> milestone -> task)
* every ancestor planning sheet body, in chain order
* this node's planning sheet body
* every cited shared contract under shared/ (full body, deterministic order)
* dependency list (resolved from node_key UUIDs to display ids)
* an explicit touch-zone instruction for the implementing agent

Determinism: same chunks + same planning files + same shared/*.md set =>
byte-identical output. No timestamps, no host info.

Output: stdout by default; ``-o PATH`` writes to a file.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from planning_artifacts import (
    ancestor_planning_paths,
    normalize_planning_dir,
    planning_artifact_paths,
)
from roadmap_load import load_roadmap
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


# ---------------------------------------------------------------------------
# Section renderers
# ---------------------------------------------------------------------------


def _section_header(node_id: str, title: str, codename: str | None) -> list[str]:
    cn = f" `{codename}`" if codename else ""
    return [
        f"# Work-packet brief: `{node_id}` — {title}{cn}",
        "",
        "_This is a deterministic compilation of every artifact the "
        "implementer needs. Read top to bottom._",
        "",
    ]


def _section_metadata(node: dict) -> list[str]:
    nid = node["id"]
    rollup = node.get("rollup_status") or node.get("status")
    tz = node.get("touch_zones") or []
    tz_str = ", ".join(tz) if tz else "_(unspecified — discover via codebase scan; see Touch zones section below)_"
    return [
        "## 1. Execution target",
        "",
        f"- **Node id:** `{nid}`",
        f"- **Title:** {node.get('title', '')}",
        f"- **Codename:** `{node.get('codename') or '—'}`",
        f"- **Type:** {node.get('type', '')}",
        f"- **Status (own):** {node.get('status')}",
        f"- **Status (rollup):** {rollup}",
        f"- **Execution (milestone hint):** {node.get('execution_milestone') or '—'}",
        f"- **Touch zones:** {tz_str}",
        "",
    ]


def _section_ancestor_chain(chain: list[dict]) -> list[str]:
    """Render the ancestor chain as a 1-line bullet per ancestor."""
    if len(chain) <= 1:
        return ["## 2. Ancestor context chain", "", "_(no ancestors — this is a root node)_", ""]
    lines = ["## 2. Ancestor context chain", ""]
    for item in chain[:-1]:
        tid = item["id"]
        typ = item.get("type", "")
        ttl = item.get("title", "")
        status = item.get("rollup_status") or item.get("status")
        lines.append(f"- **{tid}** ({typ}) — {ttl} _(rollup: {status})_")
    lines.append("")
    return lines


def _read_text_safely(path: Path) -> tuple[str, bool]:
    """Read a file; return (text, ok). Missing/unreadable files yield ('', False)."""
    if not path.is_file():
        return "", False
    try:
        return path.read_text(encoding="utf-8"), True
    except (OSError, UnicodeDecodeError):
        return "", False


def _inline_planning(
    node: dict, root: Path, by_id: dict[str, dict]
) -> list[str]:
    """Section 3: inline every relevant planning sheet body verbatim."""
    nid = node["id"]
    out = ["## 3. Planning context (inlined)", ""]
    anc = ancestor_planning_paths(nid, by_id, root)
    for rel, p in anc:
        text, ok = _read_text_safely(p)
        out.append(f"### Ancestor planning sheet: `{rel}`")
        out.append("")
        if ok:
            out.append(text.rstrip())
        else:
            out.append(f"_(not present on disk: `{rel}`)_")
        out.append("")
    pd = node.get("planning_dir")
    if isinstance(pd, str) and pd.strip():
        try:
            norm = normalize_planning_dir(pd.strip())
            paths = planning_artifact_paths(root, norm)
            p = paths["sheet"]
            rel = p.relative_to(root)
            text, ok = _read_text_safely(p)
            out.append(f"### This node's planning sheet: `{rel}`")
            out.append("")
            if ok:
                out.append(text.rstrip())
            else:
                out.append(f"_(not present on disk: `{rel}`)_")
            out.append("")
        except ValueError as e:
            out.append(f"_(invalid planning_dir on this node: {e})_")
            out.append("")
    if not anc and not pd:
        out.append("_(no planning sheets in the chain)_")
        out.append("")
    return out


def _inline_shared_contracts(root: Path) -> list[str]:
    """Section 4: inline every shared/*.md body in deterministic (sorted) order."""
    out = ["## 4. Shared contracts (inlined, deterministic order)", ""]
    shared = root / "shared"
    if not shared.is_dir():
        out.append("_(no `shared/` directory in this repo)_")
        out.append("")
        return out
    files = sorted(shared.glob("*.md"))
    if not files:
        out.append("_(no `shared/*.md` files yet)_")
        out.append("")
        return out
    for f in files:
        rel = f.relative_to(root)
        text, ok = _read_text_safely(f)
        out.append(f"### `{rel}`")
        out.append("")
        if ok:
            out.append(text.rstrip())
        else:
            out.append("_(unreadable)_")
        out.append("")
    return out


def _section_dependencies(node: dict, by_id: dict[str, dict]) -> list[str]:
    out = ["## 5. Dependencies (must complete first)", ""]
    deps = node.get("dependencies") or []
    if not deps:
        out.append("- _none_")
        out.append("")
        return out
    by_key = build_key_to_node(list(by_id.values()))
    for d in deps:
        if not isinstance(d, str):
            continue
        dep = by_key.get(d)
        if dep:
            out.append(f"- **{dep.get('id', d)}** — {dep.get('title', '(no title)')}")
        else:
            out.append(f"- **{d}** — _(missing node for this node_key)_")
    out.append("")
    return out


def _section_touch_zone_instruction(node: dict) -> list[str]:
    """F-009: explicit instruction to the implementing agent."""
    tz = node.get("touch_zones") or []
    out = ["## 6. Touch zones — implementing agent instruction", ""]
    if tz:
        out.append(
            "The PM listed these touch zones: "
            + ", ".join(f"`{z}`" for z in tz)
            + "."
        )
        out.append("")
        out.append(
            "**TODO (DEV agent):** confirm these touch zones are accurate by "
            "scanning the codebase. Add or remove zones as appropriate, then "
            "report the final list in your implementation summary."
        )
    else:
        out.append(
            "**TODO (DEV agent):** the PM did not specify touch zones. "
            "Scan the codebase to identify the files this work packet will "
            "touch, propose a `touch_zones` list (sorted, lowest-common-"
            "ancestor paths), and include it in your implementation summary."
        )
    out.append("")
    return out


def _section_rollup_semantics() -> list[str]:
    return [
        "## 7. Rollup semantics (reference)",
        "",
        "- Ancestor `rollup_status` is computed from leaf descendants.",
        "- A non-leaf is `Complete` only when every leaf descendant is `Complete`.",
        "- Otherwise the ancestor inherits the most pressing non-complete status "
        "(`Blocked` > `In Progress` > `Not Started`).",
        "- Pickup targets actionable leaves; ancestors are context-only.",
        "",
    ]


# ---------------------------------------------------------------------------
# Top-level render
# ---------------------------------------------------------------------------


def render_brief(
    node_id: str, by_id: dict[str, dict], *, repo_root: Path | None = None
) -> str:
    root = repo_root or default_user_repo_root()
    n = by_id[node_id]
    chain = ancestors(node_id, by_id) + [n]

    parts: list[list[str]] = [
        _section_header(node_id, n.get("title", ""), n.get("codename")),
        _section_metadata(n),
        _section_ancestor_chain(chain),
        _inline_planning(n, root, by_id),
        _inline_shared_contracts(root),
        _section_dependencies(n, by_id),
        _section_touch_zone_instruction(n),
        _section_rollup_semantics(),
    ]
    return "\n".join("\n".join(p) for p in parts).rstrip() + "\n"


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
