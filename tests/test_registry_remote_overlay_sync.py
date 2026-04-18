"""Tests for remote overlay sync helpers and telemetry status surfaces."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from tests.helpers import BUNDLED_SCRIPTS

if str(BUNDLED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(BUNDLED_SCRIPTS))
import roadmap_gui_settings as _rgs  # noqa: E402

from specy_road.git_workflow_config import working_tree_clean
from specy_road.pm_integration_registry import (
    describe_integration_branch_auto_ff as describe_integration_branch_auto_ff_pm,
)
from specy_road.registry_remote_overlay import (
    describe_integration_branch_auto_ff as describe_integration_branch_auto_ff_overlay,
    integration_branch_auto_ff_enabled,
    last_integration_auto_ff_status,
    last_registry_auto_fetch_status,
    maybe_auto_git_fetch,
    maybe_auto_integration_ff,
)
import specy_road.registry_remote_overlay as _registry_overlay


def _isolate_gui_settings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    gui = tmp_path / ".specy-road"
    gui.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(_rgs, "SETTINGS_DIR", gui)
    monkeypatch.setattr(_rgs, "SETTINGS_PATH", gui / "gui-settings.json")


def _write_gw(repo: Path) -> None:
    p = repo / "roadmap" / "git-workflow.yaml"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        "version: 1\nintegration_branch: main\nremote: origin\n",
        encoding="utf-8",
    )


def _init_integration_ff_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "ff"
    repo.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "t@example.com"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "T"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    roadmap = repo / "roadmap"
    roadmap.mkdir(parents=True)
    _write_gw(repo)
    (roadmap / "manifest.json").write_text('{"version":1,"includes":[]}\n', encoding="utf-8")
    subprocess.run(["git", "add", "roadmap"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo, check=True, capture_output=True)
    return repo


def _patch_subprocess_run_track_fetch_merge(
    monkeypatch: pytest.MonkeyPatch,
) -> list[list[str]]:
    tracked: list[list[str]] = []
    real_run = subprocess.run

    def fake_run(
        args: list[str],
        **kwargs: object,
    ) -> subprocess.CompletedProcess[str]:
        a = list(args)
        if a[:2] == ["git", "fetch"] and "--quiet" in a:
            tracked.append(a)
            return subprocess.CompletedProcess(a, 0, "", "")
        if len(a) >= 3 and a[0] == "git" and a[1] == "merge" and a[2] == "--ff-only":
            tracked.append(a)
            return subprocess.CompletedProcess(a, 0, "", "")
        return real_run(args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(subprocess, "run", fake_run)
    return tracked


def test_working_tree_clean(tmp_path: Path) -> None:
    repo = _init_integration_ff_repo(tmp_path)
    assert working_tree_clean(repo) is True
    (repo / "untracked.txt").write_text("x", encoding="utf-8")
    assert working_tree_clean(repo) is False


def test_integration_branch_auto_ff_enabled_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _isolate_gui_settings(monkeypatch, tmp_path)
    monkeypatch.delenv("SPECY_ROAD_GUI_AUTO_INTEGRATION_FF", raising=False)
    root = tmp_path / "x"
    root.mkdir()
    assert integration_branch_auto_ff_enabled(root) is False
    monkeypatch.setenv("SPECY_ROAD_GUI_AUTO_INTEGRATION_FF", "1")
    assert integration_branch_auto_ff_enabled(root) is True
    monkeypatch.setenv("SPECY_ROAD_GUI_AUTO_INTEGRATION_FF", "0")
    assert integration_branch_auto_ff_enabled(root) is False


def test_maybe_auto_integration_ff_skips_without_env_or_settings(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _isolate_gui_settings(monkeypatch, tmp_path)
    monkeypatch.delenv("SPECY_ROAD_GUI_AUTO_INTEGRATION_FF", raising=False)
    repo = _init_integration_ff_repo(tmp_path)
    calls: list[list[str]] = []

    def fake_run(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(list(args))
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    maybe_auto_integration_ff(repo)
    assert calls == []


def test_maybe_auto_integration_ff_skips_wrong_branch(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("SPECY_ROAD_GUI_AUTO_INTEGRATION_FF", "1")
    repo = _init_integration_ff_repo(tmp_path)
    subprocess.run(["git", "checkout", "-b", "feature/x"], cwd=repo, check=True, capture_output=True)
    calls = _patch_subprocess_run_track_fetch_merge(monkeypatch)
    maybe_auto_integration_ff(repo)
    assert calls == []


def test_maybe_auto_integration_ff_skips_dirty_tree(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("SPECY_ROAD_GUI_AUTO_INTEGRATION_FF", "1")
    repo = _init_integration_ff_repo(tmp_path)
    (repo / "dirty.txt").write_text("z", encoding="utf-8")
    calls = _patch_subprocess_run_track_fetch_merge(monkeypatch)
    maybe_auto_integration_ff(repo)
    assert calls == []


def test_maybe_auto_integration_ff_runs_fetch_and_merge(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("SPECY_ROAD_GUI_AUTO_INTEGRATION_FF", "1")
    repo = _init_integration_ff_repo(tmp_path)
    _registry_overlay._LAST_INTEGRATION_FF_MONO.clear()
    calls = _patch_subprocess_run_track_fetch_merge(monkeypatch)
    maybe_auto_integration_ff(repo)
    assert calls[0] == ["git", "fetch", "--quiet", "origin"]
    assert calls[1] == ["git", "merge", "--ff-only", "origin/main"]
    st = last_integration_auto_ff_status(repo)
    assert isinstance(st, dict)
    assert st.get("ok") is True
    assert st.get("step") == "merge_ff_only"
    maybe_auto_integration_ff(repo)
    assert len(calls) == 2


def test_maybe_auto_integration_ff_respects_throttle(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("SPECY_ROAD_GUI_AUTO_INTEGRATION_FF", "1")
    monkeypatch.setenv("SPECY_ROAD_GUI_INTEGRATION_FF_INTERVAL_S", "3600")
    repo = _init_integration_ff_repo(tmp_path)
    _registry_overlay._LAST_INTEGRATION_FF_MONO.clear()
    calls = _patch_subprocess_run_track_fetch_merge(monkeypatch)
    maybe_auto_integration_ff(repo)
    assert len(calls) == 2
    maybe_auto_integration_ff(repo)
    assert len(calls) == 2


def test_describe_integration_branch_auto_ff_overlay_export_matches_pm_module(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("SPECY_ROAD_GUI_AUTO_INTEGRATION_FF", "1")
    repo = _init_integration_ff_repo(tmp_path)
    tip = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    subprocess.run(
        ["git", "update-ref", "refs/remotes/origin/main", tip],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    _registry_overlay._LAST_INTEGRATION_FF_MONO.clear()
    maybe_auto_integration_ff(repo)
    via_overlay = describe_integration_branch_auto_ff_overlay(repo)
    via_pm = describe_integration_branch_auto_ff_pm(repo)
    assert via_overlay is not None
    assert via_pm is not None
    for k, v in via_pm.items():
        assert via_overlay.get(k) == v
    last = via_overlay.get("last_auto_ff_attempt")
    assert isinstance(last, dict)
    assert "ok" in last


def test_maybe_auto_git_fetch_records_nonzero_exit_status(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("SPECY_ROAD_GUI_REGISTRY_AUTO_FETCH", "1")
    monkeypatch.setenv("SPECY_ROAD_GUI_REGISTRY_FETCH_INTERVAL_S", "0")
    repo = _init_integration_ff_repo(tmp_path)
    real_run = subprocess.run

    def _fail_fetch(
        args: list[str],
        **kwargs: object,
    ) -> subprocess.CompletedProcess[str]:
        a = list(args)
        if a[:2] == ["git", "fetch"] and "--quiet" in a:
            return subprocess.CompletedProcess(a, 1, "", "fatal: auth failed")
        return real_run(args, **kwargs)  # type: ignore[arg-type]

    _registry_overlay._LAST_FETCH_MONO.clear()
    monkeypatch.setattr(subprocess, "run", _fail_fetch)
    maybe_auto_git_fetch(repo, "origin")
    st = last_registry_auto_fetch_status(repo)
    assert isinstance(st, dict)
    assert st.get("ok") is False
    assert st.get("reason") == "non_zero_exit"
    assert st.get("step") == "fetch"
    assert st.get("returncode") == 1
    assert "auth failed" in str(st.get("error", ""))


def test_maybe_auto_git_fetch_records_timeout_status(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("SPECY_ROAD_GUI_REGISTRY_AUTO_FETCH", "1")
    monkeypatch.setenv("SPECY_ROAD_GUI_REGISTRY_FETCH_INTERVAL_S", "0")
    repo = _init_integration_ff_repo(tmp_path)
    real_run = subprocess.run

    def _timeout_fetch(
        args: list[str],
        **kwargs: object,
    ) -> subprocess.CompletedProcess[str]:
        a = list(args)
        if a[:2] == ["git", "fetch"] and "--quiet" in a:
            raise subprocess.TimeoutExpired(cmd=["git", "fetch"], timeout=0.1)
        return real_run(args, **kwargs)  # type: ignore[arg-type]

    _registry_overlay._LAST_FETCH_MONO.clear()
    monkeypatch.setattr(subprocess, "run", _timeout_fetch)
    maybe_auto_git_fetch(repo, "origin")
    st = last_registry_auto_fetch_status(repo)
    assert isinstance(st, dict)
    assert st.get("ok") is False
    assert st.get("reason") == "timeout"
    assert st.get("step") == "fetch"


def test_maybe_auto_integration_ff_records_merge_nonzero_exit_status(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("SPECY_ROAD_GUI_AUTO_INTEGRATION_FF", "1")
    repo = _init_integration_ff_repo(tmp_path)
    real_run = subprocess.run

    def _fail_merge(
        args: list[str],
        **kwargs: object,
    ) -> subprocess.CompletedProcess[str]:
        a = list(args)
        if a[:2] == ["git", "fetch"]:
            return subprocess.CompletedProcess(a, 0, "", "")
        if len(a) >= 3 and a[:3] == ["git", "merge", "--ff-only"]:
            return subprocess.CompletedProcess(a, 1, "", "fatal: not possible")
        return real_run(args, **kwargs)  # type: ignore[arg-type]

    _registry_overlay._LAST_INTEGRATION_FF_MONO.clear()
    monkeypatch.setattr(subprocess, "run", _fail_merge)
    maybe_auto_integration_ff(repo)
    st = last_integration_auto_ff_status(repo)
    assert isinstance(st, dict)
    assert st.get("ok") is False
    assert st.get("reason") == "non_zero_exit"
    assert st.get("step") == "merge_ff_only"
    assert st.get("returncode") == 1
    assert "not possible" in str(st.get("error", ""))
