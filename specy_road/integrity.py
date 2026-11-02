"""Test-integrity findings between two commits, using git objects only.

Compares a merge base to a leaf head: removed tests, new skips, lost asserts,
pytest-related config edits, added lint suppressions, and lines added to the
baseline files the integration branch lists in ``policy.ratchet_paths``.
Python per-function checks use AST over ``git show <commit>:<path>``; no
checkout and no writes.
"""

from __future__ import annotations

import ast
import re
import subprocess
import tomllib
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from specy_road.git_changed_paths import diff_paths
from specy_road.git_subprocess import DEFAULT_TIMEOUT, git_stdout
from specy_road.orchestration_config import effective_config
from specy_road.review_policy_ref import policy_source

_CONFIG_NAMES = frozenset({"pytest.ini", "tox.ini", "setup.cfg"})
# Lint and coverage suppression markers of Python, TypeScript/JavaScript and Go linters,
# in any case and with any spacing after a colon
_SUPPRESSION = re.compile(
    r"noqa|type:\s*ignore|pragma:\s*no\s+cover|pylint:\s*disable|eslint-disable|@ts-ignore"
    r"|@ts-expect-error|nolint",
    re.IGNORECASE,
)
_HUNK = re.compile(r"@@ -\d+(?:,\d+)? \+(\d+)")
# The leaf's own .gitattributes can mark a file binary (``-diff``), and repo config can set a
# textconv driver, an external diff or a relative diff; none of them may hide an added line.
_DIFF = ("diff", "--no-relative", "--no-color", "--no-ext-diff", "--no-textconv", "--text", "--unified=0")


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
        if self.kind == "new-suppression":
            return f"new-suppression: {self.path}:{self.detail}"
        if self.kind == "baseline-widened":
            return f"baseline-widened: {self.path} +{self.detail}"
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
            (b_skips, b_count), (r_skips, r_count) = base_tests[qual], ref_tests[qual]
            if r_skips > b_skips:
                findings.append(Finding("new-skip", path, qual))
            if r_count < b_count:
                findings.append(Finding("assert-loss", path, qual, f"{b_count}->{r_count}"))
    findings.extend(_config_findings(root, base, ref))
    findings.extend(_suppression_findings(_added_lines(root, base, ref)))
    findings.extend(_ratchet_findings(root, base, ref, integration_ratchet_paths(root)))
    return sorted(findings, key=lambda f: f.line())


def findings_to_json(findings: list[Finding]) -> dict[str, list[dict[str, str]]]:
    return {"findings": [f.as_json() for f in sorted(findings, key=lambda f: f.line())]}


def _tree_paths(root: Path, commit: str) -> set[str]:
    # --full-tree: git-root-relative paths even when ``root`` is a nested project directory
    out = git_stdout(["ls-tree", "-r", "--full-tree", "--name-only", "-z", commit], root)
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


def integration_ratchet_paths(root: Path) -> list[str]:
    """``policy.ratchet_paths`` as committed on the integration branch; empty when unreadable."""
    ref, err = policy_source(root)
    if err or ref is None:
        return []
    config, err = effective_config(root, ref)
    if err:
        return []
    return [p for p in config["policy"].get("ratchet_paths") or [] if isinstance(p, str)]


def _added_lines(root: Path, base: str, ref: str) -> dict[str, list[tuple[int, str]]]:
    """``git-root path -> [(line number at ref, text)]`` for every line ``base..ref`` adds.

    One diff per changed file; the path comes from ``--name-status -z``, never from a
    patch header. Renames are followed, so a moved file's existing lines are not new.
    """
    added: dict[str, list[tuple[int, str]]] = {}
    for paths in _changed_files(root, base, ref):
        lines = _file_additions(root, base, ref, paths, "--find-renames")
        if lines:
            added[paths[-1]] = lines
    return added


def _file_additions(
    root: Path, base: str, ref: str, paths: tuple[str, ...], renames: str
) -> list[tuple[int, str]]:
    return _hunk_additions(_patch(root, [
        *_DIFF, renames, base, ref, "--", *(f":(top,literal){p}" for p in paths),
    ]))


def _patch(root: Path, args: list[str]) -> str:
    """``git <args>`` stdout decoded leniently; empty on failure."""
    return _git_bytes(root, args).decode("utf-8", "replace")


def _git_bytes(root: Path, args: list[str]) -> bytes:
    """``git <args>`` raw stdout; empty on failure.

    Spawned here, not through :mod:`specy_road.git_subprocess`, because that decodes
    strictly: one non-UTF-8 added line or file name would hide every other finding.
    """
    try:
        r = subprocess.run(["git", *args], cwd=root, capture_output=True, timeout=DEFAULT_TIMEOUT, check=False)
    except (OSError, subprocess.SubprocessError):
        return b""
    return r.stdout if r.returncode == 0 else b""


def _changed_files(root: Path, base: str, ref: str) -> list[tuple[str, ...]]:
    """``(path,)`` per changed file, ``(source, destination)`` per rename.

    A name that is not UTF-8 is dropped; a rename keeps its destination alone, so all of
    that file's lines count.
    """
    args = ["diff", "--no-relative", "--name-status", "-z", "--find-renames", base, ref]
    fields = _git_bytes(root, args).split(b"\0")
    out: list[tuple[str, ...]] = []
    i = 0
    while i < len(fields) and fields[i]:
        width = 2 if fields[i][:1] == b"R" else 1
        names = fields[i + 1:i + 1 + width]
        i += 1 + width
        decoded = [_utf8(n) for n in names]
        if names and decoded[-1] is not None:
            out.append(tuple(n for n in decoded if n is not None))
    return out


