"""Round 6, policy items: B4 trusted integration ref, B5 pinned profiles, B6 `may_process: []`,
B7 refresh-profiles containment, F13 validate uses the gate's policy source, F14 profile diagnostics."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from pathlib import Path

import pytest
import yaml

from tests.review_repo_helpers import commit_file, git, make_review_repo

from specy_road import worker_ops as ops
from specy_road import worker_state as ws
from specy_road.bundled_scripts import models_cli
from specy_road.bundled_scripts.refresh_profiles import refresh_profiles
from specy_road.bundled_scripts.role_prompt import build_prompt
from specy_road.bundled_scripts.validate_roadmap import validate_at
from specy_road.model_profiles import load_profile
from specy_road.orchestrate_plan import build_orchestration_plan, entry_may_process, may_handle
from specy_road.orchestration_config import parse_orchestration_text
from specy_road.orchestration_pinned import pinned_profile_for_entry
from specy_road.review_gate import policy_source, review_required
from specy_road.worker_adapters import placeholder_problem

REPO = Path(__file__).resolve().parent.parent
OPUS = REPO / "specy_road/templates/project/model-profiles/anthropic-claude/claude-opus-5-5.md"
COMPOSER = REPO / "specy_road/templates/project/model-profiles/cursor-composer/composer-2.5.md"
PROFILE_REL = "model-profiles/anthropic-claude/claude-opus-5-5.md"
ROSTER = f"""version: 1
roster:
  - {{id: human, family: human, roles: [coordinator, reviewer]}}
  - id: opus
    family: anthropic
    profile: {PROFILE_REL}
    roles: [coordinator, executor, reviewer]
