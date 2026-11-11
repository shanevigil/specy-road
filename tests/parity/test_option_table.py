"""The options ``specy_road.cli_args`` declares keep each command's parse behaviour.

``golden/option_table.json`` was written from the parsers before the declarations moved there: per
command and option, the action, type, choices, required flag, default, destination, nargs and
metavar. Help strings are left out; the transcript test allows those options' help to change.
"""

from __future__ import annotations

import argparse
import json

import pytest

from tests.parity.help_surface import command_tree
from tests.parity.support import GOLDEN, REGEN

pytestmark = pytest.mark.parity

TABLE = GOLDEN / "option_table.json"
SHARED_OPTIONS = ("--json", "--ref", "--model", "--base", "--remote")


def _row(action: argparse.Action) -> dict:
    return {
        "action": type(action).__name__,
        "type": getattr(action.type, "__name__", action.type),
        "choices": None if action.choices is None else list(action.choices),
        "required": action.required,
        "default": action.default,
        "dest": action.dest,
        "nargs": action.nargs,
        "metavar": action.metavar,
    }


def option_table() -> dict[str, dict]:
    """``{"specy-road worker list --json": row}`` for every shared option on every parser."""
    table = {}
    for path, parser in command_tree():
        for action in [] if parser is None else parser._actions:
            for option in set(action.option_strings) & set(SHARED_OPTIONS):
                table[" ".join((*path, option))] = _row(action)
    return dict(sorted(table.items()))


def test_shared_options_parse_as_the_table_records() -> None:
    table = option_table()
    if REGEN:
        TABLE.write_text(json.dumps(table, indent=1) + "\n", encoding="utf-8")
        return
    assert table == json.loads(TABLE.read_text(encoding="utf-8"))
