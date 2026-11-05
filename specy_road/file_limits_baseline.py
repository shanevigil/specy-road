"""Baseline today's file-limits failures into ``override_limits`` entries."""

from __future__ import annotations

import copy
import math
import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import TextIO

import yaml

from specy_road.file_limits_baseline_yaml import append_baseline_yaml_text, yaml_quoted_scalar
from specy_road.file_limits_engine import (
    build_overlay_match_sets,
    collect_tracked_files,
    function_metrics,
    line_count,
    optional_positive_int,
    resolve_limits,
    run_file_limits_scan,
)
from specy_road.runtime_paths import project_root, source_scan_root

_FILE_STEP = 50
_FUNC_STEP = 20
_BASELINE_NAME = re.compile(r"^baseline-(\d{4}-\d{2}-\d{2})-(\d+)$")


def literal_path_glob(rel_posix: str) -> str:
    """Glob under the scan root that matches only this repo-relative path."""
    out: list[str] = []
    for ch in rel_posix:
        if ch == "[":
            out.append("[[]")
        elif ch == "]":
            out.append("[]]")
        elif ch in "*?":
            out.append(f"[{ch}]")
        else:
            out.append(ch)
    return "".join(out)


def _loads_file_limits_mapping(text: str) -> dict | None:
    try:
        cfg = yaml.safe_load(text)
    except yaml.YAMLError:
        return None
    return cfg if isinstance(cfg, dict) else None


def round_up_to_step(value: int, step: int) -> int:
    if value <= 0:
        return 0
    return math.ceil(value / step) * step


@dataclass(frozen=True)
class FailingFileMetrics:
    rel: str
    file_lines: int
    worst_function_lines: int


def collect_failing_file_metrics(
    root: Path,
    cfg: dict,
    *,
    respect_gitignore: bool = True,
) -> list[FailingFileMetrics]:
    """One row per path that fails the file or function cap (not hard-alert warnings)."""
    overlay_sets = build_overlay_match_sets(root, cfg)
    out: list[FailingFileMetrics] = []
    for path in collect_tracked_files(root, cfg, respect_gitignore=respect_gitignore):
        rel = path.relative_to(root).as_posix()
        limits = resolve_limits(rel, cfg, overlay_sets)
        n = line_count(path)
        funcs = function_metrics(path)
        worst_fn = max((flines for _, _, flines in funcs), default=0)
        file_fail = n > limits.max_lines_per_file
        func_fail = any(flines > limits.max_lines_per_function for _, _, flines in funcs)
        if not file_fail and not func_fail:
            continue
        out.append(FailingFileMetrics(rel, n, worst_fn))
    return out


def file_limits_failure_count(
    root: Path,
    cfg: dict,
    *,
    strict_hard_alerts: bool = False,
    respect_gitignore: bool = True,
) -> int:
    """Count of violation lines ``file-limits`` would print (not hard-alert warnings unless strict)."""
    hard = cfg.get("hard_alerts") if isinstance(cfg.get("hard_alerts"), dict) else {}
    ha_file_n = optional_positive_int(hard.get("max_lines_per_file"))
    ha_func_n = optional_positive_int(hard.get("max_lines_per_function"))

    count = 0
    overlay_sets = build_overlay_match_sets(root, cfg)
    for path in collect_tracked_files(root, cfg, respect_gitignore=respect_gitignore):
        rel = path.relative_to(root).as_posix()
        limits = resolve_limits(rel, cfg, overlay_sets)
        n = line_count(path)
        if n > limits.max_lines_per_file:
            count += 1
        for _, _, flines in function_metrics(path):
            if flines > limits.max_lines_per_function:
                count += 1
        if strict_hard_alerts:
            if ha_file_n is not None and n > ha_file_n:
                count += 1
            for _, _, flines in function_metrics(path):
                if ha_func_n is not None and flines > ha_func_n:
                    count += 1
    return count


def bucket_failing_files(metrics: list[FailingFileMetrics]) -> dict[tuple[int, int], list[str]]:
    buckets: dict[tuple[int, int], list[str]] = defaultdict(list)
    for row in metrics:
        file_cap = round_up_to_step(row.file_lines, _FILE_STEP)
        func_cap = round_up_to_step(row.worst_function_lines, _FUNC_STEP)
        buckets[(file_cap, func_cap)].append(row.rel)
    for paths in buckets.values():
        paths.sort()
    return dict(buckets)


