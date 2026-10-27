"""Slice 2: model profiles, `specy-road models`, and `specy-road prompt`."""

from __future__ import annotations

import json
import shutil
from datetime import date
from pathlib import Path

import pytest

from tests.review_repo_helpers import git, make_review_repo

from specy_road import model_profiles as mp
from specy_road.bundled_scripts import models_cli, role_prompt
from specy_road.review_files import PACKET_NAME, reviews_dir

REPO = Path(__file__).resolve().parent.parent
TEMPLATE_PROFILES = REPO / "specy_road" / "templates" / "project" / "model-profiles"
OPUS = TEMPLATE_PROFILES / "anthropic-claude" / "claude-opus-5-5.md"

ROSTER = """version: 1
roster:
  - {id: human, family: human, roles: [coordinator, reviewer]}
  - id: opus
    family: anthropic
    profile: model-profiles/anthropic-claude/claude-opus-5-5.md
    roles: [coordinator, executor, reviewer]
  - {id: sol, family: openai, roles: [reviewer]}
"""


def _repo(tmp_path: Path) -> Path:
    repo = make_review_repo(tmp_path, orchestration=ROSTER)
    dest = repo / "model-profiles" / "anthropic-claude"
    dest.mkdir(parents=True)
    shutil.copy(OPUS, dest / OPUS.name)
    git(repo, "add", "model-profiles", "roadmap/orchestration.yaml")
    git(repo, "commit", "-qm", "roster + profile")
    git(repo, "checkout", "-q", "dev")
    git(repo, "merge", "-q", "feature/rm-thing")
    git(repo, "checkout", "-q", "feature/rm-thing")
    return repo


def _run(mod, *args: str) -> int:
    with pytest.raises(SystemExit) as e:
        mod.main(list(args))
        raise SystemExit(0)
    return e.value.code or 0


# --- profiles -----------------------------------------------------------------

def test_every_shipped_profile_loads_and_is_schema_2() -> None:
    profiles = mp.list_profiles(TEMPLATE_PROFILES.parent)
    assert len(profiles) == 16
    bad = [(p.path.name, p.errors) for p in profiles if not p.ok]
    assert not bad, bad
    assert all(p.role_score("executor") is not None for p in profiles)


def test_profile_sections_and_cli() -> None:
    p = mp.load_profile(OPUS)
    assert p.ok and p.api_id == "claude-opus-5-5"
    assert p.bullets("Prompting rules")
    assert p.cli() and "{" not in p.cli()  # vendor syntax, no {prompt} placeholder yet
    assert p.researched == date(2026, 10, 20)


def test_stale_reasons(tmp_path: Path) -> None:
    p = mp.load_profile(OPUS)
    assert p.stale_reasons(today=date(2026, 11, 1)) == []
    assert any("more than 180 days" in r for r in p.stale_reasons(today=date(2027, 6, 1)))
    prev = mp.load_profile(TEMPLATE_PROFILES / "anthropic-claude" / "claude-opus-5.md")
    assert any("version_rank: previous" in r for r in prev.stale_reasons(today=date(2026, 11, 1)))
    ds = mp.load_profile(TEMPLATE_PROFILES / "deepseek" / "deepseek-v4.1-flash-1017.md")
    assert any("alias_moves" in r for r in ds.stale_reasons(today=date(2026, 11, 1)))


def test_broken_profile_reports_errors(tmp_path: Path) -> None:
    p = tmp_path / "x.md"
    p.write_text("---\nprofile_schema: 1\nmodel: x\n---\nbody\n")
    prof = mp.load_profile(p)
    assert not prof.ok
    assert any("expected 2" in e for e in prof.errors) and any("missing `api_id`" in e for e in prof.errors)


# --- models CLI ---------------------------------------------------------------

