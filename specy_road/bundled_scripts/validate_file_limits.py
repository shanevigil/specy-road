#!/usr/bin/env python3
"""Enforce constraints/file-limits.yaml (line counts per glob, optional per-function for Python)."""

from __future__ import annotations

import argparse
import ast
import fnmatch
import sys
from pathlib import Path

import yaml

from specy_road.runtime_paths import default_user_repo_root

# Set at runtime in main() (default user project root).
ROOT = Path.cwd()

SKIP_DIR_NAMES = frozenset(
    {
        ".git",
        ".venv",
        ".conda",
        "venv",
        "node_modules",
        "__pycache__",
        ".pytest_cache",
        ".egg-info",
    }
)


def should_skip(path: Path) -> bool:
    try:
        path.relative_to(ROOT)
    except ValueError:
        return True
    return any(part in SKIP_DIR_NAMES for part in path.parts)


def excluded(rel_posix: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatch(rel_posix, p) for p in patterns)


def iter_glob_files(pattern: str) -> list[Path]:
    """Glob relative to repo root; exclude skip dirs."""
    matches: list[Path] = []
    for p in ROOT.glob(pattern):
        if p.is_file() and not should_skip(p):
            matches.append(p)
    return sorted(matches)


def line_count(path: Path) -> int:
    text = path.read_text(encoding="utf-8", errors="replace")
    if not text:
        return 0
    return text.count("\n") + (0 if text.endswith("\n") else 1)


def python_function_violations(
    path: Path, max_lines: int
) -> list[tuple[str, int, int]]:
    """Return (qualified_name, line_count, max_allowed) for functions over limit."""
    src = path.read_text(encoding="utf-8", errors="replace")
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return []

    bad: list[tuple[str, int, int]] = []

    class Visitor(ast.NodeVisitor):
        def __init__(self) -> None:
            self.stack: list[str] = []

        def _func(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
            self.stack.append(node.name)
            end = getattr(node, "end_lineno", None) or node.lineno
            nlines = end - node.lineno + 1
            if nlines > max_lines:
                bad.append((".".join(self.stack), nlines, max_lines))
            self.generic_visit(node)
            self.stack.pop()

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            self._func(node)

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
            self._func(node)

        def visit_ClassDef(self, node: ast.ClassDef) -> None:
            self.stack.append(node.name)
            self.generic_visit(node)
            self.stack.pop()

    Visitor().visit(tree)
    return bad


def _scan_repo(cfg: dict) -> bool:
    """Return True if any limit violation."""
    max_file = int(cfg.get("max_lines_per_file", 999999))
    max_func = int(cfg.get("max_lines_per_function", 999999))
    globs = cfg.get("applies_to_globs") or []
    excludes = cfg.get("exclude_globs") or []
    failed = False
    for pattern in globs:
        for path in iter_glob_files(pattern):
            rel = path.relative_to(ROOT).as_posix()
            if excluded(rel, excludes):
                continue
            n = line_count(path)
            if n > max_file:
                print(
                    f"file-limits: {rel}: {n} lines (max {max_file})",
                    file=sys.stderr,
                )
                failed = True
            if path.suffix == ".py":
                for name, lines, limit in python_function_violations(path, max_func):
                    print(
                        f"file-limits: {rel} function `{name}` "
                        f"{lines} lines (max {limit} per function)",
                        file=sys.stderr,
                    )
                    failed = True
    return failed


def main() -> None:
    global ROOT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        metavar="DIR",
        help="Repository root (default: git root or cwd).",
    )
    args = parser.parse_args()
    ROOT = (args.repo_root or default_user_repo_root()).resolve()
    config_path = ROOT / "constraints" / "file-limits.yaml"
    if not config_path.is_file():
        print(f"missing {config_path}", file=sys.stderr)
        raise SystemExit(1)
    with config_path.open(encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    if _scan_repo(cfg):
        raise SystemExit(1)
    print("OK: file limits satisfied.")


if __name__ == "__main__":
    main()
