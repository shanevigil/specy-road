"""M15.11 A1-A3: `models roster` builds entries validate accepts; validate and `orchestrate plan` name a
malformed `profile:` with its accepted form; roster examples in docs and the starter use shipped ids."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from specy_road import model_profiles as mp
from specy_road.bundled_scripts import models_cli
from specy_road.bundled_scripts.validate_roadmap import validate_at
from specy_road.orchestrate_plan import Assignment, Candidate, assign_leaf
from specy_road.orchestration_config import effective_config
from specy_road.roster_profile_check import profile_value_problem

from tests.test_models_and_prompt import make_profile_repo, run_main
from tests.test_orchestrate_plan import plan_repo
from specy_road import orchestrate_plan as op

REPO = Path(__file__).resolve().parent.parent
STARTER = REPO / "specy_road" / "templates" / "project" / "roadmap" / "orchestration.yaml"
OPUS_REL = "model-profiles/anthropic-claude/claude-opus-5-5.md"
MALFORMED = "anthropic/claude-opus-5-5"
INVALID = f"invalid profile: {MALFORMED}, accepted form {OPUS_REL}"


# --- A1: models roster ------------------------------------------------------------

def test_models_roster_prints_entries_filled_from_the_shipped_profiles(tmp_path: Path, capsys) -> None:
    repo = make_profile_repo(tmp_path)
    assert run_main(models_cli, "models", "roster", "--executor", "claude-opus-5-5", "--reviewer", "gpt-6.1-sol",
                    "--reviewer", "claude-opus-5-5", "--repo-root", str(repo)) == 0
    cap = capsys.readouterr()
    entries = yaml.safe_load(cap.out)
    assert entries == [
        {"id": "claude-opus-5-5", "family": "anthropic", "profile": OPUS_REL, "harness": "claude-code",
         "roles": ["executor", "reviewer"]},
        {"id": "gpt-6.1-sol", "family": "openai", "profile": "model-profiles/openai-gpt/gpt-6.1-sol.md",
         "harness": "codex", "roles": ["reviewer"]},
    ]
    # the repo has only the Opus profile: the missing one is named with the command that adds it
    assert "refresh-profiles --only gpt-6.1-sol" in cap.err and "claude-opus-5-5`" not in cap.err


def test_models_roster_refuses_an_unknown_profile_with_the_nearest_ids(tmp_path: Path, capsys) -> None:
    repo = make_profile_repo(tmp_path)
    assert run_main(models_cli, "models", "roster", "--executor", "claude-opus-5.5", "--repo-root", str(repo)) == 1
    err = capsys.readouterr().err
    assert "no shipped profile 'claude-opus-5.5'" in err and "nearest: claude-opus-5-5" in err


def test_models_roster_write_round_trips_through_validate(tmp_path: Path, capsys) -> None:
    repo = make_profile_repo(tmp_path)
    path = repo / "roadmap" / "orchestration.yaml"
    before = path.read_text()
    assert run_main(models_cli, "models", "roster", "--executor", "claude-opus-5-5", "--coordinator",
                    "claude-opus-5-5", "--write", "--repo-root", str(repo)) == 0
    assert "added to roadmap/orchestration.yaml: claude-opus-5-5" in capsys.readouterr().out
    text = path.read_text()
    assert text.startswith(before)   # appended inside the roster block, nothing else rewritten
    config, err = effective_config(repo)
    assert err is None
    entry = next(e for e in config["roster"] if e["id"] == "claude-opus-5-5")
    assert entry["profile"] == OPUS_REL and entry["roles"] == ["coordinator", "executor"]
    validate_at(repo, no_overlap_warn=True)
    cap = capsys.readouterr()
    assert "OK: roadmap and registry validate." in cap.out
    assert "claude-opus-5-5'" not in cap.err + cap.out and "invalid profile" not in cap.err
    # a second write adds nothing
    assert run_main(models_cli, "models", "roster", "--executor", "claude-opus-5-5", "--write",
                    "--repo-root", str(repo)) == 0
    assert "already rostered: claude-opus-5-5" in capsys.readouterr().out and path.read_text() == text


def test_models_roster_write_into_the_starter_keeps_its_comments(tmp_path: Path, capsys) -> None:
    repo = make_profile_repo(tmp_path)
    path = repo / "roadmap" / "orchestration.yaml"
    path.write_text(STARTER.read_text())
    assert run_main(models_cli, "models", "roster", "--reviewer", "claude-opus-5-5", "--write",
                    "--repo-root", str(repo)) == 0
    text = path.read_text()
    assert text.count("#") == STARTER.read_text().count("#")
    data = yaml.safe_load(text)
    assert [e["id"] for e in data["roster"]] == ["human", "my-executor", "claude-opus-5-5"]
    assert data["substitutions"] == [] and data["policy"]["max_workers"] == 2


def test_models_roster_write_keeps_an_inline_comment_on_roster_empty_list(tmp_path: Path, capsys) -> None:
    repo = make_profile_repo(tmp_path)
    path = repo / "roadmap" / "orchestration.yaml"
    path.write_text("version: 1\nroster: [] # keep me\npolicy: {reviewers_required: 1}\n")
    assert run_main(models_cli, "models", "roster", "--executor", "claude-opus-5-5", "--write",
                    "--repo-root", str(repo)) == 0
    text = path.read_text()
    assert "# keep me" in text
    assert "roster:" in text.splitlines()[1] or "roster: # keep me" in text or "roster:  # keep me" in text


# --- A2: profile values validated locally; the plan names them ----------------------

def test_validate_names_the_accepted_form_for_a_malformed_profile(tmp_path: Path, capsys) -> None:
    repo = make_profile_repo(tmp_path)
    (repo / "roadmap" / "orchestration.yaml").write_text(
        "version: 1\nroster:\n  - {id: human, family: human, roles: [coordinator, reviewer]}\n"
        f"  - {{id: opus, family: anthropic, profile: {MALFORMED}, harness: claude-code, roles: [executor]}}\n")
    capsys.readouterr()
    validate_at(repo, no_overlap_warn=True)
    err = capsys.readouterr().err
    assert f"warning: roster entry 'opus' in roadmap/orchestration.yaml: {INVALID}" in err


def test_profile_value_problem_accepts_only_a_profile_file_under_model_profiles(tmp_path: Path) -> None:
    repo = make_profile_repo(tmp_path)
    assert profile_value_problem(repo, OPUS_REL) is None
    assert profile_value_problem(repo, MALFORMED) == INVALID
    assert profile_value_problem(repo, "no-such-model") == \
        "invalid profile: no-such-model, accepted form model-profiles/<family-dir>/<profile-id>.md"


def test_plan_reports_an_invalid_profile_and_suppresses_the_may_process_hint(tmp_path: Path) -> None:
    roster = ("version: 1\nroster:\n  - {id: human, family: human, roles: [coordinator, reviewer]}\n"
              f"  - {{id: opus, family: anthropic, profile: {MALFORMED}, roles: [executor]}}\n"
              "policy: {reviewers_required: 1}\n")
    plan, err = op.build_orchestration_plan(plan_repo(tmp_path, roster))
    assert err is None and plan is not None
    problems = plan.batches[0][0].problems
    assert problems == [f"opus: {INVALID}"]
    assert not any("not committed" in p or "may_process" in p for p in problems)


def test_worktree_plan_reports_invalid_profile_form_for_a_malformed_missing_path(tmp_path: Path) -> None:
    roster = ("version: 1\nroster:\n  - {id: human, family: human, roles: [coordinator, reviewer]}\n"
              f"  - {{id: opus, family: anthropic, profile: {MALFORMED}, roles: [executor]}}\n"
              "policy: {reviewers_required: 1}\n")
    plan, err = op.build_orchestration_plan(plan_repo(tmp_path, roster), roster_from_worktree=True)
    assert err is None and plan is not None
    assert plan.batches[0][0].problems == [f"opus: {INVALID}"]


def test_committed_plan_refuses_a_malformed_profile_even_when_a_file_exists_at_that_path(tmp_path: Path) -> None:
    from tests.review_repo_helpers import git

    roster = ("version: 1\nroster:\n  - {id: human, family: human, roles: [coordinator, reviewer]}\n"
              f"  - {{id: opus, family: anthropic, profile: {MALFORMED}, roles: [executor]}}\n"
              "policy: {reviewers_required: 1}\n")
    repo = plan_repo(tmp_path, roster)
    wrong = repo / MALFORMED
    wrong.parent.mkdir(parents=True, exist_ok=True)
    wrong.write_text((REPO / "specy_road" / "templates" / "project" / "model-profiles"
                      / "anthropic-claude" / "claude-opus-5-5.md").read_text(encoding="utf-8"), encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "wrong-path profile")
    plan, err = op.build_orchestration_plan(repo)
    assert err is None and plan is not None
    assert plan.batches[0][0].problems == [f"opus: {INVALID}"]


def test_the_may_process_hint_stays_when_no_entry_was_dropped() -> None:
    node = {"id": "M1.1", "sensitivity": "internal"}
    config = {"policy": {"reviewers_required": 0, "reviewers_distinct_families": False}}
    a = assign_leaf(node, [Candidate({"id": "x", "family": "f", "roles": ["executor"]}, None)], config)
    assert any("no eligible executor: needs a rostered executor with may_process" in p for p in a.problems)
    bad = mp.Profile(Path("x.md"), {}, errors=[INVALID])
    a = assign_leaf(node | {"sensitivity": "public"},
                    [Candidate({"id": "x", "family": "f", "roles": ["executor"]}, bad)], config)
    assert a.problems == [f"x: {INVALID}"] and isinstance(a, Assignment)


# --- A3: roster examples name shipped ids -------------------------------------------

ROSTER_ID = re.compile(r"(?:^\s*#?\s*-\s+id:\s*|\{id:\s*)([A-Za-z0-9._-]+)", re.M)
PROFILE_VALUE = re.compile(r"^\s*#?\s*profile:\s*(model-profiles/\S+\.md)", re.M)


def example_problems(text: str, shipped: list[mp.Profile]) -> list[str]:
    """Roster example ids that look like a model id (they carry a version digit) and match no shipped
    profile file name, api_id or alias, and example ``profile:`` paths no shipped profile has.
    Digit-free ids (``human``, ``opus``, ``my-executor``) are labels, which the docs allow."""
    out = [f"id {m}" for m in ROSTER_ID.findall(text)
           if re.search(r"\d", m) and not any(p.for_id(m) for p in shipped)]
    root = mp.bundled_profiles_root()
    return out + [f"profile {v}" for v in PROFILE_VALUE.findall(text) if not (root / v).is_file()]


def test_the_scan_catches_a_dotted_opus_id_and_a_wrong_profile_path() -> None:
    shipped = mp.list_profiles(mp.bundled_profiles_root())
    sample = ("  - id: claude-opus-5.5\n    profile: model-profiles/anthropic/claude-opus-5.5.md\n"
              "  - {id: claude-opus-5-5, family: anthropic}\n  - id: human\n")
    assert example_problems(sample, shipped) == ["id claude-opus-5.5",
                                                 "profile model-profiles/anthropic/claude-opus-5.5.md"]


def test_docs_and_starter_roster_examples_name_shipped_profile_ids() -> None:
    shipped = mp.list_profiles(mp.bundled_profiles_root())
    files = [*sorted((REPO / "docs").glob("orchestration*.md")),
             REPO / "docs" / "design-notes" / "model-aware-orchestration-proposal.md", STARTER]
    bad = {f.relative_to(REPO).as_posix(): p for f in files if (p := example_problems(f.read_text(), shipped))}
    assert not bad, bad
    assert "id: claude-opus-5-5" in STARTER.read_text() and f"profile: {OPUS_REL}" in STARTER.read_text()
