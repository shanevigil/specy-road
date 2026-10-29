"""M3.10: worker hand-off, reconcile reporting, sync/list messages, merge finish notice."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from tests.review_repo_helpers import git, make_review_repo
from tests.test_worker_cli import FAKE, _repo, run_worker_cli, wait_for_worker, worker_roster
from tests.test_worker_cli_fixes import _nested

from specy_road import worker_adapters as wa
from specy_road import worker_ops as ops
from specy_road import worker_state as ws
from specy_road.bundled_scripts import review_cli
from specy_road.finish_land_integration import print_merge_push_notice
from specy_road.review_files import reviews_dir


def test_claude_passes_add_dir_only_in_a_linked_worktree(tmp_path: Path) -> None:
    top, project = _nested(tmp_path)
    git(top, "checkout", "-q", "dev")
    wt = tmp_path / "wt"
    git(top, "worktree", "add", "-q", str(wt), "feature/rm-thing")
    prompt = project / "work" / "prompt-M1.1-executor-opus.md"
    prompt.parent.mkdir(parents=True, exist_ok=True)
    prompt.write_text("x\n")
    handoff = reviews_dir(project, "M1.1")
    linked = wa.adapter_for("claude-code").launch(
        prompt, wt, "m", None, node_id="M1.1", repo_root=project,
    )
    assert "--add-dir" in linked.argv
    assert str(handoff) == linked.argv[linked.argv.index("--add-dir") + 1]
    main = wa.adapter_for("claude-code").launch(
        prompt, top, "m", None, node_id="M1.1", repo_root=project,
    )
    assert "--add-dir" not in main.argv


def test_reconcile_treats_a_directory_touch_zone_as_covering_files(tmp_path: Path) -> None:
    repo, _ = _repo(tmp_path)
    reg = repo / "roadmap" / "registry.yaml"
    reg.write_text(reg.read_text(encoding="utf-8").replace("- src", "- schemas/"))
    git(repo, "add", "roadmap/registry.yaml")
    git(repo, "commit", "-qm", "zones")
    run_worker_cli("worker", "delegate", "M1.1", "--model", "opus", "--repo-root", str(repo))
    rec = wait_for_worker(repo, "w-0001")
    ws.take_checkpoint(repo, rec)
    (repo / "schemas" / "node.json").parent.mkdir(parents=True, exist_ok=True)
    (repo / "schemas" / "node.json").write_text("{}\n")
    git(repo, "add", "schemas/node.json")
    git(repo, "commit", "-qm", "schema")
    _rec, delta = ops.reconcile(repo, rec.worker_id)
    assert "schemas/node.json" in delta["changed"]
    assert delta["outside_touch_zones"] == [] and not delta["needs_reconcile"]


def test_reconcile_ignores_prompt_hash_drift_when_brief_is_byte_identical(tmp_path: Path) -> None:
    repo, _ = _repo(tmp_path)
    run_worker_cli("worker", "delegate", "M1.1", "--model", "opus", "--repo-root", str(repo))
    rec = wait_for_worker(repo, "w-0001")
    ws.take_checkpoint(repo, rec)
    (repo / "src" / "touch.py").write_text("x\n")
    git(repo, "add", "src/touch.py")
    git(repo, "commit", "-qm", "impl progress")
    _rec, delta = ops.reconcile(repo, rec.worker_id)
    assert not delta["contract_changed"] and not delta["needs_reconcile"]


def test_handoff_status_labels_ready_verify_as_executor_reported(tmp_path: Path, capsys) -> None:
    repo = make_review_repo(tmp_path)
    d = reviews_dir(repo, "M1.1")
    d.mkdir(parents=True, exist_ok=True)
    (d / "READY-exec.md").write_text(
        f"---\nnode_id: M1.1\nagent: exec\nbranch: feature/rm-thing\n"
        f"commit: {git(repo, 'rev-parse', 'HEAD')}\nbase: {git(repo, 'rev-parse', 'dev')}\n"
        "changed_paths: [src/a.py]\nverify:\n  - {cmd: 'false', exit: 1, tail: boom}\n---\n"
    )
    with pytest.raises(SystemExit):
        review_cli.main(["handoff", "status", "M1.1", "--repo-root", str(repo)])
    out = capsys.readouterr().out
    assert "READY-exec.md (executor-reported):" in out
    assert "verifier `false` exited 1" in out


def test_sync_and_list_surface_the_harness_final_message(tmp_path: Path, capsys) -> None:
    limit = "You've hit your 5-hour limit · resets 6:20pm"
    script = tmp_path / "limit.py"
    script.write_text(
        f'''import json, sys
print(json.dumps({{"type": "system", "subtype": "init", "session_id": "s1", "model": "fake"}}), flush=True)
print(json.dumps({{"type": "result", "subtype": "success", "is_error": True, "result": "{limit}",
  "session_id": "s1"}}), flush=True)
sys.exit(1)
'''
    )
    repo = make_review_repo(
        tmp_path,
        orchestration=worker_roster(f"{sys.executable} {script} {{prompt}} {{session}}"),
    )
    (repo / ".gitignore").write_text("work/\n")
    git(repo, "add", ".gitignore")
    git(repo, "commit", "-qm", "ignore work")
    run_worker_cli("worker", "delegate", "M1.1", "--model", "opus", "--repo-root", str(repo))
    rec = wait_for_worker(repo, "w-0001")
    assert rec.state == "failed"
    capsys.readouterr()
    assert run_worker_cli("worker", "sync", "--repo-root", str(repo)) == 0
    sync_out = capsys.readouterr().out
    assert limit in sync_out
    assert run_worker_cli("worker", "list", "--all", "--repo-root", str(repo)) == 0
    assert limit in capsys.readouterr().out


def test_sync_shows_full_message_when_completion_has_no_ready(tmp_path: Path, capsys) -> None:
    repo, _ = _repo(tmp_path)
    run_worker_cli("worker", "delegate", "M1.1", "--model", "opus", "--repo-root", str(repo))
    rec = wait_for_worker(repo, "w-0001")
    ws.append_event(
        repo, rec, "output", source="worker",
        summary="(truncated)", detail={"message": "Stop: write READY in main checkout reviews dir"},
    )
    ws.append_event(
        repo, rec, "completion", source="worker",
        summary="exit 0; READY file missing",
        detail={"exit": 0, "ready": False},
    )
    capsys.readouterr()
    assert run_worker_cli("worker", "sync", "--repo-root", str(repo)) == 0
    assert "Stop: write READY in main checkout reviews dir" in capsys.readouterr().out


def test_finish_help_and_merge_notice(tmp_path: Path, capsys) -> None:
    help_text = subprocess.check_output(
        [sys.executable, "-m", "specy_road.cli", "finish-this-task", "--help"],
        text=True,
    )
    assert "merge lands on the integration branch and pushes it" in help_text
    assert "--push only pushes the feature branch" in help_text
    repo = make_review_repo(tmp_path)
    git(repo, "checkout", "-q", "dev")
    base = git(repo, "rev-parse", "HEAD")
    git(repo, "commit", "--allow-empty", "-qm", "extra on dev")
    git(repo, "update-ref", "refs/remotes/origin/dev", base)
    git(repo, "checkout", "-q", "feature/rm-thing")
    print_merge_push_notice(
        repo, remote="origin", integration_branch="dev", feature_branch="feature/rm-thing",
    )
    out = capsys.readouterr().out
    assert "will merge 'feature/rm-thing' into 'dev' and push origin/dev" in out
    assert "local commit" in out and "not on origin/dev yet" in out
