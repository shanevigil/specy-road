"""Tests for `specy-road ready`: the executor's READY hand-off, written from git."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.review_repo_helpers import diverge, git, make_review_repo
from tests.test_models_and_prompt import make_profile_repo

import argparse

from specy_road.bundled_scripts import review_cli, review_packet, role_prompt
from specy_road.cli import registered_agent_command_names
from specy_road.ready_run_checks import parse_run_argv
from specy_road.review_files import load_ready, reviews_dir
from specy_road.review_gate_ready import add_ready_parser

# Examples named in ``--run-argv`` help (must stay in sync with ``add_ready_parser``).
RUN_ARGV_HELP_REFUSED = ("not-json", "[]", "{}", "[1]", '[""]')
RUN_ARGV_HELP_ACCEPTED = '["echo", "ok"]'


def _run_argv_help() -> str:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers()
    add_ready_parser(sub)
    ready = sub.choices["ready"]
    return next(a.help for a in ready._actions if a.dest == "run_argv")


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
    assert "Then write `READY-opus.md` with `specy-road ready M1.1 --model=opus --run '<cmd>' ...`" in step
    assert "the last lines of its output, which the reviewers' packet shows" in step
    assert "refuses a non-zero exit" in step and "`--red-green '<cmd>=<exit>'`" in step
    assert "handoff-ready.template.md" not in step


def test_ready_run_records_the_tail_and_the_packet_shows_it(tmp_path: Path, monkeypatch, capsys) -> None:
    repo = make_review_repo(tmp_path)
    monkeypatch.chdir(repo)   # --run runs from the current directory, as the executor would
    script = "import sys; print('noise', flush=True); print('12 passed', file=sys.stderr)"
    cmd = f'python3 -c "{script}"'
    assert _cli("ready", "M1.1", "--model", "opus", "--run", cmd, "--verify", "ruff .=0",
                "--repo-root", str(repo)) == 0
    assert f"running: {cmd}" in capsys.readouterr().err
    r = load_ready(reviews_dir(repo, "M1.1") / "READY-opus.md", "M1.1", "feature/rm-thing")
    assert r.ok, r.errors
    assert r.data["verify"] == [{"cmd": "ruff .", "exit": 0}, {"cmd": cmd, "exit": 0, "tail": "noise\n12 passed"}]
    text = review_packet.build_packet(repo, "M1.1", ref=None, verify_cmds=[])
    section = text.split(f"### `{cmd}` → exit 0", 1)[1].split("###", 1)[0]
    assert "noise\n12 passed" in section and "(no output recorded)" not in section
    assert "### `ruff .` → exit 0\n\n```\n(no output recorded)" in text   # --verify keeps no output


def test_ready_run_refuses_a_failing_command_with_its_tail_and_writes_nothing(tmp_path: Path, monkeypatch,
                                                                              capsys) -> None:
    repo = make_review_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    capsys.readouterr()
    cmd = "python3 -c \"import sys; print('1 failed'); sys.exit(3)\""
    assert _cli("ready", "M1.1", "--model", "opus", "--run", cmd, "--repo-root", str(repo)) == 1
    err = capsys.readouterr().err
    assert f"failing verifier: `{cmd}` exited 3; its last lines:\n1 failed" in err and "--red-green" in err
    assert not (reviews_dir(repo, "M1.1") / "READY-opus.md").exists()
    git(repo, "checkout", "-q", "-b", "feature/other")   # a cheap refusal comes before any command runs
    assert _cli("ready", "M1.1", "--model", "opus", "--run", "touch ran", "--repo-root", str(repo)) == 1
    assert "not the registered" in capsys.readouterr().err and not (tmp_path / "ran").exists()


def test_ready_run_warns_when_exit_zero_but_tail_shows_cannot_open(tmp_path: Path, monkeypatch, capsys) -> None:
    """A loop whose middle step fails with cannot open but the last step succeeds still exits 0."""
    repo = make_review_repo(tmp_path)
    monkeypatch.chdir(repo)
    capsys.readouterr()
    cmd = (
        'bash -c \'for step in fail ok; do '
        'if [ "$step" = fail ]; then sh -c ": < /no/such/file" 2>&1 || true; else echo all_ok; fi; done\''
    )
    assert _cli("ready", "M1.1", "--model", "opus", "--run", cmd, "--verify", "ruff .=0",
                "--repo-root", str(repo)) == 0
    err = capsys.readouterr().err
    r = load_ready(reviews_dir(repo, "M1.1") / "READY-opus.md", "M1.1", "feature/rm-thing")
    assert r.ok, r.errors
    run_row = r.data["verify"][-1]
    assert run_row["exit"] == 0 and "cannot open" in run_row["warning"]
    assert f"warning: {run_row['warning']}" in err
    text = review_packet.build_packet(repo, "M1.1", ref=None, verify_cmds=[])
    assert f"**Warning:** {run_row['warning']}" in text
    assert "all_ok" in text


def test_ready_run_clean_tail_has_no_warning(tmp_path: Path, monkeypatch, capsys) -> None:
    repo = make_review_repo(tmp_path)
    monkeypatch.chdir(repo)
    capsys.readouterr()
    assert _cli("ready", "M1.1", "--model", "opus", "--run", "echo clean", "--verify", "ruff .=0",
                "--repo-root", str(repo)) == 0
    err = capsys.readouterr().err
    r = load_ready(reviews_dir(repo, "M1.1") / "READY-opus.md", "M1.1", "feature/rm-thing")
    assert r.ok and "warning" not in r.data["verify"][-1]
    assert "warning:" not in err
    text = review_packet.build_packet(repo, "M1.1", ref=None, verify_cmds=[])
    section = text.split("### `echo clean` → exit 0", 1)[1].split("###", 1)[0]
    assert "**Warning:**" not in section


def test_ready_run_argv_without_shell_and_refuses_bad_json(tmp_path: Path, monkeypatch, capsys) -> None:
    repo = make_review_repo(tmp_path)
    monkeypatch.chdir(repo)
    script = "import sys; print(sys.argv[1:])"
    argv_json = json.dumps(["python3", "-c", script, "$f has spaces"])
    capsys.readouterr()
    assert _cli("ready", "M1.1", "--model", "opus", "--run-argv", argv_json, "--verify", "ruff .=0",
                "--repo-root", str(repo)) == 0
    r = load_ready(reviews_dir(repo, "M1.1") / "READY-opus.md", "M1.1", "feature/rm-thing")
    assert r.ok, r.errors
    row = r.data["verify"][-1]
    assert row["cmd"] == 'python3 -c \'import sys; print(sys.argv[1:])\' \'$f has spaces\''
    assert "$f has spaces" in row["tail"]
    before_verify = r.data["verify"]
    capsys.readouterr()
    assert _cli("ready", "M1.1", "--model", "opus", "--run-argv", "not-json", "--repo-root", str(repo)) == 1
    assert "not valid JSON" in capsys.readouterr().err
    assert load_ready(reviews_dir(repo, "M1.1") / "READY-opus.md", "M1.1", "feature/rm-thing").data["verify"] == before_verify
    capsys.readouterr()
    assert _cli("ready", "M1.1", "--model", "opus", "--run-argv", "[]", "--repo-root", str(repo)) == 1
    assert "non-empty JSON array" in capsys.readouterr().err


def test_run_argv_help_examples_match_parse_run_argv() -> None:
    help_text = _run_argv_help()
    assert "not a non-empty JSON array of strings" in help_text
    for spec in RUN_ARGV_HELP_REFUSED:
        assert spec in help_text
        with pytest.raises(ValueError):
            parse_run_argv(spec)
    assert RUN_ARGV_HELP_ACCEPTED in help_text
    assert parse_run_argv(RUN_ARGV_HELP_ACCEPTED) == ["echo", "ok"]


def test_ready_run_argv_help_accepted_example_runs(tmp_path: Path, monkeypatch, capsys) -> None:
    repo = make_review_repo(tmp_path)
    monkeypatch.chdir(repo)
    capsys.readouterr()
    assert _cli("ready", "M1.1", "--model", "opus", "--run-argv", RUN_ARGV_HELP_ACCEPTED, "--verify", "ruff .=0",
                "--repo-root", str(repo)) == 0
    r = load_ready(reviews_dir(repo, "M1.1") / "READY-opus.md", "M1.1", "feature/rm-thing")
    assert r.ok, r.errors
    assert r.data["verify"][-1]["tail"].strip() == "ok"
