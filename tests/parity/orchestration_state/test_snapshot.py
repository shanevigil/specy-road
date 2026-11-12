""":func:`specy_road.orchestration.snapshot` gives each state row the v1 fixture's fields and
status, and writes nothing."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from specy_road import worker_state as ws
from specy_road.orchestration import snapshot
from tests.helpers import REPO
from tests.parity.orchestration_state.rows import ROWS, Row, build, snapshot_golden
from tests.parity.process.corpus import corpus_env, step_transcript
from tests.parity.support import check_golden, run_cli

pytestmark = pytest.mark.parity

FIXTURE = json.loads(
    (REPO / "tests" / "fixtures" / "orchestration_snapshot_v1.json").read_text(encoding="utf-8")
)
SHAPE = FIXTURE["shape"]
LEAF = SHAPE["leaves"]["<node id>"]


def snapshot_text(repo: Path, dirs: dict[str, Path]) -> str:
    """``snapshot(repo)`` as JSON, normalised as the command transcripts are."""
    return step_transcript(["(snapshot)"], 0, json.dumps(snapshot(repo), indent=2) + "\n", "", dirs)


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


#: Registry documents the state model reads as unknown (``read_claims``'s rule): not YAML, not
#: UTF-8, a top level that is neither a mapping nor empty (falsy ones included), and a mapping with
#: an ``entries`` key whose value is not a list, falsy values included.
UNREADABLE_REGISTRIES = {
    "not_yaml": b"entries: [\n",
    "not_utf8": b"entries: [\xff\xfe]\n",
    "list": b"- node_id: M1.1\n  branch: feature/rm-thing\n",
    "top_empty_list": b"[]\n",
    "top_false": b"false\n",
    "top_zero": b"0\n",
    "top_empty_string": b'""\n',
    "entries_not_list": b"entries: M1.1\n",
    "entries_null": b"entries:\n",
    "entries_false": b"entries: false\n",
    "entries_empty_string": b'entries: ""\n',
    "entries_empty_mapping": b"entries: {}\n",
    "entries_one": b"entries: 1\n",
}


@pytest.mark.parametrize("registry", UNREADABLE_REGISTRIES, ids=str)
@pytest.mark.parametrize(
    "row_name, status", [("fresh_manual_claim", None), ("live_worker", "running")]
)
def test_an_unreadable_registry_is_unknown_and_plan_refuses_it(
    row_name: str, status: str | None, registry: str, tmp_path: Path
) -> None:
    """The snapshot invents no claimed leaf and keeps a worker's leaf, worktrees and reviews;
    ``worker list`` still lists; ``orchestrate plan`` fails and offers no leaf as ready."""
    repo, _dirs = build(next(r for r in ROWS if r.name == row_name), tmp_path)
    (repo / "roadmap" / "registry.yaml").write_bytes(UNREADABLE_REGISTRIES[registry])
    leaves = snapshot(repo)["leaves"]
    if status is None:
        assert leaves == {}
    else:
        leaf = leaves["M1.1"]
        assert leaf["claim"] == "unknown" and leaf["status"] == status
        assert [w["id"] for w in leaf["workers"]] == ["w-0001"] and leaf["worktrees"]
    listed = run_cli("specy_road.cli", ["worker", "list", "--all"], cwd=repo, env=corpus_env())
    assert listed.returncode == 0, listed.stderr
    plan = run_cli("specy_road.cli", ["orchestrate", "plan", "--json"], cwd=repo, env=corpus_env())
    assert plan.returncode == 1 and plan.stdout == ""


#: The rule's other side: documents that mean no claims. ``None`` deletes the file.
EMPTY_REGISTRIES = {
    "absent_file": None,
    "empty_document": b"# no claims yet\n",
    "no_entries_key": b"version: 1\n",
    "empty_entries": b"version: 1\nentries: []\n",
}


@pytest.mark.parametrize("registry", EMPTY_REGISTRIES, ids=str)
def test_an_empty_registry_means_no_claims_and_plan_runs(registry: str, tmp_path: Path) -> None:
    """The worker's leaf has no claim (not ``unknown``), and ``orchestrate plan`` plans."""
    repo, _dirs = build(next(r for r in ROWS if r.name == "live_worker"), tmp_path)
    path = repo / "roadmap" / "registry.yaml"
    if EMPTY_REGISTRIES[registry] is None:
        path.unlink()
    else:
        path.write_bytes(EMPTY_REGISTRIES[registry])
    leaf = snapshot(repo)["leaves"]["M1.1"]
    assert leaf["claim"] is None and leaf["status"] == "running"
    plan = run_cli("specy_road.cli", ["orchestrate", "plan", "--json"], cwd=repo, env=corpus_env())
    assert plan.returncode == 0, plan.stderr


#: Worker records the state model cannot read: not YAML, not UTF-8, not a mapping, not the schema.
UNREADABLE_WORKER_RECORDS = {
    "not_yaml": b"state: [running\n",
    "not_utf8": b"state: \xff\xfe\n",
    "not_mapping": b"- running\n",
    "not_schema": b"worker_id: w-0001\n",
}


@pytest.mark.parametrize("record", UNREADABLE_WORKER_RECORDS, ids=str)
def test_an_unreadable_worker_record_is_leafless_unknown_and_readers_go_on(
    record: str, tmp_path: Path
) -> None:
    """The record is listed by id with every other field unknown; the claim keeps its values and
    its M15.26 status; ``worker list`` and doctor's claim report run."""
    repo, _dirs = build(next(r for r in ROWS if r.name == "fresh_manual_claim"), tmp_path)
    ws.workers_dir(repo).mkdir(parents=True, exist_ok=True)
    (ws.workers_dir(repo) / "w-0001.yaml").write_bytes(UNREADABLE_WORKER_RECORDS[record])
    snap = snapshot(repo)
    assert [(w["id"], w["status"]) for w in snap["leafless_workers"]] == [("w-0001", "unknown")]
    leaf = snap["leaves"]["M1.1"]
    assert leaf["claim"]["branch"] == "feature/rm-thing" and leaf["status"] == "abandoned"
    listed = run_cli("specy_road.cli", ["worker", "list", "--all"], cwd=repo, env=corpus_env())
    assert listed.returncode == 0, listed.stderr
    doctor = run_cli("specy_road.cli", ["doctor"], cwd=repo, env=corpus_env())
    assert doctor.returncode == 0 and "Claims with no live worker" in doctor.stdout, doctor.stderr
