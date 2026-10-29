"""Defects from the 0.3.1-rc1 three-app user test (all present since 0.2.3)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from tests.helpers import REPO, script_subprocess_env


def _cli(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "specy_road.cli", *args, "--repo-root", str(root)],
        cwd=REPO,
        env=script_subprocess_env(),
        capture_output=True,
        text=True,
    )


def _scaffold(root: Path) -> None:
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    r = subprocess.run(
        [sys.executable, "-m", "specy_road.cli", "init", "project", str(root)],
        cwd=REPO,
        env=script_subprocess_env(),
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, r.stderr


def test_move_node_keeps_the_scaffold_m1_numbering(tmp_path: Path) -> None:
    """The scaffold starts at M1; a move used to renumber every root to M0."""
    _scaffold(tmp_path)
    add = ("add-node", "--id", "M1.2", "--type", "task", "--title", "Second")
    assert _cli(tmp_path, *add, "--parent-id", "M1").returncode == 0

    r = _cli(tmp_path, "move-node", "M1.2", "--to-parent", "M1", "--index", "0")

    assert r.returncode == 0, r.stderr
    assert "[ok] moved M1.1 under M1" in r.stdout
    sheets = sorted(p.name.split("_")[0] for p in (tmp_path / "planning").glob("M*.md"))
    assert sheets == ["M1", "M1.1", "M1.2"]


def test_refresh_stubs_without_a_stub_pack_still_owns_the_blocks(tmp_path: Path) -> None:
    """The documented upgrade runs refresh-stubs; the stub pack is optional, the blocks are not."""
    _scaffold(tmp_path)
    (tmp_path / "AGENTS.md").write_text("# Ours\n", encoding="utf-8")

    r = _cli(tmp_path, "refresh-stubs")

    assert r.returncode == 0, r.stderr
    assert "no specyrd stub pack installed" in r.stdout
    assert "AGENTS.md (updated)" in r.stdout
    assert "specy-road managed block" in (tmp_path / "AGENTS.md").read_text(encoding="utf-8")


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=root, check=True, capture_output=True, text=True
    ).stdout.strip()


def test_abort_of_a_local_pickup_drops_the_claim_without_pushing(tmp_path: Path) -> None:
    """--local registers only in this checkout; abort used to refuse or push it."""
    remote, app = tmp_path / "remote.git", tmp_path / "app"
    _git(tmp_path, "init", "-q", "--bare", str(remote))
    _scaffold(app)
    assert _cli(app, "add-node", "--id", "M1.2", "--type", "task", "--title", "Other",
                "--parent-id", "M1").returncode == 0
    reg = app / "roadmap" / "registry.yaml"   # a teammate's claim, already on the remote
    reg.write_text(reg.read_text().replace("entries: []", (
        "entries:\n  - {codename: other, node_id: M1.2, branch: feature/rm-other, touch_zones: [],"
        " started: '2026-10-01', owner: Pat, implementation_review: pending}")))
    _git(app, "config", "user.email", "t@example.com")
    _git(app, "config", "user.name", "T")
    _git(app, "checkout", "-q", "-b", "main")
    _git(app, "add", "-A")
    _git(app, "commit", "-q", "-m", "init")
    _git(app, "remote", "add", "origin", str(remote))
    _git(app, "push", "-q", "-u", "origin", "main")
    pushed = _git(app, "rev-parse", "main")
    assert _cli(app, "do-next-available-task", "--local").returncode == 0
    registration = _git(app, "rev-parse", "HEAD")
    # the registration commit amended to carry source work, subject kept: refused, work kept
    (app / "src").mkdir()
    (app / "src" / "work.py").write_text("x = 1\n")
    _git(app, "add", "src/work.py")
    _git(app, "commit", "-q", "--amend", "--no-edit")
    amended = _git(app, "rev-parse", "HEAD")
    refused = _cli(app, "abort-task-pickup")
    assert refused.returncode == 1 and "commits that are not on origin/main" in refused.stderr
    assert _git(app, "rev-parse", "HEAD") == amended and (app / "src" / "work.py").is_file()
    _git(app, "reset", "-q", "--hard", registration)
    # the registration commit amended to also change the teammate's claim: refused, change kept
    reg.write_text(reg.read_text().replace("owner: Pat", "owner: Mallory"))
    _git(app, "commit", "-q", "-a", "--amend", "--no-edit")
    refused = _cli(app, "abort-task-pickup")
    assert refused.returncode == 1 and "commits that are not on origin/main" in refused.stderr
    assert "owner: Mallory" in reg.read_text()
    _git(app, "reset", "-q", "--hard", registration)

    (app / "work" / "brief-M9.9.md").write_text("another leaf's brief\n")   # §5 re-check F-R3: not this abort's
    r = _cli(app, "abort-task-pickup")

    assert r.returncode == 0, r.stderr
    assert _git(remote, "rev-parse", "main") == pushed
    assert _git(app, "rev-parse", "HEAD") == pushed
    assert _git(app, "branch", "--list", "feature/rm-*") == ""
