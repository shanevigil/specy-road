"""CLI tests for roadmap dependency subcommands."""

from __future__ import annotations

from pathlib import Path

from tests.test_roadmap_crud import _fixture_repo, _run_crud


def test_list_dependencies_cli(tmp_path: Path) -> None:
    _fixture_repo(tmp_path)
    nk991 = "10000000-0000-4000-8000-000000009902"
    r = _run_crud(
        tmp_path,
        "--repo-root",
        str(tmp_path),
        "list-dependencies",
        "M99.2",
    )
    assert r.returncode == 0, r.stderr
    assert nk991 in r.stdout
    assert "M99.1" in r.stdout


def test_list_dependencies_empty_and_unknown(tmp_path: Path) -> None:
    _fixture_repo(tmp_path)
    r = _run_crud(
        tmp_path,
        "--repo-root",
        str(tmp_path),
        "list-dependencies",
        "M99.1",
    )
    assert r.returncode == 0, r.stderr
    assert "(none)" in r.stdout
    r404 = _run_crud(
        tmp_path,
        "--repo-root",
        str(tmp_path),
        "list-dependencies",
        "M404",
    )
    assert r404.returncode == 1
    assert "no roadmap node" in r404.stderr


def test_add_remove_dependency_cli(tmp_path: Path) -> None:
    _fixture_repo(tmp_path)
    nk992 = "10000000-0000-4000-8000-000000009903"
    r0 = _run_crud(
        tmp_path,
        "--repo-root",
        str(tmp_path),
        "set-dependencies",
        "M99.2",
        "--clear",
    )
    assert r0.returncode == 0, r0.stderr
    r = _run_crud(
        tmp_path,
        "--repo-root",
        str(tmp_path),
        "add-dependency",
        "M99.1",
        nk992,
    )
    assert r.returncode == 0, r.stderr
    r2 = _run_crud(
        tmp_path,
        "--repo-root",
        str(tmp_path),
        "list-dependencies",
        "M99.1",
    )
    assert nk992 in r2.stdout
    r3 = _run_crud(
        tmp_path,
        "--repo-root",
        str(tmp_path),
        "remove-dependency",
        "M99.1",
        nk992,
    )
    assert r3.returncode == 0, r3.stderr
    r4 = _run_crud(
        tmp_path,
        "--repo-root",
        str(tmp_path),
        "list-dependencies",
        "M99.1",
    )
    assert "(none)" in r4.stdout


def test_set_dependencies_clear_and_restore(tmp_path: Path) -> None:
    _fixture_repo(tmp_path)
    nk991 = "10000000-0000-4000-8000-000000009902"
    r = _run_crud(
        tmp_path,
        "--repo-root",
        str(tmp_path),
        "set-dependencies",
        "M99.2",
        "--clear",
    )
    assert r.returncode == 0, r.stderr
    r2 = _run_crud(
        tmp_path,
        "--repo-root",
        str(tmp_path),
        "list-dependencies",
        "M99.2",
    )
    assert "(none)" in r2.stdout
    r3 = _run_crud(
        tmp_path,
        "--repo-root",
        str(tmp_path),
        "set-dependencies",
        "M99.2",
        "--deps",
        nk991,
    )
    assert r.returncode == 0, r.stderr
    r4 = _run_crud(
        tmp_path,
        "--repo-root",
        str(tmp_path),
        "list-dependencies",
        "M99.2",
    )
    assert nk991 in r4.stdout
