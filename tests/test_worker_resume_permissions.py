"""A custom launch command's permissions carry through ``message`` / ``resume`` (M11.23).

``channels.cli_resume`` is the command a resumed turn runs on a harness whose
resume is its own command; ``delegate`` warns about a launch command a resume
cannot reuse and about one that prints text instead of the event stream; the
documented hands-off Claude Code example parses and keeps the worker off the
remote.
"""

from __future__ import annotations

import json
import re
import shlex
import subprocess
from pathlib import Path

import pytest

from tests.review_repo_helpers import git, make_review_repo
from tests.test_models_and_prompt import run_main
from tests.test_orchestrate_plan import plan_repo

from specy_road import worker_adapters as wa
from specy_road.bundled_scripts import doctor, orchestrate_cli
from specy_road import worker_ops as ops
from specy_road import worker_state as ws
from specy_road.orchestration_config import validate_orchestration_dict
from specy_road.worker_adapter_cursor import force_warnings, launch_permissions
from specy_road.worker_adapter_parsers import output_mode_note, placeholder_problem, resume_form_note

DOC = Path(__file__).resolve().parents[1] / "docs" / "orchestration-workers.md"
CODEX_POLICY = "-c sandbox_mode=workspace-write -c sandbox_workspace_write.network_access=true -c approval_policy=never"
CODEX_CLI = f"codex exec --json {CODEX_POLICY} - < {{prompt}}"
CODEX_RESUME = f"codex exec resume --json {CODEX_POLICY} {{session}} - < {{prompt}}"
CURSOR_CLI = 'agent -p --output-format stream-json --trust --sandbox enabled "<prompt>"'
CURSOR_RESUME = 'agent -p --resume {session} --output-format stream-json --trust --sandbox enabled "<prompt>"'


def _roster(harness: str, cli: str | None, cli_resume: str | None = None, extra: str = "") -> str:
    channels = {"cli": cli, **({"cli_resume": cli_resume} if cli_resume else {})} if cli else {}
    return ("version: 1\nroster:\n  - {id: human, family: human, roles: [coordinator, reviewer]}\n"
            f"  - {{id: opus, family: anthropic, roles: [executor, reviewer], harness: {harness},{extra}\n"
            f"     channels: {json.dumps(channels)}}}\n"
            "policy: {max_workers: 2}\n")


def _repo(tmp_path: Path, harness: str, cli: str | None, cli_resume: str | None = None, extra: str = "") -> Path:
    repo = make_review_repo(tmp_path, orchestration=_roster(harness, cli, cli_resume, extra))
    (repo / ".gitignore").write_text("work/\n")
    git(repo, "add", ".gitignore")
    git(repo, "commit", "-qm", "ignore work")
    return repo


def _launch_then_resume(repo: Path, monkeypatch) -> tuple[wa.Launch, wa.Launch]:
    """The argv ``delegate`` launches, then the argv ``message`` resumes the recorded session with."""
    launches: list[wa.Launch] = []
    monkeypatch.setattr(ops, "spawn", lambda root, rec, launch, **kw: launches.append(launch))
    rec, _ = ops.delegate(repo, "M1.1", "opus", offline=True)
    ws.mutate(repo, rec, lambda r: setattr(r, "provider_session_id", "sess-1"))
    ws.set_state(repo, rec, "idle", pid=None)
    ops.message(repo, rec.worker_id, "go on", offline=True)
    return launches[0], launches[1]


def _config_args(cmd: str) -> list[str]:
    words = shlex.split(cmd)
    return [words[i + 1] for i, w in enumerate(words) if w == "-c"]


def test_codex_cli_resume_keeps_the_launch_policy(tmp_path: Path, monkeypatch, capsys) -> None:
    launch, resumed = _launch_then_resume(_repo(tmp_path, "codex", CODEX_CLI, CODEX_RESUME), monkeypatch)
    assert launch.argv[:2] == ["sh", "-c"] and launch.argv[2].startswith(f"codex exec --json {CODEX_POLICY} - < ")
    assert resumed.argv[2].startswith(f"codex exec resume --json {CODEX_POLICY} sess-1 - < ")
    assert resumed.session_id == "sess-1"
    assert "warning" not in capsys.readouterr().err


