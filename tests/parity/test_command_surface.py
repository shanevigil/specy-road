"""The command surface matches its goldens: the inventory both ways, and each ``--help`` transcript.

A difference fails naming the command, subcommand or alias, unless a row of command_map.yaml
authorises it (old invocation, new invocation, allowed difference).
"""

from __future__ import annotations

import argparse
import json

import pytest

from tests.parity.help_surface import crawl, parse_help
from tests.parity.support import GOLDEN, REGEN, check_golden, command_map_rows, mapped, words

pytestmark = pytest.mark.parity

INVENTORY = GOLDEN / "inventory.json"
HELP = GOLDEN / "help"


def _help_file(key: str):
    return HELP / (key.replace(" ", "__") + ".txt")


def _golden_inventory() -> dict[str, dict]:
    return json.loads(INVENTORY.read_text(encoding="utf-8")) if INVENTORY.is_file() else {}


def _regenerate(surface: dict[str, dict]) -> None:
    HELP.mkdir(parents=True, exist_ok=True)
    for stale in HELP.glob("*.txt"):
        stale.unlink()
    for key, entry in surface.items():
        _help_file(key).write_text(entry["transcript"], encoding="utf-8")
    inventory = {key: surface[key]["inventory"] for key in sorted(surface)}
    INVENTORY.write_text(json.dumps(inventory, indent=1) + "\n", encoding="utf-8")


def inventory_differences(
    golden: dict[str, dict], current: dict[str, dict], rows: list[dict]
) -> list[str]:
    """Each unauthorised difference between two inventories, naming the command it is in."""
    problems = []
    for key in sorted(golden.keys() | current.keys()):
        if mapped(key, rows):
            continue
        if key not in current:
            problems.append(f"{key}: in the golden inventory, gone from the CLI")
        elif key not in golden:
            problems.append(f"{key}: in the CLI, not in the golden inventory")
        elif golden[key] != current[key]:
            for field in sorted(golden[key].keys() | current[key].keys()):
                old, new = golden[key].get(field), current[key].get(field)
                if old != new and isinstance(old, list) and isinstance(new, list):
                    problems.append(
                        f"{key}: {field} lost {sorted(set(old) - set(new))}, "
                        f"gained {sorted(set(new) - set(old))}"
                    )
                elif old != new:
                    problems.append(f"{key}: {field} was {old!r}, now {new!r}")
    return problems


def test_inventory_matches_golden_both_ways() -> None:
    surface = crawl()
    if REGEN:
        _regenerate(surface)
        return
    current = {key: entry["inventory"] for key, entry in surface.items()}
    problems = inventory_differences(_golden_inventory(), current, command_map_rows())
    assert not problems, "command surface changed:\n" + "\n".join(problems)


def test_inventory_starts_from_the_registered_names() -> None:
    from specy_road.cli import registered_agent_command_names

    roots = {key for key, entry in crawl().items() if len(entry["inventory"]["path"]) == 1}
    registered = {
        f"{prog} {name}"
        for prog, names in registered_agent_command_names().items()
        for name in names
    }
    assert roots == registered


@pytest.mark.parametrize("key", sorted(_golden_inventory()))
def test_help_transcript_matches_golden(key: str) -> None:
    rows = command_map_rows()
    entry = crawl().get(key)
    if mapped(key, rows):
        pytest.skip(f"{key} is a command_map.yaml row")
    if REGEN and entry is None:
        return  # regeneration already dropped its golden
    assert entry is not None, f"{key} has a golden transcript but is gone from the CLI"
    check_golden(_help_file(key), entry["transcript"], words)


@pytest.mark.parametrize(
    "nargs, usage_tail, passthrough",
    [
        (argparse.REMAINDER, "...", True),
        ("*", "[rest ...]", False),
    ],
)
def test_passthrough_is_read_from_usage(nargs, usage_tail: str, passthrough: bool) -> None:
    """The inventory's passthrough flag tells ``argparse.REMAINDER`` from a list positional."""
    parser = argparse.ArgumentParser(prog="specy-road demo")
    parser.add_argument("rest", nargs=nargs)
    text = parser.format_help()
    assert usage_tail in text
    assert parse_help(("specy-road", "demo"), text)["passthrough"] is passthrough
