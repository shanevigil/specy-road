#!/usr/bin/env python3
"""Validate merged roadmap graph (manifest + chunks) and registry.yaml."""

from __future__ import annotations

import argparse
import contextlib
import re
import shutil
import sys
from pathlib import Path

import yaml

from specy_road import __version__
from specy_road.bundled_scripts.refresh_schemas import warn_if_schemas_stale
from specy_road.bundled_scripts.refresh_stubs import MANIFEST_REL, warn_if_stubs_stale
from specy_road.bundled_scripts.roadmap_chunk_utils import discover_manifest_path, load_manifest_mapping
from specy_road.bundled_scripts.roadmap_load import load_roadmap, validate_roadmap_line_limits
from specy_road.registry_yaml import registry_path
from specy_road.agents_md_block import (
    print_injected_context,
    warn_if_agents_md_block_stale,
    warn_if_context_over_limits,
    warn_missing_load_order_paths,
)
from specy_road.generated_files import warn_if_generated_files_ignored
from specy_road.git_workflow_config import load_git_workflow_config
from specy_road.init_project import project_template_root
from specy_road.orchestration_config import load_orchestration_config
from specy_road.orchestration_pinned import roster_source
from specy_road.planning_scaffold_check import notice_complete_scaffold
from specy_road.runtime_paths import add_repo_root_arg, default_user_repo_root, git_root
from specy_road.specyrd_init import _load_manifest
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
from specy_road.bundled_scripts.validate_self_heal import auto_heal_roadmap

__all__ = [
    "cycle_check",
    "pinned_version",
    "run_validation",
    "validate_at",
    "validate_codenames",
    "validate_gates",
    "validate_required_planning_dirs",
    "validate_unique_title_slugs",
    "validate_unique_titles",
    "warn_stale_parent_status",
    "warn_if_pin_differs",
    "warn_touch_zones_match_nothing",
]


_REQUIREMENT_PIN = re.compile(r"^\s*specy[-_.]road\s*(?:\[[^\]]*\])?\s*==\s*([^\s;#,]+)", re.IGNORECASE)


def pinned_version(start: Path) -> tuple[str, str] | None:
    """``(version, where declared)`` for the specy-road this checkout pins, or None.

    A ``pin`` in ``.specyrd/manifest.json`` wins; otherwise the first
    ``specy-road==`` line in a ``requirements*.txt`` at the checkout root.
    """
    checkout = git_root(start) or start
    pin = _load_manifest(checkout).get("pin")
    if isinstance(pin, str) and pin.strip():
        return pin.strip(), str(MANIFEST_REL)
    for req in sorted(checkout.glob("requirements*.txt")):
        try:
            lines = req.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            continue
        for line in lines:
            m = _REQUIREMENT_PIN.match(line)
            if m:
                return m.group(1), req.name
    return None


def warn_if_pin_differs(start: Path) -> None:
    """One non-fatal line when the running specy-road is not the version the repo pins."""
    found = pinned_version(start)
    if found is None or found[0] == __version__:
        return
    pin, where = found
    print(
        f"specy-road: warning — this repo pins specy-road {pin} ({where}) but {__version__} "
        f"is running. If the upgrade is deliberate, update the pin; otherwise install {pin}.",
        file=sys.stderr,
    )


def validate_git_workflow_contract(root: Path) -> None:
    """Validate ``roadmap/git-workflow.yaml`` if present.

    F-005: do NOT warn about missing remote-tracking refs for the
    integration branch. specy-road only cares that ``integration_branch`` is
    declared. How the application team organises branches (and what their
    local clone has fetched) is outside specy-road's scope.
    """
    gw = root / "roadmap" / "git-workflow.yaml"
    if not gw.is_file():
        print(
            "warning: missing roadmap/git-workflow.yaml — add the template "
            "from `specy-road init project` so CLI and PM GUI share your "
            "integration branch.",
            file=sys.stderr,
        )
        return
    _data, err = load_git_workflow_config(root)
    if err:
        print(err, file=sys.stderr)
        raise SystemExit(1)


def validate_orchestration_contract(root: Path) -> None:
    """Validate ``roadmap/orchestration.yaml`` if present.

    A missing file is not a warning: it means the default review policy
    (one reviewer, any family), the scaffolded starter's policy, which
    ``--generate-orchestration`` writes as an editable file.
    A file that is not what routing reads (absent on the integration branch,
    or different there) is, as ``orchestrate plan`` says.
    """
    _data, err = load_orchestration_config(root)
    if err:
        print(err, file=sys.stderr)
        raise SystemExit(1)
    _ref, drift = roster_source(root)
    if drift:
        print(f"warning: {drift}", file=sys.stderr)


def generate_orchestration(root: Path) -> None:
    """Write the ``init project`` starter to ``roadmap/orchestration.yaml`` unless one exists."""
    dest = root / "roadmap" / "orchestration.yaml"
    if dest.exists():
        print(f"{dest} exists; --generate-orchestration left it unchanged")
        return
    shutil.copyfile(project_template_root() / "roadmap" / "orchestration.yaml", dest)
    print(f"wrote {dest}: a starter roster (human plus one executor) and the default policy; "
          "edit it, then commit it to the integration branch")


def validate_at(
    root: Path,
    *,
    no_overlap_warn: bool = False,
    require_registry: bool = True,
    auto_heal: bool = True,
    show_all: bool = False,
) -> None:
    """Validate roadmap + registry under ``root`` (repo root containing ``roadmap/``).

    F-006/F-008: self-heal pass runs first (silent fixes for missing
    codenames, deprecated fields). Pass ``auto_heal=False`` to disable,
    e.g. in a read-only CI drift check. ``show_all`` lists every unauthored
    leaf instead of the first ten.
    """
    reg_path = registry_path(root)
    if require_registry and not reg_path.is_file():
        print(f"missing {reg_path}", file=sys.stderr)
        raise SystemExit(1)

    validate_roadmap_line_limits(root)
    discover_manifest_path(root)
    validate_git_workflow_contract(root)
    validate_orchestration_contract(root)
    warn_if_pin_differs(root)
    warn_if_schemas_stale(root)
    warn_if_stubs_stale(root)
    warn_if_agents_md_block_stale(root)
    warn_missing_load_order_paths(root)
    warn_if_context_over_limits(root)
    warn_if_generated_files_ignored(root)

    if auto_heal:
        changed, _logs = auto_heal_roadmap(root)
        if changed:
            # Re-check line limits after healing in case a chunk grew.
            validate_roadmap_line_limits(root)

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
        show_all=show_all,
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
            "Deprecated. Ignored. A parent status that disagrees with the F-013 "
            "rollup on Complete is reported as a warning (it never fails validation), "
            "because the authored chunk value is what a reviewer reads."
        ),
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit 1 when validation passes with warnings (or self-heal notes), "
        "e.g. as a CI gate once an upgrade window closes.",
    )
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
    args = parser.parse_args()
    root = (args.repo_root or default_user_repo_root()).resolve()
    with _counting_stderr() as stderr:
        validate_at(
            root,
            no_overlap_warn=args.no_overlap_warn,
            require_registry=True,
            show_all=args.all,
        )
        notice_complete_scaffold(root, load_roadmap(root)["nodes"], show_all=args.all)
        if args.generate_orchestration:
            generate_orchestration(root)
        print_injected_context(root)
    if args.strict and stderr.lines:
        sys.stdout.flush()   # the OK line first, then why it does not count
        print(f"FAILED (--strict): validation passed with {stderr.lines} line(s) of warnings above.",
              file=sys.stderr)
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