def test_cursor_cli_resume_keeps_the_launch_flags(tmp_path: Path, monkeypatch) -> None:
    launch, resumed = _launch_then_resume(_repo(tmp_path, "cursor", CURSOR_CLI, CURSOR_RESUME), monkeypatch)
    assert launch.argv[2].startswith("agent -p --output-format stream-json --trust --sandbox enabled ")
    assert resumed.argv[2].startswith("agent -p --resume sess-1 --output-format stream-json --trust --sandbox enabled ")


@pytest.mark.parametrize(("extra", "flags"), [
    ("", ["--trust", "--sandbox", "enabled"]),
    (" cursor_force: false,", ["--trust", "--sandbox", "enabled"]),
    (" cursor_force: true,", ["--trust", "--force"]),
])
def test_cursor_default_command_is_sandboxed_unless_the_roster_opts_into_force(
        tmp_path: Path, monkeypatch, extra: str, flags: list[str]) -> None:
    launch, resumed = _launch_then_resume(_repo(tmp_path, "cursor", None, extra=extra), monkeypatch)
    for argv in (launch.argv, resumed.argv):
        assert argv[0] == "agent" and launch_permissions(argv) == flags


def test_plan_and_doctor_warn_once_per_cursor_entry_that_force_allows(tmp_path: Path, capsys) -> None:
    roster = """version: 1
roster:
  - {id: human, family: human, roles: [coordinator, reviewer]}
  - {id: opus, family: anthropic, roles: [executor, reviewer], harness: claude-code, cursor_force: true}
  - {id: forced, family: cursor, roles: [executor], harness: cursor, cursor_force: true, available: false}
  - {id: sandboxed, family: cursor, roles: [executor], harness: cursor, cursor_force: false}
  - id: yolo
    family: xai
    roles: [reviewer]
    harness: cursor
    channels: {cli: "agent -p --trust --yolo {prompt}", cli_resume: "agent -p --resume {session} --force {prompt}"}
policy: {reviewers_required: 1}
"""
    repo = plan_repo(tmp_path, roster=roster)
    assert run_main(orchestrate_cli, "orchestrate", "plan", "--repo-root", str(repo)) == 0
    said = [ln for ln in capsys.readouterr().out.splitlines() if ln.startswith("! cursor --force:")]
    assert [ln.split()[3] for ln in said] == ["forced", "yolo"]
    assert "(cursor_force: true)" in said[0] and "channels.cli passes" in said[1] and "channels.cli_resume" in said[1]
    assert all("every command not explicitly denied" in ln for ln in said)
    with pytest.raises(SystemExit):
        doctor.main(["--repo-root", str(repo)])
    assert [ln for ln in capsys.readouterr().err.splitlines() if ln.startswith("! cursor --force:")] == said


@pytest.mark.parametrize(("cli", "passed", "forces"), [
    ("agent -p {prompt} --force; true", ["--force"], True),      # an operator ends the word
    ("agent -p {prompt} --yolo&& true", ["--yolo"], True),
    ("agent -p {prompt} --force|cat", ["--force"], True),
    ("agent -p {prompt} --force>log", ["--force"], True),
    ("(agent -p {prompt} --force)", ["--force"], True),
    ("`agent -p {prompt} --force`", ["--force"], True),
    ("$(agent -p {prompt} --force)", ["--force"], True),
    ("agent -p {prompt} -f", ["-f"], True),                      # the short alias, alone and clustered
    ("agent -pf {prompt}", ["-pf"], True),
    ("agent -p {prompt} --for\\ce", ["--force"], True),           # read as the shell reads it
    ("agent -p {prompt} --trust --sandbox=disabled --force; true", ["--trust", "--sandbox=disabled", "--force"], True),
    ("agent -p {prompt} --sandbox disabled; true", ["--sandbox", "disabled"], False),
    ("agent -p {prompt} --sandbox; true", ["--sandbox"], False),  # an operator is not the flag's value
    ("agent -p {prompt} --sandbox\ntrue", ["--sandbox"], False),  # nor is the next line
    ("agent -p {prompt} '--force;'", [], False),                 # a quoted operator is part of the word
    ("agent -p {prompt} --force\\;", [], False),
    ("agent -p {prompt} 'try --force; then stop'", [], False),
    ("agent -Hf -p {prompt}", [], False),                        # the value of -H, not a switch
    ("agent -p {prompt} --force=true", [], False),               # `agent` refuses this as an unknown option
])
def test_a_custom_cursor_command_is_read_as_the_shell_splits_it(tmp_path: Path, cli: str, passed: list[str],
                                                                forces: bool) -> None:
    launch = wa.adapter_for("cursor").launch(tmp_path / "prompt.md", tmp_path, None, cli)
    assert launch_permissions(launch.argv) == passed
    for channel in ("cli", "cli_resume"):
        assert len(force_warnings([{"id": "custom", "harness": "cursor", "channels": {channel: cli}}])) == forces


