"""M15.22: local decisions, the PR body footer, the summary commit rule, and root ``land: local``."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
import yaml

from specy_road.agent_ignores import GITIGNORE_LINES
from specy_road.bundled_scripts import do_next_prompt as dnp
from specy_road.bundled_scripts import role_prompt
from specy_road.decisions import plan_preferences, read_decisions
from specy_road.finish_land_local import land_on_integration
from specy_road.finish_pr_body import write_pr_body
from specy_road.git_workflow_config import validate_git_workflow_dict
from specy_road.bundled_scripts.validate_roadmap import validate_git_workflow_contract
from specy_road.workflow_prefs import (
    implementation_summary_rule,
    pr_body_footer,
    root_land,
    summary_ignore_rules,
    summary_rule_notice,
    warn_summary_rule,
)
from tests.decisions_repo_helpers import add_args, decisions_repo, run_decisions
from tests.review_repo_helpers import git
from tests.test_models_and_prompt import make_profile_repo

_ACCESSORS = {"pr_body_footer": pr_body_footer, "implementation_summary": implementation_summary_rule,
              "land": lambda root, _node_id: root_land(root)}
GW = "version: 1\nintegration_branch: master\nremote: origin\n"


# --- A1: decisions add --local ---------------------------------------------------------------

def _prefer(repo: Path, *extra: str) -> list[str]:
    return ["decisions", "add", "--repo-root", str(repo), "--kind", "preference", *extra]


def test_local_preference_is_merged_over_the_tracked_ledger(tmp_path: Path, capsys) -> None:
    repo = decisions_repo(tmp_path)
    shared, local = repo / "roadmap" / "decisions.yaml", repo / "roadmap" / "decisions.local.yaml"
    assert run_decisions(_prefer(repo, "--summary", "Team rule: docs go to sol", "--id", "Pteam")) == 0
    assert run_decisions(_prefer(repo, "--summary", "Shared rule", "--id", "Pboth")) == 0
    assert run_decisions(_prefer(repo, "--local", "--summary", "My rule wins here", "--id", "Pboth")) == 0
    assert run_decisions(_prefer(repo, "--local", "--summary", "Only mine")) == 0   # next id free in both ledgers
    assert [e["id"] for e in read_decisions(shared)["entries"]] == ["Pteam", "Pboth"]
    assert [e["id"] for e in read_decisions(local)["entries"]] == ["Pboth", "P1"]
    capsys.readouterr()

    assert run_decisions(["decisions", "list", "--json", "--repo-root", str(repo)]) == 0
    listed = {e["id"]: e for e in json.loads(capsys.readouterr().out)}
    assert listed["Pboth"]["summary"] == "My rule wins here" and listed["Pboth"]["source"] == "local"
    assert listed["Pteam"]["source"] == "shared" and listed["P1"]["source"] == "local"
    assert run_decisions(["decisions", "list", "--repo-root", str(repo)]) == 0
    out = capsys.readouterr().out
    assert "Shared rule" not in out and "My rule wins here" in out
    assert next(ln for ln in out.splitlines() if ln.startswith("Pboth ")).endswith("(local)")
    assert next(ln for ln in out.splitlines() if ln.startswith("Pteam ")).endswith("(shared)")

    prefs, err = plan_preferences(repo)
    assert err is None and {e["id"]: e["summary"] for e in prefs}["Pboth"] == "My rule wins here"
    assert run_decisions(["decisions", "close", "Pboth", "--answer", "done", "--repo-root", str(repo)]) == 0
    assert read_decisions(local)["entries"][0]["status"] == "closed"
    assert read_decisions(shared)["entries"][1]["status"] == "open"   # the tracked ledger is untouched


def test_local_decision_and_broken_local_ledger(tmp_path: Path, capsys) -> None:
    repo = decisions_repo(tmp_path)
    assert run_decisions(add_args(repo, "--local")) == 0
    assert not (repo / "roadmap" / "decisions.yaml").is_file()
    (repo / "roadmap" / "decisions.local.yaml").write_text("version: 1\nentries:\n  - id: P1\n", encoding="utf-8")
    capsys.readouterr()
    assert run_decisions(["decisions", "list", "--repo-root", str(repo)]) == 1
    assert "decisions.schema: roadmap/decisions.local.yaml fails its schema" in capsys.readouterr().err
    assert plan_preferences(repo)[1].startswith("roadmap/decisions.local.yaml fails its schema")


def test_local_ledger_is_in_the_managed_ignore_block() -> None:
    assert "roadmap/decisions.local.yaml" in GITIGNORE_LINES


# --- A2: pr_body_footer ----------------------------------------------------------------------

def _pr_body(tmp_path: Path, gw: str) -> str:
    (tmp_path / "roadmap").mkdir()
    (tmp_path / "roadmap" / "git-workflow.yaml").write_text(gw, encoding="utf-8")
    kw = dict(node_id="M9.9", title="T", codename=None, branch="feature/rm-t", integration_branch="main")
    return write_pr_body(work_dir=tmp_path / "work", **kw).read_text(encoding="utf-8")


def test_pr_body_footer_is_appended(tmp_path: Path) -> None:
    body = _pr_body(tmp_path, GW + "pr_body_footer: 'Generated with Tool X'\n")
    assert body.endswith("</details>\n\nGenerated with Tool X\n")


def test_pr_body_without_footer_is_unchanged(tmp_path: Path) -> None:
    assert _pr_body(tmp_path, GW).endswith("</details>\n")


BASE = {"version": 1, "integration_branch": "main", "remote": "origin"}


@pytest.mark.parametrize("key,value,expected", [
    ("pr_body_footer", "Tool X", "Tool X"),
    ("pr_body_footer", "  Tool X\n", "Tool X"),   # surrounding whitespace is stripped, the text kept
    ("pr_body_footer", "line one\nline two", "line one\nline two"),
    ("implementation_summary", "commit", "commit"),
    ("implementation_summary", "local", "local"),
    ("land", "push", "push"),
    ("land", "local", "local"),
])
def test_every_schema_valid_preference_takes_effect(tmp_path: Path, key: str, value: str, expected: str) -> None:
    """Whatever the schema accepts, the accessor honours: no valid value reads as unset."""
    assert validate_git_workflow_dict({**BASE, key: value}) is None
    (tmp_path / "roadmap").mkdir()
    (tmp_path / "roadmap" / "git-workflow.yaml").write_text(yaml.safe_dump({**BASE, key: value}), encoding="utf-8")
    assert _ACCESSORS[key](tmp_path, "M1.1") == expected


@pytest.mark.parametrize("key,value", [
    ("pr_body_footer", ""), ("pr_body_footer", " "), ("pr_body_footer", "\n"), ("pr_body_footer", " \t\n "),
    ("pr_body_footer", 3), ("pr_body_footer", None), ("pr_body_footer", ["x"]),
    ("implementation_summary", ""), ("implementation_summary", " "), ("implementation_summary", "Commit"),
    ("implementation_summary", "push"), ("implementation_summary", None), ("implementation_summary", True),
    ("land", ""), ("land", " "), ("land", "Local"), ("land", "manual"), ("land", None), ("land", 1),
])
def test_schema_refuses_what_the_workflow_would_not_honour(tmp_path: Path, capsys, key: str, value) -> None:
    """Empty, whitespace-only, unknown and wrongly typed values fail validate instead of reading as unset."""
    assert validate_git_workflow_dict({**BASE, key: value}) is not None
    (tmp_path / "roadmap").mkdir()
    (tmp_path / "roadmap" / "git-workflow.yaml").write_text(yaml.safe_dump({**BASE, key: value}), encoding="utf-8")
    with pytest.raises(SystemExit):
        validate_git_workflow_contract(tmp_path)
    assert key in capsys.readouterr().err


# --- A3: implementation_summary: commit | local ----------------------------------------------

def _pickup_prompt(repo: Path, gw_extra: str = "", node_id: str = "M1.1") -> str:
    (repo / "roadmap").mkdir(exist_ok=True)
    (repo / "roadmap" / "git-workflow.yaml").write_text(
        GW + "require_implementation_review_before_finish: true\n" + gw_extra, encoding="utf-8")
    brief = repo / "work" / f"brief-{node_id}.md"
    brief.parent.mkdir(parents=True, exist_ok=True)
    brief.write_text("# brief\n", encoding="utf-8")
    node = {"id": node_id, "type": "task", "title": "Leaf", "status": "Not Started", "codename": "leaf",
            "node_key": "22222222-2222-4222-8222-222222222222"}
    return dnp.write_agent_prompt(node, [node], brief, repo_root=repo, work_dir=repo / "work").read_text()


def test_pickup_prompt_follows_implementation_summary(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    commit = _pickup_prompt(tmp_path)
    assert "and commit it on the feature branch by explicit path" in commit
    local = _pickup_prompt(tmp_path, "implementation_summary: local\n")
    assert "leave it uncommitted" in local and "commit it on the feature branch" not in local
    assert summary_rule_notice(tmp_path, ["M1.1"]) is None
    for text in (commit, local):
        assert "add -f" not in text and "--force" not in text


def test_ignored_summary_wins_over_commit_and_validate_says_so(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / ".gitignore").write_text("work/implementation-summary-*.md\n", encoding="utf-8")
    text = _pickup_prompt(tmp_path, "implementation_summary: commit\n")
    assert "leave it uncommitted" in text and "add -f" not in text
    notice = summary_rule_notice(tmp_path, ["M1.1"])
    assert notice and ".gitignore:1:work/implementation-summary-*.md" in notice and "the ignore rule wins" in notice
    (tmp_path / ".gitignore").write_text("work/*\n!work/implementation-summary-*.md\n", encoding="utf-8")
    assert summary_rule_notice(tmp_path, ["M1.1"]) is None   # a negated rule un-ignores it


@pytest.mark.parametrize("ignore,ignored", [
    ("work/implementation-summary-M1.1.md\n", {"M1.1"}),   # one leaf's exact filename
    ("work/implementation-summary-M1.*.md\n", {"M1.1", "M1.2"}),
    ("work/implementation-summary-M2*.md\n", {"M2.10"}),
    ("work/implementation-summary-*.md\n!work/implementation-summary-M1.2.md\n", {"M1.1", "M2.10"}),   # negation
    ("work/*\n!work/implementation-summary-M1.1.md\n", {"M1.2", "M2.10"}),
    ("work/brief-*.md\n", set()),
])
def test_each_leaf_asks_git_about_its_own_summary_path(tmp_path: Path, capsys, ignore: str, ignored: set[str]) -> None:
    """R1: git is asked about the exact path of each leaf's summary, never a sample path, so a rule that
    matches some ids and not others decides per leaf, in the pickup prompt and in validate's notice."""
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / ".gitignore").write_text(ignore, encoding="utf-8")
    ids = ["M1.1", "M1.2", "M2.10"]
    assert set(summary_ignore_rules(tmp_path, ids)) == ignored
    for node_id in ids:
        text = _pickup_prompt(tmp_path, node_id=node_id)
        assert ("leave it uncommitted" in text) is (node_id in ignored), node_id
        assert "add -f" not in text
    nodes = [{"id": "M1"}, *({"id": i, "parent_id": "M1"} for i in ids)]
    warn_summary_rule(tmp_path, nodes)
    out = capsys.readouterr().out
    assert ("notice:" in out) is bool(ignored)
    for node_id in ids:
        assert (f"work/implementation-summary-{node_id}.md (" in out) is (node_id in ignored), node_id


