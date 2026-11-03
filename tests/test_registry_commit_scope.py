"""Registry commits touch only the registry, and nothing stashes ``work/``.

Pickup used to stash ``work/`` (untracked files included) around the
integration-branch registry commit and pop it afterwards. The stash stack is
shared by every session in a checkout, so files another session wrote during
that window were stranded in the stash, and a failed pop only warned.
"""

from __future__ import annotations

import subprocess
import threading
import time
from pathlib import Path

import pytest

from tests.review_repo_helpers import git, make_review_repo

from specy_road import worker_state as ws
from specy_road.bundled_scripts import do_next_task as dnt
from specy_road.bundled_scripts.do_next_task_pickup_helpers import register_and_commit
from specy_road.bundled_scripts.repo_ops import working_tree_clean


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True).stdout


def _repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "t@e.com")
    _git(tmp_path, "config", "user.name", "T")
    (tmp_path / "roadmap").mkdir()
    (tmp_path / "roadmap" / "registry.yaml").write_text("version: 1\nentries: []\n", encoding="utf-8")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "init")
    return tmp_path


def test_work_changes_do_not_count_against_a_clean_tree_when_asked(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    (repo / "work").mkdir()
    (repo / "work" / "brief-M1.1.md").write_text("brief\n", encoding="utf-8")

    assert not working_tree_clean(repo)
    assert working_tree_clean(repo, except_work=True)

    (repo / "README.md").write_text("x\n", encoding="utf-8")
    assert not working_tree_clean(repo, except_work=True)


def test_the_registry_commit_carries_only_the_registry(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    (repo / "work").mkdir()
    (repo / "work" / "staged.md").write_text("someone else's\n", encoding="utf-8")
    (repo / "work" / "untracked.md").write_text("live session file\n", encoding="utf-8")
    _git(repo, "add", "work/staged.md")

    register_and_commit(
        registry_path=repo / "roadmap" / "registry.yaml",
        git_runner=lambda *a: _git(repo, *a),
        node={"id": "M1.1", "codename": "first"},
        branch="feature/rm-first",
        reg={"version": 1, "entries": []},
        commit_message="chore: claim M1.1",
        impl_review_gate=False,
    )

    assert _git(repo, "show", "--name-only", "--format=", "HEAD").split() == ["roadmap/registry.yaml"]
    assert "A  work/staged.md" in _git(repo, "status", "--porcelain")
    assert (repo / "work" / "untracked.md").read_text(encoding="utf-8") == "live session file\n"
    assert _git(repo, "stash", "list") == ""


def _free_leaf_for_pickup(repo: Path) -> None:
    git(repo, "checkout", "-q", "dev")
    (repo / "roadmap" / "registry.yaml").write_text("version: 1\nentries: []\n", encoding="utf-8")
    chunk = repo / "roadmap" / "phases" / "M1.json"
    chunk.write_text(chunk.read_text().replace('"status": "In Progress"', '"status": "Not Started"'))
    git(repo, "commit", "-qam", "free the claim")


def test_pickup_leaves_worker_events_and_stash_alone_while_the_log_grows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A1: real ``--local`` pickup while another worker appends its event log."""
    repo = make_review_repo(tmp_path)
    _free_leaf_for_pickup(repo)
    rec = ws.create_record(repo, "M1.1", "claude-code", "opus", repo)

    during_commit = threading.Event()
    stop = threading.Event()
    appended: list[str] = []
    append_errors: list[BaseException] = []
    lock = threading.Lock()

    real_git_run = dnt.git_run

    def git_run(root, *args: str) -> None:
        if args[:1] == ("commit",):
            during_commit.set()
            time.sleep(0.15)
        real_git_run(root, *args)

    def append_while_pickup_runs() -> None:
        if not during_commit.wait(timeout=30):
            return
        n = 0
        while not stop.is_set():
            summary = f"concurrent-{n}"
            try:
                ws.append_event(repo, rec, "output", source="worker", summary=summary)
                with lock:
                    appended.append(summary)
                n += 1
            except BaseException as exc:  # noqa: BLE001 — collect, assert empty after join
                append_errors.append(exc)
            if n >= 12:
                break

    monkeypatch.setattr(dnt, "ROOT", repo)
    monkeypatch.setattr(dnt, "git_run", git_run)
    monkeypatch.setattr(dnt, "sync_integration_branch", lambda *_a, **_k: None)
    monkeypatch.setattr(dnt, "git_config_user_name", lambda _r: "T")
    monkeypatch.setattr(dnt, "prompt_on_complete", lambda _r, _oc: "merge")

    writer = threading.Thread(target=append_while_pickup_runs, name="worker-log")
    writer.start()
    try:
        dnt.main(["--local", "--on-complete", "merge", "--repo-root", str(repo)])
    finally:
        stop.set()
        writer.join(timeout=5)

    assert append_errors == []
    assert during_commit.is_set(), "pickup never reached the registry commit"
    with lock:
        assert len(appended) >= 8, "too few events during pickup; test did not exercise the race"
    assert _git(repo, "stash", "list") == ""

    evs = ws.events_since(repo, rec.worker_id)
    seqs = [e.seq for e in evs]
    assert seqs == list(range(1, len(seqs) + 1))
    outputs = [e.summary for e in evs if e.type == "output"]
    with lock:
        assert outputs == appended
    assert ws.load_record(repo, rec.worker_id).last_event_seq == seqs[-1]
