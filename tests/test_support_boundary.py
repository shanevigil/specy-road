"""The support boundary: no test module imports a test_* module, no repo-helper file, no stray manifest write."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TESTS = ROOT / "tests"
ALLOW = TESTS / "support" / "manifest_allowlist.txt"


def _modules():
    return sorted(path for path in TESTS.rglob("*.py") if path.is_file())


def _imports_a_test_module(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    hits = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            parts = node.module.split(".")
            if parts[-1].startswith("test_") or parts[0].startswith("test_"):
                hits.append(f"{path.relative_to(ROOT)}:{node.lineno}: from {node.module}")
        elif isinstance(node, ast.Import):
            for alias in node.names:
                parts = alias.name.split(".")
                if parts[-1].startswith("test_") or parts[0].startswith("test_"):
                    hits.append(f"{path.relative_to(ROOT)}:{node.lineno}: import {alias.name}")
    return hits


def _writes_manifest(node: ast.Call) -> bool:
    func = node.func
    if not isinstance(func, ast.Attribute):
        return False
    if func.attr == "write_text":
        return True
    return (
        func.attr == "dump"
        and isinstance(func.value, ast.Name)
        and func.value.id == "json"
    )


def _enclosing_function(node: ast.AST, parents: dict[int, ast.AST]) -> str | None:
    host = node
    while id(host) in parents:
        host = parents[id(host)]
        if isinstance(host, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return host.name
    return None


def _manifest_writes(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    tree = ast.parse(text, filename=str(path))
    parents: dict[int, ast.AST] = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parents[id(child)] = node
    hits = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not _writes_manifest(node):
            continue
        segment = ast.get_source_segment(text, node) or ""
        if "manifest.json" not in segment:
            continue
        fn = _enclosing_function(node, parents)
        rel = path.relative_to(ROOT).as_posix()
        if rel == "tests/support/roadmap.py" and fn == "roadmap_repo":
            continue
        hits.append(f"{rel}:{node.lineno}")
    return hits


def _allowed() -> set[str]:
    allowed = set()
    for line in ALLOW.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        allowed.add(line.split(":", 1)[0].strip())
    return allowed


def test_no_test_module_imports_a_test_module_and_manifests_stay_in_the_builder() -> None:
    """Grep-style scan: a test_* import, a ``*_repo_helpers.py`` file, or an unlisted manifest write fails."""
    imports = [hit for path in _modules() for hit in _imports_a_test_module(path)]
    helpers = sorted(path.relative_to(ROOT).as_posix() for path in TESTS.rglob("*_repo_helpers.py"))
    allowed = _allowed()
    writes = []
    for path in _modules():
        for hit in _manifest_writes(path):
            rel = hit.split(":", 1)[0]
            if rel not in allowed:
                writes.append(hit)
    assert imports == []
    assert helpers == []
    assert writes == []
