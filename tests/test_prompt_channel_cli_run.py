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
from specy_road.bundled_scripts.role_prompt_cli import bypass_problem
from specy_road.review_model_check import MISMATCH_REASON, check, check_run, normalise, reported_models


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


def _result(answer: dict, init: str | None = None, **result: object) -> list[str]:
    """A Claude-style stream: an init event naming ``init`` (none when ``None``), then the result, with ``result``'s
    extra fields (a ``model`` or ``modelUsage`` reported only there)."""
    first = [json.dumps({"type": "system", "subtype": "init", "session_id": "s", "model": init})] if init else []
    return first + [json.dumps({"type": "result", "subtype": "success", "result": "done", "structured_output": answer,
                               **result})]


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


@pytest.mark.parametrize("entry", [
    "    harness: claude-code\n",                                                   # the adapter's command
    '    harness: claude-code\n    channels: {cli: "claude -p {prompt}"}\n',       # a custom command
])
def test_a_model_with_no_api_id_is_refused_before_launch_on_every_command(tmp_path: Path, capsys, started: list,
                                                                          entry: str) -> None:
    repo, _ = _repo(tmp_path, entry, api_id="unknown")
    assert _prompt(repo, "--role", "reviewer", "--channel", "cli", "--run") == 1
    assert started == [] and not list(rf.reviews_dir(repo, "M1.1").glob("RUN-*"))
    assert NO_MODEL in capsys.readouterr().err
    assert _prompt(repo, "--role", "reviewer", "--channel", "cli") == 1   # the dry run refuses it the same way


@pytest.mark.parametrize("cli, flag", [
    ("agent -p --force; cat {prompt}", "--force"),        # a separator glued to the flag
    ("agent -p --force&&x {prompt}", "--force"),
    ("(agent -p --force) {prompt}", "--force"),
    ("(--force)", "--force"),
    ("agent -p '--force' {prompt}", "--force"),           # quoting the whole flag still passes it to the program
    ("agent --yolo=true|cat {prompt}", "--yolo"),
    ("claude -p --dangerously-skip-permissions>log {prompt}", "--dangerously-skip-permissions"),
    ("agent -p --for\\\nce {prompt}", "--force"),           # a line continuation inside the flag
    ('agent -p "--for\\\nce" {prompt}', "--force"),         # ... inside double quotes, where sh joins it too
    ("agent -p '--for\\\nce' {prompt}", "--force"),         # ... inside single quotes: sh keeps it; refused anyway
    ("agent -p a#b --force {prompt}", "--force"),           # '#' inside a word starts no comment
    ("agent -p {prompt} # no --force here", "--force"),     # a flag in a comment: refused anyway
])
def test_bypass_flags_are_found_as_sh_reads_its_words(cli: str, flag: str) -> None:
    assert f"passes {flag}," in bypass_problem(cli)


@pytest.mark.parametrize("cli", [
    'agent -p "never pass --force here" {prompt}',        # a quoted argument that only mentions the flag
    "agent -p --forceful {prompt}",                        # another flag that merely starts the same way
    "agent -p --mode ask {prompt}",
])
def test_text_that_only_mentions_a_bypass_flag_is_not_one(cli: str) -> None:
    assert bypass_problem(cli) == ""


def test_a_command_the_tokenizer_cannot_split_is_refused() -> None:
    assert "cannot be split into words" in bypass_problem("agent -p \"--force {prompt}")


@pytest.mark.parametrize("cli, flag", [
    ("agent -p --force {prompt}", "--force"),               # the CLI path; flag shapes are the rule table's
    ("agent -p --for\\\nce {prompt}", "--force"),           # split across a line continuation, end to end
])
def test_a_custom_reviewer_command_with_a_bypass_flag_is_refused(tmp_path: Path, capsys, started: list,
                                                                 cli: str, flag: str) -> None:
    block = "".join(f"        {line}\n" for line in cli.split("\n"))   # a YAML literal block keeps the backslash-newline
    repo, _ = _repo(tmp_path, f"    harness: claude-code\n    channels:\n      cli: |-\n{block}")
    assert _prompt(repo, "--role", "reviewer", "--channel", "cli", "--run") == 1
    assert started == [] and not list(rf.reviews_dir(repo, "M1.1").glob("RUN-*"))
    assert f"passes {flag}," in capsys.readouterr().err


