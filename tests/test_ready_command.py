"""Tests for `specy-road ready`: the executor's READY hand-off, written from git."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.review_repo_helpers import diverge, git, make_review_repo
from tests.test_models_and_prompt import make_profile_repo

from specy_road.bundled_scripts import review_cli, role_prompt
from specy_road.cli import registered_agent_command_names
from specy_road.review_files import load_ready, reviews_dir


def _cli(*args: str) -> int:
    with pytest.raises(SystemExit) as e:
        review_cli.main(list(args))
    return e.value.code


def _status(repo: Path, capsys) -> dict:
    capsys.readouterr()
    _cli("handoff", "status", "M1.1", "--json", "--repo-root", str(repo))
    return json.loads(capsys.readouterr().out)["nodes"][0]


def test_ready_writes_a_valid_hand_off_from_a_worktree(tmp_path: Path, capsys) -> None:
    repo = make_review_repo(tmp_path)
    git(repo, "checkout", "-q", "dev")
    wt = tmp_path / "wt"
    git(repo, "worktree", "add", "-q", str(wt), "feature/rm-thing")
    assert "ready" in registered_agent_command_names()["specy-road"]
    assert _cli("ready", "M1.1", "--model", "opus", "--verify", 'pytest -k "a=b"=0', "--verify", "ruff .=0",
                "--red-green", "pytest tests/test_a.py=1", "--repo-root", str(wt)) == 0
    path = reviews_dir(repo, "M1.1") / "READY-opus.md"   # the main checkout's directory
    r = load_ready(path, "M1.1", "feature/rm-thing")
    assert r.ok, r.errors
    assert r.data["agent"] == "opus" and r.data["commit"] == git(wt, "rev-parse", "HEAD")
    assert r.data["base"] == git(repo, "rev-parse", "dev")
    assert r.data["changed_paths"] == ["docs/x.md", "src/a.py"]
    assert r.data["verify"] == [{"cmd": 'pytest -k "a=b"', "exit": 0}, {"cmd": "ruff .", "exit": 0}]
    assert "## Red-green evidence" in r.body and "- `pytest tests/test_a.py` exited 1" in r.body
    st = _status(wt, capsys)
    assert st["state"] == "in-review" and st["ready"][0]["errors"] == []
    assert not any("exited" in p or "verif" in p for p in st["problems"])   # red-green evidence does not gate


def test_ready_refuses_a_failing_verifier_and_writes_nothing(tmp_path: Path, capsys) -> None:
    repo = make_review_repo(tmp_path)
    capsys.readouterr()
    assert _cli("ready", "M1.1", "--model", "opus", "--verify", "pytest=0", "--verify", "pytest tests/t.py=1",
                "--repo-root", str(repo)) == 1
    err = capsys.readouterr().err
    assert "failing verifier: `pytest tests/t.py` exited 1" in err and "--red-green" in err
    assert not (reviews_dir(repo, "M1.1") / "READY-opus.md").exists()


def test_ready_refuses_a_bad_spec_and_an_unregistered_branch(tmp_path: Path, capsys) -> None:
    repo = make_review_repo(tmp_path)
    capsys.readouterr()
    assert _cli("ready", "M1.1", "--model", "opus", "--verify", "pytest", "--repo-root", str(repo)) == 1
    assert "expected '<cmd>=<exit>'" in capsys.readouterr().err
    git(repo, "checkout", "-q", "-b", "feature/other")
    assert _cli("ready", "M1.1", "--model", "opus", "--verify", "pytest=0", "--repo-root", str(repo)) == 1
    assert "not the registered 'feature/rm-thing'" in capsys.readouterr().err
    assert not reviews_dir(repo, "M1.1").exists()


@pytest.mark.parametrize("case", ["clean", "bookkeeping", "code"])
def test_ready_warns_when_the_trial_merge_handoff_status_makes_conflicts(tmp_path: Path, capsys, case: str) -> None:
    repo = make_review_repo(tmp_path)
    path = diverge(repo, case)
    capsys.readouterr()
    assert _cli("ready", "M1.1", "--model", "opus", "--verify", "pytest=0", "--repo-root", str(repo)) == 0
    err = capsys.readouterr().err
    assert (reviews_dir(repo, "M1.1") / "READY-opus.md").exists()   # a warning, not a refusal
    st = _status(repo, capsys)
    if case == "code":
        assert st["trial_merge"]["blocking"] == [path]
        assert f"warning: refs/heads/dev is 1 commit(s) ahead and a trial merge conflicts on {path}" in err
        assert "Before handing off: run `git merge refs/heads/dev`" in err
    elif case == "bookkeeping":
        assert err == (f"note: a trial merge with refs/heads/dev conflicts on bookkeeping only ({path}), "
                       "which does not block review\n")
    else:
        assert st["trial_merge"] is None and err == ""


def test_handoff_status_still_validates_a_hand_written_ready(tmp_path: Path, capsys) -> None:
    repo = make_review_repo(tmp_path)
    d = reviews_dir(repo, "M1.1")
    d.mkdir(parents=True)
    (d / "READY-composer.md").write_text("node_id: M1.1\nagent: composer\n")   # no front matter
    st = _status(repo, capsys)
    assert st["state"] == "waiting"
    assert st["ready"][0]["errors"] == ["missing YAML front matter (--- … ---) at the top of the file"]


def test_executor_prompt_tells_the_executor_to_write_ready_with_the_command(tmp_path: Path) -> None:
    text = role_prompt.build_prompt(make_profile_repo(tmp_path), "M1.1", role="executor", model="opus")[0]
    step = next(line for line in text.splitlines() if line.startswith("4. "))
    assert "Then write `READY-opus.md` with `specy-road ready M1.1 --model=opus --verify '<cmd>=<exit>' ...`" in step
    assert "refuses a non-zero `--verify`" in step and "`--red-green '<cmd>=<exit>'`" in step
    assert "handoff-ready.template.md" not in step
