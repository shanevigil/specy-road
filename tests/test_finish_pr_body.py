"""F-015: PR/MR body composition (impl-summary visible + brief in <details>)."""

from __future__ import annotations

from pathlib import Path

from specy_road.finish_pr_body import compose_pr_body, pr_body_modes, write_pr_body


def _seed_work(tmp_path: Path, node: str) -> Path:
    work = tmp_path / "work"
    work.mkdir()
    (work / f"implementation-summary-{node}.md").write_text(
        "# Implementation summary\n\nDid the thing.\n", encoding="utf-8"
    )
    (work / f"brief-{node}.md").write_text(
        "# Work-packet brief\n\n## 1. Execution target\n- node: M9.9\n",
        encoding="utf-8",
    )
    return work


def test_compose_includes_impl_summary_and_brief(tmp_path: Path) -> None:
    work = _seed_work(tmp_path, "M9.9")
    body = compose_pr_body(
        work_dir=work, node_id="M9.9", title="Do the thing",
        codename="do-the-thing", branch="feature/rm-do-the-thing",
        integration_branch="main",
    )
    # Headline + branches.
    assert "[M9.9] Do the thing" in body
    assert "feature/rm-do-the-thing" in body
    assert "main" in body
    # Impl summary is in the open (not in <details>).
    assert "## Implementation summary (dev-authored)" in body
    assert "Did the thing." in body
    # Brief is wrapped in <details>.
    assert "<details>" in body
    assert "Original work-packet brief" in body
    assert "## 1. Execution target" in body
    assert "</details>" in body
    # Snapshot note tells future readers the body does not auto-update.
    assert "Snapshot generated at finish-this-task time" in body


def test_compose_handles_missing_files_gracefully(tmp_path: Path) -> None:
    work = tmp_path / "work"
    work.mkdir()
    body = compose_pr_body(
        work_dir=work, node_id="M9.9", title="t",
        codename=None, branch="feature/rm-x", integration_branch="dev",
    )
    assert "no implementation summary on disk" in body
    assert "no work-packet brief on disk" in body
    assert "[M9.9] t" in body  # codename omitted is fine


def test_compose_omits_codename_when_none(tmp_path: Path) -> None:
    work = _seed_work(tmp_path, "M9.9")
    body = compose_pr_body(
        work_dir=work, node_id="M9.9", title="t",
        codename=None, branch="feature/rm-x", integration_branch="main",
    )
    # No backticked codename in the title line when codename is None.
    assert "# [M9.9] t\n" in body


def test_write_creates_pr_body_file(tmp_path: Path) -> None:
    work = _seed_work(tmp_path, "M9.9")
    out = write_pr_body(
        work_dir=work, node_id="M9.9", title="Do",
        codename="do", branch="feature/rm-do", integration_branch="main",
    )
    assert out.is_file()
    assert out.name == "pr-body-M9.9.md"
    text = out.read_text(encoding="utf-8")
    assert "Implementation summary" in text


def test_pr_body_modes_excludes_merge() -> None:
    """on_mode='merge' goes straight to git merge — no PR body needed."""
    modes = set(pr_body_modes())
    assert "pr" in modes
    assert "auto" in modes
    assert "merge" not in modes


def test_compose_is_deterministic(tmp_path: Path) -> None:
    """Same inputs → byte-identical output (matches F-004 brief contract)."""
    work = _seed_work(tmp_path, "M9.9")
    a = compose_pr_body(
        work_dir=work, node_id="M9.9", title="t",
        codename="do", branch="feature/rm-do", integration_branch="main",
    )
    b = compose_pr_body(
        work_dir=work, node_id="M9.9", title="t",
        codename="do", branch="feature/rm-do", integration_branch="main",
    )
    assert a == b
