"""Brainstorm evidence from the repository itself, searches that found nothing, and quotes on ``add-idea``.

A repo source cites ``file[:line]`` at the commit it was recorded on, and
``verify`` checks its quote against that commit locally, without asking or
fetching. A search with no hit is recorded as such and never verified. An
idea research produced can carry its quote from the start.
"""

from __future__ import annotations

import contextlib
import io
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.helpers import DOGFOOD

from specy_road.bundled_scripts import brainstorm_cli
from specy_road.bundled_scripts import brainstorm_verify as bv
from specy_road.bundled_scripts.brainstorm_session import BrainstormError, read_session, session_path

SLUG = "how-do-we-expand-payments"
PAY = "def charge(amount):\n    # Links expire after 24 hours.\n    return link(amount)\n\n\ndef refund():\n    pass\n"


def _git(repo: Path, *args: str) -> str:
    r = subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.com", "-C", str(repo), *args],
                       check=True, capture_output=True, text=True)
    return r.stdout.strip()


def _commit(repo: Path, rel: str, text: str) -> str:
    (repo / rel).parent.mkdir(parents=True, exist_ok=True)
    (repo / rel).write_text(text, encoding="utf-8")
    _git(repo, "add", rel)
    _git(repo, "commit", "-qm", f"change {rel}")
    return _git(repo, "rev-parse", "HEAD")


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    dest = tmp_path / "repo"
    shutil.copytree(DOGFOOD, dest)
    _git(dest, "init", "-q")
    return dest


