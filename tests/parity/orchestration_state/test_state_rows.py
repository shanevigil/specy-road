"""Each orchestration state row (:mod:`tests.parity.orchestration_state.rows`) reads as it did at pickup."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.parity.orchestration_state.rows import ROWS, Row, golden_path, record
from tests.parity.support import check_golden

pytestmark = pytest.mark.parity


@pytest.mark.parametrize("row", ROWS, ids=lambda r: r.name)
def test_worker_list_plan_doctor_and_cleanup_eligibility_match_the_row(row: Row, tmp_path: Path) -> None:
    check_golden(golden_path(row), record(row, tmp_path))