def test_linked_leaf_worktree_setting_wins_over_main(tmp_path: Path) -> None:
    """R2: a leaf's preferences are read in the checkout holding its branch, from main or the worktree."""
    repo = make_profile_repo(tmp_path)
    git(repo, "checkout", "-q", "dev")
    wt = tmp_path / "leaf-wt"
    git(repo, "worktree", "add", "-q", str(wt), "feature/rm-thing")
    gw = wt / "roadmap" / "git-workflow.yaml"
    gw.write_text(gw.read_text(encoding="utf-8") + "implementation_summary: local\npr_body_footer: leaf footer\n",
                  encoding="utf-8")
    git(wt, "commit", "-qam", "leaf-only preferences")
    assert implementation_summary_rule(repo, "M1.1") == implementation_summary_rule(wt, "M1.1") == "local"
    assert pr_body_footer(repo, "M1.1") == pr_body_footer(wt, "M1.1") == "leaf footer"
    for root in (repo, wt):
        text, _, err = role_prompt.build_prompt(root, "M1.1", role="executor", model="opus")
        assert err is None and "leave it uncommitted" in text and "commit it by explicit path" not in text, root
    git(repo, "worktree", "remove", "--force", str(wt))   # branch checked out nowhere: the asking checkout decides
    assert implementation_summary_rule(repo, "M1.1") == "commit" and pr_body_footer(repo, "M1.1") is None


