"""Agent-facing prompt markdown for ``do-next-available-task``."""

from __future__ import annotations

from pathlib import Path

from generate_brief import index as make_index
from specy_road.git_workflow_config import (
    require_implementation_review_before_finish,
)
from planning_artifacts import (
    ancestor_planning_paths,
    normalize_planning_dir,
    planning_artifact_paths,
    split_frontmatter,
)

_LEAF_EXCERPT_MAX_LINES = 80

_GOVERNANCE_FILES: tuple[tuple[str, str], ...] = (
    ("constitution/purpose.md", "Purpose"),
    ("constitution/principles.md", "Principles"),
    ("constraints/README.md", "Constraints index"),
)


def _governance_lines(root: Path) -> list[str]:
    lines = [
        "## Read first (governance)",
        "",
        "Same order as `AGENTS.md` in this repository:",
        "",
    ]
    for rel, label in _GOVERNANCE_FILES:
        p = root / rel
        if p.is_file():
            lines.append(f"- **{label}:** `{rel}`")
        else:
            lines.append(f"- **{label}:** _(missing — add or ask PM)_")
    lines.append("")
    return lines


def _ancestor_planning_lines(
    node_id: str,
    by_id: dict[str, dict],
    root: Path,
) -> list[str]:
    lines = [
        "## Ancestor planning sheets",
        "",
        "Read in list order (program → phase → milestone):",
        "",
    ]
    anc = ancestor_planning_paths(node_id, by_id, root)
    if not anc:
        lines.append("_No ancestors with `planning_dir` set._")
    else:
        for rel, p in anc:
            state = "present" if p.is_file() else "missing"
            lines.append(f"- `{rel}` ({state})")
    lines.append("")
    return lines


def _leaf_planning_excerpt_lines(node: dict, root: Path) -> list[str]:
    lines = ["## Task planning sheet (excerpt)", ""]
    pd = node.get("planning_dir")
    if not isinstance(pd, str) or not pd.strip():
        lines.append(
            "_No `planning_dir` on this node — coordinate scope with PM._",
        )
        lines.append("")
        return lines
    try:
        norm = normalize_planning_dir(pd.strip())
    except ValueError as e:
        lines.append(f"_(invalid planning_dir: {e})_")
        lines.append("")
        return lines
    paths = planning_artifact_paths(root, norm)
    sheet = paths["sheet"]
    rel = sheet.relative_to(root)
    if not sheet.is_file():
        lines.append(f"`{rel}` _(file missing)_")
        lines.append("")
        return lines
    text = sheet.read_text(encoding="utf-8")
    _fm, body = split_frontmatter(text)
    body_lines = body.strip().splitlines()
    excerpt = body_lines[:_LEAF_EXCERPT_MAX_LINES]
    cap = _LEAF_EXCERPT_MAX_LINES
    lines.append(
        f"From `{rel}` (first {cap} lines of body, after frontmatter):",
    )
    lines.append("")
    lines.append("```markdown")
    lines.extend(excerpt)
    if len(body_lines) > _LEAF_EXCERPT_MAX_LINES:
        lines.append("…")
    lines.append("```")
    lines.append("")
    return lines


def _on_complete_hint_lines(on_complete: str) -> list[str]:
    oc = (on_complete or "pr").strip().lower()
    if oc == "merge":
        return [
            (
                "**Completion workflow (this task):** `merge` — when you run "
                "`specy-road finish-this-task`, the toolkit marks the node complete, "
                "removes the registry entry, then tries to **merge this feature branch "
                "into the integration branch locally** and **push** the integration "
                "branch. Resolve conflicts or open a PR/MR if the merge cannot complete."
            ),
        ]
    if oc == "auto":
        return [
            (
                "**Completion workflow (this task):** `auto` — `finish-this-task` "
                "tries **local merge + push** to the integration branch first; if that "
                "fails (conflicts, branch protection, etc.), it prints **merge pending** "
                "and the same PR/MR guidance as the `pr` mode."
            ),
        ]
    return [
        (
            "**Completion workflow (this task):** `pr` — `finish-this-task` updates "
            "roadmap/registry and JSON, then you **open a pull request (PR) or merge "
            "request (MR)** to the integration branch (GitHub uses “PR”, GitLab uses "
            "“MR”; same idea). Use `finish-this-task --push` to push the feature branch "
            "first if needed."
        ),
    ]


