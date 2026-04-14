"""Tests for roadmap_gui_remote (outbound git/LLM checks) with mocks."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

import roadmap_gui_remote as rgr


def test_test_git_remote_github_ok() -> None:
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    with patch("roadmap_gui_remote.requests.get", return_value=mock_resp) as g:
        ok, msg = rgr.test_git_remote(
            {"provider": "github", "repo": "o/r", "token": "t"},
        )
    assert ok is True
    assert "OK" in msg
    g.assert_called_once()
    assert "api.github.com/repos/o/r" in str(g.call_args)


def test_test_git_remote_github_not_200() -> None:
    mock_resp = MagicMock()
    mock_resp.status_code = 401
    mock_resp.text = "nope"
    with patch("roadmap_gui_remote.requests.get", return_value=mock_resp):
        ok, msg = rgr.test_git_remote(
            {"provider": "github", "repo": "o/r", "token": "t"},
        )
    assert ok is False
    assert "401" in msg


def test_test_git_remote_missing_repo() -> None:
    ok, msg = rgr.test_git_remote(
        {"provider": "github", "repo": "", "token": "t"},
    )
    assert ok is False
    assert "required" in msg.lower()


@pytest.mark.parametrize(
    ("provider", "url_part"),
    [
        ("gitlab", "gitlab.com"),
        ("custom", "gitlab.com"),
    ],
)
def test_test_git_remote_gitlab_ok(provider: str, url_part: str) -> None:
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    with patch("roadmap_gui_remote.requests.get", return_value=mock_resp) as g:
        ok, msg = rgr.test_git_remote(
            {
                "provider": provider,
                "repo": "group/proj",
                "token": "t",
                "base_url": "",
            },
        )
    assert ok is True
    assert url_part in str(g.call_args[0][0])


def test_test_llm_connection_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(rgr, "apply_llm_env_from_settings", lambda _llm: None)

    def fake_ping() -> None:
        return None

    with patch("review_node.ping_llm", fake_ping):
        ok, msg = rgr.test_llm_connection({"backend": "openai"})
    assert ok is True
    assert "responded" in msg.lower()


def test_test_llm_connection_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(rgr, "apply_llm_env_from_settings", lambda _llm: None)

    def bad_ping() -> None:
        raise RuntimeError("refused")

    with patch("review_node.ping_llm", bad_ping):
        ok, msg = rgr.test_llm_connection({})
    assert ok is False
    assert "refused" in msg
