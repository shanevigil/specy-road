"""Pickup points at the loop it belongs to (finding 35).

grind-session and its hook contract were documented only in
docs/grind-session.md, which nothing on the pickup path linked to — so operators
hand-rolled sub-agent orchestration and never adopted the hook.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from specy_road.on_complete_pickup import print_orchestration_hint, print_pickup_footer


@pytest.fixture(autouse=True)
def _no_inherited_marker(monkeypatch):
    monkeypatch.delenv("SPECY_ROAD_GRIND_SESSION", raising=False)


def test_the_hint_names_the_command_the_mode_and_the_docs(capsys):
    print_orchestration_hint()

    out = capsys.readouterr().out
    assert "specy-road grind-session" in out
    assert "--implement-mode hook" in out
    assert "SPECY_ROAD_" in out
    assert "docs/grind-session.md" in out


def test_the_hint_is_silent_inside_a_running_loop(monkeypatch, capsys):
    """Advertising the loop to itself once per cycle is its own flood."""
    monkeypatch.setenv("SPECY_ROAD_GRIND_SESSION", "1")

    print_orchestration_hint()

    assert capsys.readouterr().out == ""


def _footer(root: Path, **over) -> None:
    work = root / "work"
    work.mkdir(parents=True, exist_ok=True)
    brief = work / "brief-M1.1.md"
    prompt = work / "prompt-M1.1.md"
    for p in (brief, prompt):
        p.write_text("x", encoding="utf-8")
    kwargs = {
        "root": root, "work_dir": work, "brief_path": brief, "prompt_path": prompt,
        "push_registry": True, "remote": "origin", "base": "dev",
        "mr_manual": False, "impl_review_gate": False,
        "on_complete": "merge", "node_id": "M1.1",
    }
    kwargs.update(over)
    print_pickup_footer(**kwargs)


def test_the_footer_carries_the_hint_once_per_checkout(tmp_path, capsys):
    _footer(tmp_path)
    first = capsys.readouterr().out
    assert "finish-this-task" in first
    assert "grind-session" in first

    _footer(tmp_path)
    second = capsys.readouterr().out
    assert "finish-this-task" in second
    assert "grind-session" not in second
    assert (tmp_path / ".specyrd" / "cache" / "pickup-orchestration-hint").is_file()


def test_the_footer_drops_the_hint_inside_a_loop(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("SPECY_ROAD_GRIND_SESSION", "1")

    _footer(tmp_path)

    out = capsys.readouterr().out
    assert "finish-this-task" in out
    assert "grind-session" not in out


def test_the_hint_marker_leaves_the_tree_clean(tmp_path, capsys):
    """A repo whose .gitignore lacks .specyrd/cache/ stays clean, and the hint shows once."""
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / ".gitignore").write_text("*.pyc\n", encoding="utf-8")
    git = ["git", "-C", str(tmp_path), "-c", "user.name=t", "-c", "user.email=t@t"]
    subprocess.run([*git, "add", ".gitignore"], check=True)
    subprocess.run([*git, "commit", "-q", "-m", "init"], check=True)

    print_orchestration_hint(tmp_path)
    assert "grind-session" in capsys.readouterr().out
    status = subprocess.run([*git, "status", "--porcelain", "--untracked-files=all"],
                            check=True, capture_output=True, text=True).stdout
    assert status == ""

    print_orchestration_hint(tmp_path)
    assert capsys.readouterr().out == ""
