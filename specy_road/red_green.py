"""Red-green evidence: ``specy-road review red-green <NODE_ID>`` (``policy.red_green``).

A passing test proves little unless it would have failed without the change.
The tests under check are the Python test functions (``test_*`` in ``test_*.py``
or ``*_test.py``) whose source differs between the merge base and the commit
under review, or that exist only at that commit. Each runs with pytest by node
id, once in a detached temporary worktree of the merge base with the head's
versions of the changed test files overlaid, and once in a detached temporary
worktree of the commit under review. The outcomes go to
``work/reviews/<NODE_ID>/RED-GREEN.md``::

    ---
    commit: <full sha of the commit under review>
    base: <full sha of the merge base>
    tests:
      - {test: tests/test_x.py::test_new, base: fail, head: pass}
    ---

Each outcome is ``pass``, ``fail`` (a failure in the call phase in pytest's JUnit
XML) or ``error`` (a collection or setup error, or nothing ran). A test the node
declares in ``planned_test_changes`` as ``preserve: <path>::<name>`` must pass on
both; every other test must fail at base and pass at head. With
``policy.red_green`` on, :mod:`specy_road.integrity_gate` turns each break into a
gate problem.
"""

from __future__ import annotations

import argparse
import ast
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from specy_road.git_subprocess import git_code
from specy_road.integrity import _block_statements, _changed_files, _file_at, _git_bytes, _is_python_test_module
from specy_road.review_files import _read, render_front_matter, reviews_dir
from specy_road.review_policy_ref import policy_source
from specy_road.review_target import ReviewTargetError, resolve_target, same_commit
from specy_road.runtime_paths import resolve_repo_root

RED_GREEN_NAME = "RED-GREEN.md"
PRESERVE = "preserve: "
_OUTCOMES = frozenset({"pass", "fail", "error"})


def tests_under_check(repo_root: Path, base: str, head: str) -> list[str]:
    """Git-root-relative pytest node ids of the test functions ``base..head`` adds or changes."""
    root = repo_root.resolve()
    out: list[str] = []
    for path in sorted({p for p, _old, _new in _changed_files(root, base, head, "--no-renames")}):
        if not _is_python_test_module(path):
            continue
        before = _test_sources(_file_at(root, base, path))
        after = _test_sources(_file_at(root, head, path))
        out.extend(f"{path}::{qual}" for qual, src in sorted(after.items()) if before.get(qual) != src)
    return out


def _test_sources(source: str | None) -> dict[str, str]:
    """``qualname -> source`` (decorators included) for tests at module or class scope.

    Scoped as :func:`specy_road.integrity._test_functions` scopes them; a name
    defined more than once joins its definitions, so changing any one counts.
    """
    if not source:
        return {}
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return {}
    lines = source.splitlines()
    out: dict[str, str] = {}

    def scan(stmts: list[ast.stmt], prefix: str) -> None:
        for stmt in stmts:
            if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if stmt.name.startswith("test_"):
                    start = min([stmt.lineno, *(d.lineno for d in stmt.decorator_list)])
                    text = "\n".join(lines[start - 1:stmt.end_lineno])
                    key = prefix + stmt.name
                    out[key] = f"{out[key]}\n{text}" if key in out else text
            elif isinstance(stmt, ast.ClassDef):
                scan(stmt.body, f"{prefix}{stmt.name}::")
            else:
                scan(_block_statements(stmt), prefix)

    scan(tree.body, "")
    return out


def junit_outcome(xml_path: Path) -> str:
    """``error`` on any error element, else ``fail`` on any failure, else ``pass`` if a case ran."""
    try:
        cases = list(ET.parse(xml_path).getroot().iter("testcase"))
    except (OSError, ET.ParseError):
        return "error"
    tags = [{child.tag for child in case} for case in cases]
    if any("error" in t for t in tags):
        return "error"
    if any("failure" in t for t in tags):
        return "fail"
    return "pass" if any("skipped" not in t for t in tags) else "error"