def test_executor_role_prompt_follows_implementation_summary(tmp_path: Path) -> None:
    repo = make_profile_repo(tmp_path)
    text = role_prompt.build_prompt(repo, "M1.1", role="executor", model="opus")[0]
    assert "commit it by explicit path on this branch" in text
    gw = repo / "roadmap" / "git-workflow.yaml"
    gw.write_text(gw.read_text(encoding="utf-8") + "implementation_summary: local\n", encoding="utf-8")
    text = role_prompt.build_prompt(repo, "M1.1", role="executor", model="opus")[0]
    assert "leave it uncommitted" in text and "commit it by explicit path" not in text
    assert "commit (your last one)" in text and "add -f" not in text


# --- A4: root land: push | local -------------------------------------------------------------

BR = "feature/rm-x"


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True).stdout.strip()


def _land_repo(tmp_path: Path, land: str | None) -> tuple[Path, Path]:
    bare = tmp_path / "remote.git"
    _git(tmp_path, "init", "--bare", "-q", str(bare))
    repo = tmp_path / "work"
    _git(tmp_path, "init", "-q", "-b", "master", str(repo))
    _git(repo, "config", "user.email", "t@e.com")
    _git(repo, "config", "user.name", "T")
    _git(repo, "remote", "add", "origin", str(bare))
    (repo / "roadmap").mkdir()
    (repo / "roadmap" / "git-workflow.yaml").write_text(GW + (f"land: {land}\n" if land else ""), encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "init")
    _git(repo, "push", "-q", "-u", "origin", "master")
    _git(repo, "checkout", "-qb", BR)
    (repo / "feature.txt").write_text("x\n", encoding="utf-8")
    _git(repo, "add", "feature.txt")
    _git(repo, "commit", "-qm", "feature work")
    return repo, bare


