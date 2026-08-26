"""Language-neutral file line limits + optional Python per-function checks."""

from __future__ import annotations

import ast
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO


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

# Session artifacts the toolkit itself generates under ``work/``. They are
# machine-written and ephemeral (see ``work/README.md``), so a line cap on them
# reports a violation no one can act on — notably the ``pr-body-`` snapshot,
# which inlines the brief plus the implementation summary and therefore always
# dwarfs a source-file limit. Writers: ``do_next_task``, ``finish_pr_body``,
# ``on_complete_session``.
SESSION_ARTIFACT_GLOBS = (
    "work/brief-*.md",
    "work/prompt-*.md",
    "work/implementation-summary-*.md",
    "work/pr-body-*.md",
    "work/.on-complete-*.yaml",
    "work/.milestone-session.yaml",
    # Archived roadmap material. Getting finished work to stop counting against
    # line limits is a large part of why archiving exists — a scaffold's
    # `**/*.md` glob would otherwise keep flagging planning sheets for
    # milestones that shipped years ago.
    "roadmap/archive/**/*.json",
    "roadmap/archive/**/*.md",
)


def _int_limit(val: object, default: int) -> int:
    if val is None:
        return default
    try:
        n = int(val)
    except (TypeError, ValueError):
        return default
    return n if n > 0 else default


def _optional_positive_int(val: object) -> int | None:
    if val is None:
        return None
    try:
        n = int(val)
    except (TypeError, ValueError):
        return None
    return n if n > 0 else None


def should_skip(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return True
    return any(part in SKIP_DIR_NAMES for part in path.parts)


def merge_exclude_patterns(cfg: dict) -> list[str]:
    raw = list(cfg.get("exclude_globs") or []) + list(cfg.get("exclude_path_globs") or [])
    out: list[str] = []
    for p in raw:
        if p is None:
            continue
        s = str(p).strip()
        if s:
            out.append(s)
    return out


def _glob_pattern_variants(pattern: str) -> list[str]:
    """``Path.glob('dir/**')`` can omit nested files on some layouts; also try ``dir/**/*``."""
    p = pattern.strip()
    if not p:
        return []
    if p.endswith("/**") and not p.endswith("/**/*"):
        return [p, f"{p}/*"]
    return [p]


def iter_glob_files(root: Path, pattern: str) -> list[Path]:
    root = root.resolve()
    seen: set[str] = set()
    matches: list[Path] = []
    for variant in _glob_pattern_variants(pattern):
        for p in root.glob(variant):
            if not p.is_file() or should_skip(p, root):
                continue
            key = p.resolve().as_posix()
            if key in seen:
                continue
            seen.add(key)
            matches.append(p)
    return sorted(matches, key=lambda p: p.as_posix())


def collect_excluded_paths(root: Path, cfg: dict) -> frozenset[str]:
    """Paths excluded by ``exclude_globs`` / ``exclude_path_globs`` plus toolkit session artifacts."""
    matched: set[str] = set()
    for pat in [*merge_exclude_patterns(cfg), *SESSION_ARTIFACT_GLOBS]:
        for p in iter_glob_files(root, pat):
            matched.add(p.relative_to(root).as_posix())
    return frozenset(matched)


def build_overlay_match_sets(root: Path, cfg: dict) -> list[tuple[dict, frozenset[str]]]:
    """For each overlay, precompute repo-relative paths matched by ``file_globs``."""
    result: list[tuple[dict, frozenset[str]]] = []
    for ov in cfg.get("override_limits") or []:
        if not isinstance(ov, dict):
            continue
        paths: set[str] = set()
        for g in ov.get("file_globs") or []:
            gs = str(g).strip()
            if not gs:
                continue
            for p in iter_glob_files(root, gs):
                paths.add(p.relative_to(root).as_posix())
        result.append((ov, frozenset(paths)))
    return result


def line_count(path: Path) -> int:
    text = path.read_text(encoding="utf-8", errors="replace")
    if not text:
        return 0
    return text.count("\n") + (0 if text.endswith("\n") else 1)


def python_function_metrics(path: Path) -> list[tuple[str, int]]:
    """Qualified name and line span for each function/async def (Python only)."""
    src = path.read_text(encoding="utf-8", errors="replace")
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return []

    found: list[tuple[str, int]] = []

    class Visitor(ast.NodeVisitor):
        def __init__(self) -> None:
            self.stack: list[str] = []

        def _func(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
            self.stack.append(node.name)
            end = getattr(node, "end_lineno", None) or node.lineno
            nlines = end - node.lineno + 1
            found.append((".".join(self.stack), nlines))
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
    return found


@dataclass(frozen=True)
class ResolvedLimits:
    max_lines_per_file: int
    max_lines_per_function: int
    overlay_name: str | None


def resolve_limits(
    rel_posix: str,
    cfg: dict,
    overlay_sets: list[tuple[dict, frozenset[str]]],
) -> ResolvedLimits:
    mf = _int_limit(cfg.get("max_lines_per_file"), 999_999)
    mfn = _int_limit(cfg.get("max_lines_per_function"), 999_999)
    oname: str | None = None
    for ov, matched in overlay_sets:
        if rel_posix not in matched:
            continue
        if "max_lines_per_file" in ov:
            mf = _int_limit(ov.get("max_lines_per_file"), mf)
        if "max_lines_per_function" in ov:
            mfn = _int_limit(ov.get("max_lines_per_function"), mfn)
        n = ov.get("name")
        if isinstance(n, str) and n.strip():
            oname = n.strip()
    return ResolvedLimits(mf, mfn, oname)


def git_ignored_paths(root: Path, rel_paths: list[str]) -> frozenset[str]:
    """Subset of ``rel_paths`` that git ignores.

    ``git check-ignore`` consults the index by default, so a tracked file is
    never reported even when a rule would otherwise match it. Returns an empty
    set when ``root`` is not a git worktree or git is unavailable, so the scan
    degrades to plain filesystem behavior.
    """
    if not rel_paths:
        return frozenset()
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), "check-ignore", "--stdin", "-z"],
            input="\0".join(rel_paths),
            capture_output=True,
            text=True,
            check=False,
        )
    except (OSError, ValueError):
        return frozenset()
    # 0 = some paths ignored, 1 = none ignored; anything else (128 = not a
    # repo) means we cannot trust the answer.
    if proc.returncode not in (0, 1):
        return frozenset()
    return frozenset(p for p in (proc.stdout or "").split("\0") if p)


