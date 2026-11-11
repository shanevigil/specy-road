"""The process corpus (:mod:`tests.parity.process.corpus`): exit code, stdout and stderr per step.

``golden/<case>.txt`` was recorded through ``python -m specy_road.cli`` while each command still
ran in a child interpreter of its own. Each step must still match it run that way, from a shell,
and run with every other step in one interpreter.
"""

from __future__ import annotations

import difflib
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

from tests.parity.process.corpus import CASES, Case, build, corpus_env, golden_path, step_transcript
from tests.helpers import REPO
from tests.parity.support import check_golden, run_cli

pytestmark = pytest.mark.parity


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.name)
def test_each_step_in_its_own_process_matches_the_corpus(case: Case, tmp_path: Path) -> None:
    dirs, steps = build(case, tmp_path)
    env = corpus_env()
    recorded = []
    for cwd, argv in steps:
        result = run_cli("specy_road.cli", argv, cwd=cwd, env=env)
        code, out, err = result.returncode, result.stdout, result.stderr
        recorded.append(step_transcript(argv, code, out, err, dirs))
    check_golden(golden_path(case), "\n".join(recorded))


def test_every_step_in_one_process_matches_the_corpus(tmp_path: Path) -> None:
    """All cases through ``specy_road.cli.main`` in one interpreter that refuses to start another.

    Two roots, one after the other, in one process: a module that kept a root, a cache or an
    environment edit from an earlier step would print something else in a later one.
    """
    built, plan = {}, []
    for case in CASES:
        dirs, steps = build(case, tmp_path / case.name)
        built[case.name] = (dirs, steps)
        plan.append({"case": case.name, "steps": [[str(cwd), argv] for cwd, argv in steps]})
    (tmp_path / "plan.json").write_text(json.dumps(plan))
    driver = subprocess.run(
        [sys.executable, "-m", "tests.parity.process.corpus",
         tmp_path / "plan.json", tmp_path / "results.json"],
        cwd=tmp_path, env=corpus_env(), capture_output=True, text=True, check=False,
    )
    assert driver.returncode == 0, driver.stderr
    results = json.loads((tmp_path / "results.json").read_text())
    differs = []
    for case in CASES:
        dirs, steps = built[case.name]
        recorded = "\n".join(
            step_transcript(argv, code, out, err, dirs)
            for (_cwd, argv), (code, out, err) in zip(steps, results[case.name], strict=True)
        )
        expected = golden_path(case).read_text(encoding="utf-8")
        if recorded != expected:
            differs.append("".join(difflib.unified_diff(
                expected.splitlines(keepends=True), recorded.splitlines(keepends=True),
                f"golden/{case.name}.txt", "in one process",
            )))
    assert not differs, "\n".join(differs)


@pytest.mark.parametrize("name", ["cli.py", "cli_entry.py", "bundled_scripts/doctor.py",
                                  "bundled_scripts/mark_implementation_reviewed.py"])
def test_dispatch_and_nested_runs_start_no_specy_road_interpreter(name: str) -> None:
    """These run commands, in their own process: none starts ``python -m specy_road``."""
    source = (REPO / "specy_road" / name).read_text(encoding="utf-8")
    assert not re.search(r"""["']-m["']\s*,\s*["']specy_road""", source)
    assert "runpy" not in source
