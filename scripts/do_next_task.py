#!/usr/bin/env python3
"""List available agentic tasks, let the dev pick one, then branch+register+brief."""

from __future__ import annotations

import datetime
import subprocess
import sys
from pathlib import Path

import yaml
from generate_brief import index as make_index, render_brief
from roadmap_load import load_roadmap

ROOT = Path(__file__).resolve().parent.parent
REGISTRY_PATH = ROOT / "roadmap" / "registry.yaml"
WORK_DIR = ROOT / "work"


# ---------------------------------------------------------------------------
# Roadmap queries
# ---------------------------------------------------------------------------


def _load_registry() -> dict:
    if not REGISTRY_PATH.is_file():
        return {"version": 1, "entries": []}
    with REGISTRY_PATH.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {"version": 1, "entries": []}


def _claimed_node_ids(reg: dict) -> set[str]:
    return {e["node_id"] for e in reg.get("entries", []) if "node_id" in e}


def _statuses(nodes: list[dict]) -> dict[str, str]:
    return {n["id"]: (n.get("status") or "").lower() for n in nodes}


def _deps_met(node: dict, statuses: dict[str, str]) -> bool:
    return all(
        statuses.get(dep, "") == "complete"
        for dep in (node.get("dependencies") or [])
    )


def _available(nodes: list[dict], reg: dict) -> list[dict]:
    statuses = _statuses(nodes)
    claimed = _claimed_node_ids(reg)
    skip = {"complete", "in progress", "cancelled", "blocked"}
    result = []
    for n in nodes:
        if (n.get("status") or "Not Started").lower() in skip:
            continue
        if not n.get("codename"):
            continue
        exec_m = n.get("execution_milestone", "")
        exec_s = n.get("execution_subtask", "")
        if exec_m not in ("Agentic-led", "Mixed") and exec_s != "agentic":
            continue
        if not _deps_met(n, statuses):
            continue
        if n["id"] in claimed:
            continue
        result.append(n)
    return result


# ---------------------------------------------------------------------------
# Git + registry operations
# ---------------------------------------------------------------------------


def _git(*args: str) -> None:
    subprocess.check_call(["git", *args], cwd=ROOT)


def _checkout_new_branch(branch: str) -> None:
    _git("checkout", "-b", branch)


def _register_and_commit(node: dict, branch: str, reg: dict) -> None:
    codename = node["codename"]
    reg.setdefault("entries", []).append({
        "codename": codename,
        "node_id": node["id"],
        "branch": branch,
        "touch_zones": node.get("touch_zones") or [],
        "started": datetime.date.today().isoformat(),
    })
    with REGISTRY_PATH.open("w", encoding="utf-8") as f:
        yaml.dump(reg, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
    _git("add", str(REGISTRY_PATH))
    _git("commit", "-m", f"chore(rm-{codename}): register as in-progress")


# ---------------------------------------------------------------------------
# Brief + prompt output
# ---------------------------------------------------------------------------


def _write_brief(node: dict, nodes: list[dict]) -> Path:
    WORK_DIR.mkdir(exist_ok=True)
    node_id = node["id"]
    path = WORK_DIR / f"brief-{node_id}.md"
    path.write_text(render_brief(node_id, make_index(nodes)), encoding="utf-8")
    return path


def _write_prompt(node: dict, brief_path: Path) -> Path:
    node_id = node["id"]
    codename = node["codename"]
    title = node.get("title", "")
    ac = node.get("agentic_checklist") or {}

    lines = [
        f"# Task: {node_id} — {title}",
        "",
        f"You are implementing roadmap node **{node_id}** (`{codename}`).",
        f"Read the full brief at `{brief_path.relative_to(ROOT)}`.",
        "",
        "## Contract",
        "",
    ]
    if ac:
        for key in (
            "artifact_action",
            "spec_citation",
            "interface_contract",
            "constraints_note",
            "dependency_note",
        ):
            lines.append(f"- **{key}:** {ac.get(key, '—')}")
    else:
        lines.append("_(no agentic_checklist — check with PM before starting)_")

    lines += [
        "",
        "## Instructions",
        "",
        "1. Read the brief and the contracts cited in `spec_citation` before writing code.",
        "2. Stay within the declared touch zones.",
        "3. Commit incrementally — the pre-commit hook validates on every commit.",
        "4. When complete: run `specy-road finish-this-task` to close out the branch.",
    ]

    path = WORK_DIR / f"prompt-{node_id}.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def _pick(available: list[dict]) -> dict:
    print(f"Available tasks ({len(available)}):\n")
    for i, n in enumerate(available, 1):
        gate = n.get("execution_milestone") or n.get("execution_subtask") or "—"
        deps = ", ".join(n.get("dependencies") or []) or "none"
        print(f"  {i:2}. [{n['id']}] {n.get('title', '')}")
        print(f"       gate: {gate}  deps: {deps}  codename: {n['codename']}")
    print()
    try:
        raw = input("Select task number (q to quit): ").strip()
    except (KeyboardInterrupt, EOFError):
        print()
        raise SystemExit(0)
    if raw.lower() in ("q", "quit", ""):
        raise SystemExit(0)
    try:
        idx = int(raw) - 1
        if not 0 <= idx < len(available):
            raise ValueError
    except ValueError:
        print(f"Invalid selection: {raw!r}", file=sys.stderr)
        raise SystemExit(1)
    return available[idx]


def main() -> None:
    nodes = load_roadmap(ROOT)["nodes"]
    reg = _load_registry()
    available = _available(nodes, reg)

    if not available:
        print(
            "No available agentic tasks — all are complete, in-progress, "
            "blocked, or have unmet dependencies."
        )
        raise SystemExit(0)

    node = _pick(available)
    node_id = node["id"]
    branch = f"feature/rm-{node['codename']}"

    print(f"\n[{node_id}] {node.get('title', '')}")
    print(f"branch: {branch}\n")

    _checkout_new_branch(branch)
    _register_and_commit(node, branch, reg)
    print(f"registered in registry.yaml, first commit done")

    brief_path = _write_brief(node, nodes)
    prompt_path = _write_prompt(node, brief_path)

    print(f"brief:  {brief_path.relative_to(ROOT)}")
    print(f"prompt: {prompt_path.relative_to(ROOT)}")
    print()
    print("-" * 60)
    print(f"Open {prompt_path.relative_to(ROOT)} in your agent to begin.")
    print("When done: specy-road finish-this-task")
    print("-" * 60)


if __name__ == "__main__":
    main()
