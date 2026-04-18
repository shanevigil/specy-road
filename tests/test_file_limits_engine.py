"""Unit tests for specy_road.file_limits_engine."""

from __future__ import annotations

import io
from pathlib import Path

from specy_road.file_limits_engine import (
    build_overlay_match_sets,
    collect_excluded_paths,
    collect_tracked_files,
    merge_exclude_patterns,
    resolve_limits,
    run_file_limits_scan,
)


def _write_layout(root: Path, files: dict[str, str]) -> None:
    for rel, body in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")


def test_merge_exclude_patterns_merges_keys() -> None:
    cfg = {
        "exclude_globs": ["**/a/**"],
        "exclude_path_globs": ["**/b/**"],
    }
    assert merge_exclude_patterns(cfg) == ["**/a/**", "**/b/**"]


def test_collect_tracked_files_dedupes_overlapping_globs(tmp_path: Path) -> None:
    _write_layout(
        tmp_path,
        {
            "src/x.py": "print(1)\n",
        },
    )
    cfg = {
        "applies_to_globs": ["src/**/*.py", "src/x.py"],
        "exclude_globs": [],
    }
    paths = collect_tracked_files(tmp_path, cfg)
    assert len(paths) == 1


def test_collect_respects_exclude_path_globs(tmp_path: Path) -> None:
    _write_layout(
        tmp_path,
        {
            "keep/a.py": "x\n",
            "excluded_dir/b.py": "y\n",
        },
    )
    cfg = {
        "applies_to_globs": ["**/*.py"],
        "exclude_path_globs": ["excluded_dir/**"],
    }
    assert collect_excluded_paths(tmp_path, cfg) == frozenset({"excluded_dir/b.py"})
    paths = collect_tracked_files(tmp_path, cfg)
    assert {p.relative_to(tmp_path).as_posix() for p in paths} == {"keep/a.py"}


def test_resolve_limits_overlay_order_last_wins(tmp_path: Path) -> None:
    _write_layout(tmp_path, {"x.py": "x\n"})
    cfg = {
        "max_lines_per_file": 100,
        "override_limits": [
            {"name": "first", "file_globs": ["**/*.py"], "max_lines_per_file": 200},
            {"name": "second", "file_globs": ["**/*.py"], "max_lines_per_file": 300},
        ],
    }
    sets = build_overlay_match_sets(tmp_path, cfg)
    lim = resolve_limits("x.py", cfg, sets)
    assert lim.max_lines_per_file == 300
    assert lim.overlay_name == "second"


def test_run_scan_file_violation(tmp_path: Path) -> None:
    _write_layout(tmp_path, {"big.txt": "a\nb\nc\n"})
    cfg = {"max_lines_per_file": 2, "applies_to_globs": ["big.txt"]}
    err = io.StringIO()
    assert run_file_limits_scan(tmp_path, cfg, err=err) is True
    assert "max 2" in err.getvalue()


def test_hard_alerts_file_warning_non_strict(tmp_path: Path) -> None:
    body = "\n".join([f"line{i}" for i in range(50)]) + "\n"
    _write_layout(tmp_path, {"wide.txt": body})
    cfg = {
        "max_lines_per_file": 9999,
        "applies_to_globs": ["wide.txt"],
        "hard_alerts": {
            "max_lines_per_file": 10,
            "rationale": "keep modules small",
        },
    }
    err = io.StringIO()
    assert run_file_limits_scan(tmp_path, cfg, err=err) is False
    out = err.getvalue()
    assert "WARNING" in out
    assert "hard_alerts.max_lines_per_file=10" in out
    assert "keep modules small" in out


def test_strict_hard_alerts_fails_on_file_warning(tmp_path: Path) -> None:
    body = "\n".join([f"line{i}" for i in range(50)]) + "\n"
    _write_layout(tmp_path, {"wide.txt": body})
    cfg = {
        "max_lines_per_file": 9999,
        "applies_to_globs": ["wide.txt"],
        "hard_alerts": {"max_lines_per_file": 10},
    }
    err = io.StringIO()
    assert (
        run_file_limits_scan(
            tmp_path, cfg, err=err, strict_hard_alerts=True
        )
        is True
    )


def test_python_function_limit_and_hard_alert(tmp_path: Path) -> None:
    src = "def tiny():\n    return 1\n\n" + "def big():\n" + "    pass\n" * 30
    _write_layout(tmp_path, {"mod.py": src})
    cfg = {
        "max_lines_per_file": 9999,
        "max_lines_per_function": 5,
        "applies_to_globs": ["mod.py"],
        "hard_alerts": {"max_lines_per_function": 3},
    }
    err = io.StringIO()
    assert run_file_limits_scan(tmp_path, cfg, err=err) is True
    msg = err.getvalue()
    assert "max 5 per function" in msg
    assert "WARNING" in msg
    assert "hard_alerts.max_lines_per_function=3" in msg


def test_non_python_skips_function_limits(tmp_path: Path) -> None:
    body = "x\n" * 20
    _write_layout(tmp_path, {"note.md": body})
    cfg = {
        "max_lines_per_file": 9999,
        "max_lines_per_function": 2,
        "applies_to_globs": ["note.md"],
    }
    err = io.StringIO()
    assert run_file_limits_scan(tmp_path, cfg, err=err) is False
    assert "function" not in err.getvalue()
