"""More regressions from the second independent review (Gemini 4 Argon, 2026-10-27).

Routing parity between ``prompt``, ``orchestrate plan`` and ``worker
delegate``; a signing failure in ``mark-implementation-reviewed``; skill and
stub edge cases in ``refresh-stubs``; a stale brainstorm decision; and
``models show`` printing ``harness/model``.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

from tests.review_repo_helpers import git, make_review_repo
from tests.test_models_and_prompt import OPUS

from specy_road.bundled_scripts import brainstorm_cli, models_cli, refresh_stubs as rs
from specy_road.bundled_scripts import mark_implementation_reviewed as mir
from specy_road.bundled_scripts.brainstorm_session import read_session
from specy_road.bundled_scripts.role_prompt import build_prompt
from specy_road.bundled_scripts.roadmap_load import load_roadmap
from specy_road.model_profiles import profile_for_entry
from specy_road.orchestrate_plan import Candidate, assign_leaf
from specy_road.orchestration_config import effective_config
from specy_road.specyrd_init import run_init

ORCH = """version: 1
roster:
  - {id: coord, family: anthropic, roles: [coordinator], may_process: [public]}
  - {id: coord2, family: openai, roles: [coordinator], may_process: [public, restricted]}
  - id: exec1
    family: anthropic
    profile: model-profiles/anthropic-claude/claude-opus-5-5.md
    roles: [executor, coordinator]
    may_process: [public, restricted]
    harness: claude-code
    channels: {cli: "printf roster-cli-%s {prompt}"}
  - {id: sub1, family: openai, roles: [executor], may_process: [public, restricted]}
policy: {reviewers_required: 1}
substitutions:
  - {slot: rev, use: sub1, decided: "2026-01-01", expires: "2027-01-01"}
