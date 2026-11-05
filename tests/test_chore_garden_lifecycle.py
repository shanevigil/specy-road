"""``chore garden --open-chores`` against every lifecycle state of a garden leaf (M12.3 fix round 4).

Every step goes through a public CLI: ``chore garden``, ``edit-node``, ``add-node`` and ``archive``.
Only the ``stale-command`` class is followed; the repo has findings in all three classes.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.review_repo_helpers import git
from tests.test_chore_mode import _roadmap_bytes, garden_repo, run_chore_cli

from specy_road.bundled_scripts import archive_cli, roadmap_crud
from specy_road.bundled_scripts.roadmap_load import load_roadmap

TITLE = "Garden: stale command mentions"


def _open(repo: Path, capsys, under: str = "M1.1") -> tuple[int, str, str]:
    capsys.readouterr()
    code = run_chore_cli("chore", "garden", "--open-chores", "--under", under, "--repo-root", str(repo))
    out = capsys.readouterr()
    return code, out.out, out.err


def _crud(repo: Path, *args: str) -> None:
    roadmap_crud.main(["--repo-root", str(repo), *args])


def _set(repo: Path, node_id: str, *pairs: str) -> None:
    _crud(repo, "edit-node", node_id, *(x for pair in pairs for x in ("--set", pair)))


def _archive(repo: Path, node_id: str) -> None:
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", f"before archiving {node_id}")
    with pytest.raises(SystemExit) as e:
        archive_cli.main(["archive", node_id, "--repo-root", str(repo)])
    assert e.value.code == 0


def _stale(repo: Path) -> list[tuple[str, str, str, str]]:
    """Live nodes that are, or were, stale-command garden leaves: ``(id, codename, title, status)``."""
    return [(n["id"], n.get("codename"), n["title"], n["status"]) for n in load_roadmap(repo)["nodes"]
            if "stale" in (n.get("codename") or "") or "stale" in n["title"]]


def _added(out: str) -> str:
    """The id ``--open-chores`` printed for the stale-command class."""
    line = next(ln for ln in out.splitlines() if ln.startswith("garden: stale-command: "))
    return line.split()[3] if " added " in line else line.split()[2]


def test_in_progress_leaf_is_skipped(tmp_path: Path, capsys) -> None:
    """Row: In Progress / claimed leaf -> skip, printing its id."""
    repo = garden_repo(tmp_path)
    first = _added(_open(repo, capsys)[1])
    _set(repo, first, "status=In Progress")
    before = _roadmap_bytes(repo)
    code, out, _ = _open(repo, capsys)
    assert code == 0 and f"stale-command: {first} is still open; added nothing" in out
    assert _roadmap_bytes(repo) == before


def test_complete_then_archived_takes_the_next_unused_number(tmp_path: Path, capsys) -> None:
    """R5. Rows: Complete leaf -> add (2); Complete then archived -> add max + 1, then skip."""
    repo = garden_repo(tmp_path)
    first = _added(_open(repo, capsys)[1])
    _set(repo, first, "status=Complete")
    code, out, _ = _open(repo, capsys)
    second = _added(out)
    assert code == 0 and f"added {second} ({TITLE} (2))" in out
    _set(repo, second, "status=Complete")
    _archive(repo, first)
    assert first not in [row[0] for row in _stale(repo)]
    code, out, _ = _open(repo, capsys)
    third = _added(out)
    assert code == 0 and f"added {third} ({TITLE} (3))" in out
    assert [row for row in _stale(repo) if row[3] != "Complete"] == [
        (third, "garden-stale-command-3", f"{TITLE} (3)", "Not Started")]
    before = _roadmap_bytes(repo)
    code, out, _ = _open(repo, capsys)
    assert code == 0 and f"stale-command: {third} is still open; added nothing" in out
    assert _roadmap_bytes(repo) == before


def test_generations_with_gaps_skip_the_open_one_then_number_past_the_highest(tmp_path: Path, capsys) -> None:
    """Row: 1 archived, 2 Complete, 3 open -> skip (3); once 3 is Complete -> add (4)."""
    repo = garden_repo(tmp_path)
    ids = []
    for _ in range(3):
        ids.append(_added(_open(repo, capsys)[1]))
        if len(ids) < 3:
            _set(repo, ids[-1], "status=Complete")
    _archive(repo, ids[0])
    code, out, _ = _open(repo, capsys)
    assert code == 0 and f"stale-command: {ids[2]} is still open; added nothing" in out
    _set(repo, ids[2], "status=Complete")
    code, out, _ = _open(repo, capsys)
    assert code == 0 and f"({TITLE} (4))" in out and ("garden-stale-command-4" in [r[1] for r in _stale(repo)])


def test_hand_edited_leaf_keeps_its_identity_by_codename_or_title(tmp_path: Path, capsys) -> None:
    """Row: hand-edited leaf. Either the codename or the title still names it -> skip; neither -> add (1)."""
    repo = garden_repo(tmp_path)
    first = _added(_open(repo, capsys)[1])
    _set(repo, first, "title=Fix stale mentions")                         # codename garden-stale-command kept
    assert f"stale-command: {first} is still open" in _open(repo, capsys)[1]
    _set(repo, first, f"title={TITLE}", "codename=fix-stale-mentions")    # title kept, codename edited
    assert (first, "fix-stale-mentions", TITLE, "Not Started") in _stale(repo)
    assert f"stale-command: {first} is still open" in _open(repo, capsys)[1]
    _set(repo, first, "title=Fix stale mentions")                         # neither names it now
    code, out, _ = _open(repo, capsys)
    new = _added(out)
    assert code == 0 and new != first and f"added {new} ({TITLE})" in out
    assert (new, "garden-stale-command", TITLE, "Not Started") in _stale(repo)   # the freed name, generation 1


def test_leaf_under_another_parent_counts(tmp_path: Path, capsys) -> None:
    """Row: a garden leaf under a different parent -> skip while open; numbered past it once Complete."""
    repo = garden_repo(tmp_path)
    _crud(repo, "add-node", "--id", "M2", "--type", "phase", "--parent-id", "null", "--title", "Other phase")
    first = _added(_open(repo, capsys)[1])                                # under M1.1
    assert f"stale-command: {first} is still open" in _open(repo, capsys, under="M2")[1]
    _set(repo, first, "status=Complete")
    code, out, _ = _open(repo, capsys, under="M2")
    assert code == 0 and f"added M2.1 ({TITLE} (2))" in out


@pytest.mark.parametrize("state", ["active", "pending_mr"])
def test_milestone_locked_parent_is_refused(tmp_path: Path, capsys, state: str) -> None:
    """Row: milestone-locked parent -> refuse (exit 1, names the fix); graph and planning unchanged."""
    repo = garden_repo(tmp_path)
    chunk = repo / "roadmap" / "phases" / "M1.json"
    doc = json.loads(chunk.read_text())
    doc["nodes"][0]["milestone_execution"] = {"state": state, "rollup_branch": "feature/rm-thing",
                                              "integration_branch": "dev", "remote": "origin"}
    chunk.write_text(json.dumps(doc))
    before = _roadmap_bytes(repo)
    code, _, err = _open(repo, capsys)
    assert code == 1
    assert "error: --under M1.1: add-node refused the stale-command leaf: roadmap node 'M1.1' is inside milestone " \
           "subtree 'M1.1'" in err
    assert "Pass another --under parent, or fix what add-node names, then run again." in err
    assert _roadmap_bytes(repo) == before


def test_missing_parent_is_refused(tmp_path: Path, capsys) -> None:
    """Row: parent missing -> refuse (exit 1, names the fix); graph and planning unchanged."""
    repo = garden_repo(tmp_path)
    before = _roadmap_bytes(repo)
    code, _, err = _open(repo, capsys, under="M9")
    assert code == 1 and "add-node refused the stale-command leaf: parent_id 'M9' not found in roadmap" in err
    assert "Pass another --under parent" in err and _roadmap_bytes(repo) == before