policy: {{reviewers_required: 1}}
"""


def _repo(tmp_path: Path, roster: str = ROSTER) -> Path:
    """Roster and profile committed on the feature branch, then ``dev`` moved to it."""
    repo = make_review_repo(tmp_path, orchestration=roster)
    dest = repo / PROFILE_REL
    dest.parent.mkdir(parents=True)
    shutil.copy(OPUS, dest)
    git(repo, "add", "model-profiles")
    git(repo, "commit", "-qm", "profile")
    git(repo, "update-ref", "refs/heads/dev", "HEAD")
    return repo


# --- B4 ----------------------------------------------------------------------------

def test_a_feature_commit_cannot_retarget_the_integration_branch(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path, orchestration=ROSTER)
    git(repo, "branch", "rogue")
    commit_file(repo, "roadmap/git-workflow.yaml",
                "version: 1\nintegration_branch: rogue\nremote: origin\n", "retarget")
    ref, err = policy_source(repo)
    assert ref is None and "'rogue'" in err and "'dev'" in err and "names itself" in err
    assert review_required(repo)   # fails closed
    assert "orchestration config" in build_prompt(repo, "M1.1", role="executor", model="opus")[2]


def test_with_a_remote_only_the_remote_tracking_integration_ref_is_read(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path, orchestration=ROSTER)
    bare = tmp_path / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True)
    git(repo, "remote", "add", "origin", str(bare))
    ref, err = policy_source(repo)
    assert ref is None and "not fetched as origin/dev" in err   # local dev alone no longer counts
    git(repo, "push", "-q", "origin", "dev")
    assert policy_source(repo) == ("refs/remotes/origin/dev", None)
    # moving the local branch to a widened roster changes nothing
    (repo / "roadmap" / "orchestration.yaml").write_text(
        ROSTER.replace("roles: [coordinator, executor, reviewer]",
                       "roles: [coordinator, executor, reviewer]\n    may_process: [public, restricted]"))
    git(repo, "commit", "-qm", "wide", "--", "roadmap/orchestration.yaml")
    git(repo, "update-ref", "refs/heads/dev", "HEAD")
    assert policy_source(repo) == ("refs/remotes/origin/dev", None)


# --- B5 ----------------------------------------------------------------------------

def test_an_uncommitted_profile_edit_is_refused_not_executed(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    marker = tmp_path / "ran"
    prof = repo / PROFILE_REL
    prof.write_text(prof.read_text().replace("cli:", f'cli: "touch {marker} && echo {{prompt}}"\n  was_cli:', 1))
    text, p, err = build_prompt(repo, "M1.1", role="executor", model="opus")
    assert err and "differs from the copy on the integration branch" in err and "commit it" in err
    plan, _ = build_orchestration_plan(repo)
    with pytest.raises(ws.WorkerError, match="differs from the copy on the integration branch"):
        ops.delegate(repo, "M1.1", "opus", harness="generic")
    assert not marker.exists()
    with pytest.raises(SystemExit) as e:
        models_cli.main(["models", "list", "--json", "--repo-root", str(repo)])
    assert e.value.code == 0


def test_a_profile_only_in_the_working_tree_is_not_used(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path, orchestration=ROSTER)   # roster on dev, profile nowhere
    git(repo, "update-ref", "refs/heads/dev", "HEAD")
    dest = repo / PROFILE_REL
    dest.parent.mkdir(parents=True)
    shutil.copy(OPUS, dest)
    prof = pinned_profile_for_entry(repo, {"id": "opus", "profile": PROFILE_REL})
    assert not prof.ok and "not committed on the integration branch" in prof.errors[0]
    plan, _ = build_orchestration_plan(repo)


def test_the_committed_profile_is_used_when_the_tree_matches_or_lacks_it(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    assert pinned_profile_for_entry(repo, {"id": "opus", "profile": PROFILE_REL}).ok
    (repo / PROFILE_REL).unlink()
    prof = pinned_profile_for_entry(repo, {"id": "opus", "profile": PROFILE_REL})
    assert prof.ok and prof.cli()
    text, p, err = build_prompt(repo, "M1.1", role="executor", model="opus")
    assert err is None and "## Model notes" in text


@pytest.mark.parametrize("harness, profile, expect", [
    # Sandbox runbook §0 (2026-10-27): a profiled claude-code entry launched `claude -p '<prompt>'`.
    ("claude-code", OPUS, ["stream-json", "--session-id", "--model", "claude-opus-5-5"]),
    # Review round 7, R7-1: Composer's `api_id: unknown` is Cursor's default model, not `--model unknown`.
    ("cursor", COMPOSER, ["stream-json", "!--model"]),
    # R7-5: no `harness:` is generic, which runs the profile's own access.cli (`claude -p "<prompt>"`).
    (None, OPUS, ["-p", "!stream-json"]),
])
def test_a_profile_cli_launches_only_generic_workers(tmp_path: Path, monkeypatch, harness, profile, expect) -> None:
    rel = profile.relative_to(REPO / "specy_road/templates/project").as_posix()
    roster = ROSTER.replace(PROFILE_REL, rel)
    if harness:
        roster = roster.replace("family: anthropic", f"family: anthropic\n    harness: {harness}")
    repo = _repo(tmp_path, roster)
    if rel != PROFILE_REL:
        commit_file(repo, rel, profile.read_text(), "composer profile")
        git(repo, "update-ref", "refs/heads/dev", "HEAD")
    bin_dir, argv = tmp_path / "bin", tmp_path / "argv"
    bin_dir.mkdir()
    for name in ("claude", "agent"):
        (bin_dir / name).write_text(f'#!/bin/sh\necho "$@" > {argv}\ncat > /dev/null\n')
        (bin_dir / name).chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    ops.delegate(repo, "M1.1", "opus")
    for _ in range(100):
        if argv.is_file() and argv.read_text():
            break
        time.sleep(0.1)
    args = argv.read_text().split()
    for e in expect:
        assert (e[1:] not in args) if e.startswith("!") else (e in args), (e, args)
    if "--model" in expect:
        assert args[args.index("--model") + 1] == expect[expect.index("--model") + 1]


# --- B6 ----------------------------------------------------------------------------

def test_explicit_empty_may_process_denies_everything(tmp_path: Path) -> None:
    assert entry_may_process({"id": "x"}) == ["public"]
    assert entry_may_process({"id": "x", "may_process": []}) == []
    assert not may_handle({"id": "x", "may_process": []}, "public")
    roster = ROSTER.replace("roles: [coordinator, executor, reviewer]",
                            "roles: [coordinator, executor, reviewer]\n    may_process: []")
    repo = _repo(tmp_path, roster)
    assert "may process only []" in build_prompt(repo, "M1.1", role="executor", model="opus")[2]
    with pytest.raises(ws.WorkerError, match="may not process it"):
        ops.delegate(repo, "M1.1", "opus", harness="generic")
    git(repo, "checkout", "-q", "dev")
    (repo / "roadmap" / "registry.yaml").write_text("version: 1\nentries: []\n")
    chunk = repo / "roadmap" / "phases" / "M1.json"
    chunk.write_text(chunk.read_text().replace('"In Progress"', '"Not Started"'))
    git(repo, "commit", "-qam", "free")
    plan, err = build_orchestration_plan(repo)
    assert err is None and any("no eligible executor" in p for p in plan.batches[0][0].problems)


# --- B7 ----------------------------------------------------------------------------

def test_refresh_profiles_refuses_a_symlinked_destination(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    outside = tmp_path / "outside"
    repo.mkdir()
    outside.mkdir()
    os.symlink(outside, repo / "model-profiles")
    with pytest.raises(ValueError, match="symlink"):
        refresh_profiles(repo)
    assert not list(outside.rglob("*.md"))
    (repo / "model-profiles").unlink()
    (repo / "model-profiles").mkdir()
    os.symlink(outside, repo / "model-profiles" / "anthropic-claude")
    with pytest.raises(ValueError, match="symlink"):
        refresh_profiles(repo)
    assert not list(outside.rglob("*.md"))
    (repo / "model-profiles" / "anthropic-claude").unlink()
    written, _ = refresh_profiles(repo)
    assert written and all((repo / w).is_file() for w in written)


# --- F4 ----------------------------------------------------------------------------

def test_documented_cli_forms_pass_the_placeholder_guard() -> None:
    doc = (REPO / "docs" / "orchestration-models.md").read_text()
    for form in ("claude -p --model <id> < {prompt}", 'claude -p "<prompt>" --model <id>',
                 "codex exec -m <id> - < {prompt}", "agent -p --model <id> < {prompt}"):
        assert form in doc and placeholder_problem(form) is None
    assert 'claude -p "$(cat {prompt})"' in doc   # named as the refused form
    assert placeholder_problem('claude -p "$(cat {prompt})" --model x')


# --- F13 ---------------------------------------------------------------------------

def test_validate_uses_the_integration_branch_gate_switch(tmp_path: Path, capsys) -> None:
    repo = make_review_repo(tmp_path)
    chunk = repo / "roadmap" / "phases" / "M1.json"
    data = json.loads(chunk.read_text())
    data["nodes"][0].pop("acceptance")
    chunk.write_text(json.dumps(data))
    (repo / "roadmap" / "git-workflow.yaml").write_text(
        "version: 1\nintegration_branch: dev\nremote: origin\nrequire_implementation_review_before_finish: false\n")
    capsys.readouterr()
    validate_at(repo)
    assert "has no acceptance criteria" in capsys.readouterr().err
    reg = repo / "roadmap" / "registry.yaml"
    entries = yaml.safe_load(reg.read_text())
    del entries["entries"][0]["implementation_review"]
    reg.write_text(yaml.safe_dump(entries))
    with pytest.raises(SystemExit):
        validate_at(repo)
    assert "implementation_review must be" in capsys.readouterr().err


# --- F14 ---------------------------------------------------------------------------

def _profile(tmp_path: Path, front: str) -> Path:
    p = tmp_path / "p.md"
    p.write_text(f"---\nprofile_schema: 2\nfamily: x\nmodel: x\napi_id: x\nversion_rank: current\n{front}\n---\n")
    return p


def test_malformed_access_and_role_fit_are_errors_not_crashes(tmp_path: Path) -> None:
    prof = load_profile(_profile(tmp_path, "researched: 2026-01-01\naccess: a string\nrole_fit: [1]"))
    assert not prof.ok and any("`access` must be a mapping" in e for e in prof.errors)
    assert any("`role_fit` must be a mapping" in e for e in prof.errors)
    assert prof.cli() is None and prof.role_score("executor") is None
    prof = load_profile(_profile(tmp_path, "researched: 2026-01-01\naccess: {cli: [1]}\n"
                                           "role_fit: {executor: {score: high}}\ncost_usd_per_mtok: 3"))
    assert {"`access.cli` must be a string", "`role_fit.executor` must be a mapping with an integer `score`",
            "`cost_usd_per_mtok` must be a mapping"} <= set(prof.errors)


def test_impossible_dates_are_errors(tmp_path: Path) -> None:
    prof = load_profile(_profile(tmp_path, "researched: 2026-00-00\naccess: {}\nrole_fit: {}"))
    assert not prof.ok and "not valid YAML" in prof.errors[0]
    prof = load_profile(_profile(tmp_path, "researched: '2026-00-00'\naccess: {}\nrole_fit: {}"))
    assert not prof.ok and "not a calendar date" in prof.errors[-1]
    assert load_profile(_profile(tmp_path, "researched: 2026-01-15\naccess: {}\nrole_fit: {}")).ok
    for field in ("unavailable_until: '2026-00-00'", "unavailable_until: 2026-00-00", "unavailable_until: '2026-02-30'"):
        _d, err = parse_orchestration_text(ROSTER.replace("roles: [coordinator, executor, reviewer]",
                                                          f"roles: [coordinator, executor, reviewer]\n    {field}"))
        assert err and ("not a calendar date" in err or "YAML error" in err)
    _d, err = parse_orchestration_text(ROSTER.replace("policy:", "substitutions:\n  - {slot: r, use: opus, "
                                                      "decided: '2026-13-01', expires_when: x}\npolicy:"))
    assert err and "substitutions/0/decided" in err


def test_models_list_and_show_survive_an_escaping_profile_path(tmp_path: Path, capsys) -> None:
    repo = make_review_repo(tmp_path, orchestration=ROSTER.replace(PROFILE_REL, "../outside.md"))
    git(repo, "update-ref", "refs/heads/dev", "HEAD")
    for args in (["models", "list", "--repo-root", str(repo)], ["models", "list", "--json", "--repo-root", str(repo)],
                 ["models", "show", "opus", "--repo-root", str(repo)], ["models", "stale", "--repo-root", str(repo)]):
        with pytest.raises(SystemExit) as e:
            models_cli.main(args)
        assert e.value.code == 0
    assert "escapes the repository" in capsys.readouterr().out