@pytest.mark.parametrize("land", ["local", None, "push"])
def test_root_land_local_merges_locally_and_pushes_nothing(tmp_path: Path, capsys, land: str | None) -> None:
    repo, bare = _land_repo(tmp_path, land)
    remote_before = _git(bare, "rev-parse", "master")
    ok, err, done = land_on_integration(repo, remote="origin", ib="master", branch=BR, land_check_cmd=None)
    assert ok, err
    out = capsys.readouterr().out
    _git(repo, "merge-base", "--is-ancestor", BR, "master")   # the local integration branch has the leaf
    assert _git(repo, "branch", "--show-current") == BR
    if land == "local":
        assert "nothing is fetched or pushed" in out and "nothing pushed" in done
        assert _git(bare, "rev-parse", "master") == remote_before
    else:
        assert "push origin/master" in out and done.endswith("pushed to origin")
        assert _git(bare, "rev-parse", "master") == _git(repo, "rev-parse", "master")


def test_root_land_local_needs_a_local_integration_branch(tmp_path: Path) -> None:
    repo, _bare = _land_repo(tmp_path, "local")
    _git(repo, "branch", "-D", "master")
    ok, err, _done = land_on_integration(repo, remote="origin", ib="master", branch=BR, land_check_cmd=None)
    assert not ok and "no local master to merge into (land: local)" in err
