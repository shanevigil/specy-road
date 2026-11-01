"""Tests for specy-road integrity findings: test files, config, CLI and nested project roots."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.integrity_repo_helpers import commit, git, make_repo, merge_base, merge_dev, on_dev
from specy_road.bundled_scripts import integrity_cli
from specy_road.bundled_scripts import review_packet as rp
from specy_road.integrity import compare_integrity
from specy_road.review_target import resolve_target_or_exit


def test_unchanged_ref_has_no_findings(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    commit(repo, "tests/test_x.py", "def test_ok():\n    assert 1\n", "add test")
    assert compare_integrity(repo, merge_base(repo), git(repo, "rev-parse", "HEAD")) == []


def test_removed_test_file(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    on_dev(repo)
    commit(repo, "tests/test_x.py", "def test_a():\n    pass\n", "on dev")
    merge_dev(repo)
    git(repo, "rm", "tests/test_x.py")
    git(repo, "commit", "-qm", "delete file")
    lines = [f.line() for f in compare_integrity(repo, merge_base(repo), git(repo, "rev-parse", "HEAD"))]
    assert "removed-test-file: tests/test_x.py" in lines


def test_removed_go_test_file(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    on_dev(repo)
    commit(repo, "pkg/foo_test.go", "package pkg\n", "on dev")
    merge_dev(repo)
    git(repo, "rm", "pkg/foo_test.go")
    git(repo, "commit", "-qm", "drop go")
    assert compare_integrity(repo, merge_base(repo), git(repo, "rev-parse", "HEAD"))[0].line() == (
        "removed-test-file: pkg/foo_test.go"
    )


def test_config_change_conftest(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    on_dev(repo)
    commit(repo, "tests/conftest.py", "import pytest\n", "conf on dev")
    merge_dev(repo)
    commit(repo, "tests/conftest.py", "import pytest\n\npytest_plugins = []\n", "more")
    assert compare_integrity(repo, merge_base(repo), git(repo, "rev-parse", "HEAD"))[0].line() == (
        "config-change: tests/conftest.py"
    )


def test_config_change_pyproject_pytest_table(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    on_dev(repo)
    commit(repo, "pyproject.toml", "[project]\nname = 'x'\n", "proj on dev")
    merge_dev(repo)
    commit(
        repo,
        "pyproject.toml",
        "[project]\nname = 'x'\n\n[tool.pytest.ini_options]\naddopts = '-q'\n",
        "pytest",
    )
    assert compare_integrity(repo, merge_base(repo), git(repo, "rev-parse", "HEAD"))[0].line() == (
        "config-change: pyproject.toml"
    )


def test_config_change_indented_pyproject_pytest_table(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    on_dev(repo)
    commit(repo, "pyproject.toml", "  [tool.pytest.ini_options]\n  addopts = '-q'\n", "indented on dev")
    merge_dev(repo)
    commit(repo, "pyproject.toml", "  [tool.pytest.ini_options]\n  addopts = '--ignore=tests'\n", "edit")
    assert compare_integrity(repo, merge_base(repo), git(repo, "rev-parse", "HEAD"))[0].line() == (
        "config-change: pyproject.toml"
    )


def test_config_change_quoted_pyproject_pytest_table(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    on_dev(repo)
    commit(repo, "pyproject.toml", '["tool"."pytest"."ini_options"]\naddopts = "-q"\n', "quoted on dev")
    merge_dev(repo)
    commit(repo, "pyproject.toml", '["tool"."pytest"."ini_options"]\naddopts = "--ignore=tests"\n', "edit")
    assert [f.line() for f in compare_integrity(repo, merge_base(repo), git(repo, "rev-parse", "HEAD"))] == [
        "config-change: pyproject.toml"
    ]


def test_pyproject_change_outside_pytest_table_is_ignored(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    on_dev(repo)
    commit(repo, "pyproject.toml", "[project]\nname = 'x'\n", "proj on dev")
    merge_dev(repo)
    commit(repo, "pyproject.toml", "[project]\nname = 'y'\n", "rename")
    assert compare_integrity(repo, merge_base(repo), git(repo, "rev-parse", "HEAD")) == []


def test_cli_json_and_exit_codes(tmp_path: Path, capsys) -> None:
    repo = make_repo(tmp_path, roadmap=True)
    on_dev(repo)
    commit(repo, "tests/test_x.py", "def test_a():\n    assert 1\n", "on dev")
    merge_dev(repo)
    head = git(repo, "rev-parse", "HEAD")
    with pytest.raises(SystemExit) as ok:
        integrity_cli.main(["T1", "--repo-root", str(repo), "--ref", head, "--json"])
    assert ok.value.code == 0
    assert capsys.readouterr().out.strip() == ""
    commit(repo, "tests/test_x.py", "def test_a():\n    pass\n", "weaken")
    head = git(repo, "rev-parse", "HEAD")
    with pytest.raises(SystemExit) as bad:
        integrity_cli.main(["T1", "--repo-root", str(repo), "--ref", head, "--json"])
    assert bad.value.code == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["findings"][0]["kind"] == "assert-loss"


_TEST_SRC = "def test_a():\n    assert 1\n"
_CLI_FORMS = {
    "removed-test": ("tests/test_x.py", _TEST_SRC + "\ndef test_b():\n    assert 2\n", _TEST_SRC,
                     "removed-test: tests/test_x.py::test_b"),
    # a deleted Python test file reports the file and each test it held, sorted
    "removed-test-file": ("tests/test_x.py", _TEST_SRC, None,
                          "removed-test-file: tests/test_x.py\nremoved-test: tests/test_x.py::test_a"),
    "new-skip": ("tests/test_x.py", _TEST_SRC, "import pytest\n\n@pytest.mark.skip\n" + _TEST_SRC,
                 "new-skip: tests/test_x.py::test_a"),
    "assert-loss": ("tests/test_x.py", _TEST_SRC, "def test_a():\n    pass\n",
                    "assert-loss: tests/test_x.py::test_a 1->0"),
    "config-change": ("pytest.ini", "[pytest]\n", "[pytest]\naddopts = -q\n", "config-change: pytest.ini"),
}


@pytest.mark.parametrize("form", sorted(_CLI_FORMS))
def test_cli_prints_exact_line_and_exits_one_for_each_form(tmp_path: Path, capsys, form: str) -> None:
    rel, base_text, ref_text, expected = _CLI_FORMS[form]
    repo = make_repo(tmp_path, roadmap=True)
    on_dev(repo)
    commit(repo, rel, base_text, "on dev")
    merge_dev(repo)
    if ref_text is None:
        git(repo, "rm", "-q", rel)
        git(repo, "commit", "-qm", "delete")
    else:
        commit(repo, rel, ref_text, "change")
    with pytest.raises(SystemExit) as ex:
        integrity_cli.main(["T1", "--repo-root", str(repo), "--ref", git(repo, "rev-parse", "HEAD")])
    assert ex.value.code == 1
    assert capsys.readouterr().out == expected + "\n"


def test_cli_text_mode_unchanged_ref_exits_zero_silently(tmp_path: Path, capsys) -> None:
    repo = make_repo(tmp_path, roadmap=True)
    on_dev(repo)
    commit(repo, "tests/test_x.py", _TEST_SRC, "on dev")
    merge_dev(repo)
    with pytest.raises(SystemExit) as ex:
        integrity_cli.main(["T1", "--repo-root", str(repo), "--ref", git(repo, "rev-parse", "HEAD")])
    assert ex.value.code == 0
    assert capsys.readouterr().out == ""


def test_nested_project_root_reports_git_root_paths(tmp_path: Path, capsys) -> None:
    repo = make_repo(tmp_path, roadmap=True, project="sr")
    on_dev(repo)
    commit(repo, "sr/tests/test_in.py", _TEST_SRC, "inside the project")
    commit(repo, "tests/test_out.py", _TEST_SRC, "outside the project")
    merge_dev(repo)
    commit(repo, "sr/tests/test_in.py", "def test_a():\n    pass\n", "weaken inside")
    git(repo, "rm", "-q", "tests/test_out.py")
    git(repo, "commit", "-qm", "delete outside")
    head = git(repo, "rev-parse", "HEAD")
    expected = [
        "assert-loss: sr/tests/test_in.py::test_a 1->0",
        "removed-test-file: tests/test_out.py",
        "removed-test: tests/test_out.py::test_a",
    ]
    project = repo / "sr"
    with pytest.raises(SystemExit) as ex:
        integrity_cli.main(["T1", "--repo-root", str(project), "--ref", head])
    assert ex.value.code == 1
    assert capsys.readouterr().out.splitlines() == expected
    section = rp.test_integrity_section(project, resolve_target_or_exit(project, "T1", head))
    assert section[-1 - len(expected):-1] == expected
