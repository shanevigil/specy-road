"""Item ids stay the collected pytest id, except a documented stable form.

A parameter is kept verbatim. A collected id that contains the repository
root, the home directory, a temp-directory prefix or the hostname is written
as ``file::function[#index]`` and ``item_id_problems`` accepts only that form.
"""

from __future__ import annotations

import importlib.util
import socket
from pathlib import Path

import pytest

from tests.support import REPO

_spec = importlib.util.spec_from_file_location(
    "test_dedupe_worklist", REPO / "scripts" / "test_dedupe_worklist.py",
)
worklist = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(worklist)

_PREFIX = str(REPO) + "/"


def _other_home() -> str:
    """A home path hygiene accepts and that is not this machine's."""
    for path in ("/home/runner/proj", "/Users/Shared/proj", "/srv/runner/proj"):
        if str(Path.home()) not in path:
            return path
    return "/srv/runner/proj"


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
            "tests/x.py::test_rel[../../../../tmp/escaped]",
            "tests/x.py::test_rel[../../../../tmp/escaped]",
        ),
        (
            "tests/x.py::test_sr[sr/work/note]",
            "tests/x.py::test_sr[sr/work/note]",
        ),
        (
            "tests/x.py::test_win[C:\\proj\\data]",
            "tests/x.py::test_win[C:\\proj\\data]",
        ),
        (
            f"tests/x.py::test_home[{_other_home()}]",
            f"tests/x.py::test_home[{_other_home()}]",
        ),
        (
            "tests/x.py::test_users[/Users/Shared/proj]",
            "tests/x.py::test_users[/Users/Shared/proj]",
        ),
        (
            "tests/x.py::test_host[not-this-host]",
            "tests/x.py::test_host[not-this-host]",
        ),
    ],
)
def test_item_id_keeps_a_literal_parameter(raw: str, expected: str) -> None:
    assert worklist.normalize_test_id(raw) == expected


def test_machine_path_uses_the_parameter_index() -> None:
    literal = "tests/x.py::test_home[/abs-node]"
    home = f"tests/x.py::test_home[{Path.home()}/proj]"
    repo = "tests/x.py::test_from[" + _PREFIX + "specy_road/templates/a]"
    temp = "tests/x.py::test_tmp[/tmp/c]"
    host = f"tests/x.py::test_host[{socket.gethostname()}]"
    outside = "/tmp/elsewhere.py::test_outside[/abs-node]"
    assert worklist.normalize_test_id(literal) == literal
    assert worklist.normalize_test_id(home, [literal, home]) == (
        "tests/x.py::test_home[#1]"
    )
    assert worklist.normalize_test_id(repo, [repo]) == "tests/x.py::test_from[#0]"
    assert worklist.normalize_test_id(temp, [temp]) == "tests/x.py::test_tmp[#0]"
    assert worklist.normalize_test_id(host, [host]) == "tests/x.py::test_host[#0]"
    assert worklist.normalize_test_id(outside, [outside]) == (
        "elsewhere.py::test_outside[#0]"
    )


def test_check_matches_collection_or_the_stable_form() -> None:
    literal = "tests/x.py::test_home[/abs-node]"
    machine = f"tests/x.py::test_home[{Path.home()}/proj]"
    collected = [literal, machine]
    stable = "tests/x.py::test_home[#1]"
    assert worklist.item_id_problems([literal, stable], collected) == []
    assert worklist.item_id_problems(["tests/x.py::test_route[/missing]"], collected)
    assert worklist.item_id_problems([machine], collected)
    assert worklist.item_id_problems(["tests/x.py::test_home[#0]"], collected)
