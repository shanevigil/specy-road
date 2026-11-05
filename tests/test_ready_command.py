"""Tests for `specy-road ready`: the executor's READY hand-off, written from git."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.review_repo_helpers import diverge, git, make_review_repo
from tests.test_models_and_prompt import make_profile_repo

import argparse
import subprocess

from specy_road.bundled_scripts import review_cli, review_packet, role_prompt
from specy_road.cli import registered_agent_command_names
import specy_road.ready_run_checks as ready_run_checks
from specy_road.ready_run_checks import parse_run_argv, run_argv, run_check
from specy_road.review_files import load_ready, reviews_dir
from specy_road.review_gate_ready import add_ready_parser

# Examples named in ``--run-argv`` help (must stay in sync with ``add_ready_parser``).
RUN_ARGV_HELP_REFUSED = ("not-json", "[]", "{}", "[1]", '[""]')
RUN_ARGV_HELP_ACCEPTED = ('["echo", "ok"]', '["echo", ""]')
RUN_ARGV_PARSE_REFUSED = (*RUN_ARGV_HELP_REFUSED, '["", "tail"]')


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
    assert "first element is non-empty" in help_text
    for spec in RUN_ARGV_HELP_REFUSED:
        assert spec in help_text
    for spec in RUN_ARGV_HELP_ACCEPTED:
        assert spec in help_text


@pytest.mark.parametrize(
    "spec",
    RUN_ARGV_PARSE_REFUSED,
    ids=["invalid_json", "empty_array", "non_array", "non_string", "empty_program", "empty_program_with_tail"],
)
def test_parse_run_argv_refuses_invalid_shapes(spec: str) -> None:
    with pytest.raises(ValueError):
        parse_run_argv(spec)


@pytest.mark.parametrize(
    "argv",
    [
        ["echo", ""],
        ["echo", "   "],
        ["python3", "-c", "import sys; print(sys.argv[1:])", "héllo"],
    ],
    ids=["empty_later", "whitespace_later", "unicode_later"],
)
def test_parse_run_argv_accepts_later_empty_whitespace_or_unicode(argv: list[str]) -> None:
    spec = json.dumps(argv)
    assert parse_run_argv(spec) == argv


def test_ready_run_argv_passes_empty_later_argument(tmp_path: Path, monkeypatch, capsys) -> None:
    repo = make_review_repo(tmp_path)
    monkeypatch.chdir(repo)
    spec = json.dumps(["python3", "-c", "import sys; print(repr(sys.argv[1:]))", ""])
    capsys.readouterr()
    assert _cli("ready", "M1.1", "--model", "opus", "--run-argv", spec, "--verify", "ruff .=0",
                "--repo-root", str(repo)) == 0
    r = load_ready(reviews_dir(repo, "M1.1") / "READY-opus.md", "M1.1", "feature/rm-thing")
    assert r.ok, r.errors
    assert "['']" in r.data["verify"][-1]["tail"]


def test_ready_run_argv_help_accepted_example_runs(tmp_path: Path, monkeypatch, capsys) -> None:
    repo = make_review_repo(tmp_path)
    monkeypatch.chdir(repo)
    capsys.readouterr()
    assert _cli("ready", "M1.1", "--model", "opus", "--run-argv", RUN_ARGV_HELP_ACCEPTED[0], "--verify", "ruff .=0",
                "--repo-root", str(repo)) == 0
    r = load_ready(reviews_dir(repo, "M1.1") / "READY-opus.md", "M1.1", "feature/rm-thing")
    assert r.ok, r.errors
    assert r.data["verify"][-1]["tail"].strip() == "ok"


@pytest.mark.parametrize(
    "extra_args,expect_code,err_needle,side_effect",
    [
        pytest.param(["--run", ""], 1, "blank or whitespace-only", None, id="blank_run_alone"),
        pytest.param(["--run", "", "--run-argv", '["echo", "ok"]'], 1, "blank or whitespace-only", None,
                     id="blank_run_with_valid_argv"),
        pytest.param(["--run", "touch must-not-exist", "--run-argv", "[]"], 1, "non-empty JSON array",
                     "must-not-exist", id="valid_run_invalid_argv_before_execute"),
        pytest.param(["--run", "   "], 1, "blank or whitespace-only", None, id="whitespace_run_alone"),
        pytest.param(["--run", "echo shell-ok", "--run-argv", '["echo", "argv-ok"]', "--verify", "ruff .=0"], 0, None,
                     None, id="all_valid_mix"),
    ],
)
def test_ready_validates_every_run_and_run_argv_before_executing(
    tmp_path: Path, monkeypatch, capsys, extra_args: list[str], expect_code: int, err_needle: str | None,
    side_effect: str | None,
) -> None:
    repo = make_review_repo(tmp_path)
    monkeypatch.chdir(repo)
    capsys.readouterr()
    ready_path = reviews_dir(repo, "M1.1") / "READY-opus.md"
    code = _cli("ready", "M1.1", "--model", "opus", *extra_args, "--repo-root", str(repo))
    assert code == expect_code
    err = capsys.readouterr().err
    if err_needle:
        assert err_needle in err
        assert not ready_path.exists()
        if side_effect:
            assert not (repo / side_effect).exists()
    else:
        assert ready_path.exists()
        r = load_ready(ready_path, "M1.1", "feature/rm-thing")
        assert r.ok, r.errors
        assert any(v.get("tail") == "shell-ok" for v in r.data["verify"])
        assert any("argv-ok" in (v.get("tail") or "") for v in r.data["verify"])


@pytest.mark.parametrize(
    "case,expect_exit",
    [
        ("missing", 127),
        ("not_executable", 126),
        ("directory", 126),
        ("bad_interpreter", 127),
    ],
)
def test_run_argv_launch_os_errors(tmp_path: Path, case: str, expect_exit: int) -> None:
    if case == "missing":
        argv = ["/definitely/missing/program"]
    elif case == "not_executable":
        path = tmp_path / "noexec"
        path.write_text("not a program\n", encoding="utf-8")
        path.chmod(0o644)
        argv = [str(path)]
    elif case == "directory":
        argv = [str(tmp_path)]
    else:
        script = tmp_path / "bad.sh"
        script.write_text("#!/no/such/interpreter\n", encoding="utf-8")
        script.chmod(0o755)
        argv = [str(script)]
    row = run_argv(argv)
    assert row["exit"] == expect_exit
    assert row["tail"] and row["tail"] != "(no output)"
    assert "warning" not in row


def test_run_check_missing_command_exits_127_without_oserror() -> None:
    row = run_check("/definitely/missing/program")
    assert row["exit"] == 127
    assert "warning" not in row


def test_ready_run_argv_missing_executable_refuses_without_writing_ready(tmp_path: Path, capsys) -> None:
    repo = make_review_repo(tmp_path)
    capsys.readouterr()
    spec = json.dumps(["/definitely/missing/program"])
    ready_path = reviews_dir(repo, "M1.1") / "READY-opus.md"
    assert _cli("ready", "M1.1", "--model", "opus", "--run-argv", spec, "--repo-root", str(repo)) == 1
    err = capsys.readouterr().err
    assert "failing verifier" in err and "127" in err
    assert not ready_path.exists()


@pytest.mark.parametrize(
    "spec,index",
    [
        (json.dumps(["\x00"]), 0),
        (json.dumps(["echo", "\x00"]), 1),
    ],
    ids=["nul_in_program", "nul_in_later_argument"],
)
def test_parse_run_argv_refuses_embedded_nul(spec: str, index: int) -> None:
    with pytest.raises(ValueError, match=rf"argv\[{index}\] contains an embedded NUL"):
        parse_run_argv(spec)


def test_ready_run_argv_embedded_nul_refuses_before_any_live_run(tmp_path: Path, monkeypatch, capsys) -> None:
    repo = make_review_repo(tmp_path)
    monkeypatch.chdir(repo)
    marker = repo / "executed-before-invalid-argv"
    spec = json.dumps(["echo", "\u0000"])
    capsys.readouterr()
    ready_path = reviews_dir(repo, "M1.1") / "READY-opus.md"
    assert _cli("ready", "M1.1", "--model", "opus", "--run", f"touch {marker.name}", "--run-argv", spec,
                "--repo-root", str(repo)) == 1
    err = capsys.readouterr().err
    assert "embedded NUL" in err and "argv[1]" in err
    assert not marker.exists()
    assert not ready_path.exists()


def test_subprocess_launch_exception_becomes_failing_row(monkeypatch) -> None:
    def _boom(*_args, **_kwargs) -> subprocess.CompletedProcess[str]:
        raise TypeError("launch broke")

    monkeypatch.setattr(ready_run_checks.subprocess, "run", _boom)
    row = run_argv(["echo", "ok"])
    assert row["exit"] == 126 and "launch broke" in row["tail"]
    row = run_check("echo ok")
    assert row["exit"] == 126 and "launch broke" in row["tail"]

