#!/usr/bin/env python3
"""Create planning markdown under planning/<node-id>/ and set roadmap planning_dir."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

from roadmap_crud_ops import edit_node_set_pairs, merged_ids, run_validate_raise
from roadmap_load import load_roadmap
from planning_artifacts import normalize_planning_dir, resolve_planning_dir

ROOT = Path(__file__).resolve().parent.parent
_TEMPLATES = ROOT / "templates" / "planning-node"


def _render_template(name: str, node_id: str, title: str) -> str:
    path = _TEMPLATES / name
    if not path.is_file():
        raise FileNotFoundError(f"missing template {path}")
    text = path.read_text(encoding="utf-8")
    return text.replace("{{NODE_ID}}", node_id).replace("{{TITLE}}", title)


def _tasks_md_with_frontmatter(node_id: str, title: str) -> str:
    body = _render_template("tasks.md.template", node_id, title)
    return f"---\nnode_id: {node_id}\n---\n\n{body.lstrip()}"


def _task_file_stub(task_id: str, owner_title: str) -> str:
    return (
        f"---\n"
        f"node_id: {task_id}\n"
        f"---\n\n"
        f"# Task `{task_id}`\n\n"
        f"Parent feature context: {owner_title}\n\n"
        f"## Steps\n\n"
        f"- [ ] …\n"
    )


def _run_task_subcommand(
    root: Path,
    nid: str,
    by_id: dict[str, dict],
    task_id: str,
    planning_dir_override: str | None,
    force: bool,
) -> None:
    tid = task_id.strip()
    if not re.match(r"^M[0-9]+(\.[0-9]+)*$", tid):
        print(f"error: invalid task id {tid!r}", file=sys.stderr)
        raise SystemExit(1)
    if tid not in merged_ids(root):
        print(
            f"error: task id {tid!r} is not in the roadmap graph "
            "(add the node first with roadmap_crud add-node)",
            file=sys.stderr,
        )
        raise SystemExit(1)
    node = by_id[nid]
    pd_raw = planning_dir_override or node.get("planning_dir")
    if not pd_raw:
        print(
            "error: node has no planning_dir; run scaffold without --task-id first "
            "or pass --planning-dir",
            file=sys.stderr,
        )
        raise SystemExit(1)
    norm = normalize_planning_dir(str(pd_raw).strip())
    base = resolve_planning_dir(root, norm)
    tasks_d = base / "tasks"
    tasks_d.mkdir(parents=True, exist_ok=True)
    out = tasks_d / f"{tid}.md"
    if out.is_file() and not force:
        print(f"error: {out.relative_to(root)} exists (use --force)", file=sys.stderr)
        raise SystemExit(1)
    out.write_text(_task_file_stub(tid, str(node.get("title", ""))), encoding="utf-8")
    print(f"[ok] wrote {out.relative_to(root)}")
    from validate_roadmap import validate_at

    validate_at(root, no_overlap_warn=False, require_registry=True)


def _resolve_scaffold_planning_path(
    nid: str,
    node: dict,
    planning_dir: str | None,
) -> str:
    node_pd = (
        str(node.get("planning_dir") or "").strip()
        if isinstance(node.get("planning_dir"), str)
        else ""
    )
    if planning_dir and str(planning_dir).strip():
        return str(planning_dir).strip()
    if node_pd:
        return node_pd
    return f"planning/{nid}"


def _write_scaffold_template_files(
    root: Path,
    dest: Path,
    nid: str,
    title: str,
    force: bool,
    *,
    _echo: bool,
) -> list[str]:
    files = {
        "overview.md": _render_template("overview.md.template", nid, title),
        "plan.md": _render_template("plan.md.template", nid, title),
        "tasks.md": _tasks_md_with_frontmatter(nid, title),
    }
    written: list[str] = []
    for fname, content in files.items():
        path = dest / fname
        if path.is_file() and not force:
            if _echo:
                print(f"skip existing {path.relative_to(root)}", file=sys.stderr)
            continue
        path.write_text(content, encoding="utf-8")
        rel = str(path.relative_to(root)).replace("\\", "/")
        written.append(rel)
        if _echo:
            print(f"[ok] wrote {rel}")
    return written


def _run_scaffold_folder(
    root: Path,
    nid: str,
    planning_dir_override: str | None,
    force: bool,
) -> None:
    result = scaffold_planning_for_node(
        root,
        nid,
        planning_dir=planning_dir_override,
        force=force,
        _echo=True,
    )
    print(f"[ok] set planning_dir={result['planning_dir']!r} on {nid}")


def scaffold_planning_for_node(
    root: Path,
    node_id: str,
    *,
    planning_dir: str | None = None,
    force: bool = False,
    _echo: bool = False,
) -> dict[str, Any]:
    """Create planning markdown under ``planning/<node-id>/`` (or ``planning_dir``), set ``planning_dir`` on the node, validate.

    If the node already has ``planning_dir`` set, that path is used when ``planning_dir`` is omitted (same as CLI defaulting).

    :param _echo: when True (CLI), print progress to stderr like legacy behavior.
    :returns: ``planning_dir`` (normalized) and ``written`` (repo-relative paths).
    """
    root = root.resolve()
    nid = node_id.strip()
    by_id = {n["id"]: n for n in load_roadmap(root)["nodes"]}
    if nid not in by_id:
        raise ValueError(f"unknown node id {nid!r}")
    node = by_id[nid]
    title = str(node.get("title", ""))
    pd_s = _resolve_scaffold_planning_path(nid, node, planning_dir)
    norm = normalize_planning_dir(pd_s)
    dest = resolve_planning_dir(root, norm)
    if dest.exists() and not dest.is_dir():
        raise ValueError(f"{norm} exists and is not a directory")
    dest.mkdir(parents=True, exist_ok=True)
    written = _write_scaffold_template_files(
        root, dest, nid, title, force, _echo=_echo
    )
    edit_node_set_pairs(root, nid, [("planning_dir", norm)])
    run_validate_raise(root)
    return {"planning_dir": norm, "written": written}


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("node_id", help="Roadmap node id owning the planning folder (e.g. M1.2)")
    p.add_argument(
        "--planning-dir",
        dest="planning_dir",
        metavar="PATH",
        help="Repo-relative directory (default: planning/<NODE_ID>)",
    )
    p.add_argument(
        "--task-id",
        metavar="TASK_ID",
        help="Create tasks/<TASK_ID>.md with frontmatter (requires planning_dir or --planning-dir)",
    )
    p.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing template files (not recommended for edited docs)",
    )
    p.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        help="Repository root (default: parent of scripts/)",
    )
    args = p.parse_args()
    root = (args.repo_root or ROOT).resolve()
    nid = args.node_id.strip()
    by_id = {n["id"]: n for n in load_roadmap(root)["nodes"]}
    if nid not in by_id:
        print(f"error: unknown node id {nid!r}", file=sys.stderr)
        raise SystemExit(1)
    if args.task_id:
        _run_task_subcommand(
            root,
            nid,
            by_id,
            args.task_id,
            args.planning_dir,
            args.force,
        )
    else:
        try:
            _run_scaffold_folder(root, nid, args.planning_dir, args.force)
        except ValueError as e:
            print(f"error: {e}", file=sys.stderr)
            raise SystemExit(1) from e


if __name__ == "__main__":
    main()
