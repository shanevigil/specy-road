#!/usr/bin/env python3
"""Report import cycles and package imports of bundled_scripts entry points.

Scans ``specy_road`` with the AST. Every ``import`` and ``from ... import``
is an edge, including imports nested in functions, classes and
``if TYPE_CHECKING`` blocks. An import made by name at run time (``importlib``,
``runpy``, ``__import__``) is not an edge, and neither is a string in a
command table.

A strongly connected component is recorded when it contains two or more
modules. ``constraints/import-layers-baseline.json`` is a committed report:
this script prints members added and removed, components merged or split, and
entry-point edges added and removed, then exits 0. It does not fail when a
cycle grows.

The report also lists, every run, each import by the review gate
(``review_gate*``), a CLI entry point (``specy_road.cli`` and the entry points
below) or a ``gui_app*`` module of a module inside ``specy_road.orchestration``:
those callers use the package's public interface, ``specy_road.orchestration``
itself. It is a listing, not a gate.

An entry point is a ``bundled_scripts`` module with a module-level ``main``,
plus ``grind_session_cleanup`` (the grind-session command's cleanup module;
``grind_session.py`` owns ``main``, and package modules import the cleanup
module directly).

Module ids are dotted names. Comparison is by overlap, so a component that
shrinks or splits still overlaps its old members and is reported as members
removed or components split. A later leaf that only relocates a module
rewrites those dotted names in the report first (the rename rule).

Usage:
    python scripts/check_import_layers.py            # print the difference
    python scripts/check_import_layers.py --write    # rewrite the report
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from datetime import date
from pathlib import Path

# The grind-session command's cleanup module. Its main lives in grind_session.py.
CLEANUP_ENTRY_POINT = "grind_session_cleanup"


def module_index(package: Path) -> dict[Path, str]:
    """Map each Python file under ``package`` to its ``specy_road`` module name."""
    names: dict[Path, str] = {}
    for path in sorted(package.rglob("*.py")):
        parts = list(path.relative_to(package).with_suffix("").parts)
        if parts and parts[-1] == "__init__":
            parts.pop()
        dotted = ".".join(parts)
        names[path] = "specy_road" + (f".{dotted}" if dotted else "")
    return names


def _enclosing_package(module: str, path: Path) -> str:
    """Package that contains ``path``: the module itself when it is ``__init__.py``."""
    if path.name == "__init__.py":
        return module
    return module.rpartition(".")[0]


def _base_module(node: ast.ImportFrom, module: str, path: Path) -> str:
    """Module named by an ``ImportFrom``, with relative dots resolved."""
    if node.level:
        parts = _enclosing_package(module, path).split(".")
        parts = [part for part in parts if part]
        keep = len(parts) - (node.level - 1)
        if keep < 0:
            return ""
        parts = parts[:keep]
        if node.module:
            parts.extend(node.module.split("."))
        return ".".join(parts)
    return node.module or ""


def _known_target(candidate: str, known: set[str]) -> str:
    """Deepest prefix of ``candidate`` that is a module in this package."""
    parts = candidate.split(".") if candidate else []
    for length in range(len(parts), 0, -1):
        prefix = ".".join(parts[:length])
        if prefix in known:
            return prefix
    return ""


def import_targets(
    node: ast.Import | ast.ImportFrom, module: str, path: Path, known: set[str]
) -> set[str]:
    """Internal modules ``node`` imports, excluding ``module`` itself."""
    targets: set[str] = set()
    if isinstance(node, ast.Import):
        for alias in node.names:
            chosen = _known_target(alias.name, known)
            if chosen and chosen != module:
                targets.add(chosen)
        return targets
    base = _base_module(node, module, path)
    for alias in node.names or []:
        candidate = f"{base}.{alias.name}" if base else alias.name
        chosen = candidate if candidate in known else (base if base in known else "")
        if chosen and chosen != module:
            targets.add(chosen)
    return targets


def scan_imports(package: Path) -> dict[str, set[str]]:
    """Directed import graph. Keys are modules; values are the modules they import."""
    named = module_index(package)
    known = set(named.values())
    graph = {module: set() for module in known}
    for path, module in named.items():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                graph[module].update(import_targets(node, module, path, known))
    return graph


def _pop_component(stack: list[str], on_stack: set[str], root: str) -> list[str]:
    """Modules of the component whose root has just finished."""
    component: list[str] = []
    while True:
        found = stack.pop()
        on_stack.remove(found)
        component.append(found)
        if found == root:
            return component


def _by_size_then_name(component: list[str]) -> tuple[int, str]:
    return (-len(component), component[0])


def strongly_connected(graph: dict[str, set[str]]) -> list[list[str]]:
    """Components of two or more modules, each sorted, largest first."""
    index: dict[str, int] = {}
    low: dict[str, int] = {}
    stack: list[str] = []
    on_stack: set[str] = set()
    components: list[list[str]] = []
    counter = 0

    def visit(module: str) -> None:
        nonlocal counter
        index[module] = low[module] = counter
        counter += 1
        stack.append(module)
        on_stack.add(module)
        for target in graph.get(module, ()):
            if target not in index:
                visit(target)
                low[module] = min(low[module], low[target])
            elif target in on_stack:
                low[module] = min(low[module], index[target])
        if low[module] == index[module]:
            component = _pop_component(stack, on_stack, module)
            if len(component) > 1:
                components.append(sorted(component))

    for module in sorted(graph):
        if module not in index:
            visit(module)
    components.sort(key=_by_size_then_name)
    return components


def entry_point_names(package: Path) -> set[str]:
    """bundled_scripts command modules, plus the grind-session cleanup module."""
    bundled = package / "bundled_scripts"
    names: set[str] = set()
    for path in sorted(bundled.glob("*.py")):
        if path.name == "__init__.py":
            continue
        module = f"specy_road.bundled_scripts.{path.stem}"
        if path.stem == CLEANUP_ENTRY_POINT:
            names.add(module)
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        if any(isinstance(node, ast.FunctionDef) and node.name == "main" for node in tree.body):
            names.add(module)
    return names


def entry_point_edges(
    graph: dict[str, set[str]], points: set[str]
) -> list[tuple[str, str]]:
    """Imports whose target is a bundled_scripts entry point."""
    edges = [
        (source, target)
        for source, targets in graph.items()
        for target in targets
        if target in points
    ]
    return sorted(edges)


#: The subpackage whose members the gate, the CLI and the GUI reach only through its ``__init__``.
ORCHESTRATION = "specy_road.orchestration"
#: Module-name prefixes of the review gate and the PM GUI server.
INTERFACE_CALLER_PREFIXES = ("specy_road.review_gate", "specy_road.gui_app")


def orchestration_internal_imports(
    graph: dict[str, set[str]], points: set[str]
) -> list[tuple[str, str]]:
    """Imports of an orchestration member by the review gate, CLI entry points and gui_app."""
    callers = {
        module
        for module in graph
        if module in points
        or module == "specy_road.cli"
        or module.startswith(INTERFACE_CALLER_PREFIXES)
    }
    return sorted(
        (source, target)
        for source in callers
        for target in graph[source]
        if target.startswith(f"{ORCHESTRATION}.")
    )


def build_report(package: Path) -> dict:
    """The committed-report document for ``package``."""
    graph = scan_imports(package)
    components = strongly_connected(graph)
    points = entry_point_names(package)
    edges = entry_point_edges(graph, points)
    internal = orchestration_internal_imports(graph, points)
    return {
        "generated": date.today().isoformat(),
        "tool": "ast import scan (nested imports included)",
        "components": [{"size": len(component), "modules": component} for component in components],
        "entry_point_edges": [{"from": source, "to": target} for source, target in edges],
        "orchestration_internal_imports": [
            {"from": source, "to": target} for source, target in internal
        ],
    }


def _stem(module: str) -> str:
    return module.rsplit(".", 1)[-1]


def _named_lines(report: dict) -> list[str]:
    """One line per acceptance pair, with that component's size."""
    lines: list[str] = []
    saw_loader = False
    saw_crud = False
    for component in report.get("components", []):
        stems = {_stem(module) for module in component["modules"]}
        size = component["size"]
        if "roadmap_load" in stems and "finish_ancestor_rollup" in stems:
            saw_loader = True
            lines.append(
                f"component size {size} contains roadmap_load and finish_ancestor_rollup"
            )
        crud = sorted(stem for stem in stems if stem.startswith("roadmap_crud"))
        if crud and "chore_cli" in stems:
            saw_crud = True
            lines.append(f"component size {size} contains {crud[0]} and chore_cli")
    if not saw_loader:
        lines.append("no component contains roadmap_load and finish_ancestor_rollup")
    if not saw_crud:
        lines.append("no component contains a roadmap_crud module and chore_cli")
    return lines


