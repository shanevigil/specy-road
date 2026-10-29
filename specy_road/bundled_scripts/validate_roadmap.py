#!/usr/bin/env python3
"""Validate merged roadmap graph (manifest + chunks) and registry.yaml."""

from __future__ import annotations

import argparse
import contextlib
import re
import sys
from pathlib import Path

import yaml

from specy_road import __version__
from specy_road.bundled_scripts.refresh_schemas import warn_if_schemas_stale
from specy_road.bundled_scripts.refresh_stubs import MANIFEST_REL, warn_if_stubs_stale
from specy_road.bundled_scripts.roadmap_chunk_utils import discover_manifest_path, load_manifest_mapping
from specy_road.bundled_scripts.roadmap_load import load_roadmap, validate_roadmap_line_limits
from specy_road.registry_yaml import registry_path
from specy_road.agents_md_block import warn_if_agents_md_block_stale, warn_missing_load_order_paths
from specy_road.cli import REPLACED_COMMANDS, _known_commands
from specy_road.generated_files import warn_if_generated_files_ignored
from specy_road.git_workflow_config import load_git_workflow_config
from specy_road.managed_block import HTML_COMMENT, _split
from specy_road.orchestration_config import load_orchestration_config
from specy_road.runtime_paths import add_repo_root_arg, default_user_repo_root, git_root
from specy_road.specyrd_cli import _build_parser as _specyrd_parser
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
    "PROSE_NOUNS",
    "unregistered_commands",
    "warn_stale_parent_status",
    "warn_if_pin_differs",
    "warn_touch_zones_match_nothing",
    "warn_unregistered_commands",
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


_FENCE = re.compile(r"^[ \t]*(?:```|~~~)")
_INLINE_CODE = re.compile(r"`([^`\n]*)`")
# Whatever precedes the tool. The lookbehind only rejects a token glued onto
# another word, a path, or a dot.
_MENTION = re.compile(r"(?<![\w/.-])(specy-road|specyrd)[ \t]+([a-z][a-z0-9-]*)")

# Ordinary nouns that follow the product name in prose ("the specy-road toolkit").
# Not commands. The same word inside code is still reported when it is unregistered.
PROSE_NOUNS = frozenset({
    "toolkit", "command", "commands", "cli", "skill", "skills", "package",
    "project", "repo", "repository", "docs", "documentation", "workflow",
    "roadmap", "version",
})


def _command_mentions(text: str):
    """Each ``specy-road`` / ``specyrd`` token of command shape, skipping prose nouns.

    Inline code and fenced blocks yield every token. Prose skips only
    :data:`PROSE_NOUNS`.
    """
    in_fence = False
    for line in text.splitlines():
        if _FENCE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            yield from _MENTION.findall(line)
            continue
        for code in _INLINE_CODE.findall(line):
            yield from _MENTION.findall(code)
        plain = _INLINE_CODE.sub(lambda match: " " * len(match.group(0)), line)
        for tool, name in _MENTION.findall(plain):
            if name not in PROSE_NOUNS:
                yield tool, name


def unregistered_commands(text: str) -> list[str]:
    """Each ``specy-road <name>`` / ``specyrd <name>`` that Markdown ``text`` names and no CLI registers, once, in order.

    A command-shaped token is reported whatever follows it (``specy-road frob
    M1.2``, ``specy-road frob somefile.md``). A registered command is never
    reported (``specy-road validate --strict``). The one exception is prose
    that uses the product name with an ordinary noun, which is not a command:
    toolkit, command, commands, cli, skill, skills, package, project, repo,
    repository, docs, documentation, workflow, roadmap, version
    (``the specy-road toolkit is``). The same word inside code is still
    reported when it is not registered.
    """
    specyrd = next(a for a in _specyrd_parser()._actions if isinstance(a, argparse._SubParsersAction))
    registered = {"specy-road": {*_known_commands(), "version"}, "specyrd": set(specyrd.choices)}
    found: list[str] = []
    for tool, name in _command_mentions(text):
        mention = f"{tool} {name}"
        if name not in registered[tool] and mention not in found:
            found.append(mention)
    return found


def warn_unregistered_commands(root: Path) -> None:
    """One non-fatal line per command ``AGENTS.md`` / ``CLAUDE.md`` sends agents to that does not exist.

    The managed block is skipped: ``warn_if_agents_md_block_stale`` already
    reports one written by another version.
    """
    root = root.resolve()
    checkout = git_root(root) or root
    paths = dict.fromkeys(base / name for base in (root, checkout) for name in ("AGENTS.md", "CLAUDE.md"))
    for path in paths:
        if not path.is_file():
            continue
        try:
            before, _block, after = _split(path.read_text(encoding="utf-8"), HTML_COMMENT)
        except UnicodeDecodeError:
            continue
        rel = path.relative_to(checkout)
        for mention in unregistered_commands(f"{before}\n{after}"):
            replacement = REPLACED_COMMANDS.get(mention)
            advice = (f"use `{replacement}`" if replacement
                      else "it was removed and nothing replaces it" if replacement == ""
                      else f"see `{mention.split()[0]} --help`")
            print(f"agents: warning — {rel} tells agents to run `{mention}`, which is not a "
                  f"command in specy-road {__version__}; {advice}.", file=sys.stderr)


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
    (one reviewer, any family), which is the scaffolded template's content.
    """
    _data, err = load_orchestration_config(root)
    if err:
        print(err, file=sys.stderr)
        raise SystemExit(1)


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
    warn_unregistered_commands(root)
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
        "(do-next-available-task skips them), not just the first ten.",
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