def collect_tracked_files(
    root: Path,
    cfg: dict,
    *,
    respect_gitignore: bool = True,
) -> list[Path]:
    globs = cfg.get("applies_to_globs") or []
    excluded_paths = collect_excluded_paths(root, cfg)
    seen: set[str] = set()
    paths: list[Path] = []
    for pattern in globs:
        if not pattern:
            continue
        for path in iter_glob_files(root, str(pattern)):
            rel = path.relative_to(root).as_posix()
            if rel in seen:
                continue
            if rel in excluded_paths:
                continue
            seen.add(rel)
            paths.append(path)
    if respect_gitignore:
        ignored = git_ignored_paths(root, sorted(seen))
        if ignored:
            paths = [p for p in paths if p.relative_to(root).as_posix() not in ignored]
    paths.sort(key=lambda p: p.as_posix())
    return paths


def _overlay_suffix(limits: ResolvedLimits) -> str:
    if limits.overlay_name:
        return f" (overlay `{limits.overlay_name}`)"
    return ""


def run_file_limits_scan(
    root: Path,
    cfg: dict,
    *,
    strict_hard_alerts: bool = False,
    respect_gitignore: bool = True,
    err: TextIO | None = None,
) -> bool:
    """
    Print violations to ``err`` (default stderr).

    Returns True if the run should fail (violations, or strict hard alerts).
    """
    err = err or sys.stderr
    hard = cfg.get("hard_alerts") if isinstance(cfg.get("hard_alerts"), dict) else {}
    ha_file = hard.get("max_lines_per_file")
    ha_func = hard.get("max_lines_per_function")
    ha_rationale = hard.get("rationale")
    ha_note = ""
    if isinstance(ha_rationale, str) and ha_rationale.strip():
        ha_note = f" — {ha_rationale.strip()}"

    ha_file_n = _optional_positive_int(ha_file)
    ha_func_n = _optional_positive_int(ha_func)

    failed = False
    hard_failed = False
    overlay_sets = build_overlay_match_sets(root, cfg)
    paths = collect_tracked_files(root, cfg, respect_gitignore=respect_gitignore)

    for path in paths:
        rel = path.relative_to(root).as_posix()
        limits = resolve_limits(rel, cfg, overlay_sets)
        n = line_count(path)

        if ha_file_n is not None and n > ha_file_n:
            print(
                f"file-limits: WARNING: {rel}: {n} lines "
                f"(hard_alerts.max_lines_per_file={ha_file_n}){ha_note}",
                file=err,
            )
            if strict_hard_alerts:
                hard_failed = True

        if n > limits.max_lines_per_file:
            print(
                f"file-limits: {rel}: {n} lines "
                f"(max {limits.max_lines_per_file} per file){_overlay_suffix(limits)}",
                file=err,
            )
            failed = True

        if path.suffix == ".py":
            metrics = python_function_metrics(path)
            for name, flines in metrics:
                if ha_func_n is not None and flines > ha_func_n:
                    print(
                        f"file-limits: WARNING: {rel} function `{name}` "
                        f"{flines} lines (hard_alerts.max_lines_per_function={ha_func_n}; "
                        f"Python-only advisory){ha_note}",
                        file=err,
                    )
                    if strict_hard_alerts:
                        hard_failed = True

                if flines > limits.max_lines_per_function:
                    print(
                        f"file-limits: {rel} function `{name}` "
                        f"{flines} lines (max {limits.max_lines_per_function} per function)"
                        f"{_overlay_suffix(limits)}",
                        file=err,
                    )
                    failed = True

    return failed or hard_failed