def _next_baseline_index(existing_names: list[str], today: str) -> int:
    highest = 0
    for name in existing_names:
        m = _BASELINE_NAME.match(name)
        if m and m.group(1) == today:
            highest = max(highest, int(m.group(2)))
    return highest + 1


def _existing_baseline_names(cfg: dict) -> list[str]:
    names: list[str] = []
    for ov in cfg.get("override_limits") or []:
        if isinstance(ov, dict):
            n = ov.get("name")
            if isinstance(n, str):
                names.append(n.strip())
    return names


def format_baseline_entries(
    buckets: dict[tuple[int, int], list[str]],
    *,
    today: str,
    start_index: int,
) -> str:
    lines: list[str] = []
    idx = start_index
    for (file_cap, func_cap), paths in sorted(buckets.items()):
        lines.append(f"  - name: baseline-{today}-{idx}")
        lines.append("    file_globs:")
        for rel in paths:
            lines.append(f"      - {yaml_quoted_scalar(literal_path_glob(rel))}")
        lines.append(f"    max_lines_per_file: {file_cap}")
        if func_cap > 0:
            lines.append(f"    max_lines_per_function: {func_cap}")
        idx += 1
    return "\n".join(lines) + ("\n" if lines else "")


def failure_hint(config_rel: str) -> str:
    return (
        f"file-limits: add override_limits entries in {config_rel} with "
        f"specy-road file-limits --write-baseline"
    )


def plan_baseline_append(
    cfg_path: Path,
    cfg: dict,
    root: Path,
    *,
    respect_gitignore: bool = True,
    today: str | None = None,
) -> str:
    metrics = collect_failing_file_metrics(root, cfg, respect_gitignore=respect_gitignore)
    buckets = bucket_failing_files(metrics)
    if not buckets:
        return ""
    day = today or date.today().isoformat()
    start = _next_baseline_index(_existing_baseline_names(cfg), day)
    return format_baseline_entries(buckets, today=day, start_index=start)


def write_baseline(
    repo_root: Path | None,
    *,
    dry_run: bool = False,
    respect_gitignore: bool = True,
    out: TextIO | None = None,
) -> int:
    """Append baseline ``override_limits`` rows; return 0 on success."""
    out = out or sys.stdout
    project = project_root(repo_root)
    cfg_path = project / "constraints" / "file-limits.yaml"
    if not cfg_path.is_file():
        print(f"missing {cfg_path}", file=sys.stderr)
        return 1
    raw = cfg_path.read_text(encoding="utf-8")
    cfg = yaml.safe_load(raw) or {}
    if not isinstance(cfg, dict):
        print(f"invalid {cfg_path}", file=sys.stderr)
        return 1
    root = source_scan_root(project)
    block = plan_baseline_append(cfg_path, cfg, root, respect_gitignore=respect_gitignore)
    if not block:
        print("file-limits baseline: nothing to add (no failing files).", file=out)
        return 0
    if dry_run:
        print(block, file=out, end="")
        return 0
    try:
        new_text = append_baseline_yaml_text(raw, block, cfg=cfg)
    except ValueError:
        print(
            f"file-limits baseline: refusing to write {cfg_path}; "
            "append would alter existing override_limits entries.",
            file=sys.stderr,
        )
        return 1
    if _loads_file_limits_mapping(new_text) is None:
        print(
            f"file-limits baseline: refusing to write {cfg_path}; "
            "appended text would not load as YAML.",
            file=sys.stderr,
        )
        return 1
    cfg_path.write_text(new_text, encoding="utf-8")
    print(f"file-limits baseline: appended to {cfg_path.relative_to(project)}", file=out)
    return 0


def scan_with_optional_hint(
    root: Path,
    cfg: dict,
    config_rel: str,
    *,
    strict_hard_alerts: bool = False,
    respect_gitignore: bool = True,
    err: TextIO | None = None,
) -> bool:
    """Run the scan; print the baseline hint on failure when appropriate."""
    failed = run_file_limits_scan(
        root,
        cfg,
        strict_hard_alerts=strict_hard_alerts,
        respect_gitignore=respect_gitignore,
        err=err,
    )
    if failed:
        print(failure_hint(config_rel), file=err or sys.stderr)
    return failed