def _leaf_execution_contract_lines(
    node: dict,
    brief_path: Path,
    repo_root: Path,
) -> list[str]:
    node_id = node["id"]
    codename = node["codename"]
    title = node.get("title", "")
    return [
        f"# Task: {node_id} — {title}",
        "",
        (
            f"You are planning and implementing roadmap leaf "
            f"**{node_id}** (`{codename}`)."
        ),
        "",
        "## Execution Target",
        "",
        f"- **Execution Target (leaf):** `{node_id}`",
        f"- **Codename:** `{codename}`",
        "- Exactly one leaf is claimed and implemented for this pickup.",
        "",
        "## Ancestor Context Chain",
        "",
        "- Ancestors provide objective/context only (root → ... → parent).",
        "- Do not claim or branch directly from ancestor umbrella nodes.",
        "",
        "## Derived Rollup Semantics",
        "",
        (
            "- Ancestor in-progress state is derived from active descendant "
            "claims."
        ),
        (
            "- Ancestor completion is derived from descendant "
            "completion semantics."
        ),
        "",
        f"Read the full brief at `{brief_path.relative_to(repo_root)}`.",
        "",
    ]


def _finish_instruction_lines(
    node_id: str,
    repo_root: Path,
    *,
    on_complete: str,
) -> list[str]:
    base = [
        (
            "1. Read governance docs and planning sheets above, "
            "then the brief and contracts."
        ),
        "2. Stay within the declared touch zones.",
        (
            "3. Commit incrementally — the pre-commit hook validates "
            "on every commit."
        ),
    ]
    oc_lines = _on_complete_hint_lines(on_complete)
    if require_implementation_review_before_finish(repo_root):
        return base + oc_lines + [
            (
                f"4. When implementation is complete, write "
                f"`work/implementation-summary-{node_id}.md` with sections "
                "**Summary**, **Changes**, **Verification**, and optional "
                "**## Walkthrough** (numbered steps for the reviewer)."
            ),
            (
                "5. Hand off for human review. The developer runs "
                "`specy-road mark-implementation-reviewed` (reads the summary; "
                "optional walkthrough menu), then `specy-road finish-this-task`."
            ),
            (
                "**Do not** run `finish-this-task` yourself until review is "
                "recorded — the registry must show implementation review approved."
            ),
        ]
    return base + oc_lines + [
        (
            "4. When complete: run `specy-road finish-this-task` "
            "to close out the branch."
        ),
    ]


def write_agent_prompt(
    node: dict,
    nodes: list[dict],
    brief_path: Path,
    *,
    repo_root: Path,
    work_dir: Path,
    on_complete: str = "pr",
) -> Path:
    """Write ``work/prompt-<NODE_ID>.md`` and return its path."""
    node_id = node["id"]
    ac = node.get("agentic_checklist") or {}
    by_id = make_index(nodes)

    lines: list[str] = _leaf_execution_contract_lines(node, brief_path, repo_root)
    lines.extend(_governance_lines(repo_root))
    lines.extend(_ancestor_planning_lines(node_id, by_id, repo_root))
    lines.extend(_leaf_planning_excerpt_lines(node, repo_root))
    lines.extend([
        "## Contract (agentic checklist)",
        "",
    ])
    if ac:
        for key in (
            "artifact_action",
            "contract_citation",
            "interface_contract",
            "constraints_note",
            "dependency_note",
        ):
            lines.append(f"- **{key}:** {ac.get(key, '—')}")
    else:
        lines.append(
            "_(no agentic_checklist — check with PM before starting)_",
        )

    lines += ["", "## Instructions", ""]
    lines += _finish_instruction_lines(
        node_id,
        repo_root,
        on_complete=on_complete,
    )

    work_dir.mkdir(parents=True, exist_ok=True)
    path = work_dir / f"prompt-{node_id}.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
