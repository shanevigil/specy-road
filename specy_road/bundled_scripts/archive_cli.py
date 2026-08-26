"""CLI for archiving completed roadmap subtrees: archive / list / show / restore.

Mirrors ``roadmap_crud.py``'s contract: mutate, validate, and leave the result
in the working tree. Nothing here commits — ``specy-road`` publishes roadmap
changes through the normal publish path, and an archive is an ordinary roadmap
change that happens to move files.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from specy_road.archive_index import index_records, load_archive_index
from specy_road.archive_ops import archive_node, auto_archive_candidates
from specy_road.archive_plan import plan_archive, plan_summary
from specy_road.archive_restore import restore_archive
from specy_road.runtime_paths import default_user_repo_root

DEFAULT_AUTO_DAYS = 90


def _root(ns: argparse.Namespace) -> Path:
    return (ns.repo_root or default_user_repo_root()).resolve()


def _add_repo_root(p: argparse.ArgumentParser) -> None:
    p.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        metavar="DIR",
        help="Repository root (default: git root or cwd).",
    )


def _reexport(root: Path) -> None:
    """Regenerate ``roadmap.md`` so ``export --check`` does not report drift."""
    from export_roadmap_md import export_markdown
    from roadmap_load import load_roadmap

    (root / "roadmap.md").write_text(
        export_markdown(load_roadmap(root)["nodes"]), encoding="utf-8"
    )


def cmd_archive(ns: argparse.Namespace) -> int:
    root = _root(ns)
    if ns.auto:
        return _cmd_archive_auto(root, ns)
    if not ns.node_id:
        print("error: give a NODE_ID, or use --auto.", file=sys.stderr)
        return 2
    plan = plan_archive(root, ns.node_id, force=ns.force)
    if ns.dry_run:
        print("\n".join(plan_summary(plan)))
        print("\n(dry run — nothing written)")
        return 0
    rec = archive_node(root, ns.node_id, force=ns.force)
    _reexport(root)
    print(
        f"[ok] archived {rec['root_node_id']} "
        f"({len(rec['node_keys'])} node(s)) as {rec['archive_id']}"
    )
    print(f"     chunk    {rec['chunk']}")
    for move in rec.get("planning") or []:
        print(f"     planning {move['origin']} -> {move['stored']}")
    print("     restore with: specy-road restore-archive " + rec["archive_id"])
    return 0


def _cmd_archive_auto(root: Path, ns: argparse.Namespace) -> int:
    days = ns.older_than_days if ns.older_than_days is not None else DEFAULT_AUTO_DAYS
    candidates = auto_archive_candidates(root, older_than_days=days)
    if not candidates:
        print(f"[ok] nothing complete for more than {days} day(s) — nothing to archive.")
        return 0
    for node_id, done in candidates:
        if ns.dry_run:
            print(f"would archive {node_id} (complete since {done})")
            continue
        rec = archive_node(root, node_id)
        print(f"[ok] archived {node_id} as {rec['archive_id']} (complete since {done})")
    if not ns.dry_run:
        _reexport(root)
    elif candidates:
        print("\n(dry run — nothing written)")
    return 0


def cmd_list(ns: argparse.Namespace) -> int:
    doc = load_archive_index(_root(ns))
    records = index_records(doc)
    if ns.json:
        print(json.dumps(doc, indent=2, sort_keys=True))
        return 0
    if not records:
        print("no archives (roadmap/archive/index.json is absent or empty).")
        return 0
    print(f"{'ARCHIVE_ID':<34} {'DEPTH':<8} {'ROOT':<10} {'NODES':>5}  ARCHIVED_AT")
    for r in records:
        print(
            f"{r['archive_id']:<34} {r['depth']:<8} {r['root_node_id']:<10} "
            f"{len(r.get('node_keys') or []):>5}  {r.get('archived_at', '')}"
        )
    return 0


def cmd_show(ns: argparse.Namespace) -> int:
    from specy_road.archive_index import find_record

    root = _root(ns)
    rec = find_record(load_archive_index(root), ns.archive_id)
    if rec is None:
        print(
            f"error: no archive with id {ns.archive_id!r} "
            "(try: specy-road list-archives)",
            file=sys.stderr,
        )
        return 1
    if ns.json:
        print(json.dumps(rec, indent=2, sort_keys=True))
        return 0
    print(f"archive_id    {rec['archive_id']}")
    print(f"depth         {rec['depth']}")
    print(f"root          {rec['root_node_id']}  {rec['root_node_key']}")
    print(f"archived_at   {rec.get('archived_at', '')}")
    print(f"chunk         {rec.get('chunk') or '- (deep archived)'}")
    git = rec.get("git") or {}
    for key in (
        "rollup_branch",
        "integration_branch",
        "merge_commit",
        "nearest_tag",
        "closed_at",
    ):
        print(f"{key:<13} {git.get(key) or '-'}")
    print("nodes")
    for n in rec.get("nodes_summary") or []:
        print(f"  {n['id']:<10} {n['type']:<10} {n.get('status', '-'):<12} {n['title']}")
    return 0


def cmd_restore(ns: argparse.Namespace) -> int:
    root = _root(ns)
    if ns.dry_run:
        from specy_road.archive_index import find_record

        rec = find_record(load_archive_index(root), ns.archive_id)
        if rec is None:
            print(f"error: no archive with id {ns.archive_id!r}", file=sys.stderr)
            return 1
        print(
            f"would restore {rec['root_node_id']} "
            f"({len(rec.get('node_keys') or [])} node(s)) from {rec['archive_id']}"
        )
        print("\n(dry run — nothing written)")
        return 0
    out = restore_archive(root, ns.archive_id)
    _reexport(root)
    print(
        f"[ok] restored {out['archive_id']}: {out['nodes']} node(s) -> "
        + ", ".join(out["chunks"])
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="specy-road",
        description="Archive completed roadmap subtrees out of the live graph.",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("archive", help="Archive a Complete subtree.")
    sp.add_argument("node_id", metavar="NODE_ID", nargs="?")
    sp.add_argument(
        "--auto",
        action="store_true",
        help="Archive every subtree complete for longer than --older-than-days.",
    )
    sp.add_argument(
        "--older-than-days",
        type=int,
        default=None,
        metavar="N",
        help=f"Age threshold for --auto (default: {DEFAULT_AUTO_DAYS}).",
    )
    sp.add_argument(
        "--force",
        action="store_true",
        help="Archive even when the subtree does not roll up as Complete.",
    )
    sp.add_argument("--dry-run", action="store_true", help="Show the plan; write nothing.")
    _add_repo_root(sp)
    sp.set_defaults(func=cmd_archive)

    sp = sub.add_parser("list-archives", help="List archive records.")
    sp.add_argument("--json", action="store_true", help="Emit the raw index JSON.")
    _add_repo_root(sp)
    sp.set_defaults(func=cmd_list)

    sp = sub.add_parser("show-archive", help="Show one archive record in detail.")
    sp.add_argument("archive_id", metavar="ARCHIVE_ID")
    sp.add_argument("--json", action="store_true", help="Emit the raw record JSON.")
    _add_repo_root(sp)
    sp.set_defaults(func=cmd_show)

    sp = sub.add_parser("restore-archive", help="Restore an archive to the live roadmap.")
    sp.add_argument("archive_id", metavar="ARCHIVE_ID")
    sp.add_argument("--dry-run", action="store_true", help="Show the plan; write nothing.")
    _add_repo_root(sp)
    sp.set_defaults(func=cmd_restore)

    return p


def main(argv: list[str] | None = None) -> None:
    ns = build_parser().parse_args(argv)
    try:
        raise SystemExit(ns.func(ns))
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        raise SystemExit(1) from e


if __name__ == "__main__":
    main()
