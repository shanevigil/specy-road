"""M21.28: finish refuses an invalid configuration before it writes, and a later failure leaves the tree as it was.

Each row runs finish-this-task through its public entry in a sandbox and
compares worktree bytes, index blobs and HEAD before and after.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from specy_road.review_gate_agreement import GATE_FIX
from tests.helpers import REPO
from tests.review_repo_helpers import commit_file, git
from tests.test_finish_merge_mode import merge_mode_finish_repo

ORCHESTRATION = (REPO / "specy_road" / "templates" / "project" / "roadmap" / "orchestration.yaml").read_text()
AGAIN = "nothing was committed; fix it and run finish-this-task again"

#: Runs finish with the failure named by ``INJECT`` (validate, digest or registry) injected.
_INJECTED = """
import os, subprocess, sys
from unittest import mock
import specy_road.bundled_scripts.finish_task as ft

where = os.environ["INJECT"]
real = subprocess.check_call

def check_call(argv, **kw):
    if where in ("validate", "digest") and argv[1:4] == ["-m", "specy_road.cli", where]:
        if where == "digest":
            assert "Complete" in (ft.ROOT / "roadmap.md").read_text()   # export rewrote it first
        raise subprocess.CalledProcessError(3, argv)   # what check_call raises when the command exits 3
    return real(argv, **kw)

def write_registry(path, doc):
    raise OSError(28, "No space left on device", str(path))

with mock.patch.object(subprocess, "check_call", check_call), \\
        mock.patch.object(ft, "write_registry", write_registry if where == "registry" else ft.write_registry):
    ft.main(sys.argv[1:])
"""


def _repo(tmp_path: Path, monkeypatch) -> Path:
    repo, _bare = merge_mode_finish_repo(tmp_path, monkeypatch)
    commit_file(repo, "work/brief-M1.1.md", "# brief M1.1\n", "brief")
    return repo


def _state(repo: Path) -> tuple[dict[str, bytes], str, str]:
    """Worktree bytes of every tracked or untracked path, plus ignored ones under ``work/``; the index; HEAD.

    Other ignored paths are left out: the commands finish runs refresh the
    derived ``.specyrd/cache/``, which is no bookkeeping. ``work/reviews/`` is
    ignored and is where cleanup keeps a copy of an untracked summary.
    """
    names = git(repo, "ls-files", "-co", "--exclude-standard").splitlines()
    names += git(repo, "ls-files", "-oi", "--exclude-standard", "--", "work").splitlines()
    files = {n: (repo / n).read_bytes() if (repo / n).exists() else None for n in sorted(set(names))}
    return files, git(repo, "ls-files", "-s"), git(repo, "rev-parse", "HEAD")


def _run(repo: Path, argv: list[str], **env_over: str) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "PYTHONPATH": str(REPO), **env_over}
    return subprocess.run(
        [sys.executable, *argv, "--repo-root", str(repo)], cwd=repo, env=env,
        capture_output=True, text=True, check=False,
    )


def test_rc4_configuration_is_refused_before_any_write(tmp_path: Path, monkeypatch) -> None:
    """A1: reviewers required, gate off -> exit 1 naming the fix, nothing changed."""
    repo = _repo(tmp_path, monkeypatch)
    commit_file(repo, "roadmap/orchestration.yaml", ORCHESTRATION, "orchestration")
    before = _state(repo)
    result = _run(repo, ["-m", "specy_road.cli", "finish-this-task"])
    assert result.returncode == 1, result.stdout + result.stderr
    assert GATE_FIX in result.stderr
    assert "finish-this-task: nothing was changed" in result.stderr
    assert "Traceback" not in result.stderr
    assert "status -> Complete" not in result.stdout
    assert _state(repo) == before
    reg = yaml.safe_load((repo / "roadmap" / "registry.yaml").read_text())
    assert any(e.get("codename") == "thing" for e in reg["entries"])


COMMIT_REFUSED = "`git commit -m chore(rm-thing): complete, deregister` exited 1"
SUMMARY = "work/implementation-summary-M1.1.md"


@pytest.mark.parametrize(
    ("inject", "named", "setup"),
    [
        ("validate", "`specy-road validate --repo-root", None),
        ("digest", "`specy-road digest --repo-root", None),
        # roadmap.md is a committed link to payload.md: export writes the target, then digest is refused.
        ("digest", "`specy-road digest --repo-root", "link"),
        ("registry", "registry.yaml", None),
        # A tracked summary is moved over an existing work/done/ copy with other bytes.
        ("commit", COMMIT_REFUSED, "tracked"),
        # An untracked summary is copied into work/reviews/M1.1/, absent before.
        ("commit", COMMIT_REFUSED, "untracked"),
    ],
)
def test_failure_before_the_commit_restores_the_tree(
    tmp_path: Path, monkeypatch, inject: str, named: str, setup: str | None,
) -> None:
    """A3/A4: each refusal restores worktree bytes, index and HEAD, and reports cleanly."""
    repo = _repo(tmp_path, monkeypatch)
    if setup == "link":
        (repo / "payload.md").write_text("# roadmap index, before finish\n")
        (repo / "roadmap.md").symlink_to("payload.md")
        git(repo, "add", "payload.md", "roadmap.md")
        git(repo, "commit", "-qm", "roadmap.md links to payload.md")
    elif setup == "tracked":
        commit_file(repo, SUMMARY, "# summary M1.1\n", "summary")
        (repo / "work" / "done").mkdir()
        (repo / "work" / "done" / "implementation-summary-M1.1.md").write_text("# an older archive\n")
    elif setup == "untracked":
        (repo / SUMMARY).write_text("# summary M1.1, never committed\n")
    if inject == "commit":
        hook = Path(git(repo, "rev-parse", "--git-path", "hooks/pre-commit"))
        hook = hook if hook.is_absolute() else repo / hook
        hook.parent.mkdir(parents=True, exist_ok=True)
        hook.write_text("#!/bin/sh\necho 'pre-commit refused' >&2\nexit 1\n")
        hook.chmod(0o755)
        # Distinct staged and unstaged bytes on a path cleanup removes.
        (repo / "work" / "brief-M1.1.md").write_text("# brief M1.1\n\nstaged\n")
        git(repo, "add", "work/brief-M1.1.md")
        (repo / "work" / "brief-M1.1.md").write_text("# brief M1.1\n\nunstaged\n")
        argv = ["-m", "specy_road.cli", "finish-this-task"]
    else:
        argv = ["-c", _INJECTED]
    before = _state(repo)
    result = _run(repo, argv, INJECT=inject)
    out = result.stdout + result.stderr
    assert result.returncode == 1, out
    assert named in result.stderr, out
    assert AGAIN in result.stderr, out
    assert "could not restore" not in result.stderr, out
    assert "Traceback" not in result.stderr, out
    assert "[ok] bookkeeping committed" not in out
    if setup in ("tracked", "untracked"):   # cleanup wrote the destination before the commit was refused
        assert {"tracked": "[ok] archived", "untracked": "kept a copy at"}[setup] in out, out
    if setup == "link":   # the injected digest saw export's Complete through the link, so payload.md was written
        assert (repo / "roadmap.md").is_symlink()
    assert _state(repo) == before
