"""CLI tests for roadmap dependency subcommands."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.test_roadmap_crud import crud_fixture_repo, run_crud


def test_list_dependencies_cli(tmp_path: Path) -> None:
    crud_fixture_repo(tmp_path)
    nk991 = "10000000-0000-4000-8000-000000009902"
    r = run_crud(
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
    crud_fixture_repo(tmp_path)
    r = run_crud(
        tmp_path,
        "--repo-root",
        str(tmp_path),
        "list-dependencies",
        "M99.1",
    )
    assert r.returncode == 0, r.stderr
    assert "(none)" in r.stdout
    r404 = run_crud(
        tmp_path,
        "--repo-root",
        str(tmp_path),
        "list-dependencies",
        "M404",
    )
    assert r404.returncode == 1
    assert "no roadmap node" in r404.stderr


def test_add_remove_dependency_cli(tmp_path: Path) -> None:
    crud_fixture_repo(tmp_path)
    nk992 = "10000000-0000-4000-8000-000000009903"
    r0 = run_crud(
        tmp_path,
        "--repo-root",
        str(tmp_path),
        "set-dependencies",
        "M99.2",
        "--clear",
    )
    assert r0.returncode == 0, r0.stderr
    r = run_crud(
        tmp_path,
        "--repo-root",
        str(tmp_path),
        "add-dependency",
        "M99.1",
        nk992,
    )
    assert r.returncode == 0, r.stderr
    r2 = run_crud(
        tmp_path,
        "--repo-root",
        str(tmp_path),
        "list-dependencies",
        "M99.1",
    )
    assert nk992 in r2.stdout
    r3 = run_crud(
        tmp_path,
        "--repo-root",
        str(tmp_path),
        "remove-dependency",
        "M99.1",
        nk992,
    )
    assert r3.returncode == 0, r3.stderr
    r4 = run_crud(
        tmp_path,
        "--repo-root",
        str(tmp_path),
        "list-dependencies",
        "M99.1",
    )
    assert "(none)" in r4.stdout


def test_set_dependencies_clear_and_restore(tmp_path: Path) -> None:
    crud_fixture_repo(tmp_path)
    nk991 = "10000000-0000-4000-8000-000000009902"
    r = run_crud(
        tmp_path,
        "--repo-root",
        str(tmp_path),
        "set-dependencies",
        "M99.2",
        "--clear",
    )
    assert r.returncode == 0, r.stderr
    r2 = run_crud(
        tmp_path,
        "--repo-root",
        str(tmp_path),
        "list-dependencies",
        "M99.2",
    )
    assert "(none)" in r2.stdout
    r3 = run_crud(
        tmp_path,
        "--repo-root",
        str(tmp_path),
        "set-dependencies",
        "M99.2",
        "--deps",
        nk991,
    )
    assert r.returncode == 0, r.stderr
    r4 = run_crud(
        tmp_path,
        "--repo-root",
        str(tmp_path),
        "list-dependencies",
        "M99.2",
    )
    assert nk991 in r4.stdout


def _repo_with_milestone(tmp_path: Path) -> None:
    """The crud fixture plus milestone M99.3 holding leaf M99.3.1."""
    crud_fixture_repo(tmp_path)
    for nid, typ, parent in (("M99.3", "milestone", "M99"), ("M99.3.1", "task", "M99.3")):
        r = run_crud(
            tmp_path, "--repo-root", str(tmp_path), "add-node", "--id", nid,
            "--type", typ, "--title", f"Node {nid}", "--parent-id", parent,
        )
        assert r.returncode == 0, r.stderr


def _tree(root: Path) -> dict[str, bytes]:
    return {str(p.relative_to(root)): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()}


def test_add_dependency_reports_descendant_leaves_that_now_wait(tmp_path: Path) -> None:
    _repo_with_milestone(tmp_path)

    def add(nid: str, dep: str) -> list[str]:
        r = run_crud(tmp_path, "--repo-root", str(tmp_path), "add-dependency", nid, dep)
        assert r.returncode == 0, r.stderr
        assert r.stdout.startswith("[ok] added ")
        return r.stdout.splitlines()[1:]

    assert add("M99.3.1", "M99.1") == []   # a leaf has no descendants
    assert add("M99.3", "M99.1") == []     # M99.3.1 already waits on M99.1
    assert add("M99.3", "M99.2") == ["1 descendant leaves now wait on M99.2: M99.3.1"]


@pytest.mark.parametrize(
    "first, edge, message",
    [
        (   # M99.3.1 inherits M99.3's dependency on M99.2, which waits on M99.1.
            ("M99.3", "M99.2"),
            ("M99.1", "M99.3.1"),
            "error: roadmap: dependency cycle: M99.1 -> M99.3.1 -> M99.2 -> M99.1\n"
            "  M99.3.1 -> M99.2: inherited from M99.3, which depends on M99.2\n",
        ),
        (None, ("M99.3", "M99.3.1"), "error: roadmap: inherited self-edge M99.3.1 via M99.3\n"),
    ],
)
def test_add_dependency_refuses_cycle_through_inherited_dependency(
    tmp_path: Path, first: tuple[str, str] | None, edge: tuple[str, str], message: str
) -> None:
    _repo_with_milestone(tmp_path)
    if first:
        r0 = run_crud(tmp_path, "--repo-root", str(tmp_path), "add-dependency", *first)
        assert r0.returncode == 0, r0.stderr
    before = _tree(tmp_path)
    r = run_crud(tmp_path, "--repo-root", str(tmp_path), "add-dependency", *edge)
    assert r.returncode == 1
    assert r.stderr.endswith(message)
    assert _tree(tmp_path) == before
