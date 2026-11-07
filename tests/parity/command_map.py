"""command_map.yaml rows applied to the golden inventory as declared deltas.

A row is ``{old: <invocation>, new: <invocation>, allowed: <one line>}``. An invocation is command
words optionally followed by option strings (``specy-road doctor --prune``). One rule per side:

* ``old`` with options: those options may be gone from that command.
* ``old`` without options: that command and the commands under it may be gone from the CLI; one
  still present (a hidden alias) must match its golden. Its parent may stop listing it.
* ``new`` with options: those options may be added to that command.
* ``new`` without options, absent from the golden: that command and the commands under it are
  expected as the CLI has them. Its parent may list it.

Nothing else changes, so every other difference still fails. The names a row covers (its ``old``
and ``new`` commands, and the commands it adds or removes under them) may have a changed ``--help``
transcript; each still needs a golden transcript. A parent whose help lists a changed subcommand is
not covered by that row: it needs its own row (``old`` and ``new`` both the parent).
"""

from __future__ import annotations

import copy
import itertools
from collections.abc import Iterable

import yaml

from tests.parity.support import COMMAND_MAP


def command_map_rows() -> list[dict]:
    """Rows of command_map.yaml."""
    doc = yaml.safe_load(COMMAND_MAP.read_text(encoding="utf-8")) or {}
    return list(doc.get("rows") or [])


def split_invocation(text: str | None) -> tuple[str, set[str]]:
    """``"specy-road doctor --prune"`` -> ``("specy-road doctor", {"--prune"})``."""
    words = str(text or "").split()
    command = list(itertools.takewhile(lambda w: not w.startswith("-"), words))
    return " ".join(command), set(words[len(command) :])


def _under(command: str, keys: Iterable[str]) -> list[str]:
    return [k for k in keys if k == command or k.startswith(command + " ")]


def _relist(expected: dict[str, dict], key: str, present: bool) -> None:
    """Make the parent of ``key`` list (or stop listing) it as a subcommand."""
    parent, _, name = key.rpartition(" ")
    if parent in expected and " " in parent:  # roots list the registered names, not subcommands
        subs = set(expected[parent]["subcommands"])
        expected[parent]["subcommands"] = sorted(subs | {name} if present else subs - {name})


def _apply_old(row: dict, golden: dict, current: dict, expected: dict, covered: set) -> list[str]:
    """Apply a row's ``old`` side; return its errors."""
    old, options = split_invocation(row.get("old"))
    if not old:
        return []
    if old not in golden:
        return [f"command_map row old {row.get('old')!r}: not in the golden inventory"]
    if options:
        expected[old]["options"] = sorted(set(expected[old]["options"]) - options)
        unknown = sorted(options - set(golden[old]["options"]))
        return (
            [f"command_map row old {row.get('old')!r}: {unknown} not in the golden"]
            if unknown
            else []
        )
    for key in _under(old, golden):
        if key not in current:
            covered.add(key)
            del expected[key]
            _relist(expected, key, present=False)
    return []


def _apply_new(row: dict, golden: dict, current: dict, expected: dict, covered: set) -> None:
    """Apply a row's ``new`` side."""
    new, options = split_invocation(row.get("new"))
    if new and new not in golden:
        for key in sorted(_under(new, current)):
            covered.add(key)
            expected[key] = copy.deepcopy(current[key])
            _relist(expected, key, present=True)
    if new and options and new in expected:
        expected[new]["options"] = sorted(set(expected[new]["options"]) | options)


def apply_rows(
    golden: dict[str, dict], current: dict[str, dict], rows: list[dict]
) -> tuple[dict[str, dict], set[str], list[str]]:
    """The golden inventory with each row applied, the names the rows cover, and row errors.

    A row whose ``old`` names a command or option that is not in the golden is an error, so a stale
    or mistyped row cannot silently authorise nothing.
    """
    expected = copy.deepcopy(golden)
    covered: set[str] = set()
    errors: list[str] = []
    for row in rows:
        covered |= {c for c in (split_invocation(row.get(s))[0] for s in ("old", "new")) if c}
        errors += _apply_old(row, golden, current, expected, covered)
        _apply_new(row, golden, current, expected, covered)
    return expected, covered, errors


def inventory_differences(expected: dict[str, dict], current: dict[str, dict]) -> list[str]:
    """Each difference between the expected and the current inventory, naming its command."""
    problems = []
    for key in sorted(expected.keys() | current.keys()):
        if key not in current:
            problems.append(f"{key}: in the golden inventory, gone from the CLI")
        elif key not in expected:
            problems.append(f"{key}: in the CLI, not in the golden inventory")
        else:
            for field in sorted(expected[key].keys() | current[key].keys()):
                old, new = expected[key].get(field), current[key].get(field)
                if old != new and isinstance(old, list) and isinstance(new, list):
                    problems.append(
                        f"{key}: {field} lost {sorted(set(old) - set(new))}, "
                        f"gained {sorted(set(new) - set(old))}"
                    )
                elif old != new:
                    problems.append(f"{key}: {field} was {old!r}, now {new!r}")
    return problems
