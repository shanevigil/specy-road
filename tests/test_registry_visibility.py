from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from specy_road.registry_visibility import (
    build_registry_visibility,
    count_remote_feature_rm_refs,
    registry_visibility_enabled,
)


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def test_count_remote_feature_rm_refs_zero_without_git(tmp_path: Path) -> None:
    assert count_remote_feature_rm_refs(tmp_path, "origin") == 0


def test_count_remote_feature_rm_refs_counts_remote_tracking_pattern(
    tmp_path: Path,
) -> None:
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "t@e.st")
    _git(tmp_path, "config", "user.name", "test")
    (tmp_path / "f.txt").write_text("x")
    _git(tmp_path, "add", "f.txt")
    _git(tmp_path, "commit", "-m", "init")
    r = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=True,
    )
    sha = r.stdout.strip()
    _git(
        tmp_path,
        "update-ref",
        "refs/remotes/origin/feature/rm-one",
        sha,
    )
    _git(
        tmp_path,
        "update-ref",
        "refs/remotes/origin/feature/rm-two",
        sha,
    )
    assert count_remote_feature_rm_refs(tmp_path, "origin") == 2
    assert count_remote_feature_rm_refs(tmp_path, "upstream") == 0


def test_build_registry_visibility_none_when_env_disabled(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SPECY_ROAD_GUI_REGISTRY_VISIBILITY", "0")
    assert registry_visibility_enabled() is False
    gw = {
        "resolved": {
            "integration_branch": "dev",
            "remote": "origin",
            "git_branch_current": "dev",
        },
    }
    assert build_registry_visibility(tmp_path, {"entries": []}, gw) is None


def test_build_registry_visibility_on_integration_branch_flags() -> None:
    root = Path("/tmp")
    reg = {"entries": []}
    gw = {
        "resolved": {
            "integration_branch": "dev",
            "remote": "origin",
            "git_branch_current": "dev",
        },
    }
    v = build_registry_visibility(root, reg, gw)
    assert v is not None
    assert v["on_integration_branch"] is True
    assert v["local_registry_entry_count"] == 0


def test_build_registry_visibility_not_on_integration_when_branch_differs() -> None:
    v = build_registry_visibility(
        Path("/tmp"),
        {"entries": []},
        {
            "resolved": {
                "integration_branch": "dev",
                "remote": "origin",
                "git_branch_current": "feature/rm-x",
            },
        },
    )
    assert v is not None
    assert v["on_integration_branch"] is False


def test_build_registry_visibility_tolerates_non_str_resolved_fields() -> None:
    """Malformed payloads should not raise (e.g. non-string YAML edge cases)."""
    v = build_registry_visibility(
        Path("/tmp"),
        {"entries": []},
        {
            "resolved": {
                "integration_branch": 123,
                "remote": None,
                "git_branch_current": "dev",
            },
        },
    )
    assert v is not None
    assert v["remote_feature_rm_ref_count"] == 0