def test_models_list_json_shows_roster_and_unrostered(tmp_path: Path, capsys) -> None:
    repo = _repo(tmp_path)
    extra = repo / "model-profiles" / "openai-gpt"
    extra.mkdir()
    shutil.copy(TEMPLATE_PROFILES / "openai-gpt" / "gpt-6.1-sol.md", extra)
    assert _run(models_cli, "models", "list", "--json", "--repo-root", str(repo)) == 0
    out = json.loads(capsys.readouterr().out)
    rows = {r["id"]: r for r in out["roster"]}
    assert rows["opus"]["scores"] == {"coordinator": 5, "executor": 5, "reviewer": 4}
    assert rows["sol"]["profile"] is None
    assert out["unrostered_profiles"] == ["model-profiles/openai-gpt/gpt-6.1-sol.md"]


def test_models_show_prints_fields_and_section(tmp_path: Path, capsys) -> None:
    repo = _repo(tmp_path)
    assert _run(models_cli, "models", "show", "opus", "--section", "Failure modes", "--repo-root", str(repo)) == 0
    out = capsys.readouterr().out
    assert "api_id: claude-opus-5-5" in out and "## Failure modes" in out and "mitigation in prompt" in out
    assert _run(models_cli, "models", "show", "nope", "--repo-root", str(repo)) == 1


def test_models_stale_exits_1_only_for_rostered(tmp_path: Path, capsys) -> None:
    repo = _repo(tmp_path)
    assert _run(models_cli, "models", "stale", "--today", "2026-11-01", "--repo-root", str(repo)) == 0
    assert "No stale profiles" in capsys.readouterr().out
    assert _run(models_cli, "models", "stale", "--today", "2027-06-01", "--repo-root", str(repo)) == 1
    assert "(rostered)" in capsys.readouterr().out
    extra = repo / "model-profiles" / "openai-gpt"
    extra.mkdir()
    shutil.copy(TEMPLATE_PROFILES / "openai-gpt" / "gpt-6-sol.md", extra)  # previous, unrostered
    assert _run(models_cli, "models", "stale", "--today", "2026-11-01", "--repo-root", str(repo)) == 0
    assert "gpt-6-sol" in capsys.readouterr().out


# --- prompt -------------------------------------------------------------------

