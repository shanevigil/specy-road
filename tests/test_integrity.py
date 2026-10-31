"""Tests for specy-road integrity findings."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from tests.helpers import DOGFOOD
from specy_road.bundled_scripts import integrity_cli
from specy_road.bundled_scripts import review_packet as rp
from specy_road.integrity import compare_integrity
from specy_road.review_target import resolve_target_or_exit


def _git(repo: Path, *args: str) -> str:
    r = subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True)
    return r.stdout.strip()


def _commit(repo: Path, rel: str, text: str, msg: str) -> str:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    _git(repo, "add", rel)
    _git(repo, "commit", "-qm", msg)
    return _git(repo, "rev-parse", "HEAD")


def _merge_base(repo: Path) -> str:
    return _git(repo, "merge-base", "dev", "HEAD")


def _on_dev(repo: Path) -> None:
    _git(repo, "checkout", "-q", "dev")


def _on_feature(repo: Path) -> None:
    _git(repo, "checkout", "-q", "feature")


def _roadmap(repo: Path, project: str = "") -> None:
    _on_dev(repo)
    proj = repo / project
    shutil.copytree(DOGFOOD / "schemas", proj / "schemas")
    (proj / "roadmap" / "phases").mkdir(parents=True, exist_ok=True)
    (proj / "roadmap" / "manifest.json").write_text('{"version": 1, "includes": ["phases/T.json"]}', encoding="utf-8")
    node = {
        "id": "T1",
        "node_key": "11111111-1111-5111-8111-111111111111",
        "codename": "t",
        "title": "T",
        "type": "task",
        "parent_id": None,
        "sibling_order": 1,
        "status": "In Progress",
        "dependencies": [],
        "touch_zones": ["src"],
    }
    (proj / "roadmap" / "phases" / "T.json").write_text(json.dumps({"nodes": [node]}), encoding="utf-8")
    (proj / "roadmap" / "git-workflow.yaml").write_text(
        "version: 1\nintegration_branch: dev\nremote: origin\n", encoding="utf-8"
    )
    entry = {"codename": "t", "node_id": "T1", "branch": "feature"}
    (proj / "roadmap" / "registry.yaml").write_text(
        yaml.safe_dump({"version": 1, "entries": [entry]}), encoding="utf-8"
    )
    _git(repo, "add", str(proj / "roadmap"), str(proj / "schemas"))
    _git(repo, "commit", "-qm", "roadmap")


def _repo(tmp_path: Path, *, roadmap: bool = False, project: str = "") -> Path:
    root = tmp_path / "r"
    root.mkdir()
    _git(root, "init", "-q", "-b", "dev")
    _git(root, "config", "user.email", "t@e.com")
    _git(root, "config", "user.name", "T")
    _commit(root, "README.md", "# r\n", "init")
    if roadmap:
        _roadmap(root, project)
    _git(root, "checkout", "-q", "-b", "feature")
    return root


def _merge_dev(repo: Path) -> None:
    _on_feature(repo)
    _git(repo, "merge", "dev", "--no-edit")


def test_unchanged_ref_has_no_findings(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    _commit(repo, "tests/test_x.py", "def test_ok():\n    assert 1\n", "add test")
    assert compare_integrity(repo, _merge_base(repo), _git(repo, "rev-parse", "HEAD")) == []


def test_removed_test_function(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    _on_dev(repo)
    _commit(
        repo,
        "tests/test_x.py",
        "def test_keep():\n    assert 1\n\ndef test_gone():\n    assert 2\n",
        "both on dev",
    )
    _merge_dev(repo)
    _commit(repo, "tests/test_x.py", "def test_keep():\n    assert 1\n", "drop one")
    findings = compare_integrity(repo, _merge_base(repo), _git(repo, "rev-parse", "HEAD"))
    assert [f.line() for f in findings if f.kind == "removed-test"] == ["removed-test: tests/test_x.py::test_gone"]


def test_removed_test_file(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    _on_dev(repo)
    _commit(repo, "tests/test_x.py", "def test_a():\n    pass\n", "on dev")
    _merge_dev(repo)
    _git(repo, "rm", "tests/test_x.py")
    _git(repo, "commit", "-qm", "delete file")
    lines = [f.line() for f in compare_integrity(repo, _merge_base(repo), _git(repo, "rev-parse", "HEAD"))]
    assert "removed-test-file: tests/test_x.py" in lines


def test_removed_go_test_file(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    _on_dev(repo)
    _commit(repo, "pkg/foo_test.go", "package pkg\n", "on dev")
    _merge_dev(repo)
    _git(repo, "rm", "pkg/foo_test.go")
    _git(repo, "commit", "-qm", "drop go")
    assert compare_integrity(repo, _merge_base(repo), _git(repo, "rev-parse", "HEAD"))[0].line() == (
        "removed-test-file: pkg/foo_test.go"
    )


def test_new_skip_decorator(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    _on_dev(repo)
    _commit(repo, "tests/test_x.py", "def test_later():\n    assert 1\n", "on dev")
    _merge_dev(repo)
    _commit(
        repo,
        "tests/test_x.py",
        "import pytest\n\n@pytest.mark.skip\n"
        "def test_later():\n    assert 1\n",
        "skip",
    )
    assert compare_integrity(repo, _merge_base(repo), _git(repo, "rev-parse", "HEAD"))[0].line() == (
        "new-skip: tests/test_x.py::test_later"
    )


def test_new_skip_bare_xfail_decorator(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    _on_dev(repo)
    _commit(repo, "tests/test_x.py", "def test_later():\n    assert 1\n", "on dev")
    _merge_dev(repo)
    _commit(
        repo,
        "tests/test_x.py",
        "import pytest\n\n@pytest.mark.xfail\n"
        "def test_later():\n    assert 1\n",
        "bare xfail",
    )
    assert [f.line() for f in compare_integrity(repo, _merge_base(repo), _git(repo, "rev-parse", "HEAD"))] == [
        "new-skip: tests/test_x.py::test_later"
    ]


def test_new_skip_call(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    _on_dev(repo)
    _commit(repo, "tests/test_x.py", "def test_later():\n    assert 1\n", "on dev")
    _merge_dev(repo)
    _commit(
        repo,
        "tests/test_x.py",
        "import pytest\n\n"
        "def test_later():\n    pytest.skip('nope')\n    assert 1\n",
        "skip call",
    )
    assert compare_integrity(repo, _merge_base(repo), _git(repo, "rev-parse", "HEAD"))[0].line() == (
        "new-skip: tests/test_x.py::test_later"
    )


def test_unrelated_decorator_named_skip_is_not_a_skip(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    _on_dev(repo)
    _commit(repo, "tests/test_x.py", "def test_x():\n    assert 1\n", "on dev")
    _merge_dev(repo)
    _commit(
        repo,
        "tests/test_x.py",
        "class custom:\n    skip = staticmethod(lambda f: f)\n\n"
        "@custom.skip\ndef test_x():\n    assert 1\n",
        "identity decorator",
    )
    assert compare_integrity(repo, _merge_base(repo), _git(repo, "rev-parse", "HEAD")) == []


def test_assert_loss(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    _on_dev(repo)
    _commit(repo, "tests/test_x.py", "def test_thin():\n    assert 1\n    assert 2\n", "two on dev")
    _merge_dev(repo)
    _commit(repo, "tests/test_x.py", "def test_thin():\n    assert 1\n", "one")
    assert compare_integrity(repo, _merge_base(repo), _git(repo, "rev-parse", "HEAD"))[0].line() == (
        "assert-loss: tests/test_x.py::test_thin 2->1"
    )


def test_assert_loss_counts_pytest_raises(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    _on_dev(repo)
    _commit(
        repo,
        "tests/test_x.py",
        "import pytest\n\n"
        "def test_raises():\n    with pytest.raises(ValueError):\n        raise ValueError\n",
        "raises on dev",
    )
    _merge_dev(repo)
    _commit(repo, "tests/test_x.py", "def test_raises():\n    pass\n", "gone")
    line = compare_integrity(repo, _merge_base(repo), _git(repo, "rev-parse", "HEAD"))[0].line()
    assert line == "assert-loss: tests/test_x.py::test_raises 1->0"


def test_assert_loss_counts_callable_pytest_raises(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    _on_dev(repo)
    _commit(
        repo,
        "tests/test_x.py",
        "import pytest\n\ndef test_x():\n    pytest.raises(ValueError, int, 'bad')\n",
        "callable raises on dev",
    )
    _merge_dev(repo)
    _commit(repo, "tests/test_x.py", "def test_x():\n    pass\n", "gone")
    assert [f.line() for f in compare_integrity(repo, _merge_base(repo), _git(repo, "rev-parse", "HEAD"))] == [
        "assert-loss: tests/test_x.py::test_x 1->0"
    ]


def test_config_change_conftest(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    _on_dev(repo)
    _commit(repo, "tests/conftest.py", "import pytest\n", "conf on dev")
    _merge_dev(repo)
    _commit(repo, "tests/conftest.py", "import pytest\n\npytest_plugins = []\n", "more")
    assert compare_integrity(repo, _merge_base(repo), _git(repo, "rev-parse", "HEAD"))[0].line() == (
        "config-change: tests/conftest.py"
    )


def test_config_change_pyproject_pytest_table(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    _on_dev(repo)
    _commit(repo, "pyproject.toml", "[project]\nname = 'x'\n", "proj on dev")
    _merge_dev(repo)
    _commit(
        repo,
        "pyproject.toml",
        "[project]\nname = 'x'\n\n[tool.pytest.ini_options]\naddopts = '-q'\n",
        "pytest",
    )
    assert compare_integrity(repo, _merge_base(repo), _git(repo, "rev-parse", "HEAD"))[0].line() == (
        "config-change: pyproject.toml"
    )


def test_config_change_indented_pyproject_pytest_table(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    _on_dev(repo)
    _commit(repo, "pyproject.toml", "  [tool.pytest.ini_options]\n  addopts = '-q'\n", "indented on dev")
    _merge_dev(repo)
    _commit(repo, "pyproject.toml", "  [tool.pytest.ini_options]\n  addopts = '--ignore=tests'\n", "edit")
    assert compare_integrity(repo, _merge_base(repo), _git(repo, "rev-parse", "HEAD"))[0].line() == (
        "config-change: pyproject.toml"
    )


def test_config_change_quoted_pyproject_pytest_table(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    _on_dev(repo)
    _commit(repo, "pyproject.toml", '["tool"."pytest"."ini_options"]\naddopts = "-q"\n', "quoted on dev")
    _merge_dev(repo)
    _commit(repo, "pyproject.toml", '["tool"."pytest"."ini_options"]\naddopts = "--ignore=tests"\n', "edit")
    assert [f.line() for f in compare_integrity(repo, _merge_base(repo), _git(repo, "rev-parse", "HEAD"))] == [
        "config-change: pyproject.toml"
    ]


def test_pyproject_change_outside_pytest_table_is_ignored(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    _on_dev(repo)
    _commit(repo, "pyproject.toml", "[project]\nname = 'x'\n", "proj on dev")
    _merge_dev(repo)
    _commit(repo, "pyproject.toml", "[project]\nname = 'y'\n", "rename")
    assert compare_integrity(repo, _merge_base(repo), _git(repo, "rev-parse", "HEAD")) == []


def test_cli_json_and_exit_codes(tmp_path: Path, capsys) -> None:
    repo = _repo(tmp_path, roadmap=True)
    _on_dev(repo)
    _commit(repo, "tests/test_x.py", "def test_a():\n    assert 1\n", "on dev")
    _merge_dev(repo)
    head = _git(repo, "rev-parse", "HEAD")
    with pytest.raises(SystemExit) as ok:
        integrity_cli.main(["T1", "--repo-root", str(repo), "--ref", head, "--json"])
    assert ok.value.code == 0
    assert capsys.readouterr().out.strip() == ""
    _commit(repo, "tests/test_x.py", "def test_a():\n    pass\n", "weaken")
    head = _git(repo, "rev-parse", "HEAD")
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
    repo = _repo(tmp_path, roadmap=True)
    _on_dev(repo)
    _commit(repo, rel, base_text, "on dev")
    _merge_dev(repo)
    if ref_text is None:
        _git(repo, "rm", "-q", rel)
        _git(repo, "commit", "-qm", "delete")
    else:
        _commit(repo, rel, ref_text, "change")
    with pytest.raises(SystemExit) as ex:
        integrity_cli.main(["T1", "--repo-root", str(repo), "--ref", _git(repo, "rev-parse", "HEAD")])
    assert ex.value.code == 1
    assert capsys.readouterr().out == expected + "\n"


def test_cli_text_mode_unchanged_ref_exits_zero_silently(tmp_path: Path, capsys) -> None:
    repo = _repo(tmp_path, roadmap=True)
    _on_dev(repo)
    _commit(repo, "tests/test_x.py", _TEST_SRC, "on dev")
    _merge_dev(repo)
    with pytest.raises(SystemExit) as ex:
        integrity_cli.main(["T1", "--repo-root", str(repo), "--ref", _git(repo, "rev-parse", "HEAD")])
    assert ex.value.code == 0
    assert capsys.readouterr().out == ""


def test_nested_project_root_reports_git_root_paths(tmp_path: Path, capsys) -> None:
    repo = _repo(tmp_path, roadmap=True, project="sr")
    _on_dev(repo)
    _commit(repo, "sr/tests/test_in.py", _TEST_SRC, "inside the project")
    _commit(repo, "tests/test_out.py", _TEST_SRC, "outside the project")
    _merge_dev(repo)
    _commit(repo, "sr/tests/test_in.py", "def test_a():\n    pass\n", "weaken inside")
    _git(repo, "rm", "-q", "tests/test_out.py")
    _git(repo, "commit", "-qm", "delete outside")
    head = _git(repo, "rev-parse", "HEAD")
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