def _outcomes_at(root: Path, sha: str, tests: list[str], overlay: dict[str, bytes]) -> dict[str, str] | str:
    """Each test's outcome in a detached worktree of ``sha`` with ``overlay`` written over it, or an error.

    pytest runs once per node id from the worktree's git root, with the
    interpreter running specy-road, so one test's collection error cannot hide
    another. Only this worktree is removed afterwards.
    """
    holder = Path(tempfile.mkdtemp(prefix="specy-road-red-green-"))
    tree = holder / "tree"
    code, out = git_code(["worktree", "add", "--detach", str(tree), sha], root)
    if code != 0:
        shutil.rmtree(holder, ignore_errors=True)
        return f"could not create a worktree of {sha}: {out}"
    try:
        for rel, data in overlay.items():
            (tree / rel).parent.mkdir(parents=True, exist_ok=True)
            (tree / rel).write_bytes(data)
        outcomes: dict[str, str] = {}
        for i, test in enumerate(tests):
            xml = holder / f"junit-{i}.xml"
            subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", f"--junitxml={xml}",
                            test], cwd=tree, capture_output=True, check=False)
            outcomes[test] = junit_outcome(xml)
        return outcomes
    finally:
        git_code(["worktree", "remove", "--force", str(tree)], root)
        shutil.rmtree(holder, ignore_errors=True)


def run_red_green(repo_root: Path, base: str, head: str, tests: list[str]) -> list[dict[str, str]] | str:
    """One ``{test, base, head}`` per test, or an error; nothing runs when ``tests`` is empty."""
    if not tests:
        return []
    root = repo_root.resolve()
    files = sorted({t.split("::", 1)[0] for t in tests})
    overlay = {p: _git_bytes(root, ["cat-file", "blob", f"{head}:{p}"]) for p in files}
    at_base = _outcomes_at(root, base, tests, overlay)
    if isinstance(at_base, str):
        return at_base
    at_head = _outcomes_at(root, head, tests, {})
    if isinstance(at_head, str):
        return at_head
    return [{"test": t, "base": at_base[t], "head": at_head[t]} for t in tests]


def outcome_problems(rows: list[dict[str, Any]], tests: list[str], declared: set[str]) -> list[str]:
    """One ``not-green: <id>`` or ``not-red: <id>`` per test in ``tests`` whose outcomes break the rule.

    A test with no row has no evidence, so it breaks the rule too.
    """
    preserve = {d[len(PRESERVE):] for d in declared if d.startswith(PRESERVE)}
    by_test = {r["test"]: r for r in rows if isinstance(r, dict) and isinstance(r.get("test"), str)}
    out: list[str] = []
    for test in tests:
        row = by_test.get(test) or {}
        base, head = row.get("base"), row.get("head")
        if head != "pass" or (test in preserve and base != "pass"):
            out.append(f"not-green: {test}")
        elif test not in preserve and base != "fail":
            out.append(f"not-red: {test}")
    return out


def red_green_problems(repo_root: Path, node_id: str, base: str, commit: str, declared: set[str]) -> list[str]:
    """Gate problems for ``commit`` from ``RED-GREEN.md``: missing, stale, or one per test that breaks the rule.

    The tests under check are computed again from git, so a record that leaves one out does not clear it.
    """
    data, _body, errs = _read(reviews_dir(repo_root, node_id) / RED_GREEN_NAME)
    if errs:
        return ["red-green: missing"]
    recorded = str(data.get("commit") or "")
    if not same_commit(repo_root, recorded, commit):
        return [f"red-green: stale ({recorded[:12]})"]
    rows = data.get("tests") if isinstance(data.get("tests"), list) else []
    rows = [r for r in rows if isinstance(r, dict) and {r.get("base"), r.get("head")} <= _OUTCOMES]
    return outcome_problems(rows, tests_under_check(repo_root, base, commit), declared)


def cmd_red_green(ns: argparse.Namespace) -> int:
    """Run the node's tests under check at base and head; write ``RED-GREEN.md``; exit 1 on any problem."""
    from specy_road.integrity_gate import planned_test_changes   # integrity_gate imports this module

    root = resolve_repo_root(ns)
    try:
        t = resolve_target(root, ns.node_id, ns.ref)
    except ReviewTargetError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    if not t.base or not t.commit:
        print("error: cannot resolve merge base or commit under review", file=sys.stderr)
        return 1
    tests = tests_under_check(root, t.base, t.commit)
    rows = run_red_green(root, t.base, t.commit, tests)
    if isinstance(rows, str):
        print(f"error: {rows}", file=sys.stderr)
        return 1
    dest = reviews_dir(root, ns.node_id) / RED_GREEN_NAME
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(render_front_matter({"commit": t.commit, "base": t.base, "tests": rows}), encoding="utf-8")
    for r in rows:
        print(f"{r['test']}: base {r['base']}, head {r['head']}")
    print(f"Wrote {dest}")
    ref, _err = policy_source(root)
    problems = outcome_problems(rows, tests, planned_test_changes(root, ref, ns.node_id) if ref else set())
    for p in problems:
        print(p)
    return 1 if problems else 0
