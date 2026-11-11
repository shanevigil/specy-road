"""Each orchestration state row (:mod:`tests.parity.orchestration_state.rows`) reads as at pickup,
and :func:`specy_road.orchestration.snapshot` gives it the v1 fixture's fields and status."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from specy_road.orchestration import snapshot
from tests.helpers import REPO
from tests.parity.orchestration_state.rows import (
    ROWS,
    Row,
    build,
    golden_path,
    record,
    snapshot_golden,
    snapshot_text,
)
from tests.parity.support import check_golden

pytestmark = pytest.mark.parity

FIXTURE = json.loads(
    (REPO / "tests" / "fixtures" / "orchestration_snapshot_v1.json").read_text(encoding="utf-8")
)
SHAPE = FIXTURE["shape"]
LEAF = SHAPE["leaves"]["<node id>"]


@pytest.mark.parametrize("row", ROWS, ids=lambda r: r.name)
def test_worker_list_plan_doctor_and_cleanup_eligibility_match_the_row(
    row: Row, tmp_path: Path
) -> None:
    """Today's readers print what they printed at pickup, and judge the same cleanup."""
    check_golden(golden_path(row), record(row, tmp_path))


def _files(root: Path) -> dict[str, bytes]:
    return {
        str(p.relative_to(root)): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()
    }


def _check_shape(snap: dict) -> None:
    assert snap.keys() == SHAPE.keys() and snap["schema"] == FIXTURE["schema"]
    workers = [*snap["leafless_workers"]]
    for leaf in snap["leaves"].values():
        assert leaf.keys() == LEAF.keys() and leaf["status"] in FIXTURE["status_vocabulary"]
        assert leaf["claim"] in (None, "unknown") or leaf["claim"].keys() == LEAF["claim"].keys()
        assert all(w.keys() == LEAF["worktrees"][0].keys() for w in leaf["worktrees"])
        assert all(r.keys() == LEAF["reviews"][0].keys() for r in leaf["reviews"])
        workers += leaf["workers"]
    assert all(w.keys() == LEAF["workers"][0].keys() for w in workers)


@pytest.mark.parametrize("row", ROWS, ids=lambda r: r.name)
def test_snapshot_has_the_v1_fields_and_the_rows_status_and_writes_nothing(
    row: Row, tmp_path: Path
) -> None:
    """Exactly the fixture's fields, the recorded status, and no file of the repo changed."""
    repo, dirs = build(row, tmp_path)
    before = {
        d: _files(d) for d in {repo, *(p for k, p in dirs.items() if k in ("leaf", "scratch"))}
    }
    snap = snapshot(repo)
    assert {d: _files(d) for d in before} == before
    _check_shape(snap)
    check_golden(snapshot_golden(row), snapshot_text(repo, dirs))


@pytest.mark.parametrize(
    "row_name, status", [("fresh_manual_claim", None), ("live_worker", "running")]
)
def test_an_unreadable_registry_sets_the_claim_unknown_and_keeps_the_workers(
    row_name: str, status: str | None, tmp_path: Path
) -> None:
    """A registry that is not YAML: no claimed leaf is invented, and a worker's leaf stays."""
    repo, _dirs = build(next(r for r in ROWS if r.name == row_name), tmp_path)
    (repo / "roadmap" / "registry.yaml").write_text("entries: [\n", encoding="utf-8")
    leaves = snapshot(repo)["leaves"]
    if status is None:
        assert leaves == {}
    else:
        assert leaves["M1.1"]["claim"] == "unknown" and leaves["M1.1"]["status"] == status
        assert [w["id"] for w in leaves["M1.1"]["workers"]] == ["w-0001"]
