#!/usr/bin/env python3
"""Validate merged roadmap graph (manifest + chunks) and registry.yaml."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

from roadmap_chunk_utils import discover_manifest_path, load_manifest_mapping
from roadmap_load import load_roadmap, validate_roadmap_line_limits
from specy_road.git_workflow_config import (
    integration_refs_present,
    is_git_worktree,
    load_git_workflow_config,
)
from specy_road.runtime_paths import default_user_repo_root
from validate_roadmap_checks import (
    cycle_check,
    load_schema,
    run_validation,
    validate_schema,
    validate_codenames,
    validate_required_planning_dirs,
    validate_unique_title_slugs,
    validate_unique_titles,
    warn_phase_status_when_all_descendants_complete,
)
from validate_roadmap_gates import validate_gates

__all__ = [
    "cycle_check",
    "run_validation",
    "validate_at",
    "validate_codenames",
    "validate_gates",
    "validate_required_planning_dirs",
    "validate_unique_title_slugs",
    "validate_unique_titles",
    "warn_phase_status_when_all_descendants_complete",
]


def validate_git_workflow_contract(root: Path) -> None:
    """Validate ``roadmap/git-workflow.yaml`` if present; warn on missing refs."""
    gw = root / "roadmap" / "git-workflow.yaml"
    if not gw.is_file():
        print(
            "warning: missing roadmap/git-workflow.yaml — add the template from "
            "`specy-road init project` so CLI and PM GUI share your integration branch.",
            file=sys.stderr,
        )
        return
    data, err = load_git_workflow_config(root)
    if err:
        print(err, file=sys.stderr)
        raise SystemExit(1)
    assert data is not None
    if is_git_worktree(root):
        ok, _ = integration_refs_present(
            root,
            str(data["remote"]),
            str(data["integration_branch"]),
        )
        if not ok:
            print(
                "warning: no local git ref for "
                f"{data['remote']}/{data['integration_branch']} — "
                f"run: git fetch {data['remote']}",
                file=sys.stderr,
            )


def validate_at(
    root: Path,
    *,
    no_overlap_warn: bool = False,
    require_registry: bool = True,
    no_phase_status_warn: bool = False,
) -> None:
    """Validate roadmap + registry under ``root`` (repo root containing ``roadmap/``)."""
    reg_path = root / "roadmap" / "registry.yaml"
    if require_registry and not reg_path.is_file():
        print(f"missing {reg_path}", file=sys.stderr)
        raise SystemExit(1)

    validate_roadmap_line_limits(root)
    discover_manifest_path(root)
    validate_git_workflow_contract(root)
    mdoc = load_manifest_mapping(root)
    mschema = root / "schemas" / "manifest.schema.json"
    validate_schema(mdoc, load_schema(mschema), "manifest.schema")
    roadmap = load_roadmap(root)
    if reg_path.is_file():
        with reg_path.open(encoding="utf-8") as f:
            registry = yaml.safe_load(f)
    else:
        registry = {"version": 1, "entries": []}

    run_validation(
        roadmap,
        registry,
        no_overlap_warn,
        repo_root=root,
        no_phase_status_warn=no_phase_status_warn,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--no-overlap-warn",
        action="store_true",
        help="suppress touch-zone overlap warnings",
    )
    parser.add_argument(
        "--no-phase-status-warn",
        action="store_true",
        help=(
            "suppress warning when a phase is not Complete but every descendant node is"
        ),
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        metavar="DIR",
        help="Repository root (default: git root or cwd).",
    )
    args = parser.parse_args()
    root = (args.repo_root or default_user_repo_root()).resolve()
    validate_at(
        root,
        no_overlap_warn=args.no_overlap_warn,
        require_registry=True,
        no_phase_status_warn=args.no_phase_status_warn,
    )


if __name__ == "__main__":
    main()
