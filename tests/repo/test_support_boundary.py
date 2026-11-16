"""The support boundary: no test module imports a test_* module, no repo-helper file,
no stray manifest write.

An import brings in a test module when the module path or an imported name starts
with ``test_``. ``from tests import test_review_gate`` counts; ``from tests.support
import roadmap`` does not.

A manifest write is ``write_text`` on a manifest path, or ``json.dump`` whose file
is a manifest path, a name bound to ``open`` of one, or an ``open`` call on one.
A name is a manifest path when the assignment spells ``manifest.json`` and is not
only a string constant, when it is a copy of such a name, or when it is a ``/``
join of a string constant ending in ``manifest.json``. A string that only contains
those characters is not a path. ``open`` is bound by assignment or by ``with ... as``
and the ``with`` name is visible only inside that statement. The allowlist names
each write (``path:line``); a second write in that file is still a write.

A test reads this checkout when it, or a function in the same file it reaches,
reads a file whose path is the checkout root and not under ``tests/``. The root is
the imported checkout, a ``Path(__file__)`` walk up to it, or a name assigned from
one of those. That test carries the ``repo`` marker.

Limits: ``write_bytes`` is not a write. A path or file stored on an attribute or
in a subscript is not followed. An alias of ``open`` is not followed. A file
object passed into another function is not followed. A subprocess working
directory is not a read, and a read in another module is not followed.
"""

from __future__ import annotations

from tests.support import REPO
import ast
from pathlib import Path

import pytest

ROOT = REPO
TESTS = ROOT / "tests"
ALLOW = TESTS / "support" / "manifest_allowlist.txt"
_READS = frozenset({"read_text", "read_bytes", "rglob", "glob", "iterdir", "open"})


def _modules():
    return sorted(path for path in TESTS.rglob("*.py") if path.is_file())


def _where(path: Path) -> str:
    if path.is_relative_to(ROOT):
        return path.relative_to(ROOT).as_posix()
    return path.name


def _starts_test(name: str) -> bool:
    return name.startswith("test_")


def _from_import_is_a_test(node: ast.ImportFrom) -> bool:
    parts = node.module.split(".") if node.module else []
    imported = [alias.name for alias in node.names]
    return any(_starts_test(part) for part in parts) or any(_starts_test(name) for name in imported)


