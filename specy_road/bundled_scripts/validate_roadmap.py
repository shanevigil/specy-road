#!/usr/bin/env python3
"""Validate merged roadmap graph (manifest + chunks) and registry.yaml."""

from __future__ import annotations

import argparse
import contextlib
import shutil
import sys
from datetime import date
from pathlib import Path

import yaml

from specy_road.bundled_scripts.refresh_schemas import warn_if_schemas_stale
from specy_road.refresh_stubs_staleness import warn_if_stubs_stale
from specy_road.planning_artifacts import split_frontmatter
from specy_road.roadmap_chunk_utils import (
    discover_manifest_path,
    load_manifest_mapping,
)
from specy_road.roadmap_load import (
    load_roadmap,
    validate_roadmap_line_limits,
)
from specy_road.registry_yaml import registry_path
from specy_road.agents_md_block import (
    print_injected_context,
    warn_if_agents_md_block_stale,
    warn_if_context_over_limits,
    warn_missing_load_order_paths,
)
from specy_road.validate_stale_commands import unregistered_commands, warn_unregistered_commands
from specy_road.version_pin import pinned_version, warn_if_pin_differs
from specy_road.chore_garden_due import warn_garden_due
from specy_road.generated_files import warn_if_generated_files_ignored
from specy_road.git_workflow_config import load_git_workflow_config
from specy_road.init_project import project_template_root
from specy_road.orchestration_config import harness_model_warnings, load_orchestration_config, orchestration_yaml_path
from specy_road.orchestration_pinned import roster_report
from specy_road.planning_scaffold_check import notice_complete_scaffold
from specy_road.runtime_paths import add_repo_root_arg, default_user_repo_root
from specy_road.sibling_repos import warn_unconfigured_sibling_repos
from specy_road.specyrd_init import warn_if_skills_mirrored
from specy_road.bundled_scripts.validate_roadmap_checks import (
    cycle_check,
    load_schema,
    run_validation,
    validate_schema,
    validate_codenames,
    validate_required_planning_dirs,
    validate_unique_title_slugs,
    validate_unique_titles,
    warn_stale_parent_status,
    warn_touch_zones_match_nothing,
)
from specy_road.bundled_scripts.validate_roadmap_gates import validate_gates
from specy_road.bundled_scripts.validate_notices import notice_milestone_review_holds, notice_repeated_ignore_patterns, parse_validate_args, report_context_warnings
from specy_road.bundled_scripts.validate_self_heal import auto_heal_roadmap
from specy_road.bundled_scripts.validate_registry_overlap import (
    authoring_overlap_scope,
    current_authoring_overlap_scope,
)
from specy_road.validate_roadmap_runner import (
    NO_ORCHESTRATION_NOTICE,
    generate_orchestration,
    no_orchestration_notice,
    validate_at,
    validate_git_workflow_contract,
    validate_orchestration_contract,
    warn_research_register,
)

__all__ = [
    "authoring_overlap_scope",
    "cycle_check",
    "pinned_version",
    "run_validation",
    "validate_at",
    "validate_codenames",
    "validate_gates",
    "validate_required_planning_dirs",
    "validate_unique_title_slugs",
    "validate_unique_titles",
    "unregistered_commands",
    "warn_stale_parent_status",
    "warn_if_pin_differs",
    "warn_research_register",
    "warn_touch_zones_match_nothing",
    "warn_unregistered_commands",
]


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
            "Deprecated. Ignored. A parent status that disagrees with the F-013 "
            "rollup on Complete is reported as a warning (it never fails validation), "
            "because the authored chunk value is what a reviewer reads."
        ),
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit 1 when validation passes with warnings (or self-heal notes), "
        "e.g. as a CI gate once an upgrade window closes. Open leaves pickup skips as "
        "unauthored (placeholder sheet, no acceptance) are a notice, not counted.",
    )
    parser.add_argument("--strict-authoring", action="store_true",
                        help="--strict, and count the unauthored-leaf notice as warnings too.")
    parser.add_argument(
        "--all",
        action="store_true",
        help="List every open leaf with a placeholder planning sheet and no acceptance "
        "(do-next-available-task skips them), not just the first ten, and every Complete "
        "leaf whose planning sheet is still the scaffold.",
    )
    parser.add_argument(
        "--generate-orchestration",
        action="store_true",
        help="After validation passes, write the commented roadmap/orchestration.yaml starter "
        "that init project writes, when the file does not exist.",
    )
    add_repo_root_arg(parser)
    args = parse_validate_args(parser)
    root = (args.repo_root or default_user_repo_root()).resolve()
    with _counting_stderr() as stderr:
        validate_at(
            root,
            no_overlap_warn=args.no_overlap_warn,
            require_registry=True,
            show_all=args.all,
            strict_authoring=args.strict_authoring,
        )
        notice_complete_scaffold(root, load_roadmap(root)["nodes"], show_all=args.all)
        if args.generate_orchestration:
            generate_orchestration(root)
        elif not orchestration_yaml_path(root).is_file() and (notice := no_orchestration_notice(root)):
            print(notice)   # stdout: a notice, which --strict does not count
        print_injected_context(root)
    if (args.strict or args.strict_authoring) and stderr.lines:
        sys.stdout.flush()  # the OK line first, then why it does not count
        print(
            f"FAILED (--strict): validation passed with {stderr.lines} line(s) of warnings above.",
            file=sys.stderr,
        )
        raise SystemExit(1)


class _CountingStderr:
    """Pass writes through to the real stderr and count the lines.

    Every warning ``validate`` emits goes to stderr and every error exits, so a
    validation that returns having written to stderr is one that warned. One
    count here is the whole of ``--strict``, rather than a registry each of the
    dozen warning sites would have to remember to use.
    """

    def __init__(self, inner) -> None:
        self.inner = inner
        self.lines = 0

    def write(self, text: str) -> int:
        self.lines += text.count("\n")
        return self.inner.write(text)

    def flush(self) -> None:
        self.inner.flush()


@contextlib.contextmanager
def _counting_stderr():
    counter = _CountingStderr(sys.stderr)
    with contextlib.redirect_stderr(counter):
        yield counter


if __name__ == "__main__":
    main()
