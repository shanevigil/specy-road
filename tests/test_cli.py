"""Smoke tests for specy-road CLI."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DOGFOOD = REPO / "tests" / "fixtures" / "specy_road_dogfood"


def test_specy_road_validate() -> None:
    subprocess.run(
        [
            sys.executable,
            "-m",
            "specy_road.cli",
            "validate",
            "--repo-root",
            str(DOGFOOD),
        ],
        cwd=REPO,
        check=True,
    )


def test_specy_road_sync_rejects_no_git_flag() -> None:
    """F-010: --no-git is not an option; specy-road requires git + remote."""
    r = subprocess.run(
        [
            sys.executable,
            "-m",
            "specy_road.cli",
            "sync",
            "--no-git",
            "--repo-root",
            str(DOGFOOD),
        ],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    assert r.returncode != 0
    err = (r.stderr or "") + (r.stdout or "")
    assert "--no-git" in err or "unrecognized" in err


def test_specy_road_list_nodes() -> None:
    r = subprocess.run(
        [
            sys.executable,
            "-m",
            "specy_road.cli",
            "list-nodes",
            "--repo-root",
            str(DOGFOOD),
        ],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "M0" in r.stdout


def test_specy_road_archive_unknown_node_no_traceback(tmp_path: Path) -> None:
    """Bundled script stderr is enough; top-level CLI must not chain CalledProcessError."""
    import shutil

    from tests.helpers import SCHEMAS

    dest = tmp_path / "proj"
    shutil.copytree(SCHEMAS, dest / "schemas")
    shutil.copytree(REPO / "constraints", dest / "constraints")
    (dest / "roadmap" / "phases").mkdir(parents=True)
    (dest / "shared").mkdir(parents=True)
    (dest / "shared" / "README.md").write_text("# Shared\n", encoding="utf-8")
    (dest / "roadmap" / "registry.yaml").write_text(
        "version: 1\nentries: []\n",
        encoding="utf-8",
    )
    (dest / "roadmap" / "manifest.json").write_text(
        '{"version": 1, "includes": ["phases/T.json"]}\n',
        encoding="utf-8",
    )
    (dest / "roadmap" / "phases" / "T.json").write_text("[]\n", encoding="utf-8")

    r = subprocess.run(
        [
            sys.executable,
            "-m",
            "specy_road.cli",
            "archive-node",
            "M0.1.1",
            "--hard-remove",
            "--repo-root",
            str(dest),
        ],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    assert r.returncode == 1
    err = (r.stderr or "") + (r.stdout or "")
    assert "Traceback" not in err
    assert "CalledProcessError" not in err
    assert "no roadmap node" in err


def test_specy_road_list_dependencies() -> None:
    r = subprocess.run(
        [
            sys.executable,
            "-m",
            "specy_road.cli",
            "list-dependencies",
            "M0.1",
            "--repo-root",
            str(DOGFOOD),
        ],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    )
    assert r.returncode == 0, r.stderr


def test_specy_road_show_node() -> None:
    r = subprocess.run(
        [
            sys.executable,
            "-m",
            "specy_road.cli",
            "show-node",
            "M0.1",
            "--repo-root",
            str(DOGFOOD),
        ],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "M0.1" in r.stdout


def test_specy_road_do_next_available_task_help() -> None:
    r = subprocess.run(
        [
            sys.executable,
            "-m",
            "specy_road.cli",
            "do-next-available-task",
            "--help",
        ],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "--base" in r.stdout
    assert "--interactive" in r.stdout
    assert "--no-ci-skip-in-message" in r.stdout
    assert "actionable leaf task" in r.stdout
    assert "--no-sync" not in r.stdout
    assert "--no-push-registry" not in r.stdout
    assert "--milestone-subtree" in r.stdout
    assert "--under" in r.stdout


def test_specy_road_abort_task_pickup_help() -> None:
    r = subprocess.run(
        [
            sys.executable,
            "-m",
            "specy_road.cli",
            "abort-task-pickup",
            "--help",
        ],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "--base" in r.stdout
    assert "--remote" in r.stdout
    assert "--force" in r.stdout
    assert "do-next-available-task" in r.stdout or "pickup" in r.stdout


def test_specy_road_root_help_exits_zero() -> None:
    r = subprocess.run(
        [sys.executable, "-m", "specy_road.cli", "--help"],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0
    assert "validate" in r.stdout


def test_specy_road_init_requires_subcommand() -> None:
    r = subprocess.run(
        [sys.executable, "-m", "specy_road.cli", "init"],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    assert r.returncode == 2
    err = (r.stderr or "") + (r.stdout or "")
    assert "project" in err or "gui" in err


def test_specy_road_init_install_gui_dry_run() -> None:
    r = subprocess.run(
        [
            sys.executable,
            "-m",
            "specy_road.cli",
            "init",
            "gui",
            "--install-gui",
            "--dry-run",
        ],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "Would run:" in r.stdout
    assert "pip" in r.stdout
    assert "gui-next" in r.stdout
    assert "--upgrade" in r.stdout
    assert "npm" in r.stdout
    assert "npm run build" in r.stdout


def test_specy_road_init_reinstall_gui_dry_run() -> None:
    r = subprocess.run(
        [
            sys.executable,
            "-m",
            "specy_road.cli",
            "init",
            "gui",
            "--reinstall-gui",
            "--dry-run",
        ],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "Would run:" in r.stdout
    assert "--force-reinstall" in r.stdout
    assert "gui-next" in r.stdout
    assert "npm run build" in r.stdout


def test_specy_road_init_install_gui_skip_npm_dry_run() -> None:
    r = subprocess.run(
        [
            sys.executable,
            "-m",
            "specy_road.cli",
            "init",
            "gui",
            "--install-gui",
            "--skip-npm-build",
            "--dry-run",
        ],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "gui-next" in r.stdout
    assert "Would skip npm build" in r.stdout
    assert "npm run build" not in r.stdout


def test_specy_road_init_build_gui_only_dry_run() -> None:
    r = subprocess.run(
        [
            sys.executable,
            "-m",
            "specy_road.cli",
            "init",
            "gui",
            "--build-gui",
            "--dry-run",
        ],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "npm" in r.stdout
    assert "pm-gantt" in r.stdout
    assert "npm run build" in r.stdout
    assert "pip" not in r.stdout
    assert "gui-next" not in r.stdout


def test_specy_road_finish_this_task_help() -> None:
    r = subprocess.run(
        [
            sys.executable,
            "-m",
            "specy_road.cli",
            "finish-this-task",
            "--help",
        ],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "--push" in r.stdout
    assert "--no-cleanup-work" in r.stdout
    assert "--no-milestone-rollup" in r.stdout


def test_specy_road_start_milestone_session_help() -> None:
    r = subprocess.run(
        [
            sys.executable,
            "-m",
            "specy_road.cli",
            "start-milestone-session",
            "--help",
        ],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "PARENT_NODE_ID" in r.stdout
    assert ".milestone-session.yaml" in r.stdout or "milestone-session" in r.stdout


def test_specy_road_reconcile_milestone_status_help() -> None:
    r = subprocess.run(
        [
            sys.executable,
            "-m",
            "specy_road.cli",
            "reconcile-milestone-status",
            "--help",
        ],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "--apply" in r.stdout
    assert "--fallback-head-delivery" in r.stdout


def test_specy_road_open_milestone_pr_help() -> None:
    r = subprocess.run(
        [
            sys.executable,
            "-m",
            "specy_road.cli",
            "open-milestone-pr",
            "--help",
        ],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "rollup" in r.stdout.lower() or "PR" in r.stdout


def test_specy_road_mark_implementation_reviewed_help() -> None:
    r = subprocess.run(
        [
            sys.executable,
            "-m",
            "specy_road.cli",
            "mark-implementation-reviewed",
            "--help",
        ],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "--yes" in r.stdout
    assert "--allow-missing-summary" in r.stdout
