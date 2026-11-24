"""Each orchestration state row (:mod:`tests.parity.orchestration_state.rows`) reads as at pickup.

This file imports nothing the leaf added, so it also runs on the merge base's package:
``python -m tests.parity.orchestration_state.replay <ref>`` runs it there against the committed
goldens.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.support.parity import golden_file
from tests.parity.orchestration_state.rows import GOLDEN, ROWS, Row, record
from tests.parity.support import check_golden

pytestmark = pytest.mark.parity


@pytest.mark.slow
@pytest.mark.parametrize("row", ROWS, ids=lambda r: r.name)
def test_worker_list_plan_doctor_and_cleanup_eligibility_match_the_row(
    row: Row, tmp_path: Path
) -> None:
    """Today's readers print what they printed at pickup, and judge the same cleanup."""
    check_golden(golden_file(GOLDEN, row), record(row, tmp_path))
