#!/usr/bin/env python3
"""Generate a deterministic work-packet brief for a roadmap node (``specy-road brief``).

Inlines node metadata, planning sheets, cited ``shared/`` contracts, dependencies,
dependency intent, touch-zone instructions, and optional history. Same inputs =>
byte-identical output.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from specy_road.bundled_scripts.brief_acceptance import print_size_warning, render_goal_and_acceptance, with_size_line
from specy_road.bundled_scripts.brief_dependency_context import render_dependency_context_section

from specy_road import contract_citations
from specy_road.text_sections import read_text_safely as _read_text_safely
from specy_road.bundled_scripts.planning_artifacts import (
    ancestor_planning_paths,
    normalize_planning_dir,
    planning_artifact_paths,
)
from specy_road.bundled_scripts.roadmap_gui_lib import registry_by_node_id
from specy_road.bundled_scripts.roadmap_load import load_roadmap
from specy_road.bundled_scripts.roadmap_node_keys import build_key_to_node
from specy_road.milestone_subtree import structural_leaf_ids
from specy_road.registry_yaml import read_registry, registry_path
from specy_road.runtime_paths import add_repo_root_arg, default_user_repo_root, project_prefix


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


def leaf_claim_entry(
    node_id: str, *, leaf_ids: set[str], by_reg: dict[str, dict]
) -> dict | None:
    if node_id not in leaf_ids:
        return None
    entry = by_reg.get(node_id)
    br = entry.get("branch") if entry else None
    return entry if isinstance(br, str) and br.strip() else None


def list_nodes_status_label(node: dict, claim: dict | None) -> str:
    raw = str(node.get("status", ""))
    return f"{raw} (claimed)" if claim else raw


def list_nodes_json_row(node: dict, chunk_rel: str | None, claim: dict | None) -> dict:
    row = {**node, "chunk": chunk_rel, "claimed": bool(claim)}
    if claim:
        row["branch"] = claim["branch"]
    return row


def brief_status_own_line(node: dict, claim: dict | None) -> str:
    status = node.get("status")
    if not claim:
        return str(status)
    line = f"{status} — claim `{claim.get('branch', '')}`"
    owner = claim.get("owner")
    if isinstance(owner, str) and owner.strip():
        line += f" (owner: {owner.strip()})"
    return line


# Section renderers


def _section_header(node_id: str, title: str, codename: str | None) -> list[str]:
    cn = f" `{codename}`" if codename else ""
    return [
        f"# Work-packet brief: `{node_id}` — {title}{cn}",
        "",
        "_This is a deterministic compilation of every artifact the "
        "implementer needs. Read top to bottom._",
        "",
    ]


def _project_root_line(nid: str, prefix: str) -> list[str]:
    if not prefix:
        return []
    return [f"- **Project root:** `{prefix}` under the git root. Work from the git root; from there this "
            f"leaf's implementation summary is `{prefix}work/implementation-summary-{nid}.md` and its review "
            f"hand-offs go in `{prefix}work/reviews/{nid}/` of the main checkout — never in the git root's `work/`."]


def _section_metadata(node: dict, prefix: str = "", claim: dict | None = None) -> list[str]:
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
        f"- **Status (own):** {brief_status_own_line(node, claim)}",
        f"- **Status (rollup):** {rollup}",
        f"- **Execution (milestone hint):** {node.get('execution_milestone') or '—'}",
        f"- **Touch zones:** {tz_str}",
        *_project_root_line(nid, prefix),
        "",
    ] + render_goal_and_acceptance(node)


def _section_ancestor_chain(chain: list[dict]) -> list[str]:
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


def _inline_planning(
    node: dict, root: Path, by_id: dict[str, dict]
) -> list[str]:
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


def _chain_sheet_paths(
    node: dict, root: Path, by_id: dict[str, dict]
) -> list[Path]:
    paths = [p for _rel, p in ancestor_planning_paths(node["id"], by_id, root)]
    pd = node.get("planning_dir")
    if isinstance(pd, str) and pd.strip():
        try:
            norm = normalize_planning_dir(pd.strip())
            paths.append(planning_artifact_paths(root, norm)["sheet"])
        except ValueError:
            pass  # section 3 already reports the invalid planning_dir
    return paths


def _human_size(n: int) -> str:
    return f"{n / 1024:.0f} KB" if n >= 1024 else f"{n} B"


def _contract_body(root: Path, rel: str) -> list[str]:
    text, ok = _read_text_safely(root / rel)
    return [f"### `{rel}`", "", text.rstrip() if ok else "_(unreadable)_", ""]


def _uncited_listing(root: Path, uncited: list[str]) -> list[str]:
    sizes = [(rel, (root / rel).stat().st_size) for rel in uncited]
    out = [
        f"**Not inlined** — {len(uncited)} "
        f"contract{'s' if len(uncited) != 1 else ''}, "
        f"{_human_size(sum(n for _, n in sizes))}. "
        "Cite one in your planning sheet's `## References` to inline it, "
        "or reach it directly:",
        "",
    ]
    out.extend(f"- `{rel}` ({_human_size(n)})" for rel, n in sizes)
    out.extend(["", '    specy-road search "<query>" --kind shared', ""])
    return out


def _inline_shared_contracts(
    root: Path, cited: list[str], *, inline_all: bool = False
) -> list[str]:
    out = ["## 4. Shared contracts (cited)", ""]
    if not (root / contract_citations.SHARED_DIR).is_dir():
        return [*out, "_(no `shared/` directory in this repo)_", ""]
    every = contract_citations.all_contracts(root)
    if not every:
        return [*out, "_(no `shared/**/*.md` files yet)_", ""]

    if inline_all:
        inline = every
    else:
        keep = set(cited)
        if contract_citations.SHARED_README in every:
            keep.add(contract_citations.SHARED_README)
        inline = sorted(keep)

    for rel in inline:
        out.extend(_contract_body(root, rel))
    inlined = set(inline)
    uncited = [rel for rel in every if rel not in inlined]
    if uncited:
        out.extend(_uncited_listing(root, uncited))
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
    tz = node.get("touch_zones") or []
    out = ["## 7. Touch zones — implementing agent instruction", ""]
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
        "## 8. Rollup semantics (reference)",
        "",
        "- Ancestor `rollup_status` is computed from leaf descendants.",
        "- A non-leaf is `Complete` only when every leaf descendant is `Complete`.",
        "- Otherwise the ancestor inherits the most pressing non-complete status "
        "(`Blocked` > `In Progress` > `Not Started`).",
        "- Pickup targets actionable leaves; ancestors are context-only.",
        "",
    ]


def render_brief(
    node_id: str,
    by_id: dict[str, dict],
    *,
    repo_root: Path | None = None,
    include_history: bool = True,
    all_contracts: bool = False,
) -> str:
    root = repo_root or default_user_repo_root()
    n = by_id[node_id]
    nodes = list(by_id.values())
    reg = read_registry(registry_path(root))
    claim = leaf_claim_entry(
        node_id,
        leaf_ids=structural_leaf_ids(nodes),
        by_reg=registry_by_node_id(reg),
    )
    chain = ancestors(node_id, by_id) + [n]
    cited = contract_citations.cited_contracts(
        _chain_sheet_paths(n, root, by_id), root
    )

    parts: list[list[str]] = [
        _section_header(node_id, n.get("title", ""), n.get("codename")),
        _section_metadata(n, project_prefix(root), claim),
        _section_ancestor_chain(chain),
        _inline_planning(n, root, by_id),
        _inline_shared_contracts(root, cited, inline_all=all_contracts),
        _section_dependencies(n, by_id),
        render_dependency_context_section(n, by_id, root),
        _section_touch_zone_instruction(n),
        _section_rollup_semantics(),
    ]
    if include_history:
        from specy_road.bundled_scripts.brief_history_context import render_history_section

        parts.append(render_history_section(n, by_id, root))
    return with_size_line(parts[0], [ln for p in parts[1:] for ln in p])


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("node_id", help="Roadmap node id, e.g. M1.1")
    p.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Write markdown to this file (default: stdout)",
    )
    add_repo_root_arg(p)
    p.add_argument(
        "--no-history",
        action="store_true",
        help="Omit the git-derived history section (## 9).",
    )
    p.add_argument(
        "--all-contracts",
        action="store_true",
        help=(
            "Inline every shared/**/*.md instead of only those cited in the "
            "planning chain's `## References`. Restores pre-0.2.1 behaviour."
        ),
    )
    args = p.parse_args()
    root = (args.repo_root or default_user_repo_root()).resolve()

    nodes = load_nodes(root)
    by_id = index(nodes)
    if args.node_id not in by_id:
        raise SystemExit(f"unknown node id: {args.node_id}")

    text = render_brief(
        args.node_id,
        by_id,
        repo_root=root,
        include_history=not args.no_history,
        all_contracts=args.all_contracts,
    )
    print_size_warning(text)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
        print(f"Wrote {args.output}")
    else:
        print(text, end="")


if __name__ == "__main__":
    main()
