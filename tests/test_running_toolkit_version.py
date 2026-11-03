"""Checkout-aware ``running_toolkit_version`` for ``--version`` and audit records."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

from specy_road import __version__
from specy_road.git_subprocess import head_sha, working_tree_clean
from specy_road.runtime_paths import git_root, specy_road_package_dir
from specy_road.version_skew import running_toolkit_version

REPO = Path(__file__).resolve().parent.parent


def _import_running_version_from_root(repo_root: Path) -> str:
    code = textwrap.dedent(
        """
        import sys
        for mod in [m for m in list(sys.modules) if m == 'specy_road' or m.startswith('specy_road.')]:
            sys.modules.pop(mod, None)
        import specy_road.toolkit_version as tv
        print(tv.running_toolkit_version())
        """
    )
    env = {**os.environ, "PYTHONPATH": str(repo_root)}
    r = subprocess.run(
        [sys.executable, "-P", "-c", code],
        cwd=repo_root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert r.returncode == 0, r.stderr
    return r.stdout.strip().splitlines()[-1]


def _import_running_version_on_path(site_packages: Path) -> str:
    code = textwrap.dedent(
        """
        import sys
        for mod in [m for m in list(sys.modules) if m == 'specy_road' or m.startswith('specy_road.')]:
            sys.modules.pop(mod, None)
        import specy_road.toolkit_version as tv
        print(tv.running_toolkit_version())
        """
    )
    env = {**os.environ, "PYTHONPATH": str(site_packages)}
    r = subprocess.run(
        [sys.executable, "-P", "-c", code],
        cwd=site_packages,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert r.returncode == 0, r.stderr
    return r.stdout.strip().splitlines()[-1]


def _stage_specy_road_package(target_repo_root: Path) -> None:
    shutil.copytree(REPO / "specy_road", target_repo_root / "specy_road")


def test_running_version_in_this_checkout_matches_head() -> None:
    root = git_root(specy_road_package_dir())
    assert root is not None
    sha = head_sha(root)
    assert sha is not None
    v = running_toolkit_version()
    assert v.startswith(f"{__version__}+")
    assert sha[:12] in v
    if working_tree_clean(root):
        assert not v.endswith(".dirty")
    else:
        assert v.endswith(".dirty")


def test_non_checkout_install_reports_plain_version(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        textwrap.dedent(
            """
            [project]
            name = "specy-road"
            version = "9.9.9-test"
            """
        ),
        encoding="utf-8",
    )
    _stage_specy_road_package(tmp_path)
    assert _import_running_version_from_root(tmp_path) == "9.9.9-test"


def test_wheel_in_gitignored_venv_of_unrelated_repo_reports_plain_version(tmp_path: Path) -> None:
    consumer = tmp_path / "consumer"
    consumer.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=consumer, check=True)
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=consumer, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=consumer, check=True)
    (consumer / "app.py").write_text("print('hi')\n", encoding="utf-8")
    subprocess.run(["git", "add", "app.py"], cwd=consumer, check=True)
    subprocess.run(["git", "commit", "-qm", "init"], cwd=consumer, check=True)
    site = consumer / ".venv" / "lib" / f"python{sys.version_info.major}.{sys.version_info.minor}" / "site-packages"
    site.mkdir(parents=True)
    shutil.copytree(REPO / "specy_road", site / "specy_road")
    v = _import_running_version_on_path(site)
    assert "+" not in v


def test_checkout_reports_sha(tmp_path: Path) -> None:
    repo = tmp_path / "kit"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=repo, check=True)
    _stage_specy_road_package(repo)
    (repo / "pyproject.toml").write_text(
        textwrap.dedent(
            """
            [project]
            name = "specy-road"
            version = "1.0.0"
            """
        ),
        encoding="utf-8",
    )
    (repo / "marker.txt").write_text("x\n", encoding="utf-8")
    subprocess.run(["git", "add", "marker.txt", "pyproject.toml", "specy_road"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "init"], cwd=repo, check=True)
    sha = head_sha(repo)
    assert sha is not None
    v = _import_running_version_from_root(repo)
    assert v == f"1.0.0+{sha[:12]}"


def test_dirty_checkout_marks_dirty(tmp_path: Path) -> None:
    repo = tmp_path / "kit"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=repo, check=True)
    _stage_specy_road_package(repo)
    (repo / "pyproject.toml").write_text("[project]\nname = \"specy-road\"\nversion = \"1.0.0\"\n", encoding="utf-8")
    (repo / "marker.txt").write_text("x\n", encoding="utf-8")
    subprocess.run(["git", "add", "marker.txt", "pyproject.toml", "specy_road"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "init"], cwd=repo, check=True)
    sha = head_sha(repo)
    (repo / "marker.txt").write_text("dirty\n", encoding="utf-8")
    v = _import_running_version_from_root(repo)
    assert v == f"1.0.0+{sha[:12]}.dirty"


def test_worker_record_stores_toolkit_version(tmp_path: Path) -> None:
    from tests.review_repo_helpers import make_review_repo

    from specy_road import worker_state as ws

    repo = make_review_repo(tmp_path)
    rec = ws.create_record(repo, "M1.1", "generic", "m", repo)
    assert rec.toolkit_version == running_toolkit_version()
    assert ws.load_record(repo, rec.worker_id).toolkit_version == rec.toolkit_version


def test_explicit_stamp_before_render_writes_toolkit_version(tmp_path: Path) -> None:
    from specy_road.review_files import load_review, render_front_matter
    from specy_road.toolkit_version import running_toolkit_version, stamp_review_toolkit_version

    body = "notes\n"
    data = stamp_review_toolkit_version({
        "node_id": "M1.1",
        "model": "opus",
        "date": "2026-11-03",
        "verdict": "approve",
        "commit": "a" * 40,
        "acceptance": {"A1": "pass"},
        "findings": {"correctness": [], "regression": [], "boundary": [], "test_integrity": []},
        "fresh_session": True,
        "authored_fix": False,
        "is_coordinator": False,
    })
    path = tmp_path / "REVIEW-opus.md"
    path.write_text(render_front_matter(data, body), encoding="utf-8")
    loaded = load_review(path, ["A1"])
    assert loaded.ok
    assert loaded.data["toolkit_version"] == running_toolkit_version()


def test_ready_front_matter_does_not_stamp_toolkit_version(tmp_path: Path) -> None:
    from specy_road.review_files import load_ready, render_front_matter

    data = {
        "node_id": "M1.1",
        "agent": "composer-2.5",
        "branch": "feature/rm-thing",
        "commit": "a" * 40,
        "base": "b" * 40,
        "changed_paths": ["src/a.py"],
        "verify": [{"cmd": "pytest", "exit": 0}],
    }
    path = tmp_path / "READY-composer-2.5.md"
    path.write_text(render_front_matter(data, "done\n"), encoding="utf-8")
    loaded = load_ready(path)
    assert loaded.ok, loaded.errors
    assert "toolkit_version" not in loaded.data
