"""Tests for the new-suppression and baseline-widened findings of specy-road integrity."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.integrity_repo_helpers import commit, git, make_repo, merge_dev, on_dev
from specy_road.bundled_scripts import integrity_cli

_BASE = "a = 1\nb = 2\n"
_MARKERS = [
    "x = f()  # noqa: E501",
    "x = f()  # type: ignore[attr-defined]",
    "if x:  # pragma: no cover",
    "x = f()  # pylint: disable=broad-except",
    "// eslint-disable-next-line no-console",
    "// @ts-ignore",
    "// @ts-expect-error",
    "x := f() //nolint:errcheck",
]
_BASELINE = "constraints/clone-baseline.json"


def _run(repo: Path, capsys, project: str = "") -> tuple[int, str]:
    with pytest.raises(SystemExit) as ex:
        integrity_cli.main(["T1", "--repo-root", str(repo / project), "--ref", git(repo, "rev-parse", "HEAD")])
    return ex.value.code, capsys.readouterr().out


def _policy(repo: Path, paths: list[str], project: str = "") -> None:
    listed = "".join(f"\n    - {p}" for p in paths)
    commit(repo, f"{project}/roadmap/orchestration.yaml".lstrip("/"),
           f"version: 1\npolicy:\n  ratchet_paths:{listed}\n", "ratchet paths")


@pytest.mark.parametrize("marker", _MARKERS)
def test_new_suppression_prints_path_and_line_and_exits_one(tmp_path: Path, capsys, marker: str) -> None:
    repo = make_repo(tmp_path, roadmap=True)
    on_dev(repo)
    commit(repo, "src/mod.py", _BASE, "on dev")
    merge_dev(repo)
    commit(repo, "src/mod.py", _BASE + marker + "\n", "suppress")
    assert _run(repo, capsys) == (1, "new-suppression: src/mod.py:3\n")


def test_existing_suppression_moved_by_an_insert_is_not_new(tmp_path: Path, capsys) -> None:
    repo = make_repo(tmp_path, roadmap=True)
    on_dev(repo)
    commit(repo, "src/mod.py", "x = f()  # noqa\n", "on dev")
    merge_dev(repo)
    commit(repo, "src/mod.py", "import os\nx = f()  # noqa\n", "insert above")
    assert _run(repo, capsys) == (0, "")


def test_baseline_widened_prints_added_line_count_and_exits_one(tmp_path: Path, capsys) -> None:
    repo = make_repo(tmp_path, roadmap=True)
    on_dev(repo)
    _policy(repo, [_BASELINE])
    commit(repo, _BASELINE, '[\n  "a"\n]\n', "baseline on dev")
    merge_dev(repo)
    commit(repo, _BASELINE, '[\n  "a",\n  "b"\n]\n', "widen")
    assert _run(repo, capsys) == (1, f"baseline-widened: {_BASELINE} +2\n")


def test_baseline_removal_only_exits_zero(tmp_path: Path, capsys) -> None:
    repo = make_repo(tmp_path, roadmap=True)
    on_dev(repo)
    _policy(repo, [_BASELINE])
    commit(repo, _BASELINE, "a\nb\nc\n", "baseline on dev")
    merge_dev(repo)
    commit(repo, _BASELINE, "a\nc\n", "shrink")
    assert _run(repo, capsys) == (0, "")


def test_ratchet_paths_listed_only_on_the_leaf_branch_are_ignored(tmp_path: Path, capsys) -> None:
    repo = make_repo(tmp_path, roadmap=True)
    on_dev(repo)
    commit(repo, _BASELINE, "a\n", "baseline on dev")
    merge_dev(repo)
    _policy(repo, [_BASELINE])
    commit(repo, _BASELINE, "a\nb\n", "widen")
    assert _run(repo, capsys) == (0, "")


def test_nested_project_ratchet_path_outside_the_project(tmp_path: Path, capsys) -> None:
    repo = make_repo(tmp_path, roadmap=True, project="sr")
    on_dev(repo)
    _policy(repo, [_BASELINE], project="sr")
    commit(repo, _BASELINE, "a\n", "baseline on dev, at the git root")
    merge_dev(repo)
    commit(repo, _BASELINE, "a\nb\n", "widen")
    assert _run(repo, capsys, project="sr") == (1, f"baseline-widened: {_BASELINE} +1\n")


def test_non_utf8_file_in_the_diff_hides_no_other_finding(tmp_path: Path, capsys) -> None:
    repo = make_repo(tmp_path, roadmap=True)
    on_dev(repo)
    _policy(repo, [_BASELINE])
    commit(repo, _BASELINE, "a\n", "baseline on dev")
    merge_dev(repo)
    (repo / "legacy.txt").write_bytes(b"caf\xe9\n")
    (repo / _BASELINE).write_bytes(b"a\ncaf\xe9\nb  # noqa\n")
    git(repo, "add", "legacy.txt", _BASELINE)
    git(repo, "commit", "-qm", "widen with non-UTF-8 text")
    commit(repo, "src/mod.py", "x = 1  # noqa\n", "suppress")
    assert _run(repo, capsys) == (1, (
        f"baseline-widened: {_BASELINE} +2\n"
        f"new-suppression: {_BASELINE}:3\n"
        "new-suppression: src/mod.py:1\n"
    ))


def test_paths_with_spaces_are_reported_and_matched_exactly(tmp_path: Path, capsys) -> None:
    repo = make_repo(tmp_path, roadmap=True)
    on_dev(repo)
    _policy(repo, ["constraints/a b.txt"])
    commit(repo, "constraints/a b.txt", "a\n", "baseline on dev")
    merge_dev(repo)
    commit(repo, "constraints/a b.txt", "a\nb\n", "widen")
    commit(repo, "src/a b.txt", "x = 1  # noqa\n", "suppress")
    assert _run(repo, capsys) == (1, "baseline-widened: constraints/a b.txt +1\nnew-suppression: src/a b.txt:1\n")
