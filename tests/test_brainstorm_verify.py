"""Brainstorm v2: rounds, allocation, shards, evidence, verify, clusters, decisions, promote.

In-process through the CLI entry (no subprocess), on a copy of the dogfood
fixture, plus unit tests on the session fields and the verifier with a stub
fetcher. The prompt contracts the design note names are pinned here: round 1
plans without the roadmap or research, later rounds regenerate against the
pool, shards are independent, converge plays critics and names overlap
relations, triage is the human's, verify asks before it fetches.
"""

from __future__ import annotations

import io
import json
import shutil
from pathlib import Path

import pytest

from tests.helpers import DOGFOOD

from specy_road.bundled_scripts import brainstorm_cli
from specy_road.bundled_scripts import brainstorm_verify as bv
from specy_road.bundled_scripts.brainstorm_fields import parse_origin, parse_overlap, source_record
from specy_road.bundled_scripts.brainstorm_prompt import render_shard_prompt
from specy_road.bundled_scripts.brainstorm_session import (
    BrainstormError,
    BrainstormSession,
    add_idea,
    idea_from_dict,
    read_session,
    session_path,
    write_session,
)

SLUG = "how-do-we-expand-payments"


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    dest = tmp_path / "repo"
    shutil.copytree(DOGFOOD, dest)
    return dest


def _cli(repo: Path, *args: str) -> tuple[int, str, str]:
    import contextlib

    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            brainstorm_cli.main([*args, "--repo-root", str(repo)])
            code = 0
        except SystemExit as e:
            code = int(e.code or 0)
    return code, out.getvalue(), err.getvalue()


def _start(repo: Path, *extra: str) -> tuple[int, str, str]:
    return _cli(repo, "start", "--topic", "How do we expand payments?", "--under", "M1", *extra)


def _prompt(repo: Path, suffix: str = "") -> str:
    return (repo / "work" / f"brainstorm-{SLUG}{suffix}-prompt.md").read_text(encoding="utf-8")


def _session(repo: Path) -> BrainstormSession:
    return read_session(repo, SLUG)


# --- evidence and verify -----------------------------------------------------

def test_evidence_prompt_covers_the_shortlist_only(repo: Path) -> None:
    _start(repo)
    for t in ("One", "Two", "Three"):
        _cli(repo, "add-idea", "--title", t)
    code, _, err = _cli(repo, "evidence")
    assert code == 1 and "nothing to source" in err
    _cli(repo, "revise", "B1", "--recommendation", "strong")
    _cli(repo, "revise", "B2", "--recommendation", "park")
    code, out, _ = _cli(repo, "evidence")
    assert code == 0 and "1 idea(s)" in out
    text = _prompt(repo, "-evidence")
    assert "**B1** One" in text and "B2" not in text.split("## Ideas")[1].split("## Record")[0]
    assert "verbatim quote" in text and "disconfirm" in text
    assert "Never claim to have used a named research product" in text
    code, out, _ = _cli(repo, "evidence", "B3", "B2")
    assert code == 0 and "2 idea(s)" in out


def test_add_evidence_builds_a_source_record_and_mirrors_the_url(repo: Path) -> None:
    _start(repo)
    _cli(repo, "add-idea", "--title", "One", "--evidence", "https://example.com/a")
    code, out, _ = _cli(repo, "add-evidence", "B1", "--url", "https://example.com/a", "--quote", "exact words",
                        "--supports", "SMBs want links", "--stance", "for", "--tool", "claude WebFetch",
                        "--source-type", "official-doc", "--retrieved-at", "2026-10-27")
    assert code == 0 and "source 1" in out
    _cli(repo, "add-evidence", "B1", "--url", "https://example.com/b", "--stance", "against")
    idea = _session(repo).by_id("B1")
    assert idea.evidence == ["https://example.com/a", "https://example.com/b"]
    assert idea.sources[0]["tool"] == "claude WebFetch" and idea.sources[0]["retrieved_at"] == "2026-10-27"
    assert idea.sources[1]["stance"] == "against" and "quote" not in idea.sources[1]
    code, _, err = _cli(repo, "add-evidence", "B1", "--url", "https://x", "--quote", "x" * 301)
    assert code == 1 and "300" in err


