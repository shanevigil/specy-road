"""M15.3: ``prompt --channel cli`` launches nothing without ``--run``; a reviewer run uses the roster entry's model,
runs in the leaf's worktree, and a model the harness did not report as rostered is flagged and does not count."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from tests.review_delegate_helpers import fake_reviewer_run
from tests.review_repo_helpers import NODE, git, review_output, review_text
from tests.test_models_and_prompt import OPUS, commit_profile, make_profile_repo, run_main

from specy_road import review_files as rf
from specy_road.bundled_scripts import review_cli, role_prompt
from specy_road.model_profiles import load_profile
from specy_road.review_eligible import reviewer_eligibility
from specy_road.review_gate import evaluate_gate
from specy_road.review_model_check import MISMATCH_REASON, check, normalise, reported_model


def _repo(tmp_path: Path, entry: str = "    harness: claude-code\n", api_id: str | None = None,
          leaf: bool = False) -> tuple[Path, Path]:
    """``(main checkout, leaf checkout)``: the roster's ``opus`` reviewer gets ``entry``'s lines; with ``leaf`` the
    main checkout is on the integration branch and the claimed branch is in a linked worktree, else the main
    checkout has the claimed branch checked out and is the leaf's checkout."""
    repo = make_profile_repo(tmp_path)
    roster = repo / "roadmap" / "orchestration.yaml"
    roster.write_text(roster.read_text().replace("    roles: [coordinator, executor, reviewer]\n",
                                                 "    roles: [coordinator, executor, reviewer]\n" + entry))
    if api_id is not None:
        prof = repo / "model-profiles" / "anthropic-claude" / OPUS.name
        prof.write_text(prof.read_text().replace("api_id: claude-opus-5-5", f"api_id: {api_id}"))
    if entry or api_id is not None:
        commit_profile(repo)
    d = rf.reviews_dir(repo, "M1.1")
    d.mkdir(parents=True)
    (d / rf.PACKET_NAME).write_text("# Review packet: `M1.1`\n")
    if not leaf:
        return repo, repo
    git(repo, "checkout", "-q", "dev")
    git(repo, "worktree", "add", "-q", str(tmp_path / "leaf"), "feature/rm-thing")
    return repo, (tmp_path / "leaf").resolve()


@pytest.fixture
def started(monkeypatch) -> list:
    """Every process started that is not git (the harness, a shell command, the roster's preflight)."""
    out: list = []
    real = subprocess.Popen

    class Recorded(real):   # type: ignore[misc, valid-type]
        def __init__(self, args, *a, **kw):
            prog = args if isinstance(args, str) else args[0]
            if Path(str(prog)).name != "git":
                out.append(args)
            super().__init__(args, *a, **kw)

    monkeypatch.setattr(subprocess, "Popen", Recorded)
    return out


def _prompt(repo: Path, *args: str) -> int:
    return run_main(role_prompt, "M1.1", "--model", "opus", *args, "--repo-root", str(repo))


def _result(answer: dict, model: str | None = None) -> list[str]:
    init = [json.dumps({"type": "system", "subtype": "init", "session_id": "s", "model": model})] if model else []
    return init + [json.dumps({"type": "result", "subtype": "success", "result": "done", "structured_output": answer})]


# --- A1: nothing launches without --run ----------------------------------------------------------------------------

@pytest.mark.parametrize("role", ["executor", "reviewer", "rca"])
def test_channel_cli_without_run_writes_the_prompt_prints_the_command_and_starts_nothing(
        tmp_path: Path, capsys, started: list, role: str) -> None:
    repo, _ = _repo(tmp_path, "    harness: claude-code\n    preflight: touch PREFLIGHT-RAN\n")
    extra = ["--force", "--reason", "coordinator asked"] if role == "rca" else []
    if role == "rca":   # an analysis needs a filed review round to analyse
        notes = tmp_path / "notes.md"
        notes.write_text(review_text(git(repo, "rev-parse", "HEAD"), model="sol", verdict="block", a1="fail"))
        assert run_main(review_cli, "review", "record", "M1.1", "--model", "sol", "--verdict", "block",
                        "--file", str(notes), "--repo-root", str(repo)) == 0
    assert _prompt(repo, "--role", role, "--channel", "cli", *extra) == 0
    assert started == [] and not (repo / "PREFLIGHT-RAN").exists()
    assert (repo / "work" / f"prompt-M1.1-{role}-opus.md").is_file()
    err = capsys.readouterr().err
    assert "would run" in err and "add --run to launch it" in err
    if role == "reviewer":
        assert "claude -p" in err and "--model claude-opus-5-5" in err and f"in {repo}" in err
        assert not list(rf.reviews_dir(repo, "M1.1").glob("RUN-*"))   # no run record either
        assert "**specy-road files your record.**" not in (repo / "work" / "prompt-M1.1-reviewer-opus.md").read_text()


