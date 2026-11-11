"""One command-error base, printed and turned into an exit code in one place."""

from __future__ import annotations

import ast
import argparse
from pathlib import Path

import pytest

from specy_road.brainstorm_research import ResearchError
from specy_road.brainstorm_session import BrainstormError
from specy_road.bundled_scripts.review_node import ReviewError
from specy_road.cli_entry import run_handler
from specy_road.constitution_scaffold import ConstitutionExistsError
from specy_road.errors import SpecyError
from specy_road.finish_land_deterministic import DeterministicResolveError
from specy_road.harness_facts import HarnessFactsError
from specy_road.nested_repos import NestedRepoError
from specy_road.review_delegate import DelegateError
from specy_road.review_signing import SigningError
from specy_road.review_target import ReviewTargetError
from specy_road.roster_generate import RosterError
from specy_road.worker_lock import WorkerError
from specy_road.worker_state import LeaseError
from specy_road.worktree_env import EnvSetupError
from specy_road.worktree_prune import PruneError

REPO = Path(__file__).resolve().parents[1]

# Handlers whose removal would change the printed text. Recorded with the census.
KEPT_PRINT_AND_EXIT = {
    ("specy_road/nested_repos.py", ("NestedRepoError",)),
    ("specy_road/review_policy_pin.py", ("ReviewTargetError", "PolicyUnreadable")),
    (
        "specy_road/bundled_scripts/mark_implementation_reviewed.py",
        ("SigningError", "ReviewRunBusy", "SafeWriteError"),
    ),
}

COMMAND_ERRORS = (
    "WorkerError",
    "LeaseError",
    "DelegateError",
    "ReviewError",
    "BrainstormError",
    "ResearchError",
    "ReviewTargetError",
    "SigningError",
    "EnvSetupError",
    "RosterError",
    "PruneError",
    "NestedRepoError",
    "HarnessFactsError",
    "DeterministicResolveError",
    "ConstitutionExistsError",
)


def _caught(handler: ast.ExceptHandler) -> tuple[str, ...]:
    type_node = handler.type
    elements = type_node.elts if isinstance(type_node, ast.Tuple) else [type_node]
    names = []
    for element in elements:
        if isinstance(element, ast.Name):
            names.append(element.id)
        elif isinstance(element, ast.Attribute):
            names.append(element.attr)
    return tuple(names)


def _is_print(stmt: ast.stmt) -> bool:
    return (
        isinstance(stmt, ast.Expr)
        and isinstance(stmt.value, ast.Call)
        and (
            (isinstance(stmt.value.func, ast.Name) and stmt.value.func.id == "print")
            or (isinstance(stmt.value.func, ast.Attribute) and stmt.value.func.attr == "print")
        )
    )


def _is_sys_exit(stmt: ast.stmt) -> bool:
    return (
        isinstance(stmt, ast.Expr)
        and isinstance(stmt.value, ast.Call)
        and isinstance(stmt.value.func, ast.Attribute)
        and stmt.value.func.attr == "exit"
    )


def _is_system_exit(stmt: ast.stmt) -> bool:
    if not isinstance(stmt, ast.Raise) or stmt.exc is None:
        return False
    exc = stmt.exc
    func = exc.func if isinstance(exc, ast.Call) else exc
    return (isinstance(func, ast.Name) and func.id == "SystemExit") or (
        isinstance(func, ast.Attribute) and func.attr == "SystemExit"
    )


def _is_return_int(stmt: ast.stmt) -> bool:
    value = stmt.value if isinstance(stmt, ast.Return) else None
    return isinstance(value, ast.Constant) and type(value.value) is int


def _print_and_exit(handler: ast.ExceptHandler) -> bool:
    if not any(name in COMMAND_ERRORS for name in _caught(handler)):
        return False
    return all(
        _is_print(stmt) or _is_sys_exit(stmt) or _is_system_exit(stmt) or _is_return_int(stmt)
        for stmt in handler.body
    )


def _matches() -> set[tuple[str, tuple[str, ...]]]:
    found = set()
    for path in (REPO / "specy_road").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        rel = path.relative_to(REPO).as_posix()
        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler) and _print_and_exit(node):
                found.add((rel, _caught(node)))
    return found


def test_print_and_exit_handlers_are_only_the_named_exceptions() -> None:
    assert _matches() == KEPT_PRINT_AND_EXIT


@pytest.mark.parametrize(
    ("error", "parent"),
    [
        (WorkerError("missing"), Exception),
        (LeaseError("leased"), WorkerError),
        (DelegateError("refused"), Exception),
        (ReviewError("failed"), Exception),
        (BrainstormError("unreadable"), ValueError),
        (ResearchError("disabled"), Exception),
        (ReviewTargetError("no branch"), Exception),
        (SigningError("no key"), Exception),
        (EnvSetupError("copy failed"), Exception),
        (RosterError("no profile"), ValueError),
        (PruneError("not a worktree"), RuntimeError),
        (NestedRepoError("no checkout"), RuntimeError),
        (HarnessFactsError("bad fixture"), ValueError),
        (DeterministicResolveError("abort"), RuntimeError),
        (ConstitutionExistsError(("constitution/purpose.md",)), Exception),
    ],
)
def test_each_command_error_keeps_its_base_and_carries_an_exit_code(
    error: SpecyError, parent: type,
) -> None:
    assert isinstance(error, SpecyError)
    assert isinstance(error, parent)
    assert error.exit_code == 1
    assert str(error)


@pytest.mark.parametrize(
    ("error", "code"),
    [
        (SpecyError("boom", 4), 4),
        (WorkerError("missing"), 1),
        (RosterError("no profile"), 1),
    ],
)
def test_run_handler_prints_a_specy_error_and_exits_with_its_code(
    error: SpecyError, code: int, capsys: pytest.CaptureFixture[str],
) -> None:
    def fail(ns: argparse.Namespace) -> int:
        raise error

    with pytest.raises(SystemExit) as caught:
        run_handler(argparse.Namespace(func=fail))
    assert caught.value.code == code
    assert capsys.readouterr().err == f"error: {error}\n"
