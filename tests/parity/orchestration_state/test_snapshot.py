""":func:`specy_road.orchestration.snapshot` gives each state row the v1 fixture's fields and
status, and writes nothing."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

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


#: Registry documents the state model reads as unknown: not YAML, not UTF-8, not a mapping, and a
#: mapping with an ``entries`` key whose value is not a list, falsy values included.
UNREADABLE_REGISTRIES = {
    "not_yaml": b"entries: [\n",
    "not_utf8": b"entries: [\xff\xfe]\n",
    "list": b"- node_id: M1.1\n  branch: feature/rm-thing\n",
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
