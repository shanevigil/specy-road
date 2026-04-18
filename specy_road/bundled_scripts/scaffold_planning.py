#!/usr/bin/env python3
"""Create a flat planning feature sheet (planning/<id>_<slug>_<node_key>.md) and set planning_dir."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from roadmap_crud_ops import edit_node_set_pairs, run_validate_raise
from roadmap_load import load_roadmap
from planning_artifacts import (
    expected_planning_rel,
    normalize_planning_dir,
    resolve_planning_path,
)
from planning_sheet_bootstrap import render_planning_sheet_template
from specy_road.runtime_paths import default_user_repo_root


def _resolve_scaffold_planning_path(
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
    return expected_planning_rel(node)


def scaffold_planning_for_node(
    root: Path,
    node_id: str,
    *,
    planning_dir: str | None = None,
    force: bool = False,
    _echo: bool = False,
) -> dict[str, Any]:
    """Create ``planning/<id>_<slug>_<node_key>.md``, set ``planning_dir`` on the node, validate.

    :param _echo: when True (CLI), print progress to stderr.
    :returns: ``planning_dir`` (normalized) and ``written`` (repo-relative paths).
    """
    root = root.resolve()
    nid = node_id.strip()
    by_id = {n["id"]: n for n in load_roadmap(root)["nodes"]}
    if nid not in by_id:
        raise ValueError(f"unknown node id {nid!r}")
    node = by_id[nid]
    nk = node.get("node_key")
    if not nk:
        raise ValueError(f"node {nid!r} has no node_key")
    pd_s = _resolve_scaffold_planning_path(node, planning_dir)
    norm = normalize_planning_dir(pd_s)
    dest = resolve_planning_path(root, norm)
    planning_d = root / "planning"
    planning_d.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.is_dir():
        raise ValueError(f"{norm} exists and is a directory (expected a single .md file)")
    if dest.is_file() and not force:
        if _echo:
            print(f"skip existing {dest.relative_to(root)}", file=sys.stderr)
        edit_node_set_pairs(root, nid, [("planning_dir", norm)])
        run_validate_raise(root)
        return {"planning_dir": norm, "written": []}
    content = render_planning_sheet_template(nid, node_type=node.get("type"))
    dest.write_text(content, encoding="utf-8")
    rel = str(dest.relative_to(root)).replace("\\", "/")
    written = [rel]
    if _echo:
        print(f"[ok] wrote {rel}")
    edit_node_set_pairs(root, nid, [("planning_dir", norm)])
    run_validate_raise(root)
    return {"planning_dir": norm, "written": written}


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


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "node_id",
        help="Roadmap node id owning the planning file (e.g. M1.2)",
    )
    p.add_argument(
        "--planning-dir",
        dest="planning_dir",
        metavar="PATH",
        help="Repo-relative path to the .md file (default: planning/<id>_<slug>_<node_key>.md)",
    )
    p.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing feature sheet",
    )
    p.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        help="Repository root (default: git root or cwd)",
    )
    args = p.parse_args()
    root = (args.repo_root or default_user_repo_root()).resolve()
    nid = args.node_id.strip()
    by_id = {n["id"]: n for n in load_roadmap(root)["nodes"]}
    if nid not in by_id:
        print(f"error: unknown node id {nid!r}", file=sys.stderr)
        raise SystemExit(1)
    try:
        _run_scaffold_folder(root, nid, args.planning_dir, args.force)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        raise SystemExit(1) from e


if __name__ == "__main__":
    main()