NO_MODEL = "resolves to no API model id"
REFUSED_REVIEWERS = [   # M21.21: (roster entry lines, profile api_id, reason) refused alike by every entry point
    ("    harness: cursor\n    channels: {cli: 'agent --force {prompt}'}\n", None, "passes --force, which lets it"),
    ("    harness: claude-code\n    channels: {cli: 'claude -p --yolo {prompt}'}\n", None, "passes --yolo, which"),
    ("    harness: claude-code\n    channels:\n      cli: |-\n        agent -p --for\\\n        ce {prompt}\n",
     None, "passes --force, which lets it write"),   # a YAML literal block keeps the line continuation
    ("", None, "a generic reviewer needs a roster channels.cli; the profile's access.cli is never run for a reviewer"),
    ("    harness: claude-code\n", "unknown", NO_MODEL),                        # no model to pass the harness
    ("    harness: claude-code\n    routing: dynamic\n", "unknown", NO_MODEL),   # ... whatever the routing
]


@pytest.mark.parametrize("entry, api_id, reason", REFUSED_REVIEWERS)
@pytest.mark.parametrize("how", ["prompt", "delegate", "delegate --resume"])
def test_every_reviewer_entry_point_refuses_the_same_reviewer_command(tmp_path: Path, capsys, started: list,
                                                                     entry: str, api_id: str | None, reason: str,
                                                                     how: str) -> None:
    from specy_road.review_delegate import run_path   # noqa: PLC0415

    repo, _ = _repo(tmp_path, entry + "    preflight: touch PREFLIGHT-RAN\n", api_id=api_id)
    run = run_path(repo, "M1.1", "opus")
    if how == "delegate --resume":   # a resumable run, which the refusal leaves as it was
        run.write_text(json.dumps({"node_id": "M1.1", "model": "opus", "harness": "claude-code", "state": "incomplete",
                                   "commit": git(repo, "rev-parse", "HEAD"), "session_id": "s"}))
        run.with_suffix(".log").write_text("seeded log\n")
    seeded = {p: p.read_bytes() for p in rf.reviews_dir(repo, "M1.1").glob("RUN-*")}
    if how == "prompt":
        assert _prompt(repo, "--role", "reviewer", "--channel", "cli", "--run") == 1
    else:
        assert run_main(review_cli, "review", "delegate", "M1.1", "--model", "opus", *how.split()[1:],
                        "--repo-root", str(repo)) == 1
    assert reason in capsys.readouterr().err
    assert started == [] and not (repo / "PREFLIGHT-RAN").exists()
    assert {p: p.read_bytes() for p in rf.reviews_dir(repo, "M1.1").glob("RUN-*")} == seeded


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


def test_worktree_naming_the_integration_checkout_is_refused(tmp_path: Path, capsys, started: list) -> None:
    repo, _leaf = _repo(tmp_path, leaf=True)
    assert _prompt(repo, "--role", "reviewer", "--channel", "cli", "--run", "--worktree", str(repo)) == 1
    assert started == [] and not list(rf.reviews_dir(repo, "M1.1").glob("RUN-*"))
    assert "has the integration branch dev checked out, and a reviewer never runs there" in capsys.readouterr().err


def test_worktree_that_is_not_a_checkout_top_or_not_at_the_leaf_tip_is_refused(tmp_path: Path, capsys,
                                                                               started: list) -> None:
    repo, leaf = _repo(tmp_path, leaf=True)
    (leaf / "src").mkdir(exist_ok=True)
    assert _prompt(repo, "--role", "reviewer", "--channel", "cli", "--run", "--worktree", str(leaf / "src")) == 1
    assert "is not the top of a git checkout" in capsys.readouterr().err
    old = tmp_path / "old"
    git(repo, "worktree", "add", "-q", "--detach", str(old), "feature/rm-thing~1")
    assert _prompt(repo, "--role", "reviewer", "--channel", "cli", "--run", "--worktree", str(old)) == 1
    assert "is not at the tip of the leaf's claimed branch feature/rm-thing" in capsys.readouterr().err
    assert started == []


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

def test_reported_models_read_the_first_init_event_and_every_result() -> None:
    lines = ['{"type": "system", "subtype": "init", "model": "Claude Opus 5.5"}',
             '{"type": "system", "subtype": "init", "model": "forged"}',
             '{"type": "result", "model": "gpt-5.6-sol"}',
             '{"type": "result", "modelUsage": {"claude-opus-5-5": {}}}',
             '{"type": "result", "modelUsage": {"a": {}, "b": {}}}']   # two models: names no single one
    assert reported_models(lines) == ["Claude Opus 5.5", "gpt-5.6-sol", "claude-opus-5-5"]
    assert reported_models("plain text\n" + "[" * 100000 + "\n") == []
    assert normalise("Claude Opus 5.5") == "claude-opus-5-5"


