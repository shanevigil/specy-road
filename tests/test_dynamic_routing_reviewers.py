"""M11.33: a reviewer whose harness routes models dynamically does not count as an independent family by default."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from tests.review_repo_helpers import NODE, git, make_review_repo, review_text
from tests.test_worker_cli import run_worker_cli, wait_for_worker
from tests.worker_repo_helpers import FAKE, make_worker_repo, worker_roster

from specy_road import worker_runner as wr
from specy_road import worker_state as ws
from specy_road.orchestration_pinned import pinned_config
from specy_road.orchestration_routing import entry_routing, routing_problem
from specy_road.review_eligible import reviewer_eligibility
from specy_road.review_files import reviews_dir
from specy_road.review_gate import evaluate_gate
from specy_road.worker_adapters import Launch


def _roster(rev: str, *, distinct: bool = True) -> str:
    return ("version: 1\nroster:\n  - {id: opus, family: anthropic, roles: [reviewer]}\n"
            f"  - {{id: rev, family: openai, roles: [reviewer]{rev}}}\n"
            f"policy: {{reviewers_required: 2, reviewers_distinct_families: {str(distinct).lower()}}}\n")


def _gate(tmp_path: Path, rev: str, *, distinct: bool = True, rev_verdict: str = "approve"):
    repo = make_review_repo(tmp_path, orchestration=_roster(rev, distinct=distinct))
    head = git(repo, "rev-parse", "HEAD")
    d = reviews_dir(repo, "M1.1")
    d.mkdir(parents=True)
    (d / "REVIEW-opus.md").write_text(review_text(head, model="opus"))
    (d / "REVIEW-rev.md").write_text(review_text(head, model="rev", verdict=rev_verdict,
                                                 a1="pass" if rev_verdict == "approve" else "fail"))
    return repo, evaluate_gate(repo, NODE, head)


@pytest.mark.parametrize("rev, counts", [
    ("", True),                                                   # routing absent: fixed
    (", routing: fixed", True),
    (", routing: dynamic", False),
    (", routing: dynamic, pinned: true", True),
    (", harness: cursor", False),                                 # A4: no harness_model, no profile: no --model
    (", harness: cursor, harness_model: auto", False),            # A4: Cursor's Auto
    (", harness: cursor, channels: {cli: 'agent -p {prompt}'}", False),
    (""", harness: cursor, channels: {cli: "agent -p --model gpt-5.6-sol '{prompt}"}""", False),   # unbalanced quote
    (", harness: cursor, channels: {cli: 'printf %s --model gpt-5.6-sol >/dev/null; agent -p {prompt}'}", False),  # decoy
    (", harness: cursor, channels: {cli: 'agent -p --model gpt-5.6-sol {prompt} 2>&1'}", True),   # a redirection
    (""", harness: cursor, channels: {cli: 'agent -p --model "${MODEL:-auto}" {prompt}'}""", False),  # sh expands it
    (""", harness: cursor, channels: {cli: 'agent -p --model "" {prompt}'}""", False),            # an empty model
    (", harness: cursor, channels: {cli: 'agent -p --model gpt-5.6-sol {prompt} \\'}", False),   # trailing backslash
    (", harness: cursor, channels: {cli: 'agent -p --model=gpt-5.6-sol {prompt}'}", True),
    (", harness: cursor, harness_model: gpt-5.6-sol-high", True),
    (", harness: cursor, pinned: true", True),
])
def test_dynamic_routing_approval_does_not_count_toward_distinct_families(tmp_path: Path, rev: str, counts: bool) -> None:
    """A1/A4: fixed and pinned entries count; a dynamic one is listed with the reason, in handoff status too."""
    repo, g = _gate(tmp_path, rev)
    assert g.passed is counts and g.approval_count == (2 if counts else 1)
    if not counts:
        assert any(("routes models dynamically" in p or "harness_model" in p) and "pinned: true" in p for p in g.problems())
        row = next(r for r in reviewer_eligibility(repo, NODE, g, None) if r["model"] == "rev")
        assert not row["eligible"] and "pinned: true" in row["reason"]
        assert "harness_model" in row["reason"] or "routes models dynamically" in row["reason"]


def test_dynamic_routing_still_blocks_and_counts_without_distinct_families(tmp_path: Path) -> None:
    """A1: only the distinct-family count is affected: a block from a dynamic entry blocks, and with
    reviewers_distinct_families off its approval counts."""
    _repo, blocked = _gate(tmp_path / "a", ", routing: dynamic", rev_verdict="block")
    assert [b.model for b in blocked.blocks] == ["rev"] and not blocked.passed
    _repo, plain = _gate(tmp_path / "b", ", routing: dynamic", distinct=False)
    assert plain.passed and plain.approval_count == 2


@pytest.mark.parametrize("told", ["claude-opus-5-5", "claude-sonnet-5-5"])
def test_usage_keeps_requested_and_observed_model_and_sync_flags_a_mismatch(tmp_path: Path, capsys, told: str) -> None:
    """M11.33 A2: the turn's usage event keeps the --model the harness was told and the model its init line
    reported; when they differ, `worker sync` prints the mismatch."""
    repo, script = make_worker_repo(tmp_path)
    rec = ws.create_record(repo, "M1.1", "claude-code", "opus", repo)
    spec = tmp_path / "turn.json"
    spec.write_text(json.dumps({"lines": [
        {"type": "system", "subtype": "init", "session_id": "s-1", "model": "claude-opus-5-5"},
        {"type": "result", "subtype": "success", "result": "done", "session_id": "s-1", "total_cost_usd": 0.01}]}))
    wr.run(repo, rec.worker_id, Launch([sys.executable, str(script), str(spec), "--model", told]))
    usage = next(e.detail for e in ws.events_since(repo, rec.worker_id) if e.type == "usage")
    assert (usage["requested_model"], usage["observed_model"]) == (told, "claude-opus-5-5")
    capsys.readouterr()
    assert run_worker_cli("worker", "sync", "--repo-root", str(repo)) == 0
    mismatch = "model mismatch: told claude-sonnet-5-5, harness reported claude-opus-5-5"
    assert (mismatch in capsys.readouterr().out) is (told == "claude-sonnet-5-5")


def test_claude_code_unknown_profile_api_id_routes_dynamic_and_names_harness_model(tmp_path: Path) -> None:
    """M15.31 A4: any harness whose resolved model is none is dynamic; the gate names harness_model before pinned."""
    from tests.test_models_and_prompt import OPUS, commit_profile, make_profile_repo

    repo = make_profile_repo(tmp_path)
    roster = repo / "roadmap" / "orchestration.yaml"
    roster.write_text(roster.read_text().replace(
        "    roles: [coordinator, executor, reviewer]",
        "    roles: [coordinator, executor, reviewer]\n    harness: claude-code"))
    prof = repo / "model-profiles" / "anthropic-claude" / OPUS.name
    prof.write_text(prof.read_text().replace("api_id: claude-opus-5-5", "api_id: unknown"))
    commit_profile(repo)
    config, err = pinned_config(repo)
    assert err is None
    entry = next(e for e in config["roster"] if e.get("id") == "opus")
    assert entry_routing(repo, entry) == "dynamic"
    config["policy"] = {"reviewers_distinct_families": True}
    why = routing_problem(repo, config, {"model": "opus", "verdict": "approve"})
    assert why and "harness_model" in why and "pinned: true" in why


@pytest.mark.parametrize("prologue, told, requested", [
    ("", "fake", "fake"),
    ("", "claude-sonnet-5-5", "claude-sonnet-5-5"),
    ("printf %s --model decoy >/dev/null; ", "claude-sonnet-5-5", None),   # two commands: which --model is unknown
    ("", '"${SR_UNSET_MODEL:-auto}"', None),   # the shell expands it to auto: not a literal model
])
def test_custom_cli_model_is_requested_and_sync_flags_a_mismatch(tmp_path: Path, capsys, prologue: str, told: str,
                                                                  requested: str | None) -> None:
    """M11.33 A2: a roster channels.cli that is one command passing its own --model (run as `sh -c`) records it as
    requested_model, and `worker sync` flags it when the harness's init line reports another (the fake harness
    reports `fake`); in a command list, or when the shell expands the value, the harness's model is unknown, so
    neither the decoy, the unexpanded text nor a mismatch is recorded."""
    script = tmp_path / "fake.py"
    script.write_text(FAKE)
    cli = f"{prologue}{sys.executable} {script} {{prompt}} --model {told}"
    repo = make_review_repo(tmp_path, orchestration=worker_roster(cli))
    (repo / ".gitignore").write_text("work/\n")
    git(repo, "add", ".gitignore")
    git(repo, "commit", "-qm", "ignore work")
    run_worker_cli("worker", "delegate", "M1.1", "--model", "opus", "--repo-root", str(repo))
    wait_for_worker(repo, "w-0001")
    usage = next(e.detail for e in ws.events_since(repo, "w-0001") if e.type == "usage")
    assert (usage["requested_model"], usage["observed_model"]) == (requested, "fake")
    capsys.readouterr()
    assert run_worker_cli("worker", "sync", "--repo-root", str(repo)) == 0
    out = capsys.readouterr().out
    assert ("model mismatch: told claude-sonnet-5-5, harness reported fake" in out) is (requested == "claude-sonnet-5-5")
    assert "decoy" not in out and "SR_UNSET_MODEL" not in out
