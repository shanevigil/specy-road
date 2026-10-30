"""Refuse pytest when ``tests/fixtures`` holds ignored git debris or changes mid-run."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

FIXTURES_PATH = "tests/fixtures"
CLEAN_CMD = f"git clean -fdX {FIXTURES_PATH}"

_CONFIG_START_ATTR = "_fixture_guard_start_lines"


def fixtures_git_lines(repo_root: Path) -> list[str]:
    """Non-empty lines from ``git status --porcelain --ignored -- tests/fixtures``."""
    proc = subprocess.run(
        ["git", "status", "--porcelain", "--ignored", "--", FIXTURES_PATH],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return []
    return [ln for ln in proc.stdout.splitlines() if ln.strip()]


def path_from_porcelain(line: str) -> str:
    """Path of a porcelain v1 line, as git prints it (quoted when git quotes it).

    Only a rename or copy record (``R``/``C`` in the two status columns) carries
    ``old -> new``; an ordinary filename may itself contain `` -> ``.
    """
    code, body = line[:2], line[3:]
    if " -> " in body and ("R" in code or "C" in code):
        body = body.split(" -> ", 1)[1]
    return body.strip()


def ignored_fixture_paths(lines: list[str]) -> list[str]:
    return [path_from_porcelain(ln) for ln in lines if ln.startswith("!!")]


def _line_map(lines: list[str]) -> dict[str, str]:
    return {path_from_porcelain(ln): ln for ln in lines}


def paths_with_changed_status(start: list[str], end: list[str]) -> list[str]:
    before, after = _line_map(start), _line_map(end)
    keys = sorted(set(before) | set(after))
    return [p for p in keys if before.get(p) != after.get(p)]


def record_session_start(session, repo_root: Path) -> None:
    setattr(session.config, _CONFIG_START_ATTR, fixtures_git_lines(repo_root))


def session_start_lines(session) -> list[str] | None:
    return getattr(session.config, _CONFIG_START_ATTR, None)


def exit_if_ignored_fixtures_present(repo_root: Path) -> None:
    """A1: abort collection when ignored paths sit under ``tests/fixtures``."""
    import pytest

    lines = fixtures_git_lines(repo_root)
    ignored = ignored_fixture_paths(lines)
    if not ignored:
        return
    parts = [
        "pytest refused to start: ignored file(s) under tests/fixtures:",
        *(f"  {p}" for p in ignored),
        f"Run: {CLEAN_CMD}",
    ]
    pytest.exit("\n".join(parts), returncode=1)


def fail_if_fixtures_status_changed(session, repo_root: Path) -> None:
    """A2: fail the session when fixture-tree git status changed since start."""
    start = session_start_lines(session)
    if start is None:
        return
    end = fixtures_git_lines(repo_root)
    if end == start:
        return
    changed = paths_with_changed_status(start, end)
    parts = [
        "pytest failed: tests/fixtures git status changed during the run:",
        *(f"  {p}" for p in changed),
        f"Run: {CLEAN_CMD}",
    ]
    sys.stderr.write("\n".join(parts) + "\n")
    session.exitstatus = 1
