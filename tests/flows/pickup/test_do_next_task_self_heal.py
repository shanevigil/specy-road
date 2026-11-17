"""Self-heal stale registry claim (F-014) unit tests."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock

import yaml

from specy_road.bundled_scripts.do_next_task_self_heal import (
    attempt_self_cleanup,
    detect_stale_claims,
    warn_about_stale_claims_before_pickup,
    warn_unresolved_rollback,
)


def _write_registry(path: Path, entries: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.dump({"version": 1, "entries": entries}, default_flow_style=False),
        encoding="utf-8",
    )


def test_attempt_self_cleanup_removes_entry_and_calls_git(tmp_path: Path) -> None:
    reg_path = tmp_path / "roadmap" / "registry.yaml"
    _write_registry(
        reg_path,
        [
            {"codename": "stale", "node_id": "M1.1", "branch": "feature/rm-stale", "touch_zones": []},
            {"codename": "other", "node_id": "M1.2", "branch": "feature/rm-other", "touch_zones": []},
        ],
    )
    git_calls: list[tuple[str, ...]] = []

    def fake_git(*args: str) -> None:
        git_calls.append(args)

    ok = attempt_self_cleanup(
        repo_root=tmp_path,
        registry_path=reg_path,
        node_id="M1.1",
        codename="stale",
        base="main",
        remote="origin",
        git_runner=fake_git,
    )
    assert ok is True
    # The 'stale' row was removed; 'other' kept.
    new = yaml.safe_load(reg_path.read_text(encoding="utf-8"))
    cns = [e["codename"] for e in new["entries"]]
    assert cns == ["other"]
    # add + commit + push were called.
    cmds = [c[0] for c in git_calls]
    assert cmds == ["add", "commit", "push"]


def test_attempt_self_cleanup_returns_true_when_nothing_to_clean(tmp_path: Path) -> None:
    reg_path = tmp_path / "roadmap" / "registry.yaml"
    _write_registry(
        reg_path,
        [{"codename": "other", "node_id": "M1.2", "branch": "feature/rm-other", "touch_zones": []}],
    )
    fake = MagicMock()
    ok = attempt_self_cleanup(
        repo_root=tmp_path,
        registry_path=reg_path,
        node_id="M1.1",
        codename="absent",
        base="main",
        remote="origin",
        git_runner=fake,
    )
    assert ok is True
    fake.assert_not_called()


def test_attempt_self_cleanup_returns_false_when_git_fails(tmp_path: Path) -> None:
    reg_path = tmp_path / "roadmap" / "registry.yaml"
    _write_registry(
        reg_path,
        [{"codename": "stale", "node_id": "M1.1", "branch": "feature/rm-stale", "touch_zones": []}],
    )

    def boom(*_args: str) -> None:
        raise subprocess.CalledProcessError(1, "git")

    ok = attempt_self_cleanup(
        repo_root=tmp_path,
        registry_path=reg_path,
        node_id="M1.1",
        codename="stale",
        base="main",
        remote="origin",
        git_runner=boom,
    )
    assert ok is False


def test_detect_stale_claims_in_repo_with_no_branches(tmp_path: Path) -> None:
    """A registry entry whose feature branch exists nowhere is reported."""
    subprocess.check_call(["git", "init", "-q"], cwd=tmp_path)
    subprocess.check_call(["git", "config", "user.email", "t@e.com"], cwd=tmp_path)
    subprocess.check_call(["git", "config", "user.name", "T"], cwd=tmp_path)
    reg = {
        "version": 1,
        "entries": [
            {"codename": "ghost", "node_id": "M1.1", "branch": "feature/rm-ghost"},
            {"codename": "garbage", "node_id": "M1.2", "branch": "not-a-feature-branch"},
        ],
    }
    out = detect_stale_claims(repo_root=tmp_path, reg=reg, remote="origin")
    # Only the feature/rm-* entry is considered; the malformed one is skipped.
    codenames = [e["codename"] for e in out]
    assert codenames == ["ghost"]


def _repo_with_branch(tmp_path: Path, branch: str | None) -> Path:
    """A repo with one commit and, when named, a local-only (unpushed) branch."""
    subprocess.check_call(["git", "init", "-q"], cwd=tmp_path)
    subprocess.check_call(["git", "config", "user.email", "t@e.com"], cwd=tmp_path)
    subprocess.check_call(["git", "config", "user.name", "T"], cwd=tmp_path)
    subprocess.check_call(["git", "commit", "-q", "--allow-empty", "-m", "init"], cwd=tmp_path)
    if branch:
        subprocess.check_call(["git", "branch", branch], cwd=tmp_path)
    return tmp_path


LIVE = {"codename": "live", "node_id": "M1.1", "branch": "feature/rm-live"}


def test_a_local_only_branch_is_not_stale_and_prints_nothing(tmp_path: Path, capsys) -> None:
    """Branches pushed only at merge exist locally alone; their claims are live."""
    root = _repo_with_branch(tmp_path, "feature/rm-live")
    reg = {"version": 1, "entries": [LIVE]}

    assert detect_stale_claims(repo_root=root, reg=reg, remote="origin") == []
    warn_about_stale_claims_before_pickup(repo_root=root, reg=reg, remote="origin")
    assert capsys.readouterr().err == ""


def test_a_remote_only_branch_is_not_stale(tmp_path: Path) -> None:
    root = _repo_with_branch(tmp_path, None)
    subprocess.check_call(
        ["git", "update-ref", "refs/remotes/origin/feature/rm-live", "HEAD"], cwd=root,
    )
    reg = {"version": 1, "entries": [LIVE]}
    assert detect_stale_claims(repo_root=root, reg=reg, remote="origin") == []


def test_a_missing_branch_warns_and_names_both_refs_checked(tmp_path: Path, capsys) -> None:
    root = _repo_with_branch(tmp_path, None)
    reg = {"version": 1, "entries": [LIVE]}

    warn_about_stale_claims_before_pickup(repo_root=root, reg=reg, remote="origin")

    err = capsys.readouterr().err
    assert "stale registry claim was left behind" in err
    assert "local refs/heads/feature/rm-live (absent)" in err
    assert "remote refs/remotes/origin/feature/rm-live (absent)" in err
    assert "abort-task-pickup --force" in err
    assert "confirm it is dead" in err


def test_a_failed_rollback_with_a_local_branch_gives_no_fix_lines(tmp_path: Path, capsys) -> None:
    root = _repo_with_branch(tmp_path, "feature/rm-live")

    warn_unresolved_rollback(
        repo_root=root, node_id="M1.1", codename="live",
        branch="feature/rm-live", remote="origin",
    )

    err = capsys.readouterr().err
    assert "not stale" in err
    assert "stale registry claim" not in err
    assert "abort-task-pickup" not in err
    assert "registry.yaml" not in err


def test_a_failed_rollback_with_no_branch_warns(tmp_path: Path, capsys) -> None:
    root = _repo_with_branch(tmp_path, None)

    warn_unresolved_rollback(
        repo_root=root, node_id="M1.1", codename="live",
        branch="feature/rm-live", remote="origin",
    )

    err = capsys.readouterr().err
    assert "stale registry claim was left behind" in err
    assert "automatic cleanup also failed" in err
    assert "local refs/heads/feature/rm-live (absent)" in err