@pytest.mark.parametrize("spelling", [
    "--for\\\nce", "--yo\\\nlo", "--force\\\n", "\\\n--force", '"--for\\\nce"',   # a continuation joins the word
    "--for\\\n\\\nce", "--fo''rce", '--fo""r\\ce',
    "--force \\", "--force\\",                               # a trailing backslash is a literal
    "'--for\\\nce'",                                        # single quotes keep it
    "--force\\\\\n",                                       # an escaped backslash, then a real newline
    '"--force\\\\\n"',
])
def test_launch_and_resume_record_the_flags_the_shell_passes(tmp_path: Path, spelling: str) -> None:
    printed = subprocess.run(["sh", "-c", f"printf '%s\\0' {spelling}"], capture_output=True, text=True, check=True)
    shell_passes = [w for w in printed.stdout.split("\0") if w in ("--force", "--yolo")]
    cli = f"agent -p {{prompt}} --resume {{session}} {spelling}"
    cursor, prompt = wa.adapter_for("cursor"), tmp_path / "prompt.md"
    assert launch_permissions(cursor.launch(prompt, tmp_path, None, cli).argv) == shell_passes
    assert launch_permissions(cursor.resume("sess-1", prompt, tmp_path, "m", cli).argv) == shell_passes
    warned = force_warnings([{"id": "custom", "harness": "cursor", "channels": {"cli": cli}}])
    assert len(warned) == len(shell_passes)


@pytest.mark.parametrize("cli", ["agent -p {prompt} -w; true", "agent -p {prompt} --worktree|cat",
                                 "agent -p {prompt} --worktree=mine&& true", "agent -pw {prompt}",
                                 "agent -p {prompt} -wmine", "agent -p {prompt} --work\\\ntree"])
def test_a_custom_cursor_command_never_asks_for_its_own_worktree(tmp_path: Path, cli: str) -> None:
    with pytest.raises(wa.Unsupported, match="never pass -w"):
        wa.adapter_for("cursor").launch(tmp_path / "prompt.md", tmp_path, None, cli)


def test_an_unbalanced_custom_cursor_command_is_refused_and_its_earlier_words_still_warn(tmp_path: Path) -> None:
    cli = "agent -p {prompt} --force 'unbalanced"
    with pytest.raises(wa.Unsupported):
        wa.adapter_for("cursor").launch(tmp_path / "prompt.md", tmp_path, None, cli)
    assert force_warnings([{"id": "custom", "harness": "cursor", "channels": {"cli": cli}}]) != []


def _documented(lang: str, needle: str) -> str:
    blocks = [b for b in re.findall(rf"```{lang}\n(.*?)```", DOC.read_text(encoding="utf-8"), re.S) if needle in b]
    assert len(blocks) == 1, f"one ```{lang} block with {needle!r} in {DOC.name}"
    return blocks[0]


def _hands_off_cli() -> str:
    return re.search(r'cli: "(.*)"', _documented("yaml", "--settings")).group(1)


def test_the_documented_hands_off_claude_cli_keeps_its_settings_on_resume(tmp_path: Path, monkeypatch) -> None:
    cli = _hands_off_cli()
    assert placeholder_problem(cli) is None
    assert "--permission-mode acceptEdits --settings " in cli and "{session_flag}" in cli
    launch, resumed = _launch_then_resume(_repo(tmp_path, "claude-code", cli), monkeypatch)
    settings = "--settings ~/.config/specy-road/claude-worker.json "
    assert settings in launch.argv[2] and f"--session-id {launch.session_id} " in launch.argv[2]
    assert settings in resumed.argv[2] and "--resume sess-1 " in resumed.argv[2]
    assert "--permission-mode acceptEdits" in resumed.argv[2]


