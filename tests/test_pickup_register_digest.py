"""Pickup's register commit carries the regenerated digest; abort still recognises it as its own."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import yaml

from tests.helpers import REPO, script_subprocess_env


def _cli(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, "-m", "specy_road.cli", *args, "--repo-root", str(root)],
                          cwd=REPO, env=script_subprocess_env(), capture_output=True, text=True)


def _git(root: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True).stdout.strip()


def _app(tmp_path: Path) -> tuple[Path, Path]:
    remote, app = tmp_path / "remote.git", tmp_path / "app"
    _git(tmp_path, "init", "-q", "--bare", str(remote))
    subprocess.run(["git", "init", "-q", str(app)], check=True)
    r = subprocess.run([sys.executable, "-m", "specy_road.cli", "init", "project", str(app)],
                       cwd=REPO, env=script_subprocess_env(), capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert _cli(app, "export").returncode == 0 and _cli(app, "digest").returncode == 0
    _git(app, "config", "user.email", "t@example.com")
    _git(app, "config", "user.name", "T")
    _git(app, "checkout", "-q", "-b", "main")
    _git(app, "add", "-A")
    _git(app, "commit", "-q", "-m", "init")
    _git(app, "remote", "add", "origin", str(remote))
    _git(app, "push", "-q", "-u", "origin", "main")
    assert _cli(app, "digest", "--check").returncode == 0
    return remote, app


def test_pickup_commits_the_digest_with_the_claim(tmp_path: Path) -> None:
    remote, app = _app(tmp_path)

    r = _cli(app, "do-next-available-task")

    assert r.returncode == 0, r.stderr
    paths = set(_git(app, "show", "--name-only", "--format=", "main").splitlines())
    assert "roadmap-context.md" in paths
    assert paths <= {"roadmap/registry.yaml", "roadmap-context.md", "roadmap.md"}
    assert _git(remote, "rev-parse", "main") == _git(app, "rev-parse", "main")
    assert _cli(app, "digest", "--check").returncode == 0   # on the new feature branch
    assert _cli(app, "export", "--check").returncode == 0
    _git(app, "checkout", "-q", "main")
    assert _cli(app, "digest", "--check").returncode == 0   # on the integration branch


def test_abort_drops_a_local_register_commit_that_carries_the_digest(tmp_path: Path) -> None:
    remote, app = _app(tmp_path)
    pushed = _git(app, "rev-parse", "main")
    assert _cli(app, "do-next-available-task", "--local").returncode == 0
    assert "roadmap-context.md" in _git(app, "show", "--name-only", "--format=", "HEAD").splitlines()
    registration = _git(app, "rev-parse", "HEAD")
    # the same commit amended to carry another file: no longer pickup's own, so refused
    (app / "README.md").write_text("extra\n", encoding="utf-8")
    _git(app, "add", "README.md")
    _git(app, "commit", "-q", "--amend", "--no-edit")
    refused = _cli(app, "abort-task-pickup")
    assert refused.returncode == 1 and "commits that are not on origin/main" in refused.stderr
    _git(app, "reset", "-q", "--hard", registration)

    r = _cli(app, "abort-task-pickup")

    assert r.returncode == 0, r.stderr
    assert _git(app, "rev-parse", "HEAD") == pushed
    assert _git(remote, "rev-parse", "main") == pushed
    assert _git(app, "branch", "--list", "feature/rm-*") == ""


def _digest_check_at_origin_main(app: Path, snapshot: Path) -> None:
    subprocess.run(
        ["git", "worktree", "remove", "-q", "--force", str(snapshot)],
        cwd=app, check=False, capture_output=True,
    )
    _git(app, "fetch", "-q", "origin")
    _git(app, "worktree", "add", "-q", "--detach", str(snapshot), "origin/main")
    try:
        assert _cli(snapshot, "digest", "--check").returncode == 0
    finally:
        subprocess.run(
            ["git", "worktree", "remove", "-q", "--force", str(snapshot)],
            cwd=app, check=False, capture_output=True,
        )


def test_abort_after_pushed_pickup_regenerates_the_digest_on_integration(tmp_path: Path) -> None:
    """R3: removing a pushed claim must leave digest --check passing locally and on the remote."""
    remote, app = _app(tmp_path)

    assert _cli(app, "do-next-available-task").returncode == 0
    assert _cli(app, "digest", "--check").returncode == 0

    assert _cli(app, "abort-task-pickup").returncode == 0

    _git(app, "checkout", "-q", "main")
    assert _cli(app, "digest", "--check").returncode == 0
    assert _git(app, "rev-parse", "main") == _git(remote, "rev-parse", "main")
    _digest_check_at_origin_main(app, tmp_path / "origin-main-digest")


def _reject_first_integration_push(bare: Path, marker: Path) -> None:
    hook = bare / "hooks" / "pre-receive"
    hook.write_text(
        "#!/bin/sh\n"
        f"if [ ! -f {marker} ]; then touch {marker}; exit 1; fi\n"
        "exit 0\n",
    )
    hook.chmod(0o755)


def test_failed_pickup_self_heal_leaves_integration_digest_current(tmp_path: Path) -> None:
    """R4: a one-time rejected registration push must not publish a stale digest on self-heal."""
    remote, app = _app(tmp_path)
    marker = tmp_path / "saw_push"
    _reject_first_integration_push(remote, marker)

    r = _cli(app, "do-next-available-task")

    assert r.returncode == 1, r.stderr
    _git(app, "checkout", "-q", "main")
    assert _cli(app, "digest", "--check").returncode == 0
    assert _git(app, "rev-parse", "main") == _git(remote, "rev-parse", "main")
    _digest_check_at_origin_main(app, tmp_path / "self-heal-origin-main")
    reg = yaml.safe_load(
        subprocess.run(
            ["git", "--git-dir", str(remote), "show", "main:roadmap/registry.yaml"],
            check=True, capture_output=True, text=True,
        ).stdout,
    )
    assert reg.get("entries") == []
