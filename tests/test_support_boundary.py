"""The support boundary: no test module imports a test_* module, no repo-helper file,
no stray manifest write.

A manifest write is ``write_text`` or ``json.dump`` whose path is visible in the call, or whose path
was assigned first. A name is a manifest path when the assignment spells ``manifest.json`` (and is
not only a string constant), when it is a copy of such a name, or when it is a ``/`` join that uses
a string constant ending in ``manifest.json``. A string that merely contains those characters, such
as a shell command, is not a path. The scan does not follow ``write_bytes``, an attribute, or a
subscript.
"""

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
    return func.attr == "dump" and isinstance(func.value, ast.Name) and func.value.id == "json"


def _enclosing_function(node: ast.AST, parents: dict[int, ast.AST]) -> str | None:
    host = node
    while id(host) in parents:
        host = parents[id(host)]
        if isinstance(host, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return host.name
    return None


def _names(node: ast.AST):
    return [child.id for child in ast.walk(node) if isinstance(child, ast.Name)]


def _is_manifest_path(expr: ast.AST, text: str, paths: set[str], tokens: set[str]) -> bool:
    """The one path rule: spelled in the expression, copied, or joined from a filename constant."""
    segment = ast.get_source_segment(text, expr) or ""
    if "manifest.json" in segment and not isinstance(expr, ast.Constant):
        return True
    if isinstance(expr, ast.Name) and expr.id in paths:
        return True
    joined = isinstance(expr, ast.BinOp) and isinstance(expr.op, ast.Div)
    return joined and any(name in paths or name in tokens for name in _names(expr))


def _bindings(body: list[ast.stmt]) -> list[tuple[str, ast.AST]]:
    found = []
    for stmt in body:
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        if isinstance(stmt, ast.Assign):
            found.extend(
                (target.id, stmt.value) for target in stmt.targets if isinstance(target, ast.Name)
            )
        elif (
            isinstance(stmt, ast.AnnAssign)
            and isinstance(stmt.target, ast.Name)
            and stmt.value is not None
        ):
            found.append((stmt.target.id, stmt.value))
        for node in _expr_nodes(stmt):
            if isinstance(node, ast.NamedExpr) and isinstance(node.target, ast.Name):
                found.append((node.target.id, node.value))
    return found


def _expr_nodes(stmt: ast.stmt):
    stack = [stmt]
    while stack:
        node = stack.pop()
        nested = isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        if nested and node is not stmt:
            continue
        yield node
        stack.extend(ast.iter_child_nodes(node))


def _scope_paths(
    body: list[ast.stmt], text: str, paths: set[str], tokens: set[str],
) -> tuple[set[str], set[str]]:
    paths, tokens = set(paths), set(tokens)
    binds = _bindings(body)
    for _ in range(len(binds) + 1):
        grew = False
        for name, value in binds:
            filename = isinstance(value, ast.Constant) and isinstance(value.value, str)
            if filename and value.value.endswith("manifest.json"):
                if name not in tokens:
                    tokens.add(name)
                    grew = True
            elif _is_manifest_path(value, text, paths, tokens) and name not in paths:
                paths.add(name)
                grew = True
        if not grew:
            break
    return paths, tokens


def _scope_table(tree: ast.AST, text: str) -> dict[int, tuple[set[str], set[str]]]:
    table: dict[int, tuple[set[str], set[str]]] = {}

    def visit(node: ast.AST, paths: set[str], tokens: set[str]) -> None:
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            paths, tokens = _scope_paths(node.body, text, paths, tokens)
            table[id(node)] = (paths, tokens)
        for child in ast.iter_child_nodes(node):
            visit(child, paths, tokens)

    visit(tree, set(), set())
    return table


def _call_uses_manifest_path(node: ast.Call, text: str, paths: set[str], tokens: set[str]) -> bool:
    if isinstance(node.func, ast.Attribute) and node.func.attr == "write_text":
        return _is_manifest_path(node.func.value, text, paths, tokens)
    return any(_is_manifest_path(arg, text, paths, tokens) for arg in node.args)


def _manifest_writes(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    tree = ast.parse(text, filename=str(path))
    parents: dict[int, ast.AST] = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parents[id(child)] = node
    scopes = _scope_table(tree, text)
    hits = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not _writes_manifest(node):
            continue
        paths, tokens = _visible(node, parents, scopes)
        if not _call_uses_manifest_path(node, text, paths, tokens):
            continue
        fn = _enclosing_function(node, parents)
        rel = path.relative_to(ROOT).as_posix() if path.is_relative_to(ROOT) else path.name
        if rel == "tests/support/roadmap.py" and fn == "roadmap_repo":
            continue
        hits.append(f"{rel}:{node.lineno}")
    return hits


def _visible(
    node: ast.AST,
    parents: dict[int, ast.AST],
    scopes: dict[int, tuple[set[str], set[str]]],
) -> tuple[set[str], set[str]]:
    paths: set[str] = set()
    tokens: set[str] = set()
    host = node
    while id(host) in parents:
        host = parents[id(host)]
        if id(host) in scopes:
            seen_paths, seen_tokens = scopes[id(host)]
            paths |= seen_paths
            tokens |= seen_tokens
    return paths, tokens


def _allowed() -> set[str]:
    allowed = set()
    for line in ALLOW.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        allowed.add(line.split(":", 1)[0].strip())
    return allowed


def test_no_test_module_imports_a_test_module_and_manifests_stay_in_the_builder() -> None:
    """A test_* import, a ``*_repo_helpers.py`` file, or an unlisted manifest write fails."""
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


def test_a_path_assigned_before_the_write_is_still_a_manifest_write(tmp_path: Path) -> None:
    """A spelled path, a copied name, and a join of a filename constant all count."""
    source = tmp_path / "writes.py"
    source.write_text(
        "\n".join([
            'NAME = ".specyrd/manifest.json"',
            'CMD = "test -f roadmap/manifest.json"',
            "def spelled(repo):",
            '    (repo / "roadmap" / "manifest.json").write_text("{}", encoding="utf-8")',
            "def assigned(repo):",
            '    manifest = repo / "roadmap" / "manifest.json"',
            '    manifest.write_text("{}", encoding="utf-8")',
            "def joined(root):",
            "    path = root / NAME",
            '    path.write_text("{}", encoding="utf-8")',
            "def command(repo):",
            "    repo = run(repo, CMD)",
            '    (repo / "notes.md").write_text("x", encoding="utf-8")',
            "",
        ]),
        encoding="utf-8",
    )
    hits = _manifest_writes(source)
    assert [hit.split(":", 1)[1] for hit in hits] == ["4", "7", "10"]
