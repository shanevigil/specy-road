"""specy-road integrity: per-function Python findings (removed tests, new skips, lost asserts)."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.integrity_repo_helpers import commit, git, make_repo, merge_base, merge_dev, on_dev
from specy_road.integrity import compare_integrity


def test_removed_test_function(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    on_dev(repo)
    commit(
        repo,
        "tests/test_x.py",
        "def test_keep():\n    assert 1\n\ndef test_gone():\n    assert 2\n",
        "both on dev",
    )
    merge_dev(repo)
    commit(repo, "tests/test_x.py", "def test_keep():\n    assert 1\n", "drop one")
    findings = compare_integrity(repo, merge_base(repo), git(repo, "rev-parse", "HEAD"))
    assert [f.line() for f in findings if f.kind == "removed-test"] == ["removed-test: tests/test_x.py::test_gone"]


def test_new_skip_decorator(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    on_dev(repo)
    commit(repo, "tests/test_x.py", "def test_later():\n    assert 1\n", "on dev")
    merge_dev(repo)
    commit(
        repo,
        "tests/test_x.py",
        "import pytest\n\n@pytest.mark.skip\n"
        "def test_later():\n    assert 1\n",
        "skip",
    )
    assert compare_integrity(repo, merge_base(repo), git(repo, "rev-parse", "HEAD"))[0].line() == (
        "new-skip: tests/test_x.py::test_later"
    )


def test_new_skip_bare_xfail_decorator(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    on_dev(repo)
    commit(repo, "tests/test_x.py", "def test_later():\n    assert 1\n", "on dev")
    merge_dev(repo)
    commit(
        repo,
        "tests/test_x.py",
        "import pytest\n\n@pytest.mark.xfail\n"
        "def test_later():\n    assert 1\n",
        "bare xfail",
    )
    assert [f.line() for f in compare_integrity(repo, merge_base(repo), git(repo, "rev-parse", "HEAD"))] == [
        "new-skip: tests/test_x.py::test_later"
    ]


def test_new_skip_call(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    on_dev(repo)
    commit(repo, "tests/test_x.py", "def test_later():\n    assert 1\n", "on dev")
    merge_dev(repo)
    commit(
        repo,
        "tests/test_x.py",
        "import pytest\n\n"
        "def test_later():\n    pytest.skip('nope')\n    assert 1\n",
        "skip call",
    )
    assert compare_integrity(repo, merge_base(repo), git(repo, "rev-parse", "HEAD"))[0].line() == (
        "new-skip: tests/test_x.py::test_later"
    )


def test_unrelated_decorator_named_skip_is_not_a_skip(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    on_dev(repo)
    commit(repo, "tests/test_x.py", "def test_x():\n    assert 1\n", "on dev")
    merge_dev(repo)
    commit(
        repo,
        "tests/test_x.py",
        "class custom:\n    skip = staticmethod(lambda f: f)\n\n"
        "@custom.skip\ndef test_x():\n    assert 1\n",
        "identity decorator",
    )
    assert compare_integrity(repo, merge_base(repo), git(repo, "rev-parse", "HEAD")) == []


def test_assert_loss(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    on_dev(repo)
    commit(repo, "tests/test_x.py", "def test_thin():\n    assert 1\n    assert 2\n", "two on dev")
    merge_dev(repo)
    commit(repo, "tests/test_x.py", "def test_thin():\n    assert 1\n", "one")
    assert compare_integrity(repo, merge_base(repo), git(repo, "rev-parse", "HEAD"))[0].line() == (
        "assert-loss: tests/test_x.py::test_thin 2->1"
    )


def test_assert_loss_counts_pytest_raises(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    on_dev(repo)
    commit(
        repo,
        "tests/test_x.py",
        "import pytest\n\n"
        "def test_raises():\n    with pytest.raises(ValueError):\n        raise ValueError\n",
        "raises on dev",
    )
    merge_dev(repo)
    commit(repo, "tests/test_x.py", "def test_raises():\n    pass\n", "gone")
    line = compare_integrity(repo, merge_base(repo), git(repo, "rev-parse", "HEAD"))[0].line()
    assert line == "assert-loss: tests/test_x.py::test_raises 1->0"


def test_assert_loss_counts_callable_pytest_raises(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    on_dev(repo)
    commit(
        repo,
        "tests/test_x.py",
        "import pytest\n\ndef test_x():\n    pytest.raises(ValueError, int, 'bad')\n",
        "callable raises on dev",
    )
    merge_dev(repo)
    commit(repo, "tests/test_x.py", "def test_x():\n    pass\n", "gone")
    assert [f.line() for f in compare_integrity(repo, merge_base(repo), git(repo, "rev-parse", "HEAD"))] == [
        "assert-loss: tests/test_x.py::test_x 1->0"
    ]


_COND_BASE = (
    "def test_cond():\n    assert 1\n    assert 2\n"
    "def test_skip():\n    assert 1\n"
    "def test_gone():\n    assert 1\n"
)
_COND_REF = (
    "def test_cond():\n    assert 1\n"
    "@pytest.mark.skip\ndef test_skip():\n    assert 1\n"
)
# each wrapper puts the tests in a control-flow block pytest still collects from
_COND_WRAPPERS = {
    "if": ("if True:\n{0}", ""),
    "else": ("if False:\n    pass\nelse:\n{0}", ""),
    "try": ("try:\n{0}except ImportError:\n    pass\n", ""),
    "except": ("try:\n    import nonexistent_module\nexcept ImportError:\n{0}", ""),
    "finally": ("try:\n    pass\nfinally:\n{0}", ""),
    "with": ("with open(__file__):\n{0}", ""),
    "for": ("for _ in [1]:\n{0}", ""),
    "while": ("while True:\n{0}    break\n", ""),
    "match": ("match 1:\n    case _:\n{1}", ""),
    "class-if": ("class TestK:\n    if True:\n{1}", "TestK::"),
}


def _indent(text: str, levels: int) -> str:
    return "".join("    " * levels + line + "\n" for line in text.splitlines())


@pytest.mark.parametrize("kind", sorted(_COND_WRAPPERS))
def test_tests_inside_control_flow_are_compared(tmp_path: Path, kind: str) -> None:
    wrapper, prefix = _COND_WRAPPERS[kind]
    repo = make_repo(tmp_path)
    on_dev(repo)
    base = wrapper.format(_indent(_COND_BASE, 1), _indent(_COND_BASE, 2))
    commit(repo, "tests/test_c.py", "import pytest\n\n" + base, "conditional tests on dev")
    merge_dev(repo)
    ref = wrapper.format(_indent(_COND_REF, 1), _indent(_COND_REF, 2))
    commit(repo, "tests/test_c.py", "import pytest\n\n" + ref, "weaken")
    assert [f.line() for f in compare_integrity(repo, merge_base(repo), git(repo, "rev-parse", "HEAD"))] == [
        f"assert-loss: tests/test_c.py::{prefix}test_cond 2->1",
        f"new-skip: tests/test_c.py::{prefix}test_skip",
        f"removed-test: tests/test_c.py::{prefix}test_gone",
    ]


def test_branch_definitions_of_one_test_are_each_compared(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    on_dev(repo)
    both = "if X:\n    def test_a():\n        assert 1\nelse:\n    def test_a():\n        assert 2\n"
    commit(repo, "tests/test_x.py", "X = 1\n" + both, "two branches on dev")
    merge_dev(repo)
    weakened = both.replace("assert 1", "pass").replace("    def test_a():\n        assert 2",
                                                         "    @unittest.skip('x')\n    def test_a():\n        assert 2")
    commit(repo, "tests/test_x.py", "import unittest\nX = 1\n" + weakened, "weaken the if branch, skip the else")
    assert [f.line() for f in compare_integrity(repo, merge_base(repo), git(repo, "rev-parse", "HEAD"))] == [
        "assert-loss: tests/test_x.py::test_a 2->1",
        "new-skip: tests/test_x.py::test_a",
    ]


def test_skip_decorator_on_class_skips_its_methods(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    on_dev(repo)
    cls = "class TestK:\n    def test_m(self):\n        assert 1\n"
    commit(repo, "tests/test_x.py", cls, "class on dev")
    merge_dev(repo)
    commit(repo, "tests/test_x.py", "import pytest\n\n@pytest.mark.skip\n" + cls, "skip the class")
    assert [f.line() for f in compare_integrity(repo, merge_base(repo), git(repo, "rev-parse", "HEAD"))] == [
        "new-skip: tests/test_x.py::TestK::test_m"
    ]


def test_function_defined_inside_a_function_is_not_a_test(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    on_dev(repo)
    commit(repo, "tests/test_x.py", "def helper():\n    def test_inner():\n        assert 1\n", "on dev")
    merge_dev(repo)
    commit(repo, "tests/test_x.py", "def helper():\n    pass\n", "drop the inner def")
    assert compare_integrity(repo, merge_base(repo), git(repo, "rev-parse", "HEAD")) == []
