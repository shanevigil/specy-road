"""``specy-road chore start|close``: worker commands that take a chore slug in place of a node id (M11.28)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.review_repo_helpers import commit_file, git
from tests.test_worker_cli import _repo, run_worker_cli, wait_for_worker

from specy_road import review_delegate as rd
from specy_road import worker_ops as ops
from specy_road import worker_state as ws
from specy_road.bundled_scripts import chore_cli
from specy_road.worker_orphans import orphans


def run_chore_cli(*args: str) -> int:
    with pytest.raises(SystemExit) as e:
        chore_cli.main(list(args))
    return e.value.code or 0


def _start(repo: Path, slug: str = "fix-env", *extra: str) -> dict:
    assert run_chore_cli("chore", "start", slug, "--task", "Repair the env", "--zone", "src", "--json",
                         "--repo-root", str(repo), *extra) == 0
    return json.loads((repo / "work" / "chores" / f"{slug}.json").read_text())


def test_start_records_an_unregistered_chore(tmp_path: Path, capsys) -> None:
    repo, _ = _repo(tmp_path)
    registry = (repo / "roadmap" / "registry.yaml").read_text()
    branches = git(repo, "branch", "--list")
    chore = _start(repo)
    assert chore["branch"] == "feature/rm-thing" and chore["worktree"] == str(repo.resolve())
    assert chore["base"] == git(repo, "rev-parse", "HEAD") and chore["touch_zones"] == ["src"] and not chore["review"]
    assert (repo / "roadmap" / "registry.yaml").read_text() == registry and git(repo, "branch", "--list") == branches
    assert git(repo, "status", "--porcelain") == ""                       # under work/, gitignored
    capsys.readouterr()
    assert run_chore_cli("chore", "start", "fix-env", "--task", "t", "--zone", "src", "--repo-root", str(repo)) == 1
    for bad in ("M1.1", "w-0001", "Fix"):                                 # a node id, a worker id, upper case
        assert run_chore_cli("chore", "start", bad, "--task", "t", "--zone", "src", "--repo-root", str(repo)) == 1
    assert "already exists" in capsys.readouterr().err


def test_delegate_sync_usage_message_and_close(tmp_path: Path, capsys) -> None:
    repo, _ = _repo(tmp_path)
    _start(repo, "fix-env", "--model", "opus")
    capsys.readouterr()
    assert run_worker_cli("worker", "delegate", "fix-env", "--json", "--repo-root", str(repo)) == 0   # the chore's model
    out = json.loads(capsys.readouterr().out)
    assert out["created"] and out["model"] == "opus" and out["worktree"] == str(repo.resolve())
    prompt = (repo / "work" / "prompt-fix-env-executor-opus.md").read_text()
    assert "Repair the env" in prompt and "`src`" in prompt
    assert not (repo / "work" / "brief-fix-env.md").exists()
    rec = wait_for_worker(repo, out["worker_id"])
    assert rec.node_id == "fix-env" and rec.state == "idle" and rec.branch == "feature/rm-thing"

    assert run_worker_cli("worker", "sync", "--json", "--repo-root", str(repo)) == 0
    synced = json.loads(capsys.readouterr().out)
    assert [w["node_id"] for w in synced["workers"]] == ["fix-env"]
    assert orphans(repo) == {}                                            # no claim, yet not orphaned
    assert run_worker_cli("worker", "usage", "fix-env", "--json", "--repo-root", str(repo)) == 0
    assert json.loads(capsys.readouterr().out)["node_id"] == "fix-env"
    assert run_worker_cli("worker", "message", rec.worker_id, "--text", "also x", "--repo-root", str(repo)) == 0
    assert wait_for_worker(repo, rec.worker_id).state == "idle"

    capsys.readouterr()
    assert run_chore_cli("chore", "close", "fix-env", "--summary", "Env repaired", "--repo-root", str(repo)) == 0
    text = (repo / "work" / "chores" / "fix-env.md").read_text()
    assert "Env repaired" in text and "fix-env usage (1 attempt(s)" in text and "unreviewed (no review was run)" in text
    assert ws.load_record(repo, rec.worker_id).state == "terminated"     # its idle worker ended with the chore
    assert run_worker_cli("worker", "delegate", "fix-env", "--model", "opus", "--repo-root", str(repo)) == 1
    assert run_chore_cli("chore", "close", "fix-env", "--summary", "again", "--repo-root", str(repo)) == 1
    assert "was closed" in capsys.readouterr().err


def test_close_refuses_while_a_worker_runs(tmp_path: Path, monkeypatch) -> None:
    repo, _ = _repo(tmp_path)
    _start(repo)
    monkeypatch.setattr(ops, "spawn", lambda *a, **k: None)
    rec, _ = ops.delegate(repo, "fix-env", "opus")
    assert rec.state == "starting"                                       # not held: the turn has not ended
    with pytest.raises(ws.WorkerError, match="running worker"):
        chore_cli.close(repo, "fix-env", "s")


def test_roster_free_model_needs_a_harness(tmp_path: Path, monkeypatch) -> None:
    repo, _ = _repo(tmp_path)
    _start(repo, "a")
    with pytest.raises(ws.WorkerError, match="pass --harness"):
        ops.delegate(repo, "a", "gpt-x")
    with pytest.raises(ws.WorkerError, match="not in the roster"):   # a leaf still needs a rostered model
        ops.delegate(repo, "M1.1", "gpt-x", harness="codex")
    launched = []
    monkeypatch.setattr(ops, "spawn", lambda root, rec, launch, **k: launched.append(launch))
    _start(repo, "b", "--model", "gpt-x", "--harness", "codex")
    rec, created = ops.delegate(repo, "b", None)
    assert created and rec.harness == "codex" and rec.model == "gpt-x"
    assert "gpt-x" in launched[0].argv


def test_reconcile_enforces_the_chore_zones(tmp_path: Path, monkeypatch) -> None:
    repo, _ = _repo(tmp_path)
    _start(repo)
    monkeypatch.setattr(ops, "spawn", lambda *a, **k: None)
    rec, _ = ops.delegate(repo, "fix-env", "opus")
    commit_file(repo, "src/b.py", "b = 1\n", "in zone")
    _rec, delta = ops.reconcile(repo, rec.worker_id)
    assert delta["changed"] == ["src/b.py"] and not delta["outside_touch_zones"] and not delta["needs_reconcile"]
    assert not delta["contract_changed"]
    commit_file(repo, "docs/y.md", "# y\n", "out of zone")
    _rec, delta = ops.reconcile(repo, rec.worker_id)
    assert delta["outside_touch_zones"] == ["docs/y.md"] and delta["needs_reconcile"]


def _filed_review(prompt: str) -> tuple[Path, str]:
    """The path and template the chore reviewer prompt names, filled in."""
    path = Path(prompt.split("Write your verdict to\n\n`")[1].split("`")[0])
    template = prompt.split("```\n")[1].split("```")[0].replace("YYYY-MM-DD", "2026-11-03")
    return path, template


def test_review_delegate_takes_a_chore_started_with_review(tmp_path: Path) -> None:
    repo, _ = _repo(tmp_path)
    _start(repo, "plain")
    with pytest.raises(rd.DelegateError, match="without --review"):
        rd.delegate(repo, "plain", "opus")
    chore = _start(repo, "fix-env", "--review")
    # The record the reviewer prompt describes, filed as the reviewer would; the fake harness then runs the turn.
    head = git(repo, "rev-parse", "HEAD")
    path, template = _filed_review(chore_cli.chore_prompt(chore, "reviewer", "opus", repo, commit=head))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(template)
    run = rd.delegate(repo, "fix-env", "opus")
    assert "Write your verdict to" in (repo / "work" / "prompt-fix-env-reviewer-opus.md").read_text()
    assert run["state"] == "complete" and run["commit"] == git(repo, "rev-parse", "HEAD")
    chore_cli.close(repo, "fix-env", "done")
    assert "- opus: approve at " in (repo / "work" / "chores" / "fix-env.md").read_text()
    assert chore_cli.load_chore(repo, "fix-env")["closed_at"]
