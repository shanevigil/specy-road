"""Digest bytes do not depend on whether the history cache is cold or warm.

A dependency removed on a side branch, then kept by a non-fast-forward merge
after main has moved, is one mainline step dated with the merge commit. The
same ``roadmap-context.md`` is rendered when the cache is absent, when it was
written on that side branch, and when it was written on main and appended
across the merge.
"""

from __future__ import annotations

import os
import shutil
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

from specy_road.digest import DEFAULT_OUTPUT, render_digest
from specy_road.history_cache import CACHE_VERSION, cache_path, load_cache, save_cache
from specy_road.history_events import DEP_REMOVED
from specy_road.history_index import clear_memo, history_index
from tests.helpers import DOGFOOD
from tests.test_digest import run_cli
from tests.test_history_walk import commit, edit_node, git

_BASELINE = "2026-01-01T12:00:00+00:00"
_SIDE = "2026-02-01T12:00:00+00:00"
_MAIN = "2026-03-01T12:00:00+00:00"
_MERGE = "2026-04-01T12:00:00+00:00"
_REMOVAL = (
    "- 2026-04-01 `M0.2` stopped depending on "
    "`M0.3 Define API contract outline in shared/`"
)
# Absent; written on the side branch before the merge; written on main and
# appended after it. The side-branch row is the one a cold walk used to miss.
_CACHE_STATES = ("absent", "side-branch", "main-before-merge")
_DATE_VARS = ("GIT_AUTHOR_DATE", "GIT_COMMITTER_DATE")


@contextmanager
def _dated(when: str) -> Iterator[None]:
    saved = {name: os.environ.get(name) for name in _DATE_VARS}
    os.environ["GIT_AUTHOR_DATE"] = when
    os.environ["GIT_COMMITTER_DATE"] = when
    try:
        yield
    finally:
        for name, value in saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def _commit(repo: Path, message: str, when: str) -> str:
    with _dated(when):
        return commit(repo, message)


def _repo(dest: Path) -> Path:
    shutil.copytree(DOGFOOD, dest)
    git(dest, "init", "-q", "-b", "main")
    _commit(dest, "baseline roadmap", _BASELINE)
    cache_path(dest).unlink(missing_ok=True)
    return dest


def _remove_dependency(repo: Path) -> None:
    git(repo, "checkout", "-q", "-b", "feature/rm-side")
    edit_node(repo, "M0.2", dependencies=[])
    _commit(repo, "remove the dependency", _SIDE)


def _main_commit(repo: Path) -> None:
    git(repo, "checkout", "-q", "main")
    edit_node(repo, "M2", status="In Progress")
    _commit(repo, "main takes another roadmap commit", _MAIN)


def _merge(repo: Path) -> None:
    with _dated(_MERGE):
        git(repo, "merge", "-q", "--no-ff", "feature/rm-side", "-m", "merge feature")


def _index(repo: Path) -> None:
    clear_memo()
    history_index(repo)


def _prepare(dest: Path, state: str) -> Path:
    """History through the merge, with the cache left in ``state``."""
    repo = _repo(dest)
    _remove_dependency(repo)
    if state == "side-branch":
        _index(repo)
    _main_commit(repo)
    if state == "main-before-merge":
        _index(repo)
    _merge(repo)
    if state == "absent":
        cache_path(repo).unlink(missing_ok=True)
    return repo


def _stamp_cache(repo: Path) -> None:
    """Mark a cached event so an append can be told from a rebuild."""
    doc = load_cache(repo)
    assert doc is not None and doc["events"]
    doc["events"][0]["marker"] = "stamp"
    assert save_cache(repo, doc)


def _assert_check_keeps_bytes(repo: Path, body: str) -> None:
    assert run_cli(["digest"], repo) == 0
    path = repo / DEFAULT_OUTPUT
    written = path.read_bytes()
    assert written.decode("utf-8") == body
    clear_memo()
    assert run_cli(["digest", "--check"], repo) == 0
    assert path.read_bytes() == written


def _cold(tmp: Path) -> str:
    repo = _prepare(tmp, "absent")
    clear_memo()
    return render_digest(repo)


@pytest.mark.parametrize("state", _CACHE_STATES)
def test_each_cache_state_matches_the_cold_digest(tmp_path: Path, state: str) -> None:
    expected = _cold(tmp_path / "cold")
    repo = _prepare(tmp_path / "case", state)
    if state != "absent":
        _stamp_cache(repo)
    clear_memo()

    text = render_digest(repo)

    assert text == expected
    stopped = [ln for ln in text.splitlines() if "stopped depending on" in ln]
    assert stopped == [_REMOVAL]
    _assert_check_keeps_bytes(repo, text)
    stored = load_cache(repo)["events"]
    if state == "side-branch":
        assert all("marker" not in event for event in stored)
    if state == "main-before-merge":
        assert stored[0]["marker"] == "stamp"


def test_an_older_cache_at_the_merge_without_the_removal_is_rebuilt(tmp_path: Path) -> None:
    """Version 1 is the cache this change retires; a matching head must not keep it."""
    repo = _prepare(tmp_path / "repo", "absent")
    clear_memo()
    expected = render_digest(repo)
    head = git(repo, "rev-parse", "HEAD")
    assert save_cache(
        repo,
        {
            "cache_version": 1,
            "head": head,
            "last_indexed_commit": head,
            "events": [],
        },
    )
    clear_memo()

    assert render_digest(repo) == expected
    stored = load_cache(repo)
    assert stored["cache_version"] == CACHE_VERSION
    assert any(event.get("kind") == DEP_REMOVED for event in stored["events"])


def test_a_second_checkout_without_a_cache_matches(tmp_path: Path) -> None:
    repo = _prepare(tmp_path / "repo", "absent")
    clear_memo()
    expected = render_digest(repo)
    checkout = tmp_path / "checkout"
    git(repo, "worktree", "add", "--detach", "-q", str(checkout), "HEAD")
    cache_path(checkout).unlink(missing_ok=True)
    clear_memo()

    assert render_digest(checkout) == expected
