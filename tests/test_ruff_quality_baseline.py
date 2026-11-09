"""scripts/ruff_quality_baseline.py: per-file ruff family counts, a report only."""

from __future__ import annotations

import importlib.util
import json
import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "ruff_quality_baseline", ROOT / "scripts" / "ruff_quality_baseline.py"
)
quality = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(quality)

# Ten `if`s is McCabe 11, over ruff's default of 10. The waived copy still counts
# for C901 (`--ignore-noqa`) and does not count for the other families.
_BRANCHES = "".join("    if x:\n        x = x[1:]\n" for _ in range(10))
QUALITY_PY = (
    "def complex_counted(x):\n"
    f"{_BRANCHES}"
    "    return x\n"
    "\n"
    "def complex_waived(x):  # noqa: C901\n"
    f"{_BRANCHES}"
    "    return x\n"
    "\n"
    "count = 0\n"
    "\n"
    "def bump():\n"
    '    """Documented, so D103 stays quiet."""\n'
    "    global count\n"
    "    count += 1\n"
    "    return count\n"
    "\n"
    "def BadName():\n"
    '    """Documented."""\n'
    "    return 1\n"
    "\n"
    "def public_missing_doc():\n"
    "    return 1\n"
    "\n"
    "def mutable(items=[]):\n"
    '    """Documented."""\n'
    "    return items\n"
    "\n"
    "def mutable_waived(items=[]):  # noqa: B006\n"
    '    """Documented."""\n'
    "    return items\n"
    "\n"
    "class Box:\n"
    "    def method(self):\n"
    "        return 1\n"
    "\n"
    "def branched(flag):\n"
    '    """Documented."""\n'
    "    if flag:\n"
    "        return 1\n"
    "    else:\n"
    "        return 2\n"
    "\n"
    "def assigned(value):\n"
    '    """Documented."""\n'
    "    if value:\n"
    "        result = 1\n"
    "    else:\n"
    "        result = 2\n"
    "    return result\n"
)


def _write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


@pytest.mark.skipif(shutil.which("ruff") is None, reason="ruff is not installed")
def test_counts_findings_per_file_and_family_under_the_areas(tmp_path: Path) -> None:
    _write(tmp_path, "specy_road/quality.py", QUALITY_PY)
    _write(tmp_path, "specy_road/clean.py", 'def ok():\n    """Documented."""\n    return 1\n')
    _write(
        tmp_path, "scripts/also.py",
        'def also(items=[]):\n    """Documented."""\n    return items\n',
    )
    _write(tmp_path, "tests/t.py", "def test_ok():\n    assert True\n")
    _write(tmp_path, "elsewhere/wide.py", "def also(items=[]):\n    return items\n")

    assert quality.counts(tmp_path) == {
        "scripts/also.py": {"B": 1},
        "specy_road/quality.py": {
            "C901": 2,
            "PL": 1,
            "B": 1,
            "SIM": 1,
            "RET": 1,
            "N": 1,
            "D102/D103": 4,
        },
        "tests/t.py": {"D102/D103": 1},
    }


@pytest.mark.parametrize(("files", "expected"), [
    ({"a.py": {"C901": 2, "PL": 1}}, {"b.py": {"C901": 2, "PL": 1}}),
    (
        {"a.py": {"C901": 2, "PL": 1}, "b.py": {"B": 4, "C901": 3}},
        {"b.py": {"C901": 5, "PL": 1, "B": 4}},
    ),
    ({"c.py": {"B": 1}}, {"c.py": {"B": 1}}),
])
def test_transfer_sums_old_families_onto_new(tmp_path: Path, monkeypatch, files, expected) -> None:
    baseline = tmp_path / "ruff_quality_baseline.json"
    baseline.write_text(json.dumps({"commit": "abc", "files": files}), encoding="utf-8")
    monkeypatch.setattr(quality, "BASELINE", baseline)

    assert quality.main(["--transfer", "a.py", "b.py"]) == 0

    written = json.loads(baseline.read_text(encoding="utf-8"))
    assert written["commit"] == "abc"
    assert written["files"] == expected


@pytest.mark.parametrize(("files", "current", "expected"), [
    (
        {"a.py": {"C901": 3, "PL": 2}},
        {"a.py": {"C901": 1, "PL": 2}},
        {"a.py": {"C901": 1, "PL": 2}},
    ),
    (
        {"a.py": {"C901": 1}},
        {"a.py": {"C901": 4}},
        {"a.py": {"C901": 1}},
    ),
    (
        {"a.py": {"PL": 1}},
        {"a.py": {"PL": 1}, "b.py": {"PL": 2}},
        {"a.py": {"PL": 1}},
    ),
    (
        {"a.py": {"C901": 1}},
        {"a.py": {"C901": 1, "B": 2}},
        {"a.py": {"C901": 1}},
    ),
    ({"a.py": {"C901": 2}}, {}, {}),
    (
        {"a.py": {"C901": 2, "PL": 1}},
        {"a.py": {"PL": 1}},
        {"a.py": {"PL": 1}},
    ),
])
def test_shrink_lowers_entries_and_never_raises(
    tmp_path: Path, monkeypatch, files, current, expected,
) -> None:
    baseline = tmp_path / "ruff_quality_baseline.json"
    original = json.dumps({"commit": "abc", "files": files}, indent=2) + "\n"
    baseline.write_text(original, encoding="utf-8")
    monkeypatch.setattr(quality, "BASELINE", baseline)
    monkeypatch.setattr(quality, "counts", lambda *args, **kwargs: current)

    assert quality.main(["--shrink"]) == 0

    written = json.loads(baseline.read_text(encoding="utf-8"))
    assert written["commit"] == "abc"
    assert written["files"] == expected
    if expected == files:
        assert baseline.read_text(encoding="utf-8") == original


def test_report_names_rises_new_files_and_family_totals() -> None:
    baseline = {"rose.py": {"C901": 1, "PL": 2}, "fell.py": {"B": 4}, "same.py": {"N": 1}}
    current = {
        "rose.py": {"C901": 3, "PL": 2, "SIM": 1},
        "fell.py": {"B": 1},
        "same.py": {"N": 1},
        "new.py": {"RET": 2},
    }

    assert quality.report(baseline, current) == [
        "  new.py: RET 2 (not in the baseline)",
        "  rose.py C901: 1 -> 3 (+2)",
        "  rose.py SIM: 0 -> 1 (+1)",
        "  C901: 1 -> 3 (+2)",
        "  PL: 2 -> 2 (+0)",
        "  B: 4 -> 1 (-3)",
        "  SIM: 0 -> 1 (+1)",
        "  RET: 0 -> 2 (+2)",
        "  N: 1 -> 1 (+0)",
        "  D102/D103: 0 -> 0 (+0)",
    ]