def test_check_source_states(monkeypatch) -> None:
    pages = {"https://example.com/ok": (200, "<p>Some  exact\nwords here</p>"),
             "https://example.com/miss": (200, "<p>other</p>"),
             "https://example.com/paywall": (403, ""), "https://example.com/gone": (404, "")}
    monkeypatch.setattr(bv, "_is_off_host", lambda host: host != "example.com")

    def fetch(url):
        if url.endswith("boom"):
            raise OSError("down")
        return pages[url]

    assert bv.check_source({"url": "https://example.com/ok", "quote": "exact words"}, fetch) == "retrieved"
    assert bv.check_source({"url": "https://example.com/ok"}, fetch) == "retrieved"
    assert bv.check_source({"url": "https://example.com/miss", "quote": "exact words"}, fetch) == "not-found"
    assert bv.check_source({"url": "https://example.com/paywall", "quote": "x"}, fetch) == "blocked"
    assert bv.check_source({"url": "https://example.com/gone", "quote": "x"}, fetch) == "not-found"
    assert bv.check_source({"url": "https://example.com/boom", "quote": "x"}, fetch) == "blocked"
    assert bv.check_source({"url": "http://example.com/ok", "quote": "x"}, fetch) == "blocked"
    assert bv.check_source({"url": "https://localhost/ok", "quote": "x"}, fetch) == "blocked"


def test_verify_asks_before_fetching_and_records_states(repo: Path, monkeypatch) -> None:
    _start(repo)
    _cli(repo, "add-idea", "--title", "One")
    _cli(repo, "add-evidence", "B1", "--url", "https://example.com/ok", "--quote", "exact words")
    _cli(repo, "add-evidence", "B1", "--url", "https://example.com/miss", "--quote", "exact words")
    calls: list[str] = []

    def fetch(url):
        calls.append(url)
        return 200, "exact words" if url.endswith("ok") else "nope"

    monkeypatch.setattr(bv, "default_fetch", fetch)
    monkeypatch.setattr(bv, "_is_off_host", lambda host: False)
    monkeypatch.setattr("sys.stdin", io.StringIO(""))          # not a TTY, no --yes: nothing fetched
    code, out, _ = _cli(repo, "verify")
    assert code == 1 and "would fetch 2 URL(s)" in out and "pass --yes" in out and calls == []
    assert all(s["verification"] == "unverified" for s in _session(repo).by_id("B1").sources)
    code, out, _ = _cli(repo, "verify", "--yes")
    assert code == 0 and sorted(calls) == ["https://example.com/miss", "https://example.com/ok"]
    states = {s["url"]: s["verification"] for s in _session(repo).by_id("B1").sources}
    assert states == {"https://example.com/ok": "retrieved", "https://example.com/miss": "not-found"}
    assert "B1 retrieved" in out and "B1 not-found" in out
    code, out, _ = _cli(repo, "verify", "--yes")
    assert code == 0 and "nothing unverified" in out and len(calls) == 2


def test_verify_interactive_answer(monkeypatch) -> None:
    class Tty(io.StringIO):
        def isatty(self):
            return True

    monkeypatch.setattr("builtins.input", lambda _p="": "y")
    assert bv.confirm(["https://a"], yes=False, stdin=Tty(), out=io.StringIO())
    monkeypatch.setattr("builtins.input", lambda _p="": "")
    assert not bv.confirm(["https://a"], yes=False, stdin=Tty(), out=io.StringIO())


def test_default_fetch_checks_every_redirect_hop(monkeypatch) -> None:
    """A public page must not redirect the fetch onto a private host or plain http."""
    import types

    class Resp:
        def __init__(self, status, headers=None, body=b""):
            self.status_code, self.headers, self._body = status, headers or {}, body
            self.encoding = "utf-8"
            self.is_redirect = status in (301, 302, 303, 307)
            self.is_permanent_redirect = status in (301, 308)

        def iter_content(self, _n):
            yield self._body

    calls: list[str] = []
    pages = {"https://example.com/a": Resp(302, {"Location": "http://127.0.0.1/secret"}),
             "https://example.com/b": Resp(302, {"Location": "/c"}),
             "https://example.com/c": Resp(200, body=b"<p>exact words</p>")}

    def get(url, **kw):
        assert kw.get("allow_redirects") is False
        calls.append(url)
        return pages[url]

    fake = types.SimpleNamespace(get=get, compat=types.SimpleNamespace(urljoin=lambda b, l: l if l.startswith("http") else b.rsplit("/", 1)[0] + l))
    monkeypatch.setitem(__import__("sys").modules, "requests", fake)
    monkeypatch.setattr(bv, "_is_off_host", lambda host: host != "example.com")
    with pytest.raises(ValueError, match="refusing http://127.0.0.1/secret"):
        bv.default_fetch("https://example.com/a")
    assert calls == ["https://example.com/a"]
    assert bv.default_fetch("https://example.com/b") == (200, "<p>exact words</p>")
    assert bv.check_source({"url": "https://example.com/a", "quote": "secret"}, bv.default_fetch) == "blocked"