def test_help_says_only_run_launches(capsys) -> None:
    with pytest.raises(SystemExit):
        role_prompt.main(["--help"])
    text = " ".join(capsys.readouterr().out.split())
    assert "launches nothing without --run" in text and "the only flag that starts a process" in text


def test_run_needs_channel_cli(tmp_path: Path) -> None:
    repo, _ = _repo(tmp_path)
    with pytest.raises(SystemExit) as e:
        role_prompt.main(["M1.1", "--model", "opus", "--role", "executor", "--run", "--repo-root", str(repo)])
    assert e.value.code == 2


# --- A2: the reviewer's command comes from the roster entry ---------------------------------------------------------

def test_a_reviewer_without_channels_cli_never_falls_back_to_access_cli(tmp_path: Path, capsys, started: list) -> None:
    repo, _ = _repo(tmp_path, entry="")   # no harness: the profile's access.cli (`claude -p "<prompt>"`) is an example
    assert _prompt(repo, "--role", "reviewer", "--channel", "cli", "--run") == 1
    assert started == [] and not list(rf.reviews_dir(repo, "M1.1").glob("RUN-*"))
    assert "needs a roster channels.cli; the profile's access.cli is never run for a reviewer" in capsys.readouterr().err


def test_a_cursor_reviewer_uses_its_read_only_command_with_the_entrys_model(tmp_path: Path, capsys) -> None:
    repo, _ = _repo(tmp_path, "    harness: cursor\n")
    assert _prompt(repo, "--role", "reviewer", "--channel", "cli") == 0
    err = capsys.readouterr().err
    assert "agent -p --output-format stream-json --mode ask --trust --model claude-opus-5-5" in err
    assert "--force" not in err


def test_a_model_with_no_api_id_is_refused_before_launch(tmp_path: Path, capsys, started: list) -> None:
    repo, _ = _repo(tmp_path, api_id="unknown")
    assert _prompt(repo, "--role", "reviewer", "--channel", "cli", "--run") == 1
    assert started == []
    assert "resolves to no API model id" in capsys.readouterr().err


@pytest.mark.parametrize("flag", ["--force", "--yolo", "--dangerously-skip-permissions"])
def test_a_custom_reviewer_command_with_a_bypass_flag_is_refused(tmp_path: Path, capsys, started: list,
                                                                 flag: str) -> None:
    repo, _ = _repo(tmp_path, f'    harness: claude-code\n    channels: {{cli: "agent -p {flag} {{prompt}}"}}\n')
    assert _prompt(repo, "--role", "reviewer", "--channel", "cli", "--run") == 1
    assert started == []
    assert f"passes {flag}" in capsys.readouterr().err


# --- A3: the reviewer runs in the leaf's own worktree ---------------------------------------------------------------

def test_a_reviewer_run_from_the_main_checkout_launches_in_the_leafs_worktree(tmp_path: Path, monkeypatch,
                                                                              capsys) -> None:
    repo, leaf = _repo(tmp_path, leaf=True)
    assert git(repo, "branch", "--show-current") == "dev"
    answer = review_output(git(repo, "rev-parse", "feature/rm-thing"), model="opus")
    calls = fake_reviewer_run(monkeypatch, _result(answer, "claude-opus-5-5"))
    assert _prompt(repo, "--role", "reviewer", "--channel", "cli", "--run") == 0
    call = next(c for c in calls if list(c["cmd"][:2]) == ["claude", "-p"])
    assert Path(call["cwd"]).resolve() == leaf != repo.resolve()
    rec = rf.load_review(rf.review_path(repo, "M1.1", "opus"), ["A1", "A2"])
    assert rec.ok and rec.data["harness_model"] == "claude-opus-5-5" and "model_mismatch" not in rec.data


