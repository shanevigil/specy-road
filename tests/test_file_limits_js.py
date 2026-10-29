"""TS/JS function spans for the file-limits function cap (one fixture per syntax form)."""

from __future__ import annotations

import io
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from specy_road.file_limits_engine import run_file_limits_scan
from specy_road.file_limits_js import js_function_metrics
from tests.helpers import BUNDLED_SCRIPTS, REPO, script_subprocess_env

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "file_limits_js"


@pytest.mark.parametrize(
    ("fixture", "expected"),
    [
        # Overload signatures have no body; generics and object return types do not end the header.
        (
            "declaration.ts",
            [("overloaded", 4, 3), ("load", 8, 6), ("ids", 15, 4), ("shape", 20, 3)],
        ),
        # Typed bindings, `<T,>` generics and `(…)` JSX bodies; expression bodies and calls are not measured.
        ("arrow.tsx", [("Badge", 3, 5), ("usePick", 9, 3), ("parse", 13, 3)]),
        # Modifiers, accessors, private names, arrow fields; abstract signatures have no body.
        (
            "class_methods.ts",
            [
                ("Store.constructor", 5, 3),
                ("Store.add", 11, 3),
                ("Store.size", 15, 3),
                ("Store.#reset", 19, 6),
                ("Store.#reset.clear", 20, 3),
                ("Store.onChange", 26, 3),
            ],
        ),
        # Braces inside strings, nested template literals and comments are ignored.
        ("literals.mjs", [("render", 5, 5), ("after", 10, 3)]),
        (
            "legacy.js",
            [("Legacy", 1, 3), ("greet", 5, 3), ("double", 9, 3), ("Modern.greet", 14, 3)],
        ),
        ("widget.jsx", [("Widget", 1, 10), ("Widget.onClick", 2, 3)]),
    ],
)
def test_js_function_metrics_per_syntax_form(fixture: str, expected: list) -> None:
    assert js_function_metrics(FIXTURES / fixture) == expected


def _cfg(glob: str, **extra: object) -> dict:
    return {"max_lines_per_file": 9999, "max_lines_per_function": 4, "applies_to_globs": [glob], **extra}


@pytest.mark.parametrize("suffix", [".ts", ".tsx", ".js", ".jsx", ".mjs"])
def test_scan_reports_over_cap_js_function_with_line(tmp_path: Path, suffix: str) -> None:
    shutil.copy(FIXTURES / "widget.jsx", tmp_path / f"widget{suffix}")
    err = io.StringIO()
    assert run_file_limits_scan(tmp_path, _cfg(f"*{suffix}"), err=err) is True
    assert err.getvalue() == (
        f"file-limits: widget{suffix}:1 function `Widget` 10 lines (max 4 per function)\n"
    )


def test_js_function_hard_alert(tmp_path: Path) -> None:
    shutil.copy(FIXTURES / "declaration.ts", tmp_path / "declaration.ts")
    cfg = _cfg("*.ts", max_lines_per_function=99, hard_alerts={"max_lines_per_function": 5})
    err = io.StringIO()
    assert run_file_limits_scan(tmp_path, cfg, err=err) is False
    assert err.getvalue() == (
        "file-limits: WARNING: declaration.ts:8 function `load` 6 lines "
        "(hard_alerts.max_lines_per_function=5)\n"
    )
    assert run_file_limits_scan(tmp_path, cfg, err=io.StringIO(), strict_hard_alerts=True) is True


def test_validator_does_not_print_ok_with_over_cap_ts_function(tmp_path: Path) -> None:
    (tmp_path / "constraints").mkdir()
    (tmp_path / "constraints" / "file-limits.yaml").write_text(
        'max_lines_per_function: 4\napplies_to_globs:\n  - "src/**/*.tsx"\n', encoding="utf-8"
    )
    (tmp_path / "src").mkdir()
    shutil.copy(FIXTURES / "arrow.tsx", tmp_path / "src" / "arrow.tsx")
    r = subprocess.run(
        [sys.executable, str(BUNDLED_SCRIPTS / "validate_file_limits.py"), "--repo-root", str(tmp_path)],
        cwd=REPO,
        env=script_subprocess_env(),
        capture_output=True,
        text=True,
        check=False,
    )
    assert r.returncode == 1
    assert "OK" not in r.stdout
    assert "file-limits: src/arrow.tsx:3 function `Badge` 5 lines (max 4 per function)" in r.stderr
