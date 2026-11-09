"""scripts/line_width_baseline.py: per-file counts of lines over 100 characters, a report only."""

from __future__ import annotations

import importlib.util
import json
import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "line_width_baseline", ROOT / "scripts" / "line_width_baseline.py"
)
width = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(width)

LONG = "x = '" + "a" * 120 + "'\n"


@pytest.mark.skipif(shutil.which("ruff") is None, reason="ruff is not installed")
def test_counts_lines_over_100_per_file_under_the_areas(tmp_path: Path) -> None:
    files = {
        "specy_road/wide.py": LONG * 2 + "y = 1\n",
        "specy_road/waived.py": LONG.rstrip("\n") + "  # noqa: E501\n",
        "tests/narrow.py": "z = 2\n",
        "elsewhere/wide.py": LONG,
    }
    for rel, text in files.items():
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text(text, encoding="utf-8")

    assert width.counts(tmp_path) == {"specy_road/wide.py": 2}


@pytest.mark.parametrize(("files", "expected"), [
    ({"a.py": 3, "c.py": 1}, {"b.py": 3, "c.py": 1}),   # a move
    ({"a.py": 3, "b.py": 2}, {"b.py": 5}),               # a fold onto a file with its own count
    ({"c.py": 1}, {"c.py": 1}),                          # OLD had no long line
])
def test_transfer_moves_old_count_onto_new(tmp_path: Path, monkeypatch, files, expected) -> None:
    baseline = tmp_path / "line_width_baseline.json"
    baseline.write_text(json.dumps({"commit": "abc", "files": files}), encoding="utf-8")
    monkeypatch.setattr(width, "BASELINE", baseline)

    assert width.main(["--transfer", "a.py", "b.py"]) == 0

    assert json.loads(baseline.read_text(encoding="utf-8")) == {"commit": "abc", "files": expected}


def test_report_names_rises_and_new_files_and_the_total() -> None:
    baseline = {"rose.py": 2, "fell.py": 5, "same.py": 1}
    current = {"rose.py": 4, "fell.py": 1, "same.py": 1, "new.py": 3}

    assert width.report(baseline, current) == [
        "  rose.py: 2 -> 4 (+2)",
        "  new.py: 3 (not in the baseline)",
        "  total: 8 -> 9 (+1)",
    ]