def _imports_a_test_module(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    hits = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and _from_import_is_a_test(node):
            hits.append(f"{_where(path)}:{node.lineno}: from {node.module or '.'}")
        elif isinstance(node, ast.Import):
            for alias in node.names:
                parts = alias.name.split(".")
                if any(_starts_test(part) for part in parts):
                    hits.append(f"{_where(path)}:{node.lineno}: import {alias.name}")
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
    segment = _source(text, expr)
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


def _opens_manifest(expr: ast.AST, text: str, paths: set[str], tokens: set[str]) -> bool:
    if not isinstance(expr, ast.Call):
        return False
    func = expr.func
    if isinstance(func, ast.Name) and func.id == "open":
        return any(_is_manifest_path(arg, text, paths, tokens) for arg in expr.args)
    if isinstance(func, ast.Attribute) and func.attr == "open":
        return _is_manifest_path(func.value, text, paths, tokens)
    return False


def _bind_kind(
    name: str, value: ast.AST, text: str, scope: tuple[set[str], set[str], set[str]],
) -> str | None:
    paths, tokens, opened = scope
    filename = isinstance(value, ast.Constant) and isinstance(value.value, str)
    if filename and value.value.endswith("manifest.json") and name not in tokens:
        return "token"
    if _opens_manifest(value, text, paths, tokens) and name not in opened:
        return "opened"
    if _is_manifest_path(value, text, paths, tokens) and name not in paths:
        return "path"
    return None


def _scope_paths(
    body: list[ast.stmt], text: str, paths: set[str], tokens: set[str], opened: set[str],
) -> tuple[set[str], set[str], set[str]]:
    paths, tokens, opened = set(paths), set(tokens), set(opened)
    binds = _bindings(body)
    for _ in range(len(binds) + 1):
        grew = False
        for name, value in binds:
            kind = _bind_kind(name, value, text, (paths, tokens, opened))
            if kind == "token":
                tokens.add(name)
                grew = True
            elif kind == "opened":
                opened.add(name)
                grew = True
            elif kind == "path":
                paths.add(name)
                grew = True
        if not grew:
            break
    return paths, tokens, opened


def _with_opened(node: ast.AST, text: str, paths: set[str], tokens: set[str]) -> set[str]:
    opened = set()
    for item in node.items:
        target = item.optional_vars
        if isinstance(target, ast.Name) and _opens_manifest(item.context_expr, text, paths, tokens):
            opened.add(target.id)
    return opened


def _scope_table(tree: ast.AST, text: str) -> dict[int, tuple[set[str], set[str], set[str]]]:
    table: dict[int, tuple[set[str], set[str], set[str]]] = {}

    def visit(node: ast.AST, paths: set[str], tokens: set[str], opened: set[str]) -> None:
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            paths, tokens, opened = _scope_paths(node.body, text, paths, tokens, opened)
            table[id(node)] = (paths, tokens, opened)
        elif isinstance(node, (ast.With, ast.AsyncWith)):
            opened = opened | _with_opened(node, text, paths, tokens)
            table[id(node)] = (paths, tokens, opened)
        for child in ast.iter_child_nodes(node):
            visit(child, paths, tokens, opened)

    visit(tree, set(), set(), set())
    return table


def _dump_target(node: ast.Call) -> ast.AST | None:
    file_arg = node.args[1:]
    if file_arg:
        return file_arg[0]
    for keyword in node.keywords:
        if keyword.arg == "file":
            return keyword.value
    return None


def _call_uses_manifest_path(
    node: ast.Call, text: str, paths: set[str], tokens: set[str], opened: set[str],
) -> bool:
    if isinstance(node.func, ast.Attribute) and node.func.attr == "write_text":
        return _is_manifest_path(node.func.value, text, paths, tokens)
    target = _dump_target(node)
    if target is None:
        return False
    if isinstance(target, ast.Name) and target.id in opened:
        return True
    if _opens_manifest(target, text, paths, tokens):
        return True
    return _is_manifest_path(target, text, paths, tokens)


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
        paths, tokens, opened = _visible(node, parents, scopes)
        if not _call_uses_manifest_path(node, text, paths, tokens, opened):
            continue
        fn = _enclosing_function(node, parents)
        rel = _where(path)
        if rel == "tests/support/roadmap.py" and fn == "roadmap_repo":
            continue
        hits.append(f"{rel}:{node.lineno}")
    return sorted(hits, key=lambda hit: int(hit.rsplit(":", 1)[1]))


def _visible(
    node: ast.AST,
    parents: dict[int, ast.AST],
    scopes: dict[int, tuple[set[str], set[str], set[str]]],
) -> tuple[set[str], set[str], set[str]]:
    paths: set[str] = set()
    tokens: set[str] = set()
    opened: set[str] = set()
    host = node
    while id(host) in parents:
        host = parents[id(host)]
        if id(host) in scopes:
            seen_paths, seen_tokens, seen_opened = scopes[id(host)]
            paths |= seen_paths
            tokens |= seen_tokens
            opened |= seen_opened
    return paths, tokens, opened


def _allowed() -> set[str]:
    allowed = set()
    for line in ALLOW.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        path, rest = line.split(":", 1)
        line_no = rest.split(":", 1)[0].strip()
        allowed.add(f"{path.strip()}:{line_no}")
    return allowed


def _tests_segment(segment: str) -> bool:
    return '"tests"' in segment or "'tests'" in segment


def _source(text: str, node: ast.AST) -> str:
    """The node's source. Lines are split once per text; ``str.splitlines`` is not used."""
    if getattr(node, "end_lineno", None) is None:
        return ""
    cached = _source.lines
    if cached[0] is not text:
        cached = (text, text.split("\n"))
        _source.lines = cached
    lines = cached[1]
    start, end = node.lineno - 1, node.end_lineno - 1
    if start == end:
        return lines[start][node.col_offset:node.end_col_offset]
    parts = [lines[start][node.col_offset:]]
    parts.extend(lines[start + 1:end])
    parts.append(lines[end][:node.end_col_offset])
    return "\n".join(parts)


_source.lines = (None, [])


def _mentions(node: ast.AST, names: set[str]) -> bool:
    return any(isinstance(child, ast.Name) and child.id in names for child in ast.walk(node))


def _reaches_checkout(segment: str, path: Path) -> bool:
    if "__file__" not in segment or _tests_segment(segment):
        return False
    directories = len(path.relative_to(ROOT).parts) - 1
    if f"parents[{directories}]" in segment:
        return True
    return segment.count(".parent") == directories + 1


def _imported_repo(tree: ast.AST) -> set[str]:
    names = set()
    for node in tree.body:
        if not isinstance(node, ast.ImportFrom) or node.module not in {
            "tests.helpers", "tests.support",
        }:
            continue
        for alias in node.names:
            if alias.name == "REPO":
                names.add(alias.asname or alias.name)
    return names


def _derive(binds, text: str, path: Path, seed: set[str]) -> set[str]:
    names = set(seed)
    for _ in range(len(binds) + 1):
        grew = False
        for name, value in binds:
            if name in names:
                continue
            segment = _source(text, value)
            if _tests_segment(segment):
                continue
            if _mentions(value, names) or _reaches_checkout(segment, path):
                names.add(name)
                grew = True
        if not grew:
            break
    return names


def _product_names(tree: ast.AST, text: str, path: Path) -> set[str]:
    return _derive(_bindings(tree.body), text, path, _imported_repo(tree))


def _local_product(fn: ast.FunctionDef, text: str, path: Path, product: set[str]) -> set[str]:
    return _derive(_bindings(fn.body), text, path, product)


def _is_product_read(node: ast.AST, text: str, names: set[str]) -> bool:
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    attribute = isinstance(func, ast.Attribute) and func.attr in _READS
    builtin = isinstance(func, ast.Name) and func.id == "open"
    if not attribute and not builtin:
        return False
    segment = _source(text, node)
    return not _tests_segment(segment) and _mentions(node, names)


def _functions(tree: ast.AST) -> dict[str, ast.FunctionDef]:
    return {node.name: node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)}