def _cli(repo: Path, *args: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            brainstorm_cli.main([*args, "--repo-root", str(repo)])
            code = 0
        except SystemExit as e:
            code = int(e.code or 0)
    return code, out.getvalue(), err.getvalue()


def _started(repo: Path) -> None:
    _cli(repo, "start", "--topic", "How do we expand payments?", "--under", "M1")
    _cli(repo, "add-idea", "--title", "Pay by link")


def _sources(repo: Path) -> list[dict]:
    return read_session(repo, SLUG).by_id("B1").sources


# --- A1: repo sources, verified locally against their commit -----------------

def test_repo_source_records_the_commit_and_verify_checks_it_locally(repo: Path, monkeypatch) -> None:
    first = _commit(repo, "src/pay.py", PAY)
    _started(repo)
    code, out, err = _cli(repo, "add-evidence", "B1", "--source-type", "repo", "--path", "src/pay.py:2",
                          "--quote", "# Links expire after 24 hours.", "--supports", "links are short-lived")
    assert code == 0, err
    assert "source 1" in out
    _cli(repo, "add-evidence", "B1", "--path", "src/pay.py:6", "--quote", "Links expire after 24 hours.")
    src = _sources(repo)[0]
    assert {k: src[k] for k in ("source_type", "path", "commit", "verification")} == {
        "source_type": "repo", "path": "src/pay.py:2", "commit": first, "verification": "unverified"}
    assert src["url"] == f"repo:src/pay.py:2@{first[:12]}"
    assert read_session(repo, SLUG).by_id("B1").evidence == []   # the URL list stays pages only
    _commit(repo, "src/pay.py", "def charge(amount):\n    return link(amount)\n")   # the code moves on

    def no_fetch(url):
        raise AssertionError(f"a repo source must not be fetched: {url}")

    monkeypatch.setattr(bv, "default_fetch", no_fetch)
    monkeypatch.setattr("sys.stdin", io.StringIO(""))   # not a terminal, no --yes: nothing to ask for
    code, out, _ = _cli(repo, "verify")
    assert code == 0 and "would fetch" not in out
    # Checked against the recorded commit, not the moved-on HEAD; the second cites the wrong line.
    assert [s["verification"] for s in _sources(repo)] == ["matched", "not-found"]


def test_a_nested_project_cites_code_outside_it_relative_to_the_git_root(tmp_path: Path, monkeypatch) -> None:
    top = tmp_path / "top"
    project = top / "sr"
    shutil.copytree(DOGFOOD, project)
    _git(top, "init", "-q")
    first = _commit(top, "src/pay.py", PAY)
    (project / "src").mkdir(exist_ok=True)   # a same-named file under the project must not be the one read
    (project / "src" / "pay.py").write_text("nothing to see\n", encoding="utf-8")
    _started(project)
    code, _, err = _cli(project, "add-evidence", "B1", "--source-type", "repo", "--path", "src/pay.py:2",
                        "--quote", "# Links expire after 24 hours.")
    assert code == 0, err
    src = _sources(project)[0]
    assert (src["path"], src["commit"]) == ("src/pay.py:2", first)
    _commit(top, "src/pay.py", "def charge(amount):\n    return link(amount)\n")   # HEAD moves on
    monkeypatch.setattr("sys.stdin", io.StringIO(""))
    code, out, _ = _cli(project, "verify")
    assert code == 0 and "B1 matched" in out
    assert [s["verification"] for s in _sources(project)] == ["matched"]


def test_verify_checks_repo_sources_even_when_the_fetch_is_declined(repo: Path, monkeypatch) -> None:
    _commit(repo, "src/pay.py", PAY)
    _started(repo)
    _cli(repo, "add-evidence", "B1", "--path", "src/pay.py", "--quote", "return link(amount)")
    _cli(repo, "add-evidence", "B1", "--url", "https://example.com/a", "--quote", "exact words")
    monkeypatch.setattr("sys.stdin", io.StringIO(""))
    code, out, _ = _cli(repo, "verify")
    assert code == 1 and "would fetch 1 URL(s)" in out and "https://example.com/a" in out
    assert [s["verification"] for s in _sources(repo)] == ["matched", "unverified"]


def test_add_evidence_refuses_a_path_the_commit_does_not_hold(repo: Path) -> None:
    _commit(repo, "src/pay.py", PAY)
    _started(repo)
    (repo / "src" / "new.py").write_text("x = 1\n", encoding="utf-8")
    code, _, err = _cli(repo, "add-evidence", "B1", "--path", "src/new.py:1", "--quote", "x = 1")
    assert code == 1 and "not in the HEAD commit" in err
    code, _, err = _cli(repo, "add-evidence", "B1", "--source-type", "repo", "--url", "https://x", "--quote", "q")
    assert code == 1 and "--source-type repo needs --path" in err
    code, _, err = _cli(repo, "add-evidence", "B1", "--source-type", "paper", "--path", "src/pay.py", "--quote", "q")
    assert code == 1 and "--path cites a file in this repository" in err
    code, _, err = _cli(repo, "add-evidence", "B1", "--path", "src/pay.py")
    assert code == 1 and "--quote is required" in err
    assert _sources(repo) == []


def test_a_directory_is_not_a_file_to_cite(repo: Path, monkeypatch) -> None:
    _commit(repo, "src/pay.py", PAY)
    _started(repo)
    code, _, err = _cli(repo, "add-evidence", "B1", "--path", "src:3", "--quote", "pay.py")
    assert code == 1 and "a tree in the HEAD commit, not a file" in err
    assert _sources(repo) == []
    # A directory citation already in the session (hand-edited) never matches git's tree listing.
    _cli(repo, "add-evidence", "B1", "--path", "src/pay.py:2", "--quote", "pay.py")
    path = session_path(repo, SLUG)
    path.write_text(path.read_text(encoding="utf-8").replace("path: src/pay.py:2", "path: src:3"), encoding="utf-8")
    assert _sources(repo)[0]["path"] == "src:3"
    monkeypatch.setattr("sys.stdin", io.StringIO(""))
    code, out, _ = _cli(repo, "verify")
    assert code == 0 and [s["verification"] for s in _sources(repo)] == ["not-found"]


def test_a_committed_file_that_does_not_read_is_blocked_not_not_found(repo: Path, monkeypatch) -> None:
    (repo / "src").mkdir()
    (repo / "src" / "latin1.py").write_bytes(b"# caf\xe9\nvalue = 1\n")
    _git(repo, "add", "src/latin1.py")
    _git(repo, "commit", "-qm", "latin-1 file")
    _started(repo)
    code, _, err = _cli(repo, "add-evidence", "B1", "--path", "src/latin1.py:2", "--quote", "value = 1")
    assert code == 0, err
    monkeypatch.setattr("sys.stdin", io.StringIO(""))
    code, out, _ = _cli(repo, "verify")
    assert code == 0 and "B1 blocked" in out
    assert [s["verification"] for s in _sources(repo)] == ["blocked"]


def test_repo_source_states_and_quote_spans() -> None:
    assert bv.split_path("src/a.py:12") == ("src/a.py", 12)
    assert bv.split_path("src/a.py") == ("src/a.py", None)
    assert bv.split_path("C:x") == ("C:x", None)
    text = "a = 1\n\n  def f(x):\n      return   x\n"
    assert bv.quote_in_file(text, "a = 1 def f(x):", 3)   # across a blank line, whitespace collapsed
    assert bv.quote_in_file(text, "def f(x): return x", 4)
    assert not bv.quote_in_file(text, "def f(x): return x", 1)   # the span does not cover line 1
    assert bv.quote_in_file(text, "return x", None)
    assert not bv.quote_in_file(text, "", None)
    assert not bv.quote_in_file(text, "return y", None)
    src = {"source_type": "repo", "path": "a.py:1", "commit": "0" * 40, "quote": "a"}
    assert bv.is_local(src) and bv.check_source(src, lambda url: (200, "a")) == "blocked"   # no root


def test_a_commit_that_is_gone_is_blocked_and_a_missing_file_not_found(repo: Path) -> None:
    sha = _commit(repo, "src/pay.py", PAY)
    gone = {"source_type": "repo", "path": "src/pay.py:2", "commit": "f" * 40, "quote": "Links"}
    assert bv.check_repo_source(gone, repo) == "blocked"
    missing = {"source_type": "repo", "path": "src/other.py", "commit": sha, "quote": "Links"}
    assert bv.check_repo_source(missing, repo) == "not-found"


def test_a_repo_source_without_its_commit_is_rejected_on_read(repo: Path) -> None:
    _commit(repo, "src/pay.py", PAY)
    _started(repo)
    _cli(repo, "add-evidence", "B1", "--path", "src/pay.py:2", "--quote", "Links expire")
    path = session_path(repo, SLUG)
    text = path.read_text(encoding="utf-8")
    path.write_text("\n".join(ln for ln in text.splitlines() if "commit:" not in ln) + "\n", encoding="utf-8")
    with pytest.raises(BrainstormError, match="needs a path and a commit"):
        read_session(repo, SLUG)


# --- A2: a search that found nothing -----------------------------------------

def test_no_result_records_a_disconfirming_search_and_verify_skips_it(repo: Path) -> None:
    _started(repo)
    code, out, err = _cli(repo, "add-evidence", "B1", "--query", "pay-by-link chargeback complaints", "--no-result",
                          "--stance", "against", "--tool", "claude WebSearch", "--supports", "fraud risk")
    assert code == 0, err
    assert "no-result:pay-by-link chargeback complaints (against)" in out
    src = _sources(repo)[0]
    assert src["query"] == "pay-by-link chargeback complaints" and src["result"] == "none"
    assert src["stance"] == "against" and "quote" not in src
    assert read_session(repo, SLUG).by_id("B1").evidence == []
    assert bv.pending(read_session(repo, SLUG).ideas) == []
    code, out, _ = _cli(repo, "verify")
    assert code == 0 and "nothing unverified" in out


@pytest.mark.parametrize(("args", "message"), [
    (("--query", "q", "--no-result", "--quote", "x"), "--no-result takes no --quote"),
    (("--query", "q", "--quote", "x"), "--query and --no-result go together"),
    (("--no-result", "--url", "https://x", "--quote", "x"), "--query and --no-result go together"),
    (("--query", " ", "--no-result"), "--query is empty"),
    (("--query", "q", "--no-result", "--url", "https://x"), "got --url, --query"),
    (("--quote", "x",), "add-evidence takes one of --url"),
])
def test_no_result_flag_combinations_are_refused(repo: Path, args: tuple[str, ...], message: str) -> None:
    _started(repo)
    code, _, err = _cli(repo, "add-evidence", "B1", *args)
    assert code == 1 and message in err
    assert _sources(repo) == []


# --- A3: a quote on add-idea --------------------------------------------------

def test_add_idea_quote_records_a_verifiable_source(repo: Path, monkeypatch) -> None:
    _cli(repo, "start", "--topic", "How do we expand payments?", "--under", "M1")
    code, _, err = _cli(repo, "add-idea", "--title", "Pay by link", "--evidence", "https://example.com/a",
                        "--quote", "exact words", "--evidence", "https://example.com/b")
    assert code == 0, err
    idea = read_session(repo, SLUG).by_id("B1")
    assert idea.evidence == ["https://example.com/a", "https://example.com/b"]
    assert [(s["url"], s["quote"], s["verification"]) for s in idea.sources] == [
        ("https://example.com/a", "exact words", "unverified")]
    assert idea.sources[0]["retrieved_at"]
    monkeypatch.setattr(bv, "default_fetch", lambda url: (200, "<p>Exact  words</p>"))
    monkeypatch.setattr(bv.socket, "getaddrinfo",   # example.com resolves public, offline
                        lambda host, port, **kw: [(None, None, None, None, ("93.184.216.34", 443))])
    code, out, _ = _cli(repo, "verify", "--yes")
    assert code == 0 and "B1 matched" in out


def test_add_idea_quote_checks(repo: Path) -> None:
    _cli(repo, "start", "--topic", "How do we expand payments?", "--under", "M1")
    code, _, err = _cli(repo, "add-idea", "--title", "T", "--quote", "orphan")
    assert code == 1 and "1 --quote for 0 --evidence" in err
    code, _, err = _cli(repo, "add-idea", "--title", "T", "--evidence", "https://x", "--quote", "x" * 301)
    assert code == 1 and "300 characters" in err
    assert read_session(repo, SLUG).ideas == []


def test_add_idea_from_file_takes_quotes(repo: Path, tmp_path: Path) -> None:
    _cli(repo, "start", "--topic", "How do we expand payments?", "--under", "M1")
    batch = tmp_path / "ideas.yaml"
    batch.write_text("- title: A\n  evidence: [https://example.com/a]\n  quote: [a words]\n- title: B\n",
                     encoding="utf-8")
    code, _, err = _cli(repo, "add-idea", "--from-file", str(batch))
    assert code == 0, err
    session = read_session(repo, SLUG)
    assert session.by_id("B1").sources[0]["quote"] == "a words" and session.by_id("B2").sources == []
    code, _, err = _cli(repo, "add-idea", "--from-file", str(batch), "--quote", "x")
    assert code == 1 and "--quote" in err
