"""The worklist item-id rule: a pytest parameter is kept, including a literal path."""

from __future__ import annotations

import importlib.util

import pytest

from tests.support import REPO

_spec = importlib.util.spec_from_file_location(
    "test_dedupe_worklist", REPO / "scripts" / "test_dedupe_worklist.py",
)
worklist = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(worklist)

_PREFIX = str(REPO) + "/"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (
            "tests/flows/review/test_review_concurrent_writers.py"
            "::test_unknown_absolute_or_dotdot_id_creates_nothing[/abs-node]",
            "tests/flows/review/test_review_concurrent_writers.py"
            "::test_unknown_absolute_or_dotdot_id_creates_nothing[/abs-node]",
        ),
        (
            "tests/unit/test_grind_session_implement.py"
            "::test_only_the_claude_cli_takes_the_claude_path[/opt/homebrew/bin/claude -p x-True]",
            "tests/unit/test_grind_session_implement.py"
            "::test_only_the_claude_cli_takes_the_claude_path[/opt/homebrew/bin/claude -p x-True]",
        ),
        (
            "tests/flows/worker/test_claude_config_dir.py"
            "::test_the_variable_is_taken_literally[~/account]",
            "tests/flows/worker/test_claude_config_dir.py"
            "::test_the_variable_is_taken_literally[~/account]",
        ),
        (
            "tests/x.py::test_route[/api/status]",
            "tests/x.py::test_route[/api/status]",
        ),
        (
            _PREFIX + "tests/x.py::test_file",
            "tests/x.py::test_file",
        ),
        (
            "tests/x.py::test_from[" + _PREFIX + "specy_road/templates/a]",
            "tests/x.py::test_from[specy_road/templates/a]",
        ),
        (
            "tests/x.py::test_home[/home/alice/proj]",
            "tests/x.py::test_home[<path>/proj]",
        ),
        (
            "tests/x.py::test_users[/Users/alice/proj]",
            "tests/x.py::test_users[<path>/proj]",
        ),
        (
            "tests/x.py::test_host[Ada-MacBook-Pro.local]",
            "tests/x.py::test_host[<path>]",
        ),
        (
            "tests/x.py::test_sr[sr/work/note]",
            "tests/x.py::test_sr[<path>]",
        ),
        (
            "tests/x.py::test_win[C:\\Users\\alice\\proj]",
            "tests/x.py::test_win[<path>\\proj]",
        ),
        (
            "/tmp/elsewhere.py::test_outside[/abs-node]",
            "<path>[/abs-node]",
        ),
    ],
)
def test_item_id_keeps_a_literal_parameter(raw: str, expected: str) -> None:
    assert worklist.normalize_test_id(raw) == expected