def _utf8(name: bytes) -> str | None:
    try:
        return name.decode("utf-8")
    except UnicodeDecodeError:
        return None


def _hunk_additions(patch: str) -> list[tuple[int, str]]:
    """Added lines of a one-file ``--unified=0`` patch, counted only inside hunk bodies.

    A type change (symlink to regular file) is two sections; each section's header, up to
    its first ``@@``, is never content. A ``-U0`` hunk body holds only ``+``, ``-`` and
    ``\\`` lines, so a ``diff --git`` line always starts a section.
    """
    out: list[tuple[int, str]] = []
    number: int | None = None
    for raw in patch.split("\n"):
        if raw.startswith("diff --git "):
            number = None
        elif raw.startswith("@@ "):
            match = _HUNK.match(raw)
            number = int(match.group(1)) if match else None
        elif number is not None and raw.startswith("+"):
            out.append((number, raw[1:]))
            number += 1
    return out


def _suppression_findings(added: dict[str, list[tuple[int, str]]]) -> list[Finding]:
    return [
        Finding("new-suppression", path, detail=str(number))
        for path, lines in added.items()
        for number, text in lines
        if _SUPPRESSION.search(text)
    ]


def _ratchet_findings(root: Path, base: str, ref: str, ratchet_paths: list[str]) -> list[Finding]:
    """Renames are not followed: a file moved onto a ratchet path widens it by every line."""
    out: list[Finding] = []
    for path in sorted(set(ratchet_paths)):
        count = len(_file_additions(root, base, ref, (path,), "--no-renames"))
        if count:
            out.append(Finding("baseline-widened", path, detail=str(count)))
    return out


def _pytest_table_changed(base_text: str | None, ref_text: str | None) -> bool:
    return _pytest_tables(base_text) != _pytest_tables(ref_text)


def _pytest_tables(text: str | None) -> object:
    """``tool.pytest*`` tables however TOML spells them; the raw text when it does not parse."""
    if not text:
        return {}
    try:
        tool = tomllib.loads(text).get("tool", {})
    except tomllib.TOMLDecodeError:
        return text
    if not isinstance(tool, dict):
        return {}
    return {k: v for k, v in tool.items() if k.startswith("pytest")}


def _test_functions(source: str | None) -> dict[str, tuple[int, int]]:
    """``qualname -> (skipped definitions, assert count)`` for tests at module or class scope.

    Control-flow blocks (``if``, ``try``, ``with``, ``for``, ``while``, ``match``) run in the
    enclosing scope, so the tests they define count; a function body is its own scope and is
    not searched. A name defined more than once (``if``/``else`` branches) sums its definitions,
    so skipping or weakening any one of them is a finding.
    """
    if not source:
        return {}
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return {}
    out: dict[str, tuple[int, int]] = {}

    def scan(stmts: list[ast.stmt], prefix: str, class_skip: bool) -> None:
        for stmt in stmts:
            if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if stmt.name.startswith("test_"):
                    skips, count = out.get(prefix + stmt.name, (0, 0))
                    skipped = class_skip or _has_skip(stmt)
                    out[prefix + stmt.name] = (skips + skipped, count + _assert_count(stmt))
            elif isinstance(stmt, ast.ClassDef):
                # pytest applies a class's skip mark to every method in it
                inherited = class_skip or any(_decorator_skips(d) for d in stmt.decorator_list)
                scan(stmt.body, f"{prefix}{stmt.name}::", inherited)
            else:
                scan(_block_statements(stmt), prefix, class_skip)

    scan(tree.body, "", False)
    return out


def _block_statements(stmt: ast.stmt) -> list[ast.stmt]:
    """Statements nested in a control-flow block; empty for a simple statement."""
    out: list[ast.stmt] = []
    for field in ("body", "orelse", "finalbody"):
        out.extend(getattr(stmt, field, []))
    for handler in getattr(stmt, "handlers", []):   # try / try*
        out.extend(handler.body)
    for case in getattr(stmt, "cases", []):   # match
        out.extend(case.body)
    return out


def _has_skip(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    for dec in node.decorator_list:
        if _decorator_skips(dec):
            return True
    for sub in ast.walk(node):
        if isinstance(sub, ast.Call) and _call_skips(sub):
            return True
    return False


_UNITTEST_SKIPS = frozenset({"skip", "skipIf", "skipUnless"})


def _decorator_skips(dec: ast.expr) -> bool:
    """``@pytest.mark.skip|skipif|xfail`` or ``@unittest.skip|skipIf|skipUnless``, bare or called."""
    target = dec.func if isinstance(dec, ast.Call) else dec
    if isinstance(target, ast.Name):
        return target.id in _UNITTEST_SKIPS   # from unittest import skip
    if not isinstance(target, ast.Attribute):
        return False
    if target.attr in {"skip", "skipif", "xfail"} and _is_pytest_mark(target.value):
        return True
    return (target.attr in _UNITTEST_SKIPS and isinstance(target.value, ast.Name)
            and target.value.id == "unittest")


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
        elif isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute):
            owner = sub.func.value
            if not isinstance(owner, ast.Name):
                continue
            # ``with pytest.raises(...)`` and ``pytest.raises(E, f, *a)`` are one Call node each
            if (owner.id == "pytest" and sub.func.attr == "raises") or (
                owner.id == "self" and sub.func.attr.startswith("assert")
            ):
                count += 1
    return count
