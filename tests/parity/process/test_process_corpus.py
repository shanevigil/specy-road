"""The process corpus (:mod:`tests.parity.process.corpus`) through ``python -m specy_road.cli``.

Each case's steps run one after the other, each in a fresh interpreter as a user's shell starts
it, and their exit codes and output must match ``golden/<case>.txt``, recorded from the commands
as they ran before they stopped launching a child interpreter of their own.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.parity.process.corpus import CASES, Case, build, corpus_env, golden_path, step_transcript
from tests.parity.support import check_golden, run_cli

pytestmark = pytest.mark.parity


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.name)
def test_each_step_in_its_own_process_matches_the_corpus(case: Case, tmp_path: Path) -> None:
    dirs, steps = build(case, tmp_path)
    env = corpus_env()
    recorded = []
    for cwd, argv in steps:
        result = run_cli("specy_road.cli", argv, cwd=cwd, env=env)
        recorded.append(step_transcript(argv, result.returncode, result.stdout, result.stderr, dirs))
    check_golden(golden_path(case), "\n".join(recorded))
