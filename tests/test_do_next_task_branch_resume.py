"""An existing feature branch resumes the pickup; it does not roll it back.

Finding 31. ``git checkout -b`` failing with "already exists" used to raise into
the F-014 rollback, which strips the claim the same pickup had just registered:
the node went back on the available list, the branch was still there, and the
next pickup failed identically. These tests pin the loop shut.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
import yaml

from specy_road.bundled_scripts.do_next_task_pickup_helpers import (
    push_and_branch_with_self_heal,
)

CLAIM = {
    "codename": "cn",
    "node_id": "M1.1",
    "branch": "feature/rm-cn",
    "touch_zones": [],
}


def _registry(tmp_path: Path, entries=None) -> Path:
    path = tmp_path / "roadmap" / "registry.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.dump({"version": 1, "entries": entries if entries is not None else [CLAIM]}),
        encoding="utf-8",
    )
    return path


def _codenames(reg_path: Path) -> list[str]:
    data = yaml.safe_load(reg_path.read_text(encoding="utf-8"))
    return [e["codename"] for e in data["entries"]]


class _Calls:
    def __init__(self, *, push_raises=False, checkout_raises=False):
        self.git: list[tuple[str, ...]] = []
        self.created: list[str] = []
        self.adopted: list[str] = []
        self.pushed: list[tuple[str, str]] = []
        self.push_raises = push_raises
        self.checkout_raises = checkout_raises

    def git_runner(self, *args: str) -> None:
        self.git.append(args)

    def push(self, remote: str, base: str) -> None:
        self.pushed.append((remote, base))
        if self.push_raises:
            raise subprocess.CalledProcessError(1, ["git", "push"])

    def create(self, branch: str) -> None:
        if self.checkout_raises:
            raise subprocess.CalledProcessError(128, ["git", "checkout", "-b"])
        self.created.append(branch)

    def adopt(self, branch: str) -> None:
        if self.checkout_raises:
            raise subprocess.CalledProcessError(1, ["git", "checkout"])
        self.adopted.append(branch)


def _run(tmp_path: Path, calls: _Calls, *, exists: bool, reg_path: Path):
    return push_and_branch_with_self_heal(
        repo_root=tmp_path,
        registry_path=reg_path,
        git_runner=calls.git_runner,
        push_integration_branch_fn=calls.push,
        checkout_new_branch_fn=calls.create,
        checkout_existing_branch_fn=calls.adopt,
        branch_exists=lambda _root, _branch: exists,
        push_registry=True,
        base="dev",
        remote="origin",
        branch="feature/rm-cn",
        node_id="M1.1",
        codename="cn",
    )


def test_existing_branch_is_adopted_and_the_claim_survives(tmp_path, capsys):
    reg_path = _registry(tmp_path)
    calls = _Calls()

    _run(tmp_path, calls, exists=True, reg_path=reg_path)

    assert calls.adopted == ["feature/rm-cn"]
    assert calls.created == []
    assert _codenames(reg_path) == ["cn"]
    assert calls.git == []  # no self-heal commit
    assert "already exists" in capsys.readouterr().out


def test_absent_branch_is_created_as_before(tmp_path):
    reg_path = _registry(tmp_path)
    calls = _Calls()

    _run(tmp_path, calls, exists=False, reg_path=reg_path)

    assert calls.created == ["feature/rm-cn"]
    assert calls.adopted == []
    assert _codenames(reg_path) == ["cn"]


@pytest.mark.parametrize("exists", [True, False])
def test_a_failed_push_still_rolls_the_claim_back(tmp_path, exists):
    """Rollback is unchanged for failures that mean the pickup did not complete."""
    reg_path = _registry(tmp_path)
    calls = _Calls(push_raises=True)

    with pytest.raises(subprocess.CalledProcessError):
        _run(tmp_path, calls, exists=exists, reg_path=reg_path)

    assert _codenames(reg_path) == []
    assert [c[0] for c in calls.git] == ["add", "commit", "push"]


@pytest.mark.parametrize("exists", [True, False])
def test_a_failed_checkout_still_rolls_the_claim_back(tmp_path, exists):
    """A dirty tree blocks either checkout; the claim must not be stranded."""
    reg_path = _registry(tmp_path)
    calls = _Calls(checkout_raises=True)

    with pytest.raises(subprocess.CalledProcessError):
        _run(tmp_path, calls, exists=exists, reg_path=reg_path)

    assert _codenames(reg_path) == []


def test_other_lanes_claims_are_untouched_by_a_rollback(tmp_path):
    other = {**CLAIM, "codename": "other", "node_id": "M1.2", "branch": "feature/rm-other"}
    reg_path = _registry(tmp_path, [CLAIM, other])
    calls = _Calls(push_raises=True)

    with pytest.raises(subprocess.CalledProcessError):
        _run(tmp_path, calls, exists=True, reg_path=reg_path)

    assert _codenames(reg_path) == ["other"]


def test_behind_count_is_reported_when_git_can_answer(tmp_path, monkeypatch, capsys):
    from specy_road.bundled_scripts import do_next_task_pickup_helpers as helpers

    monkeypatch.setattr(helpers, "commits_behind", lambda *_a: 4)
    helpers.announce_resumed_branch(tmp_path, "feature/rm-cn", "dev")

    out = capsys.readouterr().out
    assert "4 commit(s) behind dev" in out
    assert "git merge dev" in out


def test_behind_count_is_silent_when_git_cannot_answer(tmp_path, monkeypatch, capsys):
    from specy_road.bundled_scripts import do_next_task_pickup_helpers as helpers

    monkeypatch.setattr(helpers, "commits_behind", lambda *_a: None)
    helpers.announce_resumed_branch(tmp_path, "feature/rm-cn", "dev")

    assert "behind" not in capsys.readouterr().out
