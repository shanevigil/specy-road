"""Each grind table row (:mod:`tests.parity.grind.rows`) runs as it did at pickup.

The rows drive ``specy-road grind-session`` as a subprocess and import no grind module, so the
same goldens hold before and after the grind modules move into ``specy_road/orchestration/grind``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.parity.grind.fixture import (
    add_readiness_cases,
    build_template,
    copy_project,
    offline_env,
)
from tests.parity.grind.rows import ROWS, Row, golden_path, record
from tests.parity.support import check_golden

pytestmark = pytest.mark.parity


@pytest.fixture(scope="module")
def templates(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    """The base project, and a copy with the readiness cases added, built once per worker."""
    base = build_template(tmp_path_factory.mktemp("grind-base"))
    readiness = tmp_path_factory.mktemp("grind-readiness")
    root = copy_project(base, readiness)
    add_readiness_cases(root, offline_env(readiness))
    return {"base": base, "readiness": readiness}


@pytest.mark.parametrize("row", ROWS, ids=lambda r: r.name)
def test_grind_session_matches_the_row(row: Row, tmp_path: Path, templates: dict) -> None:
    """Exit code, events, refusals and the project's state are what they were at pickup."""
    check_golden(golden_path(row), record(row, tmp_path, templates))
