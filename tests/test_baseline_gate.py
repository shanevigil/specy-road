"""Tests for the pre-pickup baseline gate (``--baseline-cmd`` / ``baseline_cmd``)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from specy_road.bundled_scripts.do_next_available import run_baseline_gate
from specy_road.bundled_scripts.grind_session_args import (
    parse_grind_session_args,
    pickup_args,
)
from specy_road.bundled_scripts.grind_session_events import EXIT_PICKUP_FAILED
from specy_road.git_workflow_config import resolve_baseline_cmd, validate_git_workflow_dict
from tests.test_grind_session import _Harness, _plan, _run

_GW = "version: 1\nintegration_branch: main\nremote: origin\n"


def _write_gw(root: Path, extra: str = "") -> None:
    (root / "roadmap").mkdir(exist_ok=True)
    (root / "roadmap" / "git-workflow.yaml").write_text(_GW + extra, encoding="utf-8")


def _git_repo(root: Path) -> Path:
    for args in (
        ["init", "-q", "-b", "main"],
        ["config", "user.email", "t@example.com"],
        ["config", "user.name", "t"],
    ):
        subprocess.run(["git", *args], cwd=root, check=True)
    (root / "tracked.txt").write_text("x\n", encoding="utf-8")
    subprocess.run(["git", "add", "tracked.txt"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=root, check=True)
    return root


# ---------------------------------------------------------------------------
# Resolution: CLI > git-workflow.yaml > none
# ---------------------------------------------------------------------------


def test_schema_accepts_baseline_cmd() -> None:
    data = {"version": 1, "integration_branch": "main", "remote": "origin",
            "baseline_cmd": "make test"}
    assert validate_git_workflow_dict(data) is None


def test_yaml_sets_the_default(tmp_path) -> None:
    _write_gw(tmp_path, "baseline_cmd: make test\n")
    assert resolve_baseline_cmd(tmp_path, cli=None) == "make test"


def test_cli_wins_over_yaml(tmp_path) -> None:
    _write_gw(tmp_path, "baseline_cmd: make test\n")
    assert resolve_baseline_cmd(tmp_path, cli="pytest -q") == "pytest -q"


def test_empty_cli_turns_the_yaml_default_off(tmp_path) -> None:
    _write_gw(tmp_path, "baseline_cmd: make test\n")
    assert resolve_baseline_cmd(tmp_path, cli="") is None


def test_no_config_means_no_baseline(tmp_path) -> None:
    assert resolve_baseline_cmd(tmp_path, cli=None) is None


# ---------------------------------------------------------------------------
# The gate itself, in a real repository
# ---------------------------------------------------------------------------


def test_passing_baseline_returns(tmp_path, capsys) -> None:
    root = _git_repo(tmp_path)
    run_baseline_gate(root, "main", cli="true", warn_only=False)
    assert "baseline on main: true" in capsys.readouterr().out


def test_failing_baseline_refuses(tmp_path, capsys) -> None:
    root = _git_repo(tmp_path)
    with pytest.raises(SystemExit) as ei:
        run_baseline_gate(root, "main", cli="exit 3", warn_only=False)
    assert ei.value.code == 1
    err = capsys.readouterr().err
    assert "baseline failed on 'main' (exit 3)" in err
    assert "--baseline-warn" in err


def test_baseline_warn_downgrades_a_failure(tmp_path, capsys) -> None:
    root = _git_repo(tmp_path)
    run_baseline_gate(root, "main", cli="exit 3", warn_only=True)
    assert "warning: baseline failed on 'main' (exit 3)" in capsys.readouterr().err


def test_baseline_that_writes_is_refused_even_when_warned(tmp_path, capsys) -> None:
    """A change left behind would ride the claim onto the feature branch."""
    root = _git_repo(tmp_path)
    with pytest.raises(SystemExit) as ei:
        run_baseline_gate(root, "main", cli="echo y >> tracked.txt", warn_only=True)
    assert ei.value.code == 1
    err = capsys.readouterr().err
    assert "must only check" in err
    assert "working tree clean -> changed outside work/" in err


def test_baseline_that_commits_is_refused(tmp_path, capsys) -> None:
    """A clean tree is not enough: a new commit would be pushed with the claim."""
    root = _git_repo(tmp_path)
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True,
                          text=True, check=True).stdout.strip()
    with pytest.raises(SystemExit) as ei:
        run_baseline_gate(root, "main", cli="git commit -q --allow-empty -m sneaky",
                          warn_only=False)
    assert ei.value.code == 1
    err = capsys.readouterr().err
    assert f"HEAD {head} -> " in err
    assert "branch refs/" not in err and "working tree" not in err


@pytest.mark.parametrize("cmd, moved", [
    ("git checkout -q -b elsewhere", "branch refs/heads/main -> refs/heads/elsewhere"),
    ("git checkout -q --detach", "branch refs/heads/main -> (detached)"),
])
def test_baseline_that_switches_ref_is_refused(tmp_path, capsys, cmd, moved) -> None:
    root = _git_repo(tmp_path)
    with pytest.raises(SystemExit) as ei:
        run_baseline_gate(root, "main", cli=cmd, warn_only=True)
    assert ei.value.code == 1
    assert moved in capsys.readouterr().err


def test_baseline_may_write_under_work(tmp_path) -> None:
    root = _git_repo(tmp_path)
    run_baseline_gate(root, "main", cli="mkdir -p work && touch work/log", warn_only=False)


def test_yaml_baseline_runs_without_a_flag(tmp_path, capsys) -> None:
    root = _git_repo(tmp_path)
    _write_gw(root, "baseline_cmd: exit 2\n")
    subprocess.run(["git", "add", "roadmap"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "gw"], cwd=root, check=True)
    with pytest.raises(SystemExit):
        run_baseline_gate(root, "main", cli=None, warn_only=False)


# ---------------------------------------------------------------------------
# grind-session: passed through to every pickup, including --step pickup
# ---------------------------------------------------------------------------


def test_grind_passes_baseline_flags_to_pickup() -> None:
    args = parse_grind_session_args(
        ["--baseline-cmd", "make test", "--baseline-warn", "--repo-root", "/tmp/x"]
    )
    out = pickup_args(args, Path("/tmp/x"))
    assert out[out.index("--baseline-cmd") + 1] == "make test"
    assert "--baseline-warn" in out


def test_grind_forwards_an_empty_baseline_to_turn_the_default_off() -> None:
    args = parse_grind_session_args(["--baseline-cmd", "", "--repo-root", "/tmp/x"])
    out = pickup_args(args, Path("/tmp/x"))
    assert out[out.index("--baseline-cmd") + 1] == ""


def test_grind_without_baseline_flags_forwards_none() -> None:
    out = pickup_args(parse_grind_session_args(["--repo-root", "/tmp/x"]), Path("/tmp/x"))
    assert "--baseline-cmd" not in out and "--baseline-warn" not in out


def test_grind_step_pickup_passes_baseline_through(monkeypatch, capsys) -> None:
    h = _Harness(monkeypatch, [_plan(ready=["M1.1"])], pickup_rc=1)
    monkeypatch.setenv("SPECY_ROAD_GRIND_SESSION", "1")  # run_session sets it; undo after
    code = _run(["--step", "pickup", "--on-complete", "merge", "--baseline-cmd",
                 "make test", "--json", "--repo-root", "/tmp/x"])
    assert code == EXIT_PICKUP_FAILED  # a refused baseline is a refused pickup
    pickup = h.cli_calls[0]
    assert pickup[pickup.index("--baseline-cmd") + 1] == "make test"
