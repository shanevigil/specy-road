#!/usr/bin/env python3
"""List available agentic tasks, let the dev pick one, then branch+register+brief."""

from __future__ import annotations

import argparse
import datetime
import subprocess
import sys
from pathlib import Path

import yaml
from generate_brief import index as make_index, render_brief
from roadmap_load import load_roadmap
from specy_road.git_workflow_config import resolve_integration_defaults
from specy_road.runtime_paths import default_user_repo_root

ROOT = Path.cwd()
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


def _statuses_by_node_key(nodes: list[dict]) -> dict[str, str]:
    """Map node_key -> lowercased status (dependencies reference node_key UUIDs)."""
    return {
        n["node_key"]: (n.get("status") or "").lower()
        for n in nodes
        if isinstance(n.get("node_key"), str) and n["node_key"]
    }


def _deps_met(node: dict, statuses_by_key: dict[str, str]) -> bool:
    return all(
        statuses_by_key.get(dep, "") == "complete"
        for dep in (node.get("dependencies") or [])
    )


def _available(nodes: list[dict], reg: dict) -> list[dict]:
    statuses_by_key = _statuses_by_node_key(nodes)
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
        if not _deps_met(n, statuses_by_key):
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


def _working_tree_clean() -> bool:
    r = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return not r.stdout.strip()


def _assert_working_tree_clean() -> None:
    if not _working_tree_clean():
        print(
            "error: working tree is not clean (commit, stash, or discard changes first).",
            file=sys.stderr,
        )
        print(
            "  Integration-branch sync and creating a new feature branch need a clean tree.",
            file=sys.stderr,
        )
        raise SystemExit(1)


def _sync_integration_branch(base: str, remote: str) -> None:
    """
    Fetch, check out the integration branch, and fast-forward to remote.
    Requires a clean working tree.
    """
    _assert_working_tree_clean()
    _git("fetch", remote)
    _git("checkout", base)
    try:
        _git("merge", "--ff-only", f"{remote}/{base}")
    except subprocess.CalledProcessError:
        print(
            f"error: could not fast-forward local '{base}' to {remote}/{base}.",
            file=sys.stderr,
        )
        print(
            "  Resolve your local integration branch (e.g. pull with rebase, or reset "
            "after team agreement), then retry.",
            file=sys.stderr,
        )
        raise SystemExit(1)


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
        "The brief lists **ancestor** planning sheets (phase/milestone) and **this node's** sheet under `planning/`. Read ancestors first for scope and constraints, then the leaf sheet.",
        "",
        "## Contract",
        "",
    ]
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
        lines.append("_(no agentic_checklist — check with PM before starting)_")

    lines += [
        "",
        "## Instructions",
        "",
        "1. Read the brief and the contracts cited in `contract_citation` before writing code.",
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


def _pick(available: list[dict], all_nodes: list[dict]) -> dict:
    key_to_id = {
        x["node_key"]: x["id"]
        for x in all_nodes
        if isinstance(x.get("node_key"), str) and x.get("node_key")
    }
    print(f"Available tasks ({len(available)}):\n")
    for i, n in enumerate(available, 1):
        gate = n.get("execution_milestone") or n.get("execution_subtask") or "—"
        dep_labels = [
            key_to_id.get(k, k) for k in (n.get("dependencies") or [])
        ]
        deps = ", ".join(dep_labels) or "none"
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


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Pick the next agentic task, sync integration branch, branch, register.",
    )
    p.add_argument(
        "--base",
        default=None,
        metavar="BRANCH",
        help=(
            "Integration branch to sync before creating feature/rm-* "
            "(default: roadmap/git-workflow.yaml, else main)."
        ),
    )
    p.add_argument(
        "--remote",
        default=None,
        metavar="NAME",
        help=(
            "Git remote to fetch and merge from "
            "(default: roadmap/git-workflow.yaml, else origin)."
        ),
    )
    p.add_argument(
        "--no-sync",
        action="store_true",
        help="Skip fetch/checkout/ff-merge of the integration branch (offline/CI).",
    )
    p.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        metavar="DIR",
        help="Repository root (default: git root or cwd).",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    global ROOT, REGISTRY_PATH, WORK_DIR
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    ROOT = (args.repo_root or default_user_repo_root()).resolve()
    REGISTRY_PATH = ROOT / "roadmap" / "registry.yaml"
    WORK_DIR = ROOT / "work"
    base, remote, gw_warns = resolve_integration_defaults(
        ROOT,
        explicit_base=args.base,
        explicit_remote=args.remote,
    )
    for w in gw_warns:
        print(f"warning: {w}", file=sys.stderr)
    nodes = load_roadmap(ROOT)["nodes"]
    reg = _load_registry()
    available = _available(nodes, reg)

    if not available:
        print(
            "No available agentic tasks — all are complete, in-progress, "
            "blocked, or have unmet dependencies."
        )
        raise SystemExit(0)

    if not args.no_sync:
        _sync_integration_branch(base, remote)

    node = _pick(available, nodes)
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
