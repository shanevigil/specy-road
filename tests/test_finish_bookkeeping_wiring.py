"""The bookkeeping commit must actually stage the work/ deletions.

``cleanup_work_artifacts`` and ``cleanup_session_sidecar`` only *return* the
tracked paths they removed; staging is the caller's job. Their own unit tests
pass whether or not anyone acts on that return value, so without this the wiring
could be deleted and the suite would stay green while the regression it fixes —
an unlinked-but-uncommitted sidecar that the next checkout restores — came back.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import finish_task as ft


def _args(**over) -> argparse.Namespace:
    base = {
        "no_cleanup_work": False,
        "push": False,
        "remote": "origin",
    }
    base.update(over)
    return argparse.Namespace(**base)


def _repo_with_tracked_session_files(tmp_path: Path, monkeypatch) -> list[list[str]]:
    """Point finish_task at tmp_path and record the git commands it runs."""
    (tmp_path / "work").mkdir()
    for name in (
        "brief-M1.1.md",
        "implementation-summary-M1.1.md",
        ".on-complete-M1.1.yaml",
    ):
        (tmp_path / "work" / name).write_text("x", encoding="utf-8")

    git_calls: list[list[str]] = []
    monkeypatch.setattr(ft, "ROOT", tmp_path)
    monkeypatch.setattr(ft, "REGISTRY_PATH", tmp_path / "roadmap" / "registry.yaml")
    monkeypatch.setattr(ft, "_git", lambda *a: git_calls.append(list(a)))
    monkeypatch.setattr(ft, "_update_chunk_status", lambda _n: [])
    monkeypatch.setattr(ft, "_validate_and_export", lambda: None)
    monkeypatch.setattr(ft, "_save_registry", lambda _d: None)
    return git_calls


def _staged(git_calls: list[list[str]]) -> list[str]:
    add = next(c for c in git_calls if c and c[0] == "add")
    return add[1:]


def test_bookkeeping_stages_the_tracked_sidecar_deletion(tmp_path, monkeypatch) -> None:
    git_calls = _repo_with_tracked_session_files(tmp_path, monkeypatch)
    monkeypatch.setattr(ft, "cleanup_work_artifacts", lambda *_a: [])
    monkeypatch.setattr(
        ft, "cleanup_session_sidecar", lambda *_a: ["work/.on-complete-M1.1.yaml"]
    )

    ft._bookkeeping_commit_phase(
        _args(), "cn", "M1.1", "feature/rm-cn", {"entries": []},
        sess_path=tmp_path / "work" / ".on-complete-M1.1.yaml",
    )

    assert "work/.on-complete-M1.1.yaml" in _staged(git_calls)
    assert any(c and c[0] == "commit" for c in git_calls)


def test_bookkeeping_stages_tracked_document_deletions(tmp_path, monkeypatch) -> None:
    git_calls = _repo_with_tracked_session_files(tmp_path, monkeypatch)
    monkeypatch.setattr(
        ft,
        "cleanup_work_artifacts",
        lambda *_a: ["work/brief-M1.1.md", "work/implementation-summary-M1.1.md"],
    )
    monkeypatch.setattr(ft, "cleanup_session_sidecar", lambda *_a: [])

    ft._bookkeeping_commit_phase(
        _args(), "cn", "M1.1", "feature/rm-cn", {"entries": []}, sess_path=None
    )

    staged = _staged(git_calls)
    assert "work/brief-M1.1.md" in staged
    assert "work/implementation-summary-M1.1.md" in staged


def test_sidecar_goes_even_with_no_cleanup_work(tmp_path, monkeypatch) -> None:
    """--no-cleanup-work keeps the documents; the sidecar is internal state."""
    git_calls = _repo_with_tracked_session_files(tmp_path, monkeypatch)
    cleanup_called: list[bool] = []
    monkeypatch.setattr(
        ft, "cleanup_work_artifacts", lambda *_a: cleanup_called.append(True) or []
    )
    sidecar_called: list[bool] = []

    def _sidecar(*_a):
        sidecar_called.append(True)
        return ["work/.on-complete-M1.1.yaml"]

    monkeypatch.setattr(ft, "cleanup_session_sidecar", _sidecar)

    ft._bookkeeping_commit_phase(
        _args(no_cleanup_work=True), "cn", "M1.1", "feature/rm-cn", {"entries": []},
        sess_path=tmp_path / "work" / ".on-complete-M1.1.yaml",
    )

    assert cleanup_called == []
    assert sidecar_called == [True]
    assert "work/.on-complete-M1.1.yaml" in _staged(git_calls)
