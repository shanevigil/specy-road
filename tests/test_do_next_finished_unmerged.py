"""A leaf finished on an unmerged feature branch is not offered again."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from specy_road.bundled_scripts import do_next_finished_unmerged as fu
from specy_road.bundled_scripts import do_next_task as dnt
from specy_road.bundled_scripts.do_next_task_pickup_helpers import (
    assert_not_already_claimed,
)


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True
    )


def _write_graph(repo: Path, status: str) -> None:
    roadmap = repo / "roadmap"
    (roadmap / "phases").mkdir(parents=True, exist_ok=True)
    (roadmap / "manifest.json").write_text(
        json.dumps({"version": 1, "includes": ["phases/M1.json"]}), encoding="utf-8"
    )
    (roadmap / "phases" / "M1.json").write_text(
        json.dumps(
            {
                "nodes": [
                    {
                        "id": "M1.1",
                        "node_key": "11111111-1111-5111-8111-111111111111",
                        "codename": "trash-soft-delete",
                        "title": "Trash",
                        "type": "task",
                        "parent_id": None,
                        "sibling_order": 1,
                        "status": status,
                        "dependencies": [],
                        "touch_zones": [],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A clone whose ``dev`` says Not Started and whose feature branch says Complete."""
    root = tmp_path / "r"
    root.mkdir()
    _git(root, "init", "-q", "-b", "dev")
    _git(root, "config", "user.email", "t@e.com")
    _git(root, "config", "user.name", "T")
    _write_graph(root, "Not Started")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "graph")

    _git(root, "checkout", "-q", "-b", "feature/rm-trash-soft-delete")
    _write_graph(root, "Complete")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "finish")
    _git(root, "checkout", "-q", "dev")
    return root


CANDIDATE = [{"id": "M1.1", "codename": "trash-soft-delete"}]


def test_finished_leaf_on_unmerged_branch_is_dropped(repo: Path) -> None:
    """The branch tip, not the registry row, is what proves the work was done."""
    ids, logs = fu.finished_unmerged_ids(
        CANDIDATE, repo_root=repo, remote="origin", integration_branch="dev"
    )
    assert ids == {"M1.1"}
    assert len(logs) == 1
    assert "M1.1" in logs[0] and "dev" in logs[0]


def test_unfinished_branch_is_left_alone(repo: Path) -> None:
    """A branch that exists but has not finished the node stays pickable."""
    _git(repo, "checkout", "-q", "feature/rm-trash-soft-delete")
    _write_graph(repo, "In Progress")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "wip")
    _git(repo, "checkout", "-q", "dev")

    ids, logs = fu.finished_unmerged_ids(
        CANDIDATE, repo_root=repo, remote="origin", integration_branch="dev"
    )
    assert ids == set()
    assert logs == []


def test_no_feature_branch_means_no_work(repo: Path) -> None:
    _git(repo, "branch", "-q", "-D", "feature/rm-trash-soft-delete")
    ids, _ = fu.finished_unmerged_ids(
        CANDIDATE, repo_root=repo, remote="origin", integration_branch="dev"
    )
    assert ids == set()


def test_candidate_without_matching_codename_is_untouched(repo: Path) -> None:
    """Branch discovery keys on codename; an unrelated leaf is not affected."""
    ids, _ = fu.finished_unmerged_ids(
        [{"id": "M2.1", "codename": "something-else"}],
        repo_root=repo,
        remote="origin",
        integration_branch="dev",
    )
    assert ids == set()


def test_empty_candidates_short_circuit(tmp_path: Path) -> None:
    """No candidates means no git calls, so a non-repo path is safe."""
    ids, logs = fu.finished_unmerged_ids(
        [], repo_root=tmp_path, remote="origin", integration_branch="dev"
    )
    assert (ids, logs) == (set(), [])


def test_non_git_directory_is_safe(tmp_path: Path) -> None:
    ids, _ = fu.finished_unmerged_ids(
        CANDIDATE, repo_root=tmp_path, remote="origin", integration_branch="dev"
    )
    assert ids == set()


def test_local_ref_wins_over_remote_tracking(repo: Path) -> None:
    """A local head is fresher than its remote-tracking ref after a local finish."""
    sha = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "feature/rm-trash-soft-delete"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    _git(
        repo, "update-ref",
        "refs/remotes/origin/feature/rm-trash-soft-delete", sha,
    )
    refs = fu.feature_refs_by_codename(repo, "origin")
    assert refs == {"trash-soft-delete": "feature/rm-trash-soft-delete"}


def test_remote_only_branch_is_still_seen(repo: Path) -> None:
    """Another clone's finished branch counts: the node is done, not free."""
    sha = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "feature/rm-trash-soft-delete"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    _git(repo, "branch", "-q", "-D", "feature/rm-trash-soft-delete")
    _git(
        repo, "update-ref",
        "refs/remotes/origin/feature/rm-trash-soft-delete", sha,
    )
    ids, _ = fu.finished_unmerged_ids(
        CANDIDATE, repo_root=repo, remote="origin", integration_branch="dev"
    )
    assert ids == {"M1.1"}


def test_drop_finished_unmerged_filters_and_reports(repo, monkeypatch, capsys) -> None:
    """The pickup queue loses the finished leaf and says why."""
    monkeypatch.setattr(dnt, "ROOT", repo)
    keep = {"id": "M1.2", "codename": "other"}
    out = dnt._drop_finished_unmerged([*CANDIDATE, keep], "dev", "origin")
    assert out == [keep]
    assert "skipping M1.1" in capsys.readouterr().out


def test_drop_finished_unmerged_is_a_no_op_when_nothing_finished(
    repo, monkeypatch, capsys
) -> None:
    monkeypatch.setattr(dnt, "ROOT", repo)
    queue = [{"id": "M1.2", "codename": "other"}]
    assert dnt._drop_finished_unmerged(queue, "dev", "origin") is queue
    assert capsys.readouterr().out == ""


# --- duplicate claim guard -------------------------------------------------


def test_duplicate_node_id_is_refused() -> None:
    reg = {"entries": [{"node_id": "M1.1", "codename": "old", "branch": "feature/rm-old"}]}
    with pytest.raises(SystemExit) as e:
        assert_not_already_claimed(reg, {"id": "M1.1", "codename": "new"})
    assert "node_id" in str(e.value) and "feature/rm-old" in str(e.value)


def test_duplicate_codename_is_refused() -> None:
    """Removal keys on codename, so a codename collision is the same corruption."""
    reg = {"entries": [{"node_id": "M9.9", "codename": "dup", "branch": "feature/rm-dup"}]}
    with pytest.raises(SystemExit) as e:
        assert_not_already_claimed(reg, {"id": "M1.1", "codename": "dup"})
    assert "codename" in str(e.value)


def test_unclaimed_node_registers_cleanly() -> None:
    reg = {"entries": [{"node_id": "M9.9", "codename": "other"}]}
    assert_not_already_claimed(reg, {"id": "M1.1", "codename": "fresh"})


def test_empty_registry_registers_cleanly() -> None:
    assert_not_already_claimed({}, {"id": "M1.1", "codename": "fresh"})
