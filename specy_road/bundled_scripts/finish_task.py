#!/usr/bin/env python3
"""Close the current roadmap feature branch: update status, deregister, validate, commit."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import yaml
from roadmap_chunk_utils import find_chunk_path, load_json_chunk, write_json_chunk
from roadmap_load import load_roadmap
from specy_road.git_workflow_config import (
    merge_request_requires_manual_approval,
    require_implementation_review_before_finish,
    resolve_integration_defaults,
    should_cleanup_work_artifacts_on_finish,
)
from specy_road.runtime_paths import default_user_repo_root

ROOT = Path.cwd()
REGISTRY_PATH = ROOT / "roadmap" / "registry.yaml"


# ---------------------------------------------------------------------------
# Git helpers
# ---------------------------------------------------------------------------


def _current_branch() -> str:
    r = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        capture_output=True,
        text=True,
        cwd=ROOT,
        check=True,
    )
    return r.stdout.strip()


def _git(*args: str) -> None:
    subprocess.check_call(["git", *args], cwd=ROOT)


# ---------------------------------------------------------------------------
# Registry helpers
# ---------------------------------------------------------------------------


def _load_registry() -> dict:
    with REGISTRY_PATH.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {"version": 1, "entries": []}


def _save_registry(doc: dict) -> None:
    with REGISTRY_PATH.open("w", encoding="utf-8") as f:
        yaml.dump(doc, f, default_flow_style=False, allow_unicode=True, sort_keys=False)


# ---------------------------------------------------------------------------
# Main (split into focused helpers to stay within line limits)
# ---------------------------------------------------------------------------


def _resolve_context(branch: str) -> tuple[str, dict, dict, list[dict]]:
    """Return (codename, registry_doc, entry, nodes) or raise SystemExit."""
    codename = branch[len("feature/rm-"):]
    reg = _load_registry()
    entries = reg.get("entries") or []
    entry = next((e for e in entries if e.get("codename") == codename), None)
    if not entry:
        print(f"error: no registry entry for codename '{codename}'.", file=sys.stderr)
        print("  Is roadmap/registry.yaml up to date?", file=sys.stderr)
        raise SystemExit(1)
    node_id = entry["node_id"]
    nodes = load_roadmap(ROOT)["nodes"]
    if not any(n["id"] == node_id for n in nodes):
        print(f"error: node '{node_id}' not found in roadmap.", file=sys.stderr)
        raise SystemExit(1)
    reg_branch = entry.get("branch")
    if not reg_branch:
        print(
            "error: registry entry is missing 'branch' — fix roadmap/registry.yaml.",
            file=sys.stderr,
        )
        raise SystemExit(1)
    if reg_branch != branch:
        print(
            f"error: registry says branch {reg_branch!r} but HEAD is {branch!r}.",
            file=sys.stderr,
        )
        print(
            "  Check out the feature branch that matches the registry, or fix the entry.",
            file=sys.stderr,
        )
        raise SystemExit(1)
    return codename, reg, entry, nodes


def _update_chunk_status(node_id: str) -> list[str]:
    """Patch status in JSON chunk file; return list of changed file paths."""
    chunk = find_chunk_path(ROOT, node_id)
    if not chunk:
        print(f"[warn] chunk file not found for {node_id} — set status manually.")
        return []
    if chunk.suffix.lower() != ".json":
        print(
            f"[warn] chunk {chunk.relative_to(ROOT)} is not .json — set status manually.",
            file=sys.stderr,
        )
        return []
    nodes = load_json_chunk(chunk)
    for n in nodes:
        if n.get("id") == node_id:
            n["status"] = "Complete"
            write_json_chunk(chunk, nodes)
            print(f"[ok] status -> Complete  ({chunk.relative_to(ROOT)})")
            return [str(chunk.relative_to(ROOT))]
    print(f"[warn] node {node_id} not found in {chunk.relative_to(ROOT)}")
    return []


def _validate_and_export() -> None:
    rr = ["--repo-root", str(ROOT)]
    subprocess.check_call(
        [sys.executable, "-m", "specy_road.cli", "validate", *rr], cwd=ROOT
    )
    subprocess.check_call(
        [sys.executable, "-m", "specy_road.cli", "export", *rr], cwd=ROOT
    )


def _work_artifact_rel_paths(node_id: str) -> tuple[str, str, str]:
    return (
        f"work/brief-{node_id}.md",
        f"work/prompt-{node_id}.md",
        f"work/implementation-summary-{node_id}.md",
    )


def _is_git_tracked(repo_root: Path, rel: str) -> bool:
    r = subprocess.run(
        ["git", "ls-files", "--", rel],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    return bool((r.stdout or "").strip())


def _cleanup_work_artifacts(repo_root: Path, node_id: str) -> list[str]:
    """Remove toolkit session files under work/; return tracked paths to stage as deletions."""
    need_add: list[str] = []
    root_r = repo_root.resolve()
    for rel in _work_artifact_rel_paths(node_id):
        path = (root_r / rel).resolve()
        if not path.is_file():
            continue
        try:
            path.relative_to(root_r)
        except ValueError:
            continue
        tracked = _is_git_tracked(root_r, rel)
        path.unlink()
        if tracked:
            need_add.append(rel)
            print(f"[ok] removed {rel} (tracked — staging deletion)")
        else:
            print(f"[ok] removed {rel}")
    return need_add


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Mark the current roadmap task complete, validate, export, commit.",
    )
    p.add_argument(
        "--push",
        action="store_true",
        help="After bookkeeping commit, run git push -u <remote> <branch>.",
    )
    p.add_argument(
        "--remote",
        default="origin",
        metavar="NAME",
        help="Remote for --push (default: origin).",
    )
    p.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        metavar="DIR",
        help="Repository root (default: git root or cwd).",
    )
    p.add_argument(
        "--no-cleanup-work",
        action="store_true",
        help=(
            "Keep work/brief-, work/prompt-, and work/implementation-summary- for this node "
            "(default: delete after successful validate/export)."
        ),
    )
    return p.parse_args(argv)


def _print_finish_tail(
    args: argparse.Namespace,
    *,
    node_id: str,
    node: dict,
    branch: str,
    integration_branch: str,
    mr_manual: bool,
) -> None:
    title = f"[{node_id}] {node.get('title', '')}"
    print()
    print("-" * 60)
    if not args.push:
        print("Branch ready. Push and open a PR:")
        print(f"  git push -u {args.remote} {branch}")
    else:
        print("Branch pushed. Open a PR:")
    print(
        f'  gh pr create --base {integration_branch} --head {branch} --title "{title}"'
    )
    if mr_manual:
        print(
            "  Merge requests require manual approval — wait for review, then merge.",
        )
    print("-" * 60)


def main(argv: list[str] | None = None) -> None:
    global ROOT, REGISTRY_PATH
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    ROOT = (args.repo_root or default_user_repo_root()).resolve()
    REGISTRY_PATH = ROOT / "roadmap" / "registry.yaml"
    branch = _current_branch()
    if not branch.startswith("feature/rm-"):
        print(
            f"error: current branch '{branch}' is not a roadmap feature branch "
            "(expected feature/rm-<codename>).",
            file=sys.stderr,
        )
        raise SystemExit(1)

    codename, reg, entry, nodes = _resolve_context(branch)
    node_id = entry["node_id"]
    node = next(n for n in nodes if n["id"] == node_id)

    if require_implementation_review_before_finish(ROOT):
        if entry.get("implementation_review") != "approved":
            print(
                "error: implementation review is required before finish-this-task.",
                file=sys.stderr,
            )
            print(
                "  Run: specy-road mark-implementation-reviewed "
                "(after work/implementation-summary-"
                f"{node_id}.md is written and you reviewed it).",
                file=sys.stderr,
            )
            raise SystemExit(1)

    print(f"Finishing [{node_id}] {node.get('title', '')}")
    print(f"Branch:   {branch}\n")

    changed_files = _update_chunk_status(node_id)
    changed_files.append(str(REGISTRY_PATH.relative_to(ROOT)))

    reg["entries"] = [e for e in reg.get("entries", []) if e.get("codename") != codename]
    _save_registry(reg)
    print(f"[ok] removed registry entry for '{codename}'\n")

    print("-> specy-road validate")
    print("-> specy-road export")
    _validate_and_export()

    work_tracked_removals: list[str] = []
    if should_cleanup_work_artifacts_on_finish(
        ROOT,
        no_cleanup_work_cli=args.no_cleanup_work,
    ):
        work_tracked_removals = _cleanup_work_artifacts(ROOT, node_id)

    changed_files.append("roadmap.md")
    changed_files.extend(work_tracked_removals)
    _git("add", *changed_files)
    _git("commit", "-m", f"chore(rm-{codename}): complete, deregister")
    print("\n[ok] bookkeeping committed")

    if args.push:
        print(f"-> git push -u {args.remote} {branch}")
        _git("push", "-u", args.remote, branch)

    ib, _rm, _gw = resolve_integration_defaults(
        ROOT,
        explicit_base=None,
        explicit_remote=None,
    )
    mr_manual = merge_request_requires_manual_approval(ROOT)
    _print_finish_tail(
        args,
        node_id=node_id,
        node=node,
        branch=branch,
        integration_branch=ib,
        mr_manual=mr_manual,
    )


if __name__ == "__main__":
    main()