"""


def _repo(tmp_path: Path, *, sensitivity: str | None = None) -> Path:
    repo = make_review_repo(tmp_path, orchestration=ORCH)
    dest = repo / "model-profiles" / "anthropic-claude"
    dest.mkdir(parents=True)
    shutil.copy(OPUS, dest / OPUS.name)
    if sensitivity:
        chunk = repo / "roadmap" / "phases" / "M1.json"
        chunk.write_text(chunk.read_text().replace('"id": "M1.1"', f'"sensitivity": "{sensitivity}", "id": "M1.1"'))
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "roster")
    return repo


def _run(mod, *args: str) -> int:
    with pytest.raises(SystemExit) as e:
        mod.main(list(args))
        raise SystemExit(0)
    return e.value.code or 0


def test_a_substitute_reviewer_gets_a_prompt(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    (repo / "work" / "reviews" / "M1.1").mkdir(parents=True)
    (repo / "work" / "reviews" / "M1.1" / "PACKET.md").write_text("# packet\n")
    text, _p, err = build_prompt(repo, "M1.1", role="reviewer", model="sub1")
    assert err is None and "## Your role: reviewer" in text
    assert "does not have the reviewer role" in build_prompt(repo, "M1.1", role="reviewer", model="exec1")[2]


def test_coordinator_sensitivity_is_checked_by_plan_and_prompt_alike(tmp_path: Path) -> None:
    repo = _repo(tmp_path, sensitivity="restricted")
    assert "may process only" in build_prompt(repo, "M1.1", role="coordinator", model="coord")[2]
    git(repo, "checkout", "-q", "dev")          # unclaimed from here: plan and prompt still check, prompt still carries the brief
    git(repo, "merge", "-q", "feature/rm-thing")
    (repo / "roadmap" / "registry.yaml").write_text("version: 1\nentries: []\n")
    config, _err = effective_config(repo)
    node = next(n for n in load_roadmap(repo)["nodes"] if n["id"] == "M1.1")
    cands = [Candidate(e, profile_for_entry(repo, e)) for e in config["roster"]]
    assert assign_leaf(node, cands, config).coordinator != "coord"    # coord has may_process: [public] only
    assert "may process only" in build_prompt(repo, "M1.1", role="coordinator", model="coord")[2]
    text, _p, err = build_prompt(repo, "M1.1", role="coordinator", model="coord2")
    assert err is None and "## Intent" in text
    assert "unknown node id" in build_prompt(repo, "M9.9", role="coordinator", model="coord2")[2]


def test_prompt_cli_channel_prefers_the_roster_channels_cli(tmp_path: Path, capsys) -> None:
    repo = _repo(tmp_path)
    git(repo, "update-ref", "refs/heads/dev", "HEAD")   # the profile, like the roster, is read from the integration branch
    assert _run(__import__("specy_road.bundled_scripts.role_prompt", fromlist=["main"]),
                "M1.1", "--model", "exec1", "--role", "executor", "--channel", "cli", "--repo-root", str(repo)) == 0
    assert "running: printf roster-cli-%s " in capsys.readouterr().err


def test_a_signing_failure_is_an_error_not_a_traceback(tmp_path: Path, monkeypatch, capsys) -> None:
    repo = make_review_repo(tmp_path, orchestration="version: 1\nroster:\n  - {id: human, family: human, "
                            "roles: [coordinator, reviewer], public_key: 'ssh-ed25519 AAAA'}\n"
                            "policy: {reviewers_required: 1, signed_reviews: true}\n")
    (repo / "work").mkdir()
    (repo / "work" / "implementation-summary-M1.1.md").write_text("## Summary\nx\n")
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda _p="": "a")
    with pytest.raises(SystemExit) as e:
        mir.main(["--sign-key", str(tmp_path / "no-such-key"), "--repo-root", str(repo)])
    assert e.value.code == 1 and "could not sign" in capsys.readouterr().err


def test_refresh_stubs_lists_a_dangling_skill_link_as_an_orphan(tmp_path: Path) -> None:
    run_init(target=tmp_path, agent="claude-code", dry_run=False, force=False, ai_commands_dir=None, role="dev")
    manifest = tmp_path / ".specyrd" / "manifest.json"
    data = manifest.read_text()
    link = ".claude/skills/specyrd-gone"
    os.symlink("../../.agents/skills/specyrd-gone", tmp_path / link)
    manifest.write_text(data.replace('".claude/skills/specyrd-validate"', f'".claude/skills/specyrd-validate", "{link}"'))
    _w, orphans = rs.refresh_stubs(tmp_path)
    assert link in orphans and (tmp_path / link).is_symlink()


def test_refresh_stubs_does_not_create_claude_md(tmp_path: Path) -> None:
    run_init(target=tmp_path, agent="claude-code", dry_run=False, force=False, ai_commands_dir=None, write_claude_md=False)
    assert not (tmp_path / "CLAUDE.md").exists()
    rs.refresh_stubs(tmp_path)
    assert not (tmp_path / "CLAUDE.md").exists()


def test_a_users_own_skill_directory_is_reported_skipped(tmp_path: Path, capsys) -> None:
    mine = tmp_path / ".claude" / "skills" / "specyrd-validate"
    mine.mkdir(parents=True)
    (mine / "SKILL.md").write_text("---\nname: specyrd-validate\n---\nmy own\n")
    (mine / "extra.txt").write_text("x")
    res = run_init(target=tmp_path, agent="claude-code", dry_run=False, force=False, ai_commands_dir=None)
    assert ".claude/skills/specyrd-validate (skipped (not ours))" in res.skipped
    assert not any(w.startswith(".claude/skills/specyrd-validate") for w in res.written)
    assert (mine / "extra.txt").is_file()


def test_the_commands_hint_is_only_for_old_harness_stubs() -> None:
    assert rs._old_command_stub(".cursor/commands/specyrd-x.md")
    assert not rs._old_command_stub("docs/commands/specyrd-x.md")


def _bs(repo: Path, *args: str) -> int:
    with pytest.raises(SystemExit) as e:
        brainstorm_cli.main([*args, "--repo-root", str(repo)])
        raise SystemExit(0)
    return e.value.code or 0


def test_accepting_a_rejected_idea_clears_the_stale_decision(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path)
    (repo / "work").mkdir(exist_ok=True)
    assert _bs(repo, "start", "--topic", "Grow", "--under", "M1") == 0
    assert _bs(repo, "add-idea", "--title", "One", "--slug", "grow") == 0
    assert _bs(repo, "reject", "B1", "--reason", "not now", "--slug", "grow") == 0
    assert read_session(repo, "grow").by_id("B1").decision["reason"] == "not now"
    assert _bs(repo, "accept", "B1", "--slug", "grow") == 0
    assert read_session(repo, "grow").by_id("B1").decision is None


def test_models_show_prints_harness_and_model(tmp_path: Path, capsys) -> None:
    repo = _repo(tmp_path)
    assert _run(models_cli, "models", "show", "exec1", "--repo-root", str(repo)) == 0
    assert "- harness/model: claude-code/exec1" in capsys.readouterr().out
