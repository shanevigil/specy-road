"""Regression tests for the slice-1 cross-family review findings (merge commits,
policy source, worktrees, remote-only branches, per-model counting, …)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests.review_repo_helpers import NODE, commit_file, git, make_review_repo, review_text
from tests.test_review_gate import TWO_FAMILIES

from specy_road.bundled_scripts import mark_implementation_reviewed as mir
from specy_road.bundled_scripts import review_cli, review_packet as rp
from specy_road.review_files import reviews_dir
from specy_road.review_gate import evaluate_gate, review_required
from specy_road.review_target import ReviewTargetError, resolve_target, same_commit


def _head(repo: Path) -> str:
    return git(repo, "rev-parse", "HEAD")


def _record(repo: Path, model: str, *, name: str | None = None, **kw) -> None:
    d = reviews_dir(repo, "M1.1")
    d.mkdir(parents=True, exist_ok=True)
    commit = kw.pop("commit", None) or _head(repo)
    text = review_text(commit, model=model, **kw)
    (d / (name or f"REVIEW-{model}.md")).write_text(text)


def _gate(repo: Path, ref: str = "HEAD"):
    t = resolve_target(repo, "M1.1", ref)
    return evaluate_gate(repo, NODE, t.commit)


def test_a_merge_after_approval_is_new_work(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path)
    _record(repo, "human")
    assert _gate(repo).passed
    git(repo, "checkout", "-q", "-b", "side", "dev")
    commit_file(repo, "src/sneak.py", "x\n", "side work")
    git(repo, "checkout", "-q", "feature/rm-thing")
    git(repo, "merge", "-q", "--no-ff", "-m", "merge side", "side")
    g = _gate(repo)
    assert g.commit == _head(repo)
    assert not g.passed and g.stale


def test_feature_branch_cannot_lower_committed_policy(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path, orchestration=TWO_FAMILIES)
    _record(repo, "opus")
    lowered = TWO_FAMILIES.replace("reviewers_required: 2, reviewers_distinct_families: true",
                                   "reviewers_required: 1")
    commit_file(repo, "roadmap/orchestration.yaml", lowered, "lower the bar")
    _record(repo, "opus")
    g = _gate(repo)
    assert g.required == 2 and g.distinct_families and not g.passed
    # An uncommitted (or skip-worktree) edit is ignored the same way.
    (repo / "roadmap" / "orchestration.yaml").write_text("version: 1\n")
    assert _gate(repo).required == 2


def test_turning_the_gate_off_on_a_branch_does_not_turn_it_off(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path)
    gw = repo / "roadmap" / "git-workflow.yaml"
    commit_file(repo, "roadmap/git-workflow.yaml",
                gw.read_text().replace("finish: true", "finish: false"), "gate off")
    assert review_required(repo)


def test_policy_change_is_flagged_in_the_packet(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path)
    commit_file(repo, "roadmap/orchestration.yaml", "version: 1\n", "policy edit")
    text = rp.build_packet(repo, "M1.1", ref=None, verify_cmds=[])
    assert "`roadmap/orchestration.yaml`  **← review policy changed on this branch**" in text
    assert "This branch edits review policy" in text


def test_packet_reads_committed_summary_and_exempts_work_files(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path)
    commit_file(repo, "work/brief-M1.1.md", "# brief\n", "brief")
    commit_file(repo, "work/implementation-summary-M1.1.md", "## Summary\nCommitted.\n", "summary")
    git(repo, "checkout", "-q", "dev")
    text = rp.build_packet(repo, "M1.1", ref=None, verify_cmds=[])
    assert "Committed." in text
    assert "- `work/brief-M1.1.md`\n" in text
    assert "1 path(s) outside the touch zones" in text  # only docs/x.md


def test_reviews_live_in_the_main_worktree(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path)
    git(repo, "checkout", "-q", "dev")
    wt = tmp_path / "wt"
    git(repo, "worktree", "add", "-q", str(wt), "feature/rm-thing")
    # Written in the coordinator's (main) checkout, for the feature tip.
    _record(repo, "human", commit=git(repo, "rev-parse", "feature/rm-thing"))
    assert reviews_dir(wt, "M1.1") == reviews_dir(repo, "M1.1")
    assert evaluate_gate(wt, NODE, resolve_target(wt, "M1.1", "HEAD").commit).passed


def test_remote_only_branch_is_reviewed_and_a_missing_one_is_an_error(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path)
    tip = _head(repo)
    bare = tmp_path / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True)
    git(repo, "remote", "add", "origin", str(bare))
    git(repo, "push", "-q", "origin", "dev", "feature/rm-thing")
    git(repo, "checkout", "-q", "dev")
    git(repo, "branch", "-q", "-D", "feature/rm-thing")
    t = resolve_target(repo, "M1.1")
    assert t.ref == "origin/feature/rm-thing" and t.commit == tip
    git(repo, "update-ref", "-d", "refs/remotes/origin/feature/rm-thing")
    with pytest.raises(ReviewTargetError, match="neither a local branch"):
        resolve_target(repo, "M1.1")


def test_one_vote_per_model_and_records_must_match_the_node(tmp_path: Path) -> None:
    orch = "version: 1\nroster:\n  - {id: human, family: human, roles: [reviewer]}\npolicy: {reviewers_required: 2}\n"
    repo = make_review_repo(tmp_path, orchestration=orch)
    _record(repo, "human")
    _record(repo, "human", name="REVIEW-human-again.md")
    g = _gate(repo)
    assert len(g.approvals) == 1 and not g.passed
    assert any("already counts" in why for _r, why in g.ineligible)
    other = review_text(_head(repo)).replace("node_id: M1.1", "node_id: M7.7")
    (reviews_dir(repo, "M1.1") / "REVIEW-human-again.md").write_text(other)
    assert any("not 'M1.1'" in " ".join(r.errors) for r in _gate(repo).invalid)


def test_a_block_beats_the_same_models_approval(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path)
    _record(repo, "human")
    _record(repo, "human", name="REVIEW-human-2.md", verdict="block", a1="fail")
    g = _gate(repo)
    assert g.blocks and not g.approvals and not g.passed


def test_substitute_family_comes_from_the_roster(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path, orchestration=TWO_FAMILIES)
    _record(repo, "opus")
    text = review_text(_head(repo), model="astra").replace("model: astra", "model: astra\nfamily: google")
    (reviews_dir(repo, "M1.1") / "REVIEW-astra.md").write_text(text)
    g = _gate(repo)
    assert {a.family for a in g.approvals} == {"anthropic", "openai"}


def test_same_commit_asks_git(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path)
    head = _head(repo)
    assert same_commit(repo, head[:7], head)
    assert not same_commit(repo, head[:7] + "0000", head)
    assert not same_commit(repo, "abcdef1", "abcdef12deadbeef")


def _cli(*args: str) -> int:
    with pytest.raises(SystemExit) as e:
        review_cli.main(list(args))
    return e.value.code


def test_status_exit_codes_and_leftover_directories(tmp_path: Path, capsys) -> None:
    repo = make_review_repo(tmp_path)
    assert _cli("handoff", "status", "NOPE", "--repo-root", str(repo)) == 1
    reviews_dir(repo, "M1.1").mkdir(parents=True)
    (repo / "roadmap" / "registry.yaml").write_text("version: 1\nentries: []\n")
    capsys.readouterr()
    assert _cli("handoff", "status", "--repo-root", str(repo)) == 0
    assert "M1.1: unclaimed" in capsys.readouterr().out


def test_packet_with_an_unresolvable_ref_exits_1(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path)
    with pytest.raises(SystemExit) as e:
        rp.main(["M1.1", "--ref", "nosuchbranch", "--repo-root", str(repo)])
    assert e.value.code == 1


def test_non_tty_without_yes_still_refuses_when_the_gate_passes(tmp_path: Path, monkeypatch) -> None:
    repo = make_review_repo(tmp_path)
    (repo / "work").mkdir(exist_ok=True)
    (repo / "work" / "implementation-summary-M1.1.md").write_text("## Summary\nx\n")
    _record(repo, "human")
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    with pytest.raises(SystemExit) as e:
        mir.main(["--repo-root", str(repo)])
    assert e.value.code == 1


# --- round 2 (verification review) -------------------------------------------

def test_an_ours_merge_after_approval_is_new_work(tmp_path: Path) -> None:
    """`-s ours` leaves the tree equal to its first parent but decides what lands."""
    repo = make_review_repo(tmp_path)
    _record(repo, "human")
    git(repo, "checkout", "-q", "-b", "side", "dev")
    commit_file(repo, "src/security.py", "fix\n", "upstream fix")
    git(repo, "checkout", "-q", "feature/rm-thing")
    git(repo, "merge", "-q", "-s", "ours", "--no-ff", "-m", "discard upstream", "side")
    g = _gate(repo)
    assert g.commit == _head(repo) and g.stale and not g.passed


def test_policy_branch_cannot_be_redirected_from_the_working_tree(tmp_path: Path, monkeypatch) -> None:
    repo = make_review_repo(tmp_path, orchestration=TWO_FAMILIES)
    _record(repo, "opus")
    git(repo, "branch", "-q", "relaxed", "dev")
    gw = repo / "roadmap" / "git-workflow.yaml"
    git(repo, "update-index", "--skip-worktree", "roadmap/git-workflow.yaml", "roadmap/orchestration.yaml")
    gw.write_text(gw.read_text().replace("integration_branch: dev", "integration_branch: nonexistent")
                  .replace("finish: true", "finish: false"))
    (repo / "roadmap" / "orchestration.yaml").write_text(
        "version: 1\nroster:\n  - {id: opus, family: anthropic, roles: [reviewer]}\n")
    monkeypatch.setenv("SPECY_ROAD_INTEGRATION_BRANCH", "relaxed")
    assert git(repo, "status", "--porcelain") == ""  # hidden from status
    g = _gate(repo)
    assert g.required == 2 and g.distinct_families and not g.passed
    assert review_required(repo)


def test_a_missing_integration_branch_fails_closed(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path)
    _record(repo, "human")
    gw = repo / "roadmap" / "git-workflow.yaml"
    commit_file(repo, "roadmap/git-workflow.yaml",
                gw.read_text().replace("integration_branch: dev", "integration_branch: nonexistent")
                .replace("finish: true", "finish: false"), "redirect")
    _record(repo, "human")
    g = _gate(repo)
    assert not g.passed and "neither" in (g.config_error or "")
    assert review_required(repo)


def test_interactive_human_approval_from_a_linked_worktree(tmp_path: Path, monkeypatch) -> None:
    repo = make_review_repo(tmp_path)
    git(repo, "checkout", "-q", "dev")
    wt = tmp_path / "wt"
    git(repo, "worktree", "add", "-q", str(wt), "feature/rm-thing")
    (wt / "work").mkdir()
    (wt / "work" / "implementation-summary-M1.1.md").write_text("## Summary\nx\n")
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda _p="": "a")
    with pytest.raises(SystemExit) as e:
        mir.main(["--repo-root", str(wt)])
        raise SystemExit(0)
    assert (e.value.code or 0) == 0
    assert (reviews_dir(repo, "M1.1") / "REVIEW-human.md").is_file()
    assert "Reviewed-by: human" in git(wt, "log", "-1", "--format=%B")


def test_naming_an_unclaimed_node_exits_1(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path)
    (repo / "roadmap" / "registry.yaml").write_text("version: 1\nentries: []\n")
    assert _cli("handoff", "status", "M1.1", "--repo-root", str(repo)) == 1


def test_a_sha_lookalike_inside_a_multiline_string_is_not_the_sha(tmp_path: Path) -> None:
    from specy_road.review_files import load_ready

    text = (
        "---\nnode_id: M1.1\nagent: x\nbranch: feature/rm-thing\nchanged_paths: [src/a.py]\n"
        "verify:\n  - cmd: git log\n    exit: 0\n    tail: \"line1\ncommit: 0000000\nline3\"\n"
        "commit: \"abc1234\"\nbase: \"def5678\"\n---\nbody\n"
    )
    p = tmp_path / "READY-x.md"
    p.write_text(text)
    r = load_ready(p)
    assert r.ok, r.errors
    assert r.data["commit"] == "abc1234" and r.data["base"] == "def5678"
    # A column-0 `---` inside a quoted string is a YAML document separator:
    # the file is rejected outright rather than read with a wrong SHA.
    p.write_text(text.replace("commit: 0000000\n", "commit: 0000000\n--- a/file\n"))
    bad = load_ready(p)
    assert not bad.ok and "not valid YAML" in bad.errors[0]


def test_scaffold_ships_hand_off_templates_and_the_prompt_names_them(tmp_path: Path) -> None:
    from specy_road.bundled_scripts.do_next_prompt import _finish_instruction_lines
    from specy_road.init_project import run_init_project
    from specy_road.review_files import load_ready, load_review

    run_init_project(tmp_path)
    ready = tmp_path / "work" / "handoff-ready.template.md"
    review = tmp_path / "work" / "review-record.template.md"
    assert ready.is_file() and review.is_file()
    # Only the placeholder SHAs fail validation.
    assert all("commit" in e or "base" in e for e in load_ready(ready).errors)
    assert all("commit" in e for e in load_review(review).errors)
    (tmp_path / "roadmap" / "git-workflow.yaml").write_text(
        "version: 1\nintegration_branch: main\nremote: origin\n"
        "require_implementation_review_before_finish: true\n")
    text = "\n".join(_finish_instruction_lines("M1.1", tmp_path, on_complete="merge"))
    assert "work/handoff-ready.template.md" in text and "work/review-record.template.md" in text