def _scan_function(fn: ast.FunctionDef, text: str, names: set[str]) -> tuple[bool, set[str]]:
    called: set[str] = set()
    reads = False
    for node in ast.walk(fn):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            called.add(node.func.id)
        if not reads and _is_product_read(node, text, names):
            reads = True
    return reads, called


def _readers(funcs, text: str, path: Path, product: set[str]) -> set[str]:
    direct: set[str] = set()
    called: dict[str, set[str]] = {}
    for name, fn in funcs.items():
        reads, targets = _scan_function(fn, text, _local_product(fn, text, path, product))
        called[name] = targets
        if reads:
            direct.add(name)
    reached = set(direct)
    for _ in range(len(funcs) + 1):
        grew = False
        for name, targets in called.items():
            if name in reached:
                continue
            if targets & reached:
                reached.add(name)
                grew = True
        if not grew:
            break
    return reached


def _attr_chain(node: ast.AST) -> list[str]:
    if isinstance(node, ast.Call):
        node = node.func
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return parts[::-1]


def _is_repo_mark(node: ast.AST) -> bool:
    return _attr_chain(node) == ["pytest", "mark", "repo"]


def _mark_expr(expr: ast.AST) -> bool:
    if isinstance(expr, (ast.List, ast.Tuple)):
        return any(_mark_expr(item) for item in expr.elts)
    return _is_repo_mark(expr)


def _module_marked(tree: ast.AST) -> bool:
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        targets = [target.id for target in node.targets if isinstance(target, ast.Name)]
        if "pytestmark" in targets and _mark_expr(node.value):
            return True
    return False


def _function_marked(fn: ast.FunctionDef) -> bool:
    return any(_is_repo_mark(item) for item in fn.decorator_list)


