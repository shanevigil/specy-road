"""Every module the CLI reaches must import cleanly on a base install.

The v0.1.4-rc3 pre-release harness found that `pip install specy-road` (no
extras) could not run `do-next-available-task` at all: `do_next_available`
imports `roadmap_gui_remote` for the MR-rejected pickup tier, that module
imports `requests` at module scope, and `requests` lived only in the `gui` /
`gui-next` / `dev` extras. The whole dev loop — pickup, abort, review, finish,
grind — died on `ModuleNotFoundError` before printing anything.

This walks the module-scope import graph from each CLI entry script and asserts
that every third-party package it reaches is declared in ``[project]
dependencies``, so an extras-only dependency can never again be reachable from
the base CLI.
"""

from __future__ import annotations

import ast
import sys
import tomllib
from pathlib import Path

import pytest

from tests.helpers import BUNDLED_SCRIPTS, REPO

# Entry scripts `specy_road/cli.py` dispatches to via ``_run``, plus the console
# entry points themselves.
CLI_ENTRY_MODULES = (
    "validate_roadmap",
    "generate_brief",
    "export_roadmap_md",
    "validate_file_limits",
    "do_next_task",
    "abort_task_pickup",
    "mark_implementation_reviewed",
    "finish_task",
    "grind_session",
    "start_milestone_session",
    "open_milestone_pr",
    "reconcile_milestone_status",
    "pm_sync",
    "roadmap_crud",
    "roadmap_rebalance",
    "refresh_schemas",
    "scaffold_planning",
)

# Optional surfaces, reached only through an extra the user opted into.
OPTIONAL_ENTRY_MODULES = frozenset({"review_node", "gui_app"})

# Import names that differ from their distribution name.
IMPORT_TO_DISTRIBUTION = {"yaml": "PyYAML"}


def _base_dependency_names() -> set[str]:
    with (REPO / "pyproject.toml").open("rb") as f:
        data = tomllib.load(f)
    out: set[str] = set()
    for spec in data["project"]["dependencies"]:
        name = spec.split(";")[0]
        for sep in (">=", "==", "<=", "~=", ">", "<", "["):
            name = name.split(sep)[0]
        out.add(name.strip().lower())
    return out


def _module_scope_imports(path: Path) -> set[str]:
    """Dotted module names imported at module scope (function-local imports excluded).

    A function-local import is a deliberate opt-in: it only fails for the caller
    that needs it, which is how an optional surface is supposed to degrade.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    out: set[str] = set()
    nodes: list[ast.stmt] = []
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            nodes.append(node)
        elif isinstance(node, ast.Try):
            nodes.extend(
                child
                for child in ast.walk(node)
                if isinstance(child, (ast.Import, ast.ImportFrom))
            )
    for imp in nodes:
        if isinstance(imp, ast.Import):
            out.update(alias.name for alias in imp.names)
        elif isinstance(imp, ast.ImportFrom) and imp.level == 0 and imp.module:
            out.add(imp.module)
    return out


def _source_for(module: str) -> Path | None:
    """Resolve a first-party module name to its file, or ``None`` if third-party."""
    if module == "specy_road":
        return REPO / "specy_road" / "__init__.py"
    if module.startswith("specy_road."):
        rest = module.split(".", 1)[1].replace(".", "/")
        candidate = REPO / "specy_road" / f"{rest}.py"
        return candidate if candidate.is_file() else None
    candidate = BUNDLED_SCRIPTS / f"{module}.py"
    return candidate if candidate.is_file() else None


def _reachable_third_party(entry: str) -> dict[str, str]:
    """Map third-party import name -> the first-party module that pulls it in."""
    seen: set[str] = set()
    pending = [entry]
    found: dict[str, str] = {}
    while pending:
        name = pending.pop()
        if name in seen or name.rsplit(".", 1)[-1] in OPTIONAL_ENTRY_MODULES:
            continue
        seen.add(name)
        path = _source_for(name)
        if path is None:
            continue
        for imported in _module_scope_imports(path):
            if _source_for(imported) is not None:
                pending.append(imported)
                continue
            top = imported.split(".")[0]
            if top in ("__future__", "specy_road") or top in sys.stdlib_module_names:
                continue
            found.setdefault(top, name)
    return found


@pytest.mark.parametrize("entry", CLI_ENTRY_MODULES)
def test_cli_entry_module_needs_only_base_dependencies(entry: str) -> None:
    declared = _base_dependency_names()
    for imported, via in sorted(_reachable_third_party(entry).items()):
        distribution = IMPORT_TO_DISTRIBUTION.get(imported, imported).lower()
        assert distribution in declared, (
            f"`specy-road {entry}` reaches `import {imported}` at module scope "
            f"(via {via}), but {distribution!r} is not in [project] dependencies. "
            "Either declare it as a base dependency or make the import "
            "function-local so the optional surface degrades on its own."
        )


def test_requests_is_a_base_dependency() -> None:
    """The specific regression: forge enrichment is reached from the dev loop."""
    assert "requests" in _base_dependency_names()
