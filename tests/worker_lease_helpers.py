"""Public helpers for cross-checkout ``policy.max_workers`` / lease tests."""

from __future__ import annotations

import subprocess
from pathlib import Path

from tests.review_repo_helpers import git

from specy_road import worker_lease as lease
from specy_road import worker_state as ws


def remote_and_clone(tmp_path: Path, repo: Path) -> tuple[Path, Path]:
    """Bare integration remote for ``repo`` and a second clone: two checkouts sharing one registry."""
    remote = tmp_path / "remote.git"
    git(tmp_path, "init", "-q", "--bare", str(remote))
    git(repo, "remote", "add", "origin", str(remote))
    git(repo, "push", "-q", "origin", "dev", "feature/rm-thing")
    git(repo, "fetch", "-q", "origin")
    git(repo, "remote", "set-head", "origin", "dev")
    clone = tmp_path / "clone"
    git(tmp_path, "clone", "-q", "-b", "dev", str(remote), str(clone))
    git(clone, "remote", "set-head", "origin", "dev")
    git(clone, "config", "user.email", "t@e.com")
    git(clone, "config", "user.name", "T")
    return remote, clone


def remote_leases(remote: Path) -> list[str]:
    out = subprocess.run(["git", "ls-remote", str(remote), lease.LEASES + "*"], capture_output=True, text=True,
                         check=True).stdout
    return sorted(line.split("\t")[1][len(lease.LEASES):] for line in out.splitlines())


def idle_worker(repo: Path, node: str, session: str = "sid-1") -> ws.WorkerRecord:
    rec = ws.create_record(repo, node, "claude-code", "opus", repo)
    ws.mutate(repo, rec, lambda r: setattr(r, "provider_session_id", session))
    return ws.set_state(repo, rec, "idle", pid=None)


def checkout_id_file(repo: Path) -> Path:
    return repo / ".git" / "specy-road-checkout-id"
