"""Tests for specy-road update (scripts/update_specy_road.py)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
import update_specy_road as usr

REPO = Path(__file__).resolve().parent.parent


def _git_user(cwd: Path) -> None:
    subprocess.run(
        ["git", "config", "user.email", "t@e.st"],
        cwd=cwd,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "t"],
        cwd=cwd,
        check=True,
        capture_output=True,
    )


def _worktree_behind_bare_with_v2(tmp_path: Path) -> Path:
    """Bare repo on ``main`` at README v2; return a clone still at v1 with old fetch state."""
    bare = tmp_path / "upstream.git"
    subprocess.run(
        ["git", "init", "--bare", str(bare)],
        check=True,
        capture_output=True,
    )
    seed = tmp_path / "seed"
    subprocess.run(
        ["git", "clone", str(bare), str(seed)],
        check=True,
        capture_output=True,
    )
    _git_user(seed)
    (seed / "README.md").write_text("v1\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=seed, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "v1"], cwd=seed, check=True, capture_output=True)
    subprocess.run(["git", "branch", "-M", "main"], cwd=seed, check=True, capture_output=True)
    subprocess.run(
        ["git", "push", "-u", "origin", "main"],
        cwd=seed,
        check=True,
        capture_output=True,
    )
    work = tmp_path / "work"
    subprocess.run(
        ["git", "clone", str(bare), str(work)],
        check=True,
        capture_output=True,
    )
    (seed / "README.md").write_text("v2\n", encoding="utf-8")
    subprocess.run(["git", "commit", "-am", "v2"], cwd=seed, check=True, capture_output=True)
    subprocess.run(["git", "push", "origin", "main"], cwd=seed, check=True, capture_output=True)
    return work


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        (
            "git@github.com:shanevigil/specy-road.git",
            "shanevigil/specy-road",
        ),
        (
            "https://github.com/shanevigil/specy-road.git",
            "shanevigil/specy-road",
        ),
        (
            "https://github.com/shanevigil/specy-road",
            "shanevigil/specy-road",
        ),
        (
            "git@github.com:other/other.git",
            "other/other",
        ),
    ],
)
def test_normalize_github_repo_path(url: str, expected: str) -> None:
    assert usr.normalize_github_repo_path(url) == expected.lower()


def test_normalize_github_repo_path_invalid() -> None:
    assert usr.normalize_github_repo_path("not-a-url") is None


@pytest.mark.parametrize(
    "url",
    [
        "git@github.com:shanevigil/specy-road.git",
        "https://github.com/shanevigil/specy-road",
    ],
)
def test_is_canonical_specy_road_remote_accepts(url: str) -> None:
    assert usr.is_canonical_specy_road_remote(url) is True


def test_is_canonical_specy_road_remote_rejects_fork() -> None:
    fork = "git@github.com:other/specy-road.git"
    assert usr.is_canonical_specy_road_remote(fork) is False


def test_specy_road_update_help() -> None:
    r = subprocess.run(
        [sys.executable, "-m", "specy_road.cli", "update", "--help"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    )
    out = r.stdout + r.stderr
    assert "--path" in out
    assert "--dry-run" in out
    assert "--allow-dirty" in out
    assert "--install-gui-stack" in out
    assert "--reset-to-origin" in out


def test_parser_reset_to_origin_flag() -> None:
    p = usr._build_parser()
    args = p.parse_args(["--reset-to-origin"])
    assert args.reset_to_origin is True


def test_update_dry_run_tmp_repo(tmp_path: Path) -> None:
    subprocess.run(
        ["git", "init"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "t@e.st"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "t"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    (tmp_path / "README.md").write_text("x\n", encoding="utf-8")
    subprocess.run(
        ["git", "add", "README.md"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "branch", "-M", "main"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        [
            "git",
            "remote",
            "add",
            "origin",
            "https://github.com/shanevigil/specy-road.git",
        ],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )

    r = subprocess.run(
        [
            sys.executable,
            "-m",
            "specy_road.cli",
            "update",
            "--path",
            str(tmp_path),
            "--dry-run",
        ],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "Would run:" in r.stdout
    assert "git fetch" in r.stdout
    assert "git checkout" in r.stdout
    assert "merge --ff-only" in r.stdout


def test_reset_to_origin_dry_run_tmp_repo(tmp_path: Path) -> None:
    subprocess.run(
        ["git", "init"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "t@e.st"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "t"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    (tmp_path / "README.md").write_text("x\n", encoding="utf-8")
    subprocess.run(
        ["git", "add", "README.md"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "branch", "-M", "main"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        [
            "git",
            "remote",
            "add",
            "origin",
            "https://github.com/shanevigil/specy-road.git",
        ],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )

    r = subprocess.run(
        [
            sys.executable,
            "-m",
            "specy_road.cli",
            "update",
            "--path",
            str(tmp_path),
            "--dry-run",
            "--reset-to-origin",
        ],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    )
    out = r.stdout + r.stderr
    assert "destructive" in out.lower()
    assert "git reset --hard" in out
    assert "git clean -fd" in out
    assert "specy_road/pm_gantt_static" in out


def test_reset_to_origin_matches_remote_bare(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Local bare remote + canonical URL bypass: tree matches origin after reset."""
    monkeypatch.setattr(usr, "is_canonical_specy_road_remote", lambda _url: True)
    work = _worktree_behind_bare_with_v2(tmp_path)
    (work / "README.md").write_text("dirty\n", encoding="utf-8")
    junk_dir = work / "specy_road" / "pm_gantt_static" / "assets"
    junk_dir.mkdir(parents=True)
    (junk_dir / "untracked.js").write_text("//u", encoding="utf-8")

    # In-process so ``monkeypatch`` on canonical remote applies (child CLI would not).
    usr.main(["--path", str(work), "--reset-to-origin"])
    assert (work / "README.md").read_text(encoding="utf-8") == "v2\n"
    st = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=work,
        capture_output=True,
        text=True,
        check=True,
    )
    assert st.stdout.strip() == ""