def _fmt(modules: frozenset[str]) -> str:
    return "[" + ", ".join(sorted(modules)) + "]"


def _section(title: str, rows: list[str]) -> str:
    body = "\n".join(f"  {row}" for row in rows) if rows else "  (none)"
    return f"{title}:\n{body}"


def _component_sets(report: dict) -> list[frozenset[str]]:
    return [frozenset(component["modules"]) for component in report.get("components", [])]


def _edge_set(report: dict) -> set[tuple[str, str]]:
    return {(edge["from"], edge["to"]) for edge in report.get("entry_point_edges", [])}


def render_difference(current: dict, baseline: dict) -> str:
    """Text of how ``current`` differs from ``baseline``. Empty sections stay visible."""
    current_sets = _component_sets(current)
    baseline_sets = _component_sets(baseline)
    current_members: set[str] = set()
    baseline_members: set[str] = set()
    for modules in current_sets:
        current_members |= modules
    for modules in baseline_sets:
        baseline_members |= modules

    merges = []
    for component in current_sets:
        hits = [old for old in baseline_sets if old & component]
        if len(hits) > 1:
            parts = " + ".join(_fmt(old) for old in sorted(hits, key=sorted))
            merges.append(f"{parts} -> {_fmt(component)}")
    splits = []
    for component in baseline_sets:
        hits = [new for new in current_sets if new & component]
        if len(hits) > 1:
            parts = " + ".join(_fmt(new) for new in sorted(hits, key=sorted))
            splits.append(f"{_fmt(component)} -> {parts}")

    added_edges = sorted(_edge_set(current) - _edge_set(baseline))
    removed_edges = sorted(_edge_set(baseline) - _edge_set(current))
    added = sorted(current_members - baseline_members)
    removed = sorted(baseline_members - current_members)
    lines = [
        f"import components: {len(current.get('components', []))}",
        f"entry-point edges: {len(current.get('entry_point_edges', []))}",
        *_named_lines(current),
        _section("members added", added),
        _section("members removed", removed),
        _section("components merged", merges),
        _section("components split", splits),
        _section("entry-point edges added", [f"{src} -> {dst}" for src, dst in added_edges]),
        _section("entry-point edges removed", [f"{src} -> {dst}" for src, dst in removed_edges]),
        _section(
            "orchestration internals imported by the gate, CLI or GUI",
            [
                f"{edge['from']} -> {edge['to']}"
                for edge in current.get("orchestration_internal_imports", [])
            ],
        ),
    ]
    if not any((added, removed, merges, splits, added_edges, removed_edges)):
        lines.append("no difference from the committed report")
    return "\n".join(lines) + "\n"


def load_report(path: Path) -> dict:
    """The committed report, or an empty one when the file is not there yet."""
    if not path.is_file():
        return {"components": [], "entry_point_edges": []}
    return json.loads(path.read_text(encoding="utf-8"))


def write_report(path: Path, report: dict) -> None:
    """Rewrite the committed report."""
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    """Print the difference from the committed report, or rewrite it with ``--write``."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--package", default=Path("specy_road"), type=Path)
    parser.add_argument(
        "--baseline", default=Path("constraints/import-layers-baseline.json"), type=Path
    )
    parser.add_argument("--write", action="store_true", help="rewrite the committed report")
    args = parser.parse_args(argv)

    report = build_report(args.package)
    if args.write:
        write_report(args.baseline, report)
        print(
            f"wrote {len(report['components'])} component(s) and "
            f"{len(report['entry_point_edges'])} entry-point edge(s) to {args.baseline}"
        )
        print("\n".join(_named_lines(report)))
        return 0
    print(render_difference(report, load_report(args.baseline)), end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
