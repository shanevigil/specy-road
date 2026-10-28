"""Lean-code gates: scripts/check_clones.py, check_test_private_imports.py, mutation_report.py."""

from __future__ import annotations

import importlib.util
import json
import shutil
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MUTMUT_SAMPLE = ROOT / "tests" / "fixtures" / "mutation" / "results-sample.txt"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


check_clones = _load("check_clones")
private_imports = _load("check_test_private_imports")
mutation_report = _load("mutation_report")

PYLINT_OUTPUT = textwrap.dedent(
    """\
    ************* Module pkg.a
    pkg/a.py:1:0: R0801: Similar lines in 2 files
    ==pkg.b:[3:11]
    ==pkg.a:[3:11]
        x = 1
        y = 2 (duplicate-code)
    pkg/a.py:1:0: R0801: Similar lines in 2 files
    ==pkg.c:[10:17]
    ==pkg.a:[20:27]
        z = 3 (duplicate-code)
    """
)

CLONE_BODY = """
def build(items):
    total = 0
    seen = set()
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        total += len(str(item)) * 3
    return total, sorted(seen)
"""


# --- check_clones -----------------------------------------------------------


def test_parse_clones_canonical_keys():
    assert check_clones.parse_clones(PYLINT_OUTPUT) == {
        ("pkg.a", "pkg.b", "8"),
        ("pkg.a", "pkg.c", "7"),
    }


def test_parse_clones_is_order_independent():
    swapped = PYLINT_OUTPUT.replace("==pkg.b:[3:11]\n==pkg.a:[3:11]", "==pkg.a:[3:11]\n==pkg.b:[3:11]")
    assert check_clones.parse_clones(swapped) == check_clones.parse_clones(PYLINT_OUTPUT)


def _pylint() -> str:
    exe = shutil.which("pylint")
    if exe is None:
        pytest.skip("pylint not installed")
    return exe


def test_check_clones_passes_on_committed_baseline(monkeypatch):
    exe = _pylint()
    monkeypatch.chdir(ROOT)
    assert check_clones.main(["--pylint", exe]) == 0


def test_check_clones_fails_on_new_clone(tmp_path, monkeypatch, capsys):
    exe = _pylint()
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "one.py").write_text(CLONE_BODY)
    (pkg / "two.py").write_text(CLONE_BODY.replace("build", "make"))
    baseline = tmp_path / "clone-baseline.json"
    args = ["--pylint", exe, "--source", str(pkg), "--baseline", str(baseline)]

    assert check_clones.main(args) == 1
    assert "NEW CLONE: pkg.one <-> pkg.two" in capsys.readouterr().out

    assert check_clones.main([*args, "--update-baseline"]) == 0
    data = json.loads(baseline.read_text())
    assert data["clones"] == [{"modules": ["pkg.one", "pkg.two"], "lines": data["clones"][0]["lines"]}]
    assert check_clones.main(args) == 0


# --- check_test_private_imports ----------------------------------------------


def test_find_private_refs_forms():
    source = textwrap.dedent(
        """\
        import specy_road.pkg._impl
        from specy_road.mod import public, _helper
        from specy_road.bundled_scripts import thing as _alias
        import specy_road.other
        import specy_road.worker_process as wp
        from specy_road.pkg import mod

        def test_x(monkeypatch):
            monkeypatch.setattr("specy_road.gui._settings", None)
            mock.patch("specy_road.gui._client")
            label = "specy_road.gui._not_a_target"
            specy_road.other._deep.call()
            specy_road.other.public()
            obj.__dunder__
            wp._cmdline(1)
            mod._x
            monkeypatch.setattr(wp, "_pid", 1)
            mock.patch.object(mod, "_y")
            wp.public()
            monkeypatch.setattr(wp, "public", 1)
            _alias.public
        """
    )
    assert private_imports.find_private_refs(source, "t.py") == {
        "specy_road.pkg._impl",
        "specy_road.mod._helper",
        "specy_road.gui._settings",
        "specy_road.gui._client",
        "specy_road.other._deep",
        "specy_road.worker_process._cmdline",
        "specy_road.pkg.mod._x",
        "specy_road.worker_process._pid",
        "specy_road.pkg.mod._y",
    }


def test_private_imports_pass_on_committed_baseline(monkeypatch):
    monkeypatch.chdir(ROOT)
    assert private_imports.main([]) == 0


@pytest.mark.parametrize(
    "source",
    [
        "from specy_road.core import _secret\n",
        "from specy_road import core as c\nc._secret()\n",
    ],
    ids=["import", "aliased-module-attribute"],
)
def test_private_imports_fail_on_new_reference(tmp_path, capsys, source):
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_new.py").write_text(source)
    baseline = tmp_path / "baseline.txt"
    args = ["--tests-dir", str(tests_dir), "--baseline", str(baseline)]

    assert private_imports.main(args) == 1
    assert "NEW PRIVATE REFERENCE: tests/test_new.py: specy_road.core._secret" in capsys.readouterr().out

    assert private_imports.main([*args, "--update-baseline"]) == 0
    assert "tests/test_new.py: specy_road.core._secret" in baseline.read_text()
    assert private_imports.main(args) == 0


# --- mutation_report --------------------------------------------------------


def test_mutation_report_parses_real_mutmut_sample():
    per_module = mutation_report.parse_results(MUTMUT_SAMPLE.read_text())
    assert "specy_road.milestone_lock" in per_module
    counts = per_module["specy_road.milestone_lock"]
    assert counts["killed"] + counts["survived"] + counts["other"] > 0
    assert mutation_report.score(counts) == round(
        100 * counts["killed"] / (counts["killed"] + counts["survived"]), 1
    )


def test_mutation_report_table_and_no_baseline(tmp_path, monkeypatch, capsys):
    out = tmp_path / "report.md"
    assert mutation_report.main(
        [str(MUTMUT_SAMPLE), "--baseline", str(tmp_path / "missing.json"), "--output", str(out)]
    ) == 0
    text = out.read_text()
    assert text.startswith("| Module | Killed | Survived | Other | Score | Baseline | Delta |")
    assert "| `specy_road.milestone_lock` |" in text
    assert text.rstrip().splitlines()[-1].startswith("| **total** |")
    assert "no baseline" in capsys.readouterr().out


def _baseline(tmp_path: Path, shift: float) -> Path:
    current = mutation_report.scores(mutation_report.parse_results(MUTMUT_SAMPLE.read_text()))
    path = tmp_path / "mutation-baseline.json"
    path.write_text(json.dumps({"modules": {m: s + shift for m, s in current.items()}}))
    return path


def test_mutation_report_flags_three_point_drop(tmp_path, capsys):
    assert mutation_report.main([str(MUTMUT_SAMPLE), "--baseline", str(_baseline(tmp_path, 3.0))]) == 1
    assert "MUTATION SCORE DROP: specy_road.milestone_lock" in capsys.readouterr().out


def test_mutation_report_tolerates_two_point_drop(tmp_path):
    assert mutation_report.main([str(MUTMUT_SAMPLE), "--baseline", str(_baseline(tmp_path, 2.0))]) == 0
    assert mutation_report.main([str(MUTMUT_SAMPLE), "--baseline", str(_baseline(tmp_path, -5.0))]) == 0


def test_mutation_report_write_baseline(tmp_path):
    target = tmp_path / "seed.json"
    assert mutation_report.main([str(MUTMUT_SAMPLE), "--write-baseline", str(target)]) == 0
    data = json.loads(target.read_text())
    assert data["max_drop"] == 2.0
    assert "specy_road.milestone_lock" in data["modules"]
