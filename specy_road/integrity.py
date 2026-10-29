"""Test-integrity findings between two commits, using git objects only.

Compares a merge base to a leaf head: removed tests, new skips, lost asserts,
and pytest-related config edits. Python per-function checks use AST over
``git show <commit>:<path>``; no checkout and no writes.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from specy_road.git_changed_paths import diff_paths
from specy_road.git_subprocess import git_stdout, git_text

_CONFIG_NAMES = frozenset({"pytest.ini", "tox.ini", "setup.cfg"})


@dataclass(frozen=True, order=True)
class Finding:
    kind: str
    path: str
    test: str = ""
    detail: str = ""

    def line(self) -> str:
        if self.kind == "removed-test":
            return f"removed-test: {self.path}::{self.test}"
        if self.kind == "removed-test-file":
            return f"removed-test-file: {self.path}"
        if self.kind == "new-skip":
            return f"new-skip: {self.path}::{self.test}"
        if self.kind == "assert-loss":
            return f"assert-loss: {self.path}::{self.test} {self.detail}"
        if self.kind == "config-change":
            return f"config-change: {self.path}"
        raise ValueError(self.kind)

    def as_json(self) -> dict[str, str]:
        return {"kind": self.kind, "path": self.path, "test": self.test, "detail": self.detail}


def compare_integrity(repo_root: Path, base: str, ref: str) -> list[Finding]:
    """Findings for ``base..ref``; sorted by their printed line."""
    root = repo_root.resolve()
    findings: list[Finding] = []
    base_files = _tree_paths(root, base)
    ref_files = _tree_paths(root, ref)
    findings.extend(_removed_test_files(base_files, ref_files))
    py_paths = sorted(p for p in base_files | ref_files if _is_python_test_module(p))
    for path in py_paths:
        base_src = _file_at(root, base, path)
        ref_src = _file_at(root, ref, path)
        base_tests = _test_functions(base_src) if base_src is not None else {}
        ref_tests = _test_functions(ref_src) if ref_src is not None else {}
        for qual, _ in sorted(base_tests.items()):
            if qual not in ref_tests:
                findings.append(Finding("removed-test", path, qual))
        for qual in sorted(set(base_tests) & set(ref_tests)):
            b_node, r_node = base_tests[qual], ref_tests[qual]
            if not _has_skip(b_node) and _has_skip(r_node):
                findings.append(Finding("new-skip", path, qual))
            b_count, r_count = _assert_count(b_node), _assert_count(r_node)
            if r_count < b_count:
                findings.append(Finding("assert-loss", path, qual, f"{b_count}->{r_count}"))
    findings.extend(_config_findings(root, base, ref))
    return sorted(findings, key=lambda f: f.line())


def findings_to_json(findings: list[Finding]) -> dict[str, list[dict[str, str]]]:
    return {"findings": [f.as_json() for f in sorted(findings, key=lambda f: f.line())]}


def _tree_paths(root: Path, commit: str) -> set[str]:
    out = git_text(["ls-tree", "-r", "--name-only", "-z", commit], root)
    if not out:
        return set()
    return {p for p in out.split("\0") if p}


def _file_at(root: Path, commit: str, path: str) -> str | None:
    return git_stdout(["show", f"{commit}:{path}"], root)


def _is_python_test_module(path: str) -> bool:
    name = PurePosixPath(path).name
    return (name.startswith("test_") and name.endswith(".py")) or name.endswith("_test.py")


def _is_removed_test_file(path: str) -> bool:
    name = PurePosixPath(path).name
    if name.startswith("test_") and name.endswith(".py"):
        return True
    if name.endswith("_test.py"):
        return True
    if ".test." in name:
        return True
    if ".spec." in name:
        return True
    return name.endswith("_test.go")


def _removed_test_files(base_files: set[str], ref_files: set[str]) -> list[Finding]:
    out: list[Finding] = []
    for path in sorted(base_files):
        if path not in ref_files and _is_removed_test_file(path):
            out.append(Finding("removed-test-file", path))
    return out


def _config_findings(root: Path, base: str, ref: str) -> list[Finding]:
    changed = diff_paths(root, f"{base}...{ref}") or []
    out: list[Finding] = []
    for path in changed:
        base_name = PurePosixPath(path).name
        if base_name == "conftest.py" or base_name in _CONFIG_NAMES:
            out.append(Finding("config-change", path))
            continue
        if base_name == "pyproject.toml" and _pytest_table_changed(
            _file_at(root, base, path), _file_at(root, ref, path)
        ):
            out.append(Finding("config-change", path))
    return out


def _pytest_table_changed(base_text: str | None, ref_text: str | None) -> bool:
    return _pytest_table_text(base_text) != _pytest_table_text(ref_text)


def _pytest_table_text(text: str | None) -> str:
    if not text:
        return ""
    lines: list[str] = []
    in_table = False
    for line in text.splitlines():
        if line.startswith("[tool.pytest"):
            in_table = True
            lines.append(line)
            continue
        if in_table:
            if line.startswith("[") and not line.startswith("[tool.pytest"):
                in_table = False
            elif in_table:
                lines.append(line)
    return "\n".join(lines)


def _test_functions(source: str | None) -> dict[str, ast.FunctionDef | ast.AsyncFunctionDef]:
    if not source:
        return {}
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return {}
    out: dict[str, ast.FunctionDef | ast.AsyncFunctionDef] = {}

    def visit_class(class_node: ast.ClassDef, prefix: str) -> None:
        for item in class_node.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name.startswith("test_"):
                out[f"{prefix}::{item.name}"] = item
            elif isinstance(item, ast.ClassDef):
                visit_class(item, f"{prefix}::{item.name}")

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_"):
            out[node.name] = node
        elif isinstance(node, ast.ClassDef):
            visit_class(node, node.name)
    return out


def _has_skip(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    for dec in node.decorator_list:
        if _decorator_skips(dec):
            return True
    for sub in ast.walk(node):
        if isinstance(sub, ast.Call) and _call_skips(sub):
            return True
    return False


def _decorator_skips(dec: ast.expr) -> bool:
    if isinstance(dec, ast.Name) and dec.id in {"skip", "skipIf", "skipUnless", "expectedFailure"}:
        return True
    if isinstance(dec, ast.Attribute) and dec.attr in {"skip", "skipIf", "skipUnless", "expectedFailure"}:
        return True
    if not isinstance(dec, ast.Call):
        return False
    target = dec.func
    if isinstance(target, ast.Name) and target.id in {"skip", "skipIf", "skipUnless", "expectedFailure"}:
        return True
    if isinstance(target, ast.Attribute):
        if target.attr in {"skip", "skipif", "xfail"} and _is_pytest_mark(target.value):
            return True
        if target.attr in {"skip", "skipIf", "skipUnless", "expectedFailure"}:
            return True
    return False


def _is_pytest_mark(value: ast.expr) -> bool:
    return isinstance(value, ast.Attribute) and value.attr == "mark" and isinstance(value.value, ast.Name) and value.value.id == "pytest"


def _call_skips(call: ast.Call) -> bool:
    func = call.func
    if isinstance(func, ast.Attribute) and func.attr in {"skip", "xfail", "importorskip"}:
        return isinstance(func.value, ast.Name) and func.value.id == "pytest"
    return False


def _assert_count(node: ast.FunctionDef | ast.AsyncFunctionDef) -> int:
    count = 0
    for sub in ast.walk(node):
        if isinstance(sub, ast.Assert):
            count += 1
        elif isinstance(sub, ast.With):
            for item in sub.items:
                ctx = item.context_expr
                if isinstance(ctx, ast.Call) and isinstance(ctx.func, ast.Attribute):
                    if ctx.func.attr == "raises" and isinstance(ctx.func.value, ast.Name) and ctx.func.value.id == "pytest":
                        count += 1
        elif isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute):
            if sub.func.attr.startswith("assert") and isinstance(sub.func.value, ast.Name) and sub.func.value.id == "self":
                count += 1
    return count
