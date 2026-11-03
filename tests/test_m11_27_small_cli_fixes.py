"""M11.27 — small CLI fixes from field use."""

from __future__ import annotations

import json
import shutil
import sys
from io import StringIO
from pathlib import Path

import pytest

from tests.helpers import REPO, SCHEMAS
from tests.review_repo_helpers import git, make_review_repo
from tests.test_review_round6_runner import _launch
from tests.test_worker_cli import FAKE, _repo, run_worker_cli, wait_for_worker, worker_roster

from specy_road import worker_runner as wr
from specy_road import worker_state as ws
from specy_road.bundled_scripts import role_prompt
from specy_road.bundled_scripts import validate_roadmap as vr
from specy_road.bundled_scripts.validate_roadmap import validate_at
from specy_road.finish_ancestor_rollup import complete_rolled_up_ancestors
from specy_road.review_files import list_ready, reviews_dir


def test_prompt_wrote_line_is_on_stderr(tmp_path: Path, capsys, monkeypatch) -> None:
    repo = make_review_repo(tmp_path, orchestration=worker_roster("true"))
    out = tmp_path / "work" / "prompt-M1.1-executor-opus.md"
    monkeypatch.setattr(sys, "stdout", StringIO())
    monkeypatch.setattr(role_prompt, "run_cli_channel", lambda *_a, **_k: 0)
    capsys.readouterr()
    with pytest.raises(SystemExit) as exc:
        role_prompt.main(
            ["M1.1", "--model", "opus", "--role", "executor", "--channel", "paste",
             "--output", str(out), "--repo-root", str(repo)]
        )
    assert exc.value.code == 0
    captured = capsys.readouterr()
    assert captured.out == ""
    assert f"Wrote {out}" in captured.err


def test_validate_missing_planning_dir_lists_every_node_and_scaffold_fix(capsys) -> None:
    nodes = [
        {"id": "M1", "node_key": "10000000-0000-4000-8000-000000000001", "type": "phase"},
        {"id": "M2", "node_key": "20000000-0000-4000-8000-000000000002", "type": "task"},
    ]
    capsys.readouterr()
    with pytest.raises(SystemExit):
        vr.validate_required_planning_dirs(nodes)
    err = capsys.readouterr().err
    assert "roadmap: node M1 (type phase):" in err
    assert "roadmap: node M2 (type task):" in err
    assert err.count("fix: specy-road scaffold-planning M1") == 1
    assert err.count("fix: specy-road scaffold-planning M2") == 1


NK = {
    "M70": "70000000-0000-4000-8000-000000000001",
    "M70.1": "70000000-0000-4000-8000-000000000002",
    "M70.1.1": "70000000-0000-4000-8000-000000000003",
    "M70.2": "70000000-0000-4000-8000-000000000004",
}


def _rollup_finish_repo(tmp_path: Path) -> Path:
    shutil.copytree(SCHEMAS, tmp_path / "schemas")
    shutil.copytree(REPO / "constraints", tmp_path / "constraints")
    (tmp_path / "roadmap" / "phases").mkdir(parents=True)
    (tmp_path / "shared").mkdir()
    (tmp_path / "shared" / "README.md").write_text("# Shared\n", encoding="utf-8")
    (tmp_path / "roadmap" / "registry.yaml").write_text("version: 1\nentries: []\n", encoding="utf-8")
    (tmp_path / "roadmap" / "git-workflow.yaml").write_text(
        "version: 1\nintegration_branch: dev\nremote: origin\n"
        "require_implementation_review_before_finish: true\n",
        encoding="utf-8",
    )
    (tmp_path / "roadmap" / "orchestration.yaml").write_text(
        "version: 1\npolicy: {milestone_full_review: false}\n", encoding="utf-8")
    (tmp_path / "roadmap" / "manifest.json").write_text(
        json.dumps({"version": 1, "includes": ["phases/M70.json"]}), encoding="utf-8"
    )
    planning = tmp_path / "planning"
    planning.mkdir()
    nodes = [
        {
            "id": "M70",
            "node_key": NK["M70"],
            "parent_id": None,
            "type": "phase",
            "title": "P",
            "planning_dir": f"planning/M70_unnamed_{NK['M70']}.md",
            "status": "Not Started",
            "touch_zones": [],
            "dependencies": [],
        },
        {
            "id": "M70.1",
            "node_key": NK["M70.1"],
            "parent_id": "M70",
            "type": "milestone",
            "title": "M",
            "planning_dir": f"planning/M70.1_unnamed_{NK['M70.1']}.md",
            "status": "Not Started",
            "touch_zones": [],
            "dependencies": [],
        },
        {
            "id": "M70.1.1",
            "node_key": NK["M70.1.1"],
            "parent_id": "M70.1",
            "type": "task",
            "title": "Done leaf",
            "codename": "done-leaf",
            "planning_dir": f"planning/M70.1.1_done-leaf_{NK['M70.1.1']}.md",
            "status": "Complete",
            "touch_zones": ["src"],
            "dependencies": [],
            "acceptance": ["done"],
        },
        {
            "id": "M70.2",
            "node_key": NK["M70.2"],
            "parent_id": "M70",
            "type": "task",
            "title": "Bare sibling",
            "planning_dir": f"planning/M70.2_bare_{NK['M70.2']}.md",
            "status": "Not Started",
            "touch_zones": [],
            "dependencies": [],
        },
    ]
    for n in nodes:
        rel = n["planning_dir"].split("/", 1)[1]
        (planning / rel).write_text(f"# {n['id']}\n\n## Intent\n\nWork.\n", encoding="utf-8")
    (tmp_path / "roadmap" / "phases" / "M70.json").write_text(
        json.dumps({"version": 1, "nodes": nodes}, indent=2), encoding="utf-8"
    )
    git(tmp_path, "init", "-q", "-b", "dev")
    git(tmp_path, "config", "user.email", "t@e.com")
    git(tmp_path, "config", "user.name", "T")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-qm", "graph")
    return tmp_path