def test_the_documented_settings_parse_and_deny_push_with_no_bare_edit_allow() -> None:
    perms = json.loads(_documented("json", '"permissions"'))["permissions"]
    assert {"Bash(git push *)", "Bash(gh pr *)"} <= set(perms["deny"])
    assert not {"Edit", "Write"} & set(perms["allow"])
    doc = DOC.read_text(encoding="utf-8")
    assert "may stop at a shell permission" not in doc and "permission_denials" in doc


def test_cli_resume_must_name_a_session_placeholder() -> None:
    def roster(cli_resume: str) -> dict:
        return {"version": 1, "roster": [{"id": "x", "family": "openai", "roles": ["executor"],
                                          "channels": {"cli": "w {prompt}", "cli_resume": cli_resume}}]}
    assert validate_orchestration_dict(roster("w --resume {session} {prompt}")) is None
    assert validate_orchestration_dict(roster("w {session_flag} {prompt}")) is None
    assert validate_orchestration_dict(roster("w --resume {prompt}"))


@pytest.mark.parametrize(("harness", "cli", "cli_resume", "warned"), [
    ("codex", "wrapper {prompt}", None, True),
    ("cursor", "wrapper {prompt}", None, True),
    ("codex", "wrapper {prompt}", "wrapper --resume {session} {prompt}", False),
    ("claude-code", "wrapper {session_flag} {prompt}", None, False),
    ("generic", "wrapper {prompt}", None, False),   # no resume at all: nothing falls back
])
def test_delegate_warns_when_a_resume_would_fall_back_to_the_default(tmp_path: Path, monkeypatch, capsys,
                                                                       harness, cli, cli_resume, warned) -> None:
    monkeypatch.setattr(ops, "spawn", lambda *a, **kw: None)
    ops.delegate(_repo(tmp_path, harness, cli, cli_resume), "M1.1", "opus", offline=True)
    err = capsys.readouterr().err
    assert ("no channels.cli_resume" in err and "default's permissions" in err) is warned


def test_delegate_notes_a_text_only_command(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(ops, "spawn", lambda *a, **kw: None)
    cli = 'agent -p --output-format text --trust "<prompt>"'
    ops.delegate(_repo(tmp_path, "cursor", cli, CURSOR_RESUME), "M1.1", "opus", offline=True)
    err = capsys.readouterr().err
    assert err.count("prints no agent event stream") == 1 and "--output-format stream-json" in err


def test_output_mode_note_reads_only_visible_print_mode_commands() -> None:
    assert "stream-json --verbose" in output_mode_note("claude -p --permission-mode acceptEdits < {prompt}")
    assert output_mode_note("/usr/local/bin/claude -p --output-format json < {prompt}")
    assert output_mode_note("cursor agent --print --output-format=text {prompt}")
    assert "--json" in output_mode_note("codex exec -c approval_policy=never - < {prompt}")
    for quiet in ("claude -p --output-format stream-json --verbose < {prompt}",
                  "agent -p --output-format=stream-json {prompt}", CODEX_CLI, CODEX_RESUME,
                  "claude-worker.sh {session} {prompt}",   # a wrapper is not looked into
                  "claude --resume {session} {prompt}", None):   # not print mode
        assert output_mode_note(quiet) is None, quiet


def test_resume_form_note_only_for_a_launch_command_with_no_resume_form() -> None:
    assert resume_form_note("w {prompt}", None)
    assert resume_form_note("w {prompt}", "w {session} {prompt}") is None
    assert resume_form_note("w {session} {prompt}", None) is None
    assert resume_form_note(None, None) is None and resume_form_note("no placeholder", None) is None


def test_codex_default_resume_repeats_every_launch_policy_flag(tmp_path: Path) -> None:
    """``codex exec resume`` carries only the conversation, so the policy must be passed again."""
    p = tmp_path / "p.md"
    p.write_text("x")
    codex = wa.adapter_for("codex")
    launch = codex.launch(p, tmp_path, "m", None, effort="high")
    resumed = codex.resume("t1", p, tmp_path, "m", None, effort="high")
    launch_policy = _config_args(shlex.join(launch.argv))
    assert {"sandbox_mode=workspace-write", "approval_policy=never"} <= set(launch_policy)
    assert launch_policy == _config_args(shlex.join(resumed.argv)) and "--json" in resumed.argv
