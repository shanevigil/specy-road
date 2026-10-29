"""``apply`` change files, ``add-node --acceptance``, and display-id dependencies."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from tests.helpers import script_subprocess_env
from tests.test_roadmap_crud import crud_fixture_repo, run_crud

NK991 = "10000000-0000-4000-8000-000000009902"
NK992 = "10000000-0000-4000-8000-000000009903"

# Chain after apply: M99.1 <- M99.2 (fixture) <- M99.3 <- M99.4.
BATCH = """\
changes:
  - op: add-node
    id: M99.3
    type: task
    title: Three
    parent_id: M99
    acceptance: [Parses the file, Names the bad entry]
    dependencies: [M99.2]
  - op: edit-node
    node: M99.1
    set:
      acceptance: [First, Second]
  - op: add-node
    id: M99.4
    type: task
    title: Four
    parent_id: M99
    acceptance: [Done]
  - op: add-dependency
    node: M99.4
    dependency: M99.3
"""


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    crud_fixture_repo(tmp_path)
    return tmp_path


def _tree(root: Path) -> dict[str, bytes]:
    return {
        str(p.relative_to(root)): p.read_bytes()
        for p in sorted(root.rglob("*"))
        if p.is_file() and p.name != "changes.yaml"
    }


def _crud(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return run_crud(root, "--repo-root", str(root), *args)


def _node(root: Path, nid: str) -> dict:
    r = _crud(root, "show-node", nid)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def _apply(root: Path, text: str, *flags: str) -> subprocess.CompletedProcess[str]:
    (root / "changes.yaml").write_text(text, encoding="utf-8")
    return _crud(root, "apply", str(root / "changes.yaml"), *flags)


def test_add_node_acceptance_is_repeatable(repo: Path) -> None:
    r = _crud(
        repo, "add-node", "--id", "M99.3", "--type", "task", "--title", "Three",
        "--parent-id", "M99", "--acceptance", "Saves offline",
        "--acceptance", "Syncs on reconnect",
    )
    assert r.returncode == 0, r.stderr
    assert _node(repo, "M99.3")["acceptance"] == ["Saves offline", "Syncs on reconnect"]


def test_add_node_dependency_takes_a_display_id_and_stores_the_key(repo: Path) -> None:
    r = _crud(
        repo, "add-node", "--id", "M99.3", "--type", "task", "--title", "Three",
        "--parent-id", "M99", "--dependency", "M99.1", "--dependency", NK992,
    )
    assert r.returncode == 0, r.stderr
    assert _node(repo, "M99.3")["dependencies"] == [NK991, NK992]


def test_add_node_unknown_dependency_is_refused_before_writing(repo: Path) -> None:
    before = _tree(repo)
    r = _crud(
        repo, "add-node", "--id", "M99.3", "--type", "task", "--title", "Three",
        "--parent-id", "M99", "--dependency", "M404",
    )
    assert r.returncode == 1
    assert "'M404' is neither a node id nor a node_key" in r.stderr
    assert _tree(repo) == before


def test_add_dependency_takes_a_display_id(repo: Path) -> None:
    assert _crud(repo, "set-dependencies", "M99.2", "--clear").returncode == 0
    r = _crud(repo, "add-dependency", "M99.1", "M99.2")
    assert r.returncode == 0, r.stderr
    assert _node(repo, "M99.1")["dependencies"] == [NK992]


def test_dry_run_validates_prints_waves_and_writes_nothing(repo: Path) -> None:
    before = _tree(repo)
    r = _apply(repo, BATCH, "--dry-run")
    assert r.returncode == 0, r.stderr
    assert "nothing was written" in r.stdout
    for i, nid in enumerate(("M99.1", "M99.2", "M99.3", "M99.4")):
        assert f"wave {i}: {nid}\n" in r.stdout
    assert "Ready now: M99.1\n" in r.stdout
    assert "Blocked: M99.4 waiting on M99.3" in r.stdout
    assert _tree(repo) == before
    assert not list((repo / "planning").glob("M99.[34]_*"))


def test_apply_writes_the_whole_batch(repo: Path) -> None:
    r = _apply(repo, BATCH)
    assert r.returncode == 0, r.stderr
    assert "[ok] applied 4 change(s)" in r.stdout
    new = _node(repo, "M99.3")
    assert new["acceptance"] == ["Parses the file", "Names the bad entry"]
    assert new["dependencies"] == [NK992]
    assert _node(repo, "M99.1")["acceptance"] == ["First", "Second"]
    assert _node(repo, "M99.4")["dependencies"] == [new["node_key"]]
    assert len(list((repo / "planning").glob("M99.[34]_*"))) == 2


def test_a_refused_change_rolls_back_the_changes_before_it(repo: Path) -> None:
    before = _tree(repo)
    r = _apply(repo, BATCH.replace("dependency: M99.3", "dependency: M404"))
    assert r.returncode == 1
    assert "change 4 (add-dependency) failed; no change in the batch was applied" in r.stderr
    # The three changes that ran first are undone, planning sheets included,
    # and their [ok] lines are not printed for work that was rolled back.
    assert _tree(repo) == before
    assert "[ok]" not in r.stdout


def test_a_dependency_cycle_is_refused_as_a_whole(repo: Path) -> None:
    before = _tree(repo)
    cycle = BATCH + "  - op: add-dependency\n    node: M99.1\n    dependency: M99.4\n"
    r = _apply(repo, cycle)
    assert r.returncode == 1
    assert "dependency cycle" in r.stderr
    assert _tree(repo) == before


@pytest.mark.parametrize(
    "entry, message",
    [
        ("- op: archive-node\n  node: M99.1\n", "change 2: each change needs op:"),
        ("- op: edit-node\n  set: {title: X}\n", "change 2: edit-node needs node:"),
        ("- op: edit-node\n  node: M99.1\n", "change 2: edit-node needs set:"),
        ("- op: add-node\n  id: M99.3\n  type: task\n  title: T\n  parent_id: M99\n  colour: red\n",
         "change 2: not a valid add-node"),
    ],
)
def test_a_malformed_entry_is_refused_before_anything_runs(
    repo: Path, entry: str, message: str
) -> None:
    before = _tree(repo)
    # A valid first entry proves nothing ran: parsing refuses the file first.
    lead = "- op: edit-node\n  node: M99.2\n  set: {title: Renamed}\n"
    r = _apply(repo, lead + entry)
    assert r.returncode == 1
    assert message in r.stderr
    assert _tree(repo) == before


def test_an_empty_change_file_is_refused(repo: Path) -> None:
    r = _apply(repo, "changes: []\n")
    assert r.returncode == 1
    assert "expected a list of changes" in r.stderr


def test_top_level_cli_dispatches_apply(repo: Path) -> None:
    (repo / "changes.yaml").write_text(BATCH, encoding="utf-8")
    r = subprocess.run(
        [sys.executable, "-m", "specy_road.cli", "apply", "changes.yaml",
         "--dry-run", "--repo-root", str(repo)],
        cwd=repo, capture_output=True, text=True, env=script_subprocess_env(),
    )
    assert r.returncode == 0, r.stderr
    assert "wave 3: M99.4" in r.stdout