def test_a_reviewer_run_with_no_leaf_worktree_is_refused(tmp_path: Path, capsys, started: list) -> None:
    repo, leaf = _repo(tmp_path, leaf=True)
    git(repo, "worktree", "remove", str(leaf))
    assert _prompt(repo, "--role", "reviewer", "--channel", "cli", "--run") == 1
    assert started == []
    err = capsys.readouterr().err
    assert "no worktree has feature/rm-thing checked out" in err and "--worktree PATH" in err
    assert "git worktree add work/.worktrees/thing feature/rm-thing" in err


def test_worktree_overrides_where_a_reviewer_runs(tmp_path: Path, monkeypatch) -> None:
    repo, leaf = _repo(tmp_path, leaf=True)
    other = tmp_path / "other"
    git(repo, "worktree", "add", "-q", "--detach", str(other), "feature/rm-thing")
    answer = review_output(git(repo, "rev-parse", "feature/rm-thing"), model="opus")
    calls = fake_reviewer_run(monkeypatch, _result(answer, "claude-opus-5-5"))
    assert _prompt(repo, "--role", "reviewer", "--channel", "cli", "--run", "--worktree", str(other)) == 0
    call = next(c for c in calls if list(c["cmd"][:2]) == ["claude", "-p"])
    assert Path(call["cwd"]).resolve() == other.resolve()


# --- A4: the harness-reported model -------------------------------------------------------------------------------

@pytest.mark.parametrize("reported, want", [
    ("claude-opus-5-5", "match"),          # the API id
    ("Claude Opus 5.5", "match"),          # the profile's display name, other case and separators
    ("gpt-5.6-sol", "mismatch"),
    (None, "unreported"),
])
def test_check_compares_the_reported_model_with_the_roster_entry(reported: str | None, want: str) -> None:
    assert check(reported, {"id": "opus"}, load_profile(OPUS)) == want


def test_reported_model_reads_the_first_init_event() -> None:
    lines = ['{"type": "system", "subtype": "init", "model": "Claude Opus 5.5"}',
             '{"type": "system", "subtype": "init", "model": "forged"}']
    assert reported_model(lines) == "Claude Opus 5.5" and reported_model("plain text\n") is None
    assert normalise("Claude Opus 5.5") == "claude-opus-5-5"


def test_a_mismatched_model_is_filed_flagged_and_excluded_from_the_gate(tmp_path: Path, monkeypatch, capsys) -> None:
    repo, leaf = _repo(tmp_path, leaf=True)
    head = git(repo, "rev-parse", "feature/rm-thing")
    fake_reviewer_run(monkeypatch, _result(review_output(head, model="opus"), "gpt-5.6-sol"))
    assert _prompt(repo, "--role", "reviewer", "--channel", "cli", "--run") == 0
    assert f"warning: {MISMATCH_REASON}" in capsys.readouterr().err
    rec = rf.load_review(rf.review_path(repo, "M1.1", "opus"), ["A1", "A2"])
    assert rec.ok and rec.data["harness_model"] == "gpt-5.6-sol" and rec.data["model_mismatch"] is True
    gate = evaluate_gate(leaf, NODE, head)
    assert not gate.approvals and not gate.passed
    assert any(MISMATCH_REASON in why for r, why in gate.ineligible if r.data["model"] == "opus")
    row = next(r for r in reviewer_eligibility(leaf, NODE, gate, "feature/rm-thing") if r["model"] == "opus")
    assert not row["eligible"] and MISMATCH_REASON in row["reason"]


def test_an_unreported_model_is_a_warning_and_the_record_counts(tmp_path: Path, monkeypatch, capsys) -> None:
    repo, leaf = _repo(tmp_path, leaf=True)
    head = git(repo, "rev-parse", "feature/rm-thing")
    fake_reviewer_run(monkeypatch, _result(review_output(head, model="opus")))
    assert _prompt(repo, "--role", "reviewer", "--channel", "cli", "--run") == 0
    assert "warning: the harness reported no model" in capsys.readouterr().err
    rec = rf.load_review(rf.review_path(repo, "M1.1", "opus"), ["A1", "A2"])
    assert rec.ok and "harness_model" not in rec.data and "model_mismatch" not in rec.data
    assert [a.model for a in evaluate_gate(leaf, NODE, head).approvals] == ["opus"]
