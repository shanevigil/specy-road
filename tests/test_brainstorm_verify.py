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
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from tests.helpers import DOGFOOD, REPO, script_subprocess_env

from specy_road.bundled_scripts import brainstorm_cli
from specy_road.bundled_scripts import brainstorm_verify as bv
from specy_road.bundled_scripts.brainstorm_session import (
    BrainstormSession,
    Idea,
    read_session,
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


def _prompt(repo: Path, pass_name: str = "r1") -> str:
    return (repo / "work" / f"brainstorm-{SLUG}-{pass_name}-prompt.md").read_text(encoding="utf-8")


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
    _cli(repo, "revise", "B3", "--recommendation", "consider")
    code, out, _ = _cli(repo, "evidence")
    assert code == 0 and "1 idea(s)" in out
    ideas = _prompt(repo, "evidence").split("## Ideas")[1].split("## Record")[0]
    assert "**B1** One" in ideas and "B2" not in ideas and "B3" not in ideas
    text = _prompt(repo, "evidence")
    assert "verbatim quote" in text and "disconfirm" in text
    assert "Never claim to have used a named research product" in text
    code, out, err = _cli(repo, "evidence", "B3", "B2")
    assert code == 0 and "2 idea(s)" in out and "warning" not in err
    for n in range(4, 17):
        _cli(repo, "add-idea", "--title", f"Idea {n}")
    code, out, err = _cli(repo, "evidence", *[f"B{n}" for n in range(1, 16)])
    assert code == 0 and "15 idea(s)" in out and "warning" not in err
    code, out, err = _cli(repo, "evidence", *[f"B{n}" for n in range(1, 17)])
    assert code == 0 and "16 idea(s)" in out and "warning: 16 ideas selected" in err


def test_add_evidence_builds_a_source_record_and_mirrors_the_url(repo: Path) -> None:
    _start(repo)
    _cli(repo, "add-idea", "--title", "One", "--evidence", "https://example.com/a")
    code, out, _ = _cli(repo, "add-evidence", "B1", "--url", "https://example.com/a", "--quote", "exact words",
                        "--supports", "SMBs want links", "--stance", "for", "--tool", "claude WebFetch",
                        "--source-type", "official-doc", "--retrieved-at", "2026-10-27")
    assert code == 0 and "source 1" in out
    code, _, err = _cli(repo, "add-evidence", "B1", "--url", "https://example.com/b", "--stance", "against")
    assert code != 0 and "--quote is required" in err
    _cli(repo, "add-evidence", "B1", "--url", "https://example.com/b", "--quote", "b words", "--stance", "against")
    idea = _session(repo).by_id("B1")
    assert idea.evidence == ["https://example.com/a", "https://example.com/b"]
    assert idea.sources[0]["tool"] == "claude WebFetch" and idea.sources[0]["retrieved_at"] == "2026-10-27"
    assert idea.sources[1]["stance"] == "against" and idea.sources[1]["quote"] == "b words"
    code, _, err = _cli(repo, "add-evidence", "B1", "--url", "https://x", "--quote", "x" * 301)
    assert code == 1 and "300" in err


def test_check_source_states(monkeypatch) -> None:
    pages = {"https://example.com/ok": (200, "<p>Some  exact\nwords here</p>"),
             "https://example.com/miss": (200, "<p>other</p>"),
             "https://example.com/paywall": (403, ""), "https://example.com/gone": (404, ""),
             "https://example.com/": (200, ""),
             "https://example.com/inline": (200, "<p>defined in <code>.git/config</code>.</p>"
                                                 "<p><b>Ex</b>port <em>files </em>, then</p><td>end</td>")}
    monkeypatch.setattr(bv, "_is_off_host", lambda host: host != "example.com")
    calls: list[str] = []

    def fetch(url):
        calls.append(url)
        if url.endswith("boom"):
            raise OSError("down")
        return pages[url]

    assert bv.check_source({"url": "https://example.com/ok", "quote": "exact words"}, fetch) == "matched"
    assert bv.check_source({"url": "https://example.com/ok"}, fetch) == "not-found"   # no quote, nothing verified
    assert bv.check_source({"url": "https://example.com/miss", "quote": "exact words"}, fetch) == "not-found"
    # Inline tags are not word breaks; a space before punctuation is dropped on both sides.
    for quote in ("defined in .git/config.", "Export files, then", "files , then"):
        assert bv.check_source({"url": "https://example.com/inline", "quote": quote}, fetch) == "matched"
    assert bv.check_source({"url": "https://example.com/inline", "quote": "thenend"}, fetch) == "not-found"
    assert bv.check_source({"url": "https://example.com/paywall", "quote": "x"}, fetch) == "blocked"
    assert bv.check_source({"url": "https://example.com/gone", "quote": "x"}, fetch) == "not-found"
    assert bv.check_source({"url": "https://example.com/boom", "quote": "x"}, fetch) == "blocked"
    assert bv.check_source({"url": "http://example.com/ok", "quote": "x"}, fetch) == "blocked"
    assert bv.check_source({"url": "https://localhost/ok", "quote": "x"}, fetch) == "blocked"
    assert calls.count("https://example.com/") == 1


_IPV6 = "2606:4700:4700::1111"


@pytest.mark.parametrize(("page", "page_status", "root_status", "state", "root"), [
    ("https://example.com/missing", 404, 404, "blocked", "https://example.com/"),
    ("https://example.com/missing", 404, 200, "not-found", "https://example.com/"),
    ("https://example.com/missing", 404, "down", "blocked", "https://example.com/"),
    ("https://example.com/gone", 410, 404, "blocked", "https://example.com/"),
    ("https://example.com/gone", 410, 200, "not-found", "https://example.com/"),
    ("https://example.com/gone", 410, "down", "blocked", "https://example.com/"),
    ("https://user:secret@example.com:8443/missing?q=1#frag", 404, 200, "not-found", "https://example.com:8443/"),
    (f"https://[{_IPV6}]/missing", 404, 200, "not-found", f"https://[{_IPV6}]/"),
    (f"https://user:secret@[{_IPV6}]:8443/missing?q=1#frag", 404, 200, "not-found", f"https://[{_IPV6}]:8443/"),
    (f"https://[{_IPV6}]:443/missing", 404, 200, "not-found", f"https://[{_IPV6}]/"),
    ("https://example.com/ok", 200, "down", "matched", None),
    ("https://example.com/err", 500, "down", "not-found", None),
])
def test_a_missing_page_follows_its_origin_root(monkeypatch, page, page_status, root_status, state, root) -> None:
    """404 and 410 ask the origin root; only a 200 root stays not-found. A 200 or 500 page does not ask."""
    monkeypatch.setattr(bv.socket, "getaddrinfo", _example_com_is_public)
    calls: list[str] = []

    def fetch(url: str):
        calls.append(url)
        if root is not None and url == root:
            if root_status == "down":
                raise OSError("down")
            return root_status, ""
        return (200, "x") if page_status == 200 else (page_status, "")

    assert bv.check_source({"url": page, "quote": "x"}, fetch) == state
    assert calls == ([page] if root is None else [page, root])


def test_a_zone_id_stays_in_the_origin_root() -> None:
    """A zone id in the hostname is part of the origin, including the ``%25`` encoding."""
    def fetch(url: str):
        if url != "https://[fe80::1%25eth0]/":
            raise OSError(url)
        return 200, ""

    assert bv.host_answers("https://[fe80::1%25eth0]/a", fetch, {}) is True


def test_two_missing_pages_on_one_origin_probe_the_root_once(monkeypatch) -> None:
    """One root fetch per origin per run; a different port is a different origin."""
    monkeypatch.setattr(bv.socket, "getaddrinfo", _example_com_is_public)
    calls: list[str] = []

    def fetch(url: str):
        calls.append(url)
        return (200, "") if url == "https://example.com:8443/" else (404, "")

    idea = Idea(id="B1", title="One", sources=[
        {"url": "https://example.com/a", "quote": "one"},
        {"url": "https://example.com/b", "quote": "two"},
        {"url": "https://example.com:8443/c", "quote": "three"},
    ])
    bv.verify_session(BrainstormSession(slug="s"), [idea], fetch=fetch)
    assert [s["verification"] for s in idea.sources] == ["blocked", "blocked", "not-found"]
    assert calls.count("https://example.com/") == 1
    assert calls.count("https://example.com:8443/") == 1


_FOLDED = {"'": "\u2018\u2019\u201a\u2032", '"': "\u201c\u201d\u201e\u2033",
           "-": "\u2010\u2011\u2012\u2013\u2014\u2015\u2212", " ": "\u00a0\u202f\u2009"}
_SAME_WORDS = [
    ("restudying<sup>[43]</sup> while helping", "restudying while helping"),
    ("effect.<sup>[44][45][46]</sup> It", "effect. It"),
    ("restudying [43] while", "restudying while"),
    ("word[a] next", "word next"),
    ("word[A] next", "word next"),
    ("word[note 1] next", "word next"),
    ("word[citation needed] next", "word next"),
    ("word[Citation Needed] next", "word next"),
    ("children\u2019s education records", "children's education records"),
    ("\u201ctesting effect\u201d", '"testing effect"'),
    ("1990\u20132000 \u2014 a decade", "1990-2000 - a decade"),
    ("26&nbsp;%", "26 %"),
    ("retriev&shy;al practice", "retrieval practice"),
    *[(f"a{ch}b", f"a{ascii_ch}b") for ascii_ch, chars in _FOLDED.items() for ch in chars],
    *[(f"retriev{ch}al practice", "retrieval practice") for ch in "\u00ad\u200b\u200c\u200d\u2060\ufeff"],
]


def _example_com_is_public(host, port, **kw):
    """``socket.getaddrinfo`` offline: public addresses for example.com and one IPv6 literal, private otherwise."""
    public = {"example.com": "93.184.216.34", _IPV6: _IPV6}
    return [(None, None, None, None, (public.get(host, "10.0.0.1"), 443))]


@pytest.mark.parametrize(("variant", "plain"), _SAME_WORDS)
def test_check_source_matches_page_text_variants_both_ways(monkeypatch, variant: str, plain: str) -> None:
    monkeypatch.setattr(bv.socket, "getaddrinfo", _example_com_is_public)
    for page, quote in ((variant, plain), (plain, variant)):
        source = {"url": "https://example.com/p", "quote": quote}
        assert bv.check_source(source, lambda url, page=page: (200, page)) == "matched"


@pytest.mark.parametrize(("page", "quote"), [("children\u2019s records", "children's files"),
                                             ("restudying[43] while", "[43]")])
def test_check_source_still_needs_the_same_words(monkeypatch, page: str, quote: str) -> None:
    monkeypatch.setattr(bv.socket, "getaddrinfo", _example_com_is_public)
    source = {"url": "https://example.com/p", "quote": quote}
    assert bv.check_source(source, lambda url: (200, page)) == "not-found"


def test_repo_quotes_do_not_get_the_page_folds() -> None:
    assert not bv.quote_in_file("children\u2019s records", "children's records", None)
    assert not bv.quote_in_file("restudying[43] while", "restudying while", None)


def test_verify_asks_before_fetching_and_records_states(repo: Path, monkeypatch) -> None:
    _start(repo)
    _cli(repo, "add-idea", "--title", "One")
    _cli(repo, "add-evidence", "B1", "--url", "https://example.com/ok", "--quote", "exact words")
    _cli(repo, "add-evidence", "B1", "--url", "https://example.com/miss", "--quote", "exact words")
    calls: list[str] = []

    def fetch(url):
        calls.append(url)
        if len(calls) == 1:   # another process adds an idea mid-fetch: verify must not hold the lock, nor drop it
            add = subprocess.run([sys.executable, "-m", "specy_road.cli", "brainstorm", "add-idea", "--title", "Two",
                                  "--repo-root", str(repo)], cwd=REPO, env=script_subprocess_env(),
                                 capture_output=True, text=True, timeout=60)
            assert add.returncode == 0, add.stderr
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
    assert states == {"https://example.com/ok": "matched", "https://example.com/miss": "not-found"}
    assert [i.title for i in _session(repo).ideas] == ["One", "Two"]
    assert "B1 matched" in out and "B1 not-found" in out
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
    calls: list[str] = []
    pages = {"https://example.com/a": (302, "http://127.0.0.1/secret", b""),
             "https://example.com/b": (302, "/c", b""),
             "https://example.com/c": (200, None, b"<p>exact words</p>")}

    def fetch_once(url):
        calls.append(url)
        return pages[url]

    monkeypatch.setattr(bv, "_fetch_once", fetch_once)
    monkeypatch.setattr(bv, "_is_off_host", lambda host: host != "example.com")
    with pytest.raises(ValueError, match="refusing http://127.0.0.1/secret"):
        bv.default_fetch("https://example.com/a")
    assert calls == ["https://example.com/a"]
    assert bv.default_fetch("https://example.com/b") == (200, "<p>exact words</p>")
    assert bv.check_source({"url": "https://example.com/a", "quote": "secret"}, bv.default_fetch) == "blocked"


def test_a_root_that_redirects_to_a_private_address_is_blocked(monkeypatch) -> None:
    """A 404 whose root redirects to a private address is blocked, and that address is never connected."""
    payloads = [
        b"HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\nConnection: close\r\n\r\n",
        b"HTTP/1.1 302 Found\r\nLocation: https://10.0.0.1/secret\r\nContent-Length: 0\r\nConnection: close\r\n\r\n",
    ]
    opened: list[tuple] = []

    class Sock:
        def __init__(self) -> None:
            self._body = payloads[len(opened) - 1]

        def sendall(self, _data: bytes) -> None:
            pass

        def makefile(self, _mode: str = "rb", _buffering: int = -1):
            return io.BytesIO(self._body)

        def close(self) -> None:
            pass

    def connect(addr, _timeout):
        opened.append(addr)
        return object()

    def wrap(_self, _sock, server_hostname=None, **_kwargs):
        return Sock()

    monkeypatch.setattr(bv.socket, "getaddrinfo", _example_com_is_public)
    monkeypatch.setattr(bv.socket, "create_connection", connect)
    monkeypatch.setattr(bv.ssl.SSLContext, "wrap_socket", wrap)
    assert bv.check_source({"url": "https://example.com/missing", "quote": "x"}, bv.default_fetch) == "blocked"
    assert opened == [("93.184.216.34", 443), ("93.184.216.34", 443)]


def test_the_connection_is_pinned_to_the_checked_address(monkeypatch) -> None:
    """The name is resolved once; the socket goes to that address with the hostname kept for TLS."""
    monkeypatch.setattr(bv.socket, "getaddrinfo",
                        lambda host, port, **kw: [(None, None, None, None, ("93.184.216.34", 443))])
    assert bv._public_address("example.com") == "93.184.216.34"
    monkeypatch.setattr(bv.socket, "getaddrinfo",
                        lambda host, port, **kw: [(None, None, None, None, ("93.184.216.34", 443)),
                                                  (None, None, None, None, ("127.0.0.1", 443))])
    assert bv._public_address("rebinder.example") is None       # one private answer poisons the name
    opened: list[tuple] = []

    class Sock:
        def close(self): pass

    monkeypatch.setattr(bv.socket, "getaddrinfo",
                        lambda host, port, **kw: [(None, None, None, None, ("93.184.216.34", 443))])
    monkeypatch.setattr(bv.socket, "create_connection", lambda addr, timeout: opened.append(addr) or Sock())

    class Ctx:
        def wrap_socket(self, sock, server_hostname=None):
            opened.append(("sni", server_hostname))
            return sock

    conn = bv._PinnedHTTPS("example.com", "93.184.216.34", 443)
    conn._context = Ctx()
    conn.connect()
    assert opened == [("93.184.216.34", 443), ("sni", "example.com")]