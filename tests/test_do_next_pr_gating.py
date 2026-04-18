"""F-007: PR-gated downstream selection in do-next-available-task."""

from __future__ import annotations

import do_next_task as dnt


def test_virtual_keys_for_mode_pr_returns_empty_set(monkeypatch) -> None:
    """When git-workflow on_complete is 'pr', virtual_complete is suppressed."""
    monkeypatch.setattr(dnt, "on_complete_from_git_workflow", lambda _r: "pr")
    keys, logs = dnt._virtual_keys_for_mode(
        {"version": 1, "entries": [{"codename": "x", "node_id": "M1"}]},
        "origin",
    )
    assert keys == set()
    assert any("PR-gating" in line for line in logs)


def test_virtual_keys_for_mode_merge_uses_virtual_complete(monkeypatch) -> None:
    """When on_complete is 'merge', virtual-complete-from-tip is computed."""
    monkeypatch.setattr(dnt, "on_complete_from_git_workflow", lambda _r: "merge")
    seen: list[dict] = []

    def fake_vc(reg, *, repo_root, remote):
        seen.append(reg)
        return {"some-key"}, ["[info] virtual"]

    monkeypatch.setattr(dnt, "_virtual_complete_from_registry", fake_vc)
    reg = {"version": 1, "entries": [{"codename": "x", "node_id": "M1"}]}
    keys, _logs = dnt._virtual_keys_for_mode(reg, "origin")
    assert keys == {"some-key"}
    assert seen and seen[0] is reg


def test_virtual_keys_for_mode_pr_silent_when_no_entries(monkeypatch) -> None:
    """No transparency log when nothing is gating."""
    monkeypatch.setattr(dnt, "on_complete_from_git_workflow", lambda _r: "pr")
    keys, logs = dnt._virtual_keys_for_mode({"version": 1, "entries": []}, "origin")
    assert keys == set()
    assert logs == []
