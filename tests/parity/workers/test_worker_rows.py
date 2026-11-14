"""Each worker row (:mod:`tests.parity.workers.rows`) leaves the state files and events it left
at pickup.

The table imports only modules that exist before and after the worker fold, so it was recorded on
the merge base and runs unchanged after it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.parity.support import check_golden
from tests.parity.workers.rows import ROWS, Row, golden_path, record

pytestmark = pytest.mark.parity


@pytest.mark.parametrize("row", ROWS, ids=lambda r: r.name)
def test_worker_row_matches_its_golden(row: Row, tmp_path: Path) -> None:
    """The steps' exits and output, the worker records, event logs, interventions, ops and
    leases."""
    check_golden(golden_path(row), record(row, tmp_path))
