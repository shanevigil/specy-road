"""Shared helpers for the M13.7 ignore-note tests (``test_m13_7_notices``, ``test_m13_7_gitignore_symlinks``)."""

from __future__ import annotations

import subprocess
from pathlib import Path


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t", *args],
                          check=True, capture_output=True, text=True).stdout


def repo_with_prompts(tmp_path: Path, untracked: int = 1) -> Path:
    git(tmp_path, "init", "-q")
    (tmp_path / "work").mkdir()
    (tmp_path / "work" / "prompt-a.md").write_text("a\n", encoding="utf-8")
    git(tmp_path, "add", "work/prompt-a.md")
    git(tmp_path, "commit", "-qm", "tracked prompt")
    for i in range(untracked):
        (tmp_path / "work" / f"prompt-u{i:02d}.md").write_text("u\n", encoding="utf-8")
    return tmp_path


def write(repo: Path, rel: str, data: str | bytes = "x\n") -> None:
    (repo / rel).parent.mkdir(parents=True, exist_ok=True)
    (repo / rel).write_bytes(data if isinstance(data, bytes) else data.encode())


def shown(repo: Path) -> set[str]:
    out = git(repo, "status", "--porcelain=v1", "-z", "--untracked-files=all")
    return {e[3:] for e in out.split("\0") if e.startswith("?? ")}


def listed(out: str, note: str) -> set[str]:
    return {ln[2:].rsplit(" (", 1)[0] for ln in out.splitlines() if ln.endswith(note)}