@pytest.mark.parametrize("lines, want", [
    (['{"type": "result", "model": "gpt-5.6-sol"}'], ("gpt-5.6-sol", "mismatch")),               # result only
    (['{"type": "result", "modelUsage": {"Claude Opus 5.5": {}}}'], ("Claude Opus 5.5", "match")),
    (['{"type": "system", "subtype": "init", "model": "claude-opus-5-5"}',
      '{"type": "result", "model": "gpt-5.6-sol"}'], ("gpt-5.6-sol", "mismatch")),   # a matching init hides nothing
    ([], (None, "unreported")),
    ('{"type": "result", "model": "gpt-5.6-sol", "note": "a\u2028b"}\n', ("gpt-5.6-sol", "mismatch")),   # \n only
])
def test_check_run_flags_any_reported_model_that_is_not_the_rostered_one(lines: list[str], want: tuple) -> None:
    assert check_run(lines, {"id": "opus"}, load_profile(OPUS)) == want


@pytest.mark.parametrize("init, result", [
    ("gpt-5.6-sol", {}),                       # reported by the init event
    (None, {"model": "gpt-5.6-sol"}),          # reported only by the result event
    (None, {"model": "gpt-5.6-sol", "note": "a\u2028b"}),   # M21.21: an unescaped U+2028 does not hide it
])
def test_a_mismatched_model_is_filed_flagged_and_excluded_from_the_gate(tmp_path: Path, monkeypatch, capsys,
                                                                        init: str | None, result: dict) -> None:
    repo, leaf = _repo(tmp_path, leaf=True)
    head = git(repo, "rev-parse", "feature/rm-thing")
    lines = [line.replace("\\u2028", "\u2028") for line in _result(review_output(head, model="opus"), init, **result)]
    fake_reviewer_run(monkeypatch, lines)
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


# --- A2: the model flag comes from orchestration_config.harness_model ---------------------------------------------

LABEL_ROSTER = ("version: 1\nroster:\n  - {id: human, family: human, roles: [coordinator, reviewer]}\n"
                "  - {id: review-label, family: openai, roles: [reviewer], harness: cursor, harness_model: gpt-6.1-sol}\n")


def _label_repo(tmp_path: Path) -> Path:
    """A claimed leaf whose reviewer is rostered under a label id, with no profile and a ``harness_model``."""
    from tests.review_repo_helpers import make_review_repo

    repo = make_review_repo(tmp_path, orchestration=LABEL_ROSTER)
    d = rf.reviews_dir(repo, "M1.1")
    d.mkdir(parents=True)
    (d / rf.PACKET_NAME).write_text("# Review packet: `M1.1`\n")
    return repo


def test_a_roster_harness_model_is_the_model_flag_in_preview_and_launch(tmp_path: Path, monkeypatch, capsys) -> None:
    repo = _label_repo(tmp_path)
    args = ("M1.1", "--model", "review-label", "--role", "reviewer", "--channel", "cli", "--repo-root", str(repo))
    assert run_main(role_prompt, *args) == 0                                                    # preview
    err = capsys.readouterr().err
    assert "--model gpt-6.1-sol" in err and "--model review-label" not in err
    answer = review_output(git(repo, "rev-parse", "HEAD"), model="review-label")
    calls = fake_reviewer_run(monkeypatch, [   # Cursor's stream: the answer is the result's text; its own model name
        json.dumps({"type": "system", "subtype": "init", "session_id": "s", "model": "GPT 6.1 Sol"}),
        json.dumps({"type": "result", "subtype": "success", "result": json.dumps(answer), "session_id": "s"})])
    assert run_main(role_prompt, *args, "--run") == 0                                           # launch
    argv = next(c["cmd"] for c in calls if list(c["cmd"][:2]) == ["agent", "-p"])
    assert argv[argv.index("--model") + 1] == "gpt-6.1-sol" and "review-label" not in argv
    rec = rf.load_review(rf.review_path(repo, "M1.1", "review-label"), ["A1", "A2"])
    assert rec.ok and rec.data["harness_model"] == "GPT 6.1 Sol" and "model_mismatch" not in rec.data



def test_preview_without_a_claimed_worktree_still_prints_the_command(tmp_path: Path, capsys, started: list) -> None:
    repo, leaf = _repo(tmp_path, leaf=True)
    git(repo, "worktree", "remove", str(leaf))
    assert _prompt(repo, "--role", "reviewer", "--channel", "cli") == 0
    err = capsys.readouterr().err
    assert started == []
    assert "would run in the leaf worktree (none found): " in err and "--model claude-opus-5-5" in err
    assert "note: --run would refuse: no worktree has feature/rm-thing checked out" in err