def _unmarked_repo_tests() -> list[str]:
    missing = []
    for path in _modules():
        text = path.read_text(encoding="utf-8")
        if "REPO" not in text and "__file__" not in text:
            continue
        if not any(name in text for name in _READS):
            continue
        tree = ast.parse(text, filename=str(path))
        if _module_marked(tree):
            continue
        product = _product_names(tree, text, path)
        funcs = _functions(tree)
        readers = _readers(funcs, text, path, product)
        rel = path.relative_to(ROOT).as_posix()
        for name, fn in funcs.items():
            if name.startswith("test_") and name in readers and not _function_marked(fn):
                missing.append(f"{rel}::{name}")
    return missing


@pytest.mark.slow
def test_no_test_module_imports_a_test_module_and_manifests_stay_in_the_builder() -> None:
    """A test_* import, a ``*_repo_helpers.py`` file, or an unlisted manifest write fails."""
    imports = [hit for path in _modules() for hit in _imports_a_test_module(path)]
    helpers = sorted(path.relative_to(ROOT).as_posix() for path in TESTS.rglob("*_repo_helpers.py"))
    detected = [hit for path in _modules() for hit in _manifest_writes(path)]
    assert imports == []
    assert helpers == []
    assert set(detected) == _allowed()


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


def test_an_imported_name_starting_with_test_is_a_test_module(tmp_path: Path) -> None:
    """``from tests import test_review_gate`` is a test-module import; a support name is not."""
    source = tmp_path / "uses.py"
    source.write_text(
        "\n".join([
            "from tests import test_review_gate",
            "from tests import test_review_gate as gate",
            "from . import test_local",
            "from tests.support import roadmap",
            "import os",
            "",
        ]),
        encoding="utf-8",
    )
    hits = _imports_a_test_module(source)
    assert [hit.split(":")[1] for hit in hits] == ["1", "2", "3"]


def test_json_dump_into_an_opened_manifest_file_is_a_write(tmp_path: Path) -> None:
    """``json.dump`` into an opened manifest file counts; a dump into another file does not."""
    source = tmp_path / "dumps.py"
    source.write_text(
        "\n".join([
            "import json",
            "def opened(repo):",
            "    with open(repo / 'manifest.json', 'w') as file:",
            "        json.dump({}, file)",
            "def direct(repo):",
            "    path = repo / 'roadmap' / 'manifest.json'",
            "    json.dump({}, open(path, 'w'))",
            "def method(repo):",
            "    with (repo / 'manifest.json').open('w') as file:",
            "        json.dump({}, file)",
            "def other(repo):",
            "    with open(repo / 'notes.md', 'w') as file:",
            "        json.dump({}, file)",
            "def keyword(repo):",
            "    file = open(repo / 'manifest.json', 'w')",
            "    json.dump({}, file=file)",
            "",
        ]),
        encoding="utf-8",
    )
    hits = _manifest_writes(source)
    assert [hit.split(":")[1] for hit in hits] == ["4", "7", "10", "16"]


def test_a_second_write_in_an_allowlisted_file_is_still_a_write(tmp_path: Path) -> None:
    """Listing one write does not exempt another write in the same file."""
    source = tmp_path / "extra.py"
    source.write_text(
        "\n".join([
            "def one(repo):",
            "    (repo / 'manifest.json').write_text('{}', encoding='utf-8')",
            "def two(repo):",
            "    (repo / 'roadmap' / 'manifest.json').write_text('{}', encoding='utf-8')",
            "",
        ]),
        encoding="utf-8",
    )
    writes = _manifest_writes(source)
    assert [hit for hit in writes if hit not in {writes[0]}] == [writes[1]]


def test_repository_scans_carry_the_repo_marker() -> None:
    """A test that reads this checkout outside ``tests/`` carries the repo marker.

    The path is the imported checkout root, a ``Path(__file__)`` walk up to that
    root, or a name assigned from one of those. A path under ``tests/`` is a
    fixture. A subprocess working directory is not a read. A path stored on an
    attribute, or a read performed in another module, is not followed.
    """
    assert _unmarked_repo_tests() == []
