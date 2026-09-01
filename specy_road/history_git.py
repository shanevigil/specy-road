"""Git plumbing for the roadmap history walk: one log pass, one blob reader.

Two primitives, both chosen to keep the walk's cost independent of roadmap size.

:func:`log_raw` is a **single** ``git log --raw`` pass. ``--raw --no-abbrev``
prints the new blob SHA of every changed file alongside each commit, so the walk
learns what to read without a second query per commit.

:class:`BlobReader` wraps **one** long-lived ``git cat-file --batch`` process
that serves every blob the walk needs. The alternative — ``git show`` per blob,
which is what :func:`roadmap_load_at_ref.load_roadmap_nodes_at_ref` does for its
single-ref use — costs ``1 + chunks`` subprocesses *per commit*. That is the
same trap :mod:`specy_road.node_activity` documents at ~31s against ~0.17s on a
400-node roadmap, and over thousands of commits it is hopeless.

Everything here is best-effort. No git binary, a shallow clone, or a directory
that is not a worktree yields less history, never an exception.
"""

from __future__ import annotations

import subprocess
from collections import OrderedDict
from pathlib import Path
from typing import Any

# Belt-and-braces bound on a pathological history, matching node_activity.
MAX_HISTORY_COMMITS = 50_000

# Parsed-chunk memo. The working set is the number of live chunks, so a cap
# well above that keeps the hit rate near 100% while bounding memory on a
# history with thousands of distinct chunk revisions.
_PARSED_CACHE_MAX = 1024

# \x01 marks a commit header line; \x1f separates its fields. Neither can occur
# in git's raw diff output or in a path, so parsing needs no lookahead.
COMMIT_MARK = "\x01"
FIELD_SEP = "\x1f"
_LOG_FORMAT = f"{COMMIT_MARK}%H{FIELD_SEP}%aI{FIELD_SEP}%an"

_NULL_SHA = "0" * 40


def run_git(root: Path, args: list[str]) -> str | None:
    """Stdout, or ``None`` on any failure. Never raises."""
    try:
        r = subprocess.run(
            ["git", *args], cwd=root, capture_output=True, text=True, check=False
        )
    except (OSError, ValueError):
        return None
    return r.stdout if r.returncode == 0 else None


def head_sha(root: Path) -> str | None:
    return (run_git(root, ["rev-parse", "HEAD"]) or "").strip() or None


def is_ancestor(root: Path, older: str, newer: str) -> bool:
    """Whether ``older`` is still reachable from ``newer``.

    False after a rebase, amend or force-push — which is exactly when an
    incrementally-built index must be thrown away rather than appended to.
    """
    try:
        r = subprocess.run(
            ["git", "merge-base", "--is-ancestor", older, newer],
            cwd=root,
            capture_output=True,
            check=False,
        )
    except (OSError, ValueError):
        return False
    return r.returncode == 0


def log_raw(root: Path, scopes: list[str], since: str | None = None) -> str | None:
    """One ``git log --raw`` pass over ``scopes``, oldest commit first.

    ``--first-parent`` walks the mainline only, so each step is a state the
    integration branch actually passed through and a merged feature branch
    arrives as a single step. Diffing a ``--no-merges`` walk instead would
    interleave parallel branches and manufacture flip-flop events (a status
    going A→B→A→B) that never happened on the branch anyone reads.

    This deliberately differs from :func:`node_activity.last_commit_dates`,
    which excludes merges: that question is "when was real work done on this
    node?", where a merge carrying someone else's edit is not work. This
    question is "what did the roadmap look like at each step?", where a merge
    *is* a transition.
    """
    base = [
        "log",
        "--reverse",
        "--first-parent",
        f"--max-count={MAX_HISTORY_COMMITS}",
        f"--format={_LOG_FORMAT}",
        "--raw",
        "--no-abbrev",
        "--no-renames",
    ]
    rev = [f"{since}..HEAD"] if since else []
    tail = ["--", *scopes]
    # Explicit on modern git; dropped on <2.31, where --first-parent already
    # implies a first-parent diff for merges.
    out = run_git(root, [*base, "--diff-merges=first-parent", *rev, *tail])
    if out is None:
        out = run_git(root, [*base, *rev, *tail])
    return out


def ls_tree_blobs(root: Path, ref: str, scope: str) -> dict[str, str]:
    """``{path: blob sha}`` under ``scope`` at ``ref``.

    Seeds an incremental walk with the file state at the last indexed commit,
    so the cache never has to store a derived blob map that could drift from
    what git actually holds.
    """
    out = run_git(root, ["ls-tree", "-r", ref, "--", scope])
    if not out:
        return {}
    blobs: dict[str, str] = {}
    for line in out.splitlines():
        meta, _, path = line.partition("\t")
        parts = meta.split()
        if len(parts) >= 3 and parts[1] == "blob" and path:
            blobs[path] = parts[2]
    return blobs


class BlobReader:
    """One ``git cat-file --batch`` process, reused for every blob.

    Use as a context manager. ``json`` memoises parsed documents by blob SHA:
    a chunk that is unchanged across a thousand commits is parsed once.
    """

    def __init__(self, root: Path) -> None:
        self._proc: subprocess.Popen[bytes] | None = None
        self._parsed: OrderedDict[str, Any] = OrderedDict()
        try:
            self._proc = subprocess.Popen(
                ["git", "cat-file", "--batch"],
                cwd=root,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            )
        except (OSError, ValueError):
            self._proc = None

    def __enter__(self) -> BlobReader:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        proc = self._proc
        self._proc = None
        if proc is None:
            return
        try:
            if proc.stdin is not None:
                proc.stdin.close()
            proc.wait(timeout=5)
        except (OSError, ValueError, subprocess.TimeoutExpired):
            proc.kill()

    def read(self, sha: str) -> bytes | None:
        """Raw blob bytes, or ``None`` if it is missing or the process is gone."""
        proc = self._proc
        if proc is None or proc.stdin is None or proc.stdout is None:
            return None
        if not sha or sha == _NULL_SHA:
            return None
        try:
            proc.stdin.write(f"{sha}\n".encode())
            proc.stdin.flush()
            header = proc.stdout.readline()
        except (OSError, ValueError, BrokenPipeError):
            self.close()
            return None
        parts = header.split()
        if len(parts) < 3 or parts[1] != b"blob":
            # "<sha> missing" — a one-line response, nothing further to consume.
            return None
        try:
            size = int(parts[2])
            data = proc.stdout.read(size)
            proc.stdout.read(1)  # the newline git appends after the payload
        except (OSError, ValueError):
            self.close()
            return None
        return data

    def json(self, sha: str) -> Any | None:
        """Parsed JSON for a blob, memoised by SHA. ``None`` if unreadable."""
        import json

        if sha in self._parsed:
            self._parsed.move_to_end(sha)
            return self._parsed[sha]
        data = self.read(sha)
        doc: Any | None = None
        if data is not None:
            try:
                doc = json.loads(data.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                doc = None
        self._parsed[sha] = doc
        if len(self._parsed) > _PARSED_CACHE_MAX:
            self._parsed.popitem(last=False)
        return doc
