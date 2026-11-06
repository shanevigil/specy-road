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
        # move-node's parser takes --index, but a change file does not.
        ("- op: move-node\n  node: M99.1\n  to_parent: M99\n  index: 0\n",
         "change 2: move-node does not take index"),
        ("- op: indent\n  node: M99.2\n  to_parent: M99\n", "change 2: not a valid indent"),
        ("- op: group-nodes\n  into_new: M99.5\n  title: G\n", "change 2: group-nodes needs nodes:"),
        ("- op: archive\n  node: M99.1\n  deep: true\n", "change 2: archive does not take deep"),
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


# Group two siblings, then three moves, a removal and a dependency. M99.3 and
# M99.4 are created first, so they have no pre-batch id to report.
REGROUP = """\
changes:
  - {op: add-node, id: M99.3, type: task, title: Three, parent_id: M99}
  - {op: add-node, id: M99.4, type: task, title: Four, parent_id: M99}
  - {op: group-nodes, nodes: [M99.1, M99.2], into_new: M99.5, title: Core}
  - {op: move-node, node: M99.3, to_parent: M99.5}
  - {op: indent, node: M99.4}
  - {op: outdent, node: M99.5.3}
  - {op: remove-node, node: M99.5.4}
  - {op: add-dependency, node: M99.6, dependency: M99.5.2}
"""


def test_dry_run_prints_the_composed_id_map_before_the_waves(repo: Path) -> None:
    before = _tree(repo)
    r = _apply(repo, REGROUP, "--dry-run")
    assert r.returncode == 0, r.stderr
    tail = r.stdout[r.stdout.index("Display ids changed (old -> new):"):]
    assert tail.splitlines()[1:4] == [
        "  M99.1 -> M99.5.1",
        "  M99.2 -> M99.5.2",
        "Waves (a leaf starts once its own dependencies are Complete):",
    ]
    assert "Blocked: M99.6 waiting on M99.5.2" in tail
    assert _tree(repo) == before


def test_a_regroup_applies_in_one_run_with_one_validation(
    repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from specy_road.bundled_scripts import roadmap_crud_ops
    from specy_road.bundled_scripts.roadmap_crud_argparse import build_parser

    validations: list[Path] = []
    real = roadmap_crud_ops.validate_at

    def counting(root: Path, **kwargs: object) -> None:
        validations.append(root)
        real(root, **kwargs)

    monkeypatch.setattr(roadmap_crud_ops, "validate_at", counting)
    (repo / "changes.yaml").write_text(REGROUP, encoding="utf-8")
    ns = build_parser().parse_args(["--repo-root", str(repo), "apply", str(repo / "changes.yaml")])
    ns.func(ns)
    assert "[ok] applied 8 change(s)" in capsys.readouterr().out
    assert len(validations) == 1
    assert _node(repo, "M99.5")["title"] == "Core"
    assert _node(repo, "M99.5.1")["node_key"] == NK991
    three = _node(repo, "M99.6")
    assert three["title"] == "Three" and three["dependencies"] == [NK992]
    assert _crud(repo, "show-node", "M99.5.3").returncode == 1
    assert sorted(p.name.split("_")[0] for p in (repo / "planning").glob("M99*")) == [
        "M99", "M99.5", "M99.5.1", "M99.5.2", "M99.6",
    ]


def test_a_refused_entry_after_an_archive_restores_everything(repo: Path) -> None:
    from specy_road.bundled_scripts.roadmap_chunk_utils import load_json_chunk, write_json_chunk
    from specy_road.generated_files import regenerate_generated_files

    chunk = repo / "roadmap" / "phases" / "T.json"
    write_json_chunk(chunk, [{**n, "status": "Complete"} if n["id"] == "M99.1" else n
                             for n in load_json_chunk(chunk)])
    regenerate_generated_files(repo)
    before = _tree(repo)
    archive = "- {op: archive, node: M99.1}\n"
    r = _apply(repo, archive + "- {op: edit-node, node: M404, set: {title: X}}\n")
    assert r.returncode == 1
    assert "change 2 (edit-node) failed; no change in the batch was applied" in r.stderr
    # roadmap.md, roadmap-context.md, the archive ledger and the moved sheet.
    assert _tree(repo) == before
    assert not (repo / "roadmap" / "archive").exists()
    # The same archive alone does apply, regenerating both files.
    assert _apply(repo, archive).returncode == 0
    after = _tree(repo)
    assert after["roadmap.md"] != before["roadmap.md"]
    assert after["roadmap-context.md"] != before["roadmap-context.md"]


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
