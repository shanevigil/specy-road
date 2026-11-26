"""F-011: scaffold ships a .gitignore that ignores session-scoped work files."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from specy_road.bundled_scripts.upgrade import run_upgrade
from specy_road.init_project import run_init_project
from specy_road.workflow_prefs import summary_ignore_rules, summary_rule_notice


@pytest.mark.parametrize("sub", ["", "sr"])
def test_init_project_ships_a_gitignore(tmp_path: Path, sub: str) -> None:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    rc = run_init_project(tmp_path / sub)
    assert rc == 0
    gi = tmp_path / ".gitignore"
    assert gi.is_file(), "init project should write a .gitignore"
    rules = [ln for ln in gi.read_text(encoding="utf-8").splitlines() if ln and not ln.startswith("#")]
    p = f"{sub}/" if sub else ""
    # All of work/ belongs to the tool; the scaffold is re-included, prefix after the `!`.
    expected = [f"{p}work/*", f"!{p}work/README.md", f"!{p}work/.gitkeep", f"!{p}work/*.template.md"]
    assert [r for r in rules if "work/" in r] == expected


def test_a_fresh_clone_holds_the_work_scaffold(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    assert run_init_project(repo) == 0
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@example.com",
                    "commit", "-qm", "init"], check=True)
    clone = tmp_path / "clone"
    subprocess.run(["git", "clone", "-q", str(repo), str(clone)], check=True)
    for rel in ("README.md", ".gitkeep", "review-record.template.md", "handoff-ready.template.md",
                "implementation-summary.template.md"):
        assert (clone / "work" / rel).is_file(), rel


def test_force_keeps_the_consumers_gitignore(tmp_path: Path) -> None:
    """--force replaced the whole file, dropping the team's own lines (rc1 feedback)."""
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    assert run_init_project(tmp_path) == 0
    gi = tmp_path / ".gitignore"
    gi.write_text(gi.read_text(encoding="utf-8") + "\nnode_modules/\n", encoding="utf-8")

    assert run_init_project(tmp_path, force=True) == 0

    text = gi.read_text(encoding="utf-8")
    assert "node_modules/" in text
    assert ".specyrd/cache/" in text


def test_refusal_points_at_the_refresh_commands(tmp_path: Path, capsys) -> None:
    assert run_init_project(tmp_path) == 0

    assert run_init_project(tmp_path) == 1

    assert "refresh-stubs" in capsys.readouterr().err


def test_a_new_project_keeps_summaries_local_without_a_notice(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    assert run_init_project(tmp_path) == 0
    assert summary_ignore_rules(tmp_path, ["M1"])   # work/* reaches the summary...
    assert summary_rule_notice(tmp_path, ["M1"]) is None   # ...and the scaffold says local, so validate is quiet


def test_upgrade_prints_the_untrack_command_for_a_file_already_tracked_under_work(tmp_path: Path, capsys) -> None:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    assert run_init_project(tmp_path) == 0
    (tmp_path / ".gitignore").write_text(".specyrd/cache/\n", encoding="utf-8")   # a block that predates work/*
    (tmp_path / "work" / "brief-M1.md").write_text("# brief\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(tmp_path), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "-c", "user.name=t", "-c", "user.email=t@example.com",
                    "commit", "-qm", "older project"], check=True)
    capsys.readouterr()

    assert run_upgrade(tmp_path) == 0

    out = capsys.readouterr().out
    assert "work/brief-M1.md (work/*): still tracked" in out
    assert "git rm --cached -- work/brief-M1.md" in out
    tracked = subprocess.run(["git", "-C", str(tmp_path), "ls-files", "work/brief-M1.md"],
                             capture_output=True, text=True, check=True).stdout
    assert tracked.strip() == "work/brief-M1.md"   # printed, never run