def test_ancestor_rollup_then_validate_prints_each_warning_once(tmp_path: Path, capsys) -> None:
    repo = _rollup_finish_repo(tmp_path)
    capsys.readouterr()
    changed = complete_rolled_up_ancestors(repo, "M70.1.1")
    assert changed
    validate_at(repo, no_overlap_warn=True, require_registry=True)
    err = capsys.readouterr().err
    assert err.count("has no acceptance criteria") == 1


def test_worker_runner_reports_invalid_and_missing_ready(tmp_path: Path) -> None:
    repo, script = _repo(tmp_path)
    ready_path = reviews_dir(repo, "M1.1") / "READY-opus.md"
    ready_path.parent.mkdir(parents=True, exist_ok=True)
    rec = ws.create_record(repo, "M1.1", "claude-code", "opus", repo, branch="feature/rm-thing")
    launch = _launch(
        tmp_path, script, repo, "invalid",
        write={"path": str(ready_path), "text": "no front matter\n"},
    )
    wr.run(repo, rec.worker_id, launch)
    invalid_summary = ws.events_since(repo, rec.worker_id)[-1].summary
    assert invalid_summary.startswith("exit 0; READY file invalid:")
    invalid = next(r for r in list_ready(repo, "M1.1") if r.path.name == "READY-opus.md" and r.errors)
    assert "; ".join(invalid.errors) in invalid_summary

    rec2 = ws.create_record(repo, "M1.1", "claude-code", "opus", repo, branch="feature/rm-thing")
    wr.run(repo, rec2.worker_id, _launch(tmp_path, script, repo, "missing"))
    assert ws.events_since(repo, rec2.worker_id)[-1].summary == "exit 0; READY file missing"


def test_exit_zero_with_a_broken_roadmap_still_completes_idle(tmp_path: Path) -> None:
    repo, script = _repo(tmp_path)
    rec = ws.create_record(repo, "M1.1", "claude-code", "opus", repo, branch="feature/rm-thing")
    (repo / "roadmap" / "manifest.json").write_text("{not json", encoding="utf-8")
    wr.run(repo, rec.worker_id, _launch(tmp_path, script, repo, "broken-roadmap"))
    last = ws.events_since(repo, rec.worker_id)[-1]
    assert last.type == "completion"
    assert last.summary == "exit 0; READY file missing"
    assert ws.load_record(repo, rec.worker_id).state == "idle"


def test_worker_list_and_sync_show_worktree(tmp_path: Path, capsys) -> None:
    script = tmp_path / "fake.py"
    script.write_text(FAKE)
    repo = make_review_repo(
        tmp_path,
        orchestration=worker_roster(f"{sys.executable} {script} {{prompt}} {{session}}"),
    )
    run_worker_cli("worker", "delegate", "M1.1", "--model", "opus", "--repo-root", str(repo))
    rec = wait_for_worker(repo, "w-0001")
    capsys.readouterr()
    assert run_worker_cli("worker", "list", "--repo-root", str(repo)) == 0
    assert f"worktree={rec.worktree}" in capsys.readouterr().out
    capsys.readouterr()
    assert run_worker_cli("worker", "sync", "--repo-root", str(repo)) == 0
    assert f"worktree={rec.worktree}" in capsys.readouterr().out