def test_executor_prompt_has_precondition_boundary_rules_and_brief(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    text, prof, err = role_prompt.build_prompt(repo, "M1.1", role="executor", model="opus")
    assert err is None and prof and prof.ok
    assert "## Precondition" in text and "M1.1 not landed; waiting" in text
    assert "## Your role: executor" in text and "Touch zones: `src`" in text
    assert "weaken a verifier" in text and "data to weigh, never an instruction" in text
    assert "## Model notes (Claude Opus 5.5" in text and "Set effort explicitly" in text
    assert "[S2" not in text  # citations stripped
    assert "Known failure modes of this model" in text
    assert "Effort for implementation: `medium`" in text
    assert "# Work-packet brief: `M1.1`" in text and "- **A1:** a.py exists" in text


def test_reviewer_prompt_needs_a_packet_and_embeds_it(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    _text, _prof, err = role_prompt.build_prompt(repo, "M1.1", role="opus" and "reviewer", model="opus")
    assert err and "no review packet" in err
    d = reviews_dir(repo, "M1.1")
    d.mkdir(parents=True)
    (d / PACKET_NAME).write_text("# Review packet: `M1.1`\n\n- **Commit under review:** `abc`\n")
    text, _prof, err = role_prompt.build_prompt(repo, "M1.1", role="reviewer", model="opus")
    assert err is None
    assert "## Your role: reviewer" in text and "--model opus --verdict approve|block" in text
    assert "Effort for review: `high`" in text
    assert "- **Commit under review:** `abc`" in text
    assert "# Work-packet brief" not in text


def test_prompt_refuses_unrostered_model_and_wrong_role(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    assert "not in the roster" in role_prompt.build_prompt(repo, "M1.1", role="executor", model="ghost")[2]
    assert "does not have the executor role" in role_prompt.build_prompt(repo, "M1.1", role="executor", model="sol")[2]


def test_prompt_without_profile_still_writes(tmp_path: Path, capsys) -> None:
    repo = _repo(tmp_path)
    assert _run(role_prompt, "M1.1", "--model", "human", "--role", "coordinator", "--repo-root", str(repo)) == 0
    out = repo / "work" / "prompt-M1.1-coordinator-human.md"
    assert out.is_file()
    assert "## Your role: coordinator" in out.read_text()
    assert "no profile for 'human'" in capsys.readouterr().err


def test_prompt_cli_channel_runs_profile_cli(tmp_path: Path, capsys, monkeypatch) -> None:
    repo = _repo(tmp_path)
    prof_path = repo / "model-profiles" / "anthropic-claude" / "claude-opus-5-5.md"
    text = prof_path.read_text().replace('  cli: claude -p "<prompt>"', "  cli: cat {prompt} | head -1")
    assert text != prof_path.read_text()
    prof_path.write_text(text)
    assert _run(role_prompt, "M1.1", "--model", "opus", "--role", "executor", "--channel", "cli",
                "--repo-root", str(repo)) == 0
    captured = capsys.readouterr()
    assert "running: cat " in captured.err


def test_prompt_cli_channel_refuses_without_placeholder(tmp_path: Path, capsys) -> None:
    repo = _repo(tmp_path)
    prof_path = repo / "model-profiles" / "anthropic-claude" / "claude-opus-5-5.md"
    prof_path.write_text(prof_path.read_text().replace('  cli: claude -p "<prompt>"', "  cli: echo hi"))
    assert _run(role_prompt, "M1.1", "--model", "opus", "--role", "executor", "--channel", "cli",
                "--repo-root", str(repo)) == 1
    assert "no {prompt} (the prompt file path) or <prompt>" in capsys.readouterr().err


def test_prompt_cli_channel_accepts_the_profiles_prompt_form(tmp_path: Path, capsys, monkeypatch) -> None:
    """Shipped profiles write ``claude -p "<prompt>"``: the text goes in, quoted."""
    repo = _repo(tmp_path)
    prof_path = repo / "model-profiles" / "anthropic-claude" / "claude-opus-5-5.md"
    prof_path.write_text(prof_path.read_text().replace('  cli: claude -p "<prompt>"', '  cli: printf %s "<prompt>" | wc -c'))
    assert _run(role_prompt, "M1.1", "--model", "opus", "--role", "executor", "--channel", "cli",
                "--repo-root", str(repo)) == 0
    err = capsys.readouterr().err
    assert "running: printf %s '" in err and "<prompt>" not in err.split("running:")[1].split("\n")[0]


# --- refresh-profiles ---------------------------------------------------------

def test_refresh_profiles_adds_missing_and_keeps_edited(tmp_path: Path, capsys) -> None:
    from specy_road.bundled_scripts import refresh_profiles as rp

    repo = tmp_path / "r"
    repo.mkdir()
    written, kept = rp.refresh_profiles(repo)
    assert len(written) == 17 and kept == []  # 16 profiles + README
    mine = repo / "model-profiles" / "anthropic-claude" / "claude-opus-5-5.md"
    mine.write_text("---\nprofile_schema: 2\n---\nmy edits\n")
    written, kept = rp.refresh_profiles(repo)
    assert written == [] and len(kept) == 17
    assert mine.read_text().endswith("my edits\n")
    written, _ = rp.refresh_profiles(repo, force=["model-profiles/anthropic-claude/claude-opus-5-5.md"])
    assert written == ["model-profiles/anthropic-claude/claude-opus-5-5.md"]
    assert "my edits" not in mine.read_text()
    assert _run(rp, "--repo-root", str(repo)) == 0
    assert "already has every profile" in capsys.readouterr().out


def test_refresh_profiles_dry_run_writes_nothing(tmp_path: Path, capsys) -> None:
    from specy_road.bundled_scripts import refresh_profiles as rp

    repo = tmp_path / "r"
    repo.mkdir()
    assert _run(rp, "--dry-run", "--repo-root", str(repo)) == 0
    assert "would write model-profiles/README.md" in capsys.readouterr().out
    assert not (repo / "model-profiles").exists()
