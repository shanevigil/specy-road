"""The cleanup commands select exactly the reconciliation table's rows; apply removes exactly them.

``reconciliation.yaml`` fixes each fixture row's action under every old cleanup command and every
new ``doctor --prune`` form; ``golden/old_selections.json`` is what the old commands selected
before the planner. A row whose action differs from that record must be a decided reduction.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest
import yaml

from tests.parity.cleanup import fixture, record
from tests.parity.support import cli_env, run_cli

pytestmark = pytest.mark.parity

TABLE = yaml.safe_load((Path(__file__).parent / "reconciliation.yaml").read_text(encoding="utf-8"))
COMMANDS = TABLE["commands"]
OLD = json.loads(record.GOLDEN.read_text(encoding="utf-8"))


def _actions(entries: list[dict]) -> dict[str, dict]:
    return {a["row"]: {"action": a["action"], "reason": a["reason"]} for a in entries}


@pytest.fixture(scope="module")
def current() -> dict[str, dict[str, dict]]:
    return {name: _actions(found) for name, found in record.selections(new_forms=True).items()}


@pytest.mark.parametrize("name", sorted(COMMANDS))
def test_each_command_selects_the_tables_rows(name: str, current) -> None:
    assert current[name] == COMMANDS[name]["rows"]


@pytest.mark.parametrize("name", sorted(n for n, c in COMMANDS.items() if c["old"]))
def test_every_change_from_the_old_selection_is_a_decided_reduction(name: str) -> None:
    old = {row: a["action"] for row, a in _actions(OLD[COMMANDS[name]["old"]]).items()}
    new = {row: a["action"] for row, a in COMMANDS[name]["rows"].items()}
    changed = {row for row in old.keys() | new.keys() if old.get(row) != new.get(row)}
    assert changed == set(COMMANDS[name].get("decided") or {})
    assert not [row for row in changed if new.get(row) == "remove"], "a removal the old lacked"


def _removed(actions: dict[str, dict]) -> set[str]:
    return {row for row, a in actions.items() if a["action"] == "remove"}


def test_every_new_form_names_the_old_commands_it_replaces() -> None:
    assert all(c.get("replaces") for n, c in COMMANDS.items() if n.startswith("doctor --prune"))


@pytest.mark.parametrize(("name", "old"), sorted(
    (n, o) for n, c in COMMANDS.items() for o in c.get("replaces") or {}))
def test_a_new_form_removes_nothing_the_command_it_replaces_kept(name: str, old: str) -> None:
    """A deprecation pointer never leads to more removals than its old command made, unless the
    table names another old command that removed that row."""
    beyond = _removed(COMMANDS[name]["rows"]) - _removed(_actions(OLD[old]))
    allowed = COMMANDS[name]["replaces"][old]
    assert beyond == set(allowed)
    assert all(row in _removed(_actions(OLD[by])) for row, by in allowed.items())


def _applied(argv: list[str]) -> tuple[dict[str, bool], bool, str]:
    with tempfile.TemporaryDirectory() as tmp:
        repo = fixture.build(Path(tmp))
        result = run_cli("specy_road.cli", [*argv, "--repo-root", str(repo)], cwd=repo,
                         env=cli_env())
        return fixture.present(repo), fixture.content_kept(repo), result.stderr


@pytest.mark.parametrize(("name", "argv"), [
    ("doctor --prune", ["doctor", "--prune", "--yes"]),
    ("branches prune", ["branches", "prune", "--delete"]),
])
def test_applying_removes_exactly_the_planned_rows(name: str, argv: list[str]) -> None:
    present, kept, err = _applied(argv)

    planned = {row for row, a in COMMANDS[name]["rows"].items() if a["action"] == "remove"}
    assert {row for row, there in present.items() if not there} == planned, err
    assert kept


@pytest.mark.parametrize(("argv", "old", "new"), [
    (["branches", "prune"], "branches prune", "doctor --prune --kind branches"),
    (["registry-prune"], "registry-prune", "doctor --prune --kind registry"),
    (["doctor", "--fix"], "doctor --fix", "doctor --prune"),
    (["grind-session", "--plan", "--delete-merged-branches"],
     "grind-session --delete-merged-branches", "doctor --prune --kind branches"),
])
def test_an_alias_prints_one_deprecation_line_naming_the_new_form(argv, old, new) -> None:
    _present, _kept, err = _applied(argv)

    lines = [line for line in err.splitlines() if "deprecated" in line]
    assert lines == [f"warning: `specy-road {old}` is deprecated and is removed in "
                     f"the release after 0.3.1; use `specy-road {new}`."]
