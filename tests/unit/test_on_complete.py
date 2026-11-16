"""Tests for on_complete (git-workflow + session + resolve_on_complete)."""

from __future__ import annotations

import pytest

from specy_road.git_workflow_config import (
    DEFAULT_ON_COMPLETE,
    on_complete_from_git_workflow,
    resolve_on_complete,
)
from specy_road.on_complete_session import (
    on_complete_session_path,
    read_on_complete_session,
    remove_on_complete_session,
    write_on_complete_session,
)


def _write_gw(tmp_path, **extra: str) -> None:
    (tmp_path / "roadmap").mkdir(parents=True)
    lines = ["version: 1", "integration_branch: main", "remote: origin"]
    for k, v in extra.items():
        lines.append(f"{k}: {v}")
    (tmp_path / "roadmap" / "git-workflow.yaml").write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )


def test_on_complete_from_git_workflow_default(tmp_path) -> None:
    _write_gw(tmp_path)
    assert on_complete_from_git_workflow(tmp_path) == DEFAULT_ON_COMPLETE


def test_on_complete_from_git_workflow_explicit(tmp_path) -> None:
    _write_gw(tmp_path, on_complete="merge")
    assert on_complete_from_git_workflow(tmp_path) == "merge"


def test_resolve_on_complete_cli_wins(tmp_path) -> None:
    _write_gw(tmp_path, on_complete="merge")
    assert (
        resolve_on_complete(tmp_path, cli="pr", session="auto") == "pr"
    )


def test_resolve_on_complete_session_second(tmp_path) -> None:
    _write_gw(tmp_path, on_complete="merge")
    assert resolve_on_complete(tmp_path, cli=None, session="auto") == "auto"


def test_resolve_on_complete_env_third(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_gw(tmp_path, on_complete="merge")
    monkeypatch.setenv("SPECY_ROAD_ON_COMPLETE", "auto")
    assert resolve_on_complete(tmp_path, cli=None, session=None) == "auto"


def test_resolve_on_complete_yaml_fourth(tmp_path) -> None:
    _write_gw(tmp_path, on_complete="merge")
    assert resolve_on_complete(tmp_path, cli=None, session=None) == "merge"


def test_resolve_on_complete_env_invalid_ignored(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_gw(tmp_path, on_complete="pr")
    monkeypatch.setenv("SPECY_ROAD_ON_COMPLETE", "nope")
    assert resolve_on_complete(tmp_path, cli=None, session=None) == "pr"


def test_session_round_trip(tmp_path) -> None:
    p = on_complete_session_path(tmp_path, "M1.2")
    write_on_complete_session(
        p,
        node_id="M1.2",
        codename="alpha",
        on_complete="pr",
    )
    assert read_on_complete_session(p, node_id="M1.2", codename="alpha") == "pr"
    remove_on_complete_session(p)
    assert not p.is_file()


def test_session_codename_mismatch(tmp_path) -> None:
    p = on_complete_session_path(tmp_path, "M1.2")
    write_on_complete_session(
        p,
        node_id="M1.2",
        codename="alpha",
        on_complete="merge",
    )
    assert read_on_complete_session(p, node_id="M1.2", codename="beta") is None


def test_invalid_on_complete_in_yaml_fails_load(tmp_path) -> None:
    from specy_road.git_workflow_config import load_git_workflow_config

    _write_gw(tmp_path, on_complete="invalid")
    data, err = load_git_workflow_config(tmp_path)
    assert data is None
    assert err is not None
