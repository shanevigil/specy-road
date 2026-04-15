from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

import roadmap_gui_remote as rgr


def _gh_pr(
    *,
    state: str,
    merged: bool,
    merged_at: str | None = None,
) -> dict:
    return {
        "state": state,
        "merged": merged,
        "merged_at": merged_at,
        "html_url": "https://github.com/o/r/pull/1",
        "title": "t",
        "user": {"login": "u"},
        "assignees": [],
        "updated_at": "2026-01-15T00:00:00Z",
    }


@pytest.mark.parametrize(
    ("entry", "expected"),
    [
        (None, False),
        ({}, False),
        ({"kind": "remote_tip"}, False),
        ({"kind": "github_pr", "pr_state": "open", "merged": False}, False),
        ({"kind": "github_pr", "pr_state": "merged", "merged": True}, False),
        ({"kind": "github_pr", "pr_state": "rejected", "merged": False}, True),
        ({"kind": "gitlab_mr", "pr_state": "closed", "merged": False}, True),
        ({"kind": "gitlab_mr", "pr_state": "closed", "merged": True}, False),
    ],
)
def test_enrichment_is_mr_rejected(entry: dict | None, expected: bool) -> None:
    assert rgr.enrichment_is_mr_rejected(entry) is expected


def test_github_pr_detail_open_pr(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(rgr, "fetch_pr_hint", lambda _gr, _br: "hint")

    open_pr = _gh_pr(state="open", merged=False)
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = [open_pr]

    with patch("roadmap_gui_remote.requests.get", return_value=resp) as g:
        out = rgr._github_pr_detail("o/r", "feature/x", "tok")

    assert out is not None
    assert out["kind"] == "github_pr"
    assert out["pr_state"] == "open"
    assert out["merged"] is False
    g.assert_called_once()


def test_github_pr_detail_merged_from_state_all(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(rgr, "fetch_pr_hint", lambda _gr, _br: "hint")

    merged = _gh_pr(state="closed", merged=True, merged_at="2026-01-10T00:00:00Z")
    empty = MagicMock()
    empty.status_code = 200
    empty.json.return_value = []
    all_resp = MagicMock()
    all_resp.status_code = 200
    all_resp.json.return_value = [merged]

    with patch("roadmap_gui_remote.requests.get", side_effect=[empty, all_resp]):
        out = rgr._github_pr_detail("o/r", "feature/x", "tok")

    assert out is not None
    assert out["pr_state"] == "merged"
    assert out["merged"] is True


def test_github_pr_detail_rejected_closed_unmerged(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(rgr, "fetch_pr_hint", lambda _gr, _br: "hint")

    rej = _gh_pr(state="closed", merged=False, merged_at=None)
    empty = MagicMock()
    empty.status_code = 200
    empty.json.return_value = []
    all_resp = MagicMock()
    all_resp.status_code = 200
    all_resp.json.return_value = [rej]

    with patch("roadmap_gui_remote.requests.get", side_effect=[empty, all_resp]):
        out = rgr._github_pr_detail("o/r", "feature/x", "tok")

    assert out is not None
    assert out["pr_state"] == "rejected"
    assert out["merged"] is False


def test_github_pr_detail_open_not_list_falls_through_to_all(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Non-list JSON on the open query must not crash; state=all still runs."""
    monkeypatch.setattr(rgr, "fetch_pr_hint", lambda _gr, _br: "hint")

    merged = _gh_pr(state="closed", merged=True, merged_at="2026-01-10T00:00:00Z")
    bad_open = MagicMock()
    bad_open.status_code = 200
    bad_open.json.return_value = {"message": "validation failed"}
    all_resp = MagicMock()
    all_resp.status_code = 200
    all_resp.json.return_value = [merged]

    with patch("roadmap_gui_remote.requests.get", side_effect=[bad_open, all_resp]):
        out = rgr._github_pr_detail("o/r", "feature/x", "tok")

    assert out is not None
    assert out["pr_state"] == "merged"


def test_gitlab_mr_detail_opened_mr(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(rgr, "fetch_pr_hint", lambda _gr, _br: "hint")
    mr = {
        "title": "m",
        "web_url": "http://gl/m/1",
        "author": {"username": "a"},
        "assignees": [],
        "updated_at": "2026-01-01",
    }
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = [mr]

    gr = {"provider": "gitlab", "repo": "g/p", "token": "t", "base_url": ""}
    with patch("roadmap_gui_remote.requests.get", return_value=resp) as g:
        out = rgr._gitlab_mr_detail(gr, "g/p", "feature/y", "tok")

    assert out is not None
    assert out["kind"] == "gitlab_mr"
    assert out["pr_state"] == "open"
    assert out["merged"] is False
    assert "merge_requests" in str(g.call_args[0][0])


def test_gitlab_mr_detail_merged_after_empty_opened(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(rgr, "fetch_pr_hint", lambda _gr, _br: "hint")
    merged_mr = {
        "title": "m",
        "web_url": "http://gl/m/1",
        "author": {"username": "a"},
        "assignees": [],
        "updated_at": "2026-01-01",
        "merge_commit_sha": "abc123",
    }
    empty = MagicMock()
    empty.status_code = 200
    empty.json.return_value = []
    merged_resp = MagicMock()
    merged_resp.status_code = 200
    merged_resp.json.return_value = [merged_mr]

    gr = {"provider": "gitlab", "repo": "g/p", "token": "t", "base_url": ""}
    with patch("roadmap_gui_remote.requests.get", side_effect=[empty, merged_resp]):
        out = rgr._gitlab_mr_detail(gr, "g/p", "feature/y", "tok")

    assert out is not None
    assert out["pr_state"] == "merged"
    assert out["merged"] is True


def test_gitlab_mr_detail_rejected_closed_without_merge_commit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(rgr, "fetch_pr_hint", lambda _gr, _br: "hint")
    closed_mr = {
        "title": "m",
        "web_url": "http://gl/m/1",
        "author": {"username": "a"},
        "assignees": [],
        "updated_at": "2026-01-01",
        "merge_commit_sha": None,
    }
    e1 = MagicMock()
    e1.status_code = 200
    e1.json.return_value = []
    e2 = MagicMock()
    e2.status_code = 200
    e2.json.return_value = []
    e3 = MagicMock()
    e3.status_code = 200
    e3.json.return_value = [closed_mr]

    gr = {"provider": "gitlab", "repo": "g/p", "token": "t", "base_url": ""}
    with patch("roadmap_gui_remote.requests.get", side_effect=[e1, e2, e3]):
        out = rgr._gitlab_mr_detail(gr, "g/p", "feature/y", "tok")

    assert out is not None
    assert out["pr_state"] == "rejected"
    assert out["merged"] is False


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
